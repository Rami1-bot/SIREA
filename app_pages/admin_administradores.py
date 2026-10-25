# pages/admin_administradores.py
"""
Gestión de administradores del sistema (alta, baja, cambio de rol).
"""

import pandas as pd
import streamlit as st

from src.auth import get_auth_manager
from src.db_manager import get_db_manager
from utils.tema import mostrar, aviso, chip
from utils.tema_admin import tabla_df, panel_cab, esc
from utils.cuentas_ui import campos_nueva_password, campo_usuario_con_sugerencias, limpiar_campos_password


def _chip_rol(rol):
    return chip(esc(rol), "info" if str(rol) == "SUPER_ADMIN" else "mute")


def _chip_activo(valor):
    return chip("Activo", "ok", "check") if valor in (True, 1, "1", "true", "True") else chip("Inactivo", "mute")


def mostrar_gestion_admins():
    """Muestra la gestion de administradores."""

    auth_manager = get_auth_manager()
    db_manager = get_db_manager()

    if not auth_manager.es_super_admin(st.session_state.admin_token):
        mostrar(aviso("warn", "Acceso restringido", "Solo SUPER_ADMIN puede gestionar administradores."))
        return

    admins = db_manager.obtener_administradores()

    # ============================================================
    # LISTA
    # ============================================================
    with st.container(key="panel_admins_lista"):
        panel_cab("Administradores", f"{len(admins) if admins else 0} cuentas con acceso al panel")
        if admins:
            df = pd.DataFrame(admins)
            vista = pd.DataFrame({
                'Usuario': df.get('usuario'),
                'Nombre': df.get('nombre'),
                'Correo': df.get('email'),
                'Rol': df.get('rol'),
                'Estado': df.get('activo', pd.Series([True] * len(df))),
            })
            mostrar(tabla_df(vista, chips={'Rol': _chip_rol, 'Estado': _chip_activo}))
        else:
            mostrar(aviso("info", "No hay administradores registrados"))

    # ============================================================
    # AGREGAR
    # ============================================================
    with st.container(key="panel_admins_agregar"):
        panel_cab("Agregar administrador", "Complete los datos; la contraseña debe cumplir los requisitos de seguridad")
        pref = "adm_nuevo"
        k_nombre, k_correo, k_usuario = f"{pref}_nombre", f"{pref}_correo", f"{pref}_usuario"

        col1, col2 = st.columns(2)
        with col1:
            nuevo_nombre = st.text_input("Nombre completo", key=k_nombre)
        with col2:
            nuevo_email = st.text_input("Correo electrónico", key=k_correo)

        col3, col4 = st.columns(2)
        with col3:
            existentes = [a.get('usuario') for a in (admins or []) if a.get('usuario')]
            nuevo_usuario = campo_usuario_con_sugerencias(
                k_usuario, k_nombre, k_correo, ocupados=existentes,
            )
        with col4:
            nuevo_rol = st.selectbox("Rol", ["ADMIN", "SUPER_ADMIN"], key=f"{pref}_rol")

        nueva_password, nueva_password_confirm = campos_nueva_password(
            f"{pref}_pw",
            contexto=[nuevo_usuario, nuevo_nombre, nuevo_email],
            ofrecer_generador=True,
        )

        if st.button("Agregar administrador", type="primary", icon=":material/person_add:", key=f"{pref}_guardar"):
            if not (nuevo_usuario or "").strip() or not nueva_password or not (nuevo_nombre or "").strip() or not (nuevo_email or "").strip():
                st.error("Complete todos los campos: nombre, correo, usuario y contraseña.")
            elif nueva_password != nueva_password_confirm:
                st.error("Las contraseñas no coinciden.")
            else:
                # auth_manager.crear_admin() aplica la misma validación que el resto
                # del sistema (usuario, correo y política de contraseñas) y deja
                # constancia en el historial de auditoría (CREAR_ADMIN).
                try:
                    exito, mensaje = auth_manager.crear_admin(
                        usuario=nuevo_usuario.strip(),
                        password=nueva_password,
                        nombre=nuevo_nombre.strip(),
                        email=nuevo_email.strip(),
                        rol=nuevo_rol,
                    )
                    if exito:
                        for k in (k_nombre, k_correo, k_usuario, f"{pref}_rol"):
                            st.session_state.pop(k, None)
                        limpiar_campos_password(f"{pref}_pw")
                        st.toast(mensaje, icon=":material/check_circle:")
                        st.rerun()
                    else:
                        st.error(mensaje)
                except Exception as e:
                    st.error(f"Error al crear el administrador: {str(e)}")

    # ============================================================
    # ELIMINAR
    # ============================================================
    if admins:
        usuario_actual = (st.session_state.get('admin_usuario') or {}).get('usuario')
        usuarios_activos = [a['usuario'] for a in admins
                            if a.get('rol') != 'SUPER_ADMIN' and a['usuario'] != usuario_actual]
        with st.container(key="peligro_admins"):
            mostrar(aviso("bad", "Eliminar administrador",
                          "La cuenta se elimina y sus sesiones activas se cierran de inmediato. "
                          "La acción queda registrada en el historial."))
            if usuarios_activos:
                col1, col2, col3 = st.columns([1.2, 1.6, 1], vertical_alignment="bottom")
                with col1:
                    admin_a_eliminar = st.selectbox("Administrador a eliminar", usuarios_activos)
                with col2:
                    confirmar = st.checkbox(f"Confirmo que deseo eliminar a «{admin_a_eliminar}»", key="adm_confirma")
                with col3:
                    if st.button("Eliminar administrador", type="primary", use_container_width=True,
                                 icon=":material/delete:", key="adm_eliminar"):
                        if not confirmar:
                            st.warning("Marque la casilla de confirmación para eliminar.")
                        else:
                            # auth_manager.eliminar_admin() además deja registro
                            # en el log de auditoría y cierra cualquier sesión
                            # activa de ese administrador de inmediato.
                            exito, mensaje = auth_manager.eliminar_admin(admin_a_eliminar)
                            if exito:
                                st.toast(mensaje, icon=":material/check_circle:")
                                st.rerun()
                            else:
                                st.error(mensaje)
            else:
                st.caption("No hay administradores para eliminar (la cuenta SUPER_ADMIN y su propia cuenta no se pueden eliminar).")
