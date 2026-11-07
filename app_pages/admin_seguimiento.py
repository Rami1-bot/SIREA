# pages/admin_seguimiento.py
"""
Seguimiento Semana Activa
Muestra el estado actual de la semana activa por red.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Optional, List

from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from src.config import Config
from app_pages.admin_helpers import requerir_admin, formatear_fecha_columna
from utils.tabla_navegable import tabla_navegable_df
from utils.helpers import sanitizar_html
from utils.tema import kpi, mostrar, aviso, lista_estado, chip
from utils.tema_admin import (esc, tabla_df, chip_porcentaje, chip_nivel, panel_cab, descargas, chip_estado, etiqueta_estado,
                              nivel_de, chip_nivel_texto, lista_cumplimiento)

# NOTA: la semana y el año activos se obtienen de Config.get_semana_actual()
# y Config.get_anio_actual() (antes había una copia local aquí que devolvía
# "semana 1" fija si fallaba la consulta a la base de datos).


def obtener_centros_excluidos() -> dict:
    """
    Obtiene los centros excluidos desde la base de datos de manera persistente.
    """
    try:
        db_manager = get_db_manager()
        return db_manager.obtener_todas_las_exclusiones_agrupadas()
    except Exception as e:
        print(f"Error al obtener centros excluidos: {e}")
        return {}


def formatear_centro(centro):
    """Formatea un centro para mostrarlo como 'codigo nombre'."""
    if isinstance(centro, dict):
        codigo = centro.get('codigo', '')
        nombre = centro.get('nombre', '')
        if codigo and nombre:
            return f"{codigo} {nombre}"
        elif nombre:
            return nombre
        else:
            return str(centro)
    return str(centro)


def obtener_nombre_centro(centro):
    """
    Obtiene el nombre del centro desde un dict o string.
    """
    if isinstance(centro, dict):
        return centro.get('nombre', str(centro))
    return str(centro)


def _chip_centro(estado) -> str:
    return {"Enviado": chip("Enviado", "ok", "check"), "Pendiente": chip("Pendiente", "warn", "reloj"),
            "Excluido": chip("Excluido", "mute")}.get(str(estado), chip(esc(estado), "mute"))


def mostrar_seguimiento_semana_activa():
    """Muestra el seguimiento de la semana activa."""

    requerir_admin()

    db_manager = get_db_manager()
    data_loader = get_data_loader()
    
    semana_activa = Config.get_semana_actual()
    anio_activo = Config.get_anio_actual()
    
    # Obtener centros excluidos desde la base de datos (persistente)
    centros_excluidos = obtener_centros_excluidos()
    
    # ============================================================
    # FILTROS
    # ============================================================
    
    # Obtener años disponibles
    anios_disponibles = db_manager.obtener_anios_epidemiologicos()
    if not anios_disponibles:
        mostrar(aviso("warn", "No hay años epidemiológicos configurados",
                      "Configure un año en la sección Configuración."))
        return
    
    opciones_anios = [a['anio'] for a in anios_disponibles]
    opciones_anios.sort(reverse=True)
    
    # Obtener redes
    todas_las_redes = data_loader.obtener_redes()
    if not todas_las_redes:
        mostrar(aviso("warn", "No hay redes configuradas"))
        return
    
    # SIREA 3.3: filtro común Año · Semana · Red (se mantiene entre módulos y al refrescar)
    from app_pages.filtro_periodo import filtro_periodo
    with st.container(key="panel_filtros_seguimiento"):
        periodo = filtro_periodo("seg", redes=todas_las_redes)
    anio_seleccionado, semana_seleccionada = periodo.anio, periodo.semana
    redes_a_procesar = [periodo.red] if periodo.red else todas_las_redes

    # ============================================================
    # MOSTRAR INFORMACIÓN DE EXCLUIDOS (resumen general)
    # ============================================================
    
    total_excluidos_general = sum(len(c) for c in centros_excluidos.values())
    if total_excluidos_general > 0:
        mostrar(aviso("info", f"{total_excluidos_general} centros están excluidos del conteo",
                      "Se excluyen por casos excepcionales y no entran en los cálculos."))
    
    # ============================================================
    # OBTENER DATOS
    # ============================================================
    
    if not redes_a_procesar:
        mostrar(aviso("warn", "Elija al menos una red"))
        return
    
    datos_seguimiento = []
    total_excluidos_mostrados = 0
    
    for red in redes_a_procesar:
        # Obtener centros de la red
        centros = data_loader.obtener_centros(red)
        
        # FILTRAR CENTROS EXCLUIDOS (usando datos desde DB)
        centros_excluidos_red = centros_excluidos.get(red, [])
        centros_filtrados = []
        for c in centros:
            # Si el centro está en la lista de excluidos, saltarlo
            centro_str = formatear_centro(c)
            if centro_str not in centros_excluidos_red:
                centros_filtrados.append(c)
        
        total_centros = len(centros_filtrados)
        total_excluidos_mostrados += len(centros_excluidos_red)
        
        if total_centros == 0:
            continue
        
        # Obtener envíos de esta red en la semana
        envios = db_manager.obtener_envios(
            anio=anio_seleccionado,
            semana=semana_seleccionada,
            red=red,
            limit=1000
        )
        
        # Nombres (normalizados, sin código) de los centros que ya
        # enviaron, excluyendo los excluidos. Se usan SOLO para
        # comparar -- en la tabla envios los centros se guardan como
        # texto "CODIGO NOMBRE" (ej. "245 H.II JAEN"), mientras que la
        # lista de centros de la red trae 'nombre' solo (ej. "H.II
        # JAEN"). Comparar esos dos formatos tal cual nunca coincide,
        # y por eso "Pendientes" mostraba TODOS los centros de la red
        # en vez de solo los que faltan.
        nombres_enviados = set()
        info_envio = {}      # nombre (minúsculas) -> datos del último envío que lo incluyó
        for envio in envios:
            centros_envio = envio.get('centros', [])
            if isinstance(centros_envio, list):
                for c in centros_envio:
                    if isinstance(c, dict):
                        nombre = c.get('nombre', str(c))
                        centro_str = formatear_centro(c)
                    else:
                        centro_str = str(c).strip()
                        partes = centro_str.split(' ', 1)
                        if len(partes) >= 2:
                            try:
                                int(partes[0])  # confirma que la 1ra parte es un código
                                nombre = partes[1].strip()
                            except ValueError:
                                nombre = centro_str
                        else:
                            nombre = centro_str
                    
                    if nombre not in centros_excluidos_red and centro_str not in centros_excluidos_red:
                        clave_c = nombre.lower()
                        nombres_enviados.add(clave_c)
                        previo = info_envio.get(clave_c)
                        if previo is None or str(envio.get('fecha_envio') or '') > previo['crudo']:
                            tipo = envio.get('tipo_reporte') or []
                            info_envio[clave_c] = {
                                'crudo': str(envio.get('fecha_envio') or ''),
                                'responsable': f"{envio.get('nombre_usuario') or ''} {envio.get('apellido_usuario') or ''}".strip() or "—",
                                'fecha': formatear_fecha_columna(envio.get('fecha_envio')),
                                'tipo': (', '.join(tipo) if isinstance(tipo, list) else str(tipo or '')).replace('Hospitalizacion', 'Hospitalización') or "—",
                                'estado': str(envio.get('estado') or ''),
                            }
        
        # Separar los centros de la red (ya sin excluidos) en enviados
        # y pendientes, comparando por nombre normalizado -- así ambas
        # listas quedan con el mismo formato "código nombre" al mostrarlas.
        centros_enviados = []
        centros_pendientes = []
        filas_centros = []
        for c in centros_filtrados:
            nombre = c.get('nombre', '') if isinstance(c, dict) else str(c)
            etiqueta = formatear_centro(c)
            if nombre and nombre.lower() in nombres_enviados:
                centros_enviados.append(etiqueta)
                i = info_envio.get(nombre.lower(), {})
                filas_centros.append([red, etiqueta, 'Enviado', i.get('responsable', '—'), i.get('tipo', '—'),
                                      i.get('fecha', '—'), i.get('estado') or '—'])
            else:
                centros_pendientes.append(etiqueta)
                filas_centros.append([red, etiqueta, 'Pendiente', '—', '—', '—', '—'])
        for ex in centros_excluidos_red:
            filas_centros.append([red, str(ex), 'Excluido', '—', '—', '—', '—'])
        
        recibidos = len(centros_enviados)
        porcentaje = round((recibidos / total_centros) * 100, 1) if total_centros > 0 else 0
        
        datos_seguimiento.append({
            'Red': red,
            'Total Establecimientos': total_centros,
            'Recibidos': recibidos,
            '% Recibido': f"{porcentaje}%",
            'Porcentaje': porcentaje,
            'Centros Enviados': centros_enviados,
            'Centros Pendientes': centros_pendientes,
            'Excluidos': centros_excluidos_red,
            'Cantidad Excluidos': len(centros_excluidos_red),
            'Filas': filas_centros,
        })
    
    if not datos_seguimiento:
        mostrar(aviso("info", "No hay datos para mostrar"))
        return
    
    # ============================================================
    # INDICADORES
    # ============================================================

    total_centros = sum(d['Total Establecimientos'] for d in datos_seguimiento)
    total_recibidos = sum(d['Recibidos'] for d in datos_seguimiento)
    total_porcentaje = round((total_recibidos / total_centros) * 100, 1) if total_centros > 0 else 0
    total_pendientes = total_centros - total_recibidos

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        mostrar(kpi("Establecimientos", total_centros, f"{len(datos_seguimiento)} redes", None, "dash"))
    with col2:
        mostrar(kpi("Recibidos", total_recibidos, f"Semana {semana_seleccionada} · {anio_seleccionado}", "ok", "check"))
    with col3:
        mostrar(kpi("Pendientes", total_pendientes, "Aún sin envío", "warn" if total_pendientes else "ok", "reloj"))
    with col4:
        tono = "ok" if total_porcentaje >= 90 else ("warn" if total_porcentaje >= 60 else "bad")
        mostrar(kpi("Cumplimiento", f"{total_porcentaje} %", "Recibidos sobre el total", tono, "barras"))

    # ============================================================
    # TABLA RESUMEN
    # ============================================================

    df_resumen = pd.DataFrame([{
        'Red': d['Red'],
        'Total de establecimientos': d['Total Establecimientos'],
        'Recibidos': d['Recibidos'],
        'Pendientes': len(d['Centros Pendientes']),
        'Excluidos': d['Cantidad Excluidos'],
        '% recibido': d['Porcentaje'],
        'Situación': nivel_de(d['Porcentaje']),
    } for d in datos_seguimiento])

    with st.container(key="panel_resumen_seguimiento"):
        panel_cab(f"Resumen · Semana {semana_seleccionada} de {anio_seleccionado}",
                  "Estado de cada red en la semana elegida")
        tabla_navegable_df(
            "seg_resumen", df_resumen,
            chips={'% recibido': chip_porcentaje, 'Situación': chip_nivel_texto},
            derecha=('Total de establecimientos', 'Recibidos', 'Pendientes', 'Excluidos', '% recibido'),
            filtro={"columna": "Situación", "opciones": ["Completo", "Parcial", "Bajo"], "etiqueta": "Situación"},
            filtros=[{"columna": "Red", "etiqueta": "Red"}],
            placeholder="Nombre de la red", unidad="redes", por_pagina_inicial=25,
            orden_inicial="% recibido: de menor a mayor",
        )
        total_excluidos = sum(d['Cantidad Excluidos'] for d in datos_seguimiento)
        if total_excluidos > 0:
            st.caption(f"{total_excluidos} centros excluidos en total (no se consideran en los cálculos).")

    # ============================================================
    # DETALLE POR RED - CENTROS ENVIADOS Y PENDIENTES
    # ============================================================

    filas_detalle = [f for d in datos_seguimiento for f in d['Filas']]
    n_env = sum(1 for f in filas_detalle if f[2] == 'Enviado')
    n_pen = sum(1 for f in filas_detalle if f[2] == 'Pendiente')
    n_exc = sum(1 for f in filas_detalle if f[2] == 'Excluido')

    with st.container(key="panel_detalle_seguimiento"):
        panel_cab("Detalle por red", "Qué centro envió, quién lo envió y cuáles faltan; filtre por red, centro o estado")
        d1, d2 = st.columns([1, 1.9], gap="large")
        with d1:
            st.markdown("**Redes más atrasadas**")
            atrasadas = sorted(datos_seguimiento, key=lambda d: (d['Porcentaje'], -len(d['Centros Pendientes'])))[:8]
            mostrar(lista_cumplimiento([(d['Red'], d['Recibidos'], d['Total Establecimientos']) for d in atrasadas]))
            if len(datos_seguimiento) > 8:
                st.caption(f"Se muestran las 8 con menor avance de {len(datos_seguimiento)} redes; el resto está en la tabla.")
        with d2:
            st.markdown("**Centros**")
            k1, k2, k3 = st.columns(3)
            with k1:
                mostrar(kpi("Enviaron", n_env, "Centros con envío", "ok", "check"))
            with k2:
                mostrar(kpi("Pendientes", n_pen, "Faltan por enviar", "warn" if n_pen else "ok", "reloj"))
            with k3:
                mostrar(kpi("Excluidos", n_exc, "No se cuentan", None, "info"))

        columnas_det = ['Red', 'Centro', 'Estado', 'Responsable', 'Tipo de reporte', 'Fecha de envío', 'Estado del envío']
        df_det = pd.DataFrame(filas_detalle, columns=columnas_det)
        orden_estado = {'Pendiente': 0, 'Enviado': 1, 'Excluido': 2}
        tabla_navegable_df(
            "seg_detalle", df_det,
            chips={'Estado': _chip_centro, 'Estado del envío': lambda e: chip_estado(e) if e and e != '—' else '—'},
            filtro={"columna": "Estado", "opciones": ['Pendiente', 'Enviado', 'Excluido'], "etiqueta": "Estado del centro"},
            filtros=[{"columna": "Red", "etiqueta": "Red"},
                     {"columna": "Centro", "etiqueta": "Centro", "depende_de": "Red"},
                     {"columna": "Tipo de reporte", "etiqueta": "Tipo de reporte"}],
            fechas={"columna": "Fecha de envío", "etiqueta": "Envío"},
            columnas_elegibles=True, ocultas=('Estado del envío',),
            orden_opciones=[("Pendientes primero", "Estado", False),
                            ("Red: A → Z", "Red", False), ("Centro: A → Z", "Centro", False)],
            claves_orden={'Estado': lambda f: orden_estado.get(str(f[2]), 9)},
            orden_inicial="Pendientes primero",
            placeholder="Centro, responsable o red", unidad="centros", por_pagina_inicial=25,
            descarga=(f"seguimiento_centros_{semana_seleccionada}_{anio_seleccionado}", "Centros"),
        )

    # ============================================================
    # DESCARGAS
    # ============================================================

    df_resumen_exp = df_resumen.copy()
    df_resumen_exp['% recibido'] = df_resumen_exp['% recibido'].apply(lambda x: f"{x}%")
    df_resumen_exp['Situación'] = [
        'Completo' if d['Porcentaje'] >= 100 else ('Parcial' if d['Porcentaje'] >= 50 else 'Bajo')
        for d in datos_seguimiento
    ]
    df_detalle = pd.DataFrame([{
        'Red': d['Red'],
        'Centros Enviados': ', '.join(d['Centros Enviados']),
        'Centros Pendientes': ', '.join(d['Centros Pendientes']),
        'Centros Excluidos': ', '.join(d.get('Excluidos', [])),
        'Total': d['Total Establecimientos'],
        'Recibidos': d['Recibidos'],
        '% Recibido': f"{d['Porcentaje']}%",
    } for d in datos_seguimiento])

    with st.container(key="panel_descargas_seguimiento"):
        panel_cab("Descargas")
        st.caption("Resumen por red, o detalle con la lista de centros de cada red.")
        st.markdown("**Resumen por red**")
        descargas(df_resumen_exp, f"seguimiento_resumen_{semana_seleccionada}_{anio_seleccionado}", "Resumen", key="seg_res")
        st.markdown("**Detalle de centros**")
        descargas(df_detalle, f"seguimiento_detalle_{semana_seleccionada}_{anio_seleccionado}", "Detalle", key="seg_det")
