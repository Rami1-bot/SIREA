# src/conexion_supabase.py
"""
Conexión a Supabase más robusta en Windows.

Por qué existe: la librería de Supabase abre por defecto UNA conexión HTTP/2 y la comparte entre todas las
sesiones de Streamlit (cada una corre en su propio hilo). En Windows eso produce, de forma intermitente,
errores como «[WinError 10035] No se puede completar de forma inmediata una operación de desbloqueo de
socket», «ConnectionTerminated» o «Invalid input ... in state CLOSED» (la conexión HTTP/2 compartida queda
en un estado inconsistente) y, a veces, un «400 Bad Request» de Cloudflare por una petición cortada.

Qué hace:
  * Usa HTTP/1.1 (un pool de conexiones independientes: no hay estado compartido que se corrompa).
  * Reintenta SOLO las lecturas (GET/HEAD) cuando la conexión se corta. Nunca reintenta escrituras
    (insertar, actualizar, borrar), para no duplicar ni repetir una acción.
  * Cierra las conexiones inactivas pronto (antes de que el servidor las cierre por su lado).

Se puede volver al comportamiento anterior con SUPABASE_HTTP2=true en el .env.
"""

import os
import time
from typing import Optional

import httpx

REINTENTOS_LECTURA = 3
ESPERA_BASE_SEGUNDOS = 0.4


class ClienteResiliente(httpx.Client):
    """httpx.Client que reintenta las lecturas (GET/HEAD) si la conexión se corta a mitad."""

    def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        if request.method not in ("GET", "HEAD"):
            return super().send(request, **kwargs)
        ultimo: Optional[Exception] = None
        for intento in range(REINTENTOS_LECTURA):
            try:
                return super().send(request, **kwargs)
            except httpx.TimeoutException:
                raise                                     # un tiempo agotado no se reintenta (triplicaría la espera)
            except httpx.TransportError as e:             # conexión cortada, reinicio de socket, protocolo, etc.
                ultimo = e
                if intento + 1 < REINTENTOS_LECTURA:
                    time.sleep(ESPERA_BASE_SEGUNDOS * (intento + 1))
        raise ultimo  # type: ignore[misc]


def crear_cliente_http(transport: Optional[httpx.BaseTransport] = None) -> httpx.Client:
    """Cliente httpx para Supabase (HTTP/1.1, reintento de lecturas, conexiones inactivas cortas)."""
    http2 = os.getenv("SUPABASE_HTTP2", "false").strip().lower() in ("1", "true", "si", "sí", "yes")
    return ClienteResiliente(
        http2=http2,
        timeout=httpx.Timeout(60.0, connect=15.0),
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=10, keepalive_expiry=15.0),
        follow_redirects=True,
        transport=transport,
    )


def crear_cliente_supabase(url: str, key: str):
    """create_client de Supabase usando la conexión robusta; si la librería no lo admite, usa la normal."""
    from supabase import create_client
    try:
        from supabase.lib.client_options import SyncClientOptions
        return create_client(url, key, options=SyncClientOptions(httpx_client=crear_cliente_http()))
    except Exception as e:                                # versión sin soporte: se conserva el comportamiento anterior
        print(f"⚠️ No se pudo usar la conexión robusta a Supabase ({e}); se usa la estándar.")
        return create_client(url, key)


# ============================================================
# DIAGNÓSTICO DE CONEXIÓN (SIREA 3.5)
# ============================================================
# Si el servidor de Supabase no se puede ubicar (DNS, sin internet, proxy o una URL mal escrita),
# cada consulta falla con «getaddrinfo failed» y la app muestra datos vacíos que parecen otro error
# (por ejemplo «AÑO NO PERMITIDO»). Esto lo detecta una vez y lo explica en pantalla.

_CACHE_DIAG: dict = {}
_ULTIMO_LOG: dict = {}
_MARCAS_SIN_RED = ("getaddrinfo", "11001", "11004", "name or service not known", "nodename nor servname",
                   "temporary failure in name resolution", "connecterror", "connection refused", "10061")


def es_error_de_conexion(error) -> bool:
    """True si el error es de red (no se ubica o no responde el servidor), no de datos."""
    texto = f"{type(error).__name__}: {error}".lower()
    return any(m in texto for m in _MARCAS_SIN_RED)


def registrar_error(mensaje: str, error=None, cada_segundos: int = 60) -> None:
    """print() del error; los de conexión se resumen en una línea por minuto (evita cientos de líneas)."""
    if error is not None and es_error_de_conexion(error):
        ahora = time.time()
        _ULTIMO_LOG["fallo"] = (ahora, str(error))     # lo usa diagnostico_conexion() aunque haya proxy
        if ahora - _ULTIMO_LOG.get("red", 0) < cada_segundos:
            return
        _ULTIMO_LOG["red"] = ahora
        print(f"⚠️ Sin conexión con la base de datos ({error}). {diagnostico_conexion() or ''} "
              f"Se omiten los avisos repetidos durante {cada_segundos} s.")
        return
    print(mensaje)


def host_supabase(url: Optional[str] = None) -> str:
    from urllib.parse import urlparse
    url = (url if url is not None else os.getenv("SUPABASE_URL", "")).strip().strip('"').strip("'")
    try:
        return (urlparse(url).hostname or "").strip()
    except Exception:
        return ""


def diagnostico_conexion(url: Optional[str] = None, cada_segundos: int = 60) -> Optional[str]:
    """
    None si el servidor de SUPABASE_URL se puede ubicar; si no, un texto que explica qué revisar.
    Solo resuelve el nombre (no envía datos ni la clave) y guarda el resultado 60 s.
    """
    import socket
    url = url if url is not None else os.getenv("SUPABASE_URL", "")
    host = host_supabase(url)
    if not (url or "").strip():
        return "SUPABASE_URL está vacío: complételo en .streamlit/secrets.toml."
    if not host:
        return f"SUPABASE_URL no es una dirección válida («{url.strip()[:60]}»). Debe ser como https://xxxx.supabase.co"
    if host in ("localhost", "127.0.0.1") or host.endswith(".local"):
        return None
    if host.lower().startswith("xxxx") or "tu-proyecto" in host.lower():
        return f"SUPABASE_URL todavía tiene el valor de ejemplo («{host}»): ponga la dirección de su proyecto."
    ahora = time.time()
    hit = _CACHE_DIAG.get(host)
    if hit and ahora - hit[0] < cada_segundos:
        return hit[1]
    # Con proxy corporativo el nombre lo resuelve el proxy: no se puede comprobar por DNS.
    # Entonces se usa lo que pasó de verdad: si una consulta falló por conexión hace poco, hay aviso.
    if any(os.getenv(v) for v in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")):
        fallo = _ULTIMO_LOG.get("fallo")
        if fallo and ahora - fallo[0] < 120:
            return (f"No se pudo conectar con «{host}» a través del proxy ({fallo[1][:120]}). Revise que el "
                    "proyecto de Supabase no esté pausado, la VPN o el proxy (variable HTTPS_PROXY).")
        return None
    anterior = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(4)
        socket.getaddrinfo(host, 443)
        resultado = None
    except OSError as e:
        resultado = (f"No se encuentra el servidor «{host}» ({e}). Revise que la PC tenga internet, que "
                     "SUPABASE_URL en .streamlit/secrets.toml esté bien escrito y, en la red de EsSalud, "
                     "la VPN o el proxy (variable HTTPS_PROXY).")
    finally:
        socket.setdefaulttimeout(anterior)
    _CACHE_DIAG[host] = (ahora, resultado)
    return resultado
