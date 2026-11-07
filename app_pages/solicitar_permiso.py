# app_pages/solicitar_permiso.py
"""
Cuadro «Solicitar acceso» (v7.6) y avisos de «sin permiso», reutilizables en las pantallas protegidas.

  aviso_sin_permiso(...)   mensaje claro de por qué algo está bloqueado y qué hacer
  cuadro_solicitud(...)    formulario siempre habilitado para pedir el permiso a oiis.winepi

El cuadro NO depende del permiso: cualquier cuenta del panel puede pedirlo.
"""

from typing import Iterable, List, Optional

import pandas as pd
import streamlit as st

from app_pages.admin_helpers import actor_actual
from src.config import Config
from src.permisos import PERMISOS, es_principal, get_permisos
from src.solicitudes_password import fecha_lima
from src.solicitudes_permiso import MAX_MENSAJE, MIN_MENSAJE, get_solicitudes_permiso
from utils.tema import aviso, chip, mostrar
from utils.tema_admin import esc, panel_cab, tabla_df

PRINCIPAL = Config.SUPERADMIN_PRINCIPAL

_TONO = {"PENDIENTE": ("Pendiente", "warn", "reloj"), "APROBADA": ("Aprobada", "ok", "check"),
         "RECHAZADA": ("Rechazada", "bad", "alerta"), "CANCELADA": ("Cancelada", "mute", None)}


def chip_solicitud(estado: str) -> str:
    texto, tono, ico = _TONO.get(estado, (estado, "mute", None))
    return chip(texto, tono, ico)


def aviso_sin_permiso(permiso: str, que_no_puede: str, donde: str = "el cuadro «Solicitar acceso» de más abajo") -> None:
    """Aviso ámbar que explica por qué hay botones bloqueados y cómo resolverlo."""
    nombre = PERMISOS[permiso][0]
    mostrar(aviso("warn", que_no_puede,
                  f"Su cuenta no tiene el permiso <strong>«{esc(nombre)}»</strong>. Ese permiso lo asigna solo el SUPER_ADMIN principal "
                  f"(<strong>{esc(PRINCIPAL)}</strong>). Puede pedirlo en {donde}; mientras tanto puede mirar la información."))


def _faltantes(actor: dict, permisos: Iterable[str]) -> List[str]:
    p = get_permisos()
    return [x for x in permisos if x in PERMISOS and not p.tiene(actor, x)]


def cuadro_solicitud(permisos: Iterable[str], clave: str, subtitulo: Optional[str] = None) -> None:
    """
    Formulario para pedir uno de `permisos` (solo se ofrecen los que la cuenta no tiene).
    No se muestra al SUPER_ADMIN principal ni a quien ya tiene todos. Siempre está habilitado.
    """
    actor = actor_actual()
    if es_principal(actor):
        return
    faltan = _faltantes(actor, list(permisos))
    if not faltan:
        return
    sol = get_solicitudes_permiso()
    usuario = actor.get("usuario", "")
    ver = st.session_state.get(f"{clave}_ver", 0)

    with st.container(key=f"panel_solicitar_{clave}"):
        panel_cab("Solicitar acceso", subtitulo or f"Pídale el permiso a {PRINCIPAL}: le llega por correo y le responde aquí y por correo")
        resultado = st.session_state.pop(f"{clave}_resultado", None)
        if resultado:
            mostrar(aviso(resultado[0], resultado[1]))

        if len(faltan) > 1:
            permiso = st.selectbox("¿Qué permiso necesita?", faltan, format_func=lambda p: PERMISOS[p][0], key=f"{clave}_perm_{ver}")
        else:
            permiso = faltan[0]
            st.markdown(f"**Permiso:** {PERMISOS[permiso][0]}")
        st.caption(PERMISOS[permiso][1])

        pendiente = sol.pendiente_de(usuario, permiso) if sol.disponible() else None
        if pendiente:
            mostrar(aviso("info", "Su solicitud está pendiente",
                          f"La envió el {esc(fecha_lima(pendiente.get('creada_en')))} y espera la respuesta de {esc(PRINCIPAL)}. "
                          "Le llegará un correo cuando la responda."))
            with st.expander("Ver lo que escribió"):
                st.write(pendiente.get("mensaje") or "")
            if st.button("Cancelar mi solicitud", key=f"{clave}_cancelar", icon=":material/close:"):
                ok, msg = sol.cancelar(actor, pendiente["id"])
                st.session_state[f"{clave}_resultado"] = ("ok" if ok else "bad", msg)
                st.rerun()
        else:
            mensaje = st.text_area(
                "¿Para qué lo necesita? (obligatorio)", key=f"{clave}_msg_{ver}", max_chars=MAX_MENSAJE, height=100,
                placeholder="Ej.: Necesito ampliar la fecha de corte de la semana 41 porque dos redes tuvieron falla de conectividad.",
                help=f"Mínimo {MIN_MENSAJE} caracteres. Entre más claro, más rápido se responde.")
            if st.button("Enviar solicitud", type="primary", icon=":material/send:", key=f"{clave}_enviar"):
                ok, msg = sol.crear(actor, permiso, mensaje)
                st.session_state[f"{clave}_resultado"] = ("ok" if ok else "warn", msg)
                if ok:
                    st.session_state[f"{clave}_ver"] = ver + 1     # vacía el cuadro de texto
                st.rerun()

        previas = sol.listar(usuario, limite=5) if sol.disponible() else []
        if previas:
            st.caption("Mis últimas solicitudes")
            df = pd.DataFrame({
                "Permiso": [PERMISOS.get(s["permiso"], (s["permiso"],))[0] for s in previas],
                "Estado": [chip_solicitud(s["estado"]) for s in previas],
                "Enviada": [fecha_lima(s.get("creada_en")) for s in previas],
                "Respuesta": [s.get("respuesta") or "—" for s in previas]})
            mostrar(tabla_df(df, crudas=("Estado",)))
