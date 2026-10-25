# pages/red_login.py
"""
Login por red: cada red asistencial entra con su propia contraseña
(generada y distribuida por el administrador, ver
pages/admin_credenciales_red.py) para ver SOLO su propio progreso de
envíos semana a semana (pages/red_progreso.py) -- sin acceso al
formulario de envío ni a los datos de otras redes.
"""

import streamlit as st

from src.auth_red import get_red_auth_manager
from src.data_loader import get_data_loader
from utils.helpers import sanitizar_html
from utils.cuentas_ui import campos_nueva_password, limpiar_campos_password
from utils.tema import (
    aplicar_tema, encabezado_publico, pie_pagina, titulo_pagina, mostrar,
    mostrar_aviso, icono, logo_uri, chip,
)
from app_pages.red_progreso import mostrar_progreso_red_login
from src.solicitudes_password import (
    get_solicitudes_password, plantilla_sustento, fecha_lima, parsear_fecha,
)
from utils.cuentas_ui import campos_correo_verificado
from utils.hilo import hilo_html


def init_session_state():
    """Inicializa las variables de sesion del login por red."""
    if 'red_token' not in st.session_state:
        st.session_state.red_token = None
    if 'red_actual' not in st.session_state:
        st.session_state.red_actual = None
    if 'red_logueada' not in st.session_state:
        st.session_state.red_logueada = False


def _marca_agua() -> str:
    """Escudo de la OIIS como marca de agua del panel izquierdo."""
    return f'<img src="{logo_uri("oiis-azul.svg")}" alt="" aria-hidden="true" class="sire-marca-agua">'


def mostrar_login_red():
    """Muestra el acceso por red: panel informativo a la izquierda y formulario a la derecha."""

    aplicar_tema()
    encabezado_publico("progreso")

    data_loader = get_data_loader()
    redes = data_loader.obtener_redes()

    with st.container(key="sire_split_claro"):
        izq, der = st.columns(2, gap="small")

        with izq:
            mostrar(f"""
            {_marca_agua()}
            <div class="sire-split-in">
              <span class="sire-pildora">{icono('barras', 15, 'currentColor', 2.4)}Para redes asistenciales</span>
              <h1>Portal de la red asistencial</h1>
              <p>Consulte el avance de su red semana a semana, los centros que faltan y el historial de envíos del año.</p>
              <div style="display:flex;flex-direction:column;gap:16px;margin-top:8px">
                <div class="sire-pt"><b>1</b><p>Elija su red y escriba la contraseña que le entregó la OIIS.</p></div>
                <div class="sire-pt"><b>2</b><p>El acceso es de solo lectura y muestra únicamente la información de su propia red.</p></div>
                <div class="sire-pt"><b>3</b><p>En su primer ingreso se le pedirá definir una contraseña propia.</p></div>
              </div>
            </div>
            <div class="sire-vista" aria-label="Ejemplo ilustrativo del avance de una red">
              <div class="sire-vista-h"><span>Red de ejemplo · Semana 39</span><small>Ejemplo</small></div>
              <div class="sire-vista-n"><b>3 de 5</b><span>centros enviaron · 60 %</span></div>
              <div class="sire-avance-pista" style="margin:0"><div style="width:60%;background:#0077C8"></div></div>
              <div style="display:flex;gap:8px;flex-wrap:wrap">
                <span class="sire-chip" style="background:#E6F4EA;color:#1E6B3A">{icono('check', 13, 'currentColor', 3)}3 enviaron</span>
                <span class="sire-chip" style="background:#FFF4D6;color:#7A5A00">{icono('reloj', 13, 'currentColor', 3)}2 pendientes</span>
              </div>
            </div>
            """)

        with der:
            with st.form("login_form_red", clear_on_submit=False):
                mostrar("""
                <h2 class="sire-form-t">Ingresar como red</h2>
                <p class="sire-form-s">Use la contraseña asignada a su red asistencial.</p>
                """)
                red = st.selectbox(
                    "Red asistencial", options=redes, index=None,
                    placeholder="Seleccione su red", key="input_red_login",
                )
                password = st.text_input(
                    "Contraseña de la red", type="password",
                    placeholder="Contraseña de su red",
                    key="input_password_red_login",
                )

                submit = st.form_submit_button("Ver el progreso de mi red", width='stretch', type="primary")

                mostrar(f"""
                <div class="sire-form-nota">{icono('info', 18, '#0077C8', 2.2)}
                <span>La contraseña la genera y entrega la OIIS; no hay registro ni recuperación automática.
                Tras 5 intentos fallidos el acceso se bloquea 5 minutos.</span></div>
                """)

                if submit:
                    if red and password:
                        red_auth = get_red_auth_manager()
                        resultado = red_auth.login(red, password)

                        if resultado['exito']:
                            st.session_state.red_token = resultado['token']
                            st.session_state.red_actual = resultado['red']
                            st.session_state.red_logueada = True
                            st.rerun()
                        else:
                            st.error(resultado['mensaje'])
                    else:
                        st.warning("Seleccione su red e ingrese la contraseña.")

            mostrar('<div class="sire-pie-form">¿Es personal de la OIIS?</div>')
            if st.button("Ir al panel de administración", key="link_ir_admin"):
                st.session_state.pagina = 'admin'
                st.session_state.seccion_admin = 'Dashboard'
                st.rerun()

    pie_pagina(margen=0)


def _cerrar_sesion_red():
    """Limpia el estado de sesión de la red (logout o expiración)."""
    red_auth = get_red_auth_manager()
    if st.session_state.get('red_token'):
        red_auth.logout(st.session_state.red_token)
    st.session_state.red_logueada = False
    st.session_state.red_token = None
    st.session_state.red_actual = None


def _formulario_cambio_password(red_auth, red: str, obligatorio: bool, key_prefix: str):
    """
    Formulario para que la propia red elija una contraseña nueva.
    Se reutiliza tanto para el cambio OBLIGATORIO (primer uso con una
    contraseña temporal asignada por el administrador) como para el
    cambio VOLUNTARIO (disponible siempre desde el dashboard).
    La contraseña debe cumplir la política de src/password_policy.py; la
    pantalla muestra qué falta y por qué se pide cada requisito.
    """
    nueva, confirmar = campos_nueva_password(
        f"{key_prefix}_pw", contexto=[red],
        etiqueta_nueva="Nueva contraseña", etiqueta_confirmar="Confirmar nueva contraseña",
    )
    if st.button("Guardar nueva contraseña", key=f"{key_prefix}_guardar", type="primary", use_container_width=True):
        if not nueva or not confirmar:
            st.error("Complete ambos campos.")
        elif nueva != confirmar:
            st.error("Las contraseñas no coinciden.")
        else:
            exito, mensaje = red_auth.cambiar_password_propio(red, nueva)
            if exito:
                limpiar_campos_password(f"{key_prefix}_pw")
                st.session_state['_pw_red_actualizada'] = True
                st.rerun()
            else:
                st.error(mensaje)


# ============================================================
# CAMBIO DE CONTRASEÑA CON APROBACIÓN DE LA OIIS
# ============================================================

_ESTADO_TEXTO = {
    "PENDIENTE": ("En revisión", "info"),
    "APROBADA": ("Aprobada", "ok"),
    "RECHAZADA": ("No aprobada", "warn"),
    "COMPLETADA": ("Completada", "ok"),
    "CANCELADA": ("Cancelada", "mute"),
    "VENCIDA": ("Vencida", "warn"),
}


def _chip_estado_solicitud(estado: str) -> str:
    texto, tono = _ESTADO_TEXTO.get(estado, (estado, "mute"))
    return chip(texto, tono)


def _formulario_nueva_solicitud(solicitudes, red: str):
    """Formulario con mensaje predefinido (nombre, correo y texto editable) para sustentar el cambio."""
    mostrar_aviso(
        "info", "El cambio de contraseña necesita aprobación",
        "Para evitar cambios frecuentes, después del primer cambio la OIIS debe autorizar uno nuevo. "
        "Complete el mensaje con el motivo; recibirá un acuse en su correo y la respuesta aparecerá aquí.")

    nombre = st.text_input("Nombre completo del solicitante *", key="sol_nombre",
                           placeholder="Ej. María Elena Quispe Rojas")
    correo, ev = campos_correo_verificado(
        "sol_correo", "sol_correo_repetido", "sol_correo_noinst", "sire_sug_sol",
        ayuda="A este correo se enviará el acuse de su solicitud y las respuestas de la OIIS.",
        que_recibira="el acuse y las respuestas de la OIIS",
    )

    # El texto predefinido se prepara una vez; luego la persona lo edita libremente.
    clave_txt = f"sol_texto_{red}"
    if clave_txt not in st.session_state:
        st.session_state[clave_txt] = plantilla_sustento(red, "")
    texto = st.text_area(
        "Mensaje para la OIIS *", key=clave_txt, height=280,
        help="Puede editar todo el texto. Reemplace la línea entre corchetes por el motivo del cambio.",
    )
    st.caption("Sea claro y específico (por ejemplo: cambio de personal responsable, sospecha de que otra persona "
               "conoce la contraseña, etc.). Evite escribir contraseñas en este mensaje.")

    if st.button("Enviar solicitud", key="sol_enviar", type="primary", icon=":material/send:",
                 use_container_width=True):
        if ev["estado"] != "ok":
            st.error(ev["detalle"] or ev["mensaje"] or "Revise el correo.")
        else:
            ok, msg, _ = solicitudes.crear(red, nombre, correo, texto)
            if ok:
                for k in ("sol_nombre", "sol_correo", "sol_correo_repetido", "sol_correo_noinst", clave_txt):
                    st.session_state.pop(k, None)
                st.session_state["_sol_enviada"] = msg
                st.rerun()
            else:
                st.error(msg)


def _bloque_hilo(solicitudes, sol: dict, puede_responder: bool):
    """Datos de la solicitud, mensajes y, si está pendiente, el cuadro para responder."""
    mostrar(
        f'<div style="display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin-bottom:10px">'
        f'<b style="color:#1D3F76">Solicitud {sanitizar_html(str(sol.get("codigo", "")))}</b>'
        f'{_chip_estado_solicitud(sol.get("estado", ""))}'
        f'<span style="color:#4F6070;font-size:14px">Enviada el {fecha_lima(sol.get("fecha_creacion"))}</span></div>'
    )
    mostrar(hilo_html(solicitudes.mensajes(sol["id"]), propio="RED"))

    if puede_responder:
        with st.form(f"sol_resp_{sol['id']}", clear_on_submit=True, border=False):
            resp = st.text_area("Agregar un mensaje", height=110, placeholder="Escriba aquí su respuesta o la información solicitada")
            c1, c2 = st.columns([3, 1.4])
            with c1:
                enviar = st.form_submit_button("Enviar mensaje", type="primary", icon=":material/send:",
                                               use_container_width=True)
            with c2:
                actualizar = st.form_submit_button("Actualizar", icon=":material/refresh:", use_container_width=True)
        if enviar:
            ok, msg = solicitudes.responder_red(sol["id"], sol["red"], resp)
            if ok:
                st.rerun()
            else:
                st.error(msg)
        elif actualizar:
            st.rerun()
        if st.button("Cancelar la solicitud", key=f"sol_cancel_{sol['id']}", type="tertiary", icon=":material/close:"):
            ok, msg = solicitudes.cancelar(sol["id"], sol["red"])
            st.rerun() if ok else st.error(msg)


def _modulo_cambio_password(red_auth, red: str):
    """
    Cambio de contraseña voluntario. Requiere una solicitud APROBADA por la
    OIIS (el servidor lo vuelve a comprobar en RedAuthManager.cambiar_password_propio).
    """
    solicitudes = get_solicitudes_password()
    if not solicitudes.disponible():
        mostrar_aviso(
            "info", "Cambio de contraseña",
            "Para cambiar la contraseña de su red, comuníquese con la OIIS.")
        return

    abierta = solicitudes.abierta(red)
    ultima = abierta or solicitudes.ultima(red)

    enviada = st.session_state.pop("_sol_enviada", None)
    if enviada:
        mostrar_aviso("ok", "Solicitud enviada", sanitizar_html(enviada))

    titulo = "Cambiar contraseña"
    if abierta:
        titulo += " · solicitud " + ("aprobada" if abierta["estado"] == "APROBADA" else "en revisión")

    with st.expander(titulo, expanded=bool(abierta) or bool(enviada)):
        if abierta and abierta["estado"] == "APROBADA":
            venc = parsear_fecha(abierta.get("fecha_vencimiento"))
            mostrar_aviso(
                "ok", "La OIIS aprobó su solicitud",
                f"Ya puede elegir su nueva contraseña. La autorización vence el <strong>{fecha_lima(venc)}</strong> (hora de Lima).")
            _formulario_cambio_password(red_auth, red, obligatorio=False, key_prefix="voluntario")
            if st.toggle("Ver el intercambio de mensajes", key="sol_ver_hilo_apr"):
                _bloque_hilo(solicitudes, abierta, puede_responder=False)
        elif abierta:
            _bloque_hilo(solicitudes, abierta, puede_responder=True)
        else:
            if ultima:
                texto, _ = _ESTADO_TEXTO.get(ultima.get("estado"), (ultima.get("estado"), ""))
                if st.toggle(f"Ver la última solicitud ({ultima.get('codigo')}) · {texto}", key="sol_ver_ultima"):
                    _bloque_hilo(solicitudes, ultima, puede_responder=False)
            _formulario_nueva_solicitud(solicitudes, red)


def mostrar_cambio_password_obligatorio(red_auth, red: str):
    """
    Pantalla de cambio OBLIGATORIO de contraseña: se muestra en vez
    del dashboard cuando la red todavía está usando una contraseña
    temporal asignada por el administrador (debe_cambiar_password = True
    en credenciales_red). No se puede omitir ni ver el progreso hasta
    elegir una contraseña propia.
    """
    aplicar_tema()
    encabezado_publico("progreso")

    with st.container(key="sire_split_claro"):
        izq, der = st.columns(2, gap="small")
        with izq:
            mostrar(f"""
            {_marca_agua()}
            <div class="sire-split-in">
              <span style="width:64px;height:64px;border-radius:18px;background:#FFFFFF;display:inline-flex;align-items:center;justify-content:center;box-shadow:0 6px 16px rgba(0,80,140,.16)">{icono('candado', 32, '#0077C8', 2)}</span>
              <span class="sire-pildora">Solo en el primer ingreso</span>
              <h1>Defina su contraseña</h1>
              <p>La red <strong>{sanitizar_html(str(red))}</strong> ingresó con una contraseña temporal.
              Por seguridad, elija una contraseña propia para poder ver su progreso.</p>
              <p style="font-size:15px">Después de guardarla, la contraseña temporal deja de funcionar.</p>
            </div>
            <div></div>
            """)
        with der:
            with st.container(key="sire_form_card"):
                mostrar("""
                <h2 class="sire-form-t">Cambio de contraseña</h2>
                <p class="sire-form-s">Elija una contraseña segura que solo usted conozca.</p>
                """)
                _formulario_cambio_password(red_auth, red, obligatorio=True, key_prefix="obligatorio")
                if st.button("Cerrar sesión", key="btn_logout_cambio_obligatorio", use_container_width=True):
                    _cerrar_sesion_red()
                    st.rerun()

    pie_pagina(margen=0)


def mostrar_dashboard_red():
    """Muestra el progreso de la red autenticada, con opción de cerrar sesión."""

    aplicar_tema()
    encabezado_publico("progreso")

    red = st.session_state.red_actual
    red_auth = get_red_auth_manager()

    col_t, col_b = st.columns([4, 1.4], vertical_alignment="bottom")
    with col_t:
        titulo_pagina(
            f"Progreso de la red {sanitizar_html(str(red))}",
            "Cumplimiento semanal de su red. Vista de solo lectura.",
            migas="Inicio / Mi progreso",
        )
    with col_b:
        st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
        if st.button("Cerrar sesión", key="btn_logout_red", use_container_width=True):
            _cerrar_sesion_red()
            st.rerun()

    if st.session_state.pop('_pw_red_actualizada', False):
        mostrar_aviso("ok", "Su contraseña se actualizó correctamente",
                      "La contraseña anterior ya no funciona. Use la nueva la próxima vez que ingrese.")

    _modulo_cambio_password(red_auth, red)

    mostrar_progreso_red_login(red)
    pie_pagina()


def main():
    """Función principal de la página de login por red."""

    # La configuración de página (título, ícono, ancho) la fija app.py.
    init_session_state()

    # La sesión de una red expira a las 8 horas (misma lógica que el
    # login de administradores) -- si el token ya no es válido, se
    # regresa al login sin necesidad de que la red haga nada especial.
    red_auth = get_red_auth_manager()
    if st.session_state.red_logueada and not red_auth.verificar_sesion(st.session_state.red_token):
        st.session_state.red_logueada = False
        st.session_state.red_token = None
        st.session_state.red_actual = None

    if not st.session_state.red_logueada:
        mostrar_login_red()
    elif red_auth.debe_cambiar_password(st.session_state.red_actual):
        # Contraseña temporal sin cambiar: se bloquea el acceso al
        # progreso hasta que la red elija una contraseña propia.
        mostrar_cambio_password_obligatorio(red_auth, st.session_state.red_actual)
    else:
        mostrar_dashboard_red()


if __name__ == "__main__":
    main()
