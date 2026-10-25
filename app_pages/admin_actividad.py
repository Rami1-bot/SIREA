# app_pages/admin_actividad.py
"""
«Control de actividad»: qué hizo cada administrador y SUPER_ADMIN (incluido oiis.winepi),
cuándo, desde dónde y con qué resultado. Lo ve oiis.winepi y quien tenga el permiso
«Ver auditoría». El registro es de solo escritura y está encadenado (ver src/auditoria.py).
"""

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from src.auditoria import CATEGORIAS, ETIQUETAS, FORMATO, LIMA, Auditoria, get_auditoria, resumen_por_usuario
from src.auditoria_excel import _fmt_iso, _txt_detalle, generar_excel_auditoria, nombre_excel_auditoria
from src.permisos import es_principal, get_permisos
from src.repositorio import get_repositorio
from utils.tema import aviso, chip, kpi, mostrar
from utils.tema_admin import esc, panel_cab, tabla_df
from app_pages.admin_helpers import actor_actual

_PERIODOS = ["Hoy", "Últimos 7 días", "Últimos 30 días", "Rango de fechas"]
_LIMITE = 3000


def puede_ver(usuario: dict) -> bool:
    """True para oiis.winepi y para quien tenga el permiso «Ver auditoría»."""
    try:
        return es_principal(usuario) or get_permisos().tiene(usuario, "VER_AUDITORIA")
    except Exception:
        return False


def _rango(periodo: str):
    hoy = datetime.now(LIMA).date()
    if periodo == "Hoy":
        d, h = hoy, hoy
    elif periodo == "Últimos 7 días":
        d, h = hoy - timedelta(days=6), hoy
    elif periodo == "Últimos 30 días":
        d, h = hoy - timedelta(days=29), hoy
    else:
        c1, c2, _ = st.columns([1, 1, 2])
        with c1:
            d = st.date_input("Desde", value=hoy - timedelta(days=30), max_value=hoy, key="act_desde")
        with c2:
            h = st.date_input("Hasta", value=hoy, max_value=hoy, key="act_hasta")
        if d > h:
            d, h = h, d
    return d, h


def _chip_resultado(r: str) -> str:
    return {"OK": chip("Correcto", "ok", "check"), "ERROR": chip("Con error", "bad"),
            "RECHAZADO": chip("Rechazado", "bad"), "PENDIENTE": chip("Pendiente", "warn", "reloj")}.get(r, chip(esc(r), "mute"))


def _chips_senales(f) -> str:
    al = Auditoria.detalle_de(f).get("alertas") or []
    return " ".join(chip(esc(a), "bad", "alerta") for a in al) or "—"


def mostrar_control_actividad():
    """Pantalla «Control de actividad»."""
    actor = actor_actual()
    if not puede_ver(actor):
        mostrar(aviso("warn", "Acceso restringido",
                      "Esta sección es para oiis.winepi y para quien tenga el permiso «Ver auditoría»."))
        return
    aud = get_auditoria()
    if not aud.disponible():
        mostrar(aviso("info", "Falta crear las tablas de auditoría y permisos",
                      "Ejecute <strong>sql/11_auditoria_permisos_repositorio.sql</strong> en el SQL Editor de Supabase."))
        return
    msg = st.session_state.pop("act_mensaje", None)
    if msg:
        mostrar(aviso(msg[0], msg[1], msg[2] if len(msg) > 2 else ""))

    with st.container(key="panel_act_filtros"):
        panel_cab("Filtros", "Elija el periodo y, si quiere, una persona o un tipo de acción")
        periodo = st.radio("Periodo", _PERIODOS, horizontal=True, key="act_periodo")
        d, h = _rango(periodo)
        desde, hasta = f"{d:%Y-%m-%d} 00:00:00", f"{h:%Y-%m-%d} 23:59:59"
        filas_periodo = aud.listar(desde=desde, hasta=hasta, limite=_LIMITE)
        personas = sorted({f.get("usuario", "") for f in filas_periodo})
        c1, c2, c3 = st.columns([1.2, 1.2, 1])
        with c1:
            persona = st.selectbox("Persona", ["Todas"] + personas, key="act_persona")
        with c2:
            cat = st.selectbox("Tipo de acción", ["Todas"] + list(CATEGORIAS), format_func=lambda c: CATEGORIAS.get(c, "Todas") if c != "Todas" else "Todas", key="act_cat")
        with c3:
            res = st.selectbox("Resultado", ["Todos", "OK", "ERROR", "RECHAZADO", "PENDIENTE"], key="act_res")
        c4, c5 = st.columns([1, 2])
        with c4:
            solo_alertas = st.checkbox("Solo con señales para revisar", key="act_alertas")
        with c5:
            buscar = st.text_input("Buscar", placeholder="Código, red, motivo, acción…", key="act_buscar")

    filas = filas_periodo
    if persona != "Todas":
        filas = [f for f in filas if f.get("usuario") == persona]
    if cat != "Todas":
        filas = [f for f in filas if f.get("categoria") == cat]
    if res != "Todos":
        filas = [f for f in filas if f.get("resultado") == res]
    if solo_alertas:
        filas = [f for f in filas if Auditoria.detalle_de(f).get("alertas")]
    if buscar.strip():
        q = buscar.strip().lower()
        filas = [f for f in filas if q in " ".join(str(v) for v in (f.get("usuario"), f.get("accion"), ETIQUETAS.get(f.get("accion"), ""),
                                                                      f.get("objeto"), f.get("detalle"))).lower()]
    if len(filas_periodo) >= _LIMITE:
        mostrar(aviso("warn", "Hay más acciones de las que se muestran", f"Se muestran las {_LIMITE} más recientes del periodo; acote el periodo para verlas todas."))

    n_alertas = sum(1 for f in filas if Auditoria.detalle_de(f).get("alertas"))
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        mostrar(kpi("Acciones", len(filas), f"{d:%d/%m} – {h:%d/%m/%Y}", None, "barras"))
    with k2:
        mostrar(kpi("Personas", len({f.get("usuario") for f in filas}), "Distintas en el periodo", None, "usuario"))
    with k3:
        mostrar(kpi("Descargas masivas", sum(1 for f in filas if f.get("accion") == "DESCARGA_MASIVA"), "ZIP descargados", None, "descarga"))
    with k4:
        mostrar(kpi("Retiros", sum(1 for f in filas if f.get("accion") == "RETIRO_EJECUTADO"), "Del repositorio", None, "basura"))
    with k5:
        mostrar(kpi("Para revisar", n_alertas, "Acciones con señales", "bad" if n_alertas else "ok", "alerta"))

    por_persona = resumen_por_usuario(filas)
    with st.container(key="panel_act_personas"):
        panel_cab("Qué hizo cada persona", "Primero quienes tienen señales para revisar")
        if por_persona:
            df = pd.DataFrame({
                "Persona": [p["usuario"] for p in por_persona], "Rol": [p.get("rol") or "—" for p in por_persona],
                "Acciones": [p["total"] for p in por_persona], "Descargas": [p["descargas"] for p in por_persona],
                "Retiros": [p["retiros"] for p in por_persona], "Duplicados": [p["duplicados"] for p in por_persona],
                "Señales": [(chip(str(p["alertas"]), "bad", "alerta") if p["alertas"] else chip("0", "ok")) for p in por_persona],
                "Última acción": [_fmt_iso(p.get("ultima")) for p in por_persona]})
            mostrar(tabla_df(df, crudas=("Señales",), derecha=("Acciones", "Descargas", "Retiros", "Duplicados")))
        else:
            mostrar('<div class="sire-vacio">No hay acciones con esos filtros.</div>')

    with st.container(key="panel_act_detalle"):
        panel_cab("Detalle de acciones", f"{len(filas)} registro(s); se muestran los {min(len(filas), 300)} más recientes")
        if filas:
            vista = filas[:300]
            df = pd.DataFrame({
                "Fecha y hora": [_fmt_iso(f.get("ocurrio_iso")) for f in vista], "Persona": [f.get("usuario") for f in vista],
                "Acción": [ETIQUETAS.get(f.get("accion"), f.get("accion")) for f in vista], "Objeto": [f.get("objeto") for f in vista],
                "Resultado": [_chip_resultado(f.get("resultado")) for f in vista], "Señales": [_chips_senales(f) for f in vista],
                "Detalle": [_txt_detalle(f)[:160] for f in vista], "IP": [f.get("ip") for f in vista]})
            mostrar(tabla_df(df, crudas=("Resultado", "Señales"), alto=520))
        else:
            mostrar('<div class="sire-vacio">No hay acciones con esos filtros.</div>')

    c1, c2 = st.columns(2)
    with c1:
        with st.container(key="panel_act_integridad"):
            panel_cab("Integridad del registro", "Comprueba que nada fue alterado ni quitado")
            if st.button("Verificar ahora", icon=":material/verified_user:", key="act_verificar"):
                with st.spinner("Verificando la cadena…"):
                    v = aud.verificar_cadena()
                aud.registrar(actor.get("usuario", ""), "AUDITORIA_VERIFICADA", "SISTEMA", rol=actor.get("rol"),
                              objeto=f"{v['filas']} registros", resultado="OK" if v["ok"] else "ERROR",
                              detalle={"filas": v["filas"], "id_roto": v["id_roto"], "motivo": v["motivo"]})
                st.session_state["act_integridad"] = v
            v = st.session_state.get("act_integridad")
            if v:
                if v["ok"]:
                    mostrar(aviso("ok", "Registro íntegro", f"{v['filas']} registros verificados: ninguno fue alterado ni falta."))
                else:
                    mostrar(aviso("bad", "Se detectó una alteración", f"{esc(v['motivo'])} Registro N.º {v['id_roto']}. Avise a TI de inmediato."))
    with c2:
        with st.container(key="panel_act_excel"):
            panel_cab("Excel de auditoría", "Resumen, por persona, detalle, descargas y retiros")
            if st.button("Generar el Excel", icon=":material/table:", key="act_excel_btn"):
                with st.spinner("Generando el Excel…"):
                    rep = get_repositorio()
                    cadena = aud.verificar_cadena()
                    xb = generar_excel_auditoria(
                        filas, {"Periodo": f"{d:%d/%m/%Y} al {h:%d/%m/%Y}", "Persona": persona if persona != "Todas" else "",
                                "Tipo de acción": CATEGORIAS.get(cat, "") if cat != "Todas" else "", "Resultado": res if res != "Todos" else "",
                                "Solo con señales": "Sí" if solo_alertas else "", "Búsqueda": buscar},
                        por_persona, rep.listar_descargas(500), rep.listar_solicitudes(None, None, 500), cadena, actor.get("usuario", ""))
                aud.registrar(actor.get("usuario", ""), "AUDITORIA_EXPORTADA", "SISTEMA", rol=actor.get("rol"),
                              objeto=f"{len(filas)} acciones", detalle={"desde": desde, "hasta": hasta, "persona": persona, "filas": len(filas)})
                st.session_state["act_excel"] = (nombre_excel_auditoria(), xb)
            ex = st.session_state.get("act_excel")
            if ex:
                st.download_button("Descargar el Excel", data=ex[1], file_name=ex[0], icon=":material/download:", key="act_excel_dl",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
