# src/responsables_red.py
"""
Responsables (encargados) de las redes para «Notificaciones» (v7.4).

Une dos fuentes para que el panel complete solo los datos del destinatario:
  · «Registrado»: personas que el panel guardó con «Guardar como responsable de la red»
    (tabla `responsables_red`, sql/15; opcional).
  · «Detectado en envíos»: personas que ya enviaron reportes de esa red (nombre, apellido y correo
    de la tabla `envios`). No necesita nada nuevo en la base de datos.

Si la misma persona está en las dos, se muestra una sola vez como «Registrado». La lista sale
ordenada con la persona que envió más recientemente primero.

Seguridad: los textos se limpian y recortan antes de guardarse; en pantalla se escapan siempre.
"""

import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.db_manager import get_db_manager
from src.logging_config import obtener_logger
from src.validacion_correo import formato_valido, normalizar

logger = obtener_logger(__name__)

TABLA = "responsables_red"
ORIGEN_REGISTRADO = "Registrado"
ORIGEN_DETECTADO = "Detectado en envíos"
_CONTROL = re.compile(r"[\x00-\x1f\x7f<>]")
_TELEFONO = re.compile(r"[^0-9+ ]")


def _limpio(texto: Optional[str], limite: int = 80) -> str:
    t = _CONTROL.sub("", str(texto or "")).strip()
    return " ".join(t.split())[:limite]


def _nombre_centro(c) -> str:
    """De «245 H.II JAEN» a «H.II JAEN» (los envíos guardan el código delante del nombre)."""
    texto = c.get("nombre", "") if isinstance(c, dict) else str(c)
    texto = str(texto).strip()
    partes = texto.split(" ", 1)
    if len(partes) == 2 and partes[0].isdigit():
        return partes[1].strip()
    return texto


def _fecha_corta(valor) -> str:
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


class ResponsablesRed:
    def __init__(self, db=None):
        self.db = db or get_db_manager()
        self._disp = None

    def _t(self):
        return self.db.supabase.table(TABLA)

    def disponible(self) -> bool:
        """True si la tabla de responsables existe (se reintenta cada 30 s mientras falte)."""
        ahora = time.time()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t().select("id").limit(1).execute()
            ok = True
        except Exception as e:
            logger.info("Responsables de red no disponibles (¿falta sql/15?): %s", e)
            ok = False
        self._disp = (ok, ahora)
        return ok

    # ------------------------------------------------------------ leer

    def registrados(self, red: str) -> List[Dict]:
        if not red or not self.disponible():
            return []
        try:
            r = self._t().select("*").eq("red", red).eq("activo", True).order("fecha_actualizacion", desc=True).execute()
            return list(r.data or [])
        except Exception as e:
            logger.warning("No se pudieron leer los responsables de %s: %s", red, e)
            return []

    def detectados(self, red: str, limite: int = 400) -> List[Dict]:
        """Personas que enviaron reportes de la red, con su último envío y los centros que reportaron."""
        if not red:
            return []
        try:
            r = (self.db.supabase.table("envios")
                 .select("nombre_usuario,apellido_usuario,correo_usuario,centros,fecha_envio")
                 .eq("red", red).order("fecha_envio", desc=True).limit(limite).execute())
        except Exception as e:
            logger.warning("No se pudieron leer los envíos de %s: %s", red, e)
            return []
        personas: Dict[str, Dict] = {}
        for e in r.data or []:
            correo = normalizar(e.get("correo_usuario"))
            if not correo or not formato_valido(correo):
                continue
            p = personas.setdefault(correo, {
                "correo": correo,
                "nombre": _limpio(e.get("nombre_usuario")),
                "apellido": _limpio(e.get("apellido_usuario")),
                "telefono": "", "origen": ORIGEN_DETECTADO,
                "ultimo_envio": e.get("fecha_envio") or "", "centros": [],
            })
            centros = e.get("centros")
            for c in (centros if isinstance(centros, list) else []):
                n = _nombre_centro(c)
                if n and n not in p["centros"]:
                    p["centros"].append(n)
        return list(personas.values())

    def combinados(self, red: str) -> List[Dict]:
        """Registrados + detectados, sin repetir correos; el de envío más reciente primero."""
        det = {p["correo"]: p for p in self.detectados(red)}
        salida: Dict[str, Dict] = {}
        for g in self.registrados(red):
            correo = normalizar(g.get("correo"))
            d = det.pop(correo, None) or {}
            salida[correo] = {
                "id": g.get("id"), "correo": correo,
                "nombre": _limpio(g.get("nombre")), "apellido": _limpio(g.get("apellido")),
                "telefono": _limpio(g.get("telefono"), 20), "origen": ORIGEN_REGISTRADO,
                "ultimo_envio": d.get("ultimo_envio", ""), "centros": d.get("centros", []),
            }
        for correo, p in det.items():
            salida[correo] = p
        lista = list(salida.values())
        # el de envío más reciente primero; quienes nunca enviaron, al final
        con = sorted([p for p in lista if p["ultimo_envio"]], key=lambda p: str(p["ultimo_envio"]), reverse=True)
        sin = [p for p in lista if not p["ultimo_envio"]]
        for p in con + sin:
            p["ultimo_envio_txt"] = _fecha_corta(p["ultimo_envio"])
        return con + sin

    # ------------------------------------------------------------ escribir

    def guardar(self, red: str, nombre: str, apellido: str, correo: str, telefono: str = "",
                actor: str = "") -> Tuple[bool, str]:
        """Guarda (o actualiza) un responsable de la red. Devuelve (ok, mensaje)."""
        correo = normalizar(correo)
        nombre, apellido = _limpio(nombre), _limpio(apellido)
        telefono = _TELEFONO.sub("", str(telefono or ""))[:20].strip()
        if not red:
            return False, "Elija una red concreta para guardar al responsable."
        if not nombre or not apellido:
            return False, "Complete nombre y apellido."
        if not formato_valido(correo):
            return False, "El correo no tiene un formato válido."
        if not self.disponible():
            return False, "Falta crear la tabla de responsables: ejecute sql/15_responsables_red.sql en Supabase."
        ahora = datetime.utcnow().isoformat() + "Z"
        try:
            existe = self._t().select("id").eq("red", red).eq("correo", correo).execute().data
            fila = {"nombre": nombre, "apellido": apellido, "telefono": telefono or None,
                    "activo": True, "fecha_actualizacion": ahora}
            if existe:
                self._t().update(fila).eq("id", existe[0]["id"]).execute()
            else:
                fila.update({"red": red, "correo": correo, "creado_por": _limpio(actor, 80) or None})
                self._t().insert(fila).execute()
            return True, "Responsable guardado."
        except Exception as e:
            logger.warning("No se pudo guardar el responsable %s de %s: %s", correo, red, e)
            return False, "No se pudo guardar el responsable."

    def quitar(self, red: str, correo: str) -> bool:
        """Quita a un responsable guardado (no borra sus envíos: si volvió a enviar, reaparece como detectado)."""
        if not self.disponible():
            return False
        try:
            self._t().delete().eq("red", red).eq("correo", normalizar(correo)).execute()
            return True
        except Exception as e:
            logger.warning("No se pudo quitar al responsable %s de %s: %s", correo, red, e)
            return False


_instancia = None


def get_responsables_red() -> ResponsablesRed:
    global _instancia
    if _instancia is None:
        _instancia = ResponsablesRed()
    return _instancia
