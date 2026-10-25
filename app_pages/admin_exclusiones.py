# pages/admin_exclusiones.py
"""
Gestión de exclusiones de centros (centros que no se cuentan en el cumplimiento).
"""

import pandas as pd
import streamlit as st

from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from utils.helpers import sanitizar_html
from utils.tema import mostrar, aviso, kpi
from utils.tema_admin import tabla_df, panel_cab
from app_pages.admin_helpers import (
    formatear_centro,
    formatear_fecha_columna,
    requerir_admin,
)


def mostrar_gestion_exclusiones():
    """
    Muestra el panel de gestion de centros excluidos.
    Usa los metodos persistentes de DatabaseManager.
    """
    requerir_admin()

    db_manager = get_db_manager()
    data_loader = get_data_loader()

    redes = data_loader.obtener_redes()

    if not redes:
        mostrar(aviso("warn", "No hay redes disponibles en la configuración"))
        return

    mostrar(aviso(
        "info", "Qué hace una exclusión",
        "Aquí puede excluir centros que no envían reportes por casos excepcionales. Los centros excluidos "
        "no se cuentan en los totales de establecimientos ni en el cumplimiento. "
        "<strong>Los cambios se guardan de forma permanente.</strong>"))

    # ============================================================
    # CARGAR EXCLUSIONES EXISTENTES DESDE LA DB
    # ============================================================
    exclusiones_existentes = db_manager.obtener_todas_las_exclusiones_agrupadas()
    exclusiones_db = db_manager.obtener_centros_excluidos()

    # ============================================================
    # INDICADORES
    # ============================================================
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        mostrar(kpi("Centros excluidos", len(exclusiones_db) if exclusiones_db else 0, "En total", None, "escudo"))
    with c2:
        mostrar(kpi("Redes con exclusiones", len(exclusiones_existentes), "Con al menos un centro", None, "dash"))

    # ============================================================
    # AGREGAR EXCLUSION
    # ============================================================
    with st.container(key="panel_excl_agregar"):
        panel_cab("Excluir un centro", "El centro deja de contarse en los totales de su red")

        col1, col2, col3 = st.columns(3)

        with col1:
            red_seleccionada = st.selectbox("Red", options=redes, key="red_exclusion")

        with col2:
            centro_a_excluir = None
            if red_seleccionada:
                centros_disponibles = data_loader.obtener_centros(red_seleccionada)
                centros_excluidos_red = exclusiones_existentes.get(red_seleccionada, [])

                centros_opciones = []
                for c in centros_disponibles:
                    centro_str = formatear_centro(c)
                    if centro_str not in centros_excluidos_red:
                        centros_opciones.append(centro_str)

                centro_a_excluir = st.selectbox(
                    "Centro a excluir", options=centros_opciones, index=None,
                    placeholder="Seleccione un centro", key="centro_exclusion"
                )

        with col3:
            motivo_exclusion = st.text_input(
                "Motivo (opcional)", placeholder="Ej.: Centro cerrado temporalmente", key="motivo_exclusion"
            )

        if st.button("Excluir centro", type="primary", icon=":material/block:",
                     key="btn_excluir", disabled=not (red_seleccionada and centro_a_excluir)):
            usuario = st.session_state.admin_usuario
            usuario_nombre = usuario.get('nombre', usuario.get('usuario', 'admin')) if isinstance(usuario, dict) else str(usuario)

            if db_manager.agregar_centro_excluido(
                red_nombre=red_seleccionada,
                centro_nombre=centro_a_excluir,
                motivo=motivo_exclusion if motivo_exclusion else None,
                creado_por=usuario_nombre
            ):
                st.toast(f"Centro «{centro_a_excluir}» excluido de la red {red_seleccionada}.",
                         icon=":material/check_circle:")
                st.rerun()
            else:
                mostrar(aviso("bad", "No se pudo excluir el centro",
                              f"Verifique que la red {sanitizar_html(red_seleccionada)} exista."))

    # ============================================================
    # EXCLUSIONES ACTUALES
    # ============================================================
    with st.container(key="panel_excl_lista"):
        panel_cab("Centros excluidos actualmente")
        if exclusiones_db:
            datos_exclusiones = []
            for item in exclusiones_db:
                red = item.get('red_nombre', '') or (item.get('redes') or {}).get('nombre', '')
                datos_exclusiones.append({
                    'Red': red or '',
                    'Centro': item.get('centro_nombre', '') or '',
                    'Motivo': item.get('motivo') or '—',
                    'Creado por': item.get('creado_por') or '—',
                    'Fecha de exclusión': formatear_fecha_columna(item.get('fecha_exclusion', '')),
                })
            mostrar(tabla_df(pd.DataFrame(datos_exclusiones)))
        else:
            mostrar(aviso("info", "No hay centros excluidos actualmente"))

    # ============================================================
    # REINCORPORAR / LIMPIAR
    # ============================================================
    redes_con_exclusiones = list(exclusiones_existentes.keys())

    if not redes_con_exclusiones:
        return

    with st.container(key="panel_excl_reincorporar"):
        panel_cab("Reincorporar un centro", "El centro vuelve a contarse en su red")
        col1, col2, col3 = st.columns([1, 1.4, 1], vertical_alignment="bottom")

        with col1:
            red_reincorporar = st.selectbox("Red", options=redes_con_exclusiones, key="red_reincorporar")
        with col2:
            centros_excluidos_red = exclusiones_existentes.get(red_reincorporar, [])
            centro_reincorporar = st.selectbox(
                "Centro a reincorporar",
                options=centros_excluidos_red if centros_excluidos_red else ["No hay centros excluidos"],
                key="centro_reincorporar"
            )
        with col3:
            reincorporar = st.button(
                "Reincorporar", use_container_width=True, icon=":material/undo:", key="btn_reincorporar",
                disabled=not (red_reincorporar and centro_reincorporar and centro_reincorporar != "No hay centros excluidos"),
            )
        if reincorporar:
            if db_manager.eliminar_centro_excluido(red_reincorporar, centro_reincorporar):
                st.toast(f"Centro «{centro_reincorporar}» reincorporado a la red {red_reincorporar}.",
                         icon=":material/check_circle:")
                st.rerun()
            else:
                mostrar(aviso("bad", "No se pudo reincorporar el centro",
                              f"Verifique que la red {sanitizar_html(red_reincorporar)} exista."))

    with st.container(key="peligro_exclusiones"):
        mostrar(aviso("bad", "Limpiar todas las exclusiones de una red",
                      "Se reincorporan TODOS los centros excluidos de la red elegida."))
        col1, col2, col3 = st.columns([1, 1.6, 1], vertical_alignment="bottom")
        with col1:
            red_limpiar = st.selectbox("Red", options=redes_con_exclusiones, key="red_limpiar")
        with col2:
            cantidad = db_manager.contar_centros_excluidos(red_limpiar) if red_limpiar else 0
            confirmar_limpiar = st.checkbox(
                f"Confirmo reincorporar {cantidad} centro(s) de {red_limpiar}",
                key="excl_confirma_limpiar")
        with col3:
            if st.button("Limpiar exclusiones", type="primary", use_container_width=True,
                         icon=":material/delete:", key="btn_limpiar_excl"):
                if not confirmar_limpiar:
                    st.warning("Marque la casilla de confirmación para continuar.")
                elif db_manager.limpiar_centros_excluidos(red_limpiar):
                    st.toast(f"Se limpiaron las exclusiones de la red {red_limpiar}.", icon=":material/check_circle:")
                    st.rerun()
                else:
                    mostrar(aviso("bad", "No se pudieron limpiar las exclusiones"))
