# pages/admin_atrasos.py
"""
Control de Atrasos: filtros por semana/año, estadísticas y registros de envíos atrasados.
"""

import pandas as pd
import streamlit as st

from src.config import Config
from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from utils.helpers import sanitizar_html
from utils.tema import kpi, mostrar, aviso
from utils.tema_admin import (
    chip_estado, etiqueta_estado, tabla_df, barras_h, panel_cab, descargas,
)
from app_pages.admin_helpers import (
    formatear_centro,
    formatear_fecha_columna,
    obtener_centros_excluidos,
    requerir_admin,
)


def mostrar_control_atrasos():
    """
    Muestra el control de atrasos con filtros por año y semana,
    columnas mejoradas y calculos de dias de retraso reales.
    """
    requerir_admin()
    
    db_manager = get_db_manager()
    data_loader = get_data_loader()
    centros_excluidos = obtener_centros_excluidos()
    
    # ============================================================
    # OBTENER AÑOS DISPONIBLES DESDE CONFIGURACION
    # ============================================================
    anios_disponibles = db_manager.obtener_anios_epidemiologicos()
    if not anios_disponibles:
        mostrar(aviso("warn", "No hay años epidemiológicos configurados",
                      "Configure un año en la sección Configuración."))
        return
    
    # Obtener año activo
    anio_activo_data = db_manager.obtener_anio_activo_epidemiologico()
    anio_activo = anio_activo_data['anio'] if anio_activo_data else anios_disponibles[0]['anio']
    
    # Obtener semana activa
    semana_activa = Config.get_semana_actual()
    
    # ============================================================
    # FILTROS: AÑO Y SEMANA
    # ============================================================
    # SIREA 3.3: filtro común Año · Semana · Red
    from app_pages.filtro_periodo import filtro_periodo
    with st.container(key="panel_filtros_atrasos"):
        periodo = filtro_periodo("atr", ayuda="Se muestran los envíos tardíos registrados mientras esa semana estaba activa.")
    anio_seleccionado, semana_seleccionada = periodo.anio, periodo.semana

    # ============================================================
    # CONSULTAR ATRASOS POR AÑO Y SEMANA
    # ============================================================
    # NOTA: se filtra por semana_activa_envio (la semana que estaba
    # activa cuando se REGISTRO el envío), no por semana (de qué
    # contenido es el reporte). Así, un reporte de la semana 36 enviado
    # tarde durante la semana activa 37 aparece como atraso de la 37
    # -- que es cuando realmente ocurrió el atraso -- no de la 36.
    
    envios_atrasados = db_manager.obtener_envios(
        anio=anio_seleccionado,
        semana_activa_envio=semana_seleccionada,
        red=periodo.red,
        solo_atrasados=True,
        incluir_atrasados=True,
        limit=1000
    )
    
    # ============================================================
    # FILTRAR CENTROS EXCLUIDOS
    # ============================================================
    envios_filtrados = []
    for envio in envios_atrasados:
        red = envio.get('red', '')
        centros = envio.get('centros', [])
        if isinstance(centros, list):
            centros_filtrados = []
            for c in centros:
                centro_str = formatear_centro(c)
                if not (red in centros_excluidos and centro_str in centros_excluidos[red]):
                    centros_filtrados.append(centro_str)
            if centros_filtrados:
                envio_copy = envio.copy()
                envio_copy['centros'] = centros_filtrados
                envios_filtrados.append(envio_copy)
        else:
            centro_str = formatear_centro(centros)
            if not (red in centros_excluidos and centro_str in centros_excluidos[red]):
                envio_copy = envio.copy()
                envio_copy['centro'] = centro_str
                envios_filtrados.append(envio_copy)
    
    total_atrasos = len(envios_filtrados)
    
    # ============================================================
    # ESTADISTICAS
    # ============================================================
    redes_count = {}
    semanas_count = {}
    for envio in envios_filtrados:
        red = envio.get('red', 'Sin Red')
        redes_count[red] = redes_count.get(red, 0) + 1
        semana = envio.get('semana', 0)
        semanas_count[semana] = semanas_count.get(semana, 0) + 1
    
    dias_atraso_promedio = 0
    if envios_filtrados:
        # Se usa dias_atraso_envio (guardado en el momento del envío),
        # no un recálculo contra la fecha de corte actual: esta última
        # puede cambiar después y "desatrasar" envíos históricos que
        # sí estaban atrasados cuando ocurrieron.
        total_dias = sum(envio.get('dias_atraso_envio', 0) or 0 for envio in envios_filtrados)
        dias_atraso_promedio = round(total_dias / len(envios_filtrados), 1)
    
    # ============================================================
    # TARJETAS DE ESTADISTICAS
    # ============================================================
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        mostrar(kpi("Total de atrasos", total_atrasos, "Envíos fuera de plazo",
                    "bad" if total_atrasos else None, "reloj"))
    with col2:
        mostrar(kpi("Redes con atrasos", len(redes_count), f"De {len(data_loader.obtener_redes())} redes"))
    with col3:
        semanas_txt = ", ".join(f"S{k}" for k in sorted(semanas_count)) if semanas_count else "Sin semanas afectadas"
        mostrar(kpi("Semanas afectadas", len(semanas_count), semanas_txt))
    with col4:
        prom = f"{int(dias_atraso_promedio) if dias_atraso_promedio == int(dias_atraso_promedio) else dias_atraso_promedio} días"
        mostrar(kpi("Promedio de atraso", prom, "Por envío tardío"))

    # ============================================================
    # ATRASOS POR RED
    # ============================================================
    if envios_filtrados:
        with st.container(key="panel_atrasos_red"):
            panel_cab("Atrasos por red", "Cantidad de envíos tardíos")
            items = sorted(redes_count.items(), key=lambda kv: kv[1], reverse=True)
            mostrar(barras_h(items, "bad"))

    # ============================================================
    # TABLA DE ATRASOS MEJORADA - CON SANITIZACIÓN
    # ============================================================
    if not envios_filtrados:
        mostrar(aviso("ok", f"No hay envíos tardíos en la semana {semana_seleccionada} de {anio_seleccionado}"))
        return

    datos_tabla = []
    for envio in envios_filtrados:
        red = envio.get('red', '')
        centros = envio.get('centros', [])
        if not isinstance(centros, list):
            centros = [envio.get('centro', '—')]
        dias_retraso = envio.get('dias_atraso_envio', 0) or 0
        semana_activa_del_envio = envio.get('semana_activa_envio', 'N/A')
        fecha_envio = envio.get('fecha_envio')
        fecha_envio_str = formatear_fecha_columna(fecha_envio) if fecha_envio else '—'
        for centro in centros:
            datos_tabla.append({
                'red': sanitizar_html(str(red)),
                'centro': sanitizar_html(str(centro)),
                'nombre_usuario': sanitizar_html(str(envio.get('nombre_usuario', ''))),
                'apellido_usuario': sanitizar_html(str(envio.get('apellido_usuario', ''))),
                'fecha_envio': fecha_envio_str,
                'semana_envio': envio.get('semana', 'N/A'),
                'semana_activa': semana_activa_del_envio,
                'estado': sanitizar_html(str(envio.get('estado', 'PENDIENTE'))),
                'observacion': sanitizar_html(str(envio.get('observacion') or '')),
                'dias_retraso': dias_retraso,
                'anio': envio.get('anio', anio_seleccionado),
            })

    df_display = pd.DataFrame(datos_tabla).sort_values('dias_retraso', ascending=False)
    df_display = df_display[[
        'red', 'centro', 'nombre_usuario', 'apellido_usuario',
        'fecha_envio', 'semana_envio', 'semana_activa',
        'estado', 'observacion', 'dias_retraso', 'anio',
    ]].copy()
    df_display.columns = [
        'Red', 'Centro', 'Nombres', 'Apellidos',
        'Fecha de envío', 'Semana', 'Semana activa',
        'Estado', 'Observación', 'Días de atraso', 'Año',
    ]

    with st.container(key="panel_registros_atrasos"):
        panel_cab("Registros de atrasos",
                  f"{len(df_display)} registros · semana {semana_seleccionada} de {anio_seleccionado}")
        vista = pd.DataFrame({
            'Responsable': (df_display['Nombres'] + ' ' + df_display['Apellidos']).str.strip(),
            'Red': df_display['Red'],
            'Centro': df_display['Centro'],
            'Semana': df_display['Semana'],
            'Fecha de envío': df_display['Fecha de envío'],
            'Atraso': df_display['Días de atraso'].apply(lambda x: f"{x} días" if x else "0 días"),
            'Estado': df_display['Estado'],
        })
        mostrar(tabla_df(vista, chips={'Estado': chip_estado}, derecha=('Semana',)))

        df_export = df_display.copy()
        df_export['Estado'] = df_export['Estado'].apply(etiqueta_estado)
        descargas(df_export, f"atrasos_semana_{semana_seleccionada}_{anio_seleccionado}", "Atrasos", key="atrasos")
