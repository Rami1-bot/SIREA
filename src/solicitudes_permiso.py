# src/solicitudes_permiso.py
"""
Solicitudes de permiso (v7.6).

Una cuenta SIN un permiso puede pedirlo desde la pantalla donde lo necesita («Solicitar acceso»).
La solicitud queda guardada (tabla solicitudes_permiso, sql/17), se avisa por correo al SUPER_ADMIN
principal y se anota en el «Control de actividad». Solo el principal la aprueba o la rechaza:

  - al aprobar, se asigna el permiso con las reglas de siempre (Permisos.otorgar: redes, vigencia, aviso);
  - al rechazar, se avisa a la persona con la respuesta.

Si la tabla aún no existe (falta sql/17), la solicitud igual sale por correo y queda en la auditoría.
Estados: PENDIENTE → APROBADA | RECHAZADA | CANCELADA
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from src.auditoria import AuditoriaError, ahora_lima, get_auditoria
from src.config import Config
from src.permisos import PERMISOS, es_principal

MIN_MENSAJE = 15
MAX_MENSAJE = 600
MAX_SOLICITUDES_DIA = 6       # contra insistencia: pedidos por persona en las últimas 24 h
ESTADOS = ("PENDIENTE", "APROBADA", "RECHAZADA", "CANCELADA")


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class SolicitudesPermiso:
    def __init__(self, db=None, permisos=None, auditoria=None, sender=None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._permisos, self._aud, self._sender = permisos, auditoria, sender
        self._disp = None

    # ------------------------------------------------------------ piezas
    @property
    def permisos(self):
        if self._permisos is None:
            from src.permisos import get_permisos
            self._permisos = get_permisos()
        return self._permisos

    @property
    def aud(self):
        if self._aud is None:
            self._aud = get_auditoria()
        return self._aud

    def _correo(self):
        if self._sender is None:
            from src.email_sender import get_email_sender
            self._sender = get_email_sender()
        return self._sender

    def _t(self):
        return self.db.supabase.table("solicitudes_permiso")

    def disponible(self) -> bool:
        import time
        ahora = time.time()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t().select("id").limit(1).execute()
            ok = True
        except Exception as e:
            print(f"Solicitudes de permiso no disponibles (¿falta sql/17?): {e}")
            ok = False
        self._disp = (ok, time.time())
        return ok

    # ------------------------------------------------------------ consulta
    def listar(self, usuario: Optional[str] = None, estado: Optional[str] = None, limite: int = 200) -> List[Dict]:
        if not self.disponible():
            return []
        q = self._t().select("*")
        if usuario:
            q = q.eq("usuario", usuario)
        if estado:
            q = q.eq("estado", estado)
        return (q.order("id", desc=True).limit(limite).execute().data or [])

    def pendiente_de(self, usuario: str, permiso: str) -> Optional[Dict]:
        return next((s for s in self.listar(usuario, "PENDIENTE") if s.get("permiso") == permiso), None)

    def n_pendientes(self) -> int:
        return len(self.listar(estado="PENDIENTE"))

    # ------------------------------------------------------------ pedir
    @staticmethod
    def mensaje_valido(mensaje: str) -> Optional[str]:
        t = " ".join((mensaje or "").split())
        if len(t) < MIN_MENSAJE:
            return f"Explique para qué necesita el permiso (mínimo {MIN_MENSAJE} caracteres)."
        if len(mensaje) > MAX_MENSAJE:
            return f"El mensaje es muy largo (máximo {MAX_MENSAJE} caracteres)."
        return None

    def crear(self, actor: Dict, permiso: str, mensaje: str) -> Tuple[bool, str]:
        usuario = str((actor or {}).get("usuario", "")).strip()
        if not usuario:
            return False, "No se pudo identificar su cuenta."
        if permiso not in PERMISOS:
            return False, "Permiso desconocido."
        if es_principal(actor):
            return False, "Usted es el SUPER_ADMIN principal: ya tiene todos los permisos."
        if self.permisos.tiene(actor, permiso):
            return False, "Su cuenta ya tiene este permiso."
        err = self.mensaje_valido(mensaje)
        if err:
            return False, err
        mensaje = " ".join(mensaje.split()) if "\n" not in mensaje else mensaje.strip()
        usa_tabla = self.disponible()
        if usa_tabla:
            if self.pendiente_de(usuario, permiso):
                return False, "Ya tiene una solicitud pendiente de este permiso. Espere la respuesta del SUPER_ADMIN principal."
            desde = (_ahora_utc() - timedelta(hours=24)).isoformat()
            recientes = [s for s in self.listar(usuario, limite=50) if str(s.get("creada_en") or "") >= desde]
            if len(recientes) >= MAX_SOLICITUDES_DIA:
                return False, "Ya envió varias solicitudes hoy. Espere la respuesta o comuníquese con la OIIS."
        cuando = ahora_lima().strftime("%d/%m/%Y %H:%M")
        try:
            self.aud.registrar(usuario, "SOLICITUD_PERMISO", "PERMISOS", rol=actor.get("rol"),
                               objeto=f"{usuario} · {permiso}",
                               detalle={"permiso": permiso, "mensaje": mensaje[:300], "guardada": usa_tabla}, obligatorio=True)
        except AuditoriaError as e:
            return False, str(e)
        fila = {"usuario": usuario, "nombre": actor.get("nombre") or usuario, "permiso": permiso, "mensaje": mensaje, "estado": "PENDIENTE"}
        if usa_tabla:
            try:
                r = self._t().insert(fila).execute().data
                if not r:
                    return False, "No se pudo guardar la solicitud. Intente de nuevo."
            except Exception as e:
                if "duplicate" in str(e).lower() or "23505" in str(e):
                    return False, "Ya tiene una solicitud pendiente de este permiso."
                return False, f"No se pudo guardar la solicitud: {e}"
        avisados = self._avisar_principal(dict(fila, cuando=cuando), permiso)
        if usa_tabla:
            return True, ("Solicitud enviada. El SUPER_ADMIN principal la revisará y le responderá por correo."
                          if avisados else "Solicitud guardada. No se pudo enviar el correo, pero el SUPER_ADMIN principal la verá en Permisos de operación.")
        return True, ("Solicitud enviada por correo al SUPER_ADMIN principal." if avisados
                      else "No se pudo enviar el correo. Comuníquese con la OIIS.")

    def _avisar_principal(self, sol: Dict, permiso: str) -> int:
        try:
            from src.email_auditoria import enviar_aviso_solicitud_permiso
            return enviar_aviso_solicitud_permiso(self._correo(), self.db, sol, PERMISOS[permiso][0])
        except Exception as e:
            print(f"No se pudo avisar la solicitud de permiso: {e}")
            return 0

    def cancelar(self, actor: Dict, solicitud_id: int) -> Tuple[bool, str]:
        usuario = str((actor or {}).get("usuario", "")).strip()
        s = (self._t().select("*").eq("id", solicitud_id).limit(1).execute().data or [None])[0] if self.disponible() else None
        if not s or s.get("usuario") != usuario or s.get("estado") != "PENDIENTE":
            return False, "La solicitud no existe o ya fue respondida."
        try:
            self.aud.registrar(usuario, "SOLICITUD_PERMISO_CANCELADA", "PERMISOS", rol=actor.get("rol"),
                               objeto=f"{usuario} · {s['permiso']}", detalle={"id": solicitud_id}, obligatorio=True)
        except AuditoriaError as e:
            return False, str(e)
        self._t().update({"estado": "CANCELADA", "resuelta_por": usuario, "resuelta_en": _ahora_utc().isoformat()}).eq("id", solicitud_id).execute()
        return True, "Solicitud cancelada."

    # ------------------------------------------------------------ responder (solo el principal)
    def _principal(self, token: str) -> Tuple[Optional[Dict], Optional[str]]:
        return self.permisos._actor_principal(token)

    def _obtener_pendiente(self, solicitud_id: int) -> Optional[Dict]:
        s = (self._t().select("*").eq("id", solicitud_id).limit(1).execute().data or [None])[0]
        return s if s and s.get("estado") == "PENDIENTE" else None

    def aprobar(self, token: str, solicitud_id: int, redes: Optional[List[str]] = None,
                vence_en: Optional[datetime] = None, respuesta: str = "") -> Tuple[bool, str]:
        actor, err = self._principal(token)
        if err:
            return False, "Solo el SUPER_ADMIN principal puede responder solicitudes."
        if not self.disponible():
            return False, "Falta ejecutar sql/17_solicitudes_permiso.sql en Supabase."
        s = self._obtener_pendiente(solicitud_id)
        if not s:
            return False, "La solicitud no existe o ya fue respondida."
        ok, msg = self.permisos.otorgar(token, s["usuario"], s["permiso"], redes, vence_en,
                                        nota=(respuesta or f"Solicitud N.º {solicitud_id}"))
        if not ok:
            return False, msg
        try:
            self.aud.registrar(actor["usuario"], "SOLICITUD_PERMISO_APROBADA", "PERMISOS", rol=actor.get("rol"),
                               objeto=f"{s['usuario']} · {s['permiso']}", detalle={"id": solicitud_id, "respuesta": (respuesta or "")[:300]})
        except Exception:
            pass
        self._t().update({"estado": "APROBADA", "resuelta_por": actor["usuario"], "resuelta_en": _ahora_utc().isoformat(),
                          "respuesta": (respuesta or "")[:600] or None}).eq("id", solicitud_id).execute()
        return True, "Solicitud aprobada. La persona recibió el aviso del permiso por correo."

    def rechazar(self, token: str, solicitud_id: int, respuesta: str = "") -> Tuple[bool, str]:
        actor, err = self._principal(token)
        if err:
            return False, "Solo el SUPER_ADMIN principal puede responder solicitudes."
        if not self.disponible():
            return False, "Falta ejecutar sql/17_solicitudes_permiso.sql en Supabase."
        s = self._obtener_pendiente(solicitud_id)
        if not s:
            return False, "La solicitud no existe o ya fue respondida."
        try:
            self.aud.registrar(actor["usuario"], "SOLICITUD_PERMISO_RECHAZADA", "PERMISOS", rol=actor.get("rol"),
                               objeto=f"{s['usuario']} · {s['permiso']}", detalle={"id": solicitud_id, "respuesta": (respuesta or "")[:300]},
                               obligatorio=True)
        except AuditoriaError as e:
            return False, str(e)
        self._t().update({"estado": "RECHAZADA", "resuelta_por": actor["usuario"], "resuelta_en": _ahora_utc().isoformat(),
                          "respuesta": (respuesta or "")[:600] or None}).eq("id", solicitud_id).execute()
        try:
            from src.email_auditoria import enviar_respuesta_solicitud_permiso
            enviar_respuesta_solicitud_permiso(self._correo(), self.db, s, PERMISOS[s["permiso"]][0], False,
                                               actor.get("nombre") or actor["usuario"], respuesta)
        except Exception as e:
            print(f"No se pudo avisar el rechazo: {e}")
        return True, "Solicitud rechazada. Se avisó a la persona."


def pendientes_permisos() -> int:
    """Solicitudes de permiso esperando respuesta (0 si no se puede consultar)."""
    try:
        return get_solicitudes_permiso().n_pendientes()
    except Exception:
        return 0


_instancia = None


def get_solicitudes_permiso() -> SolicitudesPermiso:
    global _instancia
    from src.db_manager import get_db_manager
    db = get_db_manager()
    if _instancia is None or _instancia.db is not db:
        _instancia = SolicitudesPermiso(db)
    return _instancia
