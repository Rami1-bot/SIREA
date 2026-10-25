# app_pages/admin_cierres.py
"""
Pantallas del cierre de corte:

  · panel_validacion_semana()  -> en «Configuración»: validar o corregir la semana
                                  y el corte que el sistema propuso al cerrar.
  · mostrar_informe_semana()   -> «Informe por semana»: resumen de cumplimiento por
                                  red, validación, envío a la entidad externa y envío manual.
  · mostrar_respaldos()        -> «Respaldos»: historial y respaldo manual.
  · avisos_cierre()            -> avisos para el panel de control de todas las secciones.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from src.auth import get_auth_manager
from src.calendario_epi import parsear_corte
from src.cierres import FORMATO, ahora_lima, get_cierres
from src.config import Config
from src.db_manager import get_db_manager
from src.respaldos import get_respaldos
from src.solicitudes_password import fecha_lima
from utils.corte_ui import campos_corte, texto_corte
from utils.tema import aviso, chip, kpi, mostrar
from utils.tema_admin import esc, panel_cab, tabla_df
from app_pages.admin_helpers import actor_actual, requerir_admin

_ESTADO_CIERRE = {
    "PROVISIONAL": ("Por validar", "warn", "reloj"),
    "VALIDADA": ("Validada", "ok", "check"),
    "SUPERADA": ("Superada", "mute", None),
}
_ESTADO_RESUMEN = {
    "PENDIENTE": ("Por validar", "warn", "reloj"),
    "VALIDADO": ("Validado", "info", "check"),
    "ENVIADO": ("Enviado", "ok", "check"),
}
_ESTADO_RESPALDO = {
    "EN_CURSO": ("En curso", "info", "reloj"),
    "COMPLETADO": ("Completado", "ok", "check"),
    "ERROR": ("Con error", "bad", None),
}


def _chip(tabla, clave):
    texto, tono, ico = tabla.get(clave, (clave, "mute", None))
    return chip(esc(texto), tono, ico) if ico else chip(esc(texto), tono)


def _identidad():
    u = st.session_state.get("admin_usuario") or {}
    return u.get("usuario", "SYSTEM"), u.get("nombre") or u.get("usuario", "Administrador")


def _es_super_admin() -> bool:
    return (st.session_state.get("admin_usuario") or {}).get("rol") == "SUPER_ADMIN"


def _fmt_corte(texto) -> str:
    dt = parsear_corte(texto)
    return f"{dt:%d/%m/%Y %H:%M:%S}" if dt else "—"


# ------------------------------------------------------------------ avisos

def avisos_cierre() -> dict:
    """Estado resumido para banners: {'pendiente': cierre|None, 'validada_reciente': cierre|None}."""
    try:
        cierres = get_cierres()
        if not cierres.disponible():
            return {"pendiente": None, "validada_reciente": None, "vencido": None}
        pendiente = cierres.pendiente()
        vencido = cierres.vencido_sin_cerrar()
        reciente = None
        ult = cierres.ultimo()
        if ult and ult.get("estado") == "VALIDADA" and ult.get("fecha_validacion"):
            from src.solicitudes_password import parsear_fecha
            f = parsear_fecha(ult["fecha_validacion"])
            if f and datetime.now(timezone.utc) - f < timedelta(hours=24):
                reciente = ult
        return {"pendiente": pendiente, "validada_reciente": reciente, "vencido": vencido}
    except Exception:
        return {"pendiente": None, "validada_reciente": None, "vencido": None}


# ------------------------------------------------------------------ validar semana (Configuración)

def _invalidar_avisos():
    st.session_state.pop("_menu_avisos", None)


def avisos_menu() -> dict:
    """
    Marcas discretas del menú: {'configuracion': 0/1, 'respaldos': 0/1}. Se recalcula cada 20 s
    para no consultar la base en cada clic. Configuración: hay una semana por validar o un corte vencido sin cerrar.
    Respaldos: el proceso programado dejó de responder.
    """
    import time
    previo = st.session_state.get("_menu_avisos")
    if previo and time.time() - previo[0] < 20:
        return previo[1]
    est = avisos_cierre()
    caido = _estado_latido()[0] in ("bad", "warn") and get_cierres().disponible()
    datos = {"configuracion": 1 if (est["pendiente"] or est["vencido"]) else 0, "respaldos": 1 if caido else 0}
    st.session_state["_menu_avisos"] = (time.time(), datos)
    return datos


def panel_cierre_vencido():
    """
    En «Configuración»: el corte venció y no se cerró (proceso programado caído o apagado). Permite hacer a mano
    lo mismo que haría el proceso: cerrar la semana, proponer la siguiente, avisar y evaluar el respaldo.
    """
    cierres = get_cierres()
    v = cierres.vencido_sin_cerrar()
    if not v:
        return
    usuario, nombre = _identidad()
    with st.container(key="panel_cierre_vencido"):
        panel_cab("El corte venció y no se cerró solo", f"Semana {v['semana']} · corte {v['corte']:%d/%m/%Y %H:%M:%S}")
        extra = ""
        if v["fuera_ventana"]:
            extra = (" Pasaron más de 72 horas desde el corte, por eso el sistema no lo hace solo: al hacerlo ahora "
                     "propondrá la semana siguiente y un corte futuro que usted debe revisar.")
        mostrar(aviso(
            "warn", "Probablemente el proceso programado está apagado",
            f"Hace {v['horas']} h que venció el corte y la semana sigue siendo la {v['semana']}. "
            "Puede cerrarlo ahora: el sistema propondrá la semana siguiente y el siguiente corte como "
            "<strong>provisionales</strong>, y usted los valida o corrige justo debajo." + esc(extra)))
        conf = st.checkbox("Confirmo que deseo cerrar este corte ahora", key="cierre_manual_ok")
        if st.button("Cerrar el corte ahora", type="primary", icon=":material/event_available:", key="cierre_manual_btn"):
            if not conf:
                st.info("Marque la casilla de confirmación para continuar.")
            else:
                from src.auditoria import get_auditoria
                actor = actor_actual()
                with st.spinner("Cerrando el corte..."):
                    acc = cierres.procesar(ignorar_ventana=True)
                    try:
                        resp = get_respaldos().procesar()
                    except Exception as e:
                        resp = {"error": str(e)}
                get_auditoria().registrar(usuario, "CIERRE_MANUAL", "CONFIGURACION", rol=actor.get("rol"),
                                          objeto=f"semana {v['semana']}", resultado="OK" if acc.get("cierre") else "ERROR",
                                          detalle={"corte": f"{v['corte']:%Y-%m-%d %H:%M:%S}", "cierre": acc.get("cierre"),
                                                   "respaldos": resp, "avisos": acc.get("avisos")})
                _invalidar_avisos()
                if acc.get("cierre"):
                    st.toast("Corte cerrado. Revise y valide la semana propuesta.", icon=":material/check_circle:")
                    st.rerun()
                else:
                    mostrar(aviso("bad", "No se pudo cerrar el corte", esc("; ".join(acc.get("avisos") or []) or "Revise el registro de actividad.")))


def panel_validacion_semana():
    """Validar o corregir lo que el sistema dejó al cerrar el corte."""
    cierres = get_cierres()
    if not cierres.disponible():
        mostrar(aviso("info", "Falta crear las tablas del proceso programado",
                      "Ejecute el script <strong>sql/10_programador_cierres_respaldos.sql</strong> en el SQL Editor de "
                      "Supabase. Mientras tanto, la semana y el corte se cambian a mano aquí abajo."))
        return
    c = cierres.ultimo()
    if not c:
        return
    usuario, nombre = _identidad()

    if c["estado"] == "VALIDADA":
        por = c.get("validado_por_nombre") or c.get("validado_por") or "—"
        extra = (f" Corrigió la propuesta del sistema (semana {c.get('semana_propuesta')}, corte "
                 f"{_fmt_corte(c.get('corte_propuesto'))})." if c.get("hubo_correccion") else " Coincidía con la propuesta del sistema.")
        with st.container(key="panel_cierre_validado"):
            mostrar(aviso("ok", f"Semana {c.get('semana_validada')} validada por {esc(por)}",
                          f"{esc(fecha_lima(c.get('fecha_validacion')))} · corte {esc(_fmt_corte(c.get('corte_validado')))}.{esc(extra)}"))
        return
    if c["estado"] != "PROVISIONAL":
        return

    with st.container(key="panel_cierre_pendiente"):
        panel_cab("Validar la semana propuesta por el sistema",
                  f"Se cerró el corte del {_fmt_corte(c['corte_cerrado'])} (semana {c['semana_cerrada']})")
        if c.get("aplicado"):
            mostrar(aviso("warn", "El sistema ya cambió la configuración, pero falta su validación",
                          f"Quedó <strong>semana {c['semana_propuesta']}</strong> con corte el "
                          f"<strong>{esc(_fmt_corte(c['corte_propuesto']))}</strong>. Los feriados mueven el corte: "
                          "confirme o corrija estos datos."))
        else:
            mostrar(aviso("warn", "El sistema no pudo cambiar la configuración",
                          "Defina la semana y el corte aquí abajo y valídelos."))
        if c.get("nota"):
            mostrar(aviso("info", "Revise esto", esc(c["nota"]).replace("\n", "<br>")))
        st.caption(f"Recordatorios enviados: {c.get('recordatorios_enviados', 0)} de {len(Config.RECORDATORIOS_CIERRE_HORAS)}.")

        info = get_db_manager().obtener_anio_activo_epidemiologico() or {}
        maximo = int(info.get("semanas") or 53)
        semana_base = int(c.get("semana_propuesta") or Config.get_semana_actual())
        corte_base = parsear_corte(c.get("corte_propuesto")) or ahora_lima()
        k = f"val_{c['id']}"
        c1, c2 = st.columns([1, 2])
        with c1:
            semana = st.number_input("Semana activa", min_value=1, max_value=maximo, value=min(max(1, semana_base), maximo),
                                     step=1, key=f"{k}_s")
        with c2:
            corte = campos_corte(k, corte_base)
        if st.button("Validar semana y corte", type="primary", icon=":material/verified:", key=f"{k}_btn"):
            ok, msg = cierres.validar(c["id"], usuario, nombre, int(semana), corte)
            if ok:
                _invalidar_avisos()
                st.toast(msg, icon=":material/check_circle:")
                st.rerun()
            else:
                mostrar(aviso("bad", "No se pudo validar", esc(msg)))


def banners_panel(ir_a_configuracion):
    """Banners del panel (todas las secciones salvo Configuración)."""
    est = avisos_cierre()
    if est.get("vencido") and not est["pendiente"]:
        v = est["vencido"]
        col_av, col_bt = st.columns([5, 1.3], vertical_alignment="center")
        with col_av:
            mostrar(aviso("warn", f"El corte de la semana {v['semana']} venció y no se cerró",
                          "El proceso automático no lo hizo. Puede cerrarlo a mano desde Configuración y luego validar la nueva semana."))
        with col_bt:
            st.button("Cerrar ahora", key="btn_ir_cierre_manual", type="primary", use_container_width=True,
                      icon=":material/arrow_forward:", on_click=ir_a_configuracion)
    elif est["pendiente"]:
        p = est["pendiente"]
        col_av, col_bt = st.columns([5, 1.3], vertical_alignment="center")
        with col_av:
            mostrar(aviso("warn", f"Semana {p.get('semana_propuesta')} propuesta: falta validarla",
                          f"El sistema cerró la semana {p['semana_cerrada']} y dejó la nueva semana de forma provisional. "
                          "Confirme o corrija la semana y la fecha de corte."))
        with col_bt:
            st.button("Revisar ahora", key="btn_ir_validar_semana", type="primary", use_container_width=True,
                      icon=":material/arrow_forward:", on_click=ir_a_configuracion)
    elif est["validada_reciente"]:
        v = est["validada_reciente"]
        mostrar(aviso("ok", f"Semana {v.get('semana_validada')} ya validada por "
                            f"{esc(v.get('validado_por_nombre') or v.get('validado_por') or '—')}",
                      esc(fecha_lima(v.get("fecha_validacion")))))


# ------------------------------------------------------------------ informe por semana

@st.cache_data(ttl=60, show_spinner=False)
def _datos_resumen(anio: int, semana: int, corte_txt: str):
    from src.resumen_excel import recolectar
    cierres = get_cierres()
    redes = __import__("src.data_loader", fromlist=["x"]).get_data_loader().obtener_redes()
    return recolectar(cierres.db, anio, semana, redes, parsear_corte(corte_txt) if corte_txt else None)


def _tabla_resumen(datos):
    filas = datos["filas"]
    if not filas:
        mostrar('<div class="sire-vacio">No hay redes con centros esperados para esta semana.</div>')
        return
    vista = pd.DataFrame({
        "Red": [f["red"] for f in filas],
        "Centros": [f"{f['enviados']} de {f['esperados']}" for f in filas],
        "Avance": [f"{f['pct']:.1f} %" for f in filas],
        "Estado": [f["estado"] for f in filas],
        "Responsables": [f["responsables"] for f in filas],
        "Completó / último envío": [(f["cierre"].strftime("%d/%m/%Y %H:%M:%S") if f["cierre"] else "—") for f in filas],
    })
    mostrar(tabla_df(vista, derecha=("Avance",)))


def _tabla_tardios(datos):
    t = datos["tardios"]
    if not t:
        mostrar('<div class="sire-vacio">No se registraron envíos tardíos de semanas anteriores en esta semana.</div>')
        return
    vista = pd.DataFrame({
        "Fecha y hora": [(x["fecha"].strftime("%d/%m/%Y %H:%M:%S") if x["fecha"] else "—") for x in t],
        "Red": [x["red"] for x in t],
        "Centros": [x["centros"] for x in t],
        "Semana que corresponde": [x["semana_reporte"] for x in t],
        "Responsable": [x["responsable"] for x in t],
        "Días de atraso": [x["dias_atraso"] for x in t],
    })
    mostrar(tabla_df(vista, derecha=("Semana que corresponde", "Días de atraso")))


def _bloque_validacion(cierres, c, usuario, nombre):
    est = c.get("resumen_estado", "PENDIENTE")
    externos = cierres.listar_externos(solo_activos=True)
    with st.container(key="panel_resumen_validacion"):
        panel_cab("Validación y envío a la entidad externa",
                  "El resumen solo se envía a la entidad externa después de que una persona de la OIIS lo valida")
        mostrar(f'<div class="sire-dato"><small>Estado del resumen</small>{_chip(_ESTADO_RESUMEN, est)}</div>')
        if est == "ENVIADO":
            mostrar(aviso("ok", "Enviado a la entidad externa",
                          f"Validado por {esc(c.get('resumen_validado_por_nombre') or c.get('resumen_validado_por') or '—')} · "
                          f"{esc(fecha_lima(c.get('resumen_enviado_externo_at')))}."))
            return
        if est == "VALIDADO":
            mostrar(aviso("warn", "Validado, pero no llegó a enviarse",
                          f"Validado por {esc(c.get('resumen_validado_por_nombre') or '—')}. "
                          + ("Use «Reintentar el envío»." if externos else "Un SUPER_ADMIN debe registrar destinatarios externos.")))
            if externos and st.button("Reintentar el envío", icon=":material/send:", key=f"res_reint_{c['id']}"):
                ok, msg = cierres.reintentar_envio_externo(c["id"], usuario, nombre)
                if ok:
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.error(msg)
            return
        # PENDIENTE
        st.caption(f"Destinatarios externos activos: {len(externos)}."
                   + ("" if externos else " Hasta que se registren, solo se validará el resumen."))
        st.caption("Si llegaron envíos tardíos después del corte, espere a que terminen antes de validar.")
        ok_chk = st.checkbox("Revisé el resumen y autorizo su envío a la entidad externa", key=f"res_ok_{c['id']}")
        if st.button("Validar y enviar", type="primary", icon=":material/verified:", key=f"res_val_{c['id']}"):
            if not ok_chk:
                st.info("Marque la casilla de confirmación para continuar.")
            else:
                ok, msg = cierres.validar_resumen(c["id"], usuario, nombre)
                if ok:
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    mostrar(aviso("bad", "No se pudo validar", esc(msg)))


def _bloque_envio_manual(cierres, anio, semana, usuario, nombre):
    with st.container(key="panel_resumen_manual"):
        panel_cab("Enviar el resumen por correo",
                  f"Envía el Excel de la semana {semana} ({anio}) a la persona que indique")
        with st.form("form_resumen_manual", border=False, clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                nombres = st.text_input("Nombres")
            with c2:
                apellidos = st.text_input("Apellidos")
            correo = st.text_input("Correo electrónico")
            mensaje = st.text_area("Mensaje", height=110, max_chars=2000,
                                   placeholder="Texto que acompañará al archivo (opcional).")
            enviar = st.form_submit_button("Enviar resumen", type="primary", icon=":material/send:")
        if enviar:
            ok, msg = cierres.enviar_resumen_manual(usuario, nombre, anio, semana, nombres, apellidos, correo, mensaje)
            if ok:
                st.toast(msg, icon=":material/check_circle:")
            else:
                mostrar(aviso("bad", "No se envió", esc(msg)))


def _bloque_externos(cierres, usuario):
    with st.container(key="panel_externos"):
        panel_cab("Entidad externa que califica a las redes", "Correos que reciben el resumen validado (solo SUPER_ADMIN)")
        lista = cierres.listar_externos()
        if lista:
            vista = pd.DataFrame({
                "Nombre": [f"{e.get('nombre', '')} {e.get('apellidos', '')}".strip() for e in lista],
                "Correo": [e.get("correo") for e in lista],
                "Estado": [chip("Activo", "ok", "check") if e.get("activo") else chip("Inactivo", "mute") for e in lista],
            })
            mostrar(tabla_df(vista, crudas=("Estado",)))
            etiquetas = {f"{e.get('nombre', '')} {e.get('apellidos', '')} · {e.get('correo')}": e for e in lista}
            elegido = etiquetas[st.selectbox("Destinatario", list(etiquetas), key="ext_sel")]
            c1, c2, _ = st.columns([1, 1, 2])
            with c1:
                etiqueta = "Desactivar" if elegido.get("activo") else "Activar"
                if st.button(etiqueta, key="ext_toggle", use_container_width=True):
                    cierres.cambiar_estado_externo(elegido["id"], not elegido.get("activo"), usuario)
                    st.rerun()
            with c2:
                if st.button("Eliminar", key="ext_del", use_container_width=True, icon=":material/delete:"):
                    cierres.eliminar_externo(elegido["id"], usuario)
                    st.rerun()
        else:
            mostrar('<div class="sire-vacio">Aún no hay destinatarios externos registrados.</div>')
        with st.form("form_externo", border=False, clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                n = st.text_input("Nombres")
            with c2:
                a = st.text_input("Apellidos")
            with c3:
                m = st.text_input("Correo")
            if st.form_submit_button("Agregar destinatario", type="primary", icon=":material/person_add:"):
                ok, msg = cierres.agregar_externo(n, a, m, usuario)
                if ok:
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.error(msg)


def _bloque_historial(cierres):
    lista = cierres.listar(12)
    if not lista:
        return
    with st.container(key="panel_cierres_hist"):
        panel_cab("Cierres de corte recientes", "Qué propuso el sistema y quién lo validó")
        vista = pd.DataFrame({
            "Corte cerrado": [_fmt_corte(c["corte_cerrado"]) for c in lista],
            "Semana cerrada": [c["semana_cerrada"] for c in lista],
            "Propuesta": [f"Semana {c.get('semana_propuesta')} · {_fmt_corte(c.get('corte_propuesto'))}" for c in lista],
            "Estado": [_chip(_ESTADO_CIERRE, c["estado"]) for c in lista],
            "Validada por": [c.get("validado_por_nombre") or "—" for c in lista],
            "Resumen": [_chip(_ESTADO_RESUMEN, c.get("resumen_estado", "PENDIENTE")) for c in lista],
        })
        mostrar(tabla_df(vista, crudas=("Estado", "Resumen"), derecha=("Semana cerrada",)))


def mostrar_informe_semana():
    """Pantalla «Informe por semana»."""
    requerir_admin()
    cierres = get_cierres()
    db = get_db_manager()
    usuario, nombre = _identidad()

    ult = cierres.ultimo()
    anios = sorted({a["anio"] for a in (db.obtener_anios_epidemiologicos() or []) if a.get("anio")}, reverse=True)
    anio_actual = Config.get_anio_actual()
    semana_base = int(ult["semana_cerrada"]) if ult else max(1, Config.get_semana_actual() - 1)
    anio_base = int(ult["anio"]) if ult else anio_actual

    with st.container(key="panel_informe_sel"):
        panel_cab("Semana del informe", "Por defecto, la última semana cerrada; puede elegir cualquier otra")
        c1, c2, _ = st.columns([1, 1, 2])
        opciones = anios or [anio_actual]
        with c1:
            anio = st.selectbox("Año", opciones, index=opciones.index(anio_base) if anio_base in opciones else 0,
                                key="inf_anio")
        with c2:
            semana = st.number_input("Semana", min_value=1, max_value=53, step=1, value=min(max(1, semana_base), 53),
                                     key=f"inf_semana_{anio}")
    cierre = next((c for c in cierres.listar(60) if c["anio"] == anio and c["semana_cerrada"] == int(semana)), None)
    corte_txt = cierre["corte_cerrado"] if cierre else ""

    try:
        datos = _datos_resumen(int(anio), int(semana), corte_txt)
    except Exception as e:
        mostrar(aviso("bad", "No se pudo calcular el resumen", esc(str(e))))
        return

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        mostrar(kpi("Semana", f"{datos['semana']} · {datos['anio']}", esc(datos["periodo"]), None, "calendario"))
    with k2:
        mostrar(kpi("Avance nacional", f"{datos['pct_total']:.1f} %", f"{datos['total_enviados']} de {datos['total_esperados']} centros",
                    "ok" if datos["pct_total"] >= 100 else None, "check"))
    with k3:
        mostrar(kpi("Redes", len(datos["filas"]), "Con centros esperados", None, "dash"))
    with k4:
        mostrar(kpi("Envíos tardíos", len(datos["tardios"]), "De semanas anteriores, registrados esta semana",
                    "warn" if datos["tardios"] else None, "alerta"))

    with st.container(key="panel_informe_t1"):
        panel_cab("Resumen de cumplimiento por red", "Quiénes enviaron y cuándo completó cada red")
        _tabla_resumen(datos)
    with st.container(key="panel_informe_t2"):
        panel_cab("Envíos tardíos de semanas anteriores", "Recibidos durante esta semana")
        _tabla_tardios(datos)

    try:
        from src.resumen_excel import generar_excel, nombre_archivo
        st.download_button("Descargar el Excel", data=generar_excel(datos), file_name=nombre_archivo(int(anio), int(semana)),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           icon=":material/download:", key="inf_descarga")
    except Exception as e:
        st.error(f"No se pudo generar el Excel: {e}")

    if cierre:
        _bloque_validacion(cierres, cierre, usuario, nombre)
    elif cierres.disponible():
        st.caption("Esta semana no tiene un cierre automático registrado: el envío a la entidad externa solo se habilita "
                   "para semanas cerradas por el sistema. Puede enviar el Excel manualmente aquí abajo.")
    else:
        mostrar(aviso("info", "Falta crear las tablas del proceso programado",
                      "Ejecute <strong>sql/10_programador_cierres_respaldos.sql</strong> para habilitar la validación y el envío "
                      "a la entidad externa."))
    _bloque_envio_manual(cierres, int(anio), int(semana), usuario, nombre)
    if _es_super_admin() and cierres.disponible():
        _bloque_externos(cierres, usuario)
    _bloque_historial(cierres)


# ------------------------------------------------------------------ respaldos

def _estado_latido():
    """(tono, titulo, texto) del proceso programado, según su último latido."""
    try:
        v = get_db_manager().obtener_configuracion("programador_ultimo_latido")
    except Exception:
        v = None
    if not v:
        return "warn", "El proceso programado no ha dado señales", (
            "Inicie el proceso programado (contenedor «programador» con Docker, o la tarea de GitHub Actions en "
            "Streamlit Cloud). Sin él no se cierran los cortes solos ni se hacen los respaldos automáticos.")
    from src.solicitudes_password import parsear_fecha
    f = parsear_fecha(v)
    if not f:
        return "warn", "No se pudo leer el último latido", ""
    hace = datetime.now(timezone.utc) - f
    import os as _os
    limite = int(_os.getenv("PROGRAMADOR_LATIDO_MAX_MIN", "5") or "5")
    if hace > timedelta(minutes=limite):
        return "bad", "El proceso programado dejó de responder", (
            f"Último latido: {fecha_lima(v)} (hace {int(hace.total_seconds() // 60)} min). Mientras no vuelva a funcionar, "
            "el corte se cierra a mano desde Configuración y el respaldo se hace con «Respaldar ahora», más abajo. "
            "Para reactivarlo: docker compose up -d (o la tarea de GitHub Actions en Streamlit Cloud).")
    return "ok", "Proceso programado activo", f"Último latido: {fecha_lima(v)}."


def mostrar_respaldos():
    """Pantalla «Respaldos»."""
    requerir_admin()
    resp = get_respaldos()
    usuario, nombre = _identidad()
    tono, tit, txt = _estado_latido()
    mostrar(aviso(tono, tit, esc(txt)))

    if not resp.disponible():
        mostrar(aviso("info", "Falta crear las tablas del proceso programado",
                      "Ejecute <strong>sql/10_programador_cierres_respaldos.sql</strong> en el SQL Editor de Supabase."))
        return
    listo, motivo = resp.destino_configurado()
    lista = resp.listar(30)
    completos = [r for r in lista if r.get("estado") == "COMPLETADO"]
    cierres = get_cierres().listar(200)
    n = Config.RESPALDO_CADA_N_CORTES
    faltan = n - (len(cierres) % n) if (len(cierres) % n) else n

    k1, k2, k3 = st.columns(3)
    with k1:
        ultimo_txt = "—"
        if completos:
            m = completos[0]["nombre"].replace("RESPALDO_", "").split("_intento")[0]
            try:
                ultimo_txt = datetime.strptime(m, "%Y-%m-%d_%H-%M-%S").strftime("%d/%m/%Y")
            except ValueError:
                ultimo_txt = m
        mostrar(kpi("Último respaldo", esc(ultimo_txt),
                    ("Hecho el " + fecha_lima(completos[0].get("fecha_fin"))) if completos else "Aún no hay respaldos", None, "nube"))
    with k2:
        mostrar(kpi("Próximo respaldo", f"En {faltan} corte(s)" if faltan > 1 else "Al cerrar el próximo corte",
                    f"Se respalda cada {n} cortes, a las 23:59:59 del corte", None, "reloj"))
    with k3:
        mostrar(kpi("Destino", "Drive" if (listo and not resp._es_local()) else ("Local" if listo else "Sin configurar"),
                    esc(motivo), "ok" if listo else "warn", "escudo"))

    with st.container(key="panel_respaldos_lista"):
        panel_cab("Historial de respaldos", "Cada respaldo es una carpeta con su fecha y hora exactas dentro de BACKUPS")
        if lista:
            vista = pd.DataFrame({
                "Respaldo": [r["nombre"] for r in lista],
                "Estado": [_chip(_ESTADO_RESPALDO, r["estado"]) for r in lista],
                "Origen": ["Automático" if r.get("origen") == "AUTOMATICO" else "Manual" for r in lista],
                "Registros": [r.get("total_filas", 0) for r in lista],
                "Fecha": [fecha_lima(r.get("fecha_fin") or r.get("fecha_creacion")) for r in lista],
                "Detalle": [(r.get("detalle") or "—")[:120] for r in lista],
            })
            mostrar(tabla_df(vista, crudas=("Estado",), derecha=("Registros",)))
        else:
            mostrar('<div class="sire-vacio">Todavía no hay respaldos.</div>')

    with st.container(key="panel_respaldo_manual"):
        panel_cab("Respaldar ahora", "Copia de envíos, configuración, exclusiones y años; sin contraseñas")
        if not listo:
            mostrar(aviso("warn", "No hay dónde guardar el respaldo", esc(motivo)))
            return
        from src.auditoria import get_auditoria
        from src.permisos import get_permisos
        actor = actor_actual()
        if not get_permisos().tiene(actor, "RESPALDO_MANUAL"):
            mostrar(aviso("warn", "No tiene el permiso de respaldo manual",
                          "Pídale a oiis.winepi que se lo asigne en «Permisos de operación». Los respaldos automáticos siguen su curso."))
            return
        conf = st.checkbox("Confirmo que deseo hacer un respaldo ahora", key="resp_ok")
        if st.button("Respaldar ahora", type="primary", icon=":material/backup:", key="resp_btn"):
            if not conf:
                st.info("Marque la casilla de confirmación para continuar.")
            else:
                with st.spinner("Respaldando..."):
                    info = resp.ejecutar(ahora_lima(), "MANUAL", usuario)
                get_auditoria().registrar(usuario, "RESPALDO_MANUAL", "RESPALDOS", rol=actor.get("rol"), objeto=info.get("nombre"),
                                          resultado="OK" if info["ok"] else "ERROR",
                                          detalle={"destino": info.get("destino"), "registros": info.get("total_filas"),
                                                   "motivo": info.get("motivo")})
                if info["ok"]:
                    st.toast(f"Respaldo {info['nombre']} completado.", icon=":material/check_circle:")
                    st.rerun()
                else:
                    mostrar(aviso("bad", "No se pudo completar el respaldo", esc(info.get("motivo") or "")))
