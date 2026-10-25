# pages/configuracion.py
"""
Configuración del Sistema - Unificada
Incluye configuración general y gestión de años epidemiológicos.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict

from src.config import Config
from src.auth import get_auth_manager
from src.db_manager import get_db_manager
from src.calendario_epi import (
    inicio_anio_epi, semanas_anio_epi, fin_desde_inicio, rango_semana, formatear_rango,
)
from utils.helpers import formatear_fecha
from app_pages.admin_helpers import requerir_admin
from app_pages.admin_cierres import panel_validacion_semana, panel_cierre_vencido
from utils.corte_ui import campos_corte, texto_corte
from utils.tema import kpi, mostrar, aviso, chip
from utils.tema_admin import tabla_df, panel_cab, esc


def init_session_state():
    """Inicializa las variables de sesión."""
    if 'mostrar_agregar_anio' not in st.session_state:
        st.session_state.mostrar_agregar_anio = False
    if 'mostrar_editar_anio' not in st.session_state:
        st.session_state.mostrar_editar_anio = False
    if 'anio_a_editar' not in st.session_state:
        st.session_state.anio_a_editar = None


def calcular_fecha_fin_semana(anio: int, semanas: int) -> str:
    """Último día (sábado) del año epidemiológico, calculado desde su inicio estándar."""
    return fin_desde_inicio(inicio_anio_epi(anio), semanas).strftime('%Y-%m-%d')


def calcular_semanas_para_anio(anio: int) -> int:
    """Número de semanas (52 o 53) del año epidemiológico."""
    return semanas_anio_epi(anio)


def formatear_fecha_para_mostrar(fecha_str: str) -> str:
    """Formatea una fecha YYYY-MM-DD para mostrar."""
    if not fecha_str:
        return '—'
    try:
        dt = datetime.strptime(fecha_str, '%Y-%m-%d')
        return dt.strftime('%d/%m/%Y')
    except:
        return fecha_str


def calcular_fecha_corte_semana(anio: int, semana: int, fecha_inicio_str: str = None) -> str:
    """Calcula la fecha de corte para una semana específica."""
    try:
        if fecha_inicio_str:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        else:
            fecha_inicio = datetime(anio, 1, 1)
        
        while fecha_inicio.weekday() != 6:
            fecha_inicio = fecha_inicio + timedelta(days=1)
        
        fecha_corte = fecha_inicio + timedelta(days=(semana - 1) * 7)
        fecha_corte = fecha_corte.replace(hour=23, minute=59, second=59)
        return fecha_corte.strftime('%d/%m/%Y %H:%M:%S')
    except:
        return 'No disponible'




def _parsear_corte(texto) -> Optional[datetime]:
    """'2026-10-06 23:59:59' (o solo la fecha) -> datetime; None si no se entiende."""
    t = str(texto or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(t, fmt)
            return dt.replace(hour=23, minute=59, second=59) if fmt == "%Y-%m-%d" else dt
        except ValueError:
            continue
    return None


def _a_fecha(valor) -> Optional[date]:
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _estado_anio(valor):
    return chip("Activo", "ok", "check") if str(valor) == "1" else chip("Inactivo", "mute")


def mostrar_configuracion():
    """Muestra la configuración unificada del sistema."""

    db_manager = get_db_manager()
    auth_manager = get_auth_manager()

    # ============================================================
    # CONTROL DE ACCESO -- esta página cambia configuración global
    # del sistema (semana activa, fecha de corte, años epidemiológicos).
    # Es operación habitual de los administradores, así que basta una
    # sesión de ADMIN o SUPER_ADMIN VÁLIDA (se revalida aquí mismo, sin
    # depender de que quien la invoque ya lo haya hecho). La gestión de
    # administradores, credenciales de red y logs sigue siendo solo
    # SUPER_ADMIN.
    # ============================================================
    requerir_admin()

    # ============================================================
    # OBTENER DATOS
    # ============================================================

    anios = db_manager.obtener_anios_epidemiologicos()
    anio_activo = db_manager.obtener_anio_activo_epidemiologico()

    semana_actual_db = db_manager.obtener_configuracion('semana_activa')
    semana_actual_val = int(semana_actual_db) if semana_actual_db else Config.get_semana_actual()

    fecha_corte_val = db_manager.obtener_configuracion('fecha_corte')
    fecha_corte_val = fecha_corte_val if fecha_corte_val else Config.get_fecha_corte()

    tamano_maximo_val = db_manager.obtener_configuracion('tamano_maximo_zip_mb')
    tamano_maximo_val = int(tamano_maximo_val) if tamano_maximo_val else Config.get_tamano_maximo_zip_mb()

    años_anteriores = db_manager.obtener_configuracion('años_anteriores_permitidos')
    max_anteriores = int(años_anteriores) if años_anteriores else 2

    permitir_anteriores = db_manager.obtener_configuracion('permitir_anios_anteriores')
    permitir_anteriores = permitir_anteriores.lower() == 'true' if permitir_anteriores else True

    permitir_adelantados = db_manager.obtener_configuracion('permitir_envios_adelantados')
    permitir_adelantados = permitir_adelantados.lower() == 'true' if permitir_adelantados else False

    anios_permitidos = db_manager.obtener_anios_permitidos()
    anio_activo_val = anio_activo['anio'] if anio_activo else (anios[0]['anio'] if anios else None)

    # ============================================================
    # INDICADORES
    # ============================================================

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mostrar(kpi("Año activo", anio_activo_val if anio_activo else "—", "Año epidemiológico en curso", None, "check"))
    with c2:
        mostrar(kpi("Años registrados", len(anios) if anios else 0, "Con fechas definidas", None, "dash"))
    with c3:
        mostrar(kpi("Semana activa", semana_actual_val, "Semana que reciben las redes", None, "reloj"))
    with c4:
        mostrar(kpi("Años permitidos", len(anios_permitidos) if anios_permitidos else 0, "Para envíos de las redes", None, "escudo"))

    # Validación de la semana y el corte que propuso el sistema al cerrar el corte.
    panel_cierre_vencido()
    panel_validacion_semana()

    # ============================================================
    # CONFIGURACIÓN GENERAL
    # ============================================================

    with st.container(key="panel_cfg_general"):
        panel_cab("Parámetros generales", "La semana activa y la fecha de corte las define usted; el sistema no las calcula")

        semanas_anio = int(anio_activo.get('semanas', 52) or 52) if anio_activo else 53
        inicio_anio = _a_fecha(anio_activo.get('fecha_inicio')) if anio_activo else None
        corte_actual = _parsear_corte(fecha_corte_val)
        corte_base = corte_actual or datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)

        # Las claves incluyen el valor guardado: si el valor cambia por otra vía
        # (otro administrador, el sistema), el campo se refresca solo.
        col1, col2, col3 = st.columns([1, 1.3, 1], vertical_alignment="top")
        with col1:
            nueva_semana = st.number_input(
                "Semana activa", min_value=1, max_value=max(semanas_anio, semana_actual_val),
                value=semana_actual_val, step=1, key=f"cfg_semana_{semana_actual_val}",
                help="La define usted; el sistema no la calcula.")
            if inicio_anio and 1 <= nueva_semana <= semanas_anio:
                d, h = rango_semana(inicio_anio, nueva_semana)
                st.caption(f"Semana {nueva_semana} de {anio_activo_val}: {formatear_rango(d, h)}")
            elif inicio_anio:
                st.caption(f"El año {anio_activo_val} tiene {semanas_anio} semanas.")
        with col2:
            nuevo_corte = campos_corte(f"cfg_corte_{fecha_corte_val}", corte_base)
        with col3:
            nuevo_tamano = st.number_input("Tamaño máximo ZIP (MB)", min_value=10, max_value=200,
                                           value=tamano_maximo_val, key=f"cfg_zip_{tamano_maximo_val}")

        if st.button("Guardar parámetros", type="primary", icon=":material/save:", key="cfg_guardar_general"):
            nueva_fecha_corte = nuevo_corte.strftime('%Y-%m-%d %H:%M:%S')
            cambios = [
                ('semana_activa', str(int(nueva_semana)), str(semana_actual_val), "Semana activa"),
                ('fecha_corte', nueva_fecha_corte, str(fecha_corte_val or ''), "Fecha de corte"),
                ('tamano_maximo_zip_mb', str(int(nuevo_tamano)), str(tamano_maximo_val), "Tamaño máximo ZIP"),
            ]
            fallos, hechos = [], []
            for clave, nuevo, previo, etiqueta in cambios:
                ok, detalle = db_manager.guardar_configuracion(clave, nuevo)
                if ok:
                    if nuevo != previo:
                        hechos.append(f"{etiqueta}: {previo or '—'} → {nuevo}")
                else:
                    fallos.append(f"{etiqueta}: {detalle}")
            if hechos:
                db_manager.registrar_log(
                    usuario=(st.session_state.get('admin_usuario') or {}).get('usuario', 'SYSTEM'),
                    accion='CAMBIAR_CONFIGURACION', detalle="; ".join(hechos))
            # Copia en .env solo como respaldo; en Docker puede ser de solo lectura.
            try:
                from dotenv import set_key
                env_path = Config.BASE_DIR / ".env"
                if env_path.exists():
                    set_key(str(env_path), "SEMANA_ACTUAL", str(int(nueva_semana)))
                    set_key(str(env_path), "FECHA_CORTE", nueva_fecha_corte)
                    set_key(str(env_path), "TAMANO_MAXIMO_ZIP_MB", str(int(nuevo_tamano)))
            except Exception:
                pass
            if fallos:
                mostrar(aviso("bad", "No se guardó todo",
                              "<br>".join(esc(f) for f in fallos)))
            else:
                st.toast("Parámetros guardados." if hechos else "No había cambios que guardar.",
                         icon=":material/check_circle:")
                st.rerun()

    # ============================================================
    # AÑOS EPIDEMIOLÓGICOS
    # ============================================================

    with st.container(key="panel_cfg_anios"):
        panel_cab("Años epidemiológicos", "Año activo y lista de años configurados")

        if anios:
            opciones_anios = sorted([a['anio'] for a in anios], reverse=True)
            col1, col2, col3 = st.columns([2, 1, 1], vertical_alignment="bottom")
            with col1:
                nuevo_anio_activo = st.selectbox(
                    "Año activo",
                    options=opciones_anios,
                    index=opciones_anios.index(anio_activo_val) if anio_activo_val in opciones_anios else 0,
                    help="Cambia el año activo del sistema"
                )
            with col2:
                if st.button("Activar año", type="primary", use_container_width=True, key="cfg_activar_top"):
                    if db_manager.activar_anio_epidemiologico(nuevo_anio_activo):
                        st.toast(f"Año {nuevo_anio_activo} activado.", icon=":material/check_circle:")
                        st.rerun()
                    else:
                        mostrar(aviso("bad", "No se pudo activar el año"))
            with col3:
                if st.button("Recargar", use_container_width=True, key="cfg_recargar"):
                    st.rerun()

            datos_tabla = []
            for a in anios:
                datos_tabla.append({
                    'Año': a['anio'],
                    'Semanas': a.get('semanas', 52),
                    'Fecha de inicio': formatear_fecha_para_mostrar(a.get('fecha_inicio', '')),
                    'Fecha de fin': formatear_fecha_para_mostrar(a.get('fecha_fin', '')),
                    'Estado': 1 if a.get('activo', 0) == 1 else 0,
                })
            mostrar(tabla_df(pd.DataFrame(datos_tabla), chips={'Estado': _estado_anio},
                             derecha=('Año', 'Semanas')))
        else:
            mostrar(aviso("warn", "No hay años configurados", "Agregue uno con el botón «Agregar año»."))

        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        if st.button("Agregar año", icon=":material/add:", key="cfg_abrir_agregar"):
            st.session_state.mostrar_agregar_anio = True

    # ============================================================
    # AGREGAR AÑO
    # ============================================================

    if st.session_state.mostrar_agregar_anio:
        with st.container(key="panel_cfg_agregar"):
            panel_cab("Agregar año epidemiológico", "El año se crea como inactivo; se activa manualmente")

            col1, col2 = st.columns(2)
            with col1:
                if anios:
                    sugerido = max([a['anio'] for a in anios]) + 1
                else:
                    sugerido = datetime.now().year

                nuevo_anio = st.number_input("Año", min_value=2000, max_value=2100, value=sugerido, step=1,
                                             key="cfg_nuevo_anio")
                nuevas_semanas = st.selectbox(
                    "Número de semanas", options=[52, 53],
                    index=0 if semanas_anio_epi(nuevo_anio) == 52 else 1,
                    key=f"cfg_nuevo_semanas_{nuevo_anio}",
                    help="Se propone según la regla estándar: la semana 1 es la que contiene el 4 de enero.")
            with col2:
                # Las claves incluyen el año/inicio: al cambiar el año, las fechas se recalculan solas.
                fecha_inicio_d = st.date_input(
                    "Fecha de inicio (domingo de la semana 1)", value=inicio_anio_epi(nuevo_anio),
                    format="DD/MM/YYYY", key=f"cfg_nuevo_inicio_{nuevo_anio}")
                if fecha_inicio_d.weekday() != 6:
                    mostrar(aviso("warn", "El inicio no es domingo",
                                  "Las semanas epidemiológicas van de domingo a sábado."))
                fecha_fin_d = st.date_input(
                    "Fecha de fin (sábado de la última semana)",
                    value=fin_desde_inicio(fecha_inicio_d, nuevas_semanas),
                    format="DD/MM/YYYY", key=f"cfg_nuevo_fin_{nuevo_anio}_{fecha_inicio_d}_{nuevas_semanas}")
            fecha_inicio_str = fecha_inicio_d.strftime('%Y-%m-%d')
            fecha_fin_str = fecha_fin_d.strftime('%Y-%m-%d')

            col1, col2, _ = st.columns([1, 1, 2])
            with col1:
                if st.button('Guardar año', type="primary", use_container_width=True, key="cfg_guardar_anio"):
                    try:
                        datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                        datetime.strptime(fecha_fin_str, '%Y-%m-%d')

                        existe = db_manager.obtener_anio_epidemiologico(nuevo_anio)
                        if existe:
                            mostrar(aviso("bad", f"El año {nuevo_anio} ya existe"))
                        else:
                            if db_manager.crear_anio_epidemiologico(
                                nuevo_anio, nuevas_semanas, fecha_inicio_str, fecha_fin_str, activo=False
                            ):
                                st.toast(f"Año {nuevo_anio} agregado.", icon=":material/check_circle:")
                                st.session_state.mostrar_agregar_anio = False
                                st.rerun()
                            else:
                                mostrar(aviso("bad", "No se pudo crear el año"))
                    except ValueError:
                        mostrar(aviso("bad", "Formato de fecha inválido", "Use AAAA-MM-DD."))
            with col2:
                if st.button('Cancelar', use_container_width=True, key="cfg_cancelar_anio"):
                    st.session_state.mostrar_agregar_anio = False
                    st.rerun()

    # ============================================================
    # EDITAR AÑO (FECHAS DE INICIO Y FIN)
    # ============================================================

    if anios:
        with st.container(key="panel_cfg_editar"):
            panel_cab("Editar año", "Modifique las fechas de inicio y fin de un año")

            opciones_editar = sorted([a['anio'] for a in anios], reverse=True)
            c_sel, _ = st.columns([1, 2])
            with c_sel:
                anio_editar = st.selectbox("Año a editar", options=opciones_editar, key="select_editar_anio")

            anio_data = db_manager.obtener_anio_epidemiologico(anio_editar) if anio_editar else None
            if anio_data:
                col1, col2, col3 = st.columns(3)
                with col1:
                    semanas_edit = st.number_input(
                        "Número de semanas", min_value=52, max_value=53,
                        value=int(anio_data.get('semanas', 52) or 52), key=f"edit_semanas_{anio_editar}"
                    )
                with col2:
                    ini_guardado = _a_fecha(anio_data.get('fecha_inicio')) or inicio_anio_epi(anio_editar)
                    fecha_inicio_d = st.date_input(
                        "Fecha de inicio", value=ini_guardado, format="DD/MM/YYYY",
                        key=f"edit_fecha_inicio_{anio_editar}")
                with col3:
                    fin_guardado = _a_fecha(anio_data.get('fecha_fin')) or fin_desde_inicio(fecha_inicio_d, semanas_edit)
                    fecha_fin_d = st.date_input(
                        "Fecha de fin", value=fin_guardado, format="DD/MM/YYYY",
                        key=f"edit_fecha_fin_{anio_editar}")
                fecha_inicio_edit = fecha_inicio_d.strftime('%Y-%m-%d')
                fecha_fin_edit = fecha_fin_d.strftime('%Y-%m-%d')

                if fecha_inicio_d.weekday() != 6:
                    mostrar(aviso("warn", "El inicio no es domingo",
                                  "Las semanas epidemiológicas van de domingo a sábado; revise la fecha."))
                est_ini, est_fin = inicio_anio_epi(anio_editar), fin_desde_inicio(inicio_anio_epi(anio_editar), semanas_anio_epi(anio_editar))
                if (fecha_inicio_d, int(semanas_edit)) != (est_ini, semanas_anio_epi(anio_editar)):
                    st.caption(f"Con la regla estándar, {anio_editar} empieza el {est_ini:%d/%m/%Y} "
                               f"y tiene {semanas_anio_epi(anio_editar)} semanas.")

                col1, col2, _ = st.columns([1, 1, 2], vertical_alignment="center")
                with col1:
                    if st.button("Actualizar año", type="primary", use_container_width=True, key="cfg_actualizar_anio"):
                        try:
                            datetime.strptime(fecha_inicio_edit, '%Y-%m-%d')
                            datetime.strptime(fecha_fin_edit, '%Y-%m-%d')

                            if db_manager.actualizar_anio_epidemiologico(
                                anio_editar,
                                semanas=semanas_edit,
                                fecha_inicio=fecha_inicio_edit,
                                fecha_fin=fecha_fin_edit
                            ):
                                st.toast(f"Año {anio_editar} actualizado.", icon=":material/check_circle:")
                                st.rerun()
                            else:
                                mostrar(aviso("bad", "No se pudo actualizar el año"))
                        except ValueError:
                            mostrar(aviso("bad", "Formato de fecha inválido", "Use AAAA-MM-DD."))
                with col2:
                    mostrar(_estado_anio(anio_data.get('activo', 0)))

    # ============================================================
    # GESTIÓN DE AÑOS INACTIVOS (Activar / Eliminar)
    # ============================================================

    if anios:
        anios_inactivos = [a for a in anios if a.get('activo', 0) == 0]
        if anios_inactivos:
            with st.container(key="panel_cfg_inactivos"):
                panel_cab("Años inactivos", "Active un año inactivo o elimínelo")
                opciones_inactivos = [a['anio'] for a in anios_inactivos]

                col1, col2, _ = st.columns([1, 1, 2], vertical_alignment="bottom")
                with col1:
                    anio_seleccionado = st.selectbox("Año a activar", options=opciones_inactivos, key="anio_activar_gestion")
                with col2:
                    if st.button('Activar año', type="primary", use_container_width=True, key="cfg_activar_inactivo"):
                        if db_manager.activar_anio_epidemiologico(anio_seleccionado):
                            st.toast(f"Año {anio_seleccionado} activado.", icon=":material/check_circle:")
                            st.rerun()
                        else:
                            mostrar(aviso("bad", "No se pudo activar el año"))

            with st.container(key="peligro_anio"):
                mostrar(aviso("bad", "Eliminar un año inactivo",
                              "Se elimina el año epidemiológico seleccionado. Esta acción no se puede deshacer."))
                col1, col2, col3 = st.columns([1, 1.6, 1], vertical_alignment="bottom")
                with col1:
                    anio_eliminar = st.selectbox("Año a eliminar", options=opciones_inactivos, key="anio_eliminar_gestion")
                with col2:
                    confirma = st.checkbox(f"Confirmo que deseo eliminar el año {anio_eliminar}", key="cfg_confirma_eliminar")
                with col3:
                    if st.button('Eliminar año', type="primary", use_container_width=True,
                                 icon=":material/delete:", key="cfg_eliminar_anio"):
                        if not confirma:
                            st.warning("Marque la casilla de confirmación para eliminar.")
                        elif db_manager.eliminar_anio_epidemiologico(anio_eliminar):
                            st.toast(f"Año {anio_eliminar} eliminado.", icon=":material/check_circle:")
                            st.rerun()
                        else:
                            mostrar(aviso("bad", "No se puede eliminar el año activo"))

    # ============================================================
    # CONFIGURACIÓN DE AÑOS PERMITIDOS
    # ============================================================

    with st.container(key="panel_cfg_permitidos"):
        panel_cab("Años permitidos para envío", "Qué años y semanas pueden usar las redes al enviar")

        col1, col2 = st.columns(2)
        with col1:
            max_anteriores_nuevo = st.number_input(
                "Años anteriores permitidos", min_value=0, max_value=5, value=max_anteriores,
                help="0 = solo el año activo"
            )
        with col2:
            permitir_anteriores_nuevo = st.checkbox("Permitir envíos de años anteriores", value=permitir_anteriores)
            permitir_adelantados_nuevo = st.checkbox(
                "Permitir envíos adelantados (semanas futuras)", value=permitir_adelantados
            )

        if st.button('Guardar años permitidos', type="primary", icon=":material/save:", key="cfg_guardar_permitidos"):
            resultados = [
                db_manager.guardar_configuracion('años_anteriores_permitidos', str(max_anteriores_nuevo)),
                db_manager.guardar_configuracion('permitir_anios_anteriores', str(permitir_anteriores_nuevo).lower()),
                db_manager.guardar_configuracion('permitir_envios_adelantados', str(permitir_adelantados_nuevo).lower()),
            ]
            malos = [d for ok, d in resultados if not ok]
            if malos:
                mostrar(aviso("bad", "No se pudo guardar", "<br>".join(esc(m) for m in malos)))
            else:
                st.toast("Configuración de años guardada.", icon=":material/check_circle:")
                st.rerun()

        if anios_permitidos:
            st.caption(f"Años permitidos actualmente ({len(anios_permitidos)}): {', '.join(map(str, anios_permitidos))}")
        else:
            mostrar(aviso("warn", "No hay años permitidos", "Configure un año activo."))


    # ============================================================
    # ALERTAS POR CORREO A LOS ADMINISTRADORES
    # ============================================================

    with st.container(key="panel_cfg_alertas"):
        panel_cab("Alertas por correo", "Por defecto apagadas: lo que requiere revisión aparece en «Observaciones»")
        valor_actual = str(db_manager.obtener_configuracion('alertas_correo_admin') or '').strip().lower() == 'true'
        alertas_nuevo = st.checkbox(
            "Enviar por correo un aviso a los administradores cuando un envío sea tardío, observado o duplicado",
            value=valor_actual, key="cfg_alertas_correo")
        st.caption("Quien envía siempre recibe su acuse. Los correos de seguridad (contraseñas, respaldos, cierres) no cambian.")
        if alertas_nuevo != valor_actual:
            ok, detalle = db_manager.guardar_configuracion('alertas_correo_admin', str(alertas_nuevo).lower())
            if ok:
                st.toast("Preferencia de alertas guardada.", icon=":material/check_circle:")
                st.rerun()
            else:
                mostrar(aviso("bad", "No se pudo guardar", esc(detalle)))


def main():
    init_session_state()
    mostrar_configuracion()


if __name__ == "__main__":
    main()
