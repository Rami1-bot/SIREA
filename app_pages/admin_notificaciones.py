# pages/admin_notificaciones.py
"""
Notificaciones y Recordatorios
Permite enviar recordatorios a los responsables de las redes.
"""

import re
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from src.email_sender import get_email_sender
from src.config import Config
from app_pages.admin_helpers import requerir_admin
from src.agentes.acciones import detalle_log_recordatorio
from utils.tema import mostrar, aviso, seccion, chip
from utils.tema_admin import esc, panel_cab

# NOTA: la semana y el año activos se obtienen de Config.get_semana_actual()
# y Config.get_anio_actual() (antes había copias locales de estas funciones
# con fallbacks inconsistentes entre páginas: esta llegaba a devolver
# "semana 1" fija si fallaba la consulta a la base de datos).


def obtener_fecha_corte_configurada() -> Optional[datetime]:
    """
    Obtiene la fecha de corte configurada por el administrador.
    """
    return Config.get_fecha_corte_datetime()


def calcular_dias_retraso() -> int:
    """
    Calcula los días de retraso basándose en la fecha de corte configurada por el administrador.
    """
    fecha_corte = obtener_fecha_corte_configurada()
    if not fecha_corte:
        return 0
    ahora = Config.obtener_fecha_actual()
    if ahora > fecha_corte:
        return (ahora - fecha_corte).days
    return 0


def verificar_estado_semana(semana: int, semana_activa: int, fecha_corte: datetime) -> dict:
    """
    Verifica el estado de una semana específica.
    Retorna información detallada del estado.
    """
    ahora = Config.obtener_fecha_actual()
    
    # Caso 1: Semana anterior a la activa (atraso)
    if semana < semana_activa:
        semanas_atraso = semana_activa - semana
        dias_retraso = semanas_atraso * 7
        return {
            'tipo': 'atrasado',
            'atrasada': True,
            'titulo': 'Recordatorio de atraso',
            'mensaje': f"La semana {semana} es anterior a la semana activa ({semana_activa}). Se registran {semanas_atraso} semanas de atraso ({dias_retraso} días).",
            'dias_retraso': dias_retraso,
            'semanas_atraso': semanas_atraso,
            'urgente': True
        }
    
    # Caso 2: Semana igual a la activa
    if semana == semana_activa:
        if ahora > fecha_corte:
            dias_retraso = (ahora - fecha_corte).days
            return {
                'tipo': 'atrasado',
                'atrasada': True,
                'titulo': 'Recordatorio de atraso',
                'mensaje': f"La fecha de corte ({fecha_corte.strftime('%d/%m/%Y %H:%M')}) ha vencido hace {dias_retraso} días.",
                'dias_retraso': dias_retraso,
                'semanas_atraso': 0,
                'urgente': True
            }
        else:
            dias_restantes = (fecha_corte - ahora).days
            return {
                'tipo': 'preventivo',
                'atrasada': False,
                'titulo': 'Recordatorio preventivo',
                'mensaje': f"La semana {semana} está dentro del plazo establecido. Faltan {dias_restantes} días para la fecha de corte.",
                'dias_retraso': 0,
                'semanas_atraso': 0,
                'urgente': False
            }
    
    # Caso 3: Semana futura
    if semana > semana_activa:
        return {
            'tipo': 'programado',
            'atrasada': False,
            'titulo': 'Recordatorio programado',
            'mensaje': f"La semana {semana} es futura. La semana activa actual es la {semana_activa}.",
            'dias_retraso': 0,
            'semanas_atraso': 0,
            'urgente': False
        }
    
    # Caso por defecto
    return {
        'tipo': 'indeterminado',
        'atrasada': False,
        'titulo': 'Estado no determinado',
        'mensaje': "No se ha podido determinar el estado de la semana seleccionada.",
        'dias_retraso': 0,
        'semanas_atraso': 0,
        'urgente': False
    }


def _pendientes_por_red(db_manager, data_loader, anio, semana, redes_a_procesar):
    """{red: [centros que aún no enviaron]} para la semana y las redes dadas."""
    envios = db_manager.obtener_envios(anio=anio, semana=semana, limit=2000)

    enviados_por_red = {}
    for envio in envios:
        red = envio.get('red', '')
        centros = envio.get('centros', [])
        if not isinstance(centros, list):
            continue
        for c in centros:
            if isinstance(c, dict):
                nombre = c.get('nombre', str(c))
            else:
                # En la tabla envios los centros se guardan como texto
                # "CODIGO NOMBRE" (ej. "245 H.II JAEN"): hay que quitar el
                # código para compararlos con la lista de centros de la red
                # (que solo trae el nombre); si no, "pendientes" mostraría
                # TODOS los centros en vez de solo los que faltan.
                texto = str(c).strip()
                partes = texto.split(' ', 1)
                nombre = texto
                if len(partes) >= 2:
                    try:
                        int(partes[0])
                        nombre = partes[1].strip()
                    except ValueError:
                        nombre = texto
            enviados_por_red.setdefault(red, set()).add(nombre)

    resultado = {}
    for red in redes_a_procesar:
        nombres = []
        for c in data_loader.obtener_centros(red):
            nombres.append(c.get('nombre', str(c)) if isinstance(c, dict) else str(c))
        pendientes = [n for n in nombres if n not in enviados_por_red.get(red, set())]
        if pendientes:
            resultado[red] = pendientes
    return resultado


_TIPO_RECORDATORIO = {
    'atrasado': ('Recordatorio de envío tardío', 'bad',
                 'Se enviará el correo con cabecera roja: el plazo ya venció.'),
    'preventivo': ('Recordatorio preventivo', 'info',
                   'Se enviará el correo con cabecera azul: el plazo sigue vigente.'),
    'programado': ('Recordatorio programado', 'mute',
                   'La semana elegida aún no es la activa; se enviará como preventivo.'),
}


_RE_CORREO = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def _copias(texto: str, principal: str = "") -> list:
    """Correos válidos en copia, sin repetir y sin el destinatario principal (máximo 5)."""
    vistos, out = {str(principal or "").strip().lower()}, []
    for c in re.split(r"[,;\s]+", str(texto or "")):
        c = c.strip().lower()
        if c and _RE_CORREO.match(c) and c not in vistos:
            vistos.add(c)
            out.append(c)
    return out[:5]


def _copias_invalidas(texto: str) -> list:
    return [c for c in re.split(r"[,;\s]+", str(texto or "")) if c.strip() and not _RE_CORREO.match(c.strip())]


def _llenar_responsable(red: str):
    """SIREA 3.3: llena el formulario con la persona elegida y pone en copia a los demás responsables."""
    lista = st.session_state.get("_notif_resp_lista") or []
    elegido = st.session_state.get("notif_resp_sel")
    por_correo = {r["correo"]: r for r in lista}
    r = por_correo.get(elegido)
    if not r:
        return
    nombres, apellidos = r.get("nombres") or "", r.get("apellidos") or ""
    if not (nombres or apellidos):
        partes = str(r.get("nombre") or "").split(" ", 1)
        nombres, apellidos = partes[0], (partes[1] if len(partes) > 1 else "")
    st.session_state["notif_dest_nombre"] = nombres
    st.session_state["notif_dest_apellido"] = apellidos
    st.session_state["notif_dest_correo"] = r["correo"]
    st.session_state["notif_dest_cc"] = ", ".join(x["correo"] for x in lista if x["correo"] != r["correo"])


def _sugerir_responsables(red: str):
    """Quiénes enviaron de verdad por la red en las últimas 8 semanas (lo calcula el sistema, sin IA)."""
    if not red or red == "Todas":
        st.caption("Elija una red en el paso 1 y el sistema le sugerirá a sus responsables del envío.")
        return
    try:
        from src.agentes.acciones import responsables_de_red
        lista = responsables_de_red(red, semanas=8, maximo=5)
    except Exception:  # noqa: BLE001
        lista = []
    if not lista:
        st.caption(f"No hay envíos de {esc(red)} en las últimas 8 semanas: escriba los datos a mano.")
        return
    st.session_state["_notif_resp_lista"] = lista
    opciones = [None] + [r["correo"] for r in lista]
    por_correo = {r["correo"]: r for r in lista}
    if st.session_state.get("notif_resp_sel") not in opciones or st.session_state.get("_notif_resp_red") != red:
        st.session_state["notif_resp_sel"] = None
        st.session_state["_notif_resp_red"] = red
    st.selectbox(
        f"Responsables del envío de {red} (según quién envió en las últimas 8 semanas)", options=opciones,
        key="notif_resp_sel", on_change=_llenar_responsable, args=(red,),
        format_func=lambda c: "Elija para llenar el formulario…" if c is None else
        f"{por_correo[c]['nombre']} · {c} · {por_correo[c]['envios']} envío(s), último {por_correo[c]['ultimo']}",
    )
    st.caption("Al elegir a una persona se llenan nombre, apellido y correo, y los demás responsables quedan en copia. "
               "Puede corregir cualquier dato antes de enviar.")


def mostrar_notificaciones():
    """Muestra la interfaz de notificaciones."""

    requerir_admin()

    db_manager = get_db_manager()
    data_loader = get_data_loader()
    email_sender = get_email_sender()

    semana_activa = Config.get_semana_actual()
    anio_activo = Config.get_anio_actual()

    fecha_corte_configurada = obtener_fecha_corte_configurada()
    fecha_corte_str = fecha_corte_configurada.strftime('%d/%m/%Y %H:%M:%S') if fecha_corte_configurada else "No configurada"

    anios_disponibles = db_manager.obtener_anios_epidemiologicos()
    if not anios_disponibles:
        mostrar(aviso("warn", "No hay años epidemiológicos configurados",
                      "Configure un año en la sección Configuración."))
        return

    redes = data_loader.obtener_redes()

    # SIREA 3.1: recordatorios sugeridos por el Agente de IA (se aprueban aquí mismo).
    from app_pages.agente_sugerencias import aviso_recordatorio_reciente, panel as panel_sugerencias
    panel_sugerencias(["RECORDATORIO_RED"], "Sugerencias del agente: recordatorios listos para revisar", clave="notif")

    col_main, col_side = st.columns([2.1, 1])

    # ============================================================
    # PASO 1: SEMANA Y RED
    # ============================================================
    with col_main:
        with st.container(key="sec_notif_1"):
            seccion(1, "Seleccione la semana y la red")

            # SIREA 3.3: filtro común Año · Semana · Red (el mismo de los demás módulos)
            from app_pages.filtro_periodo import filtro_periodo
            periodo = filtro_periodo("notif", redes=redes)
            anio_seleccionado, semana_seleccionada = periodo.anio, periodo.semana
            red_seleccionada = periodo.red or "Todas"

            buscar = st.button("Buscar centros pendientes", type="primary",
                               icon=":material/search:", key="notif_buscar")
            aviso_recordatorio_reciente(red_seleccionada)

    estado_semana = verificar_estado_semana(
        semana=semana_seleccionada,
        semana_activa=semana_activa,
        fecha_corte=fecha_corte_configurada,
    )

    # ============================================================
    # COLUMNA LATERAL: TIPO DE RECORDATORIO
    # ============================================================
    with col_side:
        titulo_tipo, tono_tipo, texto_tipo = _TIPO_RECORDATORIO.get(
            estado_semana['tipo'], _TIPO_RECORDATORIO['preventivo'])
        mostrar(f"""
        <div class="sire-card"><div class="sire-card-h">Tipo de recordatorio</div>
        <div class="sire-card-b" style="padding-top:16px">
        <p style="margin:0 0 12px;font-size:15px">El sistema elige el tipo según la fecha de corte.</p>
        <div style="margin-bottom:12px">{chip(titulo_tipo, tono_tipo)}</div>
        <p style="margin:0 0 8px;font-size:14px;color:#33424F">{esc(estado_semana['mensaje'])}</p>
        <p style="margin:0;font-size:13px;color:#566573">{texto_tipo}</p>
        </div></div>
        """)
        mostrar(aviso("info", "Fecha de corte configurada", esc(fecha_corte_str)))
        if st.button("Ir a Configuración", key="notif_ir_config", icon=":material/tune:",
                     use_container_width=True):
            st.session_state.seccion_admin = 'Configuracion'
            st.rerun()

    # ============================================================
    # BUSQUEDA (se guarda para no perderla al marcar casillas)
    # ============================================================
    clave_busqueda = (anio_seleccionado, semana_seleccionada, red_seleccionada)
    if buscar:
        redes_a_procesar = redes if red_seleccionada == "Todas" else [red_seleccionada]
        with st.spinner("Buscando centros pendientes..."):
            pendientes = _pendientes_por_red(
                db_manager, data_loader, anio_seleccionado, semana_seleccionada, redes_a_procesar)
        st.session_state.notif_busqueda = {'clave': clave_busqueda, 'pendientes': pendientes}

    busqueda = st.session_state.get('notif_busqueda')

    # ============================================================
    # PASO 2: CENTROS PENDIENTES
    # ============================================================
    centros_a_enviar = []
    with col_main:
        with st.container(key="sec_notif_2"):
            if not busqueda:
                seccion(2, "Centros pendientes")
                st.caption("Elija año, semana y red, y pulse «Buscar centros pendientes».")
            elif busqueda['clave'] != clave_busqueda:
                seccion(2, "Centros pendientes")
                mostrar(aviso("warn", "Cambió la selección",
                              "Pulse «Buscar centros pendientes» para actualizar la lista."))
            else:
                pendientes = busqueda['pendientes']
                total = sum(len(v) for v in pendientes.values())
                if total == 0:
                    seccion(2, "Centros pendientes (0)")
                    mostrar(aviso("ok", "Todos los centros enviaron su reporte",
                                  f"Semana {semana_seleccionada} de {anio_seleccionado}."))
                else:
                    seccion(2, f"Centros pendientes ({total})")
                    st.caption("Marque los centros que incluirá el recordatorio.")
                    for red, lista in pendientes.items():
                        st.markdown(f"**{red}** · {len(lista)} pendientes")
                        for centro in lista:
                            if st.checkbox(centro, value=True, key=f"notif_chk_{red}_{centro}"):
                                centros_a_enviar.append(centro)

    # ============================================================
    # PASO 3: DESTINATARIO
    # ============================================================
    with col_main:
        with st.container(key="sec_notif_3"):
            seccion(3, "Destinatario")
            _sugerir_responsables(red_seleccionada)
            with st.form("form_enviar_recordatorio", border=False):
                f1, f2 = st.columns(2)
                with f1:
                    nombre_destinatario = st.text_input("Nombre del responsable", key="notif_dest_nombre")
                with f2:
                    apellido_destinatario = st.text_input("Apellido del responsable", key="notif_dest_apellido")
                f3, f4 = st.columns([1.6, 1])
                with f3:
                    correo_destinatario = st.text_input("Correo electrónico", key="notif_dest_correo")
                with f4:
                    telefono_destinatario = st.text_input("Teléfono (opcional)", placeholder="9XX XXX XXX")
                copias_txt = st.text_input("En copia (opcional; otros responsables de la red, separados por comas)",
                                           key="notif_dest_cc")

                enviar = st.form_submit_button("Enviar recordatorio", type="primary",
                                               icon=":material/mail:")

        if enviar:
            if not nombre_destinatario or not apellido_destinatario or not correo_destinatario:
                mostrar(aviso("bad", "Faltan datos", "Complete nombre, apellido y correo del responsable."))
            elif '@' not in correo_destinatario:
                mostrar(aviso("bad", "Correo electrónico inválido"))
            elif _copias_invalidas(copias_txt):
                mostrar(aviso("bad", "Revise los correos en copia", esc(", ".join(_copias_invalidas(copias_txt)), 200)))
            elif not busqueda or busqueda['clave'] != clave_busqueda:
                mostrar(aviso("warn", "Busque primero los centros pendientes",
                              "La lista de centros debe corresponder a la semana y red elegidas."))
            elif not centros_a_enviar:
                mostrar(aviso("warn", "No hay centros marcados",
                              "Marque al menos un centro pendiente para enviar el recordatorio."))
            else:
                with st.spinner("Enviando recordatorio..."):
                    tipo = "ATRASADO" if estado_semana['tipo'] == 'atrasado' else "PREVENTIVO"

                    exito, mensaje = email_sender.enviar_recordatorio(
                        destinatario=correo_destinatario,
                        nombre_usuario=f"{nombre_destinatario} {apellido_destinatario}",
                        red=red_seleccionada if red_seleccionada != "Todas" else "Todas las redes",
                        semana=semana_seleccionada,
                        fecha_limite=fecha_corte_str,
                        centros_pendientes=centros_a_enviar,
                        anio=anio_seleccionado,
                        semana_actual=semana_activa,
                        anio_actual=anio_activo,
                        tipo=tipo,
                        cc=_copias(copias_txt, correo_destinatario) or None,
                    )

                    if exito:
                        cc_ok = _copias(copias_txt, correo_destinatario)
                        mostrar(aviso("ok", "Recordatorio enviado", f"Se envió a {esc(correo_destinatario)}"
                                      + (f" con copia a {esc(', '.join(cc_ok), 200)}" if cc_ok else "") + "."))
                        db_manager.registrar_log(
                            usuario=st.session_state.admin_usuario.get('usuario', 'admin'),
                            accion='ENVIO_RECORDATORIO',
                            detalle=detalle_log_recordatorio(
                                correo_destinatario, red_seleccionada if red_seleccionada != "Todas" else "Todas las redes",
                                semana_seleccionada, anio_seleccionado, tipo)
                        )
                    else:
                        mostrar(aviso("bad", "No se pudo enviar el correo", esc(mensaje)))
        else:
            remitente = getattr(Config, 'EMAIL_REMITENTE', '') or 'la cuenta institucional'
            st.caption(f"Se enviará desde {remitente}.")
