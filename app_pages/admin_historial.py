# pages/admin_historial.py
"""
Historial y logs del sistema: consulta y limpieza de registros.
"""

import pandas as pd
import streamlit as st

from src.auth import get_auth_manager
from src.db_manager import get_db_manager
from utils.tema import mostrar, aviso
from utils.tema_admin import tabla_df, panel_cab, descargas


def _limpieza(db_manager, clave: str, titulo: str, texto: str, dias: int, boton: str):
    """Bloque de limpieza de logs con confirmación explícita (solo oiis.winepi; queda en la auditoría)."""
    with st.container(key=f"peligro_logs_{clave}"):
        mostrar(aviso("bad", titulo, texto))
        col1, col2 = st.columns([2, 1], vertical_alignment="center")
        with col1:
            confirmar = st.checkbox("Confirmo que deseo eliminarlos", key=f"logs_confirma_{clave}")
        with col2:
            if st.button(boton, type="primary", use_container_width=True,
                         icon=":material/delete:", key=f"logs_btn_{clave}"):
                if not confirmar:
                    st.warning("Marque la casilla de confirmación para eliminar.")
                else:
                    from src.auditoria import AuditoriaError, get_auditoria
                    actor = auth_actor()
                    try:
                        get_auditoria().registrar(actor.get("usuario", ""), "LOGS_LIMPIADOS", "SISTEMA", rol=actor.get("rol"),
                                                  objeto=("todos" if dias == 0 else f"más de {dias} días"), resultado="PENDIENTE",
                                                  detalle={"dias": dias}, obligatorio=get_auditoria().disponible())
                    except AuditoriaError as e:
                        st.error(str(e))
                        return
                    with st.spinner("Eliminando registros..."):
                        eliminados = db_manager.limpiar_logs_antiguos(dias)
                    get_auditoria().registrar(actor.get("usuario", ""), "LOGS_LIMPIADOS", "SISTEMA", rol=actor.get("rol"),
                                              objeto=f"{eliminados} registros", detalle={"dias": dias, "eliminados": eliminados})
                    st.toast(f"Se eliminaron {eliminados} registros.", icon=":material/check_circle:")
                    st.rerun()


def auth_actor() -> dict:
    return get_auth_manager().obtener_usuario_actual(st.session_state.get('admin_token')) or {}


def mostrar_historial():
    """Muestra el historial y logs del sistema."""

    auth_manager = get_auth_manager()
    db_manager = get_db_manager()

    if not auth_manager.es_super_admin(st.session_state.get('admin_token')):
        mostrar(aviso("warn", "Acceso restringido", "Solo SUPER_ADMIN puede ver el historial y los logs."))
        return

    logs = db_manager.obtener_logs(limit=500)

    if not logs:
        mostrar(aviso("info", "No hay registros en el historial"))
        return

    df_logs = pd.DataFrame(logs)
    if 'fecha' in df_logs.columns:
        # format='ISO8601': Supabase omite los microsegundos cuando son 0; con un formato inferido del primer
        # registro, el resto fallaba y la pantalla entera mostraba «error inesperado». Hora de Lima.
        fechas = pd.to_datetime(df_logs['fecha'], format='ISO8601', utc=True, errors='coerce')
        df_logs['fecha'] = fechas.dt.tz_convert('America/Lima').dt.strftime('%d/%m/%Y %H:%M:%S').fillna(df_logs['fecha'].astype(str))
    df_logs = df_logs.drop(columns=[c for c in ('id',) if c in df_logs.columns])
    _nombres = {'fecha': 'Fecha', 'usuario': 'Usuario', 'accion': 'Acción', 'detalle': 'Detalle'}
    df_logs.columns = [_nombres.get(str(c), str(c).replace('_', ' ').capitalize()) for c in df_logs.columns]

    with st.container(key="panel_logs"):
        panel_cab("Registros del sistema", f"Últimos {len(df_logs)} registros, del más reciente al más antiguo")
        buscar = st.text_input("Buscar", placeholder="Usuario, acción o detalle", key="logs_buscar")
        df_f = df_logs
        if buscar.strip():
            q = buscar.strip().lower()
            texto = df_logs.astype(str).agg(' '.join, axis=1).str.lower()
            df_f = df_logs[texto.str.contains(q, regex=False)]
        mostrar(tabla_df(df_f, alto=520, vacio="Ningún registro coincide con la búsqueda."))
        st.caption(f"Mostrando {len(df_f)} de {len(df_logs)} registros.")
        descargas(df_f, "historial_logs", "Logs", key="logs")

    if not get_auth_manager().es_superadmin_principal(st.session_state.get('admin_token')):
        mostrar(aviso("info", "Limpieza de registros",
                      "Solo el SUPER_ADMIN principal (oiis.winepi) puede limpiar el historial. "
                      "La auditoría («Control de actividad») no se puede borrar."))
        return
    mostrar(aviso("warn", "Limpieza de registros",
                  "Eliminar registros es permanente. Conserve una copia (Descargar CSV) antes de limpiar."))

    _limpieza(db_manager, "30", "Eliminar registros con más de 30 días",
              "Se borran los registros anteriores a hace 30 días. Los más recientes se conservan.",
              30, "Limpiar (más de 30 días)")
    _limpieza(db_manager, "90", "Eliminar registros con más de 90 días",
              "Se borran los registros anteriores a hace 90 días. Los más recientes se conservan.",
              90, "Limpiar (más de 90 días)")
    _limpieza(db_manager, "todos", "Eliminar TODOS los registros",
              "Se borra todo el historial del sistema. Esta acción no se puede deshacer.",
              0, "Eliminar todos")
