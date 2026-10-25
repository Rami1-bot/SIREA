# src/auth.py
"""
Autenticación y gestión de sesiones para administradores.
Maneja login, logout, verificación de permisos y control de sesiones.
VERSIÓN MEJORADA CON BCRYPT Y MIGRACIÓN AUTOMÁTICA
"""

import hashlib
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from src.config import Config
from src.db_manager import get_db_manager
from src.password_policy import validar as validar_password, usuario_demasiado_comun
from src.security import hash_password as _hash_password_bcrypt, verificar_password as _verificar_password_bcrypt


class AuthManager:
    """
    Gestor de autenticación y sesiones.
    """
    
    def __init__(self):
        """Inicializa el gestor de autenticación."""
        self.db = get_db_manager()
        self._intentos_fallidos = {}
        self._sesiones_activas = {}
        self._bloqueos_temporales = {}
        # SIREA: bloqueos por usuario y por IP persistentes en Supabase
        # (sql/51_sesiones_e_intentos_login.sql); si la tabla no existe cae a memoria.
        from src.session_store import AlmacenSesiones
        self._bloqueos_bd = AlmacenSesiones("admin")
    
    # ============================================================
    # MÉTODOS DE HASH Y SEGURIDAD - NUEVA VERSIÓN CON BCRYPT
    # ============================================================
    
    def _hash_password(self, password: str) -> str:
        """
        Genera un hash bcrypt de la contraseña (delega en src/security.py,
        compartido con el login por red para no duplicar esta lógica).
        """
        try:
            return _hash_password_bcrypt(password)
        except Exception as e:
            print(f"Error al hashear contraseña: {e}")
            # En caso de error, no deberíamos continuar
            raise

    def _verificar_password(self, password: str, hash_almacenado: str) -> bool:
        """
        Verifica si la contraseña coincide con el hash bcrypt almacenado.
        """
        return _verificar_password_bcrypt(password, hash_almacenado)
    
    def _es_hash_antiguo(self, hash_str: str) -> bool:
        """
        Detecta si el hash es del tipo antiguo (SHA-256 con salt fijo).
        Los hashes SHA-256 tienen 64 caracteres hexadecimales.
        """
        if not hash_str:
            return False
        # SHA-256 produce 64 caracteres hexadecimales
        return len(hash_str) == 64 and all(c in '0123456789abcdefABCDEF' for c in hash_str)
    
    def _generar_token(self) -> str:
        """
        Genera un token de sesión único.
        """
        return secrets.token_urlsafe(32)
    
    def _validar_email(self, email: str) -> bool:
        """
        Valida un correo electrónico.
        """
        patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(patron, email))
    
    # ============================================================
    # MÉTODOS DE AUTENTICACIÓN - CON MIGRACIÓN AUTOMÁTICA
    # ============================================================
    
    def login(self, usuario: str, password: str, ip: str = None) -> Dict:
        """
        Autentica a un administrador.
        INCLUYE MIGRACIÓN AUTOMÁTICA de contraseñas antiguas a bcrypt.
        
        Retorna:
        {
            "exito": bool,
            "mensaje": str,
            "usuario": Dict or None,
            "token": str or None
        }
        """
        # SIREA: bloqueo persistente por usuario y por IP (sobrevive reinicios).
        try:
            min_usr = self._bloqueos_bd.minutos_bloqueo("sujeto", (usuario or "").strip().lower())
            min_ip = self._bloqueos_bd.minutos_bloqueo("ip", ip)
        except Exception:
            min_usr = min_ip = 0
        if min_usr or min_ip:
            minutos = max(min_usr, min_ip)
            return {
                "exito": False,
                "mensaje": f"Demasiados intentos fallidos. Intente nuevamente en {minutos} minutos.",
                "usuario": None,
                "token": None
            }

        # Verificar si el usuario está bloqueado
        if usuario in self._bloqueos_temporales:
            tiempo_bloqueo = self._bloqueos_temporales[usuario]
            if datetime.now() < tiempo_bloqueo:
                minutos_restantes = max(1, (tiempo_bloqueo - datetime.now()).seconds // 60)
                return {
                    "exito": False,
                    "mensaje": f"Usuario bloqueado. Intente nuevamente en {minutos_restantes} minutos.",
                    "usuario": None,
                    "token": None
                }
            else:
                # Desbloquear
                del self._bloqueos_temporales[usuario]
                if usuario in self._intentos_fallidos:
                    del self._intentos_fallidos[usuario]
        
        # Verificar intentos fallidos
        if usuario in self._intentos_fallidos:
            intentos, ultimo_intento = self._intentos_fallidos[usuario]
            if intentos >= 5:
                tiempo_espera = datetime.now() - ultimo_intento
                if tiempo_espera < timedelta(minutes=5):
                    return {
                        "exito": False,
                        "mensaje": "Demasiados intentos fallidos. Espere 5 minutos.",
                        "usuario": None,
                        "token": None
                    }
                else:
                    # Reiniciar contador
                    del self._intentos_fallidos[usuario]
        
        # Validar campos
        if not usuario or not password:
            return {
                "exito": False,
                "mensaje": "Usuario y contraseña son obligatorios",
                "usuario": None,
                "token": None
            }
        
        # Limpiar entrada
        usuario = usuario.strip()
        
        # Buscar administrador
        admin = self.db.obtener_administrador(usuario)
        if not admin or not admin.get('password_hash'):
            self._registrar_intento_fallido(usuario, ip)
            return {
                "exito": False,
                "mensaje": "Usuario o contraseña incorrectos",
                "usuario": None,
                "token": None
            }
        
        # Verificar si el administrador está activo
        if not admin.get('activo', True):
            return {
                "exito": False,
                "mensaje": "Usuario inactivo. Contacte al administrador del sistema.",
                "usuario": None,
                "token": None
            }
        
        # Verificar contraseña con bcrypt
        hash_actual = admin.get('password_hash', '')
        
        # PRIMERO: Verificar si la contraseña es correcta usando bcrypt
        if not self._verificar_password(password, hash_actual):
            # Si falla, verificar si es un hash antiguo (SHA-256)
            if self._es_hash_antiguo(hash_actual):
                # Intentar verificar con el método antiguo
                if self._verificar_password_antigua(password, hash_actual):
                    # ¡Contraseña correcta! Migrar a bcrypt automáticamente
                    try:
                        nuevo_hash = self._hash_password(password)
                        self.db.actualizar_administrador(usuario=usuario, password_hash=nuevo_hash)
                        self.db.registrar_log(
                            usuario=usuario,
                            accion='MIGRACION_PASSWORD',
                            detalle='Contraseña migrada a bcrypt automáticamente',
                            ip=ip
                        )
                        print(f"✅ Contraseña de '{usuario}' migrada a bcrypt")
                    except Exception as e:
                        print(f"⚠️ Error al migrar contraseña de '{usuario}': {e}")
                        # No falla el login, solo registramos el error
                        self.db.registrar_log(
                            usuario=usuario,
                            accion='ERROR_MIGRACION',
                            detalle=f'Error al migrar contraseña: {str(e)}',
                            ip=ip
                        )
                else:
                    # Contraseña incorrecta
                    self._registrar_intento_fallido(usuario, ip)
                    return {
                        "exito": False,
                        "mensaje": "Usuario o contraseña incorrectos",
                        "usuario": None,
                        "token": None
                    }
            else:
                # Contraseña incorrecta
                self._registrar_intento_fallido(usuario, ip)
                return {
                    "exito": False,
                    "mensaje": "Usuario o contraseña incorrectos",
                    "usuario": None,
                    "token": None
                }
        
        # Limpiar intentos fallidos
        if usuario in self._intentos_fallidos:
            del self._intentos_fallidos[usuario]
        try:
            self._bloqueos_bd.limpiar_fallos("sujeto", (usuario or "").strip().lower())
        except Exception:
            pass
        
        # Login exitoso
        token = self._generar_token()
        self._sesiones_activas[token] = {
            'usuario': usuario,
            'nombre': admin.get('nombre', usuario),
            'rol': admin.get('rol', 'ADMIN'),
            'email': admin.get('email', ''),
            'inicio': datetime.now(),
            'ultima_actividad': datetime.now(),
            'ip': ip
        }
        
        # Registrar log
        self.db.registrar_log(
            usuario=usuario,
            accion='LOGIN',
            detalle=f'Inicio de sesión exitoso desde IP: {ip or "N/A"}',
            ip=ip
        )
        
        # Actualizar último login
        self.db.actualizar_ultimo_login(usuario)
        
        return {
            "exito": True,
            "mensaje": f"Bienvenido {admin.get('nombre', usuario)}",
            "usuario": admin,
            "token": token
        }
    
    def _verificar_password_antigua(self, password: str, hash_almacenado: str) -> bool:
        """
        Verifica contraseña usando el método antiguo (SHA-256 con salt fijo).
        Solo para migración.
        """
        if not hash_almacenado:
            return False
        # Método antiguo de hashing
        salt = "ESSALUD_SALT_2024"
        hash_calculado = hashlib.sha256((salt + password).encode()).hexdigest()
        return hash_calculado == hash_almacenado
    
    def logout(self, token: str) -> bool:
        """
        Cierra la sesión de un administrador.
        """
        if token in self._sesiones_activas:
            usuario = self._sesiones_activas[token]['usuario']
            # Registrar log
            self.db.registrar_log(
                usuario=usuario,
                accion='LOGOUT',
                detalle='Cierre de sesión'
            )
            del self._sesiones_activas[token]
            return True
        return False
    
    def verificar_sesion(self, token: str) -> bool:
        """
        Verifica si un token de sesión es válido.
        """
        if not token or token not in self._sesiones_activas:
            return False
        
        sesion = self._sesiones_activas[token]
        
        # Verificar expiración (8 horas)
        inicio = sesion.get('inicio')
        if inicio is None:
            del self._sesiones_activas[token]
            return False
        
        from src.config import Config
        if datetime.now() - inicio > timedelta(hours=Config.SESION_DURACION_HORAS):
            del self._sesiones_activas[token]
            return False

        # SIREA: expiración por inactividad.
        ultima = sesion.get('ultima_actividad') or inicio
        if datetime.now() - ultima > timedelta(minutes=Config.SESION_INACTIVIDAD_MINUTOS):
            del self._sesiones_activas[token]
            return False
        
        # Actualizar última actividad
        sesion['ultima_actividad'] = datetime.now()
        
        return True
    
    def obtener_usuario_actual(self, token: str) -> Optional[Dict]:
        """
        Obtiene el usuario actual a partir del token.
        """
        if not self.verificar_sesion(token):
            return None
        
        info = self._sesiones_activas[token]
        return {
            'usuario': info.get('usuario', ''),
            'nombre': info.get('nombre', ''),
            'rol': info.get('rol', 'ADMIN'),
            'email': info.get('email', '')
        }
    
    # ============================================================
    # MÉTODOS DE PERMISOS
    # ============================================================
    
    def es_super_admin(self, token: str) -> bool:
        """
        Verifica si el usuario es SUPER_ADMIN.
        """
        usuario = self.obtener_usuario_actual(token)
        if not usuario:
            return False
        return usuario.get('rol') == 'SUPER_ADMIN'
    
    def es_admin(self, token: str) -> bool:
        """
        Verifica si el usuario es ADMIN o SUPER_ADMIN.
        """
        usuario = self.obtener_usuario_actual(token)
        if not usuario:
            return False
        return usuario.get('rol') in ['ADMIN', 'SUPER_ADMIN']
    
    def verificar_permiso(self, token: str, permiso: str) -> bool:
        """
        Verifica si el usuario tiene un permiso específico.
        """
        usuario = self.obtener_usuario_actual(token)
        if not usuario:
            return False
        
        # SUPER_ADMIN tiene todos los permisos
        if usuario.get('rol') == 'SUPER_ADMIN':
            return True
        
        # Definir permisos por rol
        permisos_por_rol = {
            'ADMIN': [
                'ver_dashboard',
                'ver_tabla_control',
                'exportar_datos',
                'enviar_correccion',
                'ver_atrasos',
                'gestionar_drive'
            ]
        }
        
        permisos = permisos_por_rol.get(usuario.get('rol', ''), [])
        return permiso in permisos
    
    # ============================================================
    # MÉTODOS DE GESTIÓN DE ADMINISTRADORES
    # ============================================================
    
    def crear_admin(
        self,
        usuario: str,
        password: str,
        nombre: str,
        email: str,
        rol: str = 'ADMIN'
    ) -> Tuple[bool, str]:
        """
        Crea un nuevo administrador.
        Solo disponible para SUPER_ADMIN.
        """
        # Validar datos
        if not usuario or not password or not nombre or not email:
            return False, "Todos los campos son obligatorios"
        
        usuario = usuario.strip()
        
        if len(usuario) < 3:
            return False, "El usuario debe tener al menos 3 caracteres"
        
        if usuario_demasiado_comun(usuario):
            return False, f"El usuario '{usuario}' es demasiado común. Elija otro que identifique a la persona (por ejemplo, inicial y apellido)."
        
        valida, motivo = validar_password(password, contexto=[usuario, nombre, email])
        if not valida:
            return False, motivo
        
        if not self._validar_email(email):
            return False, "Correo electrónico inválido"
        
        if rol not in ['ADMIN', 'SUPER_ADMIN']:
            return False, "Rol inválido"
        
        # Crear hash de contraseña con bcrypt
        password_hash = self._hash_password(password)
        
        # Guardar en base de datos
        exito = self.db.crear_administrador(
            usuario=usuario,
            password_hash=password_hash,
            nombre=nombre,
            email=email,
            rol=rol
        )
        
        if exito:
            # Registrar en logs
            self.db.registrar_log(
                usuario='SYSTEM',
                accion='CREAR_ADMIN',
                detalle=f'Administrador "{usuario}" creado con rol {rol}'
            )
            return True, f"Administrador '{usuario}' creado exitosamente"
        else:
            return False, f"El usuario '{usuario}' ya existe"
    
    def actualizar_admin(
        self,
        usuario: str,
        nombre: Optional[str] = None,
        email: Optional[str] = None,
        rol: Optional[str] = None,
        password: Optional[str] = None,
        activo: Optional[bool] = None
    ) -> Tuple[bool, str]:
        """
        Actualiza un administrador existente.
        """
        # Verificar que existe
        admin = self.db.obtener_administrador(usuario)
        if not admin:
            return False, f"El usuario '{usuario}' no existe"
        
        # Validar email
        if email and not self._validar_email(email):
            return False, "Correo electrónico inválido"
        
        # Validar rol
        if rol and rol not in ['ADMIN', 'SUPER_ADMIN']:
            return False, "Rol inválido"
        
        # Validar contraseña
        password_hash = None
        if password:
            valida, motivo = validar_password(password, contexto=[usuario, nombre or admin.get('nombre'), email or admin.get('email')])
            if not valida:
                return False, motivo
            password_hash = self._hash_password(password)
        
        # Actualizar
        exito = self.db.actualizar_administrador(
            usuario=usuario,
            nombre=nombre,
            email=email,
            rol=rol,
            password_hash=password_hash,
            activo=activo
        )
        
        if exito:
            return True, f"Administrador '{usuario}' actualizado exitosamente"
        else:
            return False, f"Error al actualizar el administrador '{usuario}'"
    
    # ============================================================
    # CUENTAS DEL PANEL: SOLO EL SUPER_ADMIN PRINCIPAL
    # ============================================================

    def es_superadmin_principal(self, token: str) -> bool:
        """
        True solo si la sesión pertenece al SUPER_ADMIN principal
        (Config.SUPERADMIN_PRINCIPAL, por defecto «oiis.winepi»).
        """
        usuario = self.obtener_usuario_actual(token)
        if not usuario or usuario.get('rol') != 'SUPER_ADMIN':
            return False
        return str(usuario.get('usuario', '')).strip().lower() == Config.SUPERADMIN_PRINCIPAL

    def _es_cuenta_principal(self, usuario: str) -> bool:
        return str(usuario or '').strip().lower() == Config.SUPERADMIN_PRINCIPAL

    def _cerrar_sesiones_de(self, usuario: str, excepto_token: Optional[str] = None) -> int:
        tokens = [t for t, info in self._sesiones_activas.items()
                  if info.get('usuario') == usuario and t != excepto_token]
        for t in tokens:
            del self._sesiones_activas[t]
        return len(tokens)

    def actualizar_datos_cuenta(
        self,
        token: str,
        usuario: str,
        nombre: str,
        email: str,
        rol: str,
        activo: bool,
    ) -> Tuple[bool, str]:
        """
        Cambia el nombre, el correo, el rol o el estado de una cuenta del panel.
        Solo lo puede hacer el SUPER_ADMIN principal. La cuenta principal no
        puede perder su rol ni desactivarse (evita quedarse sin acceso).
        """
        if not self.es_superadmin_principal(token):
            return False, "Solo el SUPER_ADMIN principal puede modificar cuentas."

        admin = self.db.obtener_administrador(usuario)
        if not admin:
            return False, f"El usuario '{usuario}' no existe"

        nombre = (nombre or '').strip()
        email = (email or '').strip()
        if len(nombre) < 3:
            return False, "Ingrese el nombre completo (mínimo 3 caracteres)."
        if not self._validar_email(email):
            return False, "Correo electrónico inválido"
        if rol not in ('ADMIN', 'SUPER_ADMIN'):
            return False, "Rol inválido"

        if self._es_cuenta_principal(usuario):
            if rol != 'SUPER_ADMIN':
                return False, "La cuenta principal debe conservar el rol SUPER_ADMIN."
            if not activo:
                return False, "La cuenta principal no se puede desactivar."

        cambios = []
        if nombre != (admin.get('nombre') or ''):
            cambios.append('nombre')
        if email != (admin.get('email') or ''):
            cambios.append('correo')
        if rol != admin.get('rol'):
            cambios.append(f"rol {admin.get('rol')} → {rol}")
        if bool(activo) != bool(admin.get('activo', True)):
            cambios.append('activada' if activo else 'desactivada')
        if not cambios:
            return True, "No hay cambios que guardar."

        if not self.db.actualizar_administrador(
            usuario=usuario, nombre=nombre, email=email, rol=rol, activo=bool(activo)
        ):
            return False, "No se pudieron guardar los cambios."

        # Las sesiones abiertas de esa cuenta toman los datos nuevos; si se
        # desactiva o cambia de rol, se cierran para que vuelva a ingresar.
        if not activo or rol != admin.get('rol'):
            self._cerrar_sesiones_de(usuario)
        else:
            for info in self._sesiones_activas.values():
                if info.get('usuario') == usuario:
                    info['nombre'], info['email'] = nombre, email

        actual = (self.obtener_usuario_actual(token) or {}).get('usuario', 'SYSTEM')
        self.db.registrar_log(
            usuario=actual, accion='EDITAR_CUENTA',
            detalle=f'Cuenta "{usuario}" modificada: {", ".join(cambios)}')
        return True, f"Se actualizó la cuenta '{usuario}'."

    def cambiar_usuario_cuenta(self, token: str, usuario: str, usuario_nuevo: str) -> Tuple[bool, str]:
        """
        Cambia el NOMBRE DE USUARIO de una cuenta del panel. Solo el SUPER_ADMIN
        principal.

        - La cuenta principal (SUPERADMIN_PRINCIPAL) nunca cambia de usuario.
        - Nadie puede tomar el nombre de la cuenta principal (daría sus privilegios).
        - El nuevo usuario no puede existir ya (sin distinguir mayúsculas), debe
          tener 3 a 40 caracteres (letras, números, punto, guion y guion bajo)
          y no puede ser un nombre genérico.
        - Se cierran las sesiones abiertas de la cuenta (debe ingresar con el
          usuario nuevo) y queda constancia en el historial.
        """
        if not self.es_superadmin_principal(token):
            return False, "Solo el SUPER_ADMIN principal puede cambiar nombres de usuario."

        usuario = (usuario or '').strip()
        nuevo = (usuario_nuevo or '').strip()

        if self._es_cuenta_principal(usuario):
            return False, "El usuario de la cuenta principal no se puede cambiar."
        if not self.db.obtener_administrador(usuario):
            return False, f"El usuario '{usuario}' no existe"
        if nuevo == usuario:
            return True, "No hay cambios que guardar."
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", nuevo):
            return False, ("El usuario debe tener entre 3 y 40 caracteres: letras, números, "
                           "punto, guion o guion bajo (sin espacios ni tildes).")
        if self._es_cuenta_principal(nuevo):
            return False, "Ese nombre de usuario está reservado."
        if usuario_demasiado_comun(nuevo):
            return False, (f"El usuario '{nuevo}' es demasiado común. Elija otro que identifique "
                           "a la persona (por ejemplo, inicial y apellido).")
        existentes = {str(a.get('usuario', '')).strip().lower() for a in (self.db.obtener_administradores() or [])}
        if nuevo.lower() in existentes and nuevo.lower() != usuario.lower():
            return False, f"El usuario '{nuevo}' ya existe."

        if not self.db.renombrar_administrador(usuario, nuevo):
            return False, "No se pudo cambiar el usuario."

        self._cerrar_sesiones_de(usuario)
        for d in (self._intentos_fallidos, self._bloqueos_temporales):
            d.pop(usuario, None)

        actual = (self.obtener_usuario_actual(token) or {}).get('usuario', 'SYSTEM')
        self.db.registrar_log(
            usuario=actual, accion='CAMBIAR_USUARIO',
            detalle=f'Usuario de la cuenta "{usuario}" cambiado a "{nuevo}"')
        return True, f"El usuario «{usuario}» ahora es «{nuevo}». Debe ingresar con el usuario nuevo."

    def restablecer_password_admin(self, token: str, usuario: str, password_nueva: str) -> Tuple[bool, str]:
        """
        Asigna una contraseña nueva a otra cuenta del panel (sin pedir la
        anterior). Solo el SUPER_ADMIN principal. Cierra las sesiones de la
        cuenta afectada y deja constancia en el historial.
        """
        if not self.es_superadmin_principal(token):
            return False, "Solo el SUPER_ADMIN principal puede restablecer contraseñas."

        admin = self.db.obtener_administrador(usuario)
        if not admin:
            return False, f"El usuario '{usuario}' no existe"

        actual = (self.obtener_usuario_actual(token) or {}).get('usuario', '')
        if usuario == actual:
            return False, "Para cambiar su propia contraseña use la sección «Mi contraseña»."

        valida, motivo = validar_password(
            password_nueva, contexto=[usuario, admin.get('nombre'), admin.get('email')])
        if not valida:
            return False, motivo

        if not self.db.actualizar_administrador(usuario=usuario, password_hash=self._hash_password(password_nueva)):
            return False, "No se pudo actualizar la contraseña."

        cerradas = self._cerrar_sesiones_de(usuario)
        self._intentos_fallidos.pop(usuario, None)
        self._bloqueos_temporales.pop(usuario, None)
        self.db.registrar_log(
            usuario=actual, accion='RESTABLECER_PASSWORD',
            detalle=f'Contraseña de "{usuario}" restablecida ({cerradas} sesión(es) cerrada(s))')
        return True, f"La contraseña de '{usuario}' se actualizó. Entréguela por un canal seguro."

    def cambiar_password_propia(self, token: str, password_actual: str, password_nueva: str) -> Tuple[bool, str]:
        """El usuario con sesión abierta cambia su propia contraseña (pide la actual)."""
        info = self.obtener_usuario_actual(token)
        if not info:
            return False, "La sesión expiró. Vuelva a iniciar sesión."
        return self.cambiar_password(info['usuario'], password_actual, password_nueva)

    def eliminar_admin(self, usuario: str) -> Tuple[bool, str]:
        """
        Elimina un administrador.
        No permite eliminar al SUPER_ADMIN principal.
        """
        admin = self.db.obtener_administrador(usuario)
        if not admin:
            return False, f"El usuario '{usuario}' no existe"
        
        if admin.get('rol') == 'SUPER_ADMIN':
            return False, "No se puede eliminar al SUPER_ADMIN principal"
        
        exito = self.db.eliminar_administrador(usuario)
        if exito:
            # Cerrar sesiones activas de este usuario
            tokens_a_eliminar = [
                token for token, info in self._sesiones_activas.items()
                if info.get('usuario') == usuario
            ]
            for token in tokens_a_eliminar:
                del self._sesiones_activas[token]
            
            # Registrar en logs
            self.db.registrar_log(
                usuario='SYSTEM',
                accion='ELIMINAR_ADMIN',
                detalle=f'Administrador "{usuario}" eliminado'
            )
            
            return True, f"Administrador '{usuario}' eliminado exitosamente"
        else:
            return False, f"Error al eliminar el administrador '{usuario}'"
    
    def listar_admins(self) -> List[Dict]:
        """
        Lista todos los administradores.
        """
        admins = self.db.obtener_administradores()
        # Ocultar hash de contraseña
        for admin in admins:
            admin.pop('password_hash', None)
        return admins
    
    # ============================================================
    # MÉTODOS AUXILIARES
    # ============================================================
    
    def _registrar_intento_fallido(self, usuario: str, ip: str = None):
        """
        Registra un intento de login fallido.
        """
        if usuario in self._intentos_fallidos:
            intentos, _ = self._intentos_fallidos[usuario]
            intentos += 1
            self._intentos_fallidos[usuario] = (intentos, datetime.now())
            
            # Bloquear temporalmente si excede 5 intentos
            if intentos >= 5:
                self._bloqueos_temporales[usuario] = datetime.now() + timedelta(minutes=5)
        else:
            self._intentos_fallidos[usuario] = (1, datetime.now())
        
        # Registrar en logs
        self.db.registrar_log(
            usuario=usuario,
            accion='LOGIN_FAILED',
            detalle=f'Intento de login fallido desde IP: {ip or "N/A"}',
            ip=ip
        )
    
        # SIREA: contador persistente por usuario y por IP.
        try:
            self._bloqueos_bd.registrar_fallo("sujeto", (usuario or "").strip().lower())
            self._bloqueos_bd.registrar_fallo("ip", ip)
        except Exception:
            pass

    def cambiar_password(
        self,
        usuario: str,
        password_actual: str,
        password_nueva: str
    ) -> Tuple[bool, str]:
        """
        Cambia la contraseña de un administrador.
        """
        admin = self.db.obtener_administrador(usuario)
        if not admin:
            return False, "Usuario no encontrado"
        
        # Verificar contraseña actual (funciona con bcrypt y con hash antiguo)
        hash_actual = admin.get('password_hash', '')
        
        # Verificar con bcrypt primero
        if not self._verificar_password(password_actual, hash_actual):
            # Si falla, verificar con método antiguo
            if self._es_hash_antiguo(hash_actual):
                if not self._verificar_password_antigua(password_actual, hash_actual):
                    return False, "Contraseña actual incorrecta"
            else:
                return False, "Contraseña actual incorrecta"
        
        valida, motivo = validar_password(
            password_nueva, contexto=[usuario, admin.get('nombre'), admin.get('email')], actual=password_actual
        )
        if not valida:
            return False, motivo
        
        # Generar nuevo hash con bcrypt
        password_hash = self._hash_password(password_nueva)
        exito = self.db.actualizar_administrador(
            usuario=usuario,
            password_hash=password_hash
        )
        
        if exito:
            # Cerrar sesiones activas de este usuario
            tokens_a_eliminar = [
                token for token, info in self._sesiones_activas.items()
                if info.get('usuario') == usuario
            ]
            for token in tokens_a_eliminar:
                del self._sesiones_activas[token]
            
            # Registrar en logs
            self.db.registrar_log(
                usuario=usuario,
                accion='CAMBIO_PASSWORD',
                detalle='Cambio de contraseña exitoso (bcrypt)'
            )
            
            return True, "Contraseña actualizada exitosamente"
        else:
            return False, "Error al actualizar la contraseña"
    
    def obtener_sesiones_activas(self) -> List[Dict]:
        """
        Obtiene la lista de sesiones activas.
        """
        sesiones = []
        for token, info in self._sesiones_activas.items():
            inicio = info.get('inicio', datetime.now())
            ultima = info.get('ultima_actividad', inicio)
            
            sesiones.append({
                'token': token[:8] + '...',  # Mostrar solo parte del token
                'usuario': info.get('usuario', ''),
                'nombre': info.get('nombre', ''),
                'rol': info.get('rol', ''),
                'inicio': inicio.strftime('%Y-%m-%d %H:%M:%S') if hasattr(inicio, 'strftime') else str(inicio),
                'ultima_actividad': ultima.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ultima, 'strftime') else str(ultima),
                'ip': info.get('ip', 'N/A')
            })
        return sesiones
    
    def cerrar_todas_las_sesiones(self, usuario: str = None) -> int:
        """
        Cierra todas las sesiones activas o solo las de un usuario específico.
        Retorna el número de sesiones cerradas.
        """
        tokens_a_eliminar = []
        
        for token, info in self._sesiones_activas.items():
            if usuario is None or info.get('usuario') == usuario:
                tokens_a_eliminar.append(token)
        
        for token in tokens_a_eliminar:
            del self._sesiones_activas[token]
        
        return len(tokens_a_eliminar)


# ============================================================
# FUNCIONES DE ACCESO RÁPIDO (para uso en Streamlit)
# ============================================================

_auth_manager = None

def get_auth_manager() -> AuthManager:
    """
    Retorna la instancia única del AuthManager.
    """
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def login(usuario: str, password: str, ip: str = None) -> Dict:
    """
    Función rápida para login.
    """
    auth = get_auth_manager()
    return auth.login(usuario, password, ip)


def logout(token: str) -> bool:
    """
    Función rápida para logout.
    """
    auth = get_auth_manager()
    return auth.logout(token)


def verificar_sesion(token: str) -> bool:
    """
    Función rápida para verificar sesión.
    """
    auth = get_auth_manager()
    return auth.verificar_sesion(token)


def obtener_usuario_actual(token: str) -> Optional[Dict]:
    """
    Función rápida para obtener usuario actual.
    """
    auth = get_auth_manager()
    return auth.obtener_usuario_actual(token)


def es_super_admin(token: str) -> bool:
    """
    Función rápida para verificar SUPER_ADMIN.
    """
    auth = get_auth_manager()
    return auth.es_super_admin(token)


def es_admin(token: str) -> bool:
    """
    Función rápida para verificar ADMIN.
    """
    auth = get_auth_manager()
    return auth.es_admin(token)


def verificar_permiso(token: str, permiso: str) -> bool:
    """
    Función rápida para verificar permisos.
    """
    auth = get_auth_manager()
    return auth.verificar_permiso(token, permiso)


def limpiar_cache():
    """
    Limpia la instancia cacheada del AuthManager.
    """
    global _auth_manager
    _auth_manager = None