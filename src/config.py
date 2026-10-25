# src/config.py
"""
Configuración del sistema.
Carga variables de entorno y las pone a disposición de toda la aplicación.
AHORA CON CONFIGURACIÓN 100% DINÁMICA DESDE SUPABASE.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key

# ============================================================
# CONFIGURACIÓN DE ZONA HORARIA - PERÚ
# ============================================================
try:
    import pytz
    ZONA_HORARIA = pytz.timezone('America/Lima')
    os.environ['TZ'] = 'America/Lima'
except ImportError:
    print("⚠️ pytz no está instalado. Instala con: pip install pytz")
    ZONA_HORARIA = None

# ============================================================
# RUTAS DEL PROYECTO
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)


def _materializar_credenciales_google() -> None:
    """
    En la nube (Streamlit Community Cloud, GitHub Actions) no se sube el
    archivo credentials/service_account.json. Si el archivo no existe y hay
    un secreto GOOGLE_CREDENTIALS_JSON (el contenido completo del JSON), se
    escribe el archivo al arrancar. En local, con el archivo presente, no
    hace nada.
    """
    try:
        ruta = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/service_account.json")
        if ruta.exists():
            return
        contenido = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        if not contenido:
            try:
                import streamlit as _st
                if "gcp_service_account" in _st.secrets:
                    import json as _json
                    contenido = _json.dumps(dict(_st.secrets["gcp_service_account"]))
            except Exception:
                contenido = ""
        if not contenido:
            return
        import json as _json
        _json.loads(contenido)                 # valida que sea un JSON correcto
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        try:
            os.chmod(ruta, 0o600)
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        print(f"[config] No se pudo crear el archivo de credenciales de Google desde los secretos: {e}")


_materializar_credenciales_google()


class Config:
    """Clase central de configuración del sistema. 100% DINÁMICA."""
    
    # ============================================================
    # INFORMACIÓN DEL SISTEMA (FIJOS)
    # ============================================================
    APP_NAME = "SIREA · Sistema de Recepción de Reportes Epidemiológicos con Agentes"
    APP_VERSION = "3.3.0"
    APP_DESCRIPTION = "Sistema de envío y control de reportes para EsSalud"
    ORGANIZATION = "EsSalud - Seguro Social de Salud del Perú"
    
    # ============================================================
    # DIRECTORIOS DEL PROYECTO (FIJOS)
    # ============================================================
    BASE_DIR = BASE_DIR
    CREDENTIALS_DIR = BASE_DIR / "credentials"
    DATA_DIR = BASE_DIR / "data"
    STORAGE_DIR = BASE_DIR / "storage"
    TEMP_DIR = STORAGE_DIR / "temp"
    LOGS_DIR = STORAGE_DIR / "logs"
    BACKUP_DIR = STORAGE_DIR / "backups"
    
    # ============================================================
    # ZONA HORARIA (FIJA)
    # ============================================================
    ZONA_HORARIA = ZONA_HORARIA
    
    # ============================================================
    # GOOGLE DRIVE API (DESDE .env - FALLBACK)
    # ============================================================
    GOOGLE_CREDENTIALS_PATH = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        "credentials/service_account.json"
    )
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip().strip('"\'').strip()
    # Carpeta de Drive donde se guardan los envíos DUPLICADOS (mismo centro y
    # semana ya enviados). Debe estar compartida como EDITOR con la cuenta de
    # servicio. Si se deja vacía, se usa una subcarpeta "DUPLICADOS" dentro de
    # la carpeta principal.
    GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID = os.getenv("GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID", "").strip().strip('"\'').strip()
    # Carpeta (opcional) donde se guardan los envíos REEMPLAZADOS por otro posterior. Si está vacía se usa
    # una subcarpeta «REEMPLAZADOS» dentro de la carpeta principal.
    GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID = os.getenv("GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID", "").strip().strip('"\'').strip()
    # Carpeta compartida de Drive para los RESPALDOS (con permiso de Gestor de
    # contenido o Editor para la cuenta de servicio). Dentro se crea una
    # subcarpeta por respaldo, con la fecha y hora exactas. Se acepta
    # BACKUPS_ID o GOOGLE_DRIVE_FOLDER_BACKUPS_ID.
    GOOGLE_DRIVE_FOLDER_BACKUPS_ID = (
        os.getenv("BACKUPS_ID") or os.getenv("GOOGLE_DRIVE_FOLDER_BACKUPS_ID") or ""
    ).strip().strip('"\'').strip()
    GOOGLE_AUTH_TYPE = os.getenv("GOOGLE_AUTH_TYPE", "service_account")
    GOOGLE_DRIVE_SCOPES = [
        "https://www.googleapis.com/auth/drive.file"
    ]
    
    # ============================================================
    # CORREO SMTP (DESDE .env - FALLBACK)
    # ============================================================
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    EMAIL_REMITENTE = os.getenv("EMAIL_REMITENTE", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_NOMBRE_MOSTRAR = os.getenv(
        "EMAIL_NOMBRE_MOSTRAR",
        "Sistema de Reportes EsSalud"
    )
    # Direccion a la que van las respuestas de los usuarios (cabecera Reply-To).
    # Util cuando se envia con una cuenta distinta (p. ej. Gmail) pero se
    # quiere que contesten a la cuenta institucional. Opcional.
    EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "").strip()

    # Correo de consultas que se muestra en el inicio y en los correos.
    # Si no se define CONTACTO_EMAIL se usa el de respuesta o el remitente.
    CONTACTO_EMAIL = (
        os.getenv("CONTACTO_EMAIL", "").strip() or EMAIL_REPLY_TO or EMAIL_REMITENTE
    )
    
    # ============================================================
    # CUENTAS DEL PANEL
    # ============================================================
    # Único SUPER_ADMIN autorizado a editar los datos y restablecer las
    # contraseñas de los demás administradores (módulo "Cuentas del panel").
    SUPERADMIN_PRINCIPAL = (os.getenv("SUPERADMIN_PRINCIPAL", "oiis.winepi") or "oiis.winepi").strip().lower()

    # Horas durante las que una red puede cambiar su contraseña una vez que
    # un SUPER_ADMIN aprobó su solicitud.
    HORAS_VALIDEZ_CAMBIO_PASSWORD = int(os.getenv("HORAS_VALIDEZ_CAMBIO_PASSWORD", "24") or "24")

    # ============================================================
    # ASISTENTES DE IA (SIREA)
    # ============================================================
    # Proveedores en orden: el primero es el principal, el resto respaldo.
    # Los guardrails y la auditoría son los mismos para todos los proveedores.
    IA_PROVEEDOR_ORDEN = [
        p.strip().lower() for p in os.getenv("IA_PROVEEDOR_ORDEN", "gemini,groq").split(",") if p.strip()
    ] or ["gemini"]
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"\'')
    GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip().strip('"\'')
    # Modelos de Gemini que se prueban si el principal falla (404/429), separados por coma.
    GEMINI_MODELOS_RESPALDO = [
        m.strip().strip('"\'') for m in os.getenv("GEMINI_MODELOS_RESPALDO", "").split(",") if m.strip()
    ]
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip().strip('"\'')
    # Modelo de Groq (capa gratuita). Si el configurado no existe, SIREA elige
    # automáticamente el primero disponible de GROQ_MODELOS_RESPALDO.
    GROQ_MODEL = (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip().strip('"\'')
    GROQ_MODELOS_RESPALDO = [
        m.strip().strip('"\'') for m in os.getenv(
            "GROQ_MODELOS_RESPALDO",
            "llama-3.3-70b-versatile,openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.1-8b-instant").split(",") if m.strip()
    ]
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
    IA_TIMEOUT_SEGUNDOS = int(os.getenv("IA_TIMEOUT_SEGUNDOS", "30") or "30")
    IA_MAX_TOOL_CALLS = int(os.getenv("IA_MAX_TOOL_CALLS", "8") or "8")
    # Agente Operativo (SIREA 3.0): corre solo en días hábiles desde esta hora (Lima).
    AGENTE_PROGRAMADO = os.getenv("AGENTE_PROGRAMADO", "true").strip().lower() in ("1", "true", "si", "sí", "yes")
    AGENTE_HORA = int(os.getenv("AGENTE_HORA", "9") or "9")

    # ============================================================
    # SESIONES Y BLOQUEOS DE LOGIN (persistentes en Supabase)
    # ============================================================
    SESION_DURACION_HORAS = int(os.getenv("SESION_DURACION_HORAS", "8") or "8")
    SESION_INACTIVIDAD_MINUTOS = int(os.getenv("SESION_INACTIVIDAD_MINUTOS", "30") or "30")
    LOGIN_MAX_INTENTOS_USUARIO = int(os.getenv("LOGIN_MAX_INTENTOS_USUARIO", "5") or "5")
    LOGIN_MAX_INTENTOS_IP = int(os.getenv("LOGIN_MAX_INTENTOS_IP", "20") or "20")
    LOGIN_BLOQUEO_MINUTOS = int(os.getenv("LOGIN_BLOQUEO_MINUTOS", "15") or "15")

    # ============================================================
    # PROCESO PROGRAMADO (cierre de corte, recordatorios, respaldos)
    # ============================================================
    # Horas (hora de Lima) de los recordatorios para validar la semana propuesta.
    # Se envían el día hábil siguiente al corte; cada hora es un recordatorio.
    RECORDATORIOS_CIERRE_HORAS = [
        h.strip() for h in (os.getenv("RECORDATORIOS_CIERRE_HORAS", "08:00,12:00,16:00") or "").split(",")
        if h.strip()
    ]
    # Se respalda cada N cortes cerrados.
    RESPALDO_CADA_N_CORTES = max(1, int(os.getenv("RESPALDO_CADA_N_CORTES", "2") or "2"))

    # ------------------------------------------------------------
    # Descarga masiva, retiro del repositorio y auditoría
    # ------------------------------------------------------------
    # Tamaño máximo de cada ZIP masivo (MB). Si la selección pesa más, se divide en partes.
    DESCARGA_MASIVA_MAX_MB = max(20, int(os.getenv("DESCARGA_MASIVA_MAX_MB", "250") or "250"))
    # Correo institucional que recibe copia de TODOS los acuses de auditoría
    # (descargas, retiros, permisos). Es un registro independiente del sistema.
    AUDITORIA_COPIA_EMAIL = os.getenv("AUDITORIA_COPIA_EMAIL", "").strip()
    # true SOLO si la app está detrás de un proxy propio (Caddy/nginx) que pone el encabezado
    # X-Forwarded-For. Con false (por defecto) ese encabezado se ignora, porque cualquiera
    # podría enviarlo y falsear la IP anotada en la auditoría.
    PROXY_CONFIABLE = os.getenv("PROXY_CONFIABLE", "false").strip().lower() in ("1", "true", "si", "sí", "yes")
    # Alertas: un retiro de más de N archivos, o fuera del horario laboral (hora de Lima).
    ALERTA_RETIRO_MAX_ARCHIVOS = max(1, int(os.getenv("ALERTA_RETIRO_MAX_ARCHIVOS", "50") or "50"))
    HORARIO_LABORAL_INICIO = int(os.getenv("HORARIO_LABORAL_INICIO", "7") or "7")
    HORARIO_LABORAL_FIN = int(os.getenv("HORARIO_LABORAL_FIN", "20") or "20")

    # Correos de administradores (separados por coma)
    EMAIL_ADMINS_STR = os.getenv("EMAIL_ADMINS", "")
    EMAIL_ADMINS = [
        email.strip() 
        for email in EMAIL_ADMINS_STR.split(",") 
        if email.strip()
    ]
    
    # ============================================================
    # SUPABASE (DESDE .env)
    # ============================================================
    # Credenciales de la base de datos en la nube. Sin esto, ningún
    # módulo del sistema puede funcionar (ver db_manager.py).
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    # ============================================================
    # BASE DE DATOS (DESDE .env - FALLBACK)
    # ============================================================
    DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
    DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "essalud.db"))
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "essalud")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    # ============================================================
    # ARCHIVOS PERMITIDOS (DESDE .env - FALLBACK)
    # ============================================================
    EXTENSIONES_PERMITIDAS_STR = os.getenv(
        "EXTENSIONES_PERMITIDAS",
        ".xlsx,.csv,.xls,.dbf"
    )
    EXTENSIONES_PERMITIDAS = [
        ext.strip().lower() 
        for ext in EXTENSIONES_PERMITIDAS_STR.split(",") 
        if ext.strip()
    ]
    
    EXTENSIONES_BLOQUEADAS = [
        ".exe", ".bat", ".cmd", ".sh", ".js", ".vbs",
        ".ps1", ".msi", ".com", ".scr", ".pif",
        # Ejecutables, scripts y documentos con macros que un
        # administrador podría abrir al descargar un envío.
        ".dll", ".jar", ".php", ".php3", ".php5", ".py", ".html", ".htm",
        ".hta", ".lnk", ".docm", ".xlsm", ".reg", ".iso", ".jse", ".vbe",
        ".wsf", ".apk", ".cpl", ".svg"
    ]
    
    # Algunos sistemas legacy (ej. exportaciones de HIS/salud) generan
    # archivos con extensión puramente numérica (.127, .128, .200...),
    # donde el número no indica un formato sino un lote/página/secuencia
    # interno del sistema que los produjo. En vez de listar cada número
    # a mano, se acepta el PATRÓN (punto + solo dígitos) como una regla
    # aparte -- nunca se cruza con EXTENSIONES_BLOQUEADAS (ningún
    # ejecutable tiene extensión numérica) y se puede desactivar aquí
    # si en algún momento se deja de necesitar.
    PERMITIR_EXTENSIONES_NUMERICAS = os.getenv(
        "PERMITIR_EXTENSIONES_NUMERICAS", "true"
    ).strip().lower() == "true"
    
    # ============================================================
    # ADMIN POR DEFECTO (DESDE .env - FALLBACK)
    # ============================================================
    # NOTA: la autenticación real vive en la tabla `administradores`
    # de Supabase (ver auth.py). ADMIN_NOMBRE/ADMIN_EMAIL solo se usan
    # como valores de referencia (p. ej. destinatario de notificaciones),
    # no son credenciales de login.
    ADMIN_NOMBRE = os.getenv("ADMIN_NOMBRE", "Administrador")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@essalud.gob.pe")
    
    # ============================================================
    # LOGGING (DESDE .env - FALLBACK)
    # ============================================================
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # ============================================================
    # CONFIGURACIONES DINÁMICAS (DESDE BASE DE DATOS)
    # ============================================================
    
    @classmethod
    def _get_db_manager(cls):
        """
        Obtiene el gestor de base de datos.
        """
        try:
            from src.db_manager import get_db_manager
            return get_db_manager()
        except Exception as e:
            print(f"⚠️ Error al conectar con la base de datos: {e}")
            return None
    
    @classmethod
    def _obtener_config_bd(cls, clave: str, valor_por_defecto: Any = None) -> Any:
        """
        Obtiene una configuración desde la base de datos.
        Si no existe, retorna el valor por defecto.
        """
        db = cls._get_db_manager()
        if db:
            try:
                valor = db.obtener_configuracion(clave)
                if valor is not None:
                    return valor
            except Exception as e:
                print(f"⚠️ Error al obtener '{clave}' desde BD: {e}")
        return valor_por_defecto
    
    # ============================================================
    # MÉTODOS DINÁMICOS DE CONFIGURACIÓN
    # ============================================================
    
    @classmethod
    def get_semana_actual(cls) -> int:
        """
        Obtiene la semana activa desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('semana_activa')
        if valor:
            try:
                return int(valor)
            except:
                pass
        # Fallback a .env
        return int(os.getenv("SEMANA_ACTUAL", "32"))
    
    @classmethod
    def get_fecha_corte(cls) -> str:
        """
        Obtiene la fecha de corte desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('fecha_corte')
        if valor:
            return valor
        # Fallback a .env
        return os.getenv("FECHA_CORTE", "")

    @classmethod
    def get_fecha_corte_datetime(cls, anio: Optional[int] = None, semana: Optional[int] = None) -> datetime:
        """
        Obtiene la fecha de corte configurada por el administrador, ya
        parseada como datetime CON zona horaria (Perú) -- igual que
        obtener_fecha_actual(). Sin esto, restar o comparar el resultado
        contra obtener_fecha_actual() lanza:
        "TypeError: can't subtract offset-naive and offset-aware datetimes".

        IMPORTANTE: la fecha de corte es un valor UNICO que el administrador
        configura y que aplica a TODOS los envios, sin importar la semana o
        el año seleccionados. Los parametros anio/semana existen solo por
        compatibilidad con quienes ya llaman a esta funcion con esos
        argumentos (por ejemplo, un selector de semana en la interfaz) y
        no afectan el resultado.
        """
        fecha_corte_str = cls.get_fecha_corte()
        fecha_parseada = None

        if fecha_corte_str:
            try:
                fecha_parseada = datetime.strptime(fecha_corte_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    fecha_parseada = datetime.strptime(fecha_corte_str, '%Y-%m-%d').replace(
                        hour=23, minute=59, second=59
                    )
                except ValueError:
                    fecha_parseada = None

        if fecha_parseada is None:
            # Si no hay fecha configurada o no se pudo parsear, usar hoy
            # como ultimo recurso (no deberia pasar en un sistema bien configurado)
            fecha_parseada = datetime.now().replace(hour=23, minute=59, second=59)

        # datetime.strptime() SIEMPRE devuelve una fecha "naive" (sin zona
        # horaria). La localizamos a Perú para que sea comparable/restable
        # contra obtener_fecha_actual() en cualquier parte del sistema.
        if cls.ZONA_HORARIA and fecha_parseada.tzinfo is None:
            fecha_parseada = cls.ZONA_HORARIA.localize(fecha_parseada)

        return fecha_parseada

    @classmethod
    def get_anio_actual(cls) -> int:
        """
        Obtiene el año activo desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        # Primero intentar desde la tabla de años
        db = cls._get_db_manager()
        if db:
            try:
                anio_activo = db.obtener_anio_activo_epidemiologico()
                if anio_activo:
                    return anio_activo['anio']
            except:
                pass
        
        # Fallback a configuración
        valor = cls._obtener_config_bd('anio_actual')
        if valor:
            try:
                return int(valor)
            except:
                pass
        # Fallback a .env; si tampoco está seteado, usar el año calendario actual
        # en vez de un valor fijo que quedaría desactualizado con el tiempo
        return int(os.getenv("ANIO_ACTUAL", str(datetime.now().year)))
    
    @classmethod
    def get_tamano_maximo_zip_mb(cls) -> int:
        """
        Obtiene el tamaño máximo de ZIP desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('tamano_maximo_zip_mb')
        if valor:
            try:
                return int(valor)
            except:
                pass
        return int(os.getenv("TAMANO_MAXIMO_ZIP_MB", "80"))
    
    @classmethod
    def get_dias_tolerancia_atraso(cls) -> int:
        """
        Obtiene los días de tolerancia para atrasos desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('dias_tolerancia_atraso')
        if valor:
            try:
                return int(valor)
            except:
                pass
        return int(os.getenv("DIAS_TOLERANCIA_ATRASO", "2"))
    
    @classmethod
    def get_años_anteriores_permitidos(cls) -> int:
        """
        Obtiene la cantidad de años anteriores permitidos desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('años_anteriores_permitidos')
        if valor:
            try:
                return int(valor)
            except:
                pass
        return int(os.getenv("AÑOS_ANTERIORES_PERMITIDOS", "2"))
    
    @classmethod
    def get_permitir_anios_anteriores(cls) -> bool:
        """
        Obtiene si se permiten años anteriores desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('permitir_anios_anteriores')
        if valor:
            return valor.lower() == 'true'
        return os.getenv("PERMITIR_ANIOS_ANTERIORES", "true").lower() == "true"
    
    @classmethod
    def get_permitir_envios_adelantados(cls) -> bool:
        """
        Obtiene si se permiten envíos adelantados desde la base de datos.
        Si no existe, usa el valor del .env (fallback).
        """
        valor = cls._obtener_config_bd('permitir_envios_adelantados')
        if valor:
            return valor.lower() == 'true'
        return os.getenv("PERMITIR_ENVIOS_ADELANTADOS", "false").lower() == "true"
    
    # ============================================================
    # MÉTODOS AUXILIARES PARA FECHAS Y ATRASOS
    # ============================================================
    
    @classmethod
    def obtener_fecha_actual(cls) -> datetime:
        """
        Obtiene la fecha y hora actual en la zona horaria de Perú.
        """
        if cls.ZONA_HORARIA:
            return datetime.now(cls.ZONA_HORARIA)
        return datetime.now()
    
    @classmethod
    def obtener_fecha_actual_str(cls) -> str:
        """
        Obtiene la fecha y hora actual como string ISO en zona horaria Perú.
        """
        return cls.obtener_fecha_actual().isoformat()
    
    @classmethod
    def obtener_fecha_corte_dinamica(cls, semana: Optional[int] = None) -> datetime:
        """
        Obtiene la fecha de corte para una semana específica.
        Si no se especifica semana, usa la semana actual.
        La fecha de corte se calcula dinámicamente.
        """
        fecha_corte_str = cls.get_fecha_corte()
        if fecha_corte_str:
            try:
                return datetime.fromisoformat(fecha_corte_str)
            except:
                pass
        
        if semana is None:
            semana = cls.get_semana_actual()
        
        anio = cls.get_anio_actual()
        
        # Calcular el domingo de la semana epidemiológica
        primer_dia = datetime(anio, 1, 1)
        dias_desde_inicio = (semana - 1) * 7
        fecha_corte = primer_dia + timedelta(days=dias_desde_inicio)
        
        while fecha_corte.weekday() != 6:
            fecha_corte += timedelta(days=1)
        
        fecha_corte = fecha_corte.replace(hour=23, minute=59, second=59)
        
        if cls.ZONA_HORARIA:
            fecha_corte = fecha_corte.replace(tzinfo=cls.ZONA_HORARIA)
        
        return fecha_corte
    
    @classmethod
    def es_envio_atrasado(cls, fecha_envio: datetime, semana: Optional[int] = None) -> bool:
        """
        Determina si un envío está atrasado basado en la fecha de corte.
        """
        fecha_corte = cls.obtener_fecha_corte_dinamica(semana)
        dias_tolerancia = cls.get_dias_tolerancia_atraso()
        fecha_limite = fecha_corte + timedelta(days=dias_tolerancia)
        
        if fecha_envio.tzinfo is None and cls.ZONA_HORARIA:
            fecha_envio = fecha_envio.replace(tzinfo=cls.ZONA_HORARIA)
        
        return fecha_envio > fecha_limite
    
    @classmethod
    def calcular_dias_atraso(cls, fecha_envio: datetime, semana: Optional[int] = None) -> int:
        """
        Calcula cuántos días de atraso tiene un envío.
        Retorna 0 si no está atrasado.
        """
        fecha_corte = cls.obtener_fecha_corte_dinamica(semana)
        dias_tolerancia = cls.get_dias_tolerancia_atraso()
        fecha_limite = fecha_corte + timedelta(days=dias_tolerancia)
        
        if fecha_envio.tzinfo is None and cls.ZONA_HORARIA:
            fecha_envio = fecha_envio.replace(tzinfo=cls.ZONA_HORARIA)
        
        if fecha_envio <= fecha_limite:
            return 0
        
        dias_atraso = (fecha_envio - fecha_limite).days
        return max(0, dias_atraso)
    
    @classmethod
    def formatear_fecha(cls, fecha: datetime, formato: str = '%d/%m/%Y %H:%M:%S') -> str:
        """
        Formatea una fecha en el formato especificado.
        Si la fecha es naive, asume zona horaria Perú.
        """
        if fecha is None:
            return ''
        
        if fecha.tzinfo is None and cls.ZONA_HORARIA:
            fecha = fecha.replace(tzinfo=cls.ZONA_HORARIA)
        
        return fecha.strftime(formato)
    
    @classmethod
    def formatear_fecha_corte(cls) -> str:
        """
        Retorna la fecha de corte formateada para mostrar.
        """
        fecha = cls.obtener_fecha_corte_dinamica()
        return cls.formatear_fecha(fecha)
    
    @classmethod
    def obtener_semanas_disponibles(cls, rango: int = 5) -> List[int]:
        """
        Obtiene una lista de semanas disponibles para filtros.
        """
        semana_actual = cls.get_semana_actual()
        inicio = max(1, semana_actual - rango)
        fin = semana_actual + 1
        return list(range(inicio, fin + 1))
    
    # ============================================================
    # VALIDACIÓN DE CONFIGURACIÓN
    # ============================================================
    
    @classmethod
    def gemini_configurado(cls) -> bool:
        """Compatibilidad con src/agentes/cliente_ia.py (heredado de SIGRE)."""
        return bool(cls.GEMINI_API_KEY)

    @classmethod
    def tiene_ia(cls) -> bool:
        """True si hay al menos un proveedor de IA con clave configurada."""
        return bool(cls.GEMINI_API_KEY or cls.GROQ_API_KEY)

    @classmethod
    def proveedores_ia_disponibles(cls) -> List[str]:
        """Proveedores con clave, en el orden configurado."""
        out = []
        for p in cls.IA_PROVEEDOR_ORDEN:
            if p == "gemini" and cls.GEMINI_API_KEY:
                out.append(p)
            elif p == "groq" and cls.GROQ_API_KEY:
                out.append(p)
        return out

    @classmethod
    def validar(cls) -> List[str]:
        """
        Verifica que las variables críticas estén configuradas.
        """
        errores = []
        
        if not cls.SUPABASE_URL:
            errores.append("SUPABASE_URL no está configurado en .env")
        
        if not cls.SUPABASE_KEY:
            errores.append("SUPABASE_KEY no está configurado en .env")
        
        if not cls.GOOGLE_DRIVE_FOLDER_ID:
            errores.append("GOOGLE_DRIVE_FOLDER_ID no está configurado en .env")
        
        creds_path = cls.BASE_DIR / cls.GOOGLE_CREDENTIALS_PATH
        if not creds_path.exists():
            errores.append(f"Archivo de credenciales no encontrado: {creds_path}")
        
        if not cls.EMAIL_REMITENTE:
            errores.append("EMAIL_REMITENTE no está configurado en .env")
        
        if not cls.EMAIL_PASSWORD:
            errores.append("EMAIL_PASSWORD no está configurado en .env")
        
        if cls.SMTP_PORT not in [25, 465, 587, 2525]:
            errores.append(f"Puerto SMTP inválido: {cls.SMTP_PORT}")
        
        if not cls.EXTENSIONES_PERMITIDAS:
            errores.append("EXTENSIONES_PERMITIDAS está vacía")
        
        if not cls.ZONA_HORARIA:
            errores.append("pytz no está instalado. Instala con: pip install pytz")
        
        return errores
    
    @classmethod
    def validar_critico(cls) -> List[str]:
        """
        Verifica únicamente las variables sin las cuales el sistema
        no puede funcionar en absoluto (conexión a Supabase).

        A diferencia de validar() -que revisa toda la configuración
        y sirve como diagnóstico general-, esta lista está pensada
        para usarse al arrancar la app y decidir si detenerla.
        """
        errores = []

        if not cls.SUPABASE_URL:
            errores.append("SUPABASE_URL no está configurado en .env")

        if not cls.SUPABASE_KEY:
            errores.append("SUPABASE_KEY no está configurado en .env")

        return errores

    @classmethod
    def resumen(cls) -> Dict:
        """
        Retorna un resumen de la configuración del sistema.
        """
        return {
            "app_name": cls.APP_NAME,
            "app_version": cls.APP_VERSION,
            "base_dir": str(cls.BASE_DIR),
            "zona_horaria": str(cls.ZONA_HORARIA) if cls.ZONA_HORARIA else "No configurada",
            "google_drive_folder_id": (
                cls.GOOGLE_DRIVE_FOLDER_ID[:10] + "..." 
                if cls.GOOGLE_DRIVE_FOLDER_ID else ""
            ),
            "email_remitente": cls.EMAIL_REMITENTE,
            "email_admins": cls.EMAIL_ADMINS,
            "db_type": cls.DB_TYPE,
            "semana_actual": cls.get_semana_actual(),
            "anio_actual": cls.get_anio_actual(),
            "fecha_corte": cls.get_fecha_corte(),
            "fecha_corte_calculada": cls.formatear_fecha_corte(),
            "fecha_actual": cls.formatear_fecha(cls.obtener_fecha_actual()),
            "tamano_maximo_zip_mb": cls.get_tamano_maximo_zip_mb(),
            "dias_tolerancia_atraso": cls.get_dias_tolerancia_atraso(),
            "extensiones_permitidas": cls.EXTENSIONES_PERMITIDAS,
            "log_level": cls.LOG_LEVEL,
            "semanas_disponibles": cls.obtener_semanas_disponibles(),
            "años_anteriores_permitidos": cls.get_años_anteriores_permitidos(),
            "permitir_anios_anteriores": cls.get_permitir_anios_anteriores(),
            "permitir_envios_adelantados": cls.get_permitir_envios_adelantados(),
        }
    
    @classmethod
    def actualizar_variable(cls, clave: str, valor: str) -> bool:
        """
        Actualiza una variable en el archivo .env.
        """
        try:
            set_key(str(ENV_FILE), clave, valor)
            return True
        except Exception as e:
            print(f"Error al actualizar {clave}: {str(e)}")
            return False
    
    @classmethod
    def recargar(cls):
        """
        Recarga las variables de entorno.
        """
        load_dotenv(ENV_FILE, override=True)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def crear_directorios():
    """Crea los directorios necesarios para el sistema."""
    directorios = [
        Config.CREDENTIALS_DIR,
        Config.DATA_DIR,
        Config.STORAGE_DIR,
        Config.TEMP_DIR,
        Config.LOGS_DIR,
        Config.BACKUP_DIR,
    ]
    
    for directorio in directorios:
        try:
            directorio.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error al crear directorio {directorio}: {str(e)}")


def validar_configuracion() -> List[str]:
    """Valida la configuración del sistema."""
    return Config.validar()


def obtener_resumen_configuracion() -> Dict:
    """Obtiene un resumen de la configuración."""
    return Config.resumen()


def obtener_fecha_actual() -> datetime:
    """Obtiene la fecha y hora actual en zona horaria Perú."""
    return Config.obtener_fecha_actual()


def formatear_fecha(fecha: datetime, formato: str = '%d/%m/%Y %H:%M:%S') -> str:
    """Formatea una fecha en zona horaria Perú."""
    return Config.formatear_fecha(fecha, formato)


def crear_archivo_env_ejemplo():
    """Crea un archivo .env.example con las variables necesarias."""
    contenido = """# ============================================================
# CONFIGURACIÓN DEL SISTEMA - ESSALUD
# ============================================================

# Google Drive API
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json
GOOGLE_DRIVE_FOLDER_ID=
# Carpeta de Drive para los envíos duplicados (compartida como EDITOR con la cuenta de servicio).
# Si se deja vacía se usa una subcarpeta "DUPLICADOS" dentro de la carpeta principal.
GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID=

# Correo SMTP
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USE_SSL=false
EMAIL_REMITENTE=
EMAIL_PASSWORD=
EMAIL_NOMBRE_MOSTRAR=Sistema de Reportes EsSalud
EMAIL_REPLY_TO=
EMAIL_ADMINS=

# Único SUPER_ADMIN que puede editar datos y contraseñas de otras cuentas del panel
SUPERADMIN_PRINCIPAL=oiis.winepi
# Horas de validez del permiso para que una red cambie su contraseña tras ser aprobada
HORAS_VALIDEZ_CAMBIO_PASSWORD=24

# Base de Datos
DB_TYPE=supabase
DB_PATH=data/essalud.db
DB_HOST=localhost
DB_PORT=3306
DB_NAME=essalud
DB_USER=
DB_PASSWORD=

# Archivos Permitidos
EXTENSIONES_PERMITIDAS=.xlsx,.csv,.xls,.dbf

# Administrador por Defecto (solo referencia, NO es credencial de login;
# el login real se gestiona en la tabla `administradores` de Supabase)
ADMIN_NOMBRE=Administrador
ADMIN_EMAIL=admin@essalud.gob.pe

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# ============================================================
# NOTA: SEMANA_ACTUAL, FECHA_CORTE y otras configuraciones
# DINÁMICAS se leen desde la base de datos (Supabase).
# Los valores en .env son solo FALLBACK.
# ============================================================
"""
    
    ruta = BASE_DIR / ".env.example"
    try:
        ruta.write_text(contenido, encoding='utf-8')
        return True, f"Archivo .env.example creado en: {ruta}"
    except Exception as e:
        return False, f"Error al crear .env.example: {str(e)}"


# ============================================================
# INICIALIZACIÓN
# ============================================================

# Crear directorios al importar
crear_directorios()

# Crear .env.example si no existe
if not (BASE_DIR / ".env.example").exists():
    crear_archivo_env_ejemplo()