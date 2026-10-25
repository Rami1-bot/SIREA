# app_pages/quipu.py
"""
SIREA 3.3 · «Quipu», el asistente de bolsillo del panel.

El quipu era el sistema de cuerdas con nudos con el que los incas llevaban
sus registros y cuentas. Este Quipu hace lo mismo con SIREA: lee lo que hay
en la base y responde en simple.

  * Botón flotante en la esquina inferior derecha de TODAS las pantallas del
    panel. Se abre en una cajita y se puede agrandar («Ampliar»).
  * Es el mismo Asistente de consulta (src/agentes/agente_investigador.py)
    con los mismos controles: solo lectura, herramientas con lista blanca,
    guardrails de entrada y salida, y cada pregunta en el Historial de IA.
  * Recibe como contexto la pantalla que la persona está mirando y la semana
    elegida en el filtro común.
  * Va dentro de un fragmento: preguntar, abrir o cerrar NO recarga la
    pantalla de atrás (no se pierden filtros ni lo que estaba escribiendo).
  * Límite por sesión: ASISTENTE_LIMITE_HORA (30 por defecto).
"""

from __future__ import annotations

import os
import time
from typing import Dict, List

import streamlit as st

from utils import tema_ia
from utils.tema import mostrar

NOMBRE = "Quipu"
CLAVE_HIST = "sirea_inv_hist"          # la misma conversación en todas las pantallas
PIE = "\n\n---\n_Respuesta generada por IA a partir de datos del sistema. Verificar antes de difundir._"

# Ícono propio: una cuerda principal con cuerdas colgantes y nudos (como un quipu).
ICONO = ('<svg width="{t}" height="{t}" viewBox="0 0 32 32" fill="none" aria-hidden="true">'
         '<path d="M4 7.5h24" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'
         '<path d="M8 8v15M13.3 8v19M18.6 8v12M24 8v17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
         '<circle cx="8" cy="14" r="2.1" fill="currentColor"/><circle cx="8" cy="20" r="1.6" fill="currentColor"/>'
         '<circle cx="13.3" cy="17" r="2.1" fill="currentColor"/><circle cx="13.3" cy="24" r="1.6" fill="currentColor"/>'
         '<circle cx="18.6" cy="13" r="1.6" fill="currentColor"/><circle cx="24" cy="16" r="2.1" fill="currentColor"/>'
         '<circle cx="24" cy="22" r="1.6" fill="currentColor"/></svg>')

SUGERENCIAS_BASE = ["¿Qué redes faltan esta semana?", "¿Qué le falta a cada red por tipo de reporte?",
                    "¿Qué redes suelen atrasarse?"]
SUGERENCIAS = {
    "Notificaciones": "¿A qué redes conviene recordar hoy?",
    "Seguimiento": "¿Cuántos centros faltan por red?",
    "Envíos tardíos": "¿Qué redes enviaron tarde esta semana?",
    "Agente de IA": "¿Qué propuestas esperan mi decisión?",
    "Observaciones": "¿Qué observaciones siguen sin revisar?",
}


def _limite_hora() -> int:
    try:
        return max(1, int(os.getenv("ASISTENTE_LIMITE_HORA") or 30))
    except ValueError:
        return 30


def _puede_preguntar() -> bool:
    ahora = time.time()
    marcas = [t for t in st.session_state.get("sirea_asist_marcas", []) if ahora - t < 3600]
    st.session_state["sirea_asist_marcas"] = marcas
    return len(marcas) < _limite_hora()


def _alternar(clave: str):
    st.session_state[clave] = not st.session_state.get(clave)


def _nueva():
    st.session_state[CLAVE_HIST] = []


def _sugerir(texto: str):
    st.session_state["sirea_quipu_pendiente"] = texto


def _contexto(pantalla: str) -> str:
    try:
        from app_pages.filtro_periodo import periodo_actual
        p = periodo_actual()
        extra = f" · viendo semana {p.semana}/{p.anio}" + (f" · red {p.red}" if p.red else "")
    except Exception:  # noqa: BLE001
        extra = ""
    return (str(pantalla or "") + extra)[:60]


def _responder(pregunta: str, pantalla: str):
    hist: List[Dict] = st.session_state.setdefault(CLAVE_HIST, [])
    if not _puede_preguntar():
        st.session_state["sirea_asist_error"] = (f"Llegó al límite de {_limite_hora()} preguntas por hora en esta sesión. "
                                                 "Vuelva a intentar en unos minutos.")
        return
    from src.agentes import agente_investigador
    try:
        r = agente_investigador.responder_pregunta(
            pregunta, [{"rol": t["rol"], "texto": t["texto"]} for t in hist], pantalla=_contexto(pantalla))
    except Exception:  # noqa: BLE001  (el detalle queda en la auditoría)
        st.session_state["sirea_asist_error"] = ("No pude consultar al proveedor de IA ahora. Revise "
                                                 "«Gobernanza de IA → Encender y apagar → Probar los proveedores».")
        return
    st.session_state.setdefault("sirea_asist_marcas", []).append(time.time())
    hist.append({"rol": "usuario", "texto": pregunta})
    hist.append({"rol": "asistente", "texto": r["texto"], "proveedor": r.get("proveedor"), "modelo": r.get("modelo"),
                 "herramientas": r.get("herramientas") or []})


def _disponible():
    try:
        from src.agentes import auditoria, estado
        from src.config import Config
        return Config.tiene_ia(), estado.esta_operativo(auditoria.AGENTE_INVESTIGADOR)
    except Exception:  # noqa: BLE001
        return False, False


@st.fragment
def quipu(pantalla: str):
    """Dibuja Quipu (botón flotante + cajita). Llamar una vez por pantalla del panel."""
    abierto = bool(st.session_state.get("sirea_quipu_abierto"))
    grande = bool(st.session_state.get("sirea_quipu_grande"))
    if abierto:
        _panel(pantalla, grande)
    with st.container(key="quipu_fab"):
        st.button("Cerrar" if abierto else NOMBRE, key="quipu_boton", on_click=_alternar, args=("sirea_quipu_abierto",),
                  icon=":material/close:" if abierto else ":material/forum:",
                  help="Quipu, su asistente de bolsillo: pregunte sobre los datos de SIREA (solo consulta).")


def _panel(pantalla: str, grande: bool):
    hay_ia, operativo = _disponible()
    hist: List[Dict] = st.session_state.setdefault(CLAVE_HIST, [])
    with st.container(key="quipu_caja_grande" if grande else "quipu_caja"):
        c1, c2, c3 = st.columns([5, 1, 1], vertical_alignment="center", gap="small")
        with c1:
            mostrar(f'<div class="quipu-cab"><span class="quipu-logo">{ICONO.format(t=26)}</span>'
                    f'<div><div class="quipu-nombre">{NOMBRE}</div>'
                    f'<div class="quipu-sub">Asistente de bolsillo · solo consulta</div></div></div>')
        c2.button("", key="quipu_tam", icon=":material/close_fullscreen:" if grande else ":material/open_in_full:",
                  on_click=_alternar, args=("sirea_quipu_grande",), help="Achicar" if grande else "Ampliar")
        c3.button("", key="quipu_nueva", icon=":material/restart_alt:", on_click=_nueva, help="Nueva conversación",
                  disabled=not hist)
        if not hay_ia:
            mostrar('<div class="quipu-vacio">Sin proveedor de IA configurado (GEMINI_API_KEY en el .env).</div>')
            return
        if not operativo:
            mostrar('<div class="quipu-vacio">Quipu está apagado. Un SUPER_ADMIN puede encenderlo en '
                    '«Gobernanza de IA → Encender y apagar».</div>')
            return

        pendiente = st.session_state.pop("sirea_quipu_pendiente", None)
        if pendiente:
            with st.spinner("Quipu está leyendo los datos…"):
                _responder(pendiente, pantalla)

        visibles = hist if grande else hist[-6:]
        if visibles:
            html = ""
            for t in visibles:
                if t["rol"] == "usuario":
                    html += tema_ia.burbuja_usuario(t["texto"])
                elif grande:
                    html += tema_ia.burbuja_asistente(t["texto"].replace(PIE, ""), t.get("proveedor"), t.get("modelo"),
                                                      t.get("herramientas") or [])
                else:
                    html += tema_ia.burbuja_asistente(t["texto"].replace(PIE, ""))
            # column-reverse: la caja abre mostrando lo último (sin JavaScript)
            mostrar(f'<div class="sirea-asist quipu-chat"><div>{html}</div></div>')
        else:
            mostrar(f'<div class="quipu-vacio">Hola, soy {NOMBRE}. Leo lo que hay en SIREA y le respondo en simple. '
                    'No envío ni cambio nada. Pruebe con:</div>')
            sug = SUGERENCIAS_BASE[:2] + ([SUGERENCIAS[pantalla]] if pantalla in SUGERENCIAS else SUGERENCIAS_BASE[2:])
            for i, s in enumerate(sug):
                st.button(s, key=f"quipu_sug_{i}", on_click=_sugerir, args=(s,), use_container_width=True)
        error = st.session_state.pop("sirea_asist_error", None)
        if error:
            st.warning(error)
        with st.form("quipu_form", clear_on_submit=True, border=False):
            pregunta = st.text_area("Su pregunta", key="quipu_q", height=70 if not grande else 90, max_chars=800,
                                    label_visibility="collapsed",
                                    placeholder="Ej.: ¿Qué le falta a la red Almenara? · ¿Quién envía por Arequipa?")
            enviar = st.form_submit_button("Preguntar", type="primary", use_container_width=True, icon=":material/send:")
        if enviar and (pregunta or "").strip():
            st.session_state["sirea_quipu_pendiente"] = pregunta.strip()
            st.rerun(scope="fragment")
        st.caption("Respuestas de IA sobre datos de SIREA: verifíquelas antes de difundirlas.")
