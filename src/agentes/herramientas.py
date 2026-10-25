# src/agentes/herramientas.py
"""
"Herramientas" de SOLO LECTURA que usan los 3 agentes de IA para consultar
el estado real del sistema.

Reutilizan las MISMAS funciones que ya usa la pantalla "Progreso por Red"
(pages/admin_progreso.py) para calcular cumplimiento, de modo que los
números que reporta un agente coincidan siempre con lo que el
administrador ve en pantalla -- nunca se recalculan por separado y el
modelo NUNCA calcula nada (Riesgo 4 del informe).

Estas funciones se le pasan a Gemini como "tools" para function-calling
automático. Por eso cada función tiene un docstring claro (Gemini lo usa
para decidir cuándo llamarla) y solo recibe/devuelve tipos simples.

GOBERNANZA DE DATOS (Ley N.° 29733 / Tabla 5.1 fila 4)
------------------------------------------------------
Todo lo que devuelven estas funciones viaja al proveedor externo (Google).
Por eso aquí se aplica el principio de MENOR PRIVILEGIO y de DATOS
AGREGADOS:

  * Nunca se devuelven campos personales del remitente de un envío
    (nombre_usuario, apellido_usuario, correo_usuario), ni IPs, ni rutas de
    archivos, ni ids de Drive, ni texto libre (observacion).
  * Las listas se construyen con LISTA BLANCA de campos (no "quitar lo
    malo", sino "dejar pasar solo lo necesario") y luego pasan por
    `guardrails.sanitizar_para_modelo` como segunda barrera.
  * Los nombres de redes y centros asistenciales son información
    institucional pública, no datos personales, y sí se devuelven.
  * Los límites (`limit`) que el modelo puede pedir se acotan.
"""

from typing import Dict, List, Optional

from src.config import Config
from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from src.agentes import guardrails
from app_pages.admin_progreso import (
    obtener_centros_excluidos,
    obtener_centros_por_red,
    calcular_porcentaje_cumplimiento,
    formatear_centro,
)

_LIMITE_MAXIMO = 200


def _acotar(limit: Optional[int], por_defecto: int) -> int:
    try:
        n = int(limit) if limit is not None else por_defecto
    except (TypeError, ValueError):
        n = por_defecto
    return max(1, min(n, _LIMITE_MAXIMO))


def _solo_fecha(valor) -> Optional[str]:
    """'2026-09-21T14:03:11+00:00' -> '2026-09-21' (la hora exacta no aporta al agente)."""
    if not valor:
        return None
    return str(valor)[:10]


def _nombres_centros(centros) -> List[str]:
    return [formatear_centro(c) for c in (centros or [])]


# ============================================================
# HERRAMIENTAS
# ============================================================

def listar_redes() -> List[str]:
    """Devuelve la lista de todas las redes asistenciales registradas en el sistema."""
    return guardrails.sanitizar_para_modelo(get_data_loader().obtener_redes())


def info_semana_actual() -> Dict:
    """
    Devuelve el año epidemiológico activo, la semana activa actual y la
    fecha límite (fecha de corte) configurada para los envíos de la semana
    en curso.
    """
    db = get_db_manager()
    anio_activo = db.obtener_anio_activo_epidemiologico()
    anio = anio_activo['anio'] if anio_activo else Config.get_anio_actual()
    try:
        semana_activa = int(db.obtener_configuracion('semana_activa') or Config.get_semana_actual())
    except (TypeError, ValueError):
        semana_activa = Config.get_semana_actual()

    return {
        'anio': anio,
        'semana_activa': semana_activa,
        'fecha_corte': Config.get_fecha_corte(),
    }


def progreso_de_una_red(
    red: str,
    anio: Optional[int] = None,
    semana: Optional[int] = None
) -> Dict:
    """
    Calcula el porcentaje de cumplimiento de una red asistencial para una
    semana: cuántos de sus centros/establecimientos ya enviaron su reporte
    y cuáles faltan. Si no se indican año/semana, usa la semana activa
    actual del sistema. Devuelve solo indicadores agregados (sin datos de
    personas).

    Args:
        red: nombre exacto de la red (ver listar_redes).
        anio: año epidemiológico. Opcional.
        semana: número de semana epidemiológica. Opcional.
    """
    db = get_db_manager()

    if anio is None or semana is None:
        info = info_semana_actual()
        anio = anio if anio is not None else info['anio']
        semana = semana if semana is not None else info['semana_activa']

    centros_excluidos = obtener_centros_excluidos()
    total_centros = obtener_centros_por_red(red, centros_excluidos)

    envios = db.obtener_envios(anio=anio, semana=semana, red=red, limit=2000)
    excluidos_red = centros_excluidos.get(red, [])

    centros_enviados = set()
    for envio in envios:
        for centro in envio.get('centros', []) or []:
            if isinstance(centro, dict):
                nombre = centro.get('nombre', str(centro))
            else:
                nombre = str(centro)
            centro_str = formatear_centro(centro)
            if nombre not in excluidos_red and centro_str not in excluidos_red:
                centros_enviados.add(centro_str)

    recibidos = len(centros_enviados)
    porcentaje = calcular_porcentaje_cumplimiento(recibidos, total_centros)

    todos_los_centros = {
        formatear_centro(c) for c in get_data_loader().obtener_centros(red)
    }
    faltantes = sorted(todos_los_centros - centros_enviados - set(excluidos_red))

    return guardrails.sanitizar_para_modelo({
        'red': red,
        'anio': anio,
        'semana': semana,
        'total_centros': total_centros,
        'recibidos': recibidos,
        'porcentaje': porcentaje,
        'centros_faltantes': faltantes,
    })


def progreso_de_todas_las_redes(
    anio: Optional[int] = None,
    semana: Optional[int] = None
) -> List[Dict]:
    """
    Calcula el porcentaje de cumplimiento de TODAS las redes para una
    semana (ver progreso_de_una_red), ordenadas de menor a mayor
    cumplimiento -- las redes más atrasadas aparecen primero.
    """
    redes = get_data_loader().obtener_redes()
    resultado = [progreso_de_una_red(red, anio, semana) for red in redes]
    resultado.sort(key=lambda r: r['porcentaje'])
    return resultado


def envios_atrasados_semana_activa(limit: int = 100) -> List[Dict]:
    """
    Devuelve los envíos que llegaron TARDE durante la semana activa actual
    (los atrasos "frescos" que tiene sentido perseguir hoy), de forma
    AGREGADA por red: red, de qué semana era el reporte, cuántos días de
    atraso tuvo, qué centros incluía y la fecha (sin hora) del envío.
    No incluye datos del remitente.
    """
    db = get_db_manager()
    info = info_semana_actual()
    crudos = db.obtener_envios_atrasados(
        info['semana_activa'], limit=_acotar(limit, 100), anio=info['anio']
    )
    # LISTA BLANCA de campos: nada del remitente, ni rutas, ni ids de Drive.
    limpios = [
        {
            'red': e.get('red'),
            'anio': e.get('anio'),
            'semana_reporte': e.get('semana'),
            'dias_atraso': e.get('dias_atraso_envio', 0),
            'fecha_envio': _solo_fecha(e.get('fecha_envio')),
            'estado': e.get('estado'),
            'cantidad_centros': len(e.get('centros') or []),
            'centros': _nombres_centros(e.get('centros')),
        }
        for e in crudos
    ]
    return guardrails.sanitizar_para_modelo(limpios)


def resumen_general_sistema() -> Dict:
    """
    Totales generales del sistema: cantidad de envíos registrados, de
    administradores activos, de carpetas de Drive configuradas y de
    registros en el historial.
    """
    r = get_db_manager().obtener_resumen_general()
    return guardrails.sanitizar_para_modelo({
        'total_envios': r.get('total_envios', 0),
        'total_admins': r.get('total_admins', 0),
        'total_carpetas': r.get('total_carpetas', 0),
        'total_logs': r.get('total_logs', 0),
    })


def historial_reciente(limite: int = 30) -> List[Dict]:
    """
    Últimas acciones registradas en el historial del sistema (qué tipo de
    acción y cuándo), para describir la actividad reciente. No incluye
    identidad de los operadores ni direcciones IP.
    """
    logs = get_db_manager().obtener_logs(limit=_acotar(limite, 30))
    limpios = [
        {
            'fecha': _solo_fecha(l.get('fecha')),
            'accion': l.get('accion'),
            'detalle': guardrails.redactar_pii(str(l.get('detalle') or ''))[:120],
        }
        for l in logs
    ]
    return guardrails.sanitizar_para_modelo(limpios)


# ============================================================
# HERRAMIENTAS NUEVAS DE SIREA (sobre SIRE v6)
# ============================================================

def _semana_y_anio(anio: Optional[int], semana: Optional[int]):
    if anio is None or semana is None:
        info = info_semana_actual()
        anio = anio if anio is not None else info['anio']
        semana = semana if semana is not None else info['semana_activa']
    return int(anio), int(semana)


def duplicados_de_red(red: str, anio: Optional[int] = None, semana: Optional[int] = None) -> Dict:
    """Envíos registrados como DUPLICADOS de una red en una semana (cuántos y qué centros)."""
    from utils.duplicados import es_duplicado
    anio, semana = _semana_y_anio(anio, semana)
    envios = get_db_manager().obtener_envios(anio=anio, semana=semana, red=red, limit=2000) or []
    dup = [e for e in envios if es_duplicado(e)]
    return guardrails.sanitizar_para_modelo({
        'red': red, 'anio': anio, 'semana': semana, 'cantidad_duplicados': len(dup),
        'detalle': [{'fecha': _solo_fecha(e.get('fecha_envio')), 'centros': _nombres_centros(e.get('centros')),
                     'estado': e.get('estado')} for e in dup[:20]],
    })


def centros_excluidos_de_red(red: str) -> Dict:
    """Centros de una red que NO se cuentan en el cumplimiento (exclusiones por casos excepcionales) y su motivo."""
    db = get_db_manager()
    filas = db.obtener_centros_excluidos_por_red(red) or []
    detalle = []
    try:
        info = db.obtener_red_por_nombre(red)
        if info:
            for f in db.obtener_centros_excluidos(red_id=info.get('id')) or []:
                detalle.append({'centro': f.get('centro_nombre'),
                                'motivo': guardrails.redactar_pii(str(f.get('motivo') or ''))[:120],
                                'desde': _solo_fecha(f.get('fecha_exclusion'))})
    except Exception:
        pass
    return guardrails.sanitizar_para_modelo({'red': red, 'cantidad_excluidos': len(filas),
                                             'centros_excluidos': detalle or [{'centro': c} for c in filas]})


def envios_tardios_de_red(red: str, anio: Optional[int] = None, semana: Optional[int] = None) -> Dict:
    """Envíos de una red recibidos DESPUÉS de la fecha de corte en una semana: cuántos, días de atraso y centros."""
    from utils.duplicados import solo_originales
    anio, semana = _semana_y_anio(anio, semana)
    envios = solo_originales(get_db_manager().obtener_envios(anio=anio, semana=semana, red=red, limit=2000) or [])
    tard = [e for e in envios if e.get('es_atrasado') or (e.get('dias_atraso_envio') or 0) > 0]
    return guardrails.sanitizar_para_modelo({
        'red': red, 'anio': anio, 'semana': semana, 'cantidad_tardios': len(tard), 'cantidad_envios': len(envios),
        'detalle': [{'fecha': _solo_fecha(e.get('fecha_envio')), 'dias_atraso': e.get('dias_atraso_envio') or 0,
                     'centros': _nombres_centros(e.get('centros'))} for e in tard[:20]],
    })


def solicitudes_abiertas() -> List[Dict]:
    """Solicitudes de cambio de contraseña de las redes que están abiertas (pendientes o aprobadas sin usar). Sin datos de personas."""
    try:
        from src.solicitudes_password import get_solicitudes_password
        filas = get_solicitudes_password().listar(estados=['PENDIENTE', 'APROBADA'], limit=100) or []
    except Exception:
        return []
    return guardrails.sanitizar_para_modelo([
        {'red': f.get('red'), 'estado': f.get('estado'), 'creada': _solo_fecha(f.get('fecha_creacion') or f.get('created_at'))}
        for f in filas
    ])


def estado_del_cierre() -> Dict:
    """Estado del último cierre de semana: qué semana se cerró, si la propuesta fue validada y si el resumen ya se envió a la entidad externa."""
    try:
        from src.cierres import get_cierres
        c = get_cierres().ultimo()
    except Exception:
        c = None
    if not c:
        return {'hay_cierre': False}
    return guardrails.sanitizar_para_modelo({
        'hay_cierre': True, 'semana_cerrada': c.get('semana_cerrada'), 'anio': c.get('anio'),
        'estado_cierre': c.get('estado'), 'semana_propuesta': c.get('semana_propuesta'),
        'resumen_estado': c.get('resumen_estado'), 'fecha': _solo_fecha(c.get('creado_at') or c.get('created_at')),
    })


def historial_de_red(red: str, limite: int = 20) -> List[Dict]:
    """Últimas acciones del historial relacionadas con una red (accesos de la red, envíos, exclusiones). Sin identidades ni IP."""
    logs = get_db_manager().obtener_logs(limit=400) or []
    r = (red or '').strip().upper()
    sel = [l for l in logs if r and (str(l.get('usuario') or '').upper() == f"RED:{r}" or r in str(l.get('detalle') or '').upper())]
    return guardrails.sanitizar_para_modelo([
        {'fecha': _solo_fecha(l.get('fecha')), 'accion': l.get('accion'),
         'detalle': guardrails.redactar_pii(str(l.get('detalle') or ''))[:120]}
        for l in sel[:_acotar(limite, 20)]
    ])


# ============================================================
# HERRAMIENTAS NUEVAS DE SIREA 3.2 (patrones, observaciones, IA)
# ============================================================

_CACHE_HIST = {"t": 0.0, "h": None}


def _historial():
    """Patrones de la semana activa (se recalculan como máximo cada 60 s durante una conversación)."""
    import time
    from src.agentes import patrones
    if _CACHE_HIST["h"] is None or time.time() - _CACHE_HIST["t"] > 60:
        _CACHE_HIST.update(t=time.time(), h=patrones.historial_semana_activa())
    return _CACHE_HIST["h"]


def faltantes_por_tipo_de_red(red: str) -> Dict:
    """Por centro de una red, qué tipos de reporte (Consulta Externa, Hospitalización, Emergencia) ya llegaron y cuáles faltan en la semana activa."""
    h = _historial()
    return guardrails.sanitizar_para_modelo({'red': red, 'anio': h.anio, 'semana': h.semana,
                                             'centros_con_pendientes': h.faltantes_por_tipo(red)[:40]})


def perfil_de_red(red: str) -> Dict:
    """Patrones de envío de una red en las últimas semanas (calculados por el sistema): semanas tarde, tipo que suele faltar, tendencia."""
    p = _historial().perfil(red)
    claves = ('red', 'semanas_analizadas', 'hay_datos_suficientes', 'semanas_tarde', 'semanas_sin_envio', 'semanas_a_tiempo',
              'lista_semanas_tarde', 'lista_semanas_sin_envio', 'suele_atrasarse', 'tipo_que_suele_faltar', 'tendencia',
              'suele_esperar_recordatorio', 'semanas_justificadas_excluidas', 'texto')
    return guardrails.sanitizar_para_modelo({k: p.get(k) for k in claves})


def panorama_semana() -> Dict:
    """Cuántas redes completaron todos sus reportes en la semana activa y cuáles tienen pendientes."""
    pan = _historial().panorama()
    return guardrails.sanitizar_para_modelo({k: pan[k] for k in ('anio', 'semana', 'redes_total', 'redes_completas',
                                                                 'redes_pendientes', 'redes_con_envio_tardio')})


def redes_con_patron_de_atraso() -> List[Dict]:
    """Redes que suelen atrasarse, que vienen empeorando o con un tipo de reporte que suele faltar (calculado por el sistema)."""
    from src.agentes import patrones
    return guardrails.sanitizar_para_modelo([{'red': p['red'], 'resumen': p['texto'], 'tendencia': p['tendencia']}
                                             for p in patrones.redes_con_patron(_historial())][:20])


def observaciones_pendientes_resumen() -> Dict:
    """Observaciones sin revisar, contadas por motivo y por red (sin textos de las redes ni datos de personas)."""
    try:
        from src.observaciones import get_observaciones
        filas = get_observaciones().listar(revisada=False, limite=500) or []
    except Exception:
        return {'disponible': False}
    por_motivo, por_red = {}, {}
    for f in filas:
        por_motivo[str(f.get('motivo'))] = por_motivo.get(str(f.get('motivo')), 0) + 1
        por_red[str(f.get('red'))] = por_red.get(str(f.get('red')), 0) + 1
    return guardrails.sanitizar_para_modelo({'total_sin_revisar': len(filas), 'por_motivo': por_motivo,
                                             'por_red': dict(sorted(por_red.items(), key=lambda x: -x[1])[:20])})


def propuestas_pendientes_del_agente() -> List[Dict]:
    """Propuestas del Agente de IA que esperan la decisión de una persona (tipo, red, semana). Sin destinatarios."""
    try:
        from src.agentes import agente_operativo as ag
        filas = ag.propuestas("PROPUESTA", 100)
    except Exception:
        return []
    return guardrails.sanitizar_para_modelo([{'tipo': f.get('tipo'), 'red': f.get('red'), 'semana': f.get('semana'),
                                              'creada': _solo_fecha(f.get('creada_at')),
                                              'justificacion': str(f.get('justificacion') or '')[:160]} for f in filas[:40]])


def actividad_ia_reciente(dias: int = 7) -> Dict:
    """Qué hizo la IA en los últimos días: propuestas, aprobadas, rechazadas, consultas e informes (cuentas del sistema)."""
    from datetime import datetime, timedelta, timezone
    dias = max(1, min(int(dias or 7), 60))
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    from src.agentes import auditoria
    filas = auditoria.obtener_registros(limite=20000, desde=desde)
    por_evento = {}
    for f in filas:
        por_evento[str(f.get('evento'))] = por_evento.get(str(f.get('evento')), 0) + 1
    try:
        from src.agentes import agente_operativo as ag
        m = ag.metricas(dias)
    except Exception:
        m = {}
    return guardrails.sanitizar_para_modelo({'dias': dias, 'registros_por_evento': por_evento,
                                             'propuestas': m.get('propuestas'), 'aprobadas': m.get('aprobadas'),
                                             'rechazadas': m.get('rechazadas'), 'pendientes': m.get('pendientes')})


# ============================================================
# REGISTRO NEUTRO (para cualquier proveedor): nombre, descripción,
# esquema JSON de parámetros y función. TODAS son de SOLO LECTURA.
# No agregar aquí ninguna función que escriba, envíe correos o cambie
# configuración.
# ============================================================

def _esq(**props) -> Dict:
    """Esquema JSON de un objeto con las propiedades indicadas (todas opcionales salvo que se marquen)."""
    requeridos = [k for k, v in props.items() if v.get('req')]
    propiedades = {k: {kk: vv for kk, vv in v.items() if kk != 'req'} for k, v in props.items()}
    out = {'type': 'object', 'properties': propiedades}
    if requeridos:
        out['required'] = requeridos
    return out


_RED = {'type': 'string', 'description': 'Nombre exacto de la red (ver listar_redes).', 'req': True}
_ANIO = {'type': 'integer', 'description': 'Año epidemiológico. Si se omite, el activo.'}
_SEM = {'type': 'integer', 'description': 'Semana epidemiológica. Si se omite, la activa.'}


def registro_herramientas():
    """Lista de `Herramienta` para el investigador (solo lectura)."""
    from src.agentes.proveedores import Herramienta as H
    return [
        H('listar_redes', 'Lista de todas las redes asistenciales registradas.', _esq(), listar_redes),
        H('info_semana_actual', 'Año activo, semana activa y fecha de corte vigente.', _esq(), info_semana_actual),
        H('progreso_de_una_red', 'Cumplimiento de una red en una semana: centros esperados, recibidos, porcentaje y centros que faltan.',
          _esq(red=_RED, anio=_ANIO, semana=_SEM), progreso_de_una_red),
        H('progreso_de_todas_las_redes', 'Cumplimiento de TODAS las redes en una semana, de menor a mayor.',
          _esq(anio=_ANIO, semana=_SEM), progreso_de_todas_las_redes),
        H('envios_atrasados_semana_activa', 'Envíos que llegaron tarde durante la semana activa, por red.',
          _esq(limit={'type': 'integer', 'description': 'Máximo de filas (hasta 200).'}), envios_atrasados_semana_activa),
        H('envios_tardios_de_red', 'Envíos tardíos de una red en una semana (días de atraso y centros).',
          _esq(red=_RED, anio=_ANIO, semana=_SEM), envios_tardios_de_red),
        H('duplicados_de_red', 'Envíos duplicados de una red en una semana.', _esq(red=_RED, anio=_ANIO, semana=_SEM), duplicados_de_red),
        H('centros_excluidos_de_red', 'Centros de una red excluidos del cumplimiento y su motivo.', _esq(red=_RED), centros_excluidos_de_red),
        H('solicitudes_abiertas', 'Solicitudes de cambio de contraseña abiertas, por red.', _esq(), solicitudes_abiertas),
        H('estado_del_cierre', 'Estado del último cierre de semana y del resumen a la entidad externa.', _esq(), estado_del_cierre),
        H('historial_de_red', 'Últimas acciones del historial relacionadas con una red.',
          _esq(red=_RED, limite={'type': 'integer', 'description': 'Máximo de filas (hasta 200).'}), historial_de_red),
        H('resumen_general_sistema', 'Totales generales del sistema.', _esq(), resumen_general_sistema),
        H('historial_reciente', 'Últimas acciones del historial del sistema (sin identidades).',
          _esq(limite={'type': 'integer', 'description': 'Máximo de filas (hasta 200).'}), historial_reciente),
        # SIREA 3.2
        H('faltantes_por_tipo_de_red', 'Por centro de una red: qué reportes (Consulta Externa, Hospitalización, Emergencia) llegaron y cuáles faltan en la semana activa.',
          _esq(red=_RED), faltantes_por_tipo_de_red),
        H('perfil_de_red', 'Patrones de envío de una red en las últimas semanas: semanas tarde, tipo que suele faltar, tendencia.',
          _esq(red=_RED), perfil_de_red),
        H('panorama_semana', 'Cuántas redes completaron todos sus reportes en la semana activa y cuáles tienen pendientes.', _esq(), panorama_semana),
        H('redes_con_patron_de_atraso', 'Redes que suelen atrasarse, que empeoran o con un tipo de reporte que suele faltar.', _esq(),
          redes_con_patron_de_atraso),
        H('observaciones_pendientes_resumen', 'Observaciones sin revisar, por motivo y por red.', _esq(), observaciones_pendientes_resumen),
        H('propuestas_pendientes_del_agente', 'Propuestas del Agente de IA que esperan la decisión de una persona.', _esq(),
          propuestas_pendientes_del_agente),
        H('actividad_ia_reciente', 'Qué hizo la IA en los últimos días (propuestas, aprobaciones, rechazos, consultas).',
          _esq(dias={'type': 'integer', 'description': 'Días hacia atrás (1 a 60).'}), actividad_ia_reciente),
    ]


# Compatibilidad con pruebas heredadas de SIGRE.
HERRAMIENTAS_CHATBOT = [listar_redes, info_semana_actual, progreso_de_una_red, progreso_de_todas_las_redes,
                        envios_atrasados_semana_activa, resumen_general_sistema, historial_reciente]
