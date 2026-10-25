# utils/helpers.py
"""
Funciones auxiliares para el sistema.
Versión robusta con manejo de errores mejorado y soporte de zona horaria Perú.
AHORA CON CONFIGURACIÓN DINÁMICA DESDE BASE DE DATOS.
"""

import os
import re
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Intentar importar zona horaria desde config
try:
    from src.config import Config
    ZONA_HORARIA = Config.ZONA_HORARIA
except (ImportError, AttributeError):
    # Fallback si no se puede importar
    try:
        import pytz
        ZONA_HORARIA = pytz.timezone('America/Lima')
        os.environ['TZ'] = 'America/Lima'
    except ImportError:
        ZONA_HORARIA = None
        logger.warning("pytz no está instalado. La zona horaria puede ser incorrecta.")


# ============================================================
# CONSTANTES
# ============================================================
MAX_NOMBRE_LENGTH = 100
FECHA_MINIMA = date(2000, 1, 1)
FECHA_MAXIMA = date(2099, 12, 31)
TAMANO_MAXIMO_MB = 100  # Tamaño máximo predeterminado en MB


# ============================================================
# FUNCIONES DE ZONA HORARIA
# ============================================================

def obtener_fecha_actual() -> datetime:
    """
    Obtiene la fecha y hora actual en zona horaria Perú.
    """
    try:
        if ZONA_HORARIA:
            return datetime.now(ZONA_HORARIA)
        else:
            return datetime.now()
    except Exception as e:
        logger.error(f"Error al obtener fecha actual: {e}")
        return datetime.now()


def obtener_fecha_actual_str(formato: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Obtiene la fecha y hora actual como string en zona horaria Perú.
    """
    try:
        fecha = obtener_fecha_actual()
        return fecha.strftime(formato)
    except Exception as e:
        logger.error(f"Error al obtener fecha actual string: {e}")
        return datetime.now().strftime(formato)


def convertir_a_zona_horaria(fecha: Union[datetime, date, str]) -> datetime:
    """
    Convierte una fecha a la zona horaria de Perú.
    """
    try:
        if fecha is None:
            return obtener_fecha_actual()
        
        if isinstance(fecha, str):
            fecha = parsear_fecha(fecha)
            if not fecha:
                return obtener_fecha_actual()
        
        if isinstance(fecha, date) and not isinstance(fecha, datetime):
            fecha = datetime.combine(fecha, datetime.min.time())
        
        if fecha.tzinfo is None and ZONA_HORARIA:
            fecha = fecha.replace(tzinfo=ZONA_HORARIA)
        
        if ZONA_HORARIA and fecha.tzinfo:
            fecha = fecha.astimezone(ZONA_HORARIA)
        
        return fecha
    except Exception as e:
        logger.error(f"Error al convertir a zona horaria: {e}")
        return obtener_fecha_actual()


def es_fecha_peru(fecha: Union[datetime, date, str]) -> bool:
    """
    Verifica si una fecha está en zona horaria Perú.
    """
    try:
        if isinstance(fecha, str):
            fecha = parsear_fecha(fecha)
            if not fecha:
                return False
        
        if isinstance(fecha, date) and not isinstance(fecha, datetime):
            return True
        
        if not isinstance(fecha, datetime):
            return False
        
        if fecha.tzinfo is None:
            return False
        
        tz_str = str(fecha.tzinfo)
        return 'Lima' in tz_str or 'America' in tz_str
    except Exception as e:
        logger.error(f"Error al verificar zona horaria: {e}")
        return False


# ============================================================
# LIMPIEZA Y SANITIZACION
# ============================================================

def sanitizar_nombre(nombre: str) -> str:
    """
    Limpia un nombre de archivo o carpeta.
    """
    try:
        if not nombre or not isinstance(nombre, str):
            return "sin_nombre"
        
        nombre = nombre.replace(" ", "_")
        nombre = re.sub(r'[^a-zA-Z0-9_\-.]', '', nombre)
        nombre = re.sub(r'[_\-.]{2,}', '_', nombre)
        if len(nombre) > MAX_NOMBRE_LENGTH:
            nombre = nombre[:MAX_NOMBRE_LENGTH]
        nombre = ''.join(c for c in nombre if c.isprintable())
        
        return nombre or "sin_nombre"
    except Exception as e:
        logger.error(f"Error al sanitizar nombre: {e}")
        return "sin_nombre"


def sanitizar_codigo(codigo: str) -> str:
    """
    Limpia un código para usarlo en identificadores.
    """
    try:
        if not codigo or not isinstance(codigo, str):
            return "sin_codigo"
        
        codigo = codigo.strip()
        if not codigo:
            return "sin_codigo"
        
        codigo = re.sub(r'[^a-zA-Z0-9]', '', codigo)
        return codigo or "sin_codigo"
    except Exception as e:
        logger.error(f"Error al sanitizar código: {e}")
        return "sin_codigo"


def sanitizar_texto(texto: str, max_length: int = 500) -> str:
    """
    Sanitiza texto para mostrar en interfaces.
    """
    try:
        if not texto or not isinstance(texto, str):
            return ""
        
        texto = ''.join(c for c in texto if c.isprintable() or c in ['\n', '\t'])
        texto = ' '.join(texto.split())
        if len(texto) > max_length:
            texto = texto[:max_length]
        
        return texto
    except Exception as e:
        logger.error(f"Error al sanitizar texto: {e}")
        return ""


# ============================================================
# GENERACION DE NOMBRES Y CODIGOS
# ============================================================

def generar_nombre_archivo(red: str, semana: int, centro: str) -> str:
    """
    Genera un nombre único para el archivo ZIP.
    """
    try:
        fecha_actual = obtener_fecha_actual()
        timestamp = fecha_actual.strftime("%Y%m%d_%H%M%S")
        red_limpia = sanitizar_nombre(red)
        centro_limpio = sanitizar_nombre(centro) if centro else "general"
        
        semana_valida = max(1, min(53, int(semana) if semana else 1))
        
        return f"{timestamp}_{red_limpia}_sem{str(semana_valida).zfill(2)}_{centro_limpio}.zip"
    except Exception as e:
        logger.error(f"Error al generar nombre de archivo: {e}")
        fecha_actual = obtener_fecha_actual()
        return f"{fecha_actual.strftime('%Y%m%d_%H%M%S')}_error_default.zip"


def generar_nombre_archivo_con_version(
    red: str,
    semana: int,
    centro: str,
    version: int = 1
) -> str:
    """
    Genera un nombre de archivo con versión.
    """
    try:
        fecha_actual = obtener_fecha_actual()
        timestamp = fecha_actual.strftime("%Y%m%d_%H%M%S")
        red_limpia = sanitizar_nombre(red)
        centro_limpio = sanitizar_nombre(centro) if centro else "general"
        
        semana_valida = max(1, min(53, int(semana) if semana else 1))
        version_valida = max(1, int(version) if version else 1)
        
        return f"{timestamp}_{red_limpia}_sem{str(semana_valida).zfill(2)}_{centro_limpio}_v{version_valida}.zip"
    except Exception as e:
        logger.error(f"Error al generar nombre con versión: {e}")
        fecha_actual = obtener_fecha_actual()
        return f"{fecha_actual.strftime('%Y%m%d_%H%M%S')}_error_v1.zip"


def obtener_codigo_seguimiento(id_envio: int) -> str:
    """
    Genera un código de seguimiento para un envío.
    """
    try:
        fecha_actual = obtener_fecha_actual()
        fecha_str = fecha_actual.strftime("%Y%m%d")
        id_valido = max(0, int(id_envio) if id_envio else 0)
        return f"ENV-{fecha_str}-{str(id_valido).zfill(4)}"
    except Exception as e:
        logger.error(f"Error al generar código de seguimiento: {e}")
        fecha_actual = obtener_fecha_actual()
        return f"ENV-{fecha_actual.strftime('%Y%m%d')}-0000"


def obtener_id_desde_codigo(codigo: str) -> Optional[int]:
    """
    Extrae el ID numérico de un código de seguimiento.
    """
    try:
        if not codigo or not isinstance(codigo, str):
            return None
        
        patron = r'ENV-\d{8}-(\d{4})'
        match = re.search(patron, codigo)
        if match:
            return int(match.group(1))
        return None
    except Exception as e:
        logger.error(f"Error al extraer ID de código: {e}")
        return None


def generar_codigo_unico(prefix: str = "", length: int = 8) -> str:
    """
    Genera un código único aleatorio.
    """
    import random
    import string
    
    try:
        fecha_actual = obtener_fecha_actual()
        timestamp = fecha_actual.strftime("%Y%m%d%H%M%S")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        codigo = f"{prefix}{timestamp}{random_part}" if prefix else f"{timestamp}{random_part}"
        return codigo[:20]
    except Exception as e:
        logger.error(f"Error al generar código único: {e}")
        fecha_actual = obtener_fecha_actual()
        return fecha_actual.strftime("%Y%m%d%H%M%S")


# ============================================================
# FECHAS DINÁMICAS (DESDE CONFIG)
# ============================================================

def obtener_semana_actual() -> int:
    """
    Obtiene la semana activa desde la configuración dinámica.
    """
    try:
        from src.config import Config
        return Config.get_semana_actual()
    except Exception as e:
        logger.error(f"Error al obtener semana actual: {e}")
        return 1


def obtener_ano_actual() -> int:
    """
    Obtiene el año actual desde la configuración dinámica.
    """
    try:
        from src.config import Config
        return Config.get_anio_actual()
    except Exception as e:
        logger.error(f"Error al obtener año actual: {e}")
        return datetime.now().year


def obtener_fecha_corte_dinamica(semana: Optional[int] = None) -> datetime:
    """
    Obtiene la fecha de corte desde la configuración dinámica.
    """
    try:
        from src.config import Config
        return Config.obtener_fecha_corte_dinamica(semana)
    except Exception as e:
        logger.error(f"Error al obtener fecha de corte: {e}")
        return obtener_fecha_actual()


def obtener_dias_tolerancia_atraso() -> int:
    """
    Obtiene los días de tolerancia desde la configuración dinámica.
    """
    try:
        from src.config import Config
        return Config.get_dias_tolerancia_atraso()
    except Exception as e:
        logger.error(f"Error al obtener días de tolerancia: {e}")
        return 2


# ============================================================
# FECHAS (CON SOPORTE DINÁMICO)
# ============================================================

def formatear_fecha(
    fecha: Optional[Union[datetime, date, str]] = None,
    formato: str = "%d/%m/%Y %H:%M"
) -> str:
    """
    Formatea una fecha para mostrar al usuario.
    Usa zona horaria Perú.
    """
    try:
        if fecha is None:
            fecha = obtener_fecha_actual()
        elif isinstance(fecha, str):
            fecha = parsear_fecha(fecha)
            if not fecha:
                fecha = obtener_fecha_actual()
        elif isinstance(fecha, date) and not isinstance(fecha, datetime):
            fecha = datetime.combine(fecha, datetime.min.time())
            if ZONA_HORARIA:
                fecha = fecha.replace(tzinfo=ZONA_HORARIA)
        
        if fecha.tzinfo is None and ZONA_HORARIA:
            fecha = fecha.replace(tzinfo=ZONA_HORARIA)
        
        return fecha.strftime(formato)
    except Exception as e:
        logger.error(f"Error al formatear fecha: {e}")
        return obtener_fecha_actual().strftime(formato)


def formatear_fecha_corta(fecha: Optional[Union[datetime, date, str]] = None) -> str:
    """Formato corto: dd/mm/yyyy"""
    return formatear_fecha(fecha, "%d/%m/%Y")


def formatear_fecha_hora(fecha: Optional[Union[datetime, date, str]] = None) -> str:
    """Formato con hora: dd/mm/yyyy HH:MM:SS"""
    return formatear_fecha(fecha, "%d/%m/%Y %H:%M:%S")


def formatear_fecha_iso(fecha: Optional[Union[datetime, date, str]] = None) -> str:
    """Formato ISO: YYYY-MM-DD HH:MM:SS"""
    return formatear_fecha(fecha, "%Y-%m-%d %H:%M:%S")


def validar_semana(semana: int) -> bool:
    """Valida que el número de semana sea válido (1-53)."""
    try:
        return 1 <= int(semana) <= 53
    except (ValueError, TypeError):
        return False


def validar_ano(ano: int) -> bool:
    """Valida que el año sea razonable (2000-2099)."""
    try:
        return 2000 <= int(ano) <= 2099
    except (ValueError, TypeError):
        return False


def fecha_es_pasada(fecha: Union[str, datetime, date]) -> bool:
    """
    Verifica si una fecha ya pasó.
    """
    try:
        if isinstance(fecha, str):
            fecha_dt = parsear_fecha(fecha)
            if not fecha_dt:
                return False
        elif isinstance(fecha, date) and not isinstance(fecha, datetime):
            fecha_dt = datetime.combine(fecha, datetime.min.time())
            if ZONA_HORARIA:
                fecha_dt = fecha_dt.replace(tzinfo=ZONA_HORARIA)
        else:
            fecha_dt = fecha
        
        fecha_actual = obtener_fecha_actual()
        
        if fecha_dt.tzinfo is None and ZONA_HORARIA:
            fecha_dt = fecha_dt.replace(tzinfo=ZONA_HORARIA)
        
        return fecha_dt < fecha_actual
    except Exception as e:
        logger.error(f"Error al verificar si fecha es pasada: {e}")
        return False


def dias_restantes(fecha_corte: Union[str, datetime, date]) -> int:
    """
    Calcula los días restantes hasta una fecha de corte.
    """
    try:
        if isinstance(fecha_corte, str):
            fecha_dt = parsear_fecha(fecha_corte)
            if not fecha_dt:
                return 0
        elif isinstance(fecha_corte, date) and not isinstance(fecha_corte, datetime):
            fecha_dt = datetime.combine(fecha_corte, datetime.min.time())
            if ZONA_HORARIA:
                fecha_dt = fecha_dt.replace(tzinfo=ZONA_HORARIA)
        else:
            fecha_dt = fecha_corte
        
        fecha_actual = obtener_fecha_actual()
        
        if fecha_dt.tzinfo is None and ZONA_HORARIA:
            fecha_dt = fecha_dt.replace(tzinfo=ZONA_HORARIA)
        
        diff = fecha_dt - fecha_actual
        return max(0, diff.days)
    except Exception as e:
        logger.error(f"Error al calcular días restantes: {e}")
        return 0


def dias_de_atraso(fecha_envio: datetime, semana: Optional[int] = None) -> int:
    """
    Calcula los días de atraso de un envío.
    Usa la configuración dinámica de fecha de corte y tolerancia.
    """
    try:
        from src.config import Config
        return Config.calcular_dias_atraso(fecha_envio, semana)
    except Exception as e:
        logger.error(f"Error al calcular días de atraso: {e}")
        return 0


def es_envio_atrasado(fecha_envio: datetime, semana: Optional[int] = None) -> bool:
    """
    Determina si un envío está atrasado.
    Usa la configuración dinámica.
    """
    try:
        from src.config import Config
        return Config.es_envio_atrasado(fecha_envio, semana)
    except Exception as e:
        logger.error(f"Error al verificar si envío está atrasado: {e}")
        return False


def parsear_fecha(fecha_str: str) -> Optional[datetime]:
    """
    Parsear una fecha desde string con múltiples formatos.
    """
    if not fecha_str or not isinstance(fecha_str, str):
        return None
    
    formatos = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f"
    ]
    
    for fmt in formatos:
        try:
            fecha = datetime.strptime(fecha_str.strip(), fmt)
            if fecha.tzinfo is None and ZONA_HORARIA:
                fecha = fecha.replace(tzinfo=ZONA_HORARIA)
            return fecha
        except ValueError:
            continue
    
    return None


# ============================================================
# CALCULOS Y ESTADISTICAS
# ============================================================

def calcular_porcentaje(parte: Union[int, float], total: Union[int, float]) -> float:
    """
    Calcula el porcentaje de parte sobre total.
    """
    try:
        parte = float(parte) if parte is not None else 0
        total = float(total) if total is not None else 0
        
        if total == 0:
            return 0.0
        
        porcentaje = (parte / total) * 100
        return round(max(0, min(100, porcentaje)), 2)
    except (ValueError, TypeError) as e:
        logger.error(f"Error al calcular porcentaje: {e}")
        return 0.0


def obtener_estado_semaforo(porcentaje: float) -> Dict[str, str]:
    """
    Determina el estado semáforo según el porcentaje.
    """
    try:
        porcentaje = float(porcentaje) if porcentaje is not None else 0
        porcentaje = max(0, min(100, porcentaje))
        
        if porcentaje >= 90:
            return {"estado": "ok", "color": "verde", "texto": "OK"}
        elif porcentaje >= 50:
            return {"estado": "parcial", "color": "amarillo", "texto": "Parcial"}
        else:
            return {"estado": "atrasado", "color": "rojo", "texto": "Atrasado"}
    except Exception as e:
        logger.error(f"Error al obtener estado semáforo: {e}")
        return {"estado": "error", "color": "gris", "texto": "Error"}


def obtener_color_semaforo(estado: str) -> str:
    """
    Obtiene el color correspondiente a un estado.
    """
    try:
        estado = str(estado).lower() if estado else ""
        colores = {
            'ok': 'verde',
            'exitoso': 'verde',
            'completado': 'verde',
            'parcial': 'amarillo',
            'en_progreso': 'amarillo',
            'pendiente': 'amarillo',
            'atrasado': 'rojo',
            'critico': 'rojo',
            'error': 'rojo',
            'observado': 'naranja',
            'revisado': 'naranja',
            'inactivo': 'gris'
        }
        return colores.get(estado, 'gris')
    except Exception as e:
        logger.error(f"Error al obtener color semáforo: {e}")
        return 'gris'


# ============================================================
# TAMAÑOS Y UNIDADES
# ============================================================

def tamaño_legible(bytes: Union[int, float, str]) -> str:
    """Convierte bytes a una representación legible."""
    try:
        bytes_val = float(bytes) if bytes is not None else 0
        bytes_val = max(0, bytes_val)
        
        if bytes_val < 1024:
            return f"{int(bytes_val)} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{bytes_val / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"
    except (ValueError, TypeError) as e:
        logger.error(f"Error al convertir tamaño a legible: {e}")
        return "0 B"


def tamaño_en_mb(bytes: Union[int, float, str]) -> float:
    """Convierte bytes a megabytes."""
    try:
        bytes_val = float(bytes) if bytes is not None else 0
        bytes_val = max(0, bytes_val)
        return round(bytes_val / (1024 * 1024), 2)
    except (ValueError, TypeError) as e:
        logger.error(f"Error al convertir tamaño a MB: {e}")
        return 0.0


def tamaño_maximo_valido(tamaño_mb: Union[int, float], maximo_mb: Union[int, float]) -> bool:
    """Verifica si un tamaño en MB es válido."""
    try:
        tamaño_mb = float(tamaño_mb) if tamaño_mb is not None else 0
        maximo_mb = float(maximo_mb) if maximo_mb is not None else TAMANO_MAXIMO_MB
        return 0 <= tamaño_mb <= maximo_mb
    except (ValueError, TypeError) as e:
        logger.error(f"Error al validar tamaño máximo: {e}")
        return False


# ============================================================
# VALIDACIONES
# ============================================================

def validar_email(email: str) -> bool:
    """Valida si un correo electrónico tiene formato correcto."""
    try:
        if not email or not isinstance(email, str):
            return False
        
        email = email.strip()
        if not email:
            return False
        
        patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(patron, email))
    except Exception as e:
        logger.error(f"Error al validar email: {e}")
        return False


def validar_telefono(telefono: str) -> bool:
    """Valida un número de teléfono peruano."""
    try:
        if not telefono or not isinstance(telefono, str):
            return False
        
        telefono = re.sub(r'[\s\-()]', '', telefono)
        patron = r'^(9\d{8}|0?[1-9]\d{6,7})$'
        return bool(re.match(patron, telefono))
    except Exception as e:
        logger.error(f"Error al validar teléfono: {e}")
        return False


def validar_dni(dni: str) -> bool:
    """Valida un DNI peruano (8 dígitos)."""
    try:
        if not dni or not isinstance(dni, str):
            return False
        
        dni = dni.strip()
        return bool(re.match(r'^\d{8}$', dni))
    except Exception as e:
        logger.error(f"Error al validar DNI: {e}")
        return False


def validar_ruc(ruc: str) -> bool:
    """Valida un RUC peruano (11 dígitos)."""
    try:
        if not ruc or not isinstance(ruc, str):
            return False
        
        ruc = ruc.strip()
        return bool(re.match(r'^\d{11}$', ruc))
    except Exception as e:
        logger.error(f"Error al validar RUC: {e}")
        return False


def validar_codigo_postal(codigo: str) -> bool:
    """Valida un código postal (5 dígitos)."""
    try:
        if not codigo or not isinstance(codigo, str):
            return False
        
        codigo = codigo.strip()
        return bool(re.match(r'^\d{5}$', codigo))
    except Exception as e:
        logger.error(f"Error al validar código postal: {e}")
        return False


# ============================================================
# ARCHIVOS
# ============================================================

def extension_archivo(nombre: str) -> str:
    """Obtiene la extensión de un archivo."""
    try:
        if not nombre or not isinstance(nombre, str):
            return ""
        
        extension = os.path.splitext(nombre)[1]
        return extension.lower() if extension else ""
    except Exception as e:
        logger.error(f"Error al obtener extensión de archivo: {e}")
        return ""


def nombre_sin_extension(nombre: str) -> str:
    """Obtiene el nombre de un archivo sin extensión."""
    try:
        if not nombre or not isinstance(nombre, str):
            return ""
        
        return os.path.splitext(nombre)[0]
    except Exception as e:
        logger.error(f"Error al obtener nombre sin extensión: {e}")
        return ""


def extensiones_permitidas_texto(extensiones: List[str]) -> str:
    """Formatea una lista de extensiones para mostrar."""
    try:
        if not extensiones:
            return "Sin extensiones"
        
        if not isinstance(extensiones, list):
            extensiones = [str(extensiones)]
        
        extensiones_limpias = [ext.lower() for ext in extensiones if ext]
        return ", ".join(extensiones_limpias) if extensiones_limpias else "Sin extensiones"
    except Exception as e:
        logger.error(f"Error al formatear extensiones: {e}")
        return "Sin extensiones"


def es_extension_permitida(nombre: str, extensiones_permitidas: List[str]) -> bool:
    """
    Verifica si un archivo tiene una extensión permitida.
    """
    try:
        if not nombre:
            return False
        
        ext = extension_archivo(nombre)
        return ext in [e.lower() for e in extensiones_permitidas] if extensiones_permitidas else False
    except Exception as e:
        logger.error(f"Error al verificar extensión permitida: {e}")
        return False


# ============================================================
# DICCIONARIOS Y LISTAS
# ============================================================

def dict_a_json(data: Any, indent: int = 2) -> str:
    """Convierte un diccionario a JSON."""
    try:
        return json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    except Exception as e:
        logger.error(f"Error al convertir dict a JSON: {e}")
        return "{}"


def json_a_dict(json_str: str) -> Dict:
    """Convierte un JSON a diccionario."""
    try:
        if not json_str or not isinstance(json_str, str):
            return {}
        
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Error al convertir JSON a dict: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error inesperado al convertir JSON: {e}")
        return {}


def listar_centros_seleccionados(centros: List[str]) -> str:
    """Formatea una lista de centros para mostrar."""
    try:
        if not centros:
            return "Ninguno"
        
        if not isinstance(centros, list):
            centros = [str(centros)]
        
        centros = [c for c in centros if c]
        if not centros:
            return "Ninguno"
        
        if len(centros) == 1:
            return centros[0]
        elif len(centros) == 2:
            return f"{centros[0]} y {centros[1]}"
        else:
            return f"{', '.join(centros[:-1])} y {centros[-1]}"
    except Exception as e:
        logger.error(f"Error al listar centros: {e}")
        return "Error al listar"


# ============================================================
# STRINGS
# ============================================================

def truncar_texto(texto: str, longitud: int = 50) -> str:
    """Trunca un texto a una longitud máxima."""
    try:
        if not texto or not isinstance(texto, str):
            return ""
        
        if len(texto) <= longitud:
            return texto
        
        return texto[:longitud] + "..."
    except Exception as e:
        logger.error(f"Error al truncar texto: {e}")
        return texto[:50] if texto else ""


def capitalizar_palabras(texto: str) -> str:
    """Capitaliza cada palabra de un texto."""
    try:
        if not texto or not isinstance(texto, str):
            return ""
        
        texto = ' '.join(texto.split())
        return " ".join(palabra.capitalize() for palabra in texto.split())
    except Exception as e:
        logger.error(f"Error al capitalizar palabras: {e}")
        return texto if texto else ""


def limpiar_espacios(texto: str) -> str:
    """Elimina espacios extra de un texto."""
    try:
        if not texto or not isinstance(texto, str):
            return ""
        
        return " ".join(texto.split())
    except Exception as e:
        logger.error(f"Error al limpiar espacios: {e}")
        return texto if texto else ""


def normalizar_texto(texto: str) -> str:
    """
    Normaliza un texto eliminando acentos y caracteres especiales.
    """
    try:
        if not texto or not isinstance(texto, str):
            return ""
        
        texto = re.sub(r'[áàäâ]', 'a', texto)
        texto = re.sub(r'[éèëê]', 'e', texto)
        texto = re.sub(r'[íìïî]', 'i', texto)
        texto = re.sub(r'[óòöô]', 'o', texto)
        texto = re.sub(r'[úùüû]', 'u', texto)
        texto = re.sub(r'[^a-zA-Z0-9\s\-_]', '', texto)
        
        return ' '.join(texto.split())
    except Exception as e:
        logger.error(f"Error al normalizar texto: {e}")
        return texto if texto else ""


# ============================================================
# FECHAS ESPECIALES (CON SOPORTE DINÁMICO)
# ============================================================

# NOTA: existía aquí una obtener_fecha_corte_semana() que calculaba la
# fecha de corte a partir de la semana. Se eliminó porque (a) no se
# usaba en ningún lado del proyecto y (b) el cálculo no correspondía
# con el comportamiento real del sistema: la fecha de corte es un
# valor único que el administrador configura (ver Config.get_fecha_corte_datetime()).

def obtener_rango_semana(semana: int, año: int = None) -> Dict[str, str]:
    """
    Obtiene el rango de fechas (lunes a domingo) de una semana.
    """
    try:
        semana = int(semana) if semana else 1
        semana = max(1, min(53, semana))
        
        if año is None:
            año = obtener_ano_actual()
        else:
            año = int(año)
            año = max(2000, min(2099, año))
        
        primer_dia = date(año, 1, 1)
        dias_a_semana = (semana - 1) * 7
        fecha = primer_dia + timedelta(days=dias_a_semana)
        
        while fecha.weekday() != 0:
            fecha = fecha + timedelta(days=1)
        
        lunes = fecha
        domingo = fecha + timedelta(days=6)
        
        return {
            'inicio': lunes.strftime("%Y-%m-%d"),
            'fin': domingo.strftime("%Y-%m-%d"),
            'lunes': lunes.strftime("%d/%m/%Y"),
            'domingo': domingo.strftime("%d/%m/%Y"),
            'semana': str(semana),
            'año': str(año)
        }
    except Exception as e:
        logger.error(f"Error al obtener rango de semana: {e}")
        fecha_actual = obtener_fecha_actual()
        return {
            'inicio': fecha_actual.strftime("%Y-%m-%d"),
            'fin': fecha_actual.strftime("%Y-%m-%d"),
            'lunes': fecha_actual.strftime("%d/%m/%Y"),
            'domingo': fecha_actual.strftime("%d/%m/%Y"),
            'semana': str(obtener_semana_actual()),
            'año': str(obtener_ano_actual())
        }


def obtener_semana_desde_fecha(fecha: Union[str, datetime, date]) -> int:
    """
    Obtiene el número de semana de una fecha dada.
    """
    try:
        if isinstance(fecha, str):
            fecha_dt = parsear_fecha(fecha)
            if not fecha_dt:
                return obtener_semana_actual()
        elif isinstance(fecha, date) and not isinstance(fecha, datetime):
            fecha_dt = datetime.combine(fecha, datetime.min.time())
            if ZONA_HORARIA:
                fecha_dt = fecha_dt.replace(tzinfo=ZONA_HORARIA)
        else:
            fecha_dt = fecha
        
        if fecha_dt.tzinfo is None and ZONA_HORARIA:
            fecha_dt = fecha_dt.replace(tzinfo=ZONA_HORARIA)
        
        return fecha_dt.isocalendar()[1]
    except Exception as e:
        logger.error(f"Error al obtener semana desde fecha: {e}")
        return obtener_semana_actual()


# ============================================================
# VALIDACIONES DE NEGOCIO
# ============================================================

def validar_monto(monto: Union[int, float]) -> bool:
    """Valida que un monto sea positivo y no exceda límites."""
    try:
        monto = float(monto) if monto is not None else 0
        return 0 <= monto <= 999999999.99
    except (ValueError, TypeError):
        return False


def validar_porcentaje(porcentaje: Union[int, float]) -> bool:
    """Valida que un porcentaje esté entre 0 y 100."""
    try:
        porcentaje = float(porcentaje) if porcentaje is not None else 0
        return 0 <= porcentaje <= 100
    except (ValueError, TypeError):
        return False


def validar_rango_fechas(fecha_inicio: str, fecha_fin: str) -> bool:
    """Valida que la fecha de inicio sea anterior a la fecha de fin."""
    try:
        inicio = parsear_fecha(fecha_inicio)
        fin = parsear_fecha(fecha_fin)
        
        if not inicio or not fin:
            return False
        
        return inicio <= fin
    except Exception:
        return False


# ============================================================
# LOGGING Y DEBUG
# ============================================================

def log_error(func_name: str, error: Exception, context: Dict = None) -> None:
    """Registra un error con contexto."""
    try:
        mensaje = f"Error en {func_name}: {str(error)}"
        if context:
            mensaje += f" | Contexto: {context}"
        logger.error(mensaje)
    except Exception:
        pass


def es_entorno_produccion() -> bool:
    """Verifica si estamos en entorno de producción."""
    try:
        return os.environ.get("ENVIRONMENT", "development").lower() == "production"
    except Exception:
        return False

# ============================================================
# SANITIZACIÓN HTML - PROTECCIÓN CONTRA XSS
# ============================================================

import html

def sanitizar_html(texto: str, max_length: int = 500) -> str:
    """
    Sanitiza texto para mostrarlo de forma segura en HTML.
    Escapa caracteres peligrosos y elimina posibles scripts.
    Usa html.escape para una protección completa contra XSS.
    
    Args:
        texto: Texto a sanitizar
        max_length: Longitud máxima del texto (por defecto 500)
    
    Returns:
        Texto sanitizado y seguro para mostrar en HTML
    """
    if not texto or not isinstance(texto, str):
        return ""
    
    # Escapar caracteres HTML peligrosos (&, <, >, ", ')
    texto_seguro = html.escape(texto)
    
    # Limitar longitud para evitar abusos
    if len(texto_seguro) > max_length:
        texto_seguro = texto_seguro[:max_length] + "..."
    
    return texto_seguro


def sanitizar_lista_html(lista: list, max_length: int = 500) -> list:
    """
    Sanitiza una lista de textos para mostrarlos de forma segura en HTML.
    
    Args:
        lista: Lista de textos a sanitizar
        max_length: Longitud máxima de cada texto
    
    Returns:
        Lista con todos los textos sanitizados
    """
    if not lista or not isinstance(lista, list):
        return []
    
    return [sanitizar_html(str(item), max_length) for item in lista]


def sanitizar_dict_html(diccionario: dict, keys: list = None, max_length: int = 500) -> dict:
    """
    Sanitiza los valores de un diccionario para mostrarlos de forma segura en HTML.
    
    Args:
        diccionario: Diccionario a sanitizar
        keys: Lista de claves a sanitizar (si es None, sanitiza todos los valores de tipo str)
        max_length: Longitud máxima de cada texto
    
    Returns:
        Diccionario con los valores sanitizados
    """
    if not diccionario or not isinstance(diccionario, dict):
        return {}
    
    resultado = diccionario.copy()
    
    if keys is None:
        # Sanitizar todos los valores que sean strings
        for key, value in resultado.items():
            if isinstance(value, str):
                resultado[key] = sanitizar_html(value, max_length)
            elif isinstance(value, list):
                resultado[key] = sanitizar_lista_html(value, max_length)
    else:
        # Sanitizar solo las claves especificadas
        for key in keys:
            if key in resultado:
                if isinstance(resultado[key], str):
                    resultado[key] = sanitizar_html(resultado[key], max_length)
                elif isinstance(resultado[key], list):
                    resultado[key] = sanitizar_lista_html(resultado[key], max_length)
    
    return resultado