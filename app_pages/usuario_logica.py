# pages/usuario_logica.py
"""
Logica de negocio del panel de usuario: verificacion de estado de envios,
formateo de datos de centros, y procesamiento del envio de reportes.

Separado de usuario.py (que se queda con el renderizado de pantalla) para
que esta logica sea reutilizable y testeable de forma independiente de
Streamlit -- son ademas las funciones con mas valor para exponer como
"tools" en la futura fase del agente de IA.
"""

import streamlit as st
import os
import tempfile
from datetime import datetime
from typing import List, Optional, Dict, Any

from src.config import Config
from src.db_manager import get_db_manager
from src.logging_config import obtener_logger

logger = obtener_logger(__name__)

# Importar DriveManager de manera segura
try:
    from src.drive_manager import get_drive_manager
    DRIVE_DISPONIBLE = True
except ImportError:
    DRIVE_DISPONIBLE = False
    print("ADVERTENCIA: Google Drive no esta disponible. Se omitira la subida a Drive.")

# Importar EmailSender de manera segura
try:
    from src.email_sender import get_email_sender
    EMAIL_DISPONIBLE = True
except ImportError:
    EMAIL_DISPONIBLE = False
    print("ADVERTENCIA: el envío de correos no está disponible.")

from utils.helpers import generar_nombre_archivo, obtener_codigo_seguimiento
from utils.duplicados import solo_originales, observacion_duplicado, PREFIJO_REEMPLAZADO
from src.observaciones import get_observaciones, limpiar_texto


# ============================================================
# NOTA: semana activa, año activo y fecha de corte se obtienen
# directamente de Config.get_semana_actual() / get_anio_actual() /
# get_fecha_corte(), que centralizan la lectura desde Supabase con
# fallback a .env.
# ============================================================


def obtener_anios_permitidos():
    """
    Obtiene la lista de años permitidos para envios desde la base de datos.
    """
    try:
        db_manager = get_db_manager()
        return db_manager.obtener_anios_permitidos()
    except:
        return [datetime.now().year]


def obtener_semanas_por_anio(anio: int) -> int:
    """
    Obtiene el numero de semanas para un año especifico desde la base de datos.
    """
    try:
        db_manager = get_db_manager()
        return db_manager.obtener_semanas_por_anio(anio)
    except:
        return 52


def obtener_semanas_disponibles_por_anio(anio: int) -> List[int]:
    """
    Obtiene la lista de semanas disponibles para un año.
    """
    semanas = obtener_semanas_por_anio(anio)
    return list(range(1, semanas + 1))


def obtener_fecha_corte_semana(anio: int, semana: int) -> datetime:
    """
    OBTIENE LA FECHA DE CORTE CONFIGURADA POR EL ADMINISTRADOR.

    La fecha de corte es una fecha fija que el administrador establece
    y se aplica a TODOS los envios, independientemente de la semana
    seleccionada (los parametros se mantienen por compatibilidad con
    quienes ya llaman a esta funcion con anio/semana).
    """
    return Config.get_fecha_corte_datetime(anio, semana)


# ============================================================
# FUNCIONES PARA OBTENER CENTROS Y EXCLUIDOS (DESDE DB)
# ============================================================

def obtener_centros_excluidos():
    """
    Obtiene el diccionario de centros excluidos desde la base de datos.
    """
    try:
        db_manager = get_db_manager()
        return db_manager.obtener_todas_las_exclusiones_agrupadas()
    except Exception as e:
        print(f"Error al obtener centros excluidos: {e}")
        return {}


def obtener_centros_con_red_por_red(red_nombre: str) -> List[Dict]:
    """
    Obtiene todos los centros de una red específica usando la vista centros_con_red.
    Retorna una lista de diccionarios con id, red_id, red_nombre, codigo, centro_nombre.
    """
    try:
        db_manager = get_db_manager()
        # Usar la vista centros_con_red para obtener datos completos
        resultado = db_manager.supabase.table('centros_con_red')\
            .select('*')\
            .eq('red_nombre', red_nombre)\
            .execute()

        return resultado.data if resultado.data else []
    except Exception as e:
        print(f"Error al obtener centros de la red {red_nombre}: {e}")
        return []


def formatear_centro_desde_dict(centro_dict: Dict) -> str:
    """
    Formatea un centro desde un diccionario de la vista centros_con_red.
    Retorna "CODIGO NOMBRE" o solo "NOMBRE" si no tiene código.
    """
    if not centro_dict:
        return ""

    codigo = centro_dict.get('codigo', '')
    nombre = centro_dict.get('centro_nombre', '') or centro_dict.get('nombre', '')

    if codigo and nombre:
        return f"{codigo} {nombre}"
    elif nombre:
        return nombre
    else:
        return str(centro_dict)


def obtener_nombre_limpio_desde_dict(centro_dict: Dict) -> str:
    """
    Obtiene el nombre limpio de un centro desde un diccionario.
    """
    if not centro_dict:
        return ""

    nombre = centro_dict.get('centro_nombre', '') or centro_dict.get('nombre', '')
    return nombre.strip()


def _parece_codigo_centro(token: str) -> bool:
    """
    Un código de centro puede ser puramente numérico ("127", "019") o
    alfanumérico ("B56", "B58"). Se considera código si es corto y
    tiene al menos un dígito -- así no se confunde la primera palabra
    de un nombre (ej. "CAP", "P.M.", "H.II") con un código real.
    """
    if not token:
        return False
    limpio = token.replace('.', '')
    if len(limpio) > 6 or not limpio.isalnum():
        return False
    return any(c.isdigit() for c in limpio)


def extraer_nombre_limpio(texto: str) -> str:
    """
    Extrae el nombre sin código de un centro en formato 'CODIGO NOMBRE'.
    Ejemplo: "468 CAP I ANTABAMBA" -> "CAP I ANTABAMBA"
    Soporta códigos numéricos ("468") y alfanuméricos ("B56").
    """
    if not texto:
        return ""

    texto = str(texto).strip()
    if not texto:
        return ""

    partes = texto.split(' ', 1)
    if len(partes) >= 2 and _parece_codigo_centro(partes[0]):
        return partes[1].strip()
    return texto


def extraer_codigo(texto: str) -> str:
    """
    Extrae el código de un centro en formato 'CODIGO NOMBRE'.
    Ejemplo: "468 CAP I ANTABAMBA" -> "468"
    Soporta códigos numéricos ("468") y alfanuméricos ("B56").
    """
    if not texto:
        return ""

    texto = str(texto).strip()
    if not texto:
        return ""

    partes = texto.split(' ', 1)
    if len(partes) >= 2 and _parece_codigo_centro(partes[0]):
        return partes[0].strip()
    return ""


# ============================================================
# FUNCIONES PARA GUARDAR Y CARGAR USUARIOS FRECUENTES
# ============================================================

def guardar_usuario_frecuente(datos_usuario: dict):
    """Guarda los datos de un usuario frecuente en session_state."""
    if 'usuarios_frecuentes' not in st.session_state:
        st.session_state.usuarios_frecuentes = []

    correo = datos_usuario.get('correo', '')
    for usuario in st.session_state.usuarios_frecuentes:
        if usuario.get('correo') == correo:
            usuario.update(datos_usuario)
            return

    st.session_state.usuarios_frecuentes.append(datos_usuario)

    if len(st.session_state.usuarios_frecuentes) > 10:
        st.session_state.usuarios_frecuentes = st.session_state.usuarios_frecuentes[-10:]


def cargar_usuarios_frecuentes():
    """Carga los usuarios frecuentes desde session_state."""
    return st.session_state.get('usuarios_frecuentes', [])


def obtener_hora_local():
    """Obtiene la hora actual en la zona horaria de Perú (no depende de la zona del servidor)."""
    return Config.obtener_fecha_actual()


def estandarizar_nombre(texto: str) -> str:
    """
    Estandariza un nombre o apellido: primera letra mayuscula, resto minusculas.
    Ejemplo: "CaRoL" -> "Carol", "MARIA" -> "Maria", "juan" -> "Juan"
    """
    if not texto or not isinstance(texto, str):
        return ""

    texto = texto.strip()
    if not texto:
        return ""

    # Si tiene espacios, capitalizar cada palabra
    palabras = texto.split()
    palabras_capitalizadas = []
    for palabra in palabras:
        if palabra:
            palabras_capitalizadas.append(palabra[0].upper() + palabra[1:].lower())

    return " ".join(palabras_capitalizadas)


def verificar_estado_envio(semana_seleccionada: int, anio_seleccionado: int = None) -> dict:
    """
    Verifica si el envío está a tiempo o es tardío.

    CRITERIOS DE VERIFICACION:
    1. El año seleccionado debe estar en la lista de años permitidos
    2. Si el año seleccionado es menor al año actual → ATRASADO
    3. Si el año seleccionado es igual al año actual:
       3.1 Si la semana seleccionada es menor a la semana actual → ATRASADO
       3.2 Si la semana seleccionada es igual a la semana actual → Verificar fecha de corte
       3.3 Si la semana seleccionada es mayor a la semana actual → PROGRAMADO (si esta permitido) o ATRASADO
    4. Si el año seleccionado es mayor al año actual → PROGRAMADO (si esta permitido) o ATRASADO

    La fecha de corte es la CONFIGURADA POR EL ADMINISTRADOR,
    y se usa SOLO cuando la semana seleccionada es igual a la semana actual.
    """
    hora_actual = Config.obtener_fecha_actual()
    semana_actual = Config.get_semana_actual()
    anio_actual = Config.get_anio_actual()

    # Si no se proporciona año, usar el actual
    if anio_seleccionado is None:
        anio_seleccionado = anio_actual

    # ============================================================
    # VALIDAR AÑO PERMITIDO
    # ============================================================
    anios_permitidos = obtener_anios_permitidos()
    if anio_seleccionado not in anios_permitidos:
        return {
            'es_atrasado': True,
            'dias_atraso': 0,
            'mensaje': f"AÑO NO PERMITIDO: {anio_seleccionado}. Años permitidos: {', '.join(map(str, anios_permitidos))}",
            'fecha_limite': None,
            'hora_actual': hora_actual,
            'semanas_atraso': 0,
            'anio_seleccionado': anio_seleccionado,
            'semana_seleccionada': semana_seleccionada,
            'anio_actual': anio_actual,
            'semana_actual': semana_actual
        }

    # ============================================================
    # OBTENER CONFIGURACIONES
    # ============================================================
    permitir_adelantados_val = permitir_adelantados()

    # ============================================================
    # CASO 1: AÑO ANTERIOR AL ACTUAL
    # ============================================================
    if anio_seleccionado < anio_actual:
        # El año seleccionado es anterior al actual → SIEMPRE ATRASADO
        semanas_atraso = (anio_actual - anio_seleccionado) * 52 + (semana_actual - semana_seleccionada)

        # Obtener fecha de corte (solo para mostrar)
        fecha_limite = obtener_fecha_corte_semana(anio_seleccionado, semana_seleccionada)

        return {
            'es_atrasado': True,
            'dias_atraso': semanas_atraso * 7,
            'mensaje': f"ENVÍO TARDÍO: Año {anio_seleccionado} anterior al año actual ({anio_actual})",
            'fecha_limite': fecha_limite,
            'hora_actual': hora_actual,
            'semanas_atraso': semanas_atraso,
            'anio_seleccionado': anio_seleccionado,
            'semana_seleccionada': semana_seleccionada,
            'anio_actual': anio_actual,
            'semana_actual': semana_actual
        }

    # ============================================================
    # CASO 2: AÑO IGUAL AL ACTUAL
    # ============================================================
    if anio_seleccionado == anio_actual:
        # Obtener fecha de corte
        fecha_limite = obtener_fecha_corte_semana(anio_seleccionado, semana_seleccionada)

        # ============================================================
        # CASO 2.1: SEMANA ANTERIOR A LA SEMANA ACTUAL
        # ============================================================
        if semana_seleccionada < semana_actual:
            # La semana seleccionada es anterior a la semana actual → ATRASADO
            semanas_atraso = semana_actual - semana_seleccionada

            return {
                'es_atrasado': True,
                'dias_atraso': semanas_atraso * 7,
                'mensaje': f"ENVÍO TARDÍO: Semana {semana_seleccionada} anterior a la semana actual ({semana_actual})",
                'fecha_limite': fecha_limite,
                'hora_actual': hora_actual,
                'semanas_atraso': semanas_atraso,
                'anio_seleccionado': anio_seleccionado,
                'semana_seleccionada': semana_seleccionada,
                'anio_actual': anio_actual,
                'semana_actual': semana_actual
            }

        # ============================================================
        # CASO 2.2: SEMANA IGUAL A LA SEMANA ACTUAL
        # ============================================================
        elif semana_seleccionada == semana_actual:
            # La semana seleccionada es igual a la semana actual
            # Verificar si la fecha actual supera la fecha de corte
            es_atrasado = hora_actual > fecha_limite if fecha_limite else False

            if es_atrasado:
                dias_atraso = (hora_actual - fecha_limite).days if fecha_limite else 0
                mensaje = f"ENVÍO TARDÍO: La fecha de corte ({fecha_limite.strftime('%d/%m/%Y %H:%M')}) ya pasó"
            else:
                dias_atraso = 0
                mensaje = "ENVÍO A TIEMPO"

            return {
                'es_atrasado': es_atrasado,
                'dias_atraso': max(0, dias_atraso) if es_atrasado else 0,
                'mensaje': mensaje,
                'fecha_limite': fecha_limite,
                'hora_actual': hora_actual,
                'semanas_atraso': 0,
                'anio_seleccionado': anio_seleccionado,
                'semana_seleccionada': semana_seleccionada,
                'anio_actual': anio_actual,
                'semana_actual': semana_actual
            }

        # ============================================================
        # CASO 2.3: SEMANA FUTURA (MAYOR A LA SEMANA ACTUAL)
        # ============================================================
        else:  # semana_seleccionada > semana_actual
            if permitir_adelantados_val:
                # Permitir envios adelantados
                return {
                    'es_atrasado': False,
                    'dias_atraso': 0,
                    'mensaje': f"ENVÍO PROGRAMADO: Semana {semana_seleccionada} (futura) - Permitido",
                    'fecha_limite': fecha_limite,
                    'hora_actual': hora_actual,
                    'semanas_atraso': 0,
                    'anio_seleccionado': anio_seleccionado,
                    'semana_seleccionada': semana_seleccionada,
                    'anio_actual': anio_actual,
                    'semana_actual': semana_actual
                }
            else:
                # No se permiten envios adelantados
                return {
                    'es_atrasado': True,
                    'dias_atraso': 0,
                    'mensaje': f"SEMANA FUTURA NO PERMITIDA: Semana {semana_seleccionada} (semana actual: {semana_actual})",
                    'fecha_limite': fecha_limite,
                    'hora_actual': hora_actual,
                    'semanas_atraso': 0,
                    'anio_seleccionado': anio_seleccionado,
                    'semana_seleccionada': semana_seleccionada,
                    'anio_actual': anio_actual,
                    'semana_actual': semana_actual
                }

    # ============================================================
    # CASO 3: AÑO FUTURO (MAYOR AL ACTUAL)
    # ============================================================
    if anio_seleccionado > anio_actual:
        if permitir_adelantados_val:
            # Permitir envios de años futuros
            return {
                'es_atrasado': False,
                'dias_atraso': 0,
                'mensaje': f"ENVÍO PROGRAMADO: Año {anio_seleccionado} (futuro) - Permitido",
                'fecha_limite': None,
                'hora_actual': hora_actual,
                'semanas_atraso': 0,
                'anio_seleccionado': anio_seleccionado,
                'semana_seleccionada': semana_seleccionada,
                'anio_actual': anio_actual,
                'semana_actual': semana_actual
            }
        else:
            return {
                'es_atrasado': True,
                'dias_atraso': 0,
                'mensaje': f"AÑO FUTURO NO PERMITIDO: {anio_seleccionado}",
                'fecha_limite': None,
                'hora_actual': hora_actual,
                'semanas_atraso': 0,
                'anio_seleccionado': anio_seleccionado,
                'semana_seleccionada': semana_seleccionada,
                'anio_actual': anio_actual,
                'semana_actual': semana_actual
            }

    # Fallback (nunca deberia llegar aqui)
    return {
        'es_atrasado': False,
        'dias_atraso': 0,
        'mensaje': "Estado no determinado",
        'fecha_limite': None,
        'hora_actual': hora_actual,
        'semanas_atraso': 0,
        'anio_seleccionado': anio_seleccionado,
        'semana_seleccionada': semana_seleccionada,
        'anio_actual': anio_actual,
        'semana_actual': semana_actual
    }


def verificar_envio_duplicado(red: str, centros: List[str], ano: int, semana: int) -> Optional[Dict]:
    """
    Verifica si ya existe un envío registrado para esta misma red, año y
    semana que incluya al menos uno de los mismos centros seleccionados.

    Es una advertencia preventiva (no bloquea nada por sí sola): sirve
    para avisar al usuario ANTES de enviar si, por ejemplo, recargó la
    página y va a volver a mandar un reporte que ya fue procesado, o si
    alguien de su red ya envió ese centro esta semana.

    Retorna None si no hay coincidencia, o un dict con:
      - 'centros_coincidentes': nombres (normalizados) de los centros
        que ya tienen un envío registrado esta semana.
      - 'envios': lista de los envíos previos que coinciden (código de
        seguimiento, fecha, estado, remitente), para dar contexto.
    """
    try:
        db_manager = get_db_manager()
        envios_previos = db_manager.obtener_envios(
            anio=ano, semana=semana, red=red, limit=1000
        )
    except Exception as e:
        print(f"Error al verificar envío duplicado: {e}")
        return None

    # Los envíos que ya fueron registrados como duplicados no cuentan como
    # "envío original": si el original se eliminó, el siguiente es un envío normal.
    envios_previos = solo_originales(envios_previos)
    if not envios_previos:
        return None

    nombres_seleccionados = {
        extraer_nombre_limpio(c).lower() for c in (centros or []) if extraer_nombre_limpio(c)
    }
    if not nombres_seleccionados:
        return None

    centros_coincidentes = set()
    envios_coincidentes = []

    for envio in envios_previos:
        centros_envio = envio.get('centros', []) or []
        nombres_envio = set()
        for c in centros_envio:
            if isinstance(c, dict):
                nombre = c.get('nombre', str(c))
            else:
                nombre = extraer_nombre_limpio(str(c))
            if nombre:
                nombres_envio.add(nombre.strip().lower())

        interseccion = nombres_seleccionados & nombres_envio
        if interseccion:
            centros_coincidentes |= interseccion
            envios_coincidentes.append({
                'codigo_seguimiento': envio.get('codigo_seguimiento', 'N/A'),
                'fecha_envio': envio.get('fecha_envio', ''),
                'estado': envio.get('estado', ''),
                'nombre_usuario': f"{envio.get('nombre_usuario', '')} {envio.get('apellido_usuario', '')}".strip(),
            })

    if not envios_coincidentes:
        return None

    return {
        'centros_coincidentes': sorted(centros_coincidentes),
        'envios': envios_coincidentes,
    }


def permitir_adelantados() -> bool:
    """Verifica si se permiten envios adelantados."""
    try:
        db_manager = get_db_manager()
        permitir = db_manager.obtener_configuracion('permitir_envios_adelantados')
        return permitir.lower() == 'true' if permitir else False
    except:
        return False


# ============================================================
# CLASIFICACIÓN POR ARCHIVO: NUEVO vs YA RECIBIDO (centro + tipo)
# ============================================================

_LETRA_DE_TIPO = {'consulta externa': 'c', 'emergencia': 'e', 'hospitalizacion': 'h', 'hospitalización': 'h'}
_TIPO_DE_LETRA = {'c': 'Consulta Externa', 'e': 'Emergencia', 'h': 'Hospitalizacion'}
_BYTES_MIN_HUELLA = 512   # archivos más pequeños (vacíos/solo cabecera) pueden repetirse legítimamente


def _letra_tipo(tipo) -> Optional[str]:
    t = str(tipo or '').strip().lower()
    if t in ('c', 'e', 'h'):
        return t
    return _LETRA_DE_TIPO.get(t)


def _clave_centro(nombre) -> str:
    return extraer_nombre_limpio(str(nombre or '')).strip().lower()


def _mapa_centros_por_codigo(red: str) -> Dict[str, Dict]:
    """{CODIGO_EN_MAYÚSCULAS: fila del centro} de la red."""
    return {
        str(c.get('codigo')).strip().upper(): c
        for c in obtener_centros_con_red_por_red(red) if c.get('codigo')
    }


def _pares_de_envio(envio: Dict) -> set:
    """
    Pares (centro, tipo) que cubre un envío ya registrado. Si el envío
    guardó el detalle por archivo (v6.8) se usa tal cual; en envíos
    anteriores se asume centros × tipos del formulario.
    """
    detalle = envio.get('detalle_archivos')
    if isinstance(detalle, list) and detalle:
        return {
            (_clave_centro(d.get('centro')), _letra_tipo(d.get('tipo')))
            for d in detalle if isinstance(d, dict) and d.get('centro') and _letra_tipo(d.get('tipo'))
        }
    centros = envio.get('centros') or []
    nombres = {
        _clave_centro(c.get('nombre', '') if isinstance(c, dict) else c) for c in centros
    }
    letras = {_letra_tipo(t) for t in (envio.get('tipo_reporte') or [])}
    return {(n, l) for n in nombres if n for l in letras if l}


def _detalle_para_bd(info_zip: Dict, mapa: Dict[str, Dict], archivos=None) -> List[Dict]:
    """Detalle por archivo que se guarda en envios.detalle_archivos (sin contenido, solo huella)."""
    incluir = set(archivos) if archivos is not None else None
    salida = []
    for d in (info_zip or {}).get('archivos_detalle', []):
        if incluir is not None and d['archivo'] not in incluir:
            continue
        fila = mapa.get(str(d.get('codigo') or '').upper())
        salida.append({
            'archivo': os.path.basename(d['archivo']),
            'codigo': d.get('codigo'),
            'centro': (fila.get('centro_nombre') or '').strip() if fila else None,
            'tipo': _letra_tipo(d.get('tipo')),
            'semana': d.get('semana'),
            'anio': d.get('anio'),
            'sha256': d.get('sha256'),
            'bytes': d.get('bytes'),
        })
    return salida


def _huellas_ya_enviadas(red: str, ano: int, semana: int, info_zip: Dict) -> List[Dict]:
    """
    Archivos de este ZIP idénticos (misma huella SHA-256) a uno enviado por
    la red en OTRA semana del mismo año -- típico de quien renombra un
    archivo viejo para aparentar el reporte de la semana. Solo se compara
    la huella: el contenido nunca se abre. Ignora archivos muy pequeños.
    """
    mias = {
        d['sha256']: d for d in (info_zip or {}).get('archivos_detalle', [])
        if d.get('sha256') and (d.get('bytes') or 0) >= _BYTES_MIN_HUELLA
    }
    if not mias:
        return []
    try:
        previos = get_db_manager().obtener_envios(anio=ano, red=red, limit=1000)
    except Exception as e:
        logger.warning("No se pudo comparar huellas con envíos previos: %s", e)
        return []
    hallados = []
    for envio in previos or []:
        if envio.get('semana') == semana:
            continue
        for d in (envio.get('detalle_archivos') or []):
            if isinstance(d, dict) and d.get('sha256') in mias and (d.get('bytes') or 0) >= _BYTES_MIN_HUELLA:
                orig = mias[d['sha256']]
                hallados.append({
                    'archivo': os.path.basename(orig['archivo']),
                    'semana_previa': envio.get('semana'),
                    'codigo_previo': envio.get('codigo_seguimiento', 'N/A'),
                })
    return hallados


def _semana_congelada(ano: int, semana: int) -> bool:
    """
    True si el resumen de esa semana ya fue validado o enviado a la entidad externa: sus números
    ya no deben cambiar solos, así que no se permite reemplazar archivos (solo duplicado).
    """
    try:
        from src.cierres import get_cierres
        c = get_cierres()
        if not c.disponible():
            return False
        filas = c._t("cierres_corte").select("resumen_estado").eq("anio", ano).eq("semana_cerrada", semana).execute().data or []
        return any(f.get("resumen_estado") in ("VALIDADO", "ENVIADO") for f in filas)
    except Exception as e:
        logger.warning("No se pudo comprobar el cierre de la semana %s/%s: %s", semana, ano, e)
        return False


def _evaluar_reemplazo(ano: int, semana: int, verificables: list, cubiertos: Dict) -> tuple:
    """
    ¿Se puede reemplazar lo ya enviado? Devuelve (posible, motivo_si_no, items) donde items es
    {envio_id: {'envio': fila, 'pares': {(centro, tipo)}}}: qué parte de cada envío anterior se reemplazaría.
    """
    if _semana_congelada(ano, semana):
        return False, ("La semana ya fue cerrada y su resumen validado: los archivos ya enviados no se pueden "
                       "reemplazar. Puede enviarlos como duplicado y la OIIS decidirá."), {}
    items: Dict = {}
    for d, fila, letra in verificables:
        par = (_clave_centro(fila.get('centro_nombre')), letra)
        for e in cubiertos.get(par, []):
            det = e.get('detalle_archivos')
            tiene_par = isinstance(det, list) and any(
                isinstance(x, dict) and (_clave_centro(x.get('centro')), _letra_tipo(x.get('tipo'))) == par for x in det)
            if not tiene_par:
                return False, ("Uno de los envíos anteriores es de una versión previa del sistema y no se puede "
                               "reemplazar archivo por archivo. Puede enviarlo como duplicado."), {}
            ident = str(e.get('drive_file_id') or '')
            if not ident or ident == 'LOCAL':
                return False, "Un envío anterior no tiene su archivo guardado en Drive, no se puede reemplazar.", {}
            it = items.setdefault(e.get('id'), {'envio': e, 'pares': set()})
            it['pares'].add(par)
    return bool(items), "", items


def clasificar_envio(red: str, ano: int, semana: int, info_zip: Optional[Dict]) -> Dict:
    """
    Separa los archivos del ZIP en NUEVOS y YA RECIBIDOS esta semana
    (mismo centro + mismo tipo c/e/h + misma red/semana/año, contra los
    envíos originales ya registrados).

    Devuelve un dict con:
      modo: 'legacy'  -> el ZIP no permite verificar centro+tipo por nombre;
                         se usa la regla antigua (centros del formulario).
            'normal'  -> nada repetido.
            'todo_duplicado' -> todo lo verificable ya estaba recibido.
            'dividir' -> hay nuevos y repetidos: se parte en dos ZIP.
      nuevos / repetidos: nombres de archivo dentro del ZIP.
      centros_repetidos / centros_nuevos: etiquetas "CODIGO NOMBRE".
      duplicado_info: compatible con el diálogo de duplicados.
      huellas: archivos idénticos a los de otra semana (aviso).
    """
    plan = {'modo': 'legacy', 'nuevos': [], 'repetidos': [], 'sin_verificar': [],
            'centros_repetidos': [], 'centros_nuevos': [], 'tipos_repetidos': [], 'tipos_nuevos': [],
            'detalle_repetido': [], 'duplicado_info': None, 'huellas': [],
            'reemplazo_posible': False, 'reemplazo_motivo': '', 'reemplazo_items': {}}
    detalle = (info_zip or {}).get('archivos_detalle') or []
    if not detalle:
        return plan

    mapa = _mapa_centros_por_codigo(red)
    verificables, sin_verificar = [], []
    for d in detalle:
        fila = mapa.get(str(d.get('codigo') or '').upper())
        letra = _letra_tipo(d.get('tipo'))
        if fila and letra:
            verificables.append((d, fila, letra))
        else:
            sin_verificar.append(d['archivo'])
    plan['sin_verificar'] = sin_verificar
    plan['huellas'] = _huellas_ya_enviadas(red, ano, semana, info_zip)
    if not verificables:
        return plan

    try:
        previos = solo_originales(get_db_manager().obtener_envios(anio=ano, semana=semana, red=red, limit=1000))
    except Exception as e:
        logger.warning("No se pudo verificar duplicados por archivo: %s", e)
        previos = []

    cubiertos: Dict[tuple, List[Dict]] = {}
    for envio in previos:
        for par in _pares_de_envio(envio):
            cubiertos.setdefault(par, []).append(envio)

    nuevos, repetidos = list(sin_verificar), []
    c_rep, c_nue, t_rep, t_nue, envios_rel = {}, {}, set(), set(), {}
    for d, fila, letra in verificables:
        par = (_clave_centro(fila.get('centro_nombre')), letra)
        etiqueta = formatear_centro_desde_dict(fila)
        if par in cubiertos:
            repetidos.append(d['archivo'])
            c_rep[etiqueta] = par
            t_rep.add(_TIPO_DE_LETRA[letra])
            for e in cubiertos[par]:
                envios_rel[e.get('id', e.get('codigo_seguimiento'))] = e
            plan['detalle_repetido'].append(f"{fila.get('centro_nombre', '').strip()} · {_TIPO_DE_LETRA[letra]}")
        else:
            nuevos.append(d['archivo'])
            c_nue[etiqueta] = par
            t_nue.add(_TIPO_DE_LETRA[letra])

    plan.update({
        'nuevos': nuevos, 'repetidos': repetidos,
        'centros_repetidos': sorted(c_rep), 'centros_nuevos': sorted(c_nue),
        'tipos_repetidos': [t for t in ('Consulta Externa', 'Hospitalizacion', 'Emergencia') if t in t_rep],
        'tipos_nuevos': [t for t in ('Consulta Externa', 'Hospitalizacion', 'Emergencia') if t in t_nue],
    })
    if not repetidos:
        plan['modo'] = 'normal'
        return plan

    plan['modo'] = 'dividir' if nuevos else 'todo_duplicado'
    plan['reemplazo_posible'], plan['reemplazo_motivo'], plan['reemplazo_items'] = _evaluar_reemplazo(
        ano, semana, verificables, cubiertos)
    plan['duplicado_info'] = {
        'centros_coincidentes': sorted({extraer_nombre_limpio(c) for c in c_rep}),
        'envios': [{
            'codigo_seguimiento': e.get('codigo_seguimiento', 'N/A'),
            'fecha_envio': e.get('fecha_envio', ''),
            'estado': e.get('estado', ''),
            'nombre_usuario': f"{e.get('nombre_usuario', '')} {e.get('apellido_usuario', '')}".strip(),
        } for e in envios_rel.values()],
        'pares_repetidos': sorted(set(plan['detalle_repetido'])),
    }
    return plan


@st.cache_data(ttl=300, show_spinner=False)
def obtener_catalogo_centros() -> Dict[str, List[Dict]]:
    """
    Catálogo de TODOS los centros de TODAS las redes: {CODIGO: [{red, centro}, ...]}.
    Sirve para reconocer a qué red pertenece un código que no es de la red elegida.
    Si no se puede leer devuelve {} (entonces no se bloquea nada por red).
    """
    try:
        filas = get_db_manager().supabase.table('centros_con_red').select('*').range(0, 4999).execute().data or []
    except Exception as e:
        logger.warning("No se pudo leer el catálogo de centros: %s", e)
        return {}
    cat: Dict[str, List[Dict]] = {}
    for f in filas:
        cod = str(f.get('codigo') or '').strip().upper()
        if cod:
            cat.setdefault(cod, []).append({'red': f.get('red_nombre') or '?', 'centro': (f.get('centro_nombre') or '').strip()})
    return cat


def validar_red_zip(info_zip: Optional[Dict], red: str) -> Dict:
    """
    Comprueba que los códigos de centro que traen los nombres de los archivos
    pertenezcan a la red elegida.

      · algún archivo de OTRA red  -> NO pasa (mezcla o ZIP equivocado).
      · ningún archivo de la red   -> NO pasa (códigos de otra red o inexistentes).
      · códigos inexistentes junto a los de la red -> pasa, con nota para la OIIS.
      · archivos sin código en el nombre -> no se pueden comprobar, no cuentan.

    Devuelve {'ok', 'mensaje' (Markdown, con qué corregir), 'propios', 'ajenos', 'desconocidos', 'nota'}.
    """
    res = {'ok': True, 'mensaje': '', 'propios': [], 'ajenos': [], 'desconocidos': [], 'nota': ''}
    detalle = [d for d in (info_zip or {}).get('archivos_detalle', []) if d.get('codigo')]
    if not detalle:
        return res
    propios_cat = _mapa_centros_por_codigo(red)
    catalogo = obtener_catalogo_centros()
    if not propios_cat and not catalogo:
        return res          # sin catálogo no hay con qué comparar

    ajenos: Dict[str, Dict] = {}
    desconocidos: Dict[str, List[str]] = {}
    propios: Dict[str, int] = {}
    for d in detalle:
        cod = str(d['codigo']).upper()
        nombre = os.path.basename(d['archivo'])
        if cod in propios_cat:
            propios[cod] = propios.get(cod, 0) + 1
        elif cod in catalogo:
            e = ajenos.setdefault(cod, {'codigo': cod, 'centros': sorted({c['centro'] for c in catalogo[cod]}),
                                        'redes': sorted({c['red'] for c in catalogo[cod]}), 'archivos': []})
            e['archivos'].append(nombre)
        else:
            desconocidos.setdefault(cod, []).append(nombre)

    res['propios'] = sorted(propios)
    res['ajenos'] = list(ajenos.values())
    res['desconocidos'] = [{'codigo': c, 'archivos': a} for c, a in sorted(desconocidos.items())]

    def _lista(nombres, limite=4):
        return ", ".join(f"`{n}`" for n in nombres[:limite]) + (f" y {len(nombres) - limite} más" if len(nombres) > limite else "")

    def _linea_ajena(e):
        return (f"- Código **{e['codigo']}** · {' / '.join(e['centros'])} → red **{' / '.join(e['redes'])}** "
                f"({len(e['archivos'])} archivo(s): {_lista(e['archivos'], 3)})")

    desc_txt = "; ".join(f"código **{d['codigo']}** ({len(d['archivos'])} archivo(s): {_lista(d['archivos'], 3)})"
                         for d in res['desconocidos'])

    if ajenos and propios:
        res['ok'] = False
        res['mensaje'] = (
            f"**El ZIP mezcla archivos de la red {red} con archivos de otras redes.**\n\n"
            f"Archivos de otra red:\n" + "\n".join(_linea_ajena(e) for e in ajenos.values()) + "\n\n"
            f"Archivos de {red}: {sum(propios.values())} (códigos {', '.join(sorted(propios))}).\n\n"
            "Qué hacer: quite del ZIP los archivos de otras redes y adjúntelo de nuevo. Cada red envía su propio ZIP."
        )
    elif ajenos:
        redes = sorted({r for e in ajenos.values() for r in e['redes']})
        res['ok'] = False
        res['mensaje'] = (
            f"**Este ZIP no corresponde a la red {red} que eligió.**\n\n"
            "Ningún archivo es de esa red:\n" + "\n".join(_linea_ajena(e) for e in ajenos.values()) + "\n\n"
            + (f"Parece un ZIP de la red **{redes[0]}**: si es así, cambie «Red asistencial». "
               if len(redes) == 1 else "Los archivos son de varias redes. ")
            + f"Si su red es {red}, adjunte el ZIP correcto."
        )
    elif desconocidos and not propios:
        res['ok'] = False
        res['mensaje'] = (
            f"**Ningún archivo del ZIP corresponde a un centro de la red {red}.**\n\n"
            f"Los códigos no existen en el catálogo de centros: {desc_txt}.\n\n"
            "Verifique que adjuntó el ZIP correcto. Si es un centro nuevo o dado de baja, comuníquese con la OIIS."
        )
    elif desconocidos:
        res['nota'] = (f"El ZIP trae código(s) que no existen en el catálogo de centros: {desc_txt}. Revisar.").replace('**', '').replace('`', '')
    return res


class _ArchivoEnMemoria:
    """Mínimo de un archivo subido (read/name) para reutilizar procesar_envio con un ZIP generado."""
    def __init__(self, contenido: bytes, nombre: str):
        self._c, self.name = contenido, nombre
    def read(self):
        return self._c
    def seek(self, *_):
        pass


def procesar_envio(nombres, apellidos, correo, red, centros, ano, semana, tipos, archivo, info_zip, estado_envio,
                   es_duplicado=False, duplicado_info=None, plan=None, sustento="", reemplazar=False):
    """
    Procesa el envio del reporte: sube el archivo a Drive, lo registra en la
    base de datos, envia el acuse al remitente, y deja el resultado en
    session_state para que mostrar_confirmacion() lo muestre.

    Si `es_duplicado` es True (la red repite un centro ya enviado esta
    semana y el usuario lo confirmó), el archivo se guarda en la carpeta de
    duplicados de Drive, el registro queda marcado como duplicado y el acuse
    es naranja. No reemplaza ni altera el envío original.

    `plan` (de clasificar_envio): si el ZIP mezcla centros/tipos nuevos con
    otros ya recibidos (modo 'dividir'), el ZIP se parte en dos: lo nuevo se
    registra como envío normal y lo repetido como duplicado (un solo acuse
    al remitente, que explica ambas partes).

    `reemplazar=True` (solo con un plan que lo permita): el ZIP completo se registra como envío
    normal y los archivos anteriores de esos centros/tipos pasan a la carpeta REEMPLAZADOS.

    `sustento`: texto opcional de quien envía (hasta 1000 caracteres) que se guarda para el módulo
    «Observaciones» del panel.
    """
    try:
        sustento = limpiar_texto(sustento)
        semanas_validas = obtener_semanas_disponibles_por_anio(ano)
        if info_zip:
            from src.zip_processor import get_zip_processor
            chequeo = get_zip_processor().validar_periodo(info_zip, semana, ano, semanas_validas)
            if not chequeo['ok']:
                # Defensa en el servidor: aunque el formulario ya lo bloquea, nunca se acepta.
                st.error(chequeo['mensaje'])
                return

        chequeo_red = validar_red_zip(info_zip, red)
        if not chequeo_red['ok']:
            st.error(chequeo_red['mensaje'])
            return
        nota_red = [chequeo_red['nota']] if chequeo_red['nota'] else []

        mapa = _mapa_centros_por_codigo(red)
        plan = plan or {}
        huellas = plan.get('huellas') or []

        if reemplazar:
            if plan.get('modo') not in ('dividir', 'todo_duplicado') or not plan.get('reemplazo_posible'):
                st.error(plan.get('reemplazo_motivo') or "No se puede reemplazar: los archivos anteriores no se pueden identificar.")
                return
            nombres_archivos = [d['archivo'] for d in (info_zip or {}).get('archivos_detalle', [])]
            notas_h = _notas_huellas(huellas, nombres_archivos)
            codigos_ant = [it['envio'].get('codigo_seguimiento') or obtener_codigo_seguimiento(it['envio'].get('id'))
                           for it in plan['reemplazo_items'].values()]
            resumen_pares = sorted({f"{p[0].upper()} · {_TIPO_DE_LETRA.get(p[1], p[1])}"
                                    for it in plan['reemplazo_items'].values() for p in it['pares']})
            nota_rep = (f"Este envío reemplazó archivos del/los envío(s) {', '.join(str(c) for c in codigos_ant)} "
                        f"({'; '.join(resumen_pares)}); los originales quedaron en la carpeta REEMPLAZADOS.")
            datos = _registrar_envio_unico(
                nombres, apellidos, correo, red, centros, ano, semana, tipos, archivo, info_zip, estado_envio,
                es_duplicado=False, duplicado_info=None,
                detalle_archivos=_detalle_para_bd(info_zip, mapa),
                notas=[nota_rep] + nota_red + notas_h, forzar_observado=bool(nota_red or notas_h),
                sustento=sustento, es_reemplazo=True, detalle_observacion=nota_rep)
            datos['reemplazo'] = _aplicar_reemplazo(plan, datos, red, ano, semana, nombres, apellidos, correo, mapa)

        elif plan.get('modo') == 'dividir':
            from src.zip_processor import get_zip_processor
            zp = get_zip_processor()
            contenido = archivo.read()
            codigos_red = list(mapa.keys())
            nombre_zip = getattr(archivo, 'name', 'envio.zip')

            bytes_dup = zp.dividir_zip(contenido, plan['repetidos'])
            bytes_nue = zp.dividir_zip(contenido, plan['nuevos'])
            info_dup = zp.validar_zip(bytes_dup, nombre_zip, codigos_centros=codigos_red)
            info_nue = zp.validar_zip(bytes_nue, nombre_zip, codigos_centros=codigos_red)

            tipos_dup = plan['tipos_repetidos'] or list(tipos)
            centros_dup = plan['centros_repetidos'] or list(centros)
            centros_nue = list(plan['centros_nuevos'])
            if plan.get('sin_verificar'):   # centro desconocido: se respeta lo que declaró el remitente
                centros_nue = sorted(set(centros_nue) | (set(centros) - set(plan['centros_repetidos'])))
            tipos_nue = plan['tipos_nuevos'] or list(tipos)

            datos_dup = _registrar_envio_unico(
                nombres, apellidos, correo, red, centros_dup, ano, semana, tipos_dup,
                _ArchivoEnMemoria(bytes_dup, nombre_zip), info_dup, estado_envio,
                es_duplicado=True, duplicado_info=plan.get('duplicado_info'),
                detalle_archivos=_detalle_para_bd(info_dup, mapa), enviar_acuse=False)

            nota = (
                f"Este ZIP traía además {len(plan['repetidos'])} archivo(s) de centro/tipo ya recibidos "
                f"esta semana ({'; '.join(sorted(set(plan['detalle_repetido'])))}): se guardaron como "
                f"duplicado, código {datos_dup['codigo']}."
            )
            notas_h = _notas_huellas(huellas, [d['archivo'] for d in info_nue.get('archivos_detalle', [])])
            datos = _registrar_envio_unico(
                nombres, apellidos, correo, red, centros_nue, ano, semana, tipos_nue,
                _ArchivoEnMemoria(bytes_nue, nombre_zip), info_nue, estado_envio,
                es_duplicado=False, duplicado_info=None,
                detalle_archivos=_detalle_para_bd(info_nue, mapa),
                notas=[nota] + nota_red + notas_h, forzar_observado=bool(nota_red or notas_h),
                sustento=sustento)
            datos['parte_duplicada'] = {
                'codigo': datos_dup['codigo'],
                'archivos': len(plan['repetidos']),
                'detalle': sorted(set(plan['detalle_repetido'])),
                'codigos_previos': datos_dup.get('codigos_previos', []),
            }
        else:
            nombres_archivos = [d['archivo'] for d in (info_zip or {}).get('archivos_detalle', [])]
            notas_h = _notas_huellas(huellas, nombres_archivos)
            datos = _registrar_envio_unico(
                nombres, apellidos, correo, red, centros, ano, semana, tipos, archivo, info_zip, estado_envio,
                es_duplicado=es_duplicado, duplicado_info=duplicado_info,
                detalle_archivos=_detalle_para_bd(info_zip, mapa),
                notas=nota_red + notas_h, forzar_observado=bool(nota_red or notas_h),
                sustento=sustento)

        datos['sustento'] = sustento
        st.session_state.usuario_envio_exitoso = True
        st.session_state.usuario_datos_envio = datos
        st.rerun()

    except Exception as e:
        # El traceback completo (rutas internas, nombres de variables,
        # posibles fragmentos de configuración) va SOLO al log del
        # servidor -- nunca a la pantalla de un remitente anónimo y no
        # autenticado. El usuario recibe un mensaje genérico y, si el
        # envío ya alcanzó a registrarse en la base de datos antes de
        # fallar (p. ej. el correo de acuse), se le indica igual.
        logger.exception("Error al procesar el envío del reporte")
        try:
            db_manager = get_db_manager()
            db_manager.registrar_log(
                usuario=correo or 'DESCONOCIDO',
                accion='ERROR_ENVIO',
                detalle=f"Excepción al procesar el envío: {str(e)}"
            )
        except Exception:
            pass
        st.error(
            "Ocurrió un error inesperado al procesar su envío. "
            "Por favor, intente nuevamente. Si el problema persiste, "
            "comuníquese con el administrador del sistema."
        )


def _alertas_admin_activas() -> bool:
    """Correos de alerta a los administradores: apagados por defecto (Configuración → alertas por correo)."""
    try:
        return str(get_db_manager().obtener_configuracion('alertas_correo_admin') or '').strip().lower() == 'true'
    except Exception:
        return False


def _reemplazar_un_envio(old: Dict, pares: set, ctx: Dict) -> Dict:
    """
    Aparta de la carpeta principal lo que un envío nuevo reemplaza (sin borrar nada) y actualiza el registro
    del envío anterior. Lanza la excepción si algo falla (Drive sin permiso, archivo ilegible…); el llamador la
    informa. `ctx`: red, semana, ano, codigo_nuevo, hora, correo, nombres, apellidos.
    Devuelve {'codigo', 'detalle', 'parcial', 'avisado'}.
    """
    from src.zip_processor import get_zip_processor
    from src.repositorio import Repositorio
    zp = get_zip_processor()
    db = get_db_manager()
    drive = get_drive_manager()
    red, semana, ano = ctx['red'], ctx['semana'], ctx['ano']
    codigo_nuevo, hora = ctx['codigo_nuevo'], ctx['hora']
    correo, nombres, apellidos = ctx['correo'], ctx['nombres'], ctx['apellidos']
    raiz = Config.GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID or None
    carpeta = f"{red}/SEMANA_{semana}_{ano}" if raiz else f"REEMPLAZADOS/{red}/SEMANA_{semana}_{ano}"
    sello = hora.strftime('%d/%m/%Y %H:%M')
    cod_old = old.get('codigo_seguimiento') or obtener_codigo_seguimiento(old.get('id'))
    avisado = False
    detalle_old = [d for d in (old.get('detalle_archivos') or []) if isinstance(d, dict)]
    quitar = [d for d in detalle_old if (_clave_centro(d.get('centro')), _letra_tipo(d.get('tipo'))) in pares]
    quedan = [d for d in detalle_old if d not in quitar]
    etiqueta = sorted({f"{str(d.get('centro') or '').upper()} · {_TIPO_DE_LETRA.get(_letra_tipo(d.get('tipo')), '')}" for d in quitar})
    ruta_old = str(old.get('ruta_zip') or '')
    carpeta_old, _, nombre_old = ruta_old.rpartition('/')
    nuevo_id = None

    if quedan:
        # Parcial: hace falta el ZIP original para armar el de lo que sigue vigente.
        contenido, motivo = Repositorio()._leer_archivo(old)
        if contenido is None:
            raise RuntimeError(motivo or "No se pudo leer el ZIP anterior.")
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            nombres_quedan = {os.path.basename(d.get('archivo') or '') for d in quedan}
            incluir = [n for n in zf.namelist() if os.path.basename(n) in nombres_quedan]
        recortado = zp.dividir_zip(contenido, incluir)
        nombre_nuevo = f"{os.path.splitext(nombre_old or 'envio.zip')[0]}_VIGENTE.zip"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp.write(recortado)
            ruta_tmp = tmp.name
        try:
            subido = drive.subir_archivo(ruta_local=ruta_tmp, nombre_archivo=nombre_nuevo,
                                         carpeta_destino=carpeta_old or f"{red}/SEMANA_{semana}_{ano}")
        finally:
            try:
                os.unlink(ruta_tmp)
            except Exception:
                pass
        nuevo_id = subido['id']
        try:
            mov = drive.mover_a_ruta(old['drive_file_id'], carpeta, raiz)
        except Exception:
            try:                                    # deshacer: no dejar dos ZIP vigentes
                drive.eliminar_archivo(nuevo_id)
            except Exception:
                pass
            raise
        nombres_centros = {_clave_centro(d.get('centro')) for d in quedan if d.get('centro')}
        centros_old = [c for c in (old.get('centros') or [])
                       if not nombres_centros or _clave_centro(c.get('nombre', '') if isinstance(c, dict) else c) in nombres_centros]
        tipos_old = [t for t in ('Consulta Externa', 'Hospitalizacion', 'Emergencia')
                     if _LETRA_DE_TIPO.get(t.lower()) in {_letra_tipo(d.get('tipo')) for d in quedan}]
        nota = (f"Parte reemplazada por el envío {codigo_nuevo} el {sello} ({'; '.join(etiqueta)}). "
                f"El ZIP original completo quedó en la carpeta REEMPLAZADOS.")
        obs = f"{old.get('observacion')} | {nota}" if old.get('observacion') else nota
        campos = {
            'drive_file_id': nuevo_id, 'ruta_zip': f"{carpeta_old}/{nombre_nuevo}" if carpeta_old else nombre_nuevo,
            'cantidad_archivos': len(quedan), 'detalle_archivos': quedan,
            'centros': centros_old, 'tipo_reporte': tipos_old or old.get('tipo_reporte'), 'observacion': obs,
        }
    else:
        mov = drive.mover_a_ruta(old['drive_file_id'], carpeta, raiz)
        nota = (f"{PREFIJO_REEMPLAZADO} · reemplazado por el envío {codigo_nuevo} el {sello}. "
                f"El archivo original quedó en la carpeta REEMPLAZADOS.")
        campos = {'drive_file_id': mov['id'], 'ruta_zip': f"{carpeta}/{nombre_old}" if nombre_old else carpeta,
                  'observacion': f"{nota} | {old.get('observacion')}" if old.get('observacion') else nota}

    if not db.actualizar_campos_envio(old['id'], campos):
        raise RuntimeError("El archivo se movió, pero no se pudo actualizar el registro del envío anterior.")

    # Aviso a quien envió lo anterior (no a los administradores). Si es la misma persona, no hace falta.
    mismo = str(old.get('correo_usuario') or '').strip().lower() == str(correo or '').strip().lower()
    if EMAIL_DISPONIBLE and old.get('correo_usuario') and not mismo:
        try:
            ok_mail, _ = get_email_sender().enviar_aviso_reemplazo(
                destinatario=old['correo_usuario'],
                nombre_usuario=f"{old.get('nombre_usuario', '')} {old.get('apellido_usuario', '')}".strip(),
                red=red, semana=semana, anio=ano, codigo_anterior=cod_old, codigo_nuevo=codigo_nuevo,
                detalle=etiqueta, reemplazado_por=f"{nombres} {apellidos}".strip(), fecha_envio=hora)
            avisado = bool(ok_mail)
        except Exception as e:
            logger.warning("No se pudo avisar del reemplazo a %s: %s", old.get('correo_usuario'), e)
    return {'codigo': cod_old, 'detalle': etiqueta, 'parcial': bool(quedan), 'avisado': avisado}


def _aplicar_reemplazo(plan: Dict, datos_nuevo: Dict, red: str, ano: int, semana: int, nombres: str,
                       apellidos: str, correo: str, mapa: Dict) -> Dict:
    """
    Con el envío nuevo ya registrado, retira de la carpeta principal lo que reemplaza SIN borrar nada:
      · envío anterior reemplazado por completo -> su ZIP se mueve a REEMPLAZADOS y el registro queda
        marcado «ENVÍO REEMPLAZADO» (deja de contar);
      · reemplazo parcial -> el ZIP original completo se mueve a REEMPLAZADOS y en su lugar queda un ZIP
        con solo lo que sigue vigente.
    Un fallo en un envío no detiene los demás: queda como «falla técnica» en Observaciones, con datos para
    reintentarlo desde el panel (por ejemplo, cuando Drive aún no daba permiso de mover archivos).
    """
    db = get_db_manager()
    codigo_nuevo = datos_nuevo['codigo']
    ctx = {'red': red, 'semana': semana, 'ano': ano, 'codigo_nuevo': codigo_nuevo,
           'hora': datos_nuevo.get('hora_envio') or obtener_hora_local(),
           'correo': correo, 'nombres': nombres, 'apellidos': apellidos}
    res = {'reemplazados': [], 'fallos': [], 'avisos_enviados': 0}

    for it in plan['reemplazo_items'].values():
        old, pares = it['envio'], it['pares']
        cod_old = old.get('codigo_seguimiento') or obtener_codigo_seguimiento(old.get('id'))
        try:
            r = _reemplazar_un_envio(old, pares, ctx)
            res['avisos_enviados'] += 1 if r['avisado'] else 0
            res['reemplazados'].append({'codigo': r['codigo'], 'detalle': r['detalle'], 'parcial': r['parcial']})
        except Exception as e:
            logger.exception("Falló el reemplazo del envío %s", cod_old)
            res['fallos'].append({'codigo': cod_old, 'motivo': f"{type(e).__name__}: {e}"})
            # Falla técnica: va a su propia pestaña del módulo Observaciones (no a la de comentarios de las redes).
            get_observaciones().registrar(
                datos_nuevo.get('envio_id'), codigo_nuevo, red, semana, ano, f"{apellidos} {nombres}".strip(), correo,
                datos_nuevo.get('estado', ''), texto='',
                detalle=(f"No se pudo apartar el envío anterior {cod_old} a la carpeta REEMPLAZADOS. {e} "
                         "Cuando se corrija el permiso, use «Reintentar» en esta pestaña."),
                es_falla=True,
                datos={'tipo': 'REEMPLAZO', 'viejo_envio_id': old.get('id'), 'codigo_viejo': cod_old,
                       'pares': sorted([list(p) for p in pares]), 'codigo_nuevo': codigo_nuevo,
                       'hora': ctx['hora'].isoformat(), 'nombres': nombres, 'apellidos': apellidos})

    # Constancia: historial y auditoría.
    try:
        detalle_aud = {'envio_nuevo': codigo_nuevo, 'reemplazados': res['reemplazados'], 'fallos': res['fallos'],
                       'red': red, 'semana': semana, 'anio': ano}
        db.registrar_log(usuario=correo, accion='ENVIO_REEMPLAZO',
                         detalle=f"Envío {codigo_nuevo} reemplazó {len(res['reemplazados'])} envío(s) anteriores"
                                 + (f"; fallaron {len(res['fallos'])}" if res['fallos'] else ""))
        from src.auditoria import get_auditoria
        get_auditoria().registrar(usuario=correo or 'REMITENTE', accion='ENVIO_REEMPLAZO', rol='REMITENTE',
                                  objeto=codigo_nuevo, detalle=detalle_aud,
                                  resultado='OK' if not res['fallos'] else 'PARCIAL')
    except Exception as e:
        logger.warning("No se pudo dejar constancia del reemplazo: %s", e)
    return res


def reintentar_reemplazo(falla: Dict, usuario: str) -> tuple:
    """
    Reintenta, desde el panel, un reemplazo que falló (fila de Observaciones de tipo falla técnica).
    Devuelve (ok, mensaje). Si sale bien, el llamador marca la falla como resuelta.
    """
    datos = falla.get('datos') or {}
    if datos.get('tipo') != 'REEMPLAZO' or not datos.get('viejo_envio_id'):
        return False, "Esta falla no se puede reintentar desde aquí."
    db = get_db_manager()
    old = db.obtener_envio(datos['viejo_envio_id'])
    if not old:
        return False, "El envío anterior ya no existe."
    from utils.duplicados import es_reemplazado as _es_rep
    if _es_rep(old):
        return True, "El envío anterior ya estaba apartado; no hacía falta reintentar."
    from datetime import datetime as _dt
    try:
        hora = _dt.fromisoformat(datos.get('hora')) if datos.get('hora') else obtener_hora_local()
    except Exception:
        hora = obtener_hora_local()
    ctx = {'red': falla.get('red'), 'semana': falla.get('semana'), 'ano': falla.get('anio'),
           'codigo_nuevo': datos.get('codigo_nuevo') or falla.get('codigo_seguimiento'), 'hora': hora,
           'correo': falla.get('correo') or '', 'nombres': datos.get('nombres', ''), 'apellidos': datos.get('apellidos', '')}
    pares = {tuple(p) for p in datos.get('pares', [])}
    try:
        r = _reemplazar_un_envio(old, pares, ctx)
    except Exception as e:
        logger.exception("Reintento de reemplazo falló")
        return False, f"{type(e).__name__}: {e}"
    try:
        from src.auditoria import get_auditoria
        get_auditoria().registrar(usuario, 'ENVIO_REEMPLAZO_REINTENTO', rol=None, objeto=ctx['codigo_nuevo'],
                                  detalle={'envio_anterior': r['codigo'], 'detalle': r['detalle']})
    except Exception:
        pass
    return True, f"Envío {r['codigo']} apartado a REEMPLAZADOS."


def _notas_huellas(huellas: List[Dict], archivos_de_la_parte: List[str]) -> List[str]:
    """Nota de observación si algún archivo de esta parte es idéntico a uno enviado en otra semana."""
    propios = {os.path.basename(a) for a in archivos_de_la_parte}
    mias = [h for h in huellas if h['archivo'] in propios]
    if not mias:
        return []
    ej = "; ".join(
        f"{h['archivo']} = semana {h['semana_previa']} (código {h['codigo_previo']})" for h in mias[:3]
    ) + (f" y {len(mias) - 3} más" if len(mias) > 3 else "")
    return [f"Posible reenvío de archivos de otra semana (contenido idéntico): {ej}. Revisar."]


def _registrar_envio_unico(nombres, apellidos, correo, red, centros, ano, semana, tipos, archivo, info_zip,
                           estado_envio, es_duplicado=False, duplicado_info=None, detalle_archivos=None,
                           notas=None, forzar_observado=False, enviar_acuse=True, sustento="",
                           es_reemplazo=False, detalle_observacion="") -> Dict:
    """
    Registra UN envío (sube a Drive, guarda en BD, acuse y alerta) y devuelve
    el dict de datos para la pantalla de confirmación. No hace st.rerun().
    Si algo falla lanza la excepción (la captura procesar_envio).
    """
    centros_limpios = [c.split(':', 1)[1] if ':' in c else c for c in centros]
    tipos_limpios = tipos
    semana_actual_sistema = Config.get_semana_actual()
    anio_actual_sistema = Config.get_anio_actual()
    hora_envio = obtener_hora_local()

    nombre_archivo = generar_nombre_archivo(
        red=red,
        semana=semana,
        centro=centros_limpios[0] if centros_limpios else "general"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
        tmp.write(archivo.read())
        ruta_temporal = tmp.name

    # Subir a Drive solo si esta disponible
    resultado_drive = {'id': 'LOCAL', 'nombre': nombre_archivo}
    carpeta_destino = f"{red}/SEMANA_{semana}_{ano}"

    # Los duplicados van a su propia carpeta: la indicada en
    # GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID o, si no se configuró, una
    # subcarpeta "DUPLICADOS" dentro de la carpeta principal.
    raiz_duplicados = (Config.GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID or None) if es_duplicado else None
    if es_duplicado:
        nombre_archivo = f"DUP_{nombre_archivo}"
        if not raiz_duplicados:
            carpeta_destino = f"DUPLICADOS/{carpeta_destino}"

    if DRIVE_DISPONIBLE:
        drive_manager = get_drive_manager()

        if len(centros_limpios) == 1:
            carpeta_destino = f"{carpeta_destino}/{centros_limpios[0]}"

        resultado_drive = drive_manager.subir_archivo(
            ruta_local=ruta_temporal,
            nombre_archivo=nombre_archivo,
            carpeta_destino=carpeta_destino,
            raiz_id=raiz_duplicados
        )

    db_manager = get_db_manager()
    estado = 'APROBADO' if info_zip and info_zip.get('estado') == 'ok' else 'OBSERVADO'
    observacion = None if info_zip and info_zip.get('estado') == 'ok' else (info_zip.get('mensaje') if info_zip else 'Sin información')

    # Archivos con extensión real (xlsx/csv/dbf) cuyo nombre no trae
    # el código del centro embebido (ej. "pc3726ii.062.csv") -- no
    # bloquean el envío ni cambian el estado, pero se anota en la
    # observación para que el admin identifique o valide el centro
    # a mano.
    archivos_sin_centro = info_zip.get('archivos_sin_centro_identificado', []) if info_zip else []
    if archivos_sin_centro:
        nota_revision = (
            f"Revisar centro manualmente en {len(archivos_sin_centro)} archivo(s) "
            f"sin código identificable en el nombre: {', '.join(archivos_sin_centro[:5])}"
            + (f" y {len(archivos_sin_centro) - 5} más" if len(archivos_sin_centro) > 5 else "")
        )
        observacion = f"{observacion} | {nota_revision}" if observacion else nota_revision

    # Archivos de nombre libre (sin tipo/semana/año legibles): se aceptan, pero
    # no se puede comprobar que sean de la semana declarada -- queda anotado.
    sin_tipo = [a for a in (info_zip.get('archivos_sin_tipo', []) if info_zip else [])
                if a not in archivos_sin_centro]
    if sin_tipo:
        nota_libre = (
            f"{len(sin_tipo)} archivo(s) con nombre libre: no se pudo validar tipo/semana/año "
            f"({', '.join(sin_tipo[:5])}" + ("…" if len(sin_tipo) > 5 else "") + ")"
        )
        observacion = f"{observacion} | {nota_libre}" if observacion else nota_libre

    for n in (notas or []):
        observacion = f"{observacion} | {n}" if observacion else n
    if forzar_observado and estado == 'APROBADO':
        estado = 'OBSERVADO'

    # Determinar si es atrasado (usar el estado_envio que ya tiene la logica correcta)
    es_atrasado = estado_envio.get('es_atrasado', False)
    dias_atraso = estado_envio.get('dias_atraso', 0)
    semanas_atraso = estado_envio.get('semanas_atraso', 0)

    # Si es atrasado, cambiar estado a ATRASADO
    if es_atrasado:
        estado = 'ATRASADO'
        mensaje_atraso = f"ENVÍO TARDÍO (Semana {semana}/{ano})"
        if semanas_atraso > 0:
            mensaje_atraso += f" - {semanas_atraso} semanas de atraso"
        if dias_atraso > 0:
            mensaje_atraso += f" - {dias_atraso} días después de la fecha de corte"

        if observacion:
            observacion = f"{mensaje_atraso} - {observacion}"
        else:
            observacion = mensaje_atraso

    codigos_previos = [e.get('codigo_seguimiento') for e in (duplicado_info or {}).get('envios', [])]
    if es_duplicado:
        # Un duplicado no cuenta como envío tardío ni a tiempo: queda
        # "observado" para que la OIIS lo revise, con el detalle en la observación.
        observacion = observacion_duplicado(codigos_previos, tardio=es_atrasado, extra=observacion or "")
        estado = 'OBSERVADO'
        es_atrasado = False
        dias_atraso = 0
        semanas_atraso = 0

    envio_id = db_manager.registrar_envio(
        nombre_usuario=nombres,
        apellido_usuario=apellidos,
        correo_usuario=correo,
        red=red,
        centros=centros_limpios,
        semana=semana,
        tipo_reporte=tipos_limpios,
        ruta_zip=f"{carpeta_destino}/{nombre_archivo}",
        drive_file_id=resultado_drive['id'],
        cantidad_archivos=info_zip.get('cantidad', 0) if info_zip else 0,
        estado=estado,
        observacion=observacion,
        anio=ano,
        es_atrasado=es_atrasado,
        # Contexto real del momento del envío (no se debe recalcular
        # despues con la configuracion vigente en ese momento futuro):
        semana_activa_envio=semana_actual_sistema,
        dias_atraso_envio=dias_atraso,
        detalle_archivos=detalle_archivos
    )

    codigo = obtener_codigo_seguimiento(envio_id)

    # Módulo «Observaciones» del panel: sustento de quien envía y envíos observados, duplicados o con reemplazo.
    get_observaciones().registrar(
        envio_id, codigo, red, semana, ano, f"{apellidos} {nombres}".strip(), correo, estado,
        texto=sustento, detalle=detalle_observacion or (observacion or ""),
        es_duplicado=es_duplicado, es_reemplazo=es_reemplazo)

    # Enviar correos solo si esta disponible
    correo_enviado = None  # None = no se intentó, True/False = resultado real
    correo_error_detalle = ""

    if EMAIL_DISPONIBLE:
        email_sender = get_email_sender()

        # Obtener fecha de corte
        fecha_corte = estado_envio.get('fecha_limite')

        if enviar_acuse:
            # Antes esto se llamaba sin revisar el resultado -- si el
            # correo fallaba por dentro (credenciales SMTP, red, etc.),
            # el usuario veía "envío exitoso" igual y nadie se enteraba
            # de que el acuse nunca salió. Ahora se guarda el resultado
            # real y se deja constancia en el log.
            correo_enviado, correo_error_detalle = email_sender.enviar_acuse_recibo(
                destinatario=correo,
                nombre_usuario=f"{nombres} {apellidos}",
                red=red,
                centros=centros_limpios,
                semana=semana,
                tipos_reporte=tipos_limpios,
                cantidad_archivos=info_zip.get('cantidad', 0) if info_zip else 0,
                codigo_seguimiento=codigo,
                estado=estado,
                observacion=observacion,
                es_duplicado=es_duplicado,
                codigos_previos=codigos_previos,
                fecha_envio=hora_envio,
                semana_actual=semana_actual_sistema,
                anio_actual=anio_actual_sistema,
                anio=ano,
                fecha_corte=fecha_corte,
                dias_atraso=dias_atraso,
                sustento=sustento
            )

            if not correo_enviado:
                db_manager.registrar_log(
                    usuario=correo,
                    accion='ERROR_ACUSE_RECIBO',
                    detalle=f"No se pudo enviar el acuse de recibo - Código: {codigo} - Motivo: {correo_error_detalle}"
                )

        # Desde la v7.0 las alertas por correo a los administradores están apagadas por defecto: lo que
        # requiere revisión aparece en el módulo «Observaciones» del panel. Se pueden reactivar en Configuración.
        if (es_atrasado or estado == 'OBSERVADO' or es_duplicado) and _alertas_admin_activas():
            email_sender.enviar_alerta_admin(
                nombre_usuario=f"{nombres} {apellidos}",
                correo_usuario=correo,
                red=red,
                centros=centros_limpios,
                semana=semana,
                observacion=observacion,
                es_atrasado=es_atrasado,
                semana_actual=semana_actual_sistema,
                anio_actual=anio_actual_sistema,
                anio=ano,
                es_duplicado=es_duplicado,
                codigos_previos=codigos_previos,
                codigo_seguimiento=codigo
            )
    else:
        correo_error_detalle = "El envío de correos no está disponible en este sistema."

    db_manager.registrar_log(
        usuario=correo,
        accion='ENVIO_DUPLICADO' if es_duplicado else 'ENVIO',
        detalle=f"{'Envío duplicado' if es_duplicado else 'Envío exitoso'} - Código: {codigo} - Estado: {estado} - Semana: {semana}/{ano} - Atrasado: {'Sí' if es_atrasado else 'No'} - Fecha: {hora_envio.strftime('%d/%m/%Y %H:%M:%S')}"
    )

    try:
        os.unlink(ruta_temporal)
    except Exception:
        pass

    return {
        'nombres': nombres,
        'apellidos': apellidos,
        'correo': correo,
        'red': red,
        'centros': centros_limpios,
        'ano': ano,
        'semana': semana,
        'tipos': tipos_limpios,
        'codigo': codigo,
        'estado': estado,
        'observacion': observacion,
        'cantidad_archivos': info_zip.get('cantidad', 0) if info_zip else 0,
        'es_atrasado': es_atrasado,
        'dias_atraso': dias_atraso,
        'semanas_atraso': semanas_atraso,
        'fecha_limite': estado_envio.get('fecha_limite'),
        'hora_envio': hora_envio,
        'correo_enviado': correo_enviado,
        'correo_error_detalle': correo_error_detalle,
        'es_duplicado': es_duplicado,
        'codigos_previos': codigos_previos,
        'envio_id': envio_id,
    }


# ============================================================
# AVANCE DE UNA RED EN LA SEMANA ACTIVA
# ============================================================

def _lista_centros_red(red: str, excluidos_red: list) -> list:
    """Centros de la red que siguen activos (sin los excluidos por el administrador)."""
    centros_db = obtener_centros_con_red_por_red(red) or []
    activos = []
    for c in centros_db:
        nombre = c.get('centro_nombre', '')
        etiqueta = formatear_centro_desde_dict(c)
        excluido = False
        for ex in excluidos_red:
            ex_nombre = extraer_nombre_limpio(ex)
            if nombre and ex_nombre and nombre.lower() == ex_nombre.lower():
                excluido = True
                break
            if etiqueta.lower() == ex.lower():
                excluido = True
                break
        if not excluido:
            activos.append(c)
    return activos


@st.cache_data(ttl=15, show_spinner=False)
def calcular_avance_red(red: str, anio: int, semana: int):
    """
    Avance de una red en la semana activa: centros que ya enviaron y
    centros pendientes (sin contar los excluidos por el administrador).

    Se guarda 15 s en cache porque el formulario se vuelve a dibujar con
    cada campo que se escribe y no hace falta consultar la base cada vez.
    Devuelve None si no se pudo calcular.
    """
    try:
        excluidos_red = (obtener_centros_excluidos() or {}).get(red, [])
        activos = _lista_centros_red(red, excluidos_red)
        if not activos:
            return {'total': 0, 'enviados': [], 'pendientes': [], 'excluidos': len(excluidos_red)}

        envios = get_db_manager().obtener_envios(anio=anio, semana=semana, red=red, limit=1000)

        # En la tabla envios los centros se guardan como "CODIGO NOMBRE" y en
        # centros_con_red solo como "NOMBRE"; se comparan por nombre limpio.
        nombres_enviados = set()
        for envio in envios or []:
            centros_envio = envio.get('centros', [])
            if isinstance(centros_envio, list):
                for c in centros_envio:
                    nombre = c.get('nombre', str(c)) if isinstance(c, dict) else extraer_nombre_limpio(str(c))
                    nombres_enviados.add(nombre.lower())

        enviados, pendientes = [], []
        for c in activos:
            nombre = (c.get('centro_nombre', '') or '').strip()
            etiqueta = formatear_centro_desde_dict(c)
            (enviados if nombre and nombre.lower() in nombres_enviados else pendientes).append(etiqueta)
        return {
            'total': len(activos),
            'enviados': sorted(enviados),
            'pendientes': sorted(pendientes),
            'excluidos': len(excluidos_red),
        }
    except Exception:
        return None
