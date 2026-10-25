# app_pages/admin_solicitudes_password.py
"""
Solicitudes de cambio de contraseña de las redes (solo SUPER_ADMIN).

Una red que ya cambió su contraseña genérica debe sustentar cualquier cambio
posterior. Aquí el SUPER_ADMIN revisa el sustento, intercambia mensajes con la
red y, si corresponde, aprueba: en ese momento se habilita el cambio de
contraseña en la pantalla de la red.
"""

import pandas as pd
import streamlit as st

from src.auth import get_auth_manager
from src.config import Config
from src.solicitudes_password import get_solicitudes_password, fecha_lima, parsear_fecha
from utils.hilo import hilo_html
from utils.tema import mostrar, aviso, chip, kpi
from utils.tema_admin import tabla_df, panel_cab, esc

_ESTADOS = {
    "PENDIENTE": ("Pendiente", "warn", "reloj"),
    "APROBADA": ("Aprobada", "ok", "check"),
    "COMPLETADA": ("Completada", "ok", "check"),
    "RECHAZADA": ("Rechazada", "bad", None),
    "CANCELADA": ("Cancelada", "mute", None),
    "VENCIDA": ("Vencida", "mute", None),
}

_FILTROS = {
    "Pendientes de respuesta": ["PENDIENTE"],
    "Aprobadas (cambio habilitado)": ["APROBADA"],
    "Todas": None,
}


def _chip_estado(estado: str) -> str:
    texto, tono, ico = _ESTADOS.get(estado, (estado, "mute", None))
    return chip(esc(texto), tono, ico) if ico else chip(esc(texto), tono)


def pendientes_para_aviso() -> int:
    """Cantidad de solicitudes esperando respuesta (0 si el módulo no está disponible)."""
    try:
        return get_solicitudes_password().pendientes()
    except Exception:
        return 0


def _identidad_admin():
    u = st.session_state.get('admin_usuario') or {}
    return u.get('usuario', 'SYSTEM'), u.get('nombre') or u.get('usuario', 'Administrador')


def _detalle(solicitudes, sol: dict):
    usuario, nombre = _identidad_admin()
    id_ = sol["id"]
    pend = sol.get("estado") == "PENDIENTE"

    with st.container(key="panel_sol_detalle"):
        panel_cab(f"Solicitud {esc(sol.get('codigo', ''))}",
                  f"Red {esc(sol.get('red', ''))} · enviada el {fecha_lima(sol.get('fecha_creacion'))}")
        c1, c2, c3 = st.columns(3)
        with c1:
            mostrar(f'<div class="sire-dato"><small>Solicitante</small><b>{esc(sol.get("nombre"))}</b></div>')
        with c2:
            mostrar(f'<div class="sire-dato"><small>Correo</small><b>{esc(sol.get("correo"))}</b></div>')
        with c3:
            mostrar(f'<div class="sire-dato"><small>Estado</small>{_chip_estado(sol.get("estado", ""))}</div>')

        if sol.get("estado") == "APROBADA":
            mostrar(aviso("ok", "Cambio habilitado",
                          f"Aprobada por {esc(sol.get('resuelto_por'))}. La red puede cambiar su contraseña hasta el "
                          f"{fecha_lima(parsear_fecha(sol.get('fecha_vencimiento')))} (hora de Lima)."))
        elif sol.get("estado") in ("RECHAZADA", "VENCIDA", "CANCELADA", "COMPLETADA") and sol.get("fecha_resolucion"):
            mostrar(aviso("info", "Solicitud cerrada", f"Resuelta el {fecha_lima(sol.get('fecha_resolucion'))}."))

        mostrar('<div style="height:6px"></div>')
        mostrar(hilo_html(solicitudes.mensajes(id_), propio="ADMIN"))

        if not pend:
            return

        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown("**Responder a la red**")
        resp = st.text_area("Mensaje para la red", key=f"sol_adm_resp_{id_}", height=100,
                            placeholder="Por ejemplo: indique el nombre de la persona que dejó de ser responsable.",
                            label_visibility="collapsed")
        if st.button("Enviar mensaje a la red", key=f"sol_adm_env_{id_}", icon=":material/send:"):
            ok, msg = solicitudes.responder_admin(id_, usuario, nombre, resp)
            if ok:
                st.session_state.pop(f"sol_adm_resp_{id_}", None)
                st.toast(msg, icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(msg)

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(key="panel_sol_aprobar"):
            panel_cab("Aprobar el cambio",
                      f"La red podrá cambiar su contraseña durante {Config.HORAS_VALIDEZ_CAMBIO_PASSWORD} horas")
            msg_apr = st.text_area("Mensaje para la red (opcional)", key=f"sol_apr_msg_{id_}", height=80,
                                   placeholder="Su solicitud fue aprobada. Ya puede elegir su nueva contraseña.")
            conf = st.checkbox("Revisé el sustento y autorizo el cambio de contraseña", key=f"sol_apr_ok_{id_}")
            if st.button("Aprobar y habilitar el cambio", type="primary", icon=":material/check_circle:",
                         key=f"sol_apr_btn_{id_}"):
                if not conf:
                    st.info("Marque la casilla de confirmación para aprobar.")
                else:
                    ok, msg = solicitudes.aprobar(id_, usuario, nombre, msg_apr)
                    if ok:
                        st.toast(msg, icon=":material/check_circle:")
                        st.rerun()
                    else:
                        st.error(msg)
    with col_b:
        with st.container(key="peligro_sol_rechazar"):
            mostrar(aviso("bad", "Rechazar la solicitud",
                          "Se informa a la red con el motivo. Podrá volver a solicitar con más sustento."))
            motivo = st.text_area("Motivo del rechazo", key=f"sol_rec_msg_{id_}", height=80,
                                  placeholder="Explique por qué no se aprueba.")
            if st.button("Rechazar solicitud", type="primary", icon=":material/block:", key=f"sol_rec_btn_{id_}"):
                ok, msg = solicitudes.rechazar(id_, usuario, nombre, motivo)
                if ok:
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.error(msg)


def mostrar_solicitudes_password():
    """Pantalla «Solicitudes de contraseña» (solo SUPER_ADMIN)."""
    auth = get_auth_manager()
    if not auth.es_super_admin(st.session_state.get('admin_token')):
        mostrar(aviso("warn", "Acceso restringido", "Solo SUPER_ADMIN puede revisar estas solicitudes."))
        return

    solicitudes = get_solicitudes_password()
    if not solicitudes.disponible():
        mostrar(aviso(
            "info", "Falta crear las tablas de solicitudes",
            "Ejecute el script <strong>sql/09_solicitudes_cambio_password.sql</strong> en el SQL Editor de Supabase "
            "y recargue esta pantalla. Mientras tanto, las redes no pueden cambiar su contraseña por su cuenta."))
        return

    todas = solicitudes.listar(limit=200)
    pendientes = [s for s in todas if s.get("estado") == "PENDIENTE"]
    vigentes = [s for s in todas if s.get("estado") == "APROBADA"]

    k1, k2, k3 = st.columns(3)
    with k1:
        mostrar(kpi("Pendientes de respuesta", len(pendientes), "Esperan su revisión", "warn" if pendientes else None, "mensaje"))
    with k2:
        mostrar(kpi("Cambio habilitado", len(vigentes), "Aprobadas aún sin usar", "ok" if vigentes else None, "check"))
    with k3:
        mostrar(kpi("Solicitudes registradas", len(todas), "Últimas 200"))

    with st.container(key="panel_sol_lista"):
        panel_cab("Solicitudes de las redes", "Elija una para leer el sustento, responder, aprobar o rechazar")
        filtro = st.radio("Mostrar", list(_FILTROS), horizontal=True, key="sol_filtro",
                          label_visibility="collapsed")
        estados = _FILTROS[filtro]
        lista = [s for s in todas if estados is None or s.get("estado") in estados]
        if not lista:
            mostrar('<div class="sire-vacio">No hay solicitudes en esta vista.</div>')
            return
        vista = pd.DataFrame({
            'Código': [s.get('codigo') for s in lista],
            'Red': [s.get('red') for s in lista],
            'Solicitante': [s.get('nombre') for s in lista],
            'Fecha': [fecha_lima(s.get('fecha_creacion')) for s in lista],
            'Estado': [_chip_estado(s.get('estado', '')) for s in lista],
        })
        mostrar(tabla_df(vista, crudas=('Estado',)))

        etiquetas = {f"{s.get('codigo')} · {s.get('red')} · {_ESTADOS.get(s.get('estado'), (s.get('estado'),))[0]}": s
                     for s in lista}
        elegida = st.selectbox("Solicitud a revisar", list(etiquetas), key="sol_elegida")

    _detalle(solicitudes, etiquetas[elegida])
