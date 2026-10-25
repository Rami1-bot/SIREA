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
