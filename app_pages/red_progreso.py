# pages/red_progreso.py
"""
Vista de progreso de UNA red (solo lectura), para el login por red.

Es una versión reducida de "Progreso por Red" (pages/admin_progreso.py)
-- misma lógica de cálculo de cumplimiento semana a semana -- pero
fijada a una sola red (la que inició sesión) y sin las opciones de
administración: no hay selector de red, no hay acceso al formulario de
envío, no se pueden ver ni gestionar otras redes.
"""

import streamlit as st
import pandas as pd

from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from utils.helpers import sanitizar_html, obtener_fecha_actual

from app_pages.admin_progreso import (
    obtener_centros_excluidos,
    obtener_centros_por_red,
    formatear_centro,
    calcular_porcentaje_cumplimiento,
    descargar_csv,
    descargar_excel,
)
from app_pages.usuario_logica import (
    extraer_nombre_limpio, obtener_centros_con_red_por_red, calcular_avance_red,
)
from utils.tema import (
    mostrar, mostrar_aviso, kpi, icono, lista_estado, periodo_semana,
    fecha_corte_info, texto_dias_restantes, AZUL, TONOS,
)
from utils.tema_admin import tabla_html, chip_porcentaje
from utils.tema import chip
from utils.duplicados import solo_originales
from app_pages.red_detalle import mostrar_detalle_envios_red


def _centros_enviados_de_envios(envios: list, excluidos_red: list) -> set:
    """Nombres normalizados de centros con al menos un envío en una lista de envíos."""
    centros_enviados = set()
    for envio in envios:
        centros_envio = envio.get('centros', [])
        if isinstance(centros_envio, list):
            for c in centros_envio:
                if isinstance(c, dict):
                    nombre = c.get('nombre', str(c))
                    centro_str = formatear_centro(c)
                else:
                    nombre = extraer_nombre_limpio(str(c))
                    centro_str = str(c)
                if nombre not in excluidos_red and centro_str not in excluidos_red:
                    centros_enviados.add(centro_str)
    return centros_enviados


@st.cache_data(ttl=30, show_spinner=False)
def _cumplimiento_semanas(red: str, anio: int, semana_inicio: int, semana_fin: int):
    """
    Cumplimiento de la red semana a semana: lista de
    {'semana', 'porcentaje', 'recibidos', 'total'}, o None si la red no
    tiene centros activos. Se guarda 30 s en cache para no repetir una
    consulta por semana cada vez que se redibuja la pantalla.
    """
    db_manager = get_db_manager()
    centros_excluidos = obtener_centros_excluidos()
    total_centros = obtener_centros_por_red(red, centros_excluidos)
    if total_centros == 0:
        return None
    excluidos_red = centros_excluidos.get(red, [])
    resultado = []
    for semana in range(semana_inicio, semana_fin + 1):
        envios = db_manager.obtener_envios(anio=anio, semana=semana, red=red, limit=2000)
        recibidos = len(_centros_enviados_de_envios(envios, excluidos_red))

        # Envíos tardíos de la semana (los duplicados no cuentan: no son un envío nuevo).
        originales = solo_originales(envios)
        tardios_lista = [e for e in originales if e.get('es_atrasado') or e.get('estado') == 'ATRASADO']
        resultado.append({
            'semana': semana,
            'porcentaje': calcular_porcentaje_cumplimiento(recibidos, total_centros),
            'recibidos': recibidos,
            'total': total_centros,
            'envios': len(originales),
            'tardios': len(tardios_lista),
            'centros_tardios': len(_centros_enviados_de_envios(tardios_lista, excluidos_red)),
        })
    return resultado


def _grafico_evolucion(datos: list, semana_activa: int) -> str:
    """Barras de cumplimiento por semana (HTML). Cada barra lleva su valor escrito."""
    alto = 160
    denso = " denso" if len(datos) > 26 else ""
    columnas = []
    for d in datos:
        pct = max(0, min(100, d['porcentaje']))
        activa = d['semana'] == semana_activa
        color = AZUL if activa else "#7FB0D6"
        h = max(2, round(pct / 100 * alto, 1))
        negrita = " act" if activa else ""
        columnas.append(
            f'<div class="sire-col{negrita}" title="Semana {d["semana"]}: {int(pct)} % '
            f'({d["recibidos"]} de {d["total"]} centros)">'
            f'<span class="pct">{int(pct)} %</span>'
            f'<div style="height:{h}px;background:{color}"></div>'
            f'<span class="sem">S{d["semana"]}</span></div>'
        )
    return (
        f'<div class="sire-chart{denso}" role="img" '
        f'aria-label="Porcentaje de centros con envío por semana">{"".join(columnas)}</div>'
    )


def _grafico_tardios(datos: list, semana_activa: int) -> str:
    """Barras de envíos tardíos por semana (HTML): cada barra lleva su cantidad escrita."""
    alto = 160
    maximo = max([d['tardios'] for d in datos] + [1])
    denso = " denso" if len(datos) > 26 else ""
    columnas = []
    for d in datos:
        n = d['tardios']
        activa = d['semana'] == semana_activa
        if n == 0:
            color, h = "#D5DDE4", 3
        else:
            color = "#B42318" if activa else "#D9847C"
            h = max(8, round(n / maximo * alto, 1))
        negrita = " act" if activa else ""
        columnas.append(
            f'<div class="sire-col{negrita}" title="Semana {d["semana"]}: {n} envío(s) tardío(s) '
            f'de {d["envios"]} recibido(s)">'
            f'<span class="pct">{n}</span>'
            f'<div style="height:{h}px;background:{color}"></div>'
            f'<span class="sem">S{d["semana"]}</span></div>'
        )
    return (
        f'<div class="sire-chart{denso}" role="img" '
        f'aria-label="Cantidad de envíos tardíos por semana">{"".join(columnas)}</div>'
    )


def _seccion_tardios(datos: list, anio: int, semana_inicio: int, semana_fin: int,
                     semana_activa: int, es_anio_activo: bool):
    """Tabla y gráfico de barras: cuántos envíos tardíos hizo la red por semana."""
    mostrar('<h2 class="sire-h2">Envíos tardíos</h2>')

    total_rango = sum(d['tardios'] for d in datos)
    actual = next((d for d in datos if es_anio_activo and d['semana'] == semana_activa), None)
    k1, k2 = st.columns(2)
    with k1:
        if actual is not None:
            mostrar(kpi(f"Semana actual ({semana_activa})", actual['tardios'],
                        f"envío(s) tardío(s) de {actual['envios']} recibido(s)",
                        tono="bad" if actual['tardios'] else "ok", ico="reloj" if actual['tardios'] else "check"))
        else:
            mostrar(kpi("Semana actual", "—", "Fuera del rango o del año elegido", ico="reloj"))
    with k2:
        mostrar(kpi(f"Semanas {semana_inicio} a {semana_fin}", total_rango,
                    "envío(s) tardío(s) en el periodo elegido",
                    tono="bad" if total_rango else "ok", ico="alerta" if total_rango else "check"))

    if total_rango == 0:
        mostrar_aviso("ok", "Sin envíos tardíos en este periodo",
                      f"La red no registró envíos fuera de plazo entre las semanas {semana_inicio} y {semana_fin} de {anio}.")

    mostrar('<div style="height:14px"></div>')
    filas = []
    for d in datos:
        dentro = max(d['envios'] - d['tardios'], 0)
        filas.append([
            f"Semana {d['semana']}" + (" (actual)" if es_anio_activo and d['semana'] == semana_activa else ""),
            d['envios'], dentro,
            chip(str(d['tardios']), "bad", "alerta") if d['tardios'] else chip("0", "ok", "check"),
            d['centros_tardios'],
        ])
    mostrar(
        f'<p class="sire-nota" style="margin:4px 0 12px">Envíos de la red por semana epidemiológica del reporte, '
        f'semanas {semana_inicio} a {semana_fin} · Año {anio}. Un envío es tardío si llegó después de la fecha de corte de su semana.</p>'
        + tabla_html(
            ['Semana', 'Envíos recibidos', 'Dentro del plazo', 'Envíos tardíos', 'Centros con envío tardío'],
            filas,
            crudas=['Envíos tardíos'],
            derecha=['Envíos recibidos', 'Dentro del plazo', 'Envíos tardíos', 'Centros con envío tardío'],
            alto=None if len(datos) <= 12 else 420,
        )
    )
    mostrar(
        '<p class="sire-nota" style="margin:20px 0 4px">Envíos tardíos por semana (barras)</p>'
        + _grafico_tardios(datos, semana_activa if es_anio_activo else -1)
    )


def _tarjeta_lista(titulo: str, items: list, tono: str, etiqueta: str, vacio: str) -> str:
    fg = TONOS[tono][0]
    borde = "#1E6B3A" if tono == "ok" else "#A15C07"
    cuerpo = lista_estado([(sanitizar_html(c), tono, etiqueta) for c in items]) if items else \
        f'<p class="sire-nota" style="margin:8px 0 12px">{vacio}</p>'
    return (
        f'<div class="sire-lcard" style="border-top-color:{borde}">'
        f'<div class="sire-lcard-h">{titulo} <span>({len(items)})</span></div>'
        f'<div class="sire-scroll">{cuerpo}</div></div>'
    )


def mostrar_progreso_red_login(red: str):
    """Muestra el progreso de UNA sola red (solo lectura): semana activa, detalle y evolución."""

    db_manager = get_db_manager()
    red_sanitizada = sanitizar_html(red)

    from src.config import Config
    semana_activa = Config.get_semana_actual()
    anio_activo_sistema = Config.get_anio_actual()

    # ============================================================
    # RESUMEN DE LA SEMANA ACTIVA
    # ============================================================
    av = calcular_avance_red(red, anio_activo_sistema, semana_activa)
    corte_txt, corte_dt = fecha_corte_info()
    periodo = periodo_semana(anio_activo_sistema, semana_activa)

    if av is None:
        mostrar_aviso("warn", "No se pudo consultar el avance de la semana activa",
                      "Intente nuevamente en unos minutos.")
    elif av['total'] == 0:
        mostrar_aviso("info", f"La red {red_sanitizada} no tiene centros activos registrados",
                      "Todos sus centros están excluidos o aún no se han cargado.")
        return
    else:
        total = av['total']
        n_env = len(av['enviados'])
        pct = int(round(n_env * 100 / total))
        color = TONOS["ok"][0] if pct >= 100 else AZUL
        barra_av = (
            f'<div class="sire-avance-pista" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" '
            f'aria-valuemax="100" aria-label="Avance de la red"><div style="width:{pct}%;background:{color}"></div></div>'
        )
        dias = texto_dias_restantes(corte_dt)
        corte_fecha = corte_txt.split(" ")[0] if corte_dt else corte_txt
        corte_hora = (corte_txt.split(" ")[1] + (" · " + dias if dias else "")) if corte_dt else dias

        c1, c2, c3 = st.columns(3)
        with c1:
            mostrar(kpi("Semana activa", f"{semana_activa}", periodo, ico="reloj"))
        with c2:
            mostrar(kpi("Avance de la semana", f"{n_env} de {total}",
                        f"centros enviaron · {pct} %{barra_av}", ico="barras"))
        with c3:
            mostrar(kpi("Fecha límite", corte_fecha, corte_hora, ico="alerta" if dias == "plazo vencido" else "check",
                        tono="bad" if dias == "plazo vencido" else None))

        # ---- Detalle de la semana activa ----
        mostrar(f'<h2 class="sire-h2">Detalle de la semana {semana_activa}</h2>')
        if av['excluidos']:
            st.caption(f"{av['excluidos']} centro(s) excluido(s) por la OIIS no se cuentan en el avance.")
        col1, col2 = st.columns(2, gap="medium")
        with col1:
            mostrar(_tarjeta_lista("Centros que ya enviaron", av['enviados'], "ok", "Enviado",
                                   "Ningún centro ha enviado todavía."))
        with col2:
            mostrar(_tarjeta_lista("Centros pendientes", av['pendientes'], "warn", "Pendiente",
                                   "Todos los centros enviaron."))

    # ============================================================
    # QUIEN ENVIO, QUE SE RECIBIO Y OBSERVACIONES (v7.1)
    # ============================================================
    if av and av.get('total'):
        mostrar_detalle_envios_red(red, anio_activo_sistema, semana_activa)

    # ============================================================
    # EVOLUCION SEMANAL
    # ============================================================
    mostrar('<h2 class="sire-h2">Evolución semanal</h2>')

    anios_disponibles = db_manager.obtener_anios_epidemiologicos()
    if not anios_disponibles:
        mostrar_aviso("warn", "No hay años epidemiológicos configurados")
        return

    anio_activo_data = db_manager.obtener_anio_activo_epidemiologico()
    anio_activo = anio_activo_data['anio'] if anio_activo_data else anios_disponibles[0]['anio']
    opciones_anios = sorted([a['anio'] for a in anios_disponibles], reverse=True)

    with st.container(key="sec_evolucion"):
        f1, f2, f3 = st.columns([1, 1, 1])
        with f1:
            anio_seleccionado = st.selectbox(
                "Año", options=opciones_anios,
                index=opciones_anios.index(anio_activo) if anio_activo in opciones_anios else 0,
                key="red_progreso_anio"
            )
        semanas_max = db_manager.obtener_semanas_por_anio(anio_seleccionado) or 52
        semanas_disponibles = list(range(1, semanas_max + 1))

        # Por defecto: las últimas 10 semanas hasta la semana activa.
        fin_def = semana_activa if (anio_seleccionado == anio_activo_sistema and semana_activa in semanas_disponibles) \
            else semanas_disponibles[-1]
        ini_def = max(1, fin_def - 9)
        with f2:
            semana_inicio = st.selectbox(
                "Semana (inicio)", options=semanas_disponibles,
                index=semanas_disponibles.index(ini_def), key=f"red_progreso_semana_inicio_{anio_seleccionado}"
            )
        with f3:
            semana_fin = st.selectbox(
                "Semana (fin)", options=semanas_disponibles,
                index=semanas_disponibles.index(fin_def), key=f"red_progreso_semana_fin_{anio_seleccionado}"
            )

        if semana_inicio > semana_fin:
            mostrar_aviso("warn", "Rango de semanas no válido", "La semana de inicio no puede ser mayor que la de fin.")
            return

        datos = _cumplimiento_semanas(red, anio_seleccionado, semana_inicio, semana_fin)
        if datos is None:
            mostrar_aviso("info", f"La red {red_sanitizada} no tiene centros activos registrados")
            return

        # Tabla de cumplimiento (una fila, una columna por semana) y, debajo, el gráfico de barras.
        fila = {'Red': red, 'Total Establecimientos': datos[0]['total']}
        for d in datos:
            fila[f"Semana {d['semana']}"] = d['porcentaje']

        columnas_sem = [f"Sem. {d['semana']}" for d in datos]
        mostrar(
            f'<p class="sire-nota" style="margin:4px 0 12px">Cumplimiento de la red: porcentaje de centros con envío, '
            f'semanas {semana_inicio} a {semana_fin} · Año {anio_seleccionado}.</p>'
            + tabla_html(
                ['Red', 'Centros'] + columnas_sem,
                [[sanitizar_html(red), datos[0]['total']] + [d['porcentaje'] for d in datos]],
                chips={c: chip_porcentaje for c in columnas_sem},
                derecha=['Centros'],
            ).replace('class="sire-tabla-wrap"', 'class="sire-tabla-wrap sire-nowrap"', 1)
        )
        mostrar(
            '<p class="sire-nota" style="margin:20px 0 4px">Evolución por semana (barras)</p>'
            + _grafico_evolucion(datos, semana_activa if anio_seleccionado == anio_activo_sistema else -1)
        )

        # Descargas
        df_progreso = pd.DataFrame([fila])
        d1, d2, _ = st.columns([1, 1, 2])
        with d1:
            descargar_csv(df_progreso, f"progreso_{red}_{anio_seleccionado}")
        with d2:
            descargar_excel(df_progreso, f"progreso_{red}_{anio_seleccionado}")

        _seccion_tardios(datos, anio_seleccionado, semana_inicio, semana_fin, semana_activa,
                         es_anio_activo=(anio_seleccionado == anio_activo_sistema))
