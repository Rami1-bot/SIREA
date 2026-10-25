# app_pages/admin_repositorio.py
"""
«Descarga y limpieza»: descarga masiva de los ZIP de una semana y retiro de
archivos del repositorio (Drive), con permisos, aprobación y trazabilidad.

  Pestañas:  Descargar · Retirar del repositorio · Solicitudes · Historial

Lo que cada persona puede hacer depende de los permisos que le asignó
oiis.winepi (ver «Permisos de operación»). El principal puede todo.
"""

from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

from src.auditoria import ETIQUETAS
from src.config import Config
from src.db_manager import get_db_manager
from src.permisos import PERMISOS, es_principal
from src.repositorio import MOTIVOS_RETIRO, MOTIVO_DESCARGADO, get_repositorio, tiene_archivo
from src.solicitudes_password import fecha_lima
from utils.duplicados import es_duplicado
from utils.tema import aviso, chip, kpi, mostrar
from utils.tema_admin import esc, panel_cab, tabla_df
from app_pages.admin_helpers import actor_actual

_ESTADO_SOL = {
    "PENDIENTE": ("Por aprobar", "warn", "reloj"),
    "EJECUTADA": ("Retirada", "ok", "check"),
    "PARCIAL": ("Parcial", "warn", "alerta"),
    "ERROR": ("Con error", "bad", None),
    "RECHAZADA": ("Rechazada", "bad", None),
    "CANCELADA": ("Cancelada", "mute", None),
}


def pendientes_retiro() -> int:
    """Solicitudes de retiro por aprobar (0 si la migración 11 no está)."""
    try:
        return get_repositorio().pendientes()
    except Exception:
        return 0


def _chip_estado(estado: str) -> str:
    texto, tono, ico = _ESTADO_SOL.get(estado, (estado, "mute", None))
    return chip(esc(texto), tono, ico) if ico else chip(esc(texto), tono)


def _mb(n) -> str:
    n = float(n or 0)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.1f} MB" if n >= 1024 ** 2 else f"{n / 1024:.0f} KB"


def _mensaje_pendiente():
    r = st.session_state.pop("rep_mensaje", None)
    if r:
        mostrar(aviso(r[0], r[1], r[2] if len(r) > 2 else ""))


def _redes_catalogo():
    try:
        from src.data_loader import obtener_redes
        return list(obtener_redes())
    except Exception:
        return []


# ------------------------------------------------------------------ selección común

def _selector(rep, actor, redes_catalogo):
    """Año, semana y redes (con «Todas»). Devuelve (anio, semana, redes|None, incluir_duplicados, permitidas)."""
    db = get_db_manager()
    anios = sorted({a["anio"] for a in (db.obtener_anios_epidemiologicos() or []) if a.get("anio")}, reverse=True)
    anio_actual = Config.get_anio_actual()
    semana_base = max(1, Config.get_semana_actual() - 1)
    con_descarga = rep.redes_con_permiso(actor, "DESCARGA_MASIVA", redes_catalogo)
    con_retiro = rep.redes_con_permiso(actor, "RETIRO_REPOSITORIO", redes_catalogo)
    visibles = [r for r in redes_catalogo if r in set(con_descarga) | set(con_retiro)]
    principal = es_principal(actor)
    if principal:
        visibles = list(redes_catalogo)
    with st.container(key="panel_rep_sel"):
        panel_cab("1. Elija la semana y las redes", "Vale tanto para descargar como para retirar archivos")
        c1, c2, c3 = st.columns([1, 1, 2.4])
        opciones = anios or [anio_actual]
        with c1:
            anio = st.selectbox("Año", opciones, index=opciones.index(anio_actual) if anio_actual in opciones else 0, key="rep_anio")
        with c2:
            semana = st.number_input("Semana", min_value=1, max_value=53, step=1, value=min(semana_base, 53), key=f"rep_semana_{anio}")
        with c3:
            etiqueta_todas = "Todas" if principal else "Todas (las de su alcance)"
            elegidas = st.multiselect("Redes", [etiqueta_todas] + visibles, default=[etiqueta_todas], key="rep_redes",
                                      help="«Todas» incluye cada red a la que usted tiene acceso.")
        dup = st.checkbox("Incluir también los envíos duplicados (van en una subcarpeta DUPLICADOS)", key="rep_dup")
    todas = (not elegidas) or etiqueta_todas in elegidas
    redes = None if todas else [r for r in elegidas if r != etiqueta_todas]
    permitidas = None if principal else (sorted(set(con_descarga) | set(con_retiro)))
    return int(anio), int(semana), redes, bool(dup), permitidas


def _tabla_por_red(envios, descargados, retirados):
    por = {}
    for e in envios:
        r = por.setdefault(e.get("red", "—"), {"Red": e.get("red", "—"), "Envíos": 0, "Con archivo": 0, "Duplicados": 0, "Ya descargados": 0, "Ya retirados": 0})
        r["Envíos"] += 1
        r["Con archivo"] += 1 if tiene_archivo(e) else 0
        r["Duplicados"] += 1 if es_duplicado(e) else 0
        r["Ya descargados"] += 1 if e["id"] in descargados else 0
        r["Ya retirados"] += 1 if e["id"] in retirados else 0
    return pd.DataFrame(sorted(por.values(), key=lambda x: x["Red"]))


# ------------------------------------------------------------------ pestaña: descargar

def _al_descargar(rep, actor, descarga_id):
    info = rep.marcar_descargada(descarga_id, actor)
    st.session_state["rep_mensaje"] = (
        ("ok", "Descarga registrada", f"Se envió el acuse a {info.get('acuse', 0)} persona(s) y quedó anotada en la auditoría.")
        if info.get("ok") else
        ("warn", "No se pudo registrar la descarga", "El archivo se descargó, pero no se pudo anotar. Avise a oiis.winepi."))


def _tab_descargar(rep, actor, anio, semana, redes, dup, permitidas, envios, desc, ret):
    tiene, alcance = rep.permisos.alcance(actor, "DESCARGA_MASIVA")
    if not tiene:
        mostrar(aviso("warn", "No tiene el permiso de descarga masiva",
                      "Pídale a oiis.winepi que se lo asigne en «Permisos de operación». Mientras tanto puede ver qué hay en la semana, pero no descargarlo."))
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        mostrar(kpi("Envíos", len(envios), f"Semana {semana} · {anio}", None, "descarga"))
    with k2:
        mostrar(kpi("Redes", len({e.get('red') for e in envios}), "Con envíos en la selección", None, "dash"))
    with k3:
        sin = sum(1 for e in envios if not tiene_archivo(e))
        mostrar(kpi("Sin archivo", sin, "No se pueden descargar", "warn" if sin else None, "alerta"))
    with k4:
        mostrar(kpi("Ya descargados", sum(1 for e in envios if e["id"] in desc), "En un ZIP masivo anterior", None, "check"))
    with st.container(key="panel_rep_tabla"):
        panel_cab("Qué hay en esta selección", "Cantidad de envíos por red")
        mostrar(tabla_df(_tabla_por_red(envios, desc, ret), derecha=("Envíos", "Con archivo", "Duplicados", "Ya descargados", "Ya retirados"),
                         vacio="No hay envíos para esa semana y esas redes."))
    if not envios or not tiene:
        return

    with st.container(key="panel_rep_preparar"):
        panel_cab("2. Preparar el ZIP", f"Un solo ZIP con una carpeta por red; si pasa de {Config.DESCARGA_MASIVA_MAX_MB} MB se divide en partes")
        mostrar(aviso("info", "¿Dónde se guarda?",
                      "El navegador lo guarda en su carpeta de «Descargas». Para elegir la carpeta cada vez, active en Chrome o Edge "
                      "<strong>Configuración → Descargas → «Preguntar dónde guardar cada archivo»</strong>."))
        firma = (anio, semana, tuple(redes or ["*"]), dup)
        if st.button("Preparar ZIP de la selección", type="primary", icon=":material/folder_zip:", key="rep_btn_preparar"):
            barra = st.progress(0.0, text="Leyendo los archivos de Drive…")

            def avance(i, n, texto):
                barra.progress(min(1.0, i / max(1, n)), text=f"Leyendo archivos de Drive ({i} de {n}) · {texto}")

            res = rep.preparar(actor, anio, semana, redes, dup, avance)
            barra.empty()
            st.session_state["rep_prep"] = {"firma": firma, "res": res}
            st.rerun()
        prep = st.session_state.get("rep_prep")
        if prep and prep["firma"] != firma:
            mostrar(aviso("info", "La selección cambió", "Prepare el ZIP de nuevo para esta semana y estas redes."))
        elif prep:
            res = prep["res"]
            if not res.get("ok"):
                mostrar(aviso("bad", "No se pudo preparar la descarga", esc(res.get("motivo", ""))))
                if res.get("fallos"):
                    lista = "".join(f"<li><strong>{esc(f['codigo'])}</strong> ({esc(f['red'])}): {esc(f['motivo'])}</li>" for f in res["fallos"][:10])
                    mostrar(aviso("warn", f"Detalle de {len(res['fallos'])} archivo(s) que no se pudieron leer",
                                  f"<ul style='margin:6px 0 0 18px'>{lista}</ul>"))
            else:
                total = sum(p["bytes"] for p in res["partes"])
                mostrar(aviso("ok", "El ZIP está listo",
                              f"{sum(p['n_archivos'] for p in res['partes'])} archivo(s) · {_mb(total)} · {len(res['partes'])} parte(s). "
                              "Al pulsar «Descargar» se anota quién lo hizo y se envía el acuse."))
                for p in res["partes"]:
                    c1, c2 = st.columns([3, 1.2], vertical_alignment="center")
                    with c1:
                        mostrar(f'<div class="sire-dato"><small>Parte {p["parte"]} de {p["total_partes"]}</small><b>{esc(p["nombre_zip"])}</b>'
                                f'<small>{p["n_archivos"]} archivo(s) · {_mb(p["bytes"])} · SHA-256 {esc(p["sha256"][:16])}…</small></div>')
                    with c2:
                        st.download_button("Descargar", data=partial(Path(p["ruta"]).read_bytes), file_name=p["nombre_zip"],
                                           mime="application/zip", icon=":material/download:", key=f"rep_dl_{p['descarga_id']}",
                                           on_click=_al_descargar, args=(rep, actor, p["descarga_id"]), use_container_width=True)
                if res.get("fallos"):
                    lista = "".join(f"<li><strong>{esc(f['codigo'])}</strong> ({esc(f['red'])}): {esc(f['motivo'])}</li>" for f in res["fallos"][:20])
                    mostrar(aviso("warn", f"{len(res['fallos'])} archivo(s) no se pudieron leer de Drive",
                                  f"<ul style='margin:6px 0 0 18px'>{lista}</ul>No están en el ZIP ni se podrán retirar hasta resolverlo."))
                if res.get("sin_archivo"):
                    mostrar(aviso("info", f"{len(res['sin_archivo'])} envío(s) sin archivo en Drive", "Solo tienen registro en la base de datos."))


# ------------------------------------------------------------------ pestaña: retirar

def _tab_retirar(rep, actor, anio, semana, redes, envios, desc, permitidas):
    principal = es_principal(actor)
    tiene, alcance = rep.permisos.alcance(actor, "RETIRO_REPOSITORIO")
    if not tiene:
        mostrar(aviso("warn", "No tiene el permiso de retiro del repositorio",
                      "Pídale a oiis.winepi que se lo asigne en «Permisos de operación»."))
        return
    mostrar(aviso(
        "info", "Cómo funciona el retiro",
        "Se quitan los <strong>archivos</strong> de Drive; el registro de recepción (quién envió y cuándo) <strong>se conserva</strong>. "
        "Por defecto van a la <strong>papelera de Drive</strong> y se pueden recuperar unos 30 días. "
        + ("Como SUPER_ADMIN principal, su retiro se ejecuta de inmediato." if principal
           else "Su solicitud la aprueba oiis.winepi; hasta entonces no se retira nada.")))
    if alcance is not None:
        envios = [e for e in envios if e.get("red") in alcance]
    ev = rep.evaluar_seleccion(anio, semana, envios)
    retirables = ev["retirables"]
    k1, k2, k3 = st.columns(3)
    with k1:
        mostrar(kpi("Se pueden retirar", len(retirables), f"Semana {semana} · {anio}", None, "basura"))
    with k2:
        mostrar(kpi("Ya retirados", len(ev["ya_retirados"]), "No vuelven a aparecer", None, "check"))
    with k3:
        mostrar(kpi("Sin descarga previa", len(ev["sin_descarga"]), "Aún no están en un ZIP masivo", "warn" if ev["sin_descarga"] else "ok", "alerta"))
    if not retirables:
        mostrar('<div class="sire-vacio">No hay archivos para retirar en esta selección.</div>')
        return
    with st.container(key="panel_rep_retirar"):
        panel_cab("2. Pedir el retiro" if not principal else "2. Retirar", f"{len(retirables)} archivo(s) de {len({e.get('red') for e in retirables})} red(es)")
        if ev["sin_descarga"]:
            mostrar(aviso("warn", f"{len(ev['sin_descarga'])} envío(s) no se descargaron antes",
                          "Si los retira, no habrá otra copia fuera de Drive. Descárguelos primero (pestaña «Descargar») salvo que haya una razón para no hacerlo; "
                          "esto se marca en la auditoría y en el aviso a oiis.winepi."))
        motivo_cat = st.selectbox("Motivo", MOTIVOS_RETIRO, key="rep_motivo_cat")
        detalle = st.text_area("Explique el motivo", key="rep_motivo", height=90, max_chars=1000,
                               placeholder="Ejemplo: ya están respaldados en el servidor y se necesita espacio en Drive.")
        definitivo = False
        if principal:
            definitivo = st.checkbox("Borrar definitivamente (no pasa por la papelera, no se puede recuperar; libera espacio)", key="rep_definitivo")
        else:
            st.caption("Los archivos irán a la papelera de Drive. El borrado definitivo lo decide solo oiis.winepi.")
        frase = f"RETIRAR S{semana}-{anio}"
        escrito = st.text_input(f"Para confirmar, escriba exactamente: {frase}", key="rep_confirma", placeholder=frase)
        etiqueta = "Retirar ahora" if principal else "Enviar la solicitud de retiro"
        if st.button(etiqueta, type="primary", icon=":material/delete:", key="rep_btn_retirar"):
            if (escrito or "").strip() != frase:
                st.info(f"Escriba {frase} para confirmar.")
            else:
                with st.spinner("Procesando…"):
                    res = rep.solicitar_retiro(actor, anio, semana, redes, retirables, motivo_cat, detalle, definitivo)
                st.session_state["rep_mensaje"] = ("ok" if res["ok"] else "bad",
                                                   "Listo" if res["ok"] else "No se pudo", esc(res["mensaje"]))
                for k in ("rep_motivo", "rep_confirma"):
                    st.session_state.pop(k, None)
                st.rerun()


# ------------------------------------------------------------------ pestaña: solicitudes

def _detalle_solicitud(rep, actor, sol, principal):
    from src.auditoria_excel import generar_excel_retiro, nombre_excel_retiro
    archivos = rep.archivos_de(sol["id"])
    redes = "Todas" if sol.get("todas_las_redes") else ", ".join(sol.get("redes") or []) or "—"
    c1, c2, c3 = st.columns(3)
    with c1:
        mostrar(f'<div class="sire-dato"><small>Solicitó</small><b>{esc(sol.get("solicitado_nombre") or sol.get("solicitado_por"))}</b>'
                f'<small>{fecha_lima(sol.get("fecha_creacion"))}</small></div>')
    with c2:
        mostrar(f'<div class="sire-dato"><small>Semana · redes</small><b>S{sol["semana"]} · {sol["anio"]}</b><small>{esc(redes)}</small></div>')
    with c3:
        mostrar(f'<div class="sire-dato"><small>Estado</small>{_chip_estado(sol["estado"])}'
                f'<small>{sol.get("n_envios", 0)} envío(s)</small></div>')
    mostrar(f'<div class="sire-dato"><small>Motivo · {esc(sol.get("motivo_categoria"))}</small><b style="font-weight:500">{esc(sol.get("motivo"))}</b></div>')
    if sol.get("sin_descarga_previa"):
        mostrar(aviso("warn", "Sin descarga previa", "Se retirarían archivos que aún no están en un ZIP masivo."))
    if sol.get("decidido_por"):
        mostrar(f'<div class="sire-dato"><small>Decidió</small><b>{esc(sol.get("decidido_nombre") or sol.get("decidido_por"))}</b>'
                f'<small>{fecha_lima(sol.get("fecha_decision"))} · {esc(sol.get("nota_decision") or "")}</small></div>')
    if archivos:
        df = pd.DataFrame({"Código": [a.get("codigo_seguimiento") for a in archivos], "Red": [a.get("red") for a in archivos],
                           "Centros": [a.get("centros") for a in archivos],
                           "Resultado": [("Retirado" if a.get("resultado") == "OK" else "Error") for a in archivos],
                           "Detalle": [a.get("detalle") for a in archivos], "Fecha": [fecha_lima(a.get("fecha")) for a in archivos]})
        mostrar(tabla_df(df, alto=260))
    if sol["estado"] in ("EJECUTADA", "PARCIAL", "ERROR"):
        st.download_button("Descargar el Excel del registro", data=generar_excel_retiro(sol, archivos),
                           file_name=nombre_excel_retiro(sol), icon=":material/download:", key=f"rep_xl_{sol['id']}",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if principal and sol["estado"] in ("PARCIAL", "ERROR"):
        if st.button("Reintentar los archivos con error", icon=":material/refresh:", key=f"rep_reint_{sol['id']}"):
            with st.spinner("Reintentando…"):
                res = rep.reintentar(st.session_state.get("admin_token"), sol["id"])
            st.session_state["rep_mensaje"] = ("ok" if res["ok"] else "bad", "Reintento", esc(res["mensaje"]))
            st.rerun()
    if sol["estado"] == "PENDIENTE" and (str(sol.get("solicitado_por")).lower() == str(actor.get("usuario", "")).lower()):
        if st.button("Cancelar mi solicitud", key=f"rep_cancel_{sol['id']}", icon=":material/close:"):
            ok, msg = rep.cancelar_solicitud(actor, sol["id"])
            st.session_state["rep_mensaje"] = ("ok" if ok else "bad", msg)
            st.rerun()


def _decidir(rep, sol):
    token = st.session_state.get("admin_token")
    mostrar('<div style="height:10px"></div>')
    st.markdown("**Su decisión**")
    nota = st.text_area("Nota (obligatoria si rechaza)", key=f"rep_nota_{sol['id']}", height=70, max_chars=500)
    definitivo = st.checkbox("Borrar definitivamente en vez de enviar a la papelera", value=bool(sol.get("definitivo")), key=f"rep_def_{sol['id']}")
    conf = st.checkbox("Revisé la selección y el motivo, y autorizo el retiro", key=f"rep_ok_{sol['id']}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Aprobar y retirar", type="primary", icon=":material/check_circle:", key=f"rep_apr_{sol['id']}", use_container_width=True):
            if not conf:
                st.info("Marque la casilla para autorizar.")
            else:
                with st.spinner("Retirando archivos…"):
                    res = rep.decidir(token, sol["id"], True, nota, definitivo)
                st.session_state["rep_mensaje"] = ("ok" if res["ok"] else "bad", "Retiro", esc(res["mensaje"]))
                st.rerun()
    with c2:
        if st.button("Rechazar", icon=":material/block:", key=f"rep_rec_{sol['id']}", use_container_width=True):
            res = rep.decidir(token, sol["id"], False, nota)
            if res["ok"]:
                st.session_state["rep_mensaje"] = ("ok", "Solicitud rechazada", esc(res["mensaje"]))
                st.rerun()
            else:
                st.error(res["mensaje"])


def _tab_solicitudes(rep, actor):
    principal = es_principal(actor)
    todas = rep.listar_solicitudes(None, None if principal else actor.get("usuario"), 200)
    if not todas:
        mostrar('<div class="sire-vacio">Todavía no hay solicitudes de retiro.</div>')
        return
    pend = [s for s in todas if s["estado"] == "PENDIENTE"]
    if principal and pend:
        mostrar(aviso("warn", f"{len(pend)} solicitud(es) esperan su decisión", "Nada se retira hasta que usted apruebe."))
        for s in pend:
            with st.container(border=True, key=f"rep_pend_{s['id']}"):
                st.markdown(f"**Solicitud N.º {s['id']}**")
                _detalle_solicitud(rep, actor, s, principal)
                _decidir(rep, s)
    with st.container(key="panel_rep_hist_sol"):
        panel_cab("Historial de solicitudes", "Todas las personas" if principal else "Las suyas")
        df = pd.DataFrame({"N.º": [s["id"] for s in todas], "Fecha": [fecha_lima(s.get("fecha_creacion")) for s in todas],
                           "Solicitó": [s.get("solicitado_por") for s in todas], "Semana": [f"S{s['semana']} · {s['anio']}" for s in todas],
                           "Envíos": [s.get("n_envios") for s in todas], "Estado": [_chip_estado(s["estado"]) for s in todas],
                           "Decidió": [s.get("decidido_por") or "—" for s in todas]})
        mostrar(tabla_df(df, crudas=("Estado",), derecha=("N.º", "Envíos")))
        ids = [s["id"] for s in todas]
        elegido = st.selectbox("Ver el detalle de la solicitud", ids, format_func=lambda i: f"N.º {i}", key="rep_sel_sol")
        sol = next(s for s in todas if s["id"] == elegido)
        if sol["estado"] != "PENDIENTE" or not principal:
            _detalle_solicitud(rep, actor, sol, principal)


# ------------------------------------------------------------------ pestaña: historial

def _tab_historial(rep, actor):
    principal = es_principal(actor)
    filas = rep.listar_descargas(100, None if principal else actor.get("usuario"))
    with st.container(key="panel_rep_hist_desc"):
        panel_cab("Descargas masivas", "Todas las personas" if principal else "Las suyas")
        if not filas:
            mostrar('<div class="sire-vacio">Todavía no hay descargas.</div>')
            return
        df = pd.DataFrame({"Fecha": [fecha_lima(f.get("fecha_preparada")) for f in filas], "Responsable": [f.get("usuario") for f in filas],
                           "Semana": [f"S{f['semana']} · {f['anio']}" for f in filas],
                           "Redes": ["Todas" if f.get("todas_las_redes") else ", ".join(f.get("redes") or []) for f in filas],
                           "Archivo": [f.get("nombre_zip") for f in filas], "Archivos": [f.get("n_archivos") for f in filas],
                           "Tamaño": [_mb(f.get("bytes")) for f in filas],
                           "Estado": [chip("Descargada", "ok", "check") if f.get("estado") == "DESCARGADA" else chip("Solo preparada", "mute") for f in filas]})
        mostrar(tabla_df(df, crudas=("Estado",), derecha=("Archivos", "Tamaño")))
        st.caption("La huella digital (SHA-256) de cada ZIP, que permite comprobar que un archivo guardado no fue modificado, está en el acuse y en el Excel de auditoría.")


# ------------------------------------------------------------------ página

def mostrar_descarga_limpieza():
    """Pantalla «Descarga y limpieza»."""
    actor = actor_actual()
    rep = get_repositorio()
    if not rep.disponible():
        mostrar(aviso("info", "Falta crear las tablas de auditoría y permisos",
                      "Ejecute <strong>sql/11_auditoria_permisos_repositorio.sql</strong> en el SQL Editor de Supabase."))
        return
    _mensaje_pendiente()
    redes_catalogo = _redes_catalogo()
    mios = rep.permisos.permisos_de(actor)
    if es_principal(actor):
        mostrar(aviso("ok", "SUPER_ADMIN principal", "Usted tiene todos los permisos. Sus retiros se ejecutan de inmediato y todo queda registrado."))
    else:
        chips = " ".join(chip(esc(PERMISOS[p][0]), "info") for p in mios) or chip("Sin permisos asignados", "warn")
        mostrar(f'<div class="sire-dato"><small>Sus permisos</small><div>{chips}</div></div>')

    anio, semana, redes, dup, permitidas = _selector(rep, actor, redes_catalogo)
    try:
        envios = rep.envios_de(anio, semana, redes, dup, permitidas=permitidas)
        desc = rep.descargados_ids(anio, semana)
        ret = rep.retirados_ids([e["id"] for e in envios]) if envios else set()
    except Exception as e:
        mostrar(aviso("bad", "No se pudo leer la selección", esc(str(e))))
        return
    t1, t2, t3, t4 = st.tabs(["Descargar", "Retirar del repositorio", "Solicitudes de retiro", "Historial de descargas"])
    with t1:
        _tab_descargar(rep, actor, anio, semana, redes, dup, permitidas, envios, desc, ret)
    with t2:
        _tab_retirar(rep, actor, anio, semana, redes, envios, desc, permitidas)
    with t3:
        _tab_solicitudes(rep, actor)
    with t4:
        _tab_historial(rep, actor)
