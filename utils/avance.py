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
    Devuelve un diccionario con:
      total, enviados, pct, redes_completas, redes_proceso, redes_sin_envio
    o None si no se pudo calcular (el inicio se muestra igual, sin cifras).
    Se guarda 2 minutos en caché: es una página pública y el cálculo hace
    una consulta por red.
    """
    try:
        from src.data_loader import get_data_loader
        from app_pages.usuario_logica import calcular_avance_red

        total = enviados = completas = proceso = sin_envio = 0
        for red in get_data_loader().obtener_redes():
            av = calcular_avance_red(red, anio, semana)
            if not av or av['total'] == 0:
                continue
            n_total, n_env = av['total'], len(av['enviados'])
            total += n_total
            enviados += n_env
            if n_env >= n_total:
                completas += 1
            elif n_env > 0:
                proceso += 1
            else:
                sin_envio += 1
        if total == 0:
            return None
        return {
            "total": total,
            "enviados": enviados,
            "pct": int(round(enviados * 100 / total)),
            "redes_completas": completas,
            "redes_proceso": proceso,
            "redes_sin_envio": sin_envio,
        }
    except Exception:
        return None
