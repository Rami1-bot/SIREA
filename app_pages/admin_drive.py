# pages/admin_drive.py
"""
Gestión de la integración con Google Drive.
"""

import pandas as pd
import streamlit as st

from src.config import Config
from src.db_manager import get_db_manager
from src.drive_manager import get_drive_manager
from utils.tema import mostrar, aviso, chip, kpi
from utils.tema_admin import tabla_df, panel_cab, esc
from app_pages.admin_helpers import requerir_admin


def _chip_activo(valor):
    return chip("Activa", "ok", "check") if valor in (True, 1, "1", "true", "True") else chip("Inactiva", "mute")


def _ids_reservados():
    """IDs de las carpetas especiales (duplicados y respaldos): no deben usarse como carpeta de reportes."""
    return {i for i in (Config.GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID, Config.GOOGLE_DRIVE_FOLDER_BACKUPS_ID) if i}


def _id_corto(valor: str) -> str:
    v = (valor or "").strip()
    return f"{v[:5]}…{v[-4:]}" if len(v) > 12 else (v or "—")


def _panel_carpetas_especiales(drive_manager):
    """Carpetas que se configuran en el servidor (.env): principal, duplicados y respaldos."""
    especiales = [
        ("Reportes (principal)", "GOOGLE_DRIVE_FOLDER_ID", Config.GOOGLE_DRIVE_FOLDER_ID,
         "Aquí se guardan los envíos de las redes."),
        ("Duplicados", "GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID", Config.GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID,
         "Envíos repetidos a propósito. Si falta, se usa una subcarpeta DUPLICADOS en la principal."),
        ("Respaldos (BACKUPS)", "GOOGLE_DRIVE_FOLDER_BACKUPS_ID", Config.GOOGLE_DRIVE_FOLDER_BACKUPS_ID,
         "Cada respaldo crea una subcarpeta con su fecha y hora exactas."),
    ]
    with st.container(key="panel_drive_especiales"):
        panel_cab("Carpetas configuradas en el servidor",
                  "Se definen en el archivo .env; desde aquí solo se comprueba su acceso")
        for i, (titulo, variable, valor, ayuda) in enumerate(especiales):
            c1, c2, c3 = st.columns([1.3, 2, 1], vertical_alignment="center")
            with c1:
                estado = chip("Configurada", "ok", "check") if valor else chip("Sin configurar", "warn")
                mostrar(f'<div class="sire-dato"><small>{esc(titulo)}</small><b>{esc(_id_corto(valor))}</b>{estado}</div>')
            with c2:
                st.caption(f"{ayuda} Variable: {variable}" + ("" if valor else ". Agréguela al .env."))
            with c3:
                if valor and st.button("Probar acceso", key=f"drive_probar_{i}", icon=":material/lan:",
                                       use_container_width=True):
                    r = drive_manager.probar_carpeta(valor)
                    if r["ok"] and r["papelera"]:
                        mostrar(aviso("ok", f"«{esc(r['nombre'])}»: acceso correcto", esc(r["detalle"])))
                    elif r["ok"]:
                        mostrar(aviso("warn", f"«{esc(r['nombre'])}»: acceso parcial", esc(r["detalle"])))
                    else:
                        mostrar(aviso("bad", "No se pudo acceder a la carpeta", esc(r["detalle"])))


def mostrar_gestion_drive():
    """Muestra la gestion de Google Drive."""

    requerir_admin()

    db_manager = get_db_manager()
    try:
        drive_manager = get_drive_manager()
    except Exception as e:
        mostrar(aviso("bad", "No se pudo conectar con Google Drive",
                      f"{esc(str(e))}<br>Revise que la credencial (credentials/service_account.json) exista y sea legible "
                      "por el contenedor, y que la carpeta esté compartida con la cuenta de servicio."))
        return

    # ============================================================
    # ESTADO DE LA CONEXION
    # ============================================================
    try:
        conexion_ok, mensaje = drive_manager.verificar_conexion()
        if conexion_ok and 'LOCAL' in str(mensaje).upper():
            mostrar(aviso("info", "Modo local", "Los archivos se guardan en el servidor, sin Google Drive. "
                          "Configure la cuenta de servicio para usar Drive."))
        elif conexion_ok:
            mostrar(aviso("ok", "Conexión con Drive activa", esc(mensaje)))
        else:
            if "404" in mensaje or "File not found" in mensaje:
                mostrar(aviso(
                    "warn", "La carpeta raíz configurada no es accesible",
                    "Verifique que el ID (GOOGLE_DRIVE_FOLDER_ID) sea correcto y que la cuenta de servicio sea "
                    "miembro de la Unidad compartida (o tenga acceso de Editor a la carpeta). El ID se configura "
                    f"en el servidor (.env), no desde esta pantalla.<br><small>Detalle técnico: {esc(mensaje)}</small>"))
            else:
                mostrar(aviso("bad", "Error de conexión con Drive", esc(mensaje)))
    except Exception as e:
        mostrar(aviso(
            "warn", "No se pudo conectar con Drive",
            f"{esc(str(e))}<br>Asegúrese de que el archivo de credenciales "
            "(credentials/service_account.json) esté configurado correctamente."))

    carpeta_activa = db_manager.obtener_carpeta_activa()
    carpetas = db_manager.obtener_carpetas_drive()

    c1, c2, c3 = st.columns(3)
    with c1:
        mostrar(kpi("Carpeta activa", esc(carpeta_activa['nombre']) if carpeta_activa else "Carpeta raíz",
                    "Carpeta de referencia de los reportes", None, "nube"))
    with c2:
        mostrar(kpi("Carpetas registradas", len(carpetas) if carpetas else 0, "Registro informativo", None, "dash"))
    with c3:
        inactivas_n = len([c for c in (carpetas or []) if c.get('activo', 0) == 0])
        mostrar(kpi("Carpetas inactivas", inactivas_n, "Se pueden activar o eliminar", None, "reloj"))

    if not carpeta_activa:
        mostrar(aviso("info", "Se usa la carpeta raíz del servidor",
                      "Los reportes se guardan en la carpeta raíz configurada en el servidor "
                      "(GOOGLE_DRIVE_FOLDER_ID). El registro de carpetas de abajo es opcional e informativo."))

    _panel_carpetas_especiales(drive_manager)

    # ============================================================
    # LISTA DE CARPETAS
    # ============================================================
    with st.container(key="panel_drive_lista"):
        panel_cab("Carpetas de Drive", "Carpetas registradas en el sistema")
        if carpetas:
            df = pd.DataFrame(carpetas)
            df = df.drop(columns=[c for c in ('id',) if c in df.columns])
            _nombres = {'nombre': 'Nombre', 'folder_id': 'ID de carpeta', 'capacidad_maxima': 'Capacidad máxima (MB)',
                        'activo': 'Estado', 'fecha_creacion': 'Creada', 'created_at': 'Creada'}
            df.columns = [_nombres.get(str(c), str(c).replace('_', ' ').capitalize()) for c in df.columns]
            chips = {c: _chip_activo for c in df.columns if c == 'Estado'}
            mostrar(tabla_df(df, chips=chips))
        else:
            mostrar(aviso("info", "No hay carpetas registradas"))

    # ============================================================
    # AGREGAR
    # ============================================================
    with st.container(key="panel_drive_agregar"):
        panel_cab("Agregar carpeta", "Registro opcional de una carpeta de Drive")
        with st.form("form_agregar_carpeta", border=False):
            col1, col2, col3 = st.columns([1.2, 1.4, 1])
            with col1:
                nombre_carpeta = st.text_input("Nombre de la carpeta")
            with col2:
                folder_id = st.text_input("ID de la carpeta en Drive")
            with col3:
                capacidad_maxima = st.number_input("Capacidad máxima (MB)", min_value=100, max_value=10000, value=1000)

            if st.form_submit_button("Agregar carpeta", type="primary", icon=":material/create_new_folder:"):
                if not nombre_carpeta or not folder_id:
                    st.error("Nombre e ID son obligatorios.")
                else:
                    if db_manager.crear_carpeta_drive(nombre_carpeta, folder_id, capacidad_maxima):
                        st.toast(f"Carpeta {nombre_carpeta} agregada.", icon=":material/check_circle:")
                        st.rerun()
                    else:
                        st.error("No se pudo agregar la carpeta.")

    # ============================================================
    # ACTIVAR / ELIMINAR
    # ============================================================
    if carpetas:
        carpetas_inactivas = [c for c in carpetas if c.get('activo', 0) == 0]

        with st.container(key="panel_drive_gestion"):
            panel_cab("Activar una carpeta", "Marca la carpeta de referencia de los reportes")
            reservados = _ids_reservados()
            activables = [c for c in carpetas_inactivas if str(c.get('folder_id', '')).strip() not in reservados]
            bloqueadas = [c for c in carpetas_inactivas if str(c.get('folder_id', '')).strip() in reservados]
            if bloqueadas:
                mostrar(aviso("info", "Algunas carpetas están reservadas",
                              "«" + "», «".join(esc(c['nombre']) for c in bloqueadas) + "» es la carpeta de duplicados "
                              "o de respaldos del servidor. No se activa como carpeta de reportes para no mezclar "
                              "los envíos normales con los duplicados o los respaldos."))
            if activables:
                col1, col2, _ = st.columns([1.5, 1, 1.5], vertical_alignment="bottom")
                with col1:
                    carpeta_a_activar = st.selectbox(
                        "Carpeta a activar", [c['nombre'] for c in activables], key="drive_activar_sel"
                    )
                with col2:
                    if st.button("Activar carpeta", use_container_width=True, type="primary", key="drive_activar"):
                        carpeta_id = next(c['id'] for c in activables if c['nombre'] == carpeta_a_activar)
                        ok, detalle = db_manager.cambiar_carpeta_activa_detallado(carpeta_id)
                        if ok:
                            st.toast(f"Carpeta «{carpeta_a_activar}» activada.", icon=":material/check_circle:")
                            st.rerun()
                        else:
                            mostrar(aviso("bad", "No se pudo activar la carpeta", esc(detalle)))
                st.caption("El destino real de los envíos lo define GOOGLE_DRIVE_FOLDER_ID en el servidor.")
            else:
                st.caption("No hay carpetas inactivas para activar.")

        if carpetas_inactivas:
            with st.container(key="peligro_drive"):
                mostrar(aviso("bad", "Eliminar una carpeta inactiva",
                              "Solo se quita el registro del sistema; los archivos de Drive no se borran."))
                col1, col2, col3 = st.columns([1.2, 1.6, 1], vertical_alignment="bottom")
                with col1:
                    carpeta_a_eliminar = st.selectbox(
                        "Carpeta a eliminar", [c['nombre'] for c in carpetas_inactivas], key="drive_eliminar_sel"
                    )
                with col2:
                    confirmar = st.checkbox(f"Confirmo que deseo eliminar «{carpeta_a_eliminar}»", key="drive_confirma")
                with col3:
                    if st.button("Eliminar carpeta", type="primary", use_container_width=True,
                                 icon=":material/delete:", key="drive_eliminar"):
                        if not confirmar:
                            st.warning("Marque la casilla de confirmación para eliminar.")
                        else:
                            carpeta_id = next(c['id'] for c in carpetas_inactivas if c['nombre'] == carpeta_a_eliminar)
                            if db_manager.eliminar_carpeta_drive(carpeta_id):
                                st.toast(f"Carpeta «{carpeta_a_eliminar}» eliminada.", icon=":material/check_circle:")
                                st.rerun()
                            else:
                                st.error("No se pudo eliminar. Solo se pueden eliminar carpetas inactivas.")
