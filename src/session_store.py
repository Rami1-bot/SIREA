# src/session_store.py
"""
Almacén de sesiones e intentos de login PERSISTENTE (Supabase) con respaldo
en memoria.

Por qué existe
--------------
Antes, `AuthManager` y `RedAuthManager` guardaban las sesiones y los
intentos fallidos en diccionarios de Python. Eso tenía tres problemas de
seguridad (hallazgo M1 de la revisión):

  1. Al reiniciar la app se perdían las sesiones y, peor, los bloqueos por
     fuerza bruta.
  2. Con más de una réplica/proceso, cada uno tenía su propio estado.
  3. El bloqueo era solo por usuario: cualquiera podía bloquear a un
     administrador con 5 intentos, y nada limitaba probar muchas cuentas
     desde una misma IP (password spraying).

Qué hace
--------
  * Sesiones en la tabla `sesiones_app` (el token se guarda HASHEADO con
    SHA-256; si alguien lee la tabla no obtiene tokens utilizables).
  * Expiración ABSOLUTA (8 h) y por INACTIVIDAD (30 min).
  * Intentos fallidos en `intentos_login`, con dos claves independientes:
    por sujeto (usuario o red) y por IP. Cada una tiene su propio umbral.
  * Si las tablas aún no existen (falta ejecutar sql/51_sesiones_e_intentos_login.sql) o la
    BD falla, cae automáticamente a memoria y avisa UNA vez por consola,
    para no dejar la app sin login.

Uso
---
    almacen = AlmacenSesiones("admin")
    almacen.crear(token, sujeto="jperez", datos={...}, ip=ip)
    sesion = almacen.obtener(token)   # None si no existe o expiró
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

TABLA_SESIONES = "sesiones_app"
TABLA_INTENTOS = "intentos_login"

def _cfg(nombre: str, defecto: int) -> int:
    try:
        from src.config import Config
        return int(getattr(Config, nombre, defecto) or defecto)
    except Exception:
        return defecto


DURACION_MAXIMA = timedelta(hours=_cfg("SESION_DURACION_HORAS", 8))
INACTIVIDAD_MAXIMA = timedelta(minutes=_cfg("SESION_INACTIVIDAD_MINUTOS", 30))

# Política de bloqueo por SUJETO (usuario o red): N fallos en 15 min => bloqueo (SIREA: .env)
LIMITE_SUJETO = dict(max_intentos=_cfg("LOGIN_MAX_INTENTOS_USUARIO", 5), ventana=timedelta(minutes=15),
                     bloqueo=timedelta(minutes=_cfg("LOGIN_BLOQUEO_MINUTOS", 15)))
# Política de bloqueo por IP: frena el "password spraying" sin que un solo atacante
# pueda bloquear a un administrador concreto tan fácilmente.
LIMITE_IP = dict(max_intentos=_cfg("LOGIN_MAX_INTENTOS_IP", 20), ventana=timedelta(minutes=15),
                 bloqueo=timedelta(minutes=_cfg("LOGIN_BLOQUEO_MINUTOS", 15)))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(valor: Any) -> Optional[datetime]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    try:
        s = str(valor).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class AlmacenSesiones:
    """Un almacén por ámbito ('admin' o 'red'); ambos comparten las tablas."""

    def __init__(self, ambito: str):
        self.ambito = ambito
        self._mem_sesiones: Dict[str, Dict[str, Any]] = {}
        self._mem_intentos: Dict[str, Dict[str, Any]] = {}
        self._usar_memoria = False
        self._aviso_mostrado = False

    # ------------------------------------------------------------
    # infraestructura
    # ------------------------------------------------------------
    def _tabla(self, nombre: str):
        from src.db_manager import get_db_manager
        return get_db_manager().supabase.table(nombre)

    def _caer_a_memoria(self, error: BaseException) -> None:
        self._usar_memoria = True
        if not self._aviso_mostrado:
            print(
                f"[session_store:{self.ambito}] No se pudo usar la BD ({error}). "
                "Sesiones e intentos se guardarán EN MEMORIA hasta reiniciar. "
                "Ejecuta sql/51_sesiones_e_intentos_login.sql en Supabase para persistirlos."
            )
            self._aviso_mostrado = True

    # ------------------------------------------------------------
    # sesiones
    # ------------------------------------------------------------
    def crear(self, token: str, sujeto: str, datos: Dict[str, Any], ip: Optional[str] = None) -> None:
        ahora = _ahora()
        fila = {
            "token_hash": hash_token(token),
            "ambito": self.ambito,
            "sujeto": sujeto,
            "datos": datos or {},
            "ip": ip,
            "inicio": _iso(ahora),
            "ultima_actividad": _iso(ahora),
        }
        if not self._usar_memoria:
            try:
                self._tabla(TABLA_SESIONES).upsert(fila, on_conflict="token_hash").execute()
                return
            except Exception as e:
                self._caer_a_memoria(e)
        self._mem_sesiones[fila["token_hash"]] = fila

    def _leer_fila(self, token_hash: str) -> Optional[Dict[str, Any]]:
        if not self._usar_memoria:
            try:
                r = self._tabla(TABLA_SESIONES).select("*").eq("token_hash", token_hash).eq("ambito", self.ambito).execute()
                return r.data[0] if r.data else None
            except Exception as e:
                self._caer_a_memoria(e)
        fila = self._mem_sesiones.get(token_hash)
        return fila if fila and fila.get("ambito") == self.ambito else None

    def obtener(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Devuelve la sesión si existe y NO ha expirado (absoluta 8 h,
        inactividad 30 min). Si expiró, la elimina y devuelve None.
        """
        if not token:
            return None
        th = hash_token(token)
        fila = self._leer_fila(th)
        if not fila:
            return None
        inicio, ultima = _parse(fila.get("inicio")), _parse(fila.get("ultima_actividad"))
        ahora = _ahora()
        if inicio is None or ahora - inicio > DURACION_MAXIMA or (ultima and ahora - ultima > INACTIVIDAD_MAXIMA):
            self.eliminar(token)
            return None
        datos = fila.get("datos") or {}
        if isinstance(datos, str):
            try:
                datos = json.loads(datos)
            except json.JSONDecodeError:
                datos = {}
        return {
            "sujeto": fila.get("sujeto"),
            "datos": datos,
            "ip": fila.get("ip"),
            "inicio": inicio,
            "ultima_actividad": ultima or inicio,
        }

    def tocar(self, token: str, datos: Optional[Dict[str, Any]] = None) -> None:
        """Actualiza 'ultima_actividad' (y opcionalmente los datos)."""
        th = hash_token(token)
        cambios: Dict[str, Any] = {"ultima_actividad": _iso(_ahora())}
        if datos is not None:
            cambios["datos"] = datos
        if not self._usar_memoria:
            try:
                self._tabla(TABLA_SESIONES).update(cambios).eq("token_hash", th).execute()
                return
            except Exception as e:
                self._caer_a_memoria(e)
        if th in self._mem_sesiones:
            self._mem_sesiones[th].update(cambios)

    def eliminar(self, token: str) -> bool:
        th = hash_token(token)
        if not self._usar_memoria:
            try:
                r = self._tabla(TABLA_SESIONES).delete().eq("token_hash", th).execute()
                return bool(r.data)
            except Exception as e:
                self._caer_a_memoria(e)
        return self._mem_sesiones.pop(th, None) is not None

    def eliminar_por_sujeto(self, sujeto: Optional[str] = None) -> int:
        """Cierra todas las sesiones del ámbito, o solo las de un sujeto."""
        if not self._usar_memoria:
            try:
                q = self._tabla(TABLA_SESIONES).delete().eq("ambito", self.ambito)
                if sujeto is not None:
                    q = q.eq("sujeto", sujeto)
                r = q.execute()
                return len(r.data or [])
            except Exception as e:
                self._caer_a_memoria(e)
        claves = [k for k, v in self._mem_sesiones.items()
                  if v.get("ambito") == self.ambito and (sujeto is None or v.get("sujeto") == sujeto)]
        for k in claves:
            del self._mem_sesiones[k]
        return len(claves)

    def listar(self) -> List[Dict[str, Any]]:
        """Sesiones vigentes del ámbito (sin tokens)."""
        filas: List[Dict[str, Any]] = []
        if not self._usar_memoria:
            try:
                r = self._tabla(TABLA_SESIONES).select("*").eq("ambito", self.ambito).execute()
                filas = r.data or []
            except Exception as e:
                self._caer_a_memoria(e)
        if self._usar_memoria:
            filas = [v for v in self._mem_sesiones.values() if v.get("ambito") == self.ambito]
        ahora = _ahora()
        vigentes = []
        for f in filas:
            inicio, ultima = _parse(f.get("inicio")), _parse(f.get("ultima_actividad"))
            if inicio and ahora - inicio <= DURACION_MAXIMA and (not ultima or ahora - ultima <= INACTIVIDAD_MAXIMA):
                vigentes.append({
                    "sujeto": f.get("sujeto"), "datos": f.get("datos") or {}, "ip": f.get("ip"),
                    "inicio": inicio, "ultima_actividad": ultima or inicio,
                })
        return vigentes

    # ------------------------------------------------------------
    # intentos fallidos / bloqueos
    # ------------------------------------------------------------
    def _clave(self, tipo: str, valor: str) -> str:
        return f"{self.ambito}:{tipo}:{(valor or '').strip().lower()}"

    def _leer_intento(self, clave: str) -> Optional[Dict[str, Any]]:
        if not self._usar_memoria:
            try:
                r = self._tabla(TABLA_INTENTOS).select("*").eq("clave", clave).execute()
                return r.data[0] if r.data else None
            except Exception as e:
                self._caer_a_memoria(e)
        return self._mem_intentos.get(clave)

    def _guardar_intento(self, fila: Dict[str, Any]) -> None:
        if not self._usar_memoria:
            try:
                self._tabla(TABLA_INTENTOS).upsert(fila, on_conflict="clave").execute()
                return
            except Exception as e:
                self._caer_a_memoria(e)
        self._mem_intentos[fila["clave"]] = fila

    def _borrar_intento(self, clave: str) -> None:
        if not self._usar_memoria:
            try:
                self._tabla(TABLA_INTENTOS).delete().eq("clave", clave).execute()
                return
            except Exception as e:
                self._caer_a_memoria(e)
        self._mem_intentos.pop(clave, None)

    def minutos_bloqueo(self, tipo: str, valor: Optional[str]) -> int:
        """
        Minutos que faltan para que se levante el bloqueo de un sujeto
        ('sujeto') o de una IP ('ip'). 0 si no está bloqueado.
        """
        if not valor:
            return 0
        fila = self._leer_intento(self._clave(tipo, valor))
        if not fila:
            return 0
        hasta = _parse(fila.get("bloqueado_hasta"))
        if hasta and hasta > _ahora():
            return max(1, int((hasta - _ahora()).total_seconds() // 60) + 1)
        return 0

    def registrar_fallo(self, tipo: str, valor: Optional[str]) -> bool:
        """
        Suma un intento fallido. Devuelve True si con este intento el
        sujeto/IP quedó bloqueado.
        """
        if not valor:
            return False
        politica = LIMITE_IP if tipo == "ip" else LIMITE_SUJETO
        clave = self._clave(tipo, valor)
        ahora = _ahora()
        fila = self._leer_intento(clave) or {"clave": clave, "intentos": 0, "ultimo_intento": None, "bloqueado_hasta": None}
        ultimo = _parse(fila.get("ultimo_intento"))
        intentos = int(fila.get("intentos") or 0)
        if ultimo is None or ahora - ultimo > politica["ventana"]:
            intentos = 0  # ventana vencida: se reinicia el contador
        intentos += 1
        bloqueado = intentos >= politica["max_intentos"]
        nueva = {
            "clave": clave,
            "intentos": intentos,
            "ultimo_intento": _iso(ahora),
            "bloqueado_hasta": _iso(ahora + politica["bloqueo"]) if bloqueado else None,
        }
        self._guardar_intento(nueva)
        return bloqueado

    def limpiar_fallos(self, tipo: str, valor: Optional[str]) -> None:
        if valor:
            self._borrar_intento(self._clave(tipo, valor))


# ------------------------------------------------------------
# IP del cliente (solo fiable detrás de un proxy inverso de confianza)
# ------------------------------------------------------------
def obtener_ip_cliente() -> Optional[str]:
    """
    IP del navegador. Usa la misma regla que la auditoría (src/auditoria.ip_cliente):
    X-Forwarded-For solo se acepta con PROXY_CONFIABLE=true (detrás del proxy HTTPS),
    porque un visitante puede falsificar ese encabezado.
    """
    try:
        from src.auditoria import ip_cliente
        return ip_cliente()
    except Exception:
        return None
