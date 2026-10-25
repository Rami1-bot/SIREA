# src/auditoria.py
"""
Auditoría de acciones del panel (quién hizo qué, cuándo y desde dónde).

Cómo se protege el registro
---------------------------
* La tabla `auditoria_acciones` es de SOLO ESCRITURA: un disparador de la base
  de datos impide editar o borrar filas (ver sql/11).
* Cada fila guarda la huella SHA-256 de la fila anterior (una «cadena»). Si
  alguien alterara o quitara una fila por otra vía, `verificar_cadena()` lo detecta.
* Las operaciones delicadas (descarga masiva, retiro de archivos, permisos)
  usan `obligatorio=True`: si no se puede dejar constancia, la operación NO se hace.

Limitación honesta: quien administra la propia base de datos puede desactivar
el disparador. Por eso los acuses por correo (y la copia opcional a un buzón
institucional, AUDITORIA_COPIA_EMAIL) sirven como registro independiente.

La hora que se guarda es la de Lima.
"""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

LIMA = timezone(timedelta(hours=-5))
FORMATO = "%Y-%m-%d %H:%M:%S"
GENESIS = "GENESIS"
TABLA = "auditoria_acciones"

# Categorías (para filtrar) y etiquetas legibles de las acciones propias de esta función.
CATEGORIAS = {
    "ACCESO": "Accesos",
    "CUENTAS": "Cuentas",
    "PERMISOS": "Permisos",
    "DESCARGAS": "Descargas masivas",
    "RETIROS": "Retiros del repositorio",
    "DUPLICADOS": "Duplicados",
    "RESPALDOS": "Respaldos",
    "CONFIGURACION": "Configuración",
    "CIERRES": "Cierres y resúmenes",
    "SISTEMA": "Sistema y registros",
    "GENERAL": "General",
}

ETIQUETAS = {
    "DESCARGA_PREPARADA": "Preparó una descarga masiva",
    "DESCARGA_MASIVA": "Descargó un ZIP masivo",
    "RETIRO_SOLICITADO": "Solicitó retirar archivos",
    "RETIRO_APROBADO": "Aprobó un retiro de archivos",
    "RETIRO_RECHAZADO": "Rechazó un retiro de archivos",
    "RETIRO_CANCELADO": "Canceló su solicitud de retiro",
    "RETIRO_EJECUTADO": "Retiró archivos del repositorio",
    "RETIRO_ARCHIVO": "Retiro de un archivo",
    "PERMISO_OTORGADO": "Otorgó un permiso",
    "PERMISO_REVOCADO": "Revocó un permiso",
    "DUPLICADO_ELIMINADO": "Eliminó un duplicado",
    "RESPALDO_MANUAL": "Hizo un respaldo manual",
    "RESPALDO": "Respaldo completado",
    "RESPALDO_ERROR": "Respaldo con error",
    "AUDITORIA_VERIFICADA": "Verificó la integridad de la auditoría",
    "AUDITORIA_EXPORTADA": "Descargó el Excel de auditoría",
    "LOGS_LIMPIADOS": "Limpió el historial de logs",
    "ACCESO_DENEGADO": "Intento sin permiso",
}


class AuditoriaError(Exception):
    """No se pudo dejar constancia de una acción que la exige."""


def ahora_lima() -> datetime:
    return datetime.now(LIMA).replace(tzinfo=None)


def json_canonico(detalle) -> str:
    """Texto JSON estable (mismo texto siempre) del detalle de una acción."""
    if detalle is None or detalle == "":
        return ""
    if isinstance(detalle, str):
        return detalle
    return json.dumps(detalle, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def calcular_hash(hash_prev: str, fila: Dict) -> str:
    """Huella de una fila: depende de la fila anterior y de todo el contenido de ésta."""
    partes = [hash_prev, fila.get("ocurrio_iso", ""), fila.get("usuario", ""), fila.get("rol") or "",
              fila.get("accion", ""), fila.get("categoria", ""), fila.get("objeto") or "",
              fila.get("resultado", ""), fila.get("detalle") or ""]
    return hashlib.sha256("\x1f".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def ip_cliente() -> Optional[str]:
    """IP desde la que llega la petición (si el servidor la conoce)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx(suppress_warning=True) is None:      # fuera de una sesión de Streamlit (proceso programado, pruebas)
            return None
        import streamlit as st
        from src.config import Config
        cab = getattr(st.context, "headers", None)
        if cab and Config.PROXY_CONFIABLE:
            # Solo con un proxy propio delante: la última IP de la lista es la que añadió ese proxy
            # (las anteriores las puede escribir el propio visitante).
            for nombre in ("X-Forwarded-For", "X-Real-Ip", "X-Real-IP"):
                v = cab.get(nombre)
                if v:
                    return str(v).split(",")[-1].strip()[:64]
        ip = getattr(st.context, "ip_address", None)
        return str(ip)[:64] if ip else None
    except Exception:
        return None


def _categoria_de(accion: str) -> str:
    a = (accion or "").upper()
    if a.startswith(("LOGIN", "LOGOUT", "BLOQUEO", "SESION")):
        return "ACCESO"
    if any(k in a for k in ("ADMIN", "PASSWORD", "USUARIO", "CUENTA", "CREDENCIAL")):
        return "CUENTAS"
    if "PERMISO" in a:
        return "PERMISOS"
    if "DUPLICADO" in a or "REEMPLAZO" in a:
        return "DUPLICADOS"
    if "RESPALDO" in a:
        return "RESPALDOS"
    if any(k in a for k in ("CONFIG", "SEMANA", "CORTE", "ANIO", "EXCLU")):
        return "CONFIGURACION"
    if any(k in a for k in ("RESUMEN", "CIERRE", "DESTINATARIO")):
        return "CIERRES"
    if "LOG" in a:
        return "SISTEMA"
    return "GENERAL"


def evaluar_alertas(accion: str, detalle: Optional[Dict], momento: Optional[datetime] = None) -> List[str]:
    """Señales que merecen una segunda mirada (se guardan junto con la acción)."""
    from src.config import Config
    momento = momento or ahora_lima()
    detalle = detalle or {}
    alertas = []
    if accion in ("RETIRO_EJECUTADO", "RETIRO_SOLICITADO", "RETIRO_APROBADO", "DUPLICADO_ELIMINADO", "LOGS_LIMPIADOS"):
        if detalle.get("sin_descarga_previa"):
            alertas.append("Retiro sin descarga previa")
        if int(detalle.get("n_envios") or detalle.get("n_archivos") or 0) > Config.ALERTA_RETIRO_MAX_ARCHIVOS:
            alertas.append(f"Más de {Config.ALERTA_RETIRO_MAX_ARCHIVOS} archivos")
        if detalle.get("definitivo"):
            alertas.append("Borrado definitivo")
    if accion in ("RETIRO_EJECUTADO", "RETIRO_SOLICITADO", "RETIRO_APROBADO", "DESCARGA_MASIVA", "DUPLICADO_ELIMINADO",
                  "LOGS_LIMPIADOS", "PERMISO_OTORGADO"):
        fuera = not (Config.HORARIO_LABORAL_INICIO <= momento.hour < Config.HORARIO_LABORAL_FIN) or momento.weekday() >= 5
        if fuera:
            alertas.append("Fuera del horario laboral")
    return alertas


class Auditoria:
    def __init__(self, db=None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._disp = None

    def _t(self, nombre: str = TABLA):
        return self.db.supabase.table(nombre)

    def disponible(self) -> bool:
        """True si la migración 11 ya se ejecutó (se reintenta cada 30 s mientras falte)."""
        ahora = time.time()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t().select("id").limit(1).execute()
            ok = True
        except Exception as e:
            print(f"Auditoría no disponible (¿falta sql/11?): {e}")
            ok = False
        self._disp = (ok, ahora)
        return ok

    # ------------------------------------------------------------ escribir

    def _ultimo_hash(self) -> str:
        r = self._t().select("hash").order("id", desc=True).limit(1).execute().data
        return r[0]["hash"] if r else GENESIS

    def registrar(self, usuario: str, accion: str, categoria: Optional[str] = None, rol: Optional[str] = None,
                  objeto: Optional[str] = None, detalle: Optional[Dict] = None, resultado: str = "OK",
                  ip: Optional[str] = None, obligatorio: bool = False, linea_log: bool = True) -> Optional[Dict]:
        """
        Deja constancia de una acción. Devuelve la fila guardada.
        Con obligatorio=True lanza AuditoriaError si no se pudo (y la operación no debe seguir).
        """
        usuario = str(usuario or "SYSTEM")
        categoria = categoria or _categoria_de(accion)
        momento = ahora_lima()
        det = dict(detalle) if isinstance(detalle, dict) else ({"texto": detalle} if detalle else {})
        alertas = evaluar_alertas(accion, det, momento)
        if alertas:
            det["alertas"] = alertas
        fila = {"ocurrio_iso": momento.strftime(FORMATO), "usuario": usuario, "rol": rol, "accion": accion,
                "categoria": categoria, "objeto": (str(objeto)[:300] if objeto else None),
                "detalle": json_canonico(det) or None, "resultado": resultado, "ip": ip or ip_cliente()}
        if not self.disponible():
            if obligatorio:
                raise AuditoriaError("La auditoría no está disponible: falta ejecutar sql/11_auditoria_permisos_repositorio.sql.")
            return None
        ultimo_error = None
        for intento in range(8):
            try:
                prev = self._ultimo_hash()
                fila["hash_prev"] = prev
                fila["hash"] = calcular_hash(prev, fila)
                r = self._t().insert(dict(fila)).execute().data
                if linea_log:
                    self._linea_log(usuario, accion, objeto, det, fila["ip"])
                return r[0] if r else fila
            except Exception as e:
                ultimo_error = e
                texto = str(e).lower()
                if "duplicate" in texto or "23505" in texto or "uq_auditoria" in texto:
                    time.sleep(0.05 * (intento + 1))   # otro proceso escribió al mismo tiempo: reintentar encadenando
                    continue
                break
        print(f"No se pudo registrar en la auditoría ({accion}): {ultimo_error}")
        if obligatorio:
            raise AuditoriaError(f"No se pudo dejar constancia en la auditoría: {ultimo_error}")
        return None

    def _linea_log(self, usuario, accion, objeto, detalle, ip):
        """Una línea legible en «Historial y logs» (sin pasar por registrar_log, para no duplicar)."""
        try:
            partes = [ETIQUETAS.get(accion, accion)]
            if objeto:
                partes.append(str(objeto))
            self._t("logs").insert({"usuario": usuario, "accion": accion, "detalle": " · ".join(partes)[:500], "ip": ip}).execute()
        except Exception:
            pass

    def espejo(self, usuario: str, accion: str, detalle: Optional[str] = None, ip: Optional[str] = None) -> None:
        """
        Copia a la auditoría lo que se anota con db.registrar_log (accesos, cuentas, configuración…),
        para que TODO el panel quede en un solo registro. Nunca lanza errores.
        """
        try:
            u = str(usuario or "").strip()
            if not u or u.upper().startswith("RED:"):
                return
            if not self.disponible():
                return
            rol = None
            try:
                adm = self.db.obtener_administrador(u)
                rol = (adm or {}).get("rol")
            except Exception:
                pass
            self.registrar(u, accion, rol=rol, detalle={"texto": detalle} if detalle else None, ip=ip, linea_log=False)
        except Exception as e:
            print(f"Espejo de auditoría omitido: {e}")

    # ------------------------------------------------------------ leer

    def listar(self, desde: Optional[str] = None, hasta: Optional[str] = None, usuario: Optional[str] = None,
               categoria: Optional[str] = None, accion: Optional[str] = None, resultado: Optional[str] = None,
               limite: int = 500, offset: int = 0) -> List[Dict]:
        """Filas más recientes primero. `desde`/`hasta` son 'AAAA-MM-DD HH:MM:SS' (hora de Lima)."""
        if not self.disponible():
            return []
        q = self._t().select("*")
        if desde:
            q = q.gte("ocurrio_iso", desde)
        if hasta:
            q = q.lte("ocurrio_iso", hasta)
        if usuario:
            q = q.eq("usuario", usuario)
        if categoria:
            q = q.eq("categoria", categoria)
        if accion:
            q = q.eq("accion", accion)
        if resultado:
            q = q.eq("resultado", resultado)
        return q.order("id", desc=True).range(offset, offset + limite - 1).execute().data or []

    @staticmethod
    def detalle_de(fila: Dict) -> Dict:
        try:
            d = json.loads(fila.get("detalle") or "{}")
            return d if isinstance(d, dict) else {"texto": str(d)}
        except Exception:
            return {"texto": str(fila.get("detalle") or "")}

    def verificar_cadena(self, lote: int = 1000) -> Dict:
        """
        Recorre toda la auditoría y comprueba la cadena de huellas.
        Devuelve {ok, filas, id_roto, motivo}.
        """
        if not self.disponible():
            return {"ok": False, "filas": 0, "id_roto": None, "motivo": "La auditoría no está disponible."}
        esperado, total, desde = GENESIS, 0, 0
        while True:
            filas = self._t().select("*").order("id").range(desde, desde + lote - 1).execute().data or []
            if not filas:
                break
            for f in filas:
                total += 1
                if f.get("hash_prev") != esperado:
                    return {"ok": False, "filas": total, "id_roto": f.get("id"),
                            "motivo": "Falta una fila anterior o fue reemplazada (la cadena no continúa)."}
                if calcular_hash(f["hash_prev"], f) != f.get("hash"):
                    return {"ok": False, "filas": total, "id_roto": f.get("id"),
                            "motivo": "El contenido de esta fila fue alterado."}
                esperado = f["hash"]
            desde += lote
            if len(filas) < lote:
                break
        return {"ok": True, "filas": total, "id_roto": None, "motivo": "La cadena está íntegra."}


def resumen_por_usuario(filas: List[Dict]) -> List[Dict]:
    """Conteo de acciones por persona: [{usuario, total, ultima, descargas, retiros, alertas}]."""
    por: Dict[str, Dict] = {}
    for f in filas:
        u = f.get("usuario", "")
        r = por.setdefault(u, {"usuario": u, "rol": f.get("rol") or "", "total": 0, "descargas": 0, "retiros": 0,
                               "duplicados": 0, "alertas": 0, "ultima": ""})
        r["total"] += 1
        if f.get("rol"):
            r["rol"] = f["rol"]
        if f.get("accion") == "DESCARGA_MASIVA":
            r["descargas"] += 1
        if f.get("accion") == "RETIRO_EJECUTADO":
            r["retiros"] += 1
        if f.get("accion") == "DUPLICADO_ELIMINADO":
            r["duplicados"] += 1
        if Auditoria.detalle_de(f).get("alertas"):
            r["alertas"] += 1
        r["ultima"] = max(r["ultima"], f.get("ocurrio_iso", ""))
    return sorted(por.values(), key=lambda x: (-x["alertas"], -x["total"]))


_auditoria = None


def get_auditoria() -> Auditoria:
    global _auditoria
    from src.db_manager import get_db_manager
    db = get_db_manager()
    if _auditoria is None or _auditoria.db is not db:
        _auditoria = Auditoria(db)
    return _auditoria
