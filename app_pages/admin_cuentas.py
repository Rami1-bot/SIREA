# app_pages/admin_cuentas.py
"""
Cuentas del panel: cambio de datos y de contraseñas de administradores y
SUPER_ADMIN. Solo lo puede usar el SUPER_ADMIN principal (usuario definido en
SUPERADMIN_PRINCIPAL, por defecto «oiis.winepi»).

Alta y baja de cuentas siguen en «Administradores»; aquí se corrige y se
mantiene lo que ya existe (datos, nombre de usuario y contraseñas).
"""

import pandas as pd
import streamlit as st

from src.auth import get_auth_manager
from src.config import Config
from src.db_manager import get_db_manager
from utils.tema import mostrar, aviso, chip
from utils.tema_admin import tabla_df, panel_cab, esc
from utils.cuentas_ui import campos_nueva_password, limpiar_campos_password


def _chip_rol(rol):
    return chip(esc(rol), "info" if str(rol) == "SUPER_ADMIN" else "mute")


def _chip_activo(valor):
    return chip("Activo", "ok", "check") if valor in (True, 1, "1", "true", "True") else chip("Inactivo", "mute")


def _es_principal(usuario) -> bool:
    return str(usuario or "").strip().lower() == Config.SUPERADMIN_PRINCIPAL


def _etiqueta(a) -> str:
    marca = " (cuenta principal)" if _es_principal(a.get('usuario')) else ""
    return f"{a.get('usuario')} · {a.get('nombre', '')}{marca}"


def _panel_lista(admins):
    with st.container(key="panel_cuentas_lista"):
        panel_cab("Cuentas con acceso al panel",
                  f"{len(admins)} cuenta(s). Aquí se corrigen sus datos y se restablecen sus contraseñas")
        df = pd.DataFrame(admins)
        vista = pd.DataFrame({
            'Usuario': df.get('usuario'),
            'Nombre': df.get('nombre'),
            'Correo': df.get('email'),
            'Rol': df.get('rol'),
            'Estado': df.get('activo', pd.Series([True] * len(df))),
        })
        mostrar(tabla_df(vista, chips={'Rol': _chip_rol, 'Estado': _chip_activo}))


def _panel_editar_datos(auth, token, admins):
    with st.container(key="panel_cuentas_datos"):
        panel_cab("Modificar datos de una cuenta",
                  "Nombre, correo, rol y estado. Si cambia el rol o desactiva la cuenta, su sesión se cierra")
        etiquetas = {_etiqueta(a): a for a in admins}
        # Tras cambiar un usuario, se deja seleccionada la misma cuenta con su nombre nuevo.
        pendiente = st.session_state.get("cta_sel_pendiente")
        if pendiente in etiquetas:
            st.session_state["cta_datos_sel"] = pendiente
        elegida = st.selectbox("Cuenta", list(etiquetas), key="cta_datos_sel")
        a = etiquetas[elegida]
        u = a['usuario']
        principal = _es_principal(u)

        c1, c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Nombre completo", value=a.get('nombre') or "", key=f"cta_nombre_{u}")
        with c2:
            correo = st.text_input("Correo electrónico", value=a.get('email') or "", key=f"cta_correo_{u}")
        c3, c4 = st.columns(2)
        with c3:
            roles = ["ADMIN", "SUPER_ADMIN"]
            rol = st.selectbox("Rol", roles, index=roles.index(a.get('rol')) if a.get('rol') in roles else 0,
                               key=f"cta_rol_{u}", disabled=principal)
        with c4:
            activo = st.toggle("Cuenta activa", value=bool(a.get('activo', True)),
                               key=f"cta_activo_{u}", disabled=principal)
        if principal:
            mostrar(aviso("info", "Cuenta principal",
                          "La cuenta principal conserva siempre el rol SUPER_ADMIN y no se puede desactivar. "
                          "Sí puede cambiar su nombre y correo."))

        if st.button("Guardar cambios", type="primary", icon=":material/save:", key=f"cta_guardar_{u}"):
            ok, msg = auth.actualizar_datos_cuenta(token, u, nombre, correo, rol, activo)
            if ok:
                st.toast(msg, icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(msg)


def _panel_cambiar_usuario(auth, token, admins):
    with st.container(key="panel_cuentas_usuario"):
        panel_cab("Cambiar el nombre de usuario",
                  "El usuario con el que la persona ingresa al panel. Su sesión se cierra y debe ingresar con el nuevo")
        etiquetas = {_etiqueta(a): a for a in admins}
        if st.session_state.get("cta_sel_pendiente") in etiquetas:
            st.session_state["cta_user_sel"] = st.session_state["cta_sel_pendiente"]
        elegida = st.selectbox("Cuenta", list(etiquetas), key="cta_user_sel")
        a = etiquetas[elegida]
        u = a['usuario']
        if _es_principal(u):
            mostrar(aviso("info", "Usuario protegido",
                          f"El usuario de la cuenta principal («{esc(u)}») no se puede cambiar. "
                          "Tampoco se puede asignar a otra cuenta."))
            return
        nuevo = st.text_input("Nuevo nombre de usuario", value=u, key=f"cta_user_{u}",
                              help="3 a 40 caracteres: letras, números, punto, guion o guion bajo. "
                                   "Conviene que identifique a la persona, por ejemplo inicial + apellido.")
        if st.button("Cambiar usuario", type="primary", icon=":material/badge:", key=f"cta_user_btn_{u}"):
            nuevo_limpio = (nuevo or "").strip()
            if nuevo_limpio == u:
                st.info("El usuario es el mismo; escriba uno distinto.")
            else:
                ok, msg = auth.cambiar_usuario_cuenta(token, u, nuevo_limpio)
                if ok:
                    st.session_state.pop(f"cta_user_{u}", None)
                    st.session_state["cta_sel_pendiente"] = f"{nuevo_limpio} · {a.get('nombre', '')}"
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.error(msg)


def _panel_restablecer(auth, token, admins, usuario_actual):
    otros = [a for a in admins if a.get('usuario') != usuario_actual]
    with st.container(key="panel_cuentas_password"):
        panel_cab("Restablecer la contraseña de otra cuenta",
                  "Úselo cuando alguien olvidó su contraseña o cuando haya dudas sobre su seguridad")
        if not otros:
            st.caption("No hay otras cuentas para restablecer.")
            return
        etiquetas = {_etiqueta(a): a for a in otros}
        if st.session_state.get("cta_sel_pendiente") in etiquetas:
            st.session_state["cta_pw_sel"] = st.session_state["cta_sel_pendiente"]
        elegida = st.selectbox("Cuenta", list(etiquetas), key="cta_pw_sel")
        a = etiquetas[elegida]
        u = a['usuario']
        pref = f"cta_pw_{u}"

        nueva, confirmar = campos_nueva_password(
            pref, contexto=[u, a.get('nombre'), a.get('email')], ofrecer_generador=True)
        confirma = st.checkbox(
            f"Confirmo que deseo cambiar la contraseña de «{u}». Sus sesiones abiertas se cerrarán.",
            key=f"{pref}_ok")
        if st.button("Restablecer contraseña", type="primary", icon=":material/lock_reset:", key=f"{pref}_btn"):
            if not nueva:
                st.error("Ingrese la nueva contraseña.")
            elif nueva != confirmar:
                st.error("Las contraseñas no coinciden.")
            elif not confirma:
                st.info("Marque la casilla de confirmación para continuar.")
            else:
                ok, msg = auth.restablecer_password_admin(token, u, nueva)
                if ok:
                    limpiar_campos_password(pref)
                    st.session_state.pop(f"{pref}_ok", None)
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.error(msg)


def _panel_mi_password(auth, token, usuario_actual):
    with st.container(key="panel_cuentas_mia"):
        panel_cab("Mi contraseña",
                  "Cambie la contraseña de su propia cuenta. Se le pedirá volver a ingresar")
        actual = st.text_input("Contraseña actual", type="password", key="cta_mia_actual",
                               autocomplete="current-password")
        nueva, confirmar = campos_nueva_password(
            "cta_mia", contexto=[usuario_actual.get('usuario'), usuario_actual.get('nombre'),
                                 usuario_actual.get('email')], actual=actual)
        if st.button("Cambiar mi contraseña", type="primary", icon=":material/key:", key="cta_mia_btn"):
            if not actual:
                st.error("Ingrese su contraseña actual.")
            elif not nueva:
                st.error("Ingrese la nueva contraseña.")
            elif nueva != confirmar:
                st.error("Las contraseñas no coinciden.")
            else:
                ok, msg = auth.cambiar_password_propia(token, actual, nueva)
                if ok:
                    # El cambio cierra todas las sesiones de la cuenta: se vuelve al ingreso.
                    st.session_state.admin_logueado = False
                    st.session_state.admin_token = None
                    st.session_state.admin_usuario = None
                    st.session_state.pop("cta_mia_actual", None)
                    limpiar_campos_password("cta_mia")
                    st.session_state.cambio_password_ok = True
                    st.rerun()
                else:
                    st.error(msg)


def mostrar_cuentas_panel():
    """Pantalla «Cuentas del panel» (solo SUPER_ADMIN principal)."""
    auth = get_auth_manager()
    token = st.session_state.get('admin_token')

    if not auth.es_superadmin_principal(token):
        mostrar(aviso("warn", "Acceso restringido",
                      "Esta sección es exclusiva de la cuenta SUPER_ADMIN principal del sistema."))
        return

    usuario_actual = auth.obtener_usuario_actual(token) or {}
    admins = get_db_manager().obtener_administradores() or []
    if not admins:
        mostrar(aviso("info", "No hay cuentas registradas"))
        return

    _panel_lista(admins)
    _panel_editar_datos(auth, token, admins)
    _panel_cambiar_usuario(auth, token, admins)
    _panel_restablecer(auth, token, admins, usuario_actual.get('usuario'))
    _panel_mi_password(auth, token, usuario_actual)
    st.session_state.pop("cta_sel_pendiente", None)
