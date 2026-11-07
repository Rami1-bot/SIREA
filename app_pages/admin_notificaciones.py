# pages/admin_notificaciones.py
"""
Notificaciones y Recordatorios
Permite enviar recordatorios a los responsables de las redes.
"""

import time

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from src.email_sender import get_email_sender
from src.config import Config
from src.responsables_red import get_responsables_red, ORIGEN_REGISTRADO
from src.validacion_correo import formato_valido, normalizar
from app_pages.admin_helpers import requerir_admin, actor_actual
from src.auditoria import get_auditoria
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


def _fijar_seleccion(todos: bool, filas):
    st.session_state.notif_sel = set(filas) if todos else set()
    st.session_state.notif_ver = st.session_state.get('notif_ver', 0) + 1


def _tabla_centros(pendientes: dict) -> list:
    """Tabla de centros pendientes con casilla «Incluir», búsqueda y filtro por red. Devuelve los nombres marcados."""
    filas = [(r, c) for r, lista in pendientes.items() for c in lista]
    sel = st.session_state.setdefault('notif_sel', set(filas))
    sel &= set(filas)                                        # por si cambió la lista
    ver = st.session_state.get('notif_ver', 0)

    with st.container(key="tnav_notif"):
        c1, c2 = st.columns([2.2, 1.2], gap="medium", vertical_alignment="bottom")
        with c1:
            consulta = st.text_input("Buscar centro", key="notif_q", placeholder="Escriba para buscar",
                                     icon=":material/search:")
        with c2:
            if len(pendientes) > 1:
                red_f = st.selectbox("Ver solo una red", ["Todas"] + list(pendientes), key="notif_f_red")
            else:
                red_f = "Todas"
        b1, b2, _ = st.columns([1.6, 1.6, 1.4], gap="small")
        with b1:
            st.button("Marcar todos", key="notif_marcar_todos", icon=":material/done_all:",
                      on_click=_fijar_seleccion, args=(True, filas), use_container_width=True)
        with b2:
            st.button("Quitar todos", key="notif_quitar_todos", icon=":material/remove_done:",
                      on_click=_fijar_seleccion, args=(False, filas), use_container_width=True)

    q = (consulta or "").strip().lower()
    visibles = [(r, c) for r, c in filas
                if (red_f == "Todas" or r == red_f) and (not q or all(t in f"{r} {c}".lower() for t in q.split()))]
    if not visibles:
        mostrar('<div class="sire-vacio">Ningún centro coincide con la búsqueda.</div>')
    else:
        df = pd.DataFrame({
            "Incluir": [(r, c) in sel for r, c in visibles],
            "Red": [r for r, _ in visibles],
            "Centro": [c for _, c in visibles],
        })
        editado = st.data_editor(
            df, hide_index=True, use_container_width=True, disabled=["Red", "Centro"],
            height=min(420, 40 + 36 * len(df)),
            column_config={"Incluir": st.column_config.CheckboxColumn("Incluir", width="small")},
            key=f"notif_ed_{ver}_{abs(hash((q, red_f)))}",
        )
        for (r, c), marcado in zip(visibles, editado["Incluir"].tolist()):
            if marcado:
                sel.add((r, c))
            else:
                sel.discard((r, c))
    marcados = [c for r, c in filas if (r, c) in sel]
    st.caption(f"{len(marcados)} de {len(filas)} centros marcados. La selección se conserva al buscar o filtrar.")
    return marcados


def _lista_responsables(red: str) -> list:
    """Responsables de la red (guardados + detectados en envíos), con memoria de 60 s."""
    cache = st.session_state.get('notif_resp_cache')
    if cache and cache[0] == red and time.time() - cache[1] < 60:
        return cache[2]
    lista = get_responsables_red().combinados(red) if red and red != "Todas" else []
    st.session_state.notif_resp_cache = (red, time.time(), lista)
    return lista


def _centros_por_destino(destinos: list, centros: list, por_centro: bool) -> list:
    """[(destino, centros)]: todos reciben todo, o cada uno solo los centros que atiende (el resto va al primero)."""
    if not por_centro or len(destinos) < 2:
        return [(d, list(centros)) for d in destinos]
    asignados = [[c for c in centros if c in set(d.get('centros') or [])] for d in destinos]
    sueltos = [c for c in centros if not any(c in a for a in asignados)]
    asignados[0] = [c for c in centros if c in set(asignados[0]) or c in sueltos]
    return [(d, a) for d, a in zip(destinos, asignados) if a]


def _paso_envio(db_manager, email_sender, *, red, anio, semana, semana_activa, anio_activo, estado_semana,
                fecha_corte_str, busqueda, clave_busqueda, centros, resumen_ph):
    resp_obj = get_responsables_red()
    ver_m = st.session_state.get('notif_m_ver', 0)
    k = lambda n: f"notif_m_{n}_{ver_m}"            # noqa: E731  (claves del formulario manual)

    resultado = st.session_state.get('notif_resultado')
    if resultado:
        for tipo, titulo, texto in resultado:
            mostrar(aviso(tipo, titulo, texto))

    responsables = _lista_responsables(red)
    elegidos = []
    if red == "Todas":
        st.caption("Con «Todas» las redes no hay responsables que proponer: escriba el destinatario más abajo.")
    elif not responsables:
        st.caption("Aún no hay responsables conocidos de esta red. Escriba uno abajo y, si quiere, guárdelo.")
    else:
        st.markdown(f"**Responsables conocidos de {esc(red)}**")
        st.caption("Salen de los envíos anteriores y de los que usted guardó. Marque a quién enviar; "
                   "por defecto va la persona que envió más recientemente.")
        for i, p in enumerate(responsables):
            with st.container(key=f"resp_card_{i}"):
                c1, c2 = st.columns([0.07, 1], vertical_alignment="top")
                with c1:
                    marcado = st.checkbox(f"Enviar a {p['nombre']} {p['apellido']}", value=(i == 0),
                                          key=f"notif_resp_{red}_{p['correo']}", label_visibility="collapsed")
                with c2:
                    etiq_origen = chip(p['origen'], "ok" if p['origen'] == ORIGEN_REGISTRADO else "info")
                    reciente = chip("Más reciente", "info") if i == 0 and p.get('ultimo_envio') else ""
                    ult = f" · último envío {esc(p['ultimo_envio_txt'])}" if p.get('ultimo_envio_txt') else ""
                    cen = ""
                    if p.get('centros'):
                        vistos = p['centros'][:3]
                        extra = f" y {len(p['centros']) - 3} más" if len(p['centros']) > 3 else ""
                        cen = f'<div class="sire-resp-c">Reportó: {esc(", ".join(vistos))}{esc(extra)}</div>'
                    mostrar(
                        f'<div class="sire-resp"><b>{esc(p["nombre"])} {esc(p["apellido"])}</b> {etiq_origen} {reciente}'
                        f'<div class="sire-resp-m">{esc(p["correo"])}{ult}</div>{cen}</div>')
            if marcado:
                elegidos.append(p)
        if any(p.get('centros') for p in elegidos) and len(elegidos) > 1:
            por_centro = st.toggle("Enviar a cada responsable solo los centros que atiende", value=False,
                                   key="notif_por_centro",
                                   help="Los centros que nadie atiende van al primer responsable marcado.")
        else:
            por_centro = False
        registrados = [p for p in responsables if p['origen'] == ORIGEN_REGISTRADO]
        if registrados:
            with st.expander("Quitar a un responsable guardado"):
                for p in registrados:
                    a, b = st.columns([3, 1], vertical_alignment="center")
                    a.markdown(f"{esc(p['nombre'])} {esc(p['apellido'])} · {esc(p['correo'])}")
                    if b.button("Quitar", key=f"notif_quitar_{p['correo']}", icon=":material/delete:",
                                use_container_width=True):
                        if resp_obj.quitar(red, p['correo']):
                            st.session_state.pop('notif_resp_cache', None)
                            st.toast("Responsable quitado de la lista.", icon=":material/check_circle:")
                            st.rerun()
    if red == "Todas" or not responsables:
        por_centro = False

    st.markdown("**Otra persona**" if responsables else "**Destinatario**")
    f1, f2 = st.columns(2)
    with f1:
        nombre = st.text_input("Nombre del responsable", key=k("nombre"))
    with f2:
        apellido = st.text_input("Apellido del responsable", key=k("apellido"))
    f3, f4 = st.columns([1.6, 1])
    with f3:
        correo = st.text_input("Correo electrónico", key=k("correo"))
    with f4:
        telefono = st.text_input("Teléfono (opcional)", placeholder="9XX XXX XXX", key=k("telefono"))
    guardar = False
    if red != "Todas":
        guardar = st.checkbox(f"Guardar como responsable de {red} para próximos envíos", value=True, key=k("guardar"))

    manual_escrito = any(x.strip() for x in (nombre, apellido, correo))
    destinos = [dict(p) for p in elegidos]
    error = None
    if manual_escrito:
        if not nombre.strip() or not apellido.strip() or not correo.strip():
            error = ("Faltan datos", "Complete nombre, apellido y correo de la otra persona, o borre lo escrito.")
        elif not formato_valido(correo):
            error = ("Correo electrónico inválido", "Revise que el correo esté bien escrito.")
        elif normalizar(correo) not in {d['correo'] for d in destinos}:
            destinos.append({'nombre': nombre.strip(), 'apellido': apellido.strip(), 'correo': normalizar(correo),
                             'centros': [], 'manual': True})

    # SIREA 3.3: con varias personas y todos los centros, se puede mandar UN solo correo con los demás en copia.
    en_copia = False
    if len(destinos) > 1 and not por_centro:
        en_copia = st.toggle("Un solo correo: el primero como destinatario y los demás en copia", value=False,
                             key="notif_en_copia",
                             help="Así todos ven que el aviso llegó al equipo de la red. Si lo deja apagado, "
                                  "cada persona recibe su propio correo.")

    reparto = _centros_por_destino(destinos, centros, por_centro) if destinos else []

    # resumen lateral
    with resumen_ph.container():
        filas = [("Semana", f"{semana} · {anio}"), ("Red", red), ("Centros marcados", str(len(centros))),
                 ("Destinatarios", str(len(destinos)))]
        celdas = "".join(f'<div class="sire-res-k">{esc(a)}</div><div class="sire-res-v">{esc(b)}</div>' for a, b in filas)
        quienes = "".join(f"<li>{esc(d['nombre'])} {esc(d['apellido'])} <span>{esc(d['correo'])}</span></li>" for d in destinos)
        mostrar(f'<div class="sire-card"><div class="sire-card-h">Resumen del envío</div><div class="sire-card-b">'
                f'<div class="sire-res">{celdas}</div>'
                + (f'<ul class="sire-res-l">{quienes}</ul>' if quienes else '')
                + '</div></div>')

    enviar = st.button("Enviar recordatorio", type="primary", icon=":material/mail:", key="notif_enviar")
    remitente = getattr(Config, 'EMAIL_REMITENTE', '') or 'la cuenta institucional'
    st.caption(f"Se enviará desde {remitente}.")
    if not enviar:
        return

    if error:
        mostrar(aviso("bad", *error))
        return
    if not destinos:
        mostrar(aviso("bad", "Falta el destinatario", "Marque a un responsable o escriba los datos de otra persona."))
        return
    if not busqueda or busqueda['clave'] != clave_busqueda:
        mostrar(aviso("warn", "Busque primero los centros pendientes",
                      "La lista de centros debe corresponder a la semana y red elegidas."))
        return
    if not centros:
        mostrar(aviso("warn", "No hay centros marcados",
                      "Marque al menos un centro pendiente para enviar el recordatorio."))
        return

    tipo = "ATRASADO" if estado_semana['tipo'] == 'atrasado' else "PREVENTIVO"
    actor_cta = actor_actual()                                  # sesión validada en el servidor
    actor = actor_cta.get('usuario') or 'admin'

    # v7.5: topes para que una sola cuenta no pueda inundar de correos a las redes.
    aud = get_auditoria()
    if len(reparto) > Config.NOTIF_MAX_DESTINATARIOS:
        mostrar(aviso("bad", "Demasiados destinatarios en un solo envío",
                      f"Este envío llegaría a {len(reparto)} personas; el máximo por envío es {Config.NOTIF_MAX_DESTINATARIOS}. "
                      "Envíelo por partes (por red)."))
        return
    ya_enviados = aud.correos_enviados_recientes(actor, 60)
    if ya_enviados + len(reparto) > Config.NOTIF_MAX_CORREOS_HORA:
        aud.registrar(actor, "NOTIFICACION_LIMITE", "NOTIFICACIONES", rol=actor_cta.get('rol'),
                      objeto=f"{red} · semana {semana}/{anio}", resultado="RECHAZADO",
                      detalle={"ya_enviados_ultima_hora": ya_enviados, "pedidos": len(reparto),
                               "tope": Config.NOTIF_MAX_CORREOS_HORA})
        mostrar(aviso("warn", "Alcanzó el tope de correos por hora",
                      f"En la última hora su cuenta envió {ya_enviados} correo(s) y el tope es {Config.NOTIF_MAX_CORREOS_HORA}. "
                      "Intente de nuevo más tarde."))
        return
    salida, enviados = [], 0
    nombre_red = red if red != "Todas" else "Todas las redes"
    if en_copia and reparto:
        tandas = [(reparto[0][0], reparto[0][1], [d['correo'] for d, _ in reparto[1:]])]
    else:
        tandas = [(d, cs, None) for d, cs in reparto]
    with st.spinner("Enviando recordatorio..."):
        for d, cs, cc in tandas:
            exito, mensaje = email_sender.enviar_recordatorio(
                destinatario=d['correo'], nombre_usuario=f"{d['nombre']} {d['apellido']}".strip(),
                red=nombre_red, semana=semana,
                fecha_limite=fecha_corte_str, centros_pendientes=cs, anio=anio,
                semana_actual=semana_activa, anio_actual=anio_activo, tipo=tipo, cc=cc or None)
            if exito:
                enviados += 1 + len(cc or [])
                copia = f" con copia a {esc(', '.join(cc))}" if cc else ""
                salida.append(("ok", "Recordatorio enviado", f"Se envió a {esc(d['correo'])}{copia} ({len(cs)} centros)."))
                # Formato único del log (lo lee el Agente de IA para no repetir recordatorios).
                db_manager.registrar_log(
                    usuario=actor, accion='ENVIO_RECORDATORIO',
                    detalle=detalle_log_recordatorio(d['correo'], nombre_red, semana, anio, tipo))
            else:
                salida.append(("bad", f"No se pudo enviar a {esc(d['correo'])}", esc(mensaje)))
    aud.registrar(actor, "NOTIFICACION_ENVIADA", "NOTIFICACIONES", rol=actor_cta.get('rol'),
                  objeto=f"{red} · semana {semana}/{anio}", resultado="OK" if enviados == len(reparto) else "ERROR",
                  detalle={"tipo": tipo, "n_destinatarios": len(reparto), "n_ok": enviados,
                           "n_error": len(reparto) - enviados, "correos": [d['correo'] for d, _ in reparto][:40],
                           "centros": sum(len(cs) for _, cs in reparto)})
    if guardar and enviados and manual_escrito and not error and red != "Todas":
        ok_g, msg_g = resp_obj.guardar(red, nombre, apellido, correo, telefono, actor)
        salida.append(("ok" if ok_g else "warn", "Responsable guardado" if ok_g else "No se guardó al responsable",
                       "Quedará propuesto en los próximos envíos de esta red." if ok_g else esc(msg_g)))
        st.session_state.pop('notif_resp_cache', None)
    st.session_state.notif_resultado = salida
    if enviados:
        st.session_state.notif_m_ver = ver_m + 1            # limpia el formulario manual
    st.rerun()


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
        st.session_state.notif_sel = {(r, c) for r, lista in pendientes.items() for c in lista}
        st.session_state.notif_ver = st.session_state.get('notif_ver', 0) + 1
        st.session_state.pop('notif_resultado', None)

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
                    centros_a_enviar = _tabla_centros(pendientes)

    # ============================================================
    # PASO 3: RESPONSABLES Y ENVIO
    # ============================================================
    with col_side:
        resumen_ph = st.empty()

    with col_main:
        with st.container(key="sec_notif_3"):
            seccion(3, "Responsables y envío")
            _paso_envio(
                db_manager, email_sender,
                red=red_seleccionada, anio=anio_seleccionado, semana=semana_seleccionada,
                semana_activa=semana_activa, anio_activo=anio_activo,
                estado_semana=estado_semana, fecha_corte_str=fecha_corte_str,
                busqueda=busqueda, clave_busqueda=clave_busqueda,
                centros=centros_a_enviar, resumen_ph=resumen_ph,
            )
