# pages/admin_dashboard.py
"""
Panel de control del administrador: indicadores de la semana activa,
envíos y cumplimiento por red, y tabla de control.
"""

import pandas as pd
import streamlit as st

from src.config import Config
from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from utils.helpers import sanitizar_html
from utils.tema import kpi, mostrar, aviso
from utils.tema_admin import (
    esc, chip_estado, etiqueta_estado, chip_nivel, chip_porcentaje,
    tabla_df, tabla_html, barras_h, lista_cumplimiento, panel_cab, vacio,
    descargas,
)
from app_pages.admin_helpers import (
    formatear_centro,
    formatear_fecha_columna,
    obtener_centros_excluidos,
    requerir_admin,
)

_FILTRO_ESTADOS = {
    "Todos": None,
    "Recibido a tiempo": "APROBADO",
    "Observado": "OBSERVADO",
    "Envío tardío": "ATRASADO",
}


def _porcentaje(parte, total):
    return round(parte / total * 100) if total else 0


def mostrar_dashboard_principal():
    """Panel de control: indicadores, gráficas y tabla de la semana elegida (por defecto, la activa)."""

    requerir_admin()

    db_manager = get_db_manager()
    data_loader = get_data_loader()

    # SIREA 3.3: Año · Semana · Red (por defecto la semana activa; la elección se comparte con los demás módulos)
    from app_pages.filtro_periodo import filtro_periodo
    with st.container(key="panel_dash_filtro"):
        periodo = filtro_periodo("dash")
    semana_activa, anio_activo, red_filtro = periodo.semana, periodo.anio, periodo.red

    centros_excluidos = obtener_centros_excluidos()

    stats = db_manager.obtener_estadisticas_semana(semana_activa, incluir_atrasados=False, anio=anio_activo)
    if red_filtro:
        envios_red = [e for e in db_manager.obtener_envios(semana=semana_activa, anio=anio_activo, red=red_filtro,
                                                           incluir_atrasados=False, limit=1000)]
        por_estado = {}
        for e in envios_red:
            por_estado[e.get('estado')] = por_estado.get(e.get('estado'), 0) + 1
        stats = {**stats, 'total_envios': len(envios_red), 'aprobados': por_estado.get('APROBADO', 0),
                 'observados': por_estado.get('OBSERVADO', 0), 'envios_por_red': {red_filtro: len(envios_red)},
                 'atrasados': len([e for e in db_manager.obtener_envios_atrasados(semana_activa, limit=1000, anio=anio_activo)
                                   if e.get('red') == red_filtro])}

    total = stats.get('total_envios', 0)
    aprobados = stats.get('aprobados', 0)
    observados = stats.get('observados', 0)
    atrasados = stats.get('atrasados', 0)

    # ------------------------------------------------------------
    # Indicadores
    # ------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mostrar(kpi("Total de envíos", total, f"Semana {semana_activa} · {anio_activo}" + (f" · {red_filtro}" if red_filtro else ""),
                    None, "dash"))
    with c2:
        mostrar(kpi("Recibidos a tiempo", aprobados, f"{_porcentaje(aprobados, total)} % del total", "ok", "check"))
    with c3:
        mostrar(kpi("Observados", observados, "Requieren corrección", "warn", "alerta"))
    with c4:
        mostrar(kpi("Envíos tardíos", atrasados, "Fuera de plazo", "bad", "reloj"))

    # ------------------------------------------------------------
    # Datos de la tabla de control
    # ------------------------------------------------------------
    envios_tabla = db_manager.obtener_envios(semana=semana_activa, anio=anio_activo, red=red_filtro,
                                             incluir_atrasados=False, limit=1000)

    total_establecimientos_por_red = {}
    redes_vista = [red_filtro] if red_filtro else data_loader.obtener_redes()
    for red in redes_vista:
        centros = data_loader.obtener_centros(red)
        excluidos_red = centros_excluidos.get(red, [])
        total_establecimientos_por_red[red] = len([
            c for c in centros if formatear_centro(c) not in excluidos_red
        ])

    tiene_duplicados = False
    datos_tabla = []
    if envios_tabla:
        centros_unicos = {}
        for envio in envios_tabla:
            red = envio.get('red', '')
            centros = envio.get('centros', [])
            if isinstance(centros, list):
                for centro in centros:
                    centro_str = formatear_centro(centro)
                    if red in centros_excluidos and centro_str in centros_excluidos[red]:
                        continue
                    centros_unicos.setdefault((red, centro_str), []).append(envio)

        for (red, centro_str), envios_lista in centros_unicos.items():
            if len(envios_lista) > 1:
                tiene_duplicados = True
            envio = max(envios_lista, key=lambda e: e.get('fecha_envio', ''))
            datos_tabla.append({
                'nombres': sanitizar_html(str(envio.get('nombre_usuario', ''))),
                'apellidos': sanitizar_html(str(envio.get('apellido_usuario', ''))),
                'red': sanitizar_html(str(red)),
                'centro': sanitizar_html(str(centro_str)),
                'semana': envio.get('semana', 0),
                'tipo_reporte': sanitizar_html(', '.join(envio.get('tipo_reporte', []))),
                'fecha_envio': envio.get('fecha_envio', ''),
                'estado': sanitizar_html(str(envio.get('estado', ''))),
                'observacion': sanitizar_html(str(envio.get('observacion') or '')),
                'recibido': 1,
            })

    # (v7.0) Ya no hay cartel fijo de duplicados: se ven en «Observaciones» y «Control de duplicados».

    if not envios_tabla:
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        mostrar(aviso("info", f"No hay envíos registrados para la semana {semana_activa}/{anio_activo}"
                      + (f" de {esc(red_filtro)}" if red_filtro else ""),
                      "Cuando las redes envíen sus reportes aparecerán aquí." if periodo.es_activa
                      else "Elija otra semana o vuelva a la semana activa."))
        return

    if not datos_tabla:
        mostrar(aviso("info", "No hay datos para mostrar en la tabla"))
        return

    df_tabla = pd.DataFrame(datos_tabla)
    recibidos_por_red = df_tabla.groupby('red')['recibido'].count().reset_index(name='recibidos')
    df_tabla = df_tabla.merge(recibidos_por_red, on='red', how='left')
    df_tabla['establecimientos'] = df_tabla['red'].map(
        lambda r: total_establecimientos_por_red.get(r, 0)
    )
    df_tabla['porcentaje'] = df_tabla.apply(
        lambda row: round((row['recibidos'] / row['establecimientos']) * 100, 1)
        if row['establecimientos'] > 0 else 0,
        axis=1,
    )
    df_tabla['fecha_envio'] = df_tabla['fecha_envio'].apply(formatear_fecha_columna)

    # ------------------------------------------------------------
    # Cumplimiento por red (centros con envío / centros de la red)
    # ------------------------------------------------------------
    datos_progreso_redes = []
    for red in redes_vista:
        total_centros_red = total_establecimientos_por_red.get(red, 0)
        if total_centros_red <= 0:
            continue
        red_clave = sanitizar_html(str(red))
        df_red = df_tabla[df_tabla['red'] == red_clave]
        recibidos_red = int(df_red['recibidos'].iloc[0]) if not df_red.empty else 0
        datos_progreso_redes.append({
            'red': red_clave,
            'total': total_centros_red,
            'recibidos': recibidos_red,
            'pendientes': total_centros_red - recibidos_red,
            'porcentaje': round((recibidos_red / total_centros_red) * 100, 1),
        })
    datos_progreso_redes.sort(key=lambda d: d['porcentaje'], reverse=True)

    # ------------------------------------------------------------
    # Envíos por red y cumplimiento por red
    # ------------------------------------------------------------
    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(key="panel_envios_red"):
            panel_cab("Envíos por red", f"Semana {semana_activa}/{anio_activo} · cantidad de envíos")
            items = sorted(stats.get('envios_por_red', {}).items(), key=lambda kv: kv[1], reverse=True)
            mostrar(barras_h(items, "info"))
    with col_b:
        with st.container(key="panel_cumplimiento_red"):
            panel_cab("Cumplimiento por red", "Centros con envío sobre el total de la red")
            mostrar(lista_cumplimiento(
                [(d['red'], d['recibidos'], d['total']) for d in datos_progreso_redes[:8]]
            ))
            if len(datos_progreso_redes) > 8:
                st.caption(f"Se muestran las 8 redes con mayor cumplimiento de {len(datos_progreso_redes)}. "
                           "El resumen completo está al final de esta página.")

    # ------------------------------------------------------------
    # Tabla de control
    # ------------------------------------------------------------
    df_display = df_tabla[[
        'nombres', 'apellidos', 'red', 'centro', 'semana',
        'tipo_reporte', 'fecha_envio', 'estado', 'observacion',
        'establecimientos', 'recibidos', 'porcentaje',
    ]].copy()
    df_display.columns = [
        'Nombres', 'Apellidos', 'Red', 'Centro', 'Semana',
        'Tipo de reporte', 'Fecha de envío', 'Estado', 'Observación',
        'Establecimientos', 'Recibidos', '% Recibido',
    ]
    df_display['% Recibido'] = df_display['% Recibido'].apply(lambda x: f"{x}%")

    with st.container(key="panel_tabla_control"):
        panel_cab(f"Tabla de control · Semana {semana_activa}/{anio_activo}" + (f" · {red_filtro}" if red_filtro else ""))

        f2, f3 = st.columns(2)
        with f2:
            sel_estado = st.selectbox("Estado", list(_FILTRO_ESTADOS), key="dash_filtro_estado")
        with f3:
            buscar = st.text_input("Buscar", placeholder="Responsable o centro", key="dash_filtro_buscar")

        df_f = df_display
        estado_db = _FILTRO_ESTADOS[sel_estado]
        if estado_db:
            df_f = df_f[df_f['Estado'].astype(str).str.upper() == estado_db]
        if buscar.strip():
            q = buscar.strip().lower()
            texto = (df_f['Nombres'] + ' ' + df_f['Apellidos'] + ' ' + df_f['Centro']).str.lower()
            df_f = df_f[texto.str.contains(q, regex=False)]

        vista = pd.DataFrame({
            'Responsable': (df_f['Nombres'] + ' ' + df_f['Apellidos']).str.strip(),
            'Red': df_f['Red'],
            'Centro': df_f['Centro'],
            'Tipo de reporte': df_f['Tipo de reporte'].str.replace('Hospitalizacion', 'Hospitalización', regex=False),
            'Fecha de envío': df_f['Fecha de envío'],
            'Estado': df_f['Estado'],
            'Observación': df_f['Observación'],
        })
        if not (vista['Observación'].astype(str).str.strip() != '').any():
            vista = vista.drop(columns=['Observación'])
        mostrar(tabla_df(vista, chips={'Estado': chip_estado}, vacio="Ningún registro coincide con los filtros."))
        st.caption(f"Mostrando {len(df_f)} de {len(df_display)} registros.")

        excluidos_total = sum(len(c) for c in centros_excluidos.values())
        if excluidos_total > 0:
            st.caption(f"{excluidos_total} centros están excluidos del conteo por casos excepcionales.")

        df_export = df_display.copy()
        df_export['Estado'] = df_export['Estado'].apply(etiqueta_estado)
        descargas(df_export, f"tabla_control_semana_{semana_activa}_{anio_activo}", "Tabla de control", key="dash_tabla")

    # ------------------------------------------------------------
    # Resumen de cumplimiento por red
    # ------------------------------------------------------------
    if datos_progreso_redes:
        total_centros_global = sum(d['total'] for d in datos_progreso_redes)
        total_recibidos_global = sum(d['recibidos'] for d in datos_progreso_redes)
        pct_global = round(total_recibidos_global / total_centros_global * 100, 1) if total_centros_global else 0

        with st.container(key="panel_resumen_red"):
            panel_cab("Resumen de cumplimiento por red",
                      f"{total_recibidos_global} de {total_centros_global} centros con envío · {pct_global} % global")
            df_resumen = pd.DataFrame([{
                'Red': d['red'],
                'Total de centros': d['total'],
                'Recibidos': d['recibidos'],
                'Pendientes': d['pendientes'],
                '% de cumplimiento': d['porcentaje'],
                'Situación': d['porcentaje'],
            } for d in datos_progreso_redes])
            mostrar(tabla_df(
                df_resumen,
                chips={'% de cumplimiento': chip_porcentaje, 'Situación': chip_nivel},
                derecha=('Total de centros', 'Recibidos', 'Pendientes'),
            ))
            df_resumen_exp = df_resumen.copy()
            df_resumen_exp['% de cumplimiento'] = df_resumen_exp['% de cumplimiento'].apply(lambda x: f"{x:.1f}%")
            df_resumen_exp['Situación'] = [
                'Completo' if d['porcentaje'] >= 100 else ('Parcial' if d['porcentaje'] >= 50 else 'Bajo')
                for d in datos_progreso_redes
            ]
            descargas(df_resumen_exp, f"progreso_cumplimiento_semana_{semana_activa}_{anio_activo}", "Progreso", key="dash_resumen")
