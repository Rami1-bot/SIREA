# utils/frecuentes.py
"""
Usuarios frecuentes.

Los datos del responsable (nombres, apellidos y correo) se guardan en el
navegador de la persona (localStorage), no en el servidor; así el siguiente
envío desde ese mismo equipo se completa con un clic, incluso días después.

El componente (components/frecuentes) es invisible: guarda, quita y lee la
lista. Esta capa solo lo envuelve.
"""

import uuid
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

_RUTA = Path(__file__).resolve().parent.parent / "components" / "frecuentes"
_componente = components.declare_component("sire_frecuentes", path=str(_RUTA))

CLAVE_ACCION = "_frec_accion"
_CAMPOS_FORM = ("input_nombres", "input_apellidos", "input_correo", "input_correo_repetido")


def almacen(accion: Optional[Dict] = None) -> List[Dict]:
    """
    Dibuja el componente invisible y devuelve la lista guardada en el navegador.
    `accion` (guardar / quitar / olvidar) se aplica una sola vez gracias a su nonce.
    """
    with st.container(key="sire_frec_wrap"):
        valor = _componente(accion=accion or st.session_state.get(CLAVE_ACCION), key="sire_frec", default=None)
    return [u for u in valor if isinstance(u, dict) and u.get("correo")] if isinstance(valor, list) else []


def guardar_tras_envio(nombres: str, apellidos: str, correo: str, codigo: str):
    """Pide al navegador recordar a esta persona (se llama en la pantalla de confirmación)."""
    almacen({"tipo": "guardar", "nonce": f"g-{codigo}",
             "datos": {"nombres": nombres, "apellidos": apellidos, "correo": correo}})


def _usar(usuario: Dict):
    """Callback del chip: completa los campos del formulario."""
    st.session_state["input_nombres"] = usuario.get("nombres", "")
    st.session_state["input_apellidos"] = usuario.get("apellidos", "")
    st.session_state["input_correo"] = usuario.get("correo", "")
    st.session_state["input_correo_repetido"] = usuario.get("correo", "")
    st.session_state.pop("chk_correo_noinst", None)


def _quitar(correo: str):
    st.session_state[CLAVE_ACCION] = {"tipo": "quitar", "correo": correo, "nonce": f"q-{uuid.uuid4().hex}"}


def _olvidar():
    st.session_state[CLAVE_ACCION] = {"tipo": "olvidar", "nonce": f"o-{uuid.uuid4().hex}"}


def panel(lista: List[Dict]):
    """Chips de usuarios frecuentes: un clic completa apellidos, nombres y correo."""
    if not lista:
        return
    from utils.tema import mostrar
    import html

    with st.container(key="sire_frecuentes"):
        mostrar('<div class="sire-frec-t">Usuarios frecuentes en este equipo</div>'
                '<div class="sire-frec-s">Haga clic en una persona para completar sus apellidos, nombres y correo. '
                'Los datos se guardan solo en este navegador.</div>')
        for i, u in enumerate(lista[:6]):
            c1, c2 = st.columns([12, 1], vertical_alignment="center")
            nombre = f"{u.get('apellidos', '')} {u.get('nombres', '')}".strip() or "Sin nombre"
            with c1:
                st.button(f"{nombre} · {u.get('correo', '')}", key=f"frec_usar_{i}", use_container_width=True,
                          icon=":material/person:", on_click=_usar, args=(u,))
            with c2:
                st.button("", key=f"frec_quitar_{i}", icon=":material/close:", help="Quitar de la lista",
                          on_click=_quitar, args=(u.get("correo", ""),))
        st.button("Olvidar todos", key="frec_olvidar", type="tertiary", icon=":material/delete:", on_click=_olvidar)
