# app_pages/agentes_ui.py
"""
Pestaña «Investigador» dentro de «Agente de IA»: chat de diagnóstico
(solo lectura). Los asistentes de redacción, control y pre-evaluación de
SIREA 2.x se retiraron en SIREA 3.0 (ver estado.CATALOGO).

Reglas: todo texto de datos o del modelo pasa por `esc()`; lila = IA
pendiente, verde = validado por una persona.
"""

from __future__ import annotations

from typing import Callable, Dict, List

import streamlit as st

from src.agentes import auditoria, estado
from utils.tema import aviso, mostrar
from utils.tema_ia import esc  # admite esc(texto, maximo)
from utils import tema_ia


def _no_operativo(agente: str) -> bool:
    if estado.esta_operativo(agente):
        return False
    g, i = estado.estado_global(), estado.estado_individual(agente)
    nombre = estado.CATALOGO[agente].nombre
    if g != estado.ACTIVO_HITL:
        texto = (f"La IA está «{estado.ETIQUETA_UI.get(g, g)}» (estado general). "
                 "Un SUPER_ADMIN puede reactivarla en «Gobernanza de IA → Encender y apagar».")
    else:
        texto = (f"El estado general es «Activo», pero el {nombre} está «{estado.ETIQUETA_UI.get(i, i)}». "
                 "Un SUPER_ADMIN puede activarlo en «Gobernanza de IA → Encender y apagar → Activar la IA».")
    mostrar(aviso("warn", "Asistente no disponible", esc(texto)))
    return True


# ------------------------------------------------------------
# 1. Investigador
# ------------------------------------------------------------

def investigador(usuario: Dict, on_error: Callable):
    agente = auditoria.AGENTE_INVESTIGADOR
    with st.expander("¿Qué hace este asistente?", expanded=False):
        st.markdown("Pregunte en lenguaje natural; el asistente lee solo lo necesario de la base con herramientas de solo "
                    "lectura y responde con esos datos. No envía ni cambia nada. Es Quipu, el asistente de bolsillo de todas las "
                    "pantallas (abajo a la derecha; es la misma conversación). Ejemplos: «¿Qué le falta a la red Almenara?» · «¿Qué redes suelen "
                    "atrasarse?» · «¿Cuántas observaciones hay sin revisar?» · «¿Qué hizo la IA esta semana?»")
    if _no_operativo(agente):
        return
    hist: List[Dict] = st.session_state.setdefault("sirea_inv_hist", [])
    c1, c2 = st.columns([3.6, 1.4])
    with c2:
        if st.button("Nueva conversación", key="inv_nueva", use_container_width=True, icon=":material/restart_alt:"):
            st.session_state["sirea_inv_hist"] = []
            st.rerun()
    for t in hist:
        if t["rol"] == "usuario":
            mostrar(tema_ia.burbuja_usuario(t["texto"]))
        else:
            mostrar(tema_ia.burbuja_asistente(t["texto"].replace("\n---\n_Respuesta generada por IA a partir de datos del sistema. Verificar antes de difundir._", ""),
                                             t.get("proveedor"), t.get("modelo"), t.get("herramientas") or []))
    pregunta = st.chat_input("Escriba su pregunta de diagnóstico…", key="inv_input", max_chars=800)
    if pregunta:
        from src.agentes import agente_investigador
        with st.spinner("Investigando en los datos del sistema…"):
            try:
                r = agente_investigador.responder_pregunta(pregunta, [{"rol": t["rol"], "texto": t["texto"]} for t in hist])
            except Exception as e:  # noqa: BLE001
                on_error(e)
                return
        hist.append({"rol": "usuario", "texto": pregunta})
        hist.append({"rol": "asistente", "texto": r["texto"], "proveedor": r.get("proveedor"),
                     "modelo": r.get("modelo"), "herramientas": r.get("herramientas") or []})
        st.rerun()
