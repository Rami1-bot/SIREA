# utils/corte_ui.py
"""Campos de pantalla para elegir una fecha de corte (calendario + hora)."""

from datetime import datetime
from typing import Optional

import streamlit as st

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def texto_corte(dt: datetime) -> str:
    """'martes 13/10/2026 a las 23:59:59'."""
    return f"{DIAS[dt.weekday()]} {dt:%d/%m/%Y} a las {dt:%H:%M:%S}"


def campos_corte(clave: str, base: datetime, etiqueta_fecha: str = "Fecha de corte") -> datetime:
    """
    Calendario + lista de horas («23:59:59» primero). Devuelve el datetime elegido.
    `clave` debe cambiar cuando cambie el valor guardado, para que los campos se refresquen.
    """
    cf, ch = st.columns([1.5, 1])
    with cf:
        fecha = st.date_input(etiqueta_fecha, value=base.date(), format="DD/MM/YYYY", key=f"{clave}_f")
    with ch:
        horas = ["23:59:59"] + [f"{h:02d}:{m:02d}:00" for h in range(24) for m in (0, 30)]
        hora_base = base.strftime("%H:%M:%S")
        if hora_base not in horas:
            horas.insert(1, hora_base)
        hora = st.selectbox("Hora", horas, index=horas.index(hora_base), key=f"{clave}_h")
    elegido = datetime.combine(fecha, datetime.strptime(hora, "%H:%M:%S").time())
    st.caption(f"Corte: {texto_corte(elegido)}")
    return elegido
