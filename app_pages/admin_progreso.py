# pages/admin_progreso.py
"""
Progreso por Red - Semana a Semana
Muestra el histórico de cumplimiento de cada red.
VERSIÓN MEJORADA CON SANITIZACIÓN HTML Y NÚMEROS ENTEROS
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from typing import Optional, List

from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from utils.helpers import sanitizar_html, sanitizar_lista_html
from app_pages.admin_helpers import requerir_admin
from utils.tema import mostrar, aviso
from utils.tema_admin import (
    tabla_df, chip_porcentaje, chip_nivel, barras_h, lista_cumplimiento, panel_cab,
)


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


def obtener_centros_por_red(red: str, centros_excluidos: dict = None) -> int:
    """
    Obtiene el número total de centros de una red, excluyendo los excluidos.
    """
    try:
        data_loader = get_data_loader()
        centros = data_loader.obtener_centros(red)
        
        if centros_excluidos is None:
            centros_excluidos = obtener_centros_excluidos()
        
        excluidos_red = centros_excluidos.get(red, [])
        centros_filtrados = []
        for c in centros:
            centro_str = formatear_centro(c)
            if centro_str not in excluidos_red:
                centros_filtrados.append(c)
        
        return len(centros_filtrados)
    except:
        return 0


def formatear_centro(centro) -> str:
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


def obtener_nombre_centro(centro) -> str:
    """Obtiene el nombre del centro desde un dict o string."""
    if isinstance(centro, dict):
        return centro.get('nombre', str(centro))
    return str(centro)


def calcular_porcentaje_cumplimiento(recibidos: int, total: int) -> float:
    """Calcula el porcentaje de cumplimiento."""
    if total == 0:
        return 0.0
    return round((recibidos / total) * 100, 1)


def obtener_indicador_porcentaje(porcentaje: float) -> str:
    """Retorna el indicador HTML (etiqueta con el porcentaje) según el valor."""
    from utils.tema_admin import chip_porcentaje
    return chip_porcentaje(max(0, porcentaje))


def barra_progreso_html(porcentaje: float, ancho: int = 120) -> str:
    """Genera una barra de progreso en HTML con el porcentaje escrito."""
    from utils.tema import barra
    return barra(max(0, min(100, porcentaje)))


def descargar_csv(df: pd.DataFrame, nombre: str):
    """Descarga un DataFrame como CSV."""
    csv = df.to_csv(index=False).encode('utf-8-sig')
    return st.download_button(
        label='Descargar CSV',
        icon=':material/download:',
        data=csv,
        file_name=f"{nombre}.csv",
        mime="text/csv",
        key=f"csv_{nombre}",
        use_container_width=True
    )


def descargar_excel(df: pd.DataFrame, nombre: str):
    """Descarga un DataFrame como Excel."""
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
        excel_data = output.getvalue()
        return st.download_button(
            label='Descargar Excel',
            icon=':material/download:',
            data=excel_data,
            file_name=f"{nombre}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"excel_{nombre}",
            use_container_width=True
        )
    except Exception as e:
        st.warning(f"No se pudo generar Excel: {str(e)}")


def sanitizar_datos_progreso(datos: list) -> list:
    """
    Sanitiza los datos de progreso para prevenir XSS.
    """
    datos_sanitizados = []
    for d in datos:
        # Sanitizar el nombre de la red
        red_sanitizada = sanitizar_html(str(d.get('Red', '')))
        
        # Crear copia del diccionario con la red sanitizada
        d_sanitizado = d.copy()
        d_sanitizado['Red'] = red_sanitizada
        
        datos_sanitizados.append(d_sanitizado)
    
    return datos_sanitizados


def _centros_enviados_semana(db_manager, anio, semana, red, excluidos_red):
    """Centros de la red con envío en la semana (sin contar los excluidos)."""
    envios = db_manager.obtener_envios(anio=anio, semana=semana, red=red, limit=2000)
    enviados = set()
    for envio in envios:
        centros_envio = envio.get('centros', [])
        if isinstance(centros_envio, list):
            for c in centros_envio:
                if isinstance(c, dict):
                    nombre = c.get('nombre', str(c))
                    centro_str = formatear_centro(c)
                else:
                    nombre = str(c)
                    centro_str = str(c)
                if nombre not in excluidos_red and centro_str not in excluidos_red:
                    enviados.add(centro_str)
    return enviados


def mostrar_progreso_redes():
    """Muestra el progreso semana a semana de cada red."""

    requerir_admin()

    db_manager = get_db_manager()
    data_loader = get_data_loader()

    # Obtener centros excluidos desde la base de datos (persistente)
    centros_excluidos = obtener_centros_excluidos()

    anios_disponibles = db_manager.obtener_anios_epidemiologicos()
    if not anios_disponibles:
        mostrar(aviso("warn", "No hay años epidemiológicos configurados",
                      "Configure un año en la sección Configuración."))
        return

    anio_activo_data = db_manager.obtener_anio_activo_epidemiologico()
    anio_activo = anio_activo_data['anio'] if anio_activo_data else anios_disponibles[0]['anio']

    opciones_anios = [a['anio'] for a in anios_disponibles]
    opciones_anios.sort(reverse=True)
    # SIREA 3.3: arranca con el año y la red elegidos en el filtro común de los demás módulos
    from app_pages.filtro_periodo import periodo_actual
    _p = periodo_actual()
    if _p.anio in opciones_anios:
        anio_activo = _p.anio

    todas_las_redes = data_loader.obtener_redes()
    semanas_max = db_manager.obtener_semanas_por_anio(anio_activo)
    semanas_disponibles = list(range(1, semanas_max + 1))
    opciones_redes = ["Todas"] + todas_las_redes

    total_excluidos = sum(len(c) for c in centros_excluidos.values())
    if total_excluidos > 0:
        mostrar(aviso("info", f"{total_excluidos} centros están excluidos del conteo",
                      "Se excluyen por casos excepcionales y no entran en ningún cálculo de esta página."))

    # ============================================================
    # TABLA DE PROGRESO SEMANA A SEMANA
    # ============================================================
    with st.container(key="panel_progreso_tabla"):
        panel_cab("Cumplimiento semana a semana",
                  "Porcentaje de centros con envío en cada semana, por red")

        col1, col2, col3 = st.columns(3)
        with col1:
            anio_seleccionado = st.selectbox(
                "Año",
                options=opciones_anios,
                index=opciones_anios.index(anio_activo) if anio_activo in opciones_anios else 0,
                key="progreso_anio"
            )
        with col2:
            semana_inicio = st.selectbox(
                "Semana de inicio", options=semanas_disponibles, index=0, key="progreso_semana_inicio"
            )
        with col3:
            semana_fin = st.selectbox(
                "Semana de fin", options=semanas_disponibles,
                index=len(semanas_disponibles) - 1, key="progreso_semana_fin"
            )

        redes_seleccionadas = st.multiselect(
            "Redes", options=opciones_redes, default=[_p.red] if _p.red in opciones_redes else ["Todas"], key="progreso_redes",
            placeholder="Elija una o más redes",
        )

        if semana_inicio > semana_fin:
            mostrar(aviso("warn", "La semana de inicio no puede ser mayor que la de fin"))
            return

        redes_a_procesar = todas_las_redes if "Todas" in redes_seleccionadas else redes_seleccionadas
        if not redes_a_procesar:
            mostrar(aviso("warn", "Elija al menos una red"))
            return

        semanas = list(range(semana_inicio, semana_fin + 1))

        datos_progreso = []
        for red in redes_a_procesar:
            total_centros = obtener_centros_por_red(red, centros_excluidos)
            if total_centros == 0:
                continue
            fila = {'Red': sanitizar_html(red), 'Total de centros': total_centros}
            excluidos_red = centros_excluidos.get(red, [])
            for semana in semanas:
                recibidos = len(_centros_enviados_semana(db_manager, anio_seleccionado, semana, red, excluidos_red))
                fila[f'S{semana}'] = calcular_porcentaje_cumplimiento(recibidos, total_centros)
            datos_progreso.append(fila)

        if not datos_progreso:
            mostrar(aviso("info", "No hay datos para mostrar"))
            return

        df_progreso = pd.DataFrame(datos_progreso)
        chips = {f'S{sem}': chip_porcentaje for sem in semanas}
        mostrar(tabla_df(df_progreso, chips=chips, derecha=('Total de centros',)))
        st.caption(f"{len(datos_progreso)} redes · {len(semanas)} semanas · año {anio_seleccionado}. "
                   "Verde: 90 % o más · Ámbar: 60 % a 89 % · Rojo: menos de 60 %.")

        c1, c2, _ = st.columns([1, 1, 2.2])
        with c1:
            descargar_csv(df_progreso, f"progreso_redes_{anio_seleccionado}")
        with c2:
            descargar_excel(df_progreso, f"progreso_redes_{anio_seleccionado}")

    # ============================================================
    # ANALISIS DE CUMPLIMIENTO (independiente de los filtros de arriba)
    # ============================================================
    with st.container(key="panel_progreso_analisis"):
        panel_cab("Análisis de cumplimiento por red",
                  "Envíos recibidos sobre los esperados (centros × semanas) en el periodo elegido")

        col1, col2, col3 = st.columns(3)
        with col1:
            anio_analisis = st.selectbox(
                "Año", options=opciones_anios,
                index=opciones_anios.index(anio_activo) if anio_activo in opciones_anios else 0,
                key="analisis_anio"
            )
        with col2:
            semana_analisis_inicio = st.selectbox(
                "Semana de inicio", options=semanas_disponibles, index=0, key="analisis_semana_inicio"
            )
        with col3:
            semana_analisis_fin = st.selectbox(
                "Semana de fin", options=semanas_disponibles,
                index=len(semanas_disponibles) - 1, key="analisis_semana_fin"
            )

        redes_analisis = st.multiselect(
            "Redes", options=opciones_redes, default=["Todas"], key="analisis_redes",
            placeholder="Elija una o más redes",
        )
        redes_analisis_procesar = todas_las_redes if "Todas" in redes_analisis else redes_analisis

        if semana_analisis_inicio > semana_analisis_fin:
            mostrar(aviso("warn", "La semana de inicio no puede ser mayor que la de fin"))
            return

        semanas_analisis = list(range(semana_analisis_inicio, semana_analisis_fin + 1))

        datos_analisis = []
        for red in redes_analisis_procesar:
            total_centros = obtener_centros_por_red(red, centros_excluidos)
            if total_centros == 0:
                continue
            excluidos_red = centros_excluidos.get(red, [])
            total_recibidos = sum(
                len(_centros_enviados_semana(db_manager, anio_analisis, semana, red, excluidos_red))
                for semana in semanas_analisis
            )
            porcentaje_total = calcular_porcentaje_cumplimiento(
                total_recibidos, total_centros * len(semanas_analisis)
            )
            datos_analisis.append({
                'Red': sanitizar_html(red),
                'Total Centros': total_centros,
                'Total Envíos': total_recibidos,
                'Esperados': total_centros * len(semanas_analisis),
                'Porcentaje': porcentaje_total,
            })

        if not datos_analisis:
            mostrar(aviso("info", "No hay datos para mostrar en el análisis"))
            return

        ordenados = sorted(datos_analisis, key=lambda d: d['Porcentaje'], reverse=True)
        mostrar(lista_cumplimiento(
            [(d['Red'], d['Total Envíos'], d['Esperados']) for d in ordenados], detalle="envíos"
        ))
        st.caption(f"{len(datos_analisis)} redes · {len(semanas_analisis)} semanas.")

    with st.container(key="panel_progreso_entregas"):
        panel_cab("Entregas por red", "Cantidad de envíos recibidos en el periodo")
        mostrar(barras_h([(d['Red'], d['Total Envíos']) for d in
                          sorted(datos_analisis, key=lambda d: d['Total Envíos'], reverse=True)], "info"))

        df_analisis_display = pd.DataFrame([{
            'Red': d['Red'],
            'Total Centros': d['Total Centros'],
            'Envíos Recibidos': d['Total Envíos'],
            'Porcentaje de Cumplimiento': f"{int(d['Porcentaje'])}%",
            'Estado': 'Completo' if d['Porcentaje'] >= 100 else ('Parcial' if d['Porcentaje'] >= 50 else 'Bajo'),
        } for d in datos_analisis])

        c1, c2, _ = st.columns([1, 1, 2.2])
        with c1:
            descargar_csv(df_analisis_display, f"analisis_cumplimiento_{anio_analisis}")
        with c2:
            descargar_excel(df_analisis_display, f"analisis_cumplimiento_{anio_analisis}")
