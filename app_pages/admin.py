# pages/admin.py
"""
Panel de administrador - Dashboard de control y gestión.
VERSIÓN MEJORADA CON SANITIZACIÓN HTML PARA PREVENIR XSS
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from src.config import Config
from src.auth import get_auth_manager
from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from src.drive_manager import get_drive_manager
from src.email_sender import get_email_sender
from utils.helpers import (
    formatear_fecha,
    calcular_porcentaje,
    obtener_estado_semaforo,
    obtener_fecha_actual,
    sanitizar_html,
    sanitizar_lista_html,
    sanitizar_dict_html
)
from utils.tema import (
    aplicar_tema, encabezado_publico, pie_pagina, mostrar, mostrar_aviso,
    marca_svg, chip, icono, logo_uri, aviso,
)
from utils.tema_admin import encabezado_admin, esc

# ============================================================
# IMPORTS DE NUEVOS MODULOS (FASE 2)
# ============================================================
from app_pages.admin_progreso import mostrar_progreso_redes
from app_pages.admin_seguimiento import mostrar_seguimiento_semana_activa
from app_pages.admin_notificaciones import mostrar_notificaciones

# ============================================================
# PÁGINAS SEPARADAS (división de admin.py en módulos más chicos)
# ============================================================
from app_pages.admin_helpers import obtener_centros_excluidos
from app_pages.admin_exclusiones import mostrar_gestion_exclusiones
from app_pages.admin_dashboard import mostrar_dashboard_principal
from app_pages.admin_atrasos import mostrar_control_atrasos
from app_pages.admin_duplicados import mostrar_control_duplicados
from app_pages.admin_observaciones import mostrar_observaciones, contadores_observaciones
from app_pages.admin_administradores import mostrar_gestion_admins
from app_pages.admin_cuentas import mostrar_cuentas_panel
from app_pages.admin_solicitudes_password import mostrar_solicitudes_password, pendientes_para_aviso
from app_pages.admin_cierres import mostrar_informe_semana, mostrar_respaldos, banners_panel, avisos_menu
from app_pages.admin_credenciales_red import mostrar_gestion_credenciales_red
from app_pages.admin_drive import mostrar_gestion_drive
from app_pages.admin_historial import mostrar_historial
from app_pages.admin_repositorio import mostrar_descarga_limpieza, pendientes_retiro
from app_pages.admin_permisos import mostrar_permisos_operacion
from app_pages.admin_actividad import mostrar_control_actividad, puede_ver as puede_ver_actividad



# ============================================================
# NAVEGACION DEL PANEL
# ============================================================
# clave (valor de st.session_state.seccion_admin) -> etiqueta del menu,
# icono, titulo y subtitulo de la pagina. Las claves no cambian: otras
# pantallas (p. ej. "Ir a Control de duplicados") las usan para navegar.

SECCIONES = {
    'Dashboard': (
        'Panel de control', ':material/dashboard:',
        'Panel de control', 'Resumen de envíos de la semana en curso.'),
    'Seguimiento Semana Activa': (
        'Seguimiento semanal', ':material/checklist:',
        'Seguimiento semanal', 'Qué centros ya enviaron y cuáles faltan en la semana seleccionada.'),
    'Progreso por Red': (
        'Progreso por red', ':material/bar_chart:',
        'Progreso por red', 'Cumplimiento de cada red, semana a semana.'),
    'Control de Atrasos': (
        'Control de atrasos', ':material/schedule:',
        'Control de atrasos', 'Envíos recibidos después de la fecha de corte.'),
    'Control de Duplicados': (
        'Control de duplicados', ':material/content_copy:',
        'Control de duplicados', 'Centros con más de un envío en la misma semana.'),
    'Observaciones': (
        'Observaciones', ':material/chat:',
        'Observaciones', 'Comentarios de las redes y envíos que requieren revisión: observados, duplicados y reemplazos.'),
    'Informe por Semana': (
        'Informe por semana', ':material/summarize:',
        'Informe por semana', 'Resumen de cumplimiento por red: revisar, validar y enviar a la entidad externa.'),
    'Descarga y Limpieza': (
        'Descarga y limpieza', ':material/folder_zip:',
        'Descarga y limpieza', 'Descargue en masa los ZIP de una semana y retire del repositorio los archivos que ya no hacen falta.'),
    'Notificaciones': (
        'Notificaciones', ':material/mail:',
        'Notificaciones', 'Recordatorios por correo a las redes con envíos pendientes.'),
    'Exclusion de Centros': (
        'Exclusión de centros', ':material/block:',
        'Exclusión de centros', 'Centros que no se cuentan en el cumplimiento por casos excepcionales.'),
    'Configuracion': (
        'Configuración', ':material/tune:',
        'Configuración', 'Años epidemiológicos, semana activa y parámetros del sistema.'),
    'Gestion de Drive': (
        'Almacenamiento (Drive)', ':material/folder:',
        'Almacenamiento (Drive)', 'Archivos recibidos y espacio disponible en Google Drive.'),
    'Gestion de Administradores': (
        'Administradores', ':material/group:',
        'Administradores', 'Cuentas con acceso al panel de administración.'),
    'Solicitudes de Contraseña': (
        'Solicitudes de contraseña', ':material/mark_email_unread:',
        'Solicitudes de contraseña', 'Redes que piden cambiar su contraseña: revise el sustento, responda y apruebe.'),
    'Cuentas del Panel': (
        'Cuentas del panel', ':material/manage_accounts:',
        'Cuentas del panel', 'Cambio de datos, nombre de usuario y contraseñas de administradores y SUPER_ADMIN.'),
    'Credenciales de Red': (
        'Credenciales de red', ':material/key:',
        'Credenciales de red', 'Contraseñas con las que cada red consulta su progreso.'),
    'Respaldos': (
        'Respaldos', ':material/backup:',
        'Respaldos', 'Copias de seguridad del control de lo recibido en la carpeta BACKUPS de Drive.'),
    'Historial y Logs': (
        'Historial y logs', ':material/description:',
        'Historial y logs', 'Registro de acciones realizadas en el sistema.'),
    'Control de Actividad': (
        'Control de actividad', ':material/visibility:',
        'Control de actividad', 'Qué hizo cada administrador y SUPER_ADMIN: descargas, retiros, duplicados, respaldos y más.'),
    'Permisos de Operacion': (
        'Permisos de operación', ':material/key:',
        'Permisos de operación', 'Quién puede descargar en masa, retirar archivos, respaldar y ver la auditoría (solo oiis.winepi).'),
    'Agente de IA': (
        'Agente de IA', ':material/auto_awesome:',
        'Agente de IA', 'Lo que la IA preparó para usted: pendientes, recordatorios por aprobar, patrones de las redes e informe semanal.'),
    'Gobernanza de IA': (
        'Gobernanza de IA', ':material/policy:',
        'Gobernanza de IA', 'Cómo funciona la IA y cómo se controla: rondas del agente, procedimientos, evaluaciones, memoria, encendido y apagado, e historial.'),
}

GRUPOS_NAV = [
    ('Monitoreo', ['Dashboard', 'Seguimiento Semana Activa', 'Progreso por Red']),
    ('Gestión de envíos', ['Control de Atrasos', 'Control de Duplicados', 'Observaciones', 'Informe por Semana', 'Descarga y Limpieza', 'Notificaciones']),
    ('Administración', ['Exclusion de Centros', 'Configuracion', 'Gestion de Drive', 'Respaldos']),
    ('Solo SUPER_ADMIN', ['Gestion de Administradores', 'Solicitudes de Contraseña', 'Cuentas del Panel', 'Credenciales de Red', 'Historial y Logs']),
    ('Trazabilidad', ['Control de Actividad', 'Permisos de Operacion']),
    ('Inteligencia artificial', ['Agente de IA', 'Gobernanza de IA']),
]

# Un ADMIN (no SUPER_ADMIN) no gestiona otros administradores,
# credenciales de red ni ve el historial/logs del sistema: esas
# secciones ni siquiera aparecen en su menú (además cada página ya se
# protege por su cuenta si se llegara a acceder de otra forma).
SECCIONES_SOLO_SUPER_ADMIN = ['Gestion de Administradores', 'Solicitudes de Contraseña', 'Cuentas del Panel', 'Credenciales de Red', 'Historial y Logs']

# «Cuentas del panel» la ve únicamente el SUPER_ADMIN principal (oiis.winepi).
SECCIONES_SOLO_PRINCIPAL = ['Cuentas del Panel', 'Permisos de Operacion']

# «Control de actividad» la ve oiis.winepi y quien tenga el permiso «Ver auditoría».
SECCIONES_POR_PERMISO = ['Control de Actividad']


def init_session_state():
    """Inicializa las variables de sesion."""
    if 'admin_token' not in st.session_state:
        st.session_state.admin_token = None
    if 'admin_usuario' not in st.session_state:
        st.session_state.admin_usuario = None
    if 'admin_logueado' not in st.session_state:
        st.session_state.admin_logueado = False
    if 'pagina' not in st.session_state:
        st.session_state.pagina = 'landing'
    if 'seccion_admin' not in st.session_state:
        st.session_state.seccion_admin = 'Dashboard'
    if not st.session_state.get('_seccion_desde_url'):
        st.session_state._seccion_desde_url = True
        try:
            s = st.query_params.get("s")
            if s in SECCIONES:
                st.session_state.seccion_admin = s
        except Exception:
            pass
    if 'mostrar_corte_semana' not in st.session_state:
        st.session_state.mostrar_corte_semana = False
    if 'confirmar_eliminar_logs' not in st.session_state:
        st.session_state.confirmar_eliminar_logs = False
    if 'log_accion' not in st.session_state:
        st.session_state.log_accion = None
    if 'log_confirmado' not in st.session_state:
        st.session_state.log_confirmado = False


def _ir_a_seccion(clave: str):
    st.session_state.seccion_admin = clave
    try:
        st.query_params["s"] = clave        # SIREA 3.3: al refrescar (F5) se vuelve a la misma sección
    except Exception:
        pass


# ============================================================
# SIREA 3.3 · SESIÓN QUE SOBREVIVE AL REFRESCAR (F5)
# ============================================================
# Streamlit empieza una sesión nueva al refrescar el navegador. El token de la
# sesión (aleatorio; sigue venciendo a las 8 h o tras 30 min sin uso, igual
# que antes) se guarda en una cookie del navegador de este sitio (SameSite
# Strict; Secure cuando el sitio es https). Al volver a cargar, si el token
# sigue vigente en el servidor, se recupera la sesión sin pedir contraseña.
# Al cerrar sesión la cookie se borra y el token deja de valer.
_COOKIE_SESION = "sirea_admin_sesion"


def _js_cookie(valor: str, max_age: int):
    seguro = "; Secure" if str(getattr(st.context, "url", "") or "").startswith("https") else ""
    import json as _json
    st.html(f"<script>document.cookie = {_json.dumps(_COOKIE_SESION)} + '=' + {_json.dumps(valor)} + "
            f"'; path=/; max-age={int(max_age)}; SameSite=Strict{seguro}';</script>", unsafe_allow_javascript=True)


def _guardar_sesion_en_navegador():
    token = st.session_state.get("admin_token")
    if token and (st.context.cookies or {}).get(_COOKIE_SESION) != token \
            and st.session_state.get("_cookie_escrita") != token:
        from src.config import Config
        _js_cookie(token, int(Config.SESION_DURACION_HORAS) * 3600)
        st.session_state["_cookie_escrita"] = token


def _borrar_sesion_del_navegador():
    _js_cookie("", 0)
    st.session_state["_cookie_escrita"] = None


def _recuperar_sesion() -> bool:
    """Si el navegador trae un token vigente, recupera la sesión (después de un F5)."""
    if st.session_state.get("admin_logueado") or st.session_state.get("_sesion_cerrada_a_mano"):
        return False
    token = (st.context.cookies or {}).get(_COOKIE_SESION)
    if not token:
        return False
    auth_manager = get_auth_manager()
    info = auth_manager.obtener_usuario_actual(token)
    if not info:
        return False
    admin = get_db_manager().obtener_administrador(info.get("usuario")) or {}
    if not admin or not admin.get("activo", True):
        return False
    admin = {k: v for k, v in admin.items() if k != "password_hash"}
    st.session_state.admin_token = token
    st.session_state.admin_usuario = admin
    st.session_state.admin_logueado = True
    st.session_state["_cookie_escrita"] = token
    return True


def _cerrar_sesion_admin():
    auth_manager = get_auth_manager()
    auth_manager.logout(st.session_state.admin_token)
    st.session_state.admin_logueado = False
    st.session_state.admin_token = None
    st.session_state.admin_usuario = None
    st.session_state["_sesion_cerrada_a_mano"] = True
    st.session_state["_borrar_cookie"] = True


def mostrar_login():
    """Inicio de sesión del panel: información a la izquierda y formulario a la derecha."""

    aplicar_tema()
    if st.session_state.pop("_borrar_cookie", False):
        _borrar_sesion_del_navegador()
    encabezado_publico("admin", nav=False)

    with st.container(key="sire_split_oscuro"):
        izq, der = st.columns(2, gap="small")

        with izq:
            mostrar(f"""
            <img src="{logo_uri('essalud-blanco.png')}" alt="EsSalud" class="sire-split-logo">
            <div class="sire-split-in">
              <span class="sire-pildora">{icono('candado', 15, 'currentColor', 2.4)}Solo personal autorizado</span>
              <h1>Panel de administración OIIS</h1>
              <p>Seguimiento de los reportes epidemiológicos de las redes asistenciales, control de envíos y gestión de cuentas.</p>
              <div style="display:flex;flex-direction:column;gap:12px;margin-top:6px">
                <div class="sire-ck">{icono('check', 20, '#FFFFFF', 2.6)}<span>Cada acción queda registrada en el historial.</span></div>
                <div class="sire-ck">{icono('check', 20, '#FFFFFF', 2.6)}<span>Tras 5 intentos fallidos, el acceso se bloquea 5 minutos.</span></div>
                <div class="sire-ck">{icono('check', 20, '#FFFFFF', 2.6)}<span>La sesión caduca a las 8 horas.</span></div>
              </div>
            </div>
            <div class="sire-split-pie">EsSalud · Oficina de Inteligencia e Información Sanitaria</div>
            """)

        with der:
            if st.session_state.pop('cambio_password_ok', False):
                mostrar(aviso("ok", "Contraseña actualizada", "Ingrese con su nueva contraseña."))
            with st.form("login_form", clear_on_submit=False):
                mostrar("""
                <h2 class="sire-form-t">Iniciar sesión</h2>
                <p class="sire-form-s">Ingrese con su usuario y contraseña del panel.</p>
                """)
                usuario = st.text_input("Usuario", placeholder="Ingrese su usuario")
                password = st.text_input("Contraseña", type="password", placeholder="Ingrese su contraseña")

                submit = st.form_submit_button("Entrar al panel", width='stretch', type="primary")

                mostrar(f"""
                <div class="sire-form-nota">{icono('candado', 18, '#0077C8', 2.2)}
                <span>Si olvidó su contraseña, solicite a un SUPER_ADMIN que la restablezca.</span></div>
                """)

                if submit:
                    if usuario and password:
                        auth_manager = get_auth_manager()
                        resultado = auth_manager.login(usuario, password)

                        if resultado['exito']:
                            st.session_state.admin_token = resultado['token']
                            st.session_state.admin_usuario = {k: v for k, v in (resultado['usuario'] or {}).items()
                                                              if k != 'password_hash'}
                            st.session_state.admin_logueado = True
                            st.session_state["_sesion_cerrada_a_mano"] = False
                            st.rerun()
                        else:
                            st.error(resultado['mensaje'])
                    else:
                        st.warning("Ingrese su usuario y su contraseña.")

            mostrar('<div class="sire-pie-form">¿Es una red asistencial?</div>')
            if st.button("Ir al portal de redes", key="link_ir_red"):
                st.session_state.pagina = 'red_progreso'
                st.rerun()
            if st.button("Volver al inicio", key="link_volver_inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()

    pie_pagina(margen=0)


def _iniciales(nombre: str) -> str:
    partes = [p for p in str(nombre or '').replace('_', ' ').split() if p]
    if not partes:
        return 'AD'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[1][0]).upper()


def _menu_lateral(usuario_actual: dict, es_super_admin: bool, es_principal: bool = False) -> str:
    """Dibuja el menu lateral y devuelve la clave de la seccion activa."""
    ver_actividad = es_principal or puede_ver_actividad(usuario_actual)
    disponibles = {
        k for k in SECCIONES
        if (es_super_admin or k not in SECCIONES_SOLO_SUPER_ADMIN)
        and (es_principal or k not in SECCIONES_SOLO_PRINCIPAL)
        and (ver_actividad or k not in SECCIONES_POR_PERMISO)
    }
    activa = st.session_state.get('seccion_admin', 'Dashboard')
    if activa not in disponibles:
        activa = 'Dashboard'
        st.session_state.seccion_admin = activa

    # Aviso de solicitudes de contraseña pendientes (lo ve todo SUPER_ADMIN).
    n_solicitudes = pendientes_para_aviso() if es_super_admin else 0
    n_retiros = pendientes_retiro() if es_principal else 0
    cont_obs = contadores_observaciones()
    n_obs, n_fallas = cont_obs['normales'], cont_obs['fallas']
    marcas = avisos_menu()

    with st.sidebar:
        mostrar(f"""
        <div class="sire-side-brand">{marca_svg(42, invertida=True)}
          <div><b>SIRE<span style="color:#D9C7F2">A</span></b><small>Panel OIIS</small></div></div>
        """)

        for grupo, claves in GRUPOS_NAV:
            claves = [c for c in claves if c in disponibles]
            if not claves:
                continue
            mostrar(f'<div class="sire-side-grupo">{grupo}</div>')
            for clave in claves:
                etiqueta, ico, _, _ = SECCIONES[clave]
                if clave == 'Solicitudes de Contraseña' and n_solicitudes:
                    etiqueta = f"{etiqueta} ({n_solicitudes})"
                if clave == 'Configuracion' and marcas['configuracion']:
                    etiqueta = f"{etiqueta} (1)"
                if clave == 'Respaldos' and marcas['respaldos']:
                    etiqueta = f"{etiqueta} (!)"
                if clave == 'Observaciones' and (n_obs or n_fallas):
                    etiqueta = f"{etiqueta} ({n_obs})" if n_obs else etiqueta
                    etiqueta = f"{etiqueta} !" if n_fallas else etiqueta
                if clave == 'Descarga y Limpieza' and n_retiros:
                    etiqueta = f"{etiqueta} ({n_retiros})"
                st.button(
                    etiqueta,
                    key=f"nav_{clave}",
                    icon=ico,
                    type="primary" if clave == activa else "secondary",
                    use_container_width=True,
                    on_click=_ir_a_seccion,
                    args=(clave,),
                )

        nombre = usuario_actual.get('nombre', 'Administrador')
        rol = usuario_actual.get('rol', 'ADMIN')
        mostrar(f"""
        <div class="sire-side-user"><span class="sire-avatar">{esc(_iniciales(nombre))}</span>
          <div><b>{esc(nombre)}</b>{chip(esc(rol), 'info')}</div></div>
        """)
        if st.button("Cerrar sesión", key="nav_salir", icon=":material/logout:", use_container_width=True):
            _cerrar_sesion_admin()
            st.rerun()

    return activa


def mostrar_dashboard():
    """Muestra el panel con su menu lateral y la seccion elegida."""

    aplicar_tema(admin=True)

    usuario_actual = st.session_state.admin_usuario or {}
    es_super_admin = usuario_actual.get('rol') == 'SUPER_ADMIN'

    es_principal = bool(es_super_admin and get_auth_manager().es_superadmin_principal(st.session_state.admin_token))

    seccion = _menu_lateral(usuario_actual, es_super_admin, es_principal)
    _guardar_sesion_en_navegador()
    try:
        if st.query_params.get("s") != seccion:
            st.query_params["s"] = seccion
    except Exception:
        pass
    _, _, titulo, subtitulo = SECCIONES[seccion]
    encabezado_admin(titulo, subtitulo)

    # SIREA 3.3: Quipu, el asistente de bolsillo (flotante, abajo a la derecha, en todas las pantallas)
    try:
        from app_pages.quipu import quipu
        quipu(titulo)
    except Exception as e:  # noqa: BLE001  (si falla, la pantalla sigue funcionando)
        print(f"Quipu no disponible: {e}")

    # Notificación en la interfaz: una red pidió cambiar su contraseña.
    if es_super_admin and seccion != 'Solicitudes de Contraseña':
        n = pendientes_para_aviso()
        if n:
            col_av, col_bt = st.columns([5, 1.3], vertical_alignment="center")
            with col_av:
                mostrar(aviso(
                    "warn",
                    f"{n} red(es) solicitan cambiar su contraseña" if n != 1 else "Una red solicita cambiar su contraseña",
                    "Revise el sustento y responda o apruebe desde «Solicitudes de contraseña»."))
            with col_bt:
                st.button("Revisar ahora", key="btn_ir_solicitudes", type="primary", use_container_width=True,
                          icon=":material/arrow_forward:", on_click=_ir_a_seccion, args=('Solicitudes de Contraseña',))

    # Solicitudes de retiro de archivos esperando la decisión de oiis.winepi.
    if es_principal and seccion != 'Descarga y Limpieza':
        n_ret = pendientes_retiro()
        if n_ret:
            col_av, col_bt = st.columns([5, 1.3], vertical_alignment="center")
            with col_av:
                mostrar(aviso(
                    "warn",
                    f"{n_ret} solicitudes de retiro de archivos esperan su decisión" if n_ret != 1 else "Una solicitud de retiro de archivos espera su decisión",
                    "No se retira nada hasta que usted la apruebe."))
            with col_bt:
                st.button("Revisar ahora", key="btn_ir_retiros", type="primary", use_container_width=True,
                          icon=":material/arrow_forward:", on_click=_ir_a_seccion, args=('Descarga y Limpieza',))

    # Semana propuesta por el sistema al cerrar el corte: falta validarla (o ya la validó alguien).
    if seccion != 'Configuracion':
        banners_panel(lambda: _ir_a_seccion('Configuracion'))

    # ============================================================
    # MANEJO DE SECCIONES
    # ============================================================
    try:
        _mostrar_seccion(seccion)
    except Exception:  # noqa: BLE001  una sección con error no debe tumbar todo el panel
        import logging
        logging.getLogger("sirea.panel").exception("Error en la sección %s", seccion)
        mostrar(aviso("bad", "Esta sección tuvo un problema",
                      "El detalle quedó en el registro del servidor. Puede reintentar o ir a otra sección del menú; "
                      "su sesión sigue abierta."))
        st.button("Reintentar", key="btn_reintentar_seccion", icon=":material/refresh:", type="primary")

    pie_pagina()



def _mostrar_seccion(seccion: str):
    """Dibuja la sección elegida del menú."""
    if seccion == "Dashboard":
        mostrar_dashboard_principal()
    elif seccion == "Control de Atrasos":
        mostrar_control_atrasos()
    elif seccion == "Control de Duplicados":
        mostrar_control_duplicados()
    elif seccion == "Observaciones":
        mostrar_observaciones()
    elif seccion == "Progreso por Red":
        mostrar_progreso_redes()
    elif seccion == "Seguimiento Semana Activa":
        mostrar_seguimiento_semana_activa()
    elif seccion == "Informe por Semana":
        mostrar_informe_semana()
    elif seccion == "Respaldos":
        mostrar_respaldos()
    elif seccion == "Descarga y Limpieza":
        mostrar_descarga_limpieza()
    elif seccion == "Control de Actividad":
        mostrar_control_actividad()
    elif seccion == "Permisos de Operacion":
        mostrar_permisos_operacion()
    elif seccion == "Notificaciones":
        mostrar_notificaciones()
    elif seccion == "Gestion de Administradores":
        mostrar_gestion_admins()
    elif seccion == "Solicitudes de Contraseña":
        mostrar_solicitudes_password()
    elif seccion == "Cuentas del Panel":
        mostrar_cuentas_panel()
    elif seccion == "Credenciales de Red":
        mostrar_gestion_credenciales_red()
    elif seccion == "Gestion de Drive":
        mostrar_gestion_drive()
    elif seccion == "Exclusion de Centros":
        mostrar_gestion_exclusiones()
    elif seccion == "Configuracion":
        from app_pages.configuracion import main as config_main
        config_main()
    elif seccion == "Historial y Logs":
        mostrar_historial()
    elif seccion == "Agente de IA":
        from app_pages.admin_agentes_ia import mostrar_agentes_ia
        mostrar_agentes_ia()
    elif seccion == "Gobernanza de IA":
        from app_pages.admin_agentes_ia import mostrar_gobernanza_ia
        mostrar_gobernanza_ia()

def main():
    """Funcion principal de la pagina."""

    # La configuración de página (título, ícono, ancho) la fija app.py.
    init_session_state()
    _recuperar_sesion()

    # ============================================================
    # REVALIDAR LA SESIÓN EN CADA CARGA -- `admin_logueado` es solo un
    # booleano que se enciende una vez al iniciar sesión y por sí solo
    # no expira. Sin esto, una pestaña abierta sigue mostrando el panel
    # aunque el token ya haya vencido (8 horas, AuthManager.verificar_sesion)
    # o haya sido invalidado explícitamente (cambio de contraseña,
    # eliminación del administrador, reinicio del proceso).
    # ============================================================
    if st.session_state.admin_logueado:
        auth_manager = get_auth_manager()
        if not auth_manager.verificar_sesion(st.session_state.admin_token):
            st.session_state.admin_logueado = False
            st.session_state.admin_token = None
            st.session_state.admin_usuario = None
            st.session_state.admin_sesion_expirada = True

    if not st.session_state.admin_logueado:
        if st.session_state.pop('admin_sesion_expirada', False):
            st.warning("Tu sesión expiró. Por favor, vuelve a iniciar sesión.")
        mostrar_login()
    else:
        mostrar_dashboard()


if __name__ == "__main__":
    main()
