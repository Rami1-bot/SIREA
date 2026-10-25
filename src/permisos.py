# src/permisos.py
"""
Permisos de operación sobre el repositorio de archivos.

SOLO el SUPER_ADMIN principal (Config.SUPERADMIN_PRINCIPAL, «oiis.winepi»)
los asigna o los quita. Cada permiso se da por persona (ADMIN o SUPER_ADMIN),
con alcance opcional por redes y fecha de vencimiento. El principal siempre
los tiene todos.

  DESCARGA_MASIVA     preparar y descargar el ZIP de una semana
  RETIRO_REPOSITORIO  pedir el retiro de archivos del repositorio y eliminar duplicados
  RESPALDO_MANUAL     hacer un respaldo manual
  VER_AUDITORIA       ver el «Control de actividad»
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.auditoria import LIMA, AuditoriaError, get_auditoria
from src.config import Config

PERMISOS = {
    "DESCARGA_MASIVA": ("Descarga masiva", "Preparar y descargar el ZIP de las redes de una semana."),
    "RETIRO_REPOSITORIO": ("Retiro del repositorio", "Pedir el retiro de archivos de Drive (lo aprueba oiis.winepi) y eliminar duplicados."),
    "RESPALDO_MANUAL": ("Respaldo manual", "Hacer un respaldo a la carpeta BACKUPS cuando lo necesite."),
    "VER_AUDITORIA": ("Ver auditoría", "Consultar el «Control de actividad» de todas las personas."),
}


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parsear(valor) -> Optional[datetime]:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def es_principal(usuario: Optional[Dict]) -> bool:
    """True si la cuenta es el SUPER_ADMIN principal."""
    u = usuario or {}
    return u.get("rol") == "SUPER_ADMIN" and str(u.get("usuario", "")).strip().lower() == Config.SUPERADMIN_PRINCIPAL


class Permisos:
    def __init__(self, db=None, auth=None, auditoria=None, sender=None, correo_fn=None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._auth, self._aud, self._sender, self._correo_fn = auth, auditoria, sender, correo_fn
        self._disp = None

    @property
    def auth(self):
        if self._auth is None:
            from src.auth import get_auth_manager
            self._auth = get_auth_manager()
        return self._auth

    @property
    def aud(self):
        if self._aud is None:
            self._aud = get_auditoria()
        return self._aud

    def _t(self):
        return self.db.supabase.table("permisos_operaciones")

    def disponible(self) -> bool:
        import time
        ahora = time.time()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t().select("id").limit(1).execute()
            ok = True
        except Exception as e:
            print(f"Permisos no disponibles (¿falta sql/11?): {e}")
            ok = False
        self._disp = (ok, time.time())
        return ok

    # ------------------------------------------------------------ consulta

    def _vigente(self, fila: Dict) -> bool:
        if not fila.get("activo"):
            return False
        v = _parsear(fila.get("vence_en"))
        return not (v and v <= _ahora_utc())

    def listar(self, usuario: Optional[str] = None, solo_vigentes: bool = False) -> List[Dict]:
        if not self.disponible():
            return []
        q = self._t().select("*")
        if usuario:
            q = q.eq("usuario", usuario)
        filas = q.order("id", desc=True).execute().data or []
        return [f for f in filas if self._vigente(f)] if solo_vigentes else filas

    def alcance(self, usuario: Optional[Dict], permiso: str) -> Tuple[bool, Optional[List[str]]]:
        """
        (tiene, redes): `redes` es None si el permiso vale para todas las redes,
        o la lista de redes permitidas.
        """
        if es_principal(usuario):
            return True, None
        nombre = str((usuario or {}).get("usuario", "")).strip()
        if not nombre or not self.disponible():
            return False, None
        for f in self._t().select("*").eq("usuario", nombre).eq("permiso", permiso).eq("activo", True).execute().data or []:
            if self._vigente(f):
                redes = f.get("redes")
                return True, (list(redes) if redes else None)
        return False, None

    def tiene(self, usuario: Optional[Dict], permiso: str) -> bool:
        return self.alcance(usuario, permiso)[0]

    def permisos_de(self, usuario: Optional[Dict]) -> Dict[str, Optional[List[str]]]:
        """{permiso: redes|None} de los permisos vigentes de una persona."""
        return {p: self.alcance(usuario, p)[1] for p in PERMISOS if self.alcance(usuario, p)[0]}

    # ------------------------------------------------------------ administrar (solo el principal)

    def _actor_principal(self, token: str) -> Tuple[Optional[Dict], Optional[str]]:
        if not self.auth.es_superadmin_principal(token):
            return None, "Solo el SUPER_ADMIN principal puede asignar permisos."
        return self.auth.obtener_usuario_actual(token), None

    def otorgar(self, token: str, usuario: str, permiso: str, redes: Optional[List[str]] = None,
                vence_en: Optional[datetime] = None, nota: str = "") -> Tuple[bool, str]:
        actor, err = self._actor_principal(token)
        if err:
            return False, err
        if permiso not in PERMISOS:
            return False, "Permiso desconocido."
        if not self.disponible():
            return False, "Falta ejecutar sql/11_auditoria_permisos_repositorio.sql en Supabase."
        adm = self.db.obtener_administrador(usuario)
        if not adm or not adm.get("activo", True):
            return False, "La cuenta no existe o está desactivada."
        if str(usuario).strip().lower() == Config.SUPERADMIN_PRINCIPAL:
            return False, "El SUPER_ADMIN principal ya tiene todos los permisos."
        if vence_en is not None:
            if vence_en.tzinfo is None:          # sin zona = hora de Lima
                vence_en = vence_en.replace(tzinfo=LIMA)
            if vence_en <= _ahora_utc():
                return False, "La fecha de vencimiento ya pasó."
        existente = [f for f in self.listar(usuario) if f.get("permiso") == permiso and f.get("activo")]
        redes = [r for r in (redes or []) if r] or None
        detalle = {"destinatario": usuario, "permiso": permiso, "redes": redes or "todas",
                   "vence_en": vence_en.isoformat() if vence_en else None, "nota": (nota or "")[:300],
                   "reemplaza": bool(existente)}
        try:
            self.aud.registrar(actor["usuario"], "PERMISO_OTORGADO", "PERMISOS", rol=actor.get("rol"),
                               objeto=f"{usuario} · {permiso}", detalle=detalle, obligatorio=True)
        except AuditoriaError as e:
            return False, str(e)
        for f in existente:   # el nuevo reemplaza al vigente
            self._t().update({"activo": False, "revocado_por": actor["usuario"], "fecha_revocacion": _ahora_utc().isoformat(),
                              "motivo_revocacion": "Reemplazado por un permiso nuevo"}).eq("id", f["id"]).execute()
        try:
            r = self._t().insert({"usuario": usuario, "permiso": permiso, "redes": redes,
                                  "vence_en": vence_en.isoformat() if vence_en else None, "activo": True,
                                  "nota": (nota or "")[:300] or None, "otorgado_por": actor["usuario"]}).execute().data
            if not r:
                return False, "No se pudo guardar el permiso."
        except Exception as e:
            return False, f"No se pudo guardar el permiso: {e}"
        self._avisar(adm, actor, "otorgado", permiso, redes, vence_en, nota)
        return True, "Permiso otorgado."

    def revocar(self, token: str, permiso_id: int, motivo: str = "") -> Tuple[bool, str]:
        actor, err = self._actor_principal(token)
        if err:
            return False, err
        if not self.disponible():
            return False, "Falta ejecutar sql/11_auditoria_permisos_repositorio.sql en Supabase."
        fila = (self._t().select("*").eq("id", permiso_id).limit(1).execute().data or [None])[0]
        if not fila or not fila.get("activo"):
            return False, "El permiso no existe o ya estaba revocado."
        try:
            self.aud.registrar(actor["usuario"], "PERMISO_REVOCADO", "PERMISOS", rol=actor.get("rol"),
                               objeto=f"{fila['usuario']} · {fila['permiso']}",
                               detalle={"destinatario": fila["usuario"], "permiso": fila["permiso"], "motivo": (motivo or "")[:300]},
                               obligatorio=True)
        except AuditoriaError as e:
            return False, str(e)
        r = self._t().update({"activo": False, "revocado_por": actor["usuario"], "fecha_revocacion": _ahora_utc().isoformat(),
                              "motivo_revocacion": (motivo or "")[:300] or None}).eq("id", permiso_id).execute().data
        if not r:
            return False, "No se pudo revocar el permiso."
        adm = self.db.obtener_administrador(fila["usuario"])
        if adm:
            self._avisar(adm, actor, "revocado", fila["permiso"], None, None, motivo)
        return True, "Permiso revocado."

    def revocar_todos(self, token: str, usuario: str, motivo: str = "") -> Tuple[bool, str]:
        vigentes = [f for f in self.listar(usuario) if f.get("activo")]
        if not vigentes:
            return False, "La cuenta no tiene permisos vigentes."
        n = 0
        for f in vigentes:
            ok, msg = self.revocar(token, f["id"], motivo)
            if not ok:
                return False, msg
            n += 1
        return True, f"Se revocaron {n} permiso(s)."

    # ------------------------------------------------------------ correo

    def _avisar(self, adm: Dict, actor: Dict, tipo: str, permiso: str, redes, vence_en, nota) -> None:
        try:
            from src.email_auditoria import enviar_aviso_permiso
            sender = self._sender
            if sender is None:
                from src.email_sender import get_email_sender
                sender = get_email_sender()
            enviar_aviso_permiso(sender, adm, actor, tipo, PERMISOS[permiso][0], redes, vence_en, nota)
        except Exception as e:
            print(f"No se pudo avisar del permiso: {e}")


_permisos = None


def get_permisos() -> Permisos:
    global _permisos
    from src.db_manager import get_db_manager
    db = get_db_manager()
    if _permisos is None or _permisos.db is not db:
        _permisos = Permisos(db)
    return _permisos
