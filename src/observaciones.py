# src/observaciones.py
"""
Observaciones de los envíos (v7.0).

Una fila por envío que tenga algo que revisar:
  · el sustento que escribió quien envía (opcional, hasta 1000 caracteres),
  · un envío OBSERVADO, DUPLICADO o que REEMPLAZÓ a otro.
Se muestran en el módulo «Observaciones» del panel, con un contador de lo
pendiente de revisar (sin correos). Los envíos tardíos siguen en «Control de
atrasos»; si traen sustento, también aparecen aquí.

El texto vive en una tabla aparte (sql/13_observaciones_envio.sql), no en
`envios`, para no engordar esa tabla. Si la tabla aún no existe, el envío se
registra igual y solo se pierde el sustento.
"""

import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.db_manager import get_db_manager
from src.logging_config import obtener_logger

logger = obtener_logger(__name__)

TABLA = "observaciones_envio"
MAX_TEXTO = 1000
MAX_DETALLE = 1500
MOTIVOS = ("REEMPLAZO", "DUPLICADO", "OBSERVADO", "SUSTENTO")      # de mayor a menor prioridad
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpiar_texto(texto: Optional[str], limite: int = MAX_TEXTO) -> str:
    """Texto plano: sin caracteres de control, sin líneas en blanco repetidas, recortado al límite."""
    t = _CONTROL.sub("", str(texto or "")).replace("\r\n", "\n").replace("\r", "\n").strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t[:limite].strip()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class Observaciones:
    def __init__(self, db=None):
        self.db = db or get_db_manager()
        self._disp = None

    def _t(self):
        return self.db.supabase.table(TABLA)

    def disponible(self) -> bool:
        """True si la migración 13 ya se ejecutó (se reintenta cada 30 s mientras falte)."""
        ahora = time.time()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t().select("id").limit(1).execute()
            ok = True
        except Exception as e:
            logger.warning("Observaciones no disponibles (¿falta sql/13?): %s", e)
            ok = False
        self._disp = (ok, ahora)
        return ok

    # ------------------------------------------------------------ escribir

    @staticmethod
    def motivo_de(estado: str, es_duplicado: bool, es_reemplazo: bool, texto: str, es_falla: bool = False) -> Optional[str]:
        """Motivo principal de la fila, o None si el envío no tiene nada que revisar."""
        if es_falla:
            return "FALLA"
        if es_reemplazo:
            return "REEMPLAZO"
        if es_duplicado:
            return "DUPLICADO"
        if str(estado or "").upper() == "OBSERVADO":
            return "OBSERVADO"
        if texto:
            return "SUSTENTO"
        return None

    def registrar(self, envio_id, codigo: str, red: str, semana, anio, remitente: str, correo: str,
                  estado_envio: str, texto: str = "", detalle: str = "", es_duplicado: bool = False,
                  es_reemplazo: bool = False, es_falla: bool = False, datos: Optional[Dict] = None) -> bool:
        """Guarda la fila si el envío tiene algo que revisar. Nunca lanza: un fallo aquí no debe perder el envío."""
        try:
            texto = limpiar_texto(texto)
            motivo = self.motivo_de(estado_envio, es_duplicado, es_reemplazo, texto, es_falla)
            if not motivo:
                return False
            if not self.disponible():
                return False
            fila = {
                "envio_id": envio_id, "codigo_seguimiento": str(codigo), "red": red, "semana": semana, "anio": anio,
                "remitente": limpiar_texto(remitente, 200), "correo": limpiar_texto(correo, 200), "motivo": motivo,
                "estado_envio": estado_envio, "texto": texto or None,
                "detalle": limpiar_texto(detalle, MAX_DETALLE) or None,
            }
            if datos:
                fila["datos"] = datos
            try:
                self._t().insert(fila).execute()
            except Exception as e:
                # Sin la migración 14 la base no conoce el motivo FALLA ni la columna `datos`: se guarda como «Reemplazo».
                if motivo == "FALLA" or "datos" in fila:
                    logger.warning("Observación guardada sin categoría de falla (¿falta sql/14?): %s", e)
                    fila.pop("datos", None)
                    if fila["motivo"] == "FALLA":
                        fila["motivo"] = "REEMPLAZO"
                    self._t().insert(fila).execute()
                else:
                    raise
            return True
        except Exception as e:
            logger.warning("No se pudo guardar la observación del envío %s: %s", codigo, e)
            return False

    # ------------------------------------------------------------ consultar

    def listar(self, revisada: Optional[bool] = False, red: Optional[str] = None, anio: Optional[int] = None,
               semana: Optional[int] = None, motivo: Optional[str] = None, limite: int = 300) -> List[Dict]:
        if not self.disponible():
            return []
        q = self._t().select("*")
        if revisada is not None:
            q = q.eq("revisada", revisada)
        if red:
            q = q.eq("red", red)
        if anio:
            q = q.eq("anio", anio)
        if semana:
            q = q.eq("semana", semana)
        if motivo:
            q = q.eq("motivo", motivo)
        return q.order("fecha_creacion", desc=True).limit(limite).execute().data or []

    @staticmethod
    def categoria_de(fila: Dict) -> str:
        """
        COMENTARIO: lo que escribió quien envía (aunque el envío también sea duplicado, observado o reemplazo).
        REVISION: el sistema marcó el envío por sus reglas (observado, duplicado, reemplazo) y no hay texto.
        FALLA: algo técnico que no salió bien (por ejemplo, Drive sin permiso de mover).
        """
        if fila.get("motivo") == "FALLA":
            return "FALLA"
        if str(fila.get("texto") or "").strip():
            return "COMENTARIO"
        return "REVISION"

    def contadores(self) -> Dict[str, int]:
        """Sin revisar por categoría, para el menú: {'normales': comentarios + por revisar, 'fallas': n}."""
        try:
            if not self.disponible():
                return {"normales": 0, "fallas": 0}
            filas = self._t().select("motivo,texto").eq("revisada", False).limit(2000).execute().data or []
            fallas = sum(1 for f in filas if f.get("motivo") == "FALLA")
            return {"normales": len(filas) - fallas, "fallas": fallas}
        except Exception:
            return {"normales": 0, "fallas": 0}

    def pendientes(self) -> int:
        """Cantidad sin revisar de comentarios y envíos por revisar (las fallas técnicas se cuentan aparte)."""
        return self.contadores()["normales"]

    def marcar_revisadas(self, ids: List, usuario: str) -> int:
        """Marca filas como revisadas. Devuelve cuántas se actualizaron."""
        n = 0
        for i in ids:
            try:
                r = self._t().update({"revisada": True, "revisada_por": usuario, "fecha_revision": _ahora()}) \
                    .eq("id", i).eq("revisada", False).execute()
                n += len(r.data or [])
            except Exception as e:
                logger.warning("No se pudo marcar la observación %s: %s", i, e)
        return n


_instancia: Optional[Observaciones] = None


def get_observaciones() -> Observaciones:
    global _instancia
    if _instancia is None:
        _instancia = Observaciones()
    return _instancia
