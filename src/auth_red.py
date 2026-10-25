# src/auth_red.py
"""
Autenticación para el login por red ("Progreso por Red").

Cada red asistencial tiene su propia contraseña -- generada y
distribuida manualmente por el administrador, no hay autoregistro --
para consultar UNICAMENTE su propio progreso de envíos semana a
semana (igual que "Progreso por Red" en el panel de administrador,
pero limitado a una sola red). No da acceso al formulario de envío ni
a los datos de otras redes.

Es un sistema de login paralelo y separado de src/auth.py (login de
administradores): comparten solo el hashing de contraseñas (ver
src/security.py) para no duplicar esa lógica.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from src.db_manager import get_db_manager
from src.password_policy import validar as validar_password
from src.security import hash_password, verificar_password


class RedAuthManager:
    """Gestor de autenticación y sesiones para el login por red."""

    def __init__(self):
        self.db = get_db_manager()
        self._intentos_fallidos = {}
        self._bloqueos_temporales = {}
        from src.session_store import AlmacenSesiones
        self._bloqueos_bd = AlmacenSesiones("red")
        self._sesiones_activas = {}

    def _generar_token(self) -> str:
        return secrets.token_urlsafe(32)

    # ============================================================
    # LOGIN
    # ============================================================

    def login(self, red: str, password: str, ip: str = None) -> Dict:
        """
        Autentica el login de una red.

        Retorna:
        {"exito": bool, "mensaje": str, "red": str or None, "token": str or None}
        """
        if not red or not password:
            return {
                "exito": False,
                "mensaje": "Seleccione su red e ingrese la contraseña",
                "red": None,
                "token": None
            }

        red = red.strip()

        # SIREA: bloqueo persistente por red y por IP.
        try:
            min_red = self._bloqueos_bd.minutos_bloqueo("sujeto", red.lower())
            min_ip = self._bloqueos_bd.minutos_bloqueo("ip", ip)
        except Exception:
            min_red = min_ip = 0
        if min_red or min_ip:
            return {
                "exito": False,
                "mensaje": f"Demasiados intentos fallidos. Intente nuevamente en {max(min_red, min_ip)} minutos.",
                "red": None,
                "token": None
            }

        # Bloqueo temporal tras varios intentos fallidos -- misma
        # protección que usa el login de administradores.
        if red in self._bloqueos_temporales:
            tiempo_bloqueo = self._bloqueos_temporales[red]
            if datetime.now() < tiempo_bloqueo:
                minutos_restantes = max(1, (tiempo_bloqueo - datetime.now()).seconds // 60)
                return {
                    "exito": False,
                    "mensaje": f"Demasiados intentos fallidos. Intente nuevamente en {minutos_restantes} minutos.",
                    "red": None,
                    "token": None
                }
            else:
                del self._bloqueos_temporales[red]
                self._intentos_fallidos.pop(red, None)

        credencial = self.db.obtener_credencial_red(red)
        if not credencial or not credencial.get('password_hash'):
            self._registrar_intento_fallido(red, ip)
            return {"exito": False, "mensaje": "Red o contraseña incorrectos", "red": None, "token": None}

        if not credencial.get('activo', True):
            return {
                "exito": False,
                "mensaje": "El acceso de esta red está desactivado. Contacte al administrador.",
                "red": None,
                "token": None
            }

        if not verificar_password(password, credencial.get('password_hash', '')):
            self._registrar_intento_fallido(red, ip)
            return {"exito": False, "mensaje": "Red o contraseña incorrectos", "red": None, "token": None}

        # Login exitoso
        self._intentos_fallidos.pop(red, None)
        try:
            self._bloqueos_bd.limpiar_fallos("sujeto", red.lower())
        except Exception:
            pass

        token = self._generar_token()
        self._sesiones_activas[token] = {
            'red': red,
            'inicio': datetime.now(),
            'ultima_actividad': datetime.now(),
            'ip': ip
        }

        self.db.actualizar_ultimo_login_red(red)
        self.db.registrar_log(
            usuario=f"RED:{red}",
            accion='LOGIN_RED',
            detalle=f'Inicio de sesión de la red {red} desde IP: {ip or "N/A"}',
            ip=ip
        )

        return {"exito": True, "mensaje": f"Bienvenido, red {red}", "red": red, "token": token}

    def _registrar_intento_fallido(self, red: str, ip: str = None):
        if red in self._intentos_fallidos:
            intentos, _ = self._intentos_fallidos[red]
            intentos += 1
            self._intentos_fallidos[red] = (intentos, datetime.now())
            if intentos >= 5:
                self._bloqueos_temporales[red] = datetime.now() + timedelta(minutes=5)
        else:
            self._intentos_fallidos[red] = (1, datetime.now())
        try:
            self._bloqueos_bd.registrar_fallo("sujeto", (red or "").strip().lower())
            self._bloqueos_bd.registrar_fallo("ip", ip)
        except Exception:
            pass

        self.db.registrar_log(
            usuario=f"RED:{red}",
            accion='LOGIN_RED_FAILED',
            detalle=f'Intento de login de red fallido desde IP: {ip or "N/A"}',
            ip=ip
        )

    def logout(self, token: str) -> bool:
        if token in self._sesiones_activas:
            red = self._sesiones_activas[token]['red']
            self.db.registrar_log(usuario=f"RED:{red}", accion='LOGOUT_RED', detalle='Cierre de sesión de red')
            del self._sesiones_activas[token]
            return True
        return False

    def verificar_sesion(self, token: str) -> bool:
        if not token or token not in self._sesiones_activas:
            return False

        sesion = self._sesiones_activas[token]
        inicio = sesion.get('inicio')
        if inicio is None:
            self._sesiones_activas.pop(token, None)
            return False

        # Misma expiración que las sesiones de administrador (SIREA: .env).
        from src.config import Config
        if datetime.now() - inicio > timedelta(hours=Config.SESION_DURACION_HORAS):
            self._sesiones_activas.pop(token, None)
            return False
        ultima = sesion.get('ultima_actividad') or inicio
        if datetime.now() - ultima > timedelta(minutes=Config.SESION_INACTIVIDAD_MINUTOS):
            self._sesiones_activas.pop(token, None)
            return False

        sesion['ultima_actividad'] = datetime.now()
        return True

    def obtener_red_actual(self, token: str) -> Optional[str]:
        """Obtiene el nombre de la red autenticada a partir del token."""
        if not self.verificar_sesion(token):
            return None
        return self._sesiones_activas[token]['red']

    # ============================================================
    # GESTIÓN DE CREDENCIALES (uso exclusivo del administrador)
    # ============================================================

    def crear_o_actualizar_credencial(
        self, red: str, password: str, creado_por: Optional[str] = None,
        debe_cambiar_password: bool = True
    ) -> Tuple[bool, str]:
        """
        Crea la credencial de una red o, si ya existe, le asigna una
        contraseña nueva (regenerar). El administrador genera esta
        contraseña y se la entrega manualmente a la red -- no hay
        autoregistro ni recuperación automática de contraseña.

        debe_cambiar_password=True por defecto: esta contraseña la
        puso el administrador (es "temporal" desde el punto de vista
        de la red), así que se le pedirá cambiarla la primera vez que
        entre a "Ver mi progreso".
        """
        if not red:
            return False, "Debe indicar la red"
        valida, motivo = validar_password(password, contexto=[red])
        if not valida:
            return False, motivo

        password_hash = hash_password(password)
        existente = self.db.obtener_credencial_red(red)

        if existente:
            exito = self.db.actualizar_credencial_red(
                red, password_hash=password_hash, activo=True,
                debe_cambiar_password=debe_cambiar_password
            )
            accion = 'RESET_PASSWORD_RED'
            mensaje_ok = f"Contraseña de la red '{red}' actualizada exitosamente"
        else:
            exito = self.db.crear_credencial_red(
                red, password_hash=password_hash, creado_por=creado_por,
                debe_cambiar_password=debe_cambiar_password
            )
            accion = 'CREAR_CREDENCIAL_RED'
            mensaje_ok = f"Credencial creada para la red '{red}'"

        if exito:
            self.db.registrar_log(usuario=creado_por or 'SYSTEM', accion=accion, detalle=f"Red: {red}")
            return True, mensaje_ok
        return False, f"No se pudo guardar la credencial de la red '{red}'"

    def debe_cambiar_password(self, red: str) -> bool:
        """Indica si la red debe cambiar su contraseña antes de poder
        ver su progreso (contraseña temporal/asignada por el admin)."""
        credencial = self.db.obtener_credencial_red(red)
        if not credencial:
            return False
        return bool(credencial.get('debe_cambiar_password', False))

    def cambiar_password_propio(self, red: str, password_nueva: str) -> Tuple[bool, str]:
        """
        Permite que la propia red cambie su contraseña (ya sea porque
        es obligatorio tras usar una contraseña temporal, o de forma
        voluntaria desde "Ver mi progreso"). A diferencia de
        crear_o_actualizar_credencial (uso del administrador), esto
        siempre deja debe_cambiar_password en False: la nueva
        contraseña la eligió la propia red, ya no es temporal.
        """
        if not red:
            return False, "Red inválida"

        # Primer cambio (contraseña genérica → propia): libre y obligatorio.
        # Cambios posteriores: solo con una solicitud APROBADA y vigente
        # (ver src/solicitudes_password.py). Se exige aquí, en el servidor,
        # y no solo en la pantalla.
        forzado = self.debe_cambiar_password(red)
        solicitudes = None
        if not forzado:
            from src.solicitudes_password import get_solicitudes_password
            solicitudes = get_solicitudes_password()
            if not solicitudes.disponible():
                return False, "El cambio de contraseña requiere autorización de la OIIS. Comuníquese con la OIIS."
            if not solicitudes.habilitada(red):
                return False, "El cambio de contraseña requiere la aprobación de la OIIS. Envíe una solicitud con su sustento."

        valida, motivo = validar_password(password_nueva, contexto=[red])
        if not valida:
            return False, motivo
        # No se puede reutilizar la contraseña vigente (la temporal incluida).
        credencial = self.db.obtener_credencial_red(red) or {}
        hash_actual = credencial.get('password_hash')
        if hash_actual and verificar_password(password_nueva, hash_actual):
            return False, "La nueva contraseña debe ser distinta de la actual."

        password_hash = hash_password(password_nueva)
        exito = self.db.actualizar_credencial_red(
            red, password_hash=password_hash, debe_cambiar_password=False
        )
        if exito:
            if solicitudes is not None:
                solicitudes.completar(red)
            self.db.registrar_log(
                usuario=f"RED:{red}", accion='CAMBIO_PASSWORD_RED_PROPIO',
                detalle=f"La red {red} cambió su propia contraseña"
                        + ("" if forzado else " (con aprobación de la OIIS)")
            )
            return True, "Contraseña actualizada exitosamente"
        return False, "No se pudo actualizar la contraseña. Intente nuevamente."

    def desactivar_credencial(self, red: str) -> Tuple[bool, str]:
        """Desactiva el acceso de una red sin borrar su credencial (se puede reactivar)."""
        exito = self.db.actualizar_credencial_red(red, activo=False)
        if exito:
            # Cerrar cualquier sesión activa de esa red de inmediato.
            tokens_a_eliminar = [
                token for token, info in self._sesiones_activas.items()
                if info.get('red') == red
            ]
            for token in tokens_a_eliminar:
                del self._sesiones_activas[token]
            return True, f"Acceso de la red '{red}' desactivado"
        return False, f"No se pudo desactivar el acceso de la red '{red}'"

    def activar_credencial(self, red: str) -> Tuple[bool, str]:
        exito = self.db.actualizar_credencial_red(red, activo=True)
        if exito:
            return True, f"Acceso de la red '{red}' activado"
        return False, f"No se pudo activar el acceso de la red '{red}'"

    def eliminar_credencial(self, red: str) -> Tuple[bool, str]:
        exito = self.db.eliminar_credencial_red(red)
        if exito:
            tokens_a_eliminar = [
                token for token, info in self._sesiones_activas.items()
                if info.get('red') == red
            ]
            for token in tokens_a_eliminar:
                del self._sesiones_activas[token]
            return True, f"Credencial de la red '{red}' eliminada"
        return False, f"No se pudo eliminar la credencial de la red '{red}'"

    def listar_credenciales(self) -> List[Dict]:
        """Lista las redes con credencial configurada, sin exponer el hash."""
        credenciales = self.db.listar_credenciales_red()
        for c in credenciales:
            c.pop('password_hash', None)
        return credenciales


# ============================================================
# FUNCIONES DE ACCESO RÁPIDO (para uso en Streamlit)
# ============================================================

_red_auth_manager = None


def get_red_auth_manager() -> RedAuthManager:
    """Retorna la instancia única del RedAuthManager."""
    global _red_auth_manager
    if _red_auth_manager is None:
        _red_auth_manager = RedAuthManager()
    return _red_auth_manager


def login_red(red: str, password: str, ip: str = None) -> Dict:
    """Función rápida para el login de una red."""
    return get_red_auth_manager().login(red, password, ip)


def logout_red(token: str) -> bool:
    """Función rápida para cerrar la sesión de una red."""
    return get_red_auth_manager().logout(token)


def verificar_sesion_red(token: str) -> bool:
    """Función rápida para verificar la sesión de una red."""
    return get_red_auth_manager().verificar_sesion(token)


def obtener_red_actual(token: str) -> Optional[str]:
    """Función rápida para obtener la red autenticada a partir del token."""
    return get_red_auth_manager().obtener_red_actual(token)


def limpiar_cache():
    """Limpia la instancia cacheada del RedAuthManager."""
    global _red_auth_manager
    _red_auth_manager = None
