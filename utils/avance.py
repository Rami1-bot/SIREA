# utils/avance.py
"""
Avance nacional de la semana activa para el inicio público.

Solo se calculan cifras agregadas (centros con reporte sobre centros
esperados, y cuántas redes están completas, en proceso o sin envíos). El
inicio es una página pública: no se muestran nombres ni porcentajes de redes
individuales (eso queda en el panel de administración).
"""

import streamlit as st


@st.cache_data(ttl=120, show_spinner=False)
def avance_nacional(anio: int, semana: int):
    """
    Diccionario con total, enviados, pct, redes_completas, redes_proceso, redes_sin_envio,
    o None si no se pudo calcular (el inicio se muestra igual, sin cifras).

    SIREA 3.5: lee lo que dejó precalculado el proceso programado (menos de 10 minutos);
    si no hay, lo calcula con 3 consultas en total (antes, dos por red). Además se guarda
    2 minutos en la memoria de esta instancia.
    """
    from src.avance_nacional import obtener
    return obtener(anio, semana)
