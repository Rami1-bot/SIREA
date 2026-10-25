# src/solicitudes_password.py
"""
Solicitudes de cambio de contraseña de las redes.

Regla: la primera vez (contraseña genérica → contraseña propia) el cambio es
obligatorio y libre. Después, para evitar cambios constantes, una red que
quiera volver a cambiarla debe:

  1. enviar un sustento (formulario con mensaje predefinido y editable);
  2. esperar la revisión de un SUPER_ADMIN, que puede responder pidiendo más
     información (intercambio de mensajes en ambas pantallas);
  3. si se aprueba, se habilita el cambio por un tiempo limitado
     (HORAS_VALIDEZ_CAMBIO_PASSWORD) y se marca como COMPLETADA al usarse.

Estados: PENDIENTE → APROBADA → COMPLETADA | RECHAZADA | CANCELADA | VENCIDA
Solo puede haber una solicitud abierta (PENDIENTE o APROBADA) por red.
"""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from src.config import Config
from src.db_manager import get_db_manager
from src.validacion_correo import evaluar as evaluar_correo, normalizar as normalizar_correo

ABIERTAS = ("PENDIENTE", "APROBADA")
MIN_SUSTENTO = 30          # caracteres (sin contar el texto de la plantilla)
MAX_TEXTO = 2000
PLACEHOLDER = "[Escriba aquí el motivo del cambio]"


def plantilla_sustento(red: str, nombre: str = "") -> str:
    """Mensaje predefinido que la red completa y edita antes de enviarlo."""
    firma = nombre.strip() or "[Su nombre]"
    return (
        "Estimados señores de la OIIS:\n\n"
        f"Por medio del presente, la red {red} solicita autorización para cambiar la contraseña "
        "de acceso a su portal del SIREA, por el siguiente motivo:\n\n"
        f"{PLACEHOLDER}\n\n"
        "Agradezco de antemano su atención.\n\n"
        f"Atentamente,\n{firma}\nRed {red}"
    )


def parsear_fecha(valor) -> Optional[datetime]:
    """ISO de la base de datos → datetime con zona horaria (UTC si no la trae)."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fecha_lima(valor, con_hora: bool = True) -> str:
    """Fecha de la base de datos mostrada en hora de Lima (UTC-5)."""
    d = parsear_fecha(valor)
    if not d:
        return "—"
    d = d.astimezone(timezone(timedelta(hours=-5)))
    return d.strftime("%d/%m/%Y %H:%M") if con_hora else d.strftime("%d/%m/%Y")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class SolicitudesPassword:
    """Lógica del flujo de solicitudes (la pantalla solo dibuja)."""

    def __init__(self):
        self.db = get_db_manager()

    # ---------------- consulta ----------------

    def disponible(self) -> bool:
        return self.db.solicitudes_password_disponibles()

    def _revisar_vencimiento(self, sol: Optional[Dict]) -> Optional[Dict]:
        """Una solicitud APROBADA cuyo plazo pasó se marca VENCIDA."""
        if sol and sol.get("estado") == "APROBADA":
            venc = parsear_fecha(sol.get("fecha_vencimiento"))
            if venc and _ahora() > venc:
                self.db.actualizar_solicitud_password(sol["id"], estado="VENCIDA")
                sol = {**sol, "estado": "VENCIDA"}
        return sol

    def abierta(self, red: str) -> Optional[Dict]:
        lista = self.db.listar_solicitudes_password(red=red, estados=list(ABIERTAS), limit=1)
        return self._revisar_vencimiento(lista[0]) if lista else None

    def ultima(self, red: str) -> Optional[Dict]:
        """La solicitud más reciente de la red (abierta o cerrada)."""
        lista = self.db.listar_solicitudes_password(red=red, limit=1)
        return self._revisar_vencimiento(lista[0]) if lista else None

    def obtener(self, solicitud_id) -> Optional[Dict]:
        return self._revisar_vencimiento(self.db.obtener_solicitud_password(solicitud_id))

    def listar(self, estados: Optional[List[str]] = None, limit: int = 100) -> List[Dict]:
        return [self._revisar_vencimiento(s) for s in self.db.listar_solicitudes_password(estados=estados, limit=limit)]

    def mensajes(self, solicitud_id) -> List[Dict]:
        return self.db.obtener_mensajes_solicitud(solicitud_id)

    def pendientes(self) -> int:
        """Solicitudes que esperan respuesta de la OIIS (para el aviso del panel)."""
        if not self.disponible():
            return 0
        return self.db.contar_solicitudes_password("PENDIENTE")

    def habilitada(self, red: str) -> Optional[Dict]:
        """Solicitud APROBADA y vigente que permite cambiar la contraseña ahora."""
        sol = self.abierta(red)
        return sol if sol and sol.get("estado") == "APROBADA" else None

    # ---------------- acciones de la red ----------------

    @staticmethod
    def _texto_valido(texto: str) -> Tuple[bool, str]:
        t = (texto or "").strip()
        if not t:
            return False, "Escriba el mensaje."
        if len(t) > MAX_TEXTO:
            return False, f"El mensaje es demasiado largo (máximo {MAX_TEXTO} caracteres)."
        return True, t

    def crear(self, red: str, nombre: str, correo: str, texto: str) -> Tuple[bool, str, Optional[Dict]]:
        """La red envía su sustento. Registra la solicitud y envía los correos."""
        if not self.disponible():
            return False, "El módulo de solicitudes aún no está habilitado. Comuníquese con la OIIS.", None
        nombre = (nombre or "").strip()
        if len(nombre) < 3:
            return False, "Ingrese su nombre completo.", None
        correo = normalizar_correo(correo)
        ev = evaluar_correo(correo, correo, confirmado_no_institucional=True)
        if ev["estado"] != "ok":
            return False, ev["detalle"] or ev["mensaje"], None

        texto = (texto or "").replace("[Su nombre]", nombre)
        ok, texto = self._texto_valido(texto)
        if not ok:
            return False, texto, None
        if PLACEHOLDER in texto:
            return False, "Reemplace el texto entre corchetes por el motivo del cambio.", None
        base = plantilla_sustento(red, nombre).replace(PLACEHOLDER, "")
        conserva_plantilla = base[:60] in texto
        motivo_ok = (len(texto) - len(base) >= MIN_SUSTENTO) if conserva_plantilla else (len(texto) >= 80)
        if not motivo_ok:
            return False, "Explique el motivo con más detalle (por ejemplo, por qué la contraseña actual ya no es segura).", None

        if self.abierta(red):
            return False, "Su red ya tiene una solicitud en curso. Continúe el intercambio en esa solicitud.", None

        codigo = f"SOL-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
        sol = self.db.crear_solicitud_password(codigo, red, nombre, correo)
        if not sol:
            return False, "No se pudo registrar la solicitud. Intente nuevamente.", None
        self.db.agregar_mensaje_solicitud(sol["id"], "RED", nombre, texto)
        self.db.registrar_log(usuario=f"RED:{red}", accion="SOLICITUD_PASSWORD",
                              detalle=f"Solicitud {codigo} enviada por {nombre}")
        self._correo_nueva(sol, texto)
        return True, f"Solicitud {codigo} enviada. Recibirá un acuse en su correo.", sol

    def responder_red(self, solicitud_id, red: str, texto: str) -> Tuple[bool, str]:
        sol = self.obtener(solicitud_id)
        if not sol or sol.get("red") != red:
            return False, "No se encontró la solicitud."
        if sol.get("estado") != "PENDIENTE":
            return False, "La solicitud ya no admite más mensajes."
        ok, texto = self._texto_valido(texto)
        if not ok:
            return False, texto
        self.db.agregar_mensaje_solicitud(sol["id"], "RED", sol.get("nombre") or red, texto)
        return True, "Mensaje enviado."

    def cancelar(self, solicitud_id, red: str) -> Tuple[bool, str]:
        sol = self.obtener(solicitud_id)
        if not sol or sol.get("red") != red or sol.get("estado") not in ABIERTAS:
            return False, "No se encontró una solicitud abierta."
        self.db.actualizar_solicitud_password(sol["id"], estado="CANCELADA", fecha_resolucion=_ahora().isoformat())
        self.db.agregar_mensaje_solicitud(sol["id"], "SISTEMA", "Sistema", "La red canceló la solicitud.")
        self.db.registrar_log(usuario=f"RED:{red}", accion="SOLICITUD_PASSWORD_CANCELADA",
                              detalle=f"Solicitud {sol.get('codigo')} cancelada por la red")
        return True, "Solicitud cancelada."

    def completar(self, red: str) -> None:
        """Se llama cuando la red usó su autorización: la solicitud queda cerrada."""
        sol = self.abierta(red)
        if sol and sol.get("estado") == "APROBADA":
            self.db.actualizar_solicitud_password(sol["id"], estado="COMPLETADA", fecha_uso=_ahora().isoformat())
            self.db.agregar_mensaje_solicitud(sol["id"], "SISTEMA", "Sistema", "La red cambió su contraseña.")

    # ---------------- acciones del administrador ----------------

    def responder_admin(self, solicitud_id, admin_usuario: str, admin_nombre: str, texto: str) -> Tuple[bool, str]:
        sol = self.obtener(solicitud_id)
        if not sol or sol.get("estado") != "PENDIENTE":
            return False, "La solicitud ya no está pendiente."
        ok, texto = self._texto_valido(texto)
        if not ok:
            return False, texto
        self.db.agregar_mensaje_solicitud(sol["id"], "ADMIN", admin_nombre or admin_usuario, texto)
        self.db.registrar_log(usuario=admin_usuario, accion="SOLICITUD_PASSWORD_RESPUESTA",
                              detalle=f"Respuesta a {sol.get('codigo')} (red {sol.get('red')})")
        self._correo_respuesta(sol, "RESPUESTA", texto, admin_nombre or admin_usuario)
        return True, "Respuesta enviada a la red."

    def aprobar(self, solicitud_id, admin_usuario: str, admin_nombre: str, mensaje: str = "") -> Tuple[bool, str]:
        sol = self.obtener(solicitud_id)
        if not sol or sol.get("estado") != "PENDIENTE":
            return False, "La solicitud ya no está pendiente."
        horas = Config.HORAS_VALIDEZ_CAMBIO_PASSWORD
        ahora = _ahora()
        if not self.db.actualizar_solicitud_password(
            sol["id"], estado="APROBADA", fecha_resolucion=ahora.isoformat(), resuelto_por=admin_usuario,
            fecha_vencimiento=(ahora + timedelta(hours=horas)).isoformat()
        ):
            return False, "No se pudo aprobar la solicitud."
        texto = (mensaje or "").strip() or "Su solicitud fue aprobada. Ya puede elegir su nueva contraseña."
        self.db.agregar_mensaje_solicitud(sol["id"], "ADMIN", admin_nombre or admin_usuario, texto)
        self.db.agregar_mensaje_solicitud(
            sol["id"], "SISTEMA", "Sistema",
            f"Solicitud aprobada por {admin_nombre or admin_usuario}. Cambio habilitado por {horas} horas.")
        self.db.registrar_log(usuario=admin_usuario, accion="SOLICITUD_PASSWORD_APROBADA",
                              detalle=f"Solicitud {sol.get('codigo')} aprobada (red {sol.get('red')})")
        self._correo_respuesta(sol, "APROBADA", texto, admin_nombre or admin_usuario, horas)
        return True, f"Solicitud aprobada. La red {sol.get('red')} ya puede cambiar su contraseña."

    def rechazar(self, solicitud_id, admin_usuario: str, admin_nombre: str, motivo: str) -> Tuple[bool, str]:
        sol = self.obtener(solicitud_id)
        if not sol or sol.get("estado") != "PENDIENTE":
            return False, "La solicitud ya no está pendiente."
        motivo = (motivo or "").strip()
        if len(motivo) < 10:
            return False, "Indique el motivo del rechazo (mínimo 10 caracteres)."
        if len(motivo) > MAX_TEXTO:
            return False, f"El motivo es demasiado largo (máximo {MAX_TEXTO} caracteres)."
        if not self.db.actualizar_solicitud_password(
            sol["id"], estado="RECHAZADA", fecha_resolucion=_ahora().isoformat(), resuelto_por=admin_usuario
        ):
            return False, "No se pudo rechazar la solicitud."
        self.db.agregar_mensaje_solicitud(sol["id"], "ADMIN", admin_nombre or admin_usuario, motivo)
        self.db.agregar_mensaje_solicitud(sol["id"], "SISTEMA", "Sistema",
                                          f"Solicitud rechazada por {admin_nombre or admin_usuario}.")
        self.db.registrar_log(usuario=admin_usuario, accion="SOLICITUD_PASSWORD_RECHAZADA",
                              detalle=f"Solicitud {sol.get('codigo')} rechazada (red {sol.get('red')})")
        self._correo_respuesta(sol, "RECHAZADA", motivo, admin_nombre or admin_usuario)
        return True, "Solicitud rechazada. Se informó a la red."

    # ---------------- correos (nunca deben romper el flujo) ----------------

    def _correo_nueva(self, sol: Dict, texto: str):
        try:
            from src.email_sender import get_email_sender
            es = get_email_sender()
            es.enviar_acuse_solicitud_password(sol["correo"], sol["nombre"], sol["red"], sol["codigo"], texto)
            es.enviar_alerta_solicitud_password(sol["red"], sol["nombre"], sol["correo"], sol["codigo"], texto)
        except Exception as e:
            print(f"No se pudieron enviar los correos de la solicitud: {e}")

    def _correo_respuesta(self, sol: Dict, tipo: str, texto: str, responsable: str, horas: Optional[int] = None):
        try:
            from src.email_sender import get_email_sender
            get_email_sender().enviar_respuesta_solicitud_password(
                sol["correo"], sol["nombre"], sol["red"], sol["codigo"], tipo, texto, responsable, horas)
        except Exception as e:
            print(f"No se pudo enviar el correo de respuesta: {e}")


_instancia = None


def get_solicitudes_password() -> SolicitudesPassword:
    global _instancia
    if _instancia is None:
        _instancia = SolicitudesPassword()
    return _instancia
