# app_pages/agente_sugerencias.py
"""
Sugerencias del Agente Operativo DENTRO de cada sección de SIRE.

Cada cosa en su lugar: los recordatorios sugeridos aparecen en
«Notificaciones» y las propuestas sobre observaciones en «Observaciones».
Se aprueban o rechazan ahí mismo con la misma tarjeta (y las mismas
reglas) que en «Agente de IA». Si la IA está detenida o no hay
sugerencias, el panel no estorba: la sección funciona igual que siempre.
"""

from __future__ import annotations

from typing import Iterable

import streamlit as st

from utils.tema import aviso, mostrar
from utils.tema_ia import esc

TIPOS_OBSERVACION = ("SOLICITAR_CORRECCION", "MARCAR_REVISADA", "REINTENTAR_FALLA")


def panel(tipos: Iterable[str], titulo: str, vacio: str = "", clave: str = "sug") -> int:
    """Muestra las propuestas pendientes de esos tipos. Devuelve cuántas había."""
    try:
        from src.agentes import agente_operativo as ag, estado
        from src.agentes.skills import cargar_todas
        if not ag.disponible():
            return 0
        tipos = set(tipos)
        pend = [p for p in ag.propuestas("PROPUESTA") if p.get("tipo") in tipos]
    except Exception:
        return 0
    flash = st.session_state.pop("sirea_bandeja_flash", None)
    if flash:
        (st.success if flash[0] else st.error)(flash[1])
    if not pend:
        if vacio:
            st.caption(vacio)
        return 0
    from app_pages.admin_agentes_ia import _tarjeta_propuesta
    no_opera = not estado.esta_operativo(ag.AGENTE)
    skills = cargar_todas()
    with st.expander(f"✦ {titulo} ({len(pend)})", expanded=True):
        st.caption("Propuestas del Agente de IA. Revise, corrija si hace falta y apruebe: recién ahí se ejecutan.")
        if no_opera:
            mostrar(aviso("warn", "La IA está detenida", "Puede revisar las sugerencias, pero no aprobarlas hasta reactivarla."))
        for p in pend:
            _tarjeta_propuesta(p, skills.get(p.get("skill")), deshabilitar=no_opera)
    return len(pend)


def aviso_recordatorio_reciente(red: str):
    """En Notificaciones: avisa si la red ya recibió un recordatorio o tiene uno sugerido."""
    if not red or red == "Todas":
        return
    try:
        from src.agentes import acciones, agente_operativo as ag
        ult = acciones.ultimo_recordatorio(red, dias=3)
        sugerido = any(p.get("tipo") == "RECORDATORIO_RED" and p.get("red") == red for p in ag.propuestas("PROPUESTA"))
    except Exception:
        return
    if ult:
        from datetime import datetime, timezone
        f = acciones._parse(ult["ejecutada_at"])
        horas = int((datetime.now(timezone.utc) - f).total_seconds() // 3600) if f else None
        quien = "el Agente de IA (aprobado por una persona)" if ult.get("origen") == "agente" else "una persona desde aquí"
        if horas is not None and horas < 20:
            mostrar(aviso("warn", f"{esc(red)} ya recibió un recordatorio hace {horas} h",
                          f"Lo envió {quien}. Para no saturar a la red, espere al menos 20 horas antes de otro."))
    if sugerido:
        mostrar(aviso("info", f"El agente ya sugirió un recordatorio para {esc(red)}",
                      "Está arriba, en «Sugerencias del agente». Si lo aprueba, no hace falta enviarlo también a mano."))
