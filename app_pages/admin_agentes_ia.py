# app_pages/admin_agentes_ia.py
"""
Panel «Agente de IA» de SIREA 3.0.

Pestañas:
  * Bandeja        propuestas del Agente Operativo: aprobar (con edición),
                   rechazar con motivo. Es donde trabaja la persona.
  * Corridas       ejecutar ahora y ver la traza paso a paso de cada corrida.
  * Skills         procedimientos que sigue el agente (versión, huella,
                   compuerta de evaluaciones) y su texto completo.
  * Evaluaciones   casos de prueba: con IA contra sin IA.
  * Memoria        notas por red que el agente lee en cada corrida.
  * Investigador   consulta de diagnóstico (solo lectura).
  * Estado         botón de detención, proveedores, catálogo y ciclo de vida.
  * Auditoría      registro inmutable.

Las fichas de gobernanza (riesgos, controles, marcos) viven en el código y
en docs/GOBERNANZA_SIREA.md; no se muestran aquí.

Reglas de la pantalla: todo texto que venga de datos o del modelo pasa por
`esc()`; lila = propuesta de la IA pendiente; verde = decidido por una persona.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from src.agentes import auditoria, estado
from src.config import Config
from utils import tema_ia
from utils.tema import aviso, chip, kpi, mostrar
from utils.tema_admin import kpis, mostrar_tabla
from utils.tema_ia import esc  # admite esc(texto, maximo)

OPERATIVO = auditoria.AGENTE_OPERATIVO

TITULO_ACCION = {
    "RECORDATORIO_RED": ("Recordatorio a la red", "Aprobar y enviar", ":material/send:"),
    "SOLICITAR_CORRECCION": ("Pedir corrección a la red", "Aprobar y enviar", ":material/send:"),
    "MARCAR_REVISADA": ("Dar por revisada la observación", "Aprobar y marcar", ":material/task_alt:"),
    "REINTENTAR_FALLA": ("Reintentar falla técnica", "Aprobar y reintentar", ":material/refresh:"),
    "ESCALAR": ("Necesita una decisión suya", "Lo asumo yo", ":material/front_hand:"),
    "NOTA_MEMORIA": ("Recordar un dato de la red", "Guardar en la memoria", ":material/bookmark_add:"),
}
CORTO = {"RECORDATORIO_RED": "Recordar a la red", "SOLICITAR_CORRECCION": "Pedir corrección", "MARCAR_REVISADA": "Dar por revisada",
         "REINTENTAR_FALLA": "Reintentar", "ESCALAR": "Escalar a una persona", "NOTA_MEMORIA": "Nota de memoria",
         "SIN_ACCION": "No actuar"}
TONO_ESTADO_ACCION = {"PROPUESTA": "ia", "EJECUTADA": "ok", "FALLIDA": "bad", "RECHAZADA": "mute", "VENCIDA": "mute"}


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

def _usuario_actual() -> Dict[str, str]:
    info = st.session_state.get("admin_usuario") or {}
    return {"usuario": str(info.get("usuario") or ""), "rol": str(info.get("rol") or "ADMIN"),
            "nombre": str(info.get("nombre") or info.get("usuario") or "")}


def _es_super_admin() -> bool:
    return _usuario_actual()["rol"] == "SUPER_ADMIN"


def _chip_estado(est: str) -> str:
    return chip(estado.ETIQUETA_UI.get(est, est), estado.TONO_UI.get(est, "mute"))


def _mostrar_error(e: Exception):
    """Errores sin trazas técnicas al usuario; el detalle queda en el log del servidor."""
    import logging
    logging.getLogger("sirea.agentes").exception("Error en el panel de IA: %s", e)
    from src.agentes.proveedores import ProveedorNoDisponibleError
    if isinstance(e, estado.AgenteNoDisponibleError):
        mostrar(aviso("warn", "Agente no disponible", esc(estado.mensaje_no_disponible(e.agente))))
    elif isinstance(e, ProveedorNoDisponibleError):
        mostrar(aviso("bad", "Ningún proveedor de IA pudo responder",
                      esc(str(e), 700) + " · Use «Gobernanza de IA → Encender y apagar → Probar los proveedores de IA» para verificar claves y modelos."))
    elif isinstance(e, RuntimeError):
        mostrar(aviso("bad", "No se pudo completar la operación", esc(str(e), 500)))
    else:
        mostrar(aviso("bad", "No se pudo completar la operación",
                      "Ocurrió un error al consultar al proveedor de IA o a la base de datos. "
                      "Revise la configuración (claves en el .env) o intente más tarde."))


def _fecha_corta(valor) -> str:
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if dt.tzinfo and Config.ZONA_HORARIA:
            dt = dt.astimezone(Config.ZONA_HORARIA)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(valor or "")[:16]


def _multilinea(texto, maximo: int = 6000) -> str:
    """Texto escapado conservando los saltos de línea (el HTML se compacta al mostrarse)."""
    return esc(texto or "", maximo).replace("\n", "<br>")


def _pct(v) -> str:
    return "—" if v is None else f"{round(float(v) * 100)} %"


def _aviso_no_operativo() -> bool:
    """Muestra por qué el Agente Operativo no opera. Devuelve True si no opera."""
    if estado.esta_operativo(OPERATIVO):
        return False
    g, i = estado.estado_global(), estado.estado_individual(OPERATIVO)
    if g != estado.ACTIVO_HITL:
        texto = (f"La IA está «{estado.ETIQUETA_UI.get(g, g)}» (estado general). Un SUPER_ADMIN puede reactivarla en «Gobernanza de IA → Encender y apagar».")
    else:
        texto = (f"El Agente Operativo está «{estado.ETIQUETA_UI.get(i, i)}». Para activarlo, primero una skill debe pasar "
                 "sus evaluaciones («Gobernanza de IA → Evaluaciones») y luego un SUPER_ADMIN lo activa en «Encender y apagar».")
    mostrar(aviso("warn", "El Agente Operativo no está activo", esc(texto)))
    return True


# ------------------------------------------------------------
# entrada
# ------------------------------------------------------------

def mostrar_agentes_ia():
    from src.agentes import agente_operativo as ag
    res = estado.resumen()
    if not Config.tiene_ia():
        mostrar(aviso("warn", "Sin proveedor de IA configurado",
                      "Agregue GEMINI_API_KEY (y opcionalmente GROQ_API_KEY) en el .env. Sin proveedor, el agente "
                      "solo puede trabajar en modo reglas y no pasará sus evaluaciones."))
    if not ag.disponible():
        mostrar(aviso("bad", "Faltan las tablas del Agente Operativo",
                      "Ejecute <b>sql/52_agente_operativo.sql</b> en el SQL Editor de Supabase y recargue la página."))

    m = ag.metricas(30)
    provs = Config.proveedores_ia_disponibles()
    kpis([
        kpi("Propuestas por decidir", m["pendientes"], "Esperan su aprobación o rechazo", tono="ia", ico="ia"),
        kpi("Ejecutadas (30 días)", m["ejecutadas"], f"Aprobadas por una persona · rechazadas {m['rechazadas']}",
            tono="ok", ico="check"),
        kpi("Aprobación", _pct(m["tasa_aprobacion"]), f"Sin editar: {_pct(m['tasa_sin_editar'])} de las aprobadas",
            tono="info", ico="barras"),
        kpi("Estado", "Activo" if res.efectivo[OPERATIVO] == estado.ACTIVO_HITL
            else estado.ETIQUETA_UI.get(res.efectivo[OPERATIVO], res.efectivo[OPERATIVO]),
            ("Con supervisión humana · " if res.efectivo[OPERATIVO] == estado.ACTIVO_HITL else "")
            + "Proveedores: " + (" → ".join(p.capitalize() for p in provs) if provs else "ninguno"),
            tono=estado.TONO_UI.get(res.efectivo[OPERATIVO]), ico="escudo"),
    ])

    etiquetas = ["Pendientes", "Bandeja", "Patrones", "Informe semanal"]
    tabs = dict(zip(etiquetas, st.tabs(etiquetas)))
    with tabs["Pendientes"]:
        _tab_pendientes()
    with tabs["Bandeja"]:
        _tab_bandeja()
    with tabs["Patrones"]:
        _tab_patrones()
    with tabs["Informe semanal"]:
        _tab_informe()
    st.caption("¿Cómo decide la IA, quién la controla y qué hizo? Está en «Gobernanza de IA». "
               "Para preguntas rápidas use Quipu, el asistente de bolsillo (abajo a la derecha).")


def mostrar_gobernanza_ia():
    """SIREA 3.3: cómo funciona la IA y cómo se controla (separado del trabajo diario)."""
    res = estado.resumen()
    if not Config.tiene_ia():
        mostrar(aviso("warn", "Sin proveedor de IA configurado",
                      "Agregue GEMINI_API_KEY (y opcionalmente GROQ_API_KEY) en el .env."))
    etiquetas = ["Cómo funciona", "Rondas del agente", "Procedimientos", "Evaluaciones", "Memoria", "Encender y apagar",
                 "Historial de IA"]
    tabs = dict(zip(etiquetas, st.tabs(etiquetas)))
    with tabs["Cómo funciona"]:
        _tab_como_funciona(res)
    with tabs["Rondas del agente"]:
        _tab_corridas()
    with tabs["Procedimientos"]:
        _tab_skills()
    with tabs["Evaluaciones"]:
        _tab_evaluaciones()
    with tabs["Memoria"]:
        _tab_memoria()
    with tabs["Encender y apagar"]:
        _tab_estado(res)
    with tabs["Historial de IA"]:
        _tab_auditoria()


def _tab_como_funciona(res):
    pasos = [
        ("1", "Mira los datos", "Cada día hábil el sistema revisa qué llegó, qué falta por centro y tipo de reporte, y cómo viene cada red. "
                                "Esto lo cuenta el sistema, no la IA."),
        ("2", "Hace su ronda", "El agente lee cada caso con su procedimiento escrito (skill) y propone qué hacer: recordar, escalar o no actuar."),
        ("3", "Las reglas revisan", "Se descarta lo que no cumple: centros inventados, datos personales, comparaciones con otras redes, "
                                    "recordatorios repetidos."),
        ("4", "Usted decide", "Lo que pasa queda en «Agente de IA → Bandeja». Nada se envía sin su aprobación."),
        ("5", "Queda registrado", "Cada consulta, propuesta, aprobación y envío va al Historial de IA, que nadie puede borrar."),
    ]
    filas = "".join(f'<div class="sirea-paso"><span class="sirea-paso-n">{n}</span><div><b>{esc(t)}</b><br>{esc(d)}</div></div>'
                    for n, t, d in pasos)
    mostrar(f'<div class="sirea-pasos">{filas}</div>')
    st.caption("Quipu, el asistente de bolsillo, solo consulta: responde con los datos del sistema y no cambia nada.")
    fichas = list(estado.CATALOGO.values())
    cols = st.columns(3)
    for i, f in enumerate(fichas):
        with cols[i % 3]:
            mostrar(tema_ia.tarjeta_agente(f.nombre, f.rol, f.descripcion, f.nivel,
                                           estado_chip=_chip_estado(res.efectivo[f.clave]), gris=not f.construido))


# ------------------------------------------------------------
# Centro de pendientes (catálogo por secciones)
# ------------------------------------------------------------

_TTL_PENDIENTES = 120


def _ir(destino: str):
    st.session_state.seccion_admin = destino


def _tab_pendientes():
    import time
    from src.agentes import pendientes
    from utils.tema import TONOS
    rol = _usuario_actual()["rol"]
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.caption("Todo lo que hoy necesita a un administrador, por sección y lo urgente primero. "
               "Las reglas detectan; la IA interviene solo donde hay que leer o decidir (chip lila).")
    cache = st.session_state.get("sirea_pendientes")
    if c2.button("Actualizar", key="pend_actualizar", icon=":material/refresh:", use_container_width=True) \
            or not cache or cache[0] != rol or time.time() - cache[1] > _TTL_PENDIENTES:
        with st.spinner("Revisando cada sección…"):
            cache = (rol, time.time(), pendientes.todos(rol))
        st.session_state["sirea_pendientes"] = cache
    lista = cache[2]
    urgentes = [p for p in lista if p.requiere_atencion]
    if urgentes:
        mostrar(aviso("warn", f"{len(urgentes)} sección(es) requieren atención",
                      esc(" · ".join(p.titulo for p in urgentes))))
    else:
        mostrar(aviso("ok", "Todo en orden", "No hay nada urgente en ninguna sección."))
    cols = st.columns(2)
    for i, p in enumerate(lista):
        fg = TONOS.get(p.tono, TONOS["mute"])[0]
        chips = (tema_ia.chip_ia("Regla + IA") if "IA" in p.origen else chip("Lo detecta una regla", "mute", "info"))
        if p.nivel == "restringido":
            chips += chip("Uso restringido: solo sugiere", "warn", "candado")
        items = "".join(f"<li>{esc(d, 220)}</li>" for d in p.detalle if d)
        with cols[i % 2]:
            with st.container(border=True, key=f"pend_{p.clave}"):
                mostrar(f'<div class="sirea-pend" style="border-left:5px solid {fg}">'
                        f'<div class="sirea-prop-cab"><div class="sirea-prop-tit">{esc(p.titulo)}</div>'
                        f'<div style="display:flex;gap:6px;flex-wrap:wrap">{chips}</div></div>'
                        f'<div class="sirea-pend-cifra" style="color:{fg}">{esc(p.cifra)}</div>'
                        f'<div class="sirea-prop-just">{esc(p.resumen)}</div>'
                        + (f'<ul class="sirea-pend-lista">{items}</ul>' if items else "") + "</div>")
                if p.destino:
                    st.button(p.accion or "Ir", key=f"pend_ir_{p.clave}", icon=":material/arrow_forward:",
                              on_click=_ir, args=(p.destino,), use_container_width=True)
                elif p.clave == "agente" and p.cifra not in ("0", "—"):
                    st.caption("Están en la pestaña «Bandeja», aquí arriba.")


# ------------------------------------------------------------
# Bandeja
# ------------------------------------------------------------

def _tab_bandeja():
    from src.agentes import agente_operativo as ag
    from src.agentes.skills import cargar_todas
    skills = cargar_todas()
    no_opera = _aviso_no_operativo()
    pend = ag.propuestas("PROPUESTA")
    flash = st.session_state.pop("sirea_bandeja_flash", None)
    if flash:
        (st.success if flash[0] else st.error)(flash[1])
    if not pend:
        mostrar(aviso("info", "No hay propuestas por decidir",
                      "El agente corre solo cada día hábil desde las "
                      f"{int(getattr(Config, 'AGENTE_HORA', 9)):02d}:00 (hora de Lima). También puede correrlo ahora en «Gobernanza de IA → Rondas del agente»."))
    else:
        from app_pages.filtro_periodo import filtro_red
        c1, c2 = st.columns([1.3, 3], vertical_alignment="bottom")
        with c1:
            red_f = filtro_red("bandeja", [p.get("red") for p in pend])
        filtro = c2.radio("Mostrar", ["Todas"] + [s.nombre for s in skills.values()], horizontal=True, key="bandeja_filtro",
                          label_visibility="collapsed")
        vistas = 0
        for p in pend:
            sk = skills.get(p.get("skill"))
            if filtro != "Todas" and (not sk or sk.nombre != filtro):
                continue
            if red_f and p.get("red") != red_f:
                continue
            vistas += 1
            _tarjeta_propuesta(p, sk, deshabilitar=no_opera)
        if not vistas:
            st.caption(f"Ninguna de las {len(pend)} propuesta(s) coincide con el filtro.")

    with st.expander("Historial de decisiones", expanded=False):
        hist = [h for h in ag.historial_acciones(200) if h.get("estado") != "PROPUESTA"]
        if not hist:
            st.caption("Todavía no hay decisiones.")
        else:
            filas = [[_fecha_corta(h.get("decidida_at") or h.get("creada_at")), TITULO_ACCION.get(h["tipo"], (h["tipo"],))[0],
                      esc(h.get("red") or "—", 30), chip(esc(h.get("estado")), TONO_ESTADO_ACCION.get(h.get("estado"), "mute")),
                      esc(h.get("decidida_por") or "—", 24), "Sí" if h.get("editada") else "No",
                      esc(h.get("resultado") or h.get("motivo_decision") or "", 120)] for h in hist]
            mostrar_tabla(pd.DataFrame(filas, columns=["Fecha", "Acción", "Red", "Estado", "Decidió", "Editada", "Resultado o motivo"]),
                          crudas=("Estado",))


def _tarjeta_propuesta(p: Dict, sk, deshabilitar: bool):
    from src.agentes import agente_operativo as ag
    pid = p["id"]
    tipo = p.get("tipo")
    titulo, boton, ico = TITULO_ACCION.get(tipo, (tipo, "Aprobar", ":material/check:"))
    pay = dict(p.get("payload") or {})
    ev = p.get("evidencia") or {}
    actor = _usuario_actual()
    requiere = sk.quien_aprueba if sk else "SUPER_ADMIN"
    puede = requiere != "SUPER_ADMIN" or actor["rol"] == "SUPER_ADMIN"
    with st.container(key=f"prop_{pid}"):
        sub = " · ".join(x for x in [str(p.get("red") or ""), f"semana {p['semana']}" if p.get("semana") else "",
                                     f"código {pay['codigo']}" if pay.get("codigo") else "", _fecha_corta(p.get("creada_at"))] if x)
        origen = (tema_ia.chip_ia("Propuesta de la IA") if p.get("origen") == "ia"
                  else chip("Regla sin IA", "mute", "info"))
        prov = str(p.get("proveedor") or "")
        mostrar(f'<div class="sirea-prop-cab"><div><div class="sirea-prop-tit">{esc(titulo)}</div>'
                f'<div class="sirea-prop-sub">{esc(sub)}</div></div>'
                f'<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">{origen}'
                f'{tema_ia.chip_proveedor(prov.split(":")[0], prov.split(":", 1)[1] if ":" in prov else None) if prov else ""}'
                f'{chip(esc(sk.nombre if sk else p.get("skill")), "info")}</div></div>'
                f'<div class="sirea-prop-just">{esc(p.get("justificacion") or "")}</div>')

        ed: Dict[str, str] = {}
        if tipo == "RECORDATORIO_RED":
            _detalle_recordatorio(pid, pay, ev, ed)
        elif tipo == "SOLICITAR_CORRECCION":
            c1, c2 = st.columns(2)
            ed["destinatario"] = c1.text_input("Correo del destinatario", value=pay.get("destinatario") or "", key=f"d_{pid}",
                                               help=pay.get("destinatario_origen") or "")
            ed["nombre_destinatario"] = c2.text_input("Nombre", value=pay.get("nombre_destinatario") or "", key=f"n_{pid}")
            ed["motivo_correccion"] = st.text_area("Qué debe corregir la red", value=pay.get("motivo_correccion") or "",
                                                   key=f"c_{pid}", max_chars=700, height=100)
        elif tipo in ("MARCAR_REVISADA", "NOTA_MEMORIA"):
            ed["nota"] = st.text_area("Nota", value=pay.get("nota") or "", key=f"t_{pid}", max_chars=300, height=70)
            if tipo == "NOTA_MEMORIA":
                st.caption(f"Vigencia: {pay.get('vigencia_dias', 60)} días. El agente la leerá en cada corrida sobre esta red.")
        elif tipo == "ESCALAR":
            mostrar(f'<div class="sirea-prop-dato"><b>Qué debe decidir:</b> {esc(pay.get("motivo") or "", 600)}</div>')
            st.caption("«Lo asumo yo» solo deja constancia de que una persona tomó el caso; no envía nada.")

        with st.expander("Por qué lo propone", expanded=False):
            st.markdown(f"**Razonamiento del agente:** {esc(ev.get('razonamiento') or '—', 600)}", unsafe_allow_html=True)
            datos = []
            if ev.get("recibidos") is not None:
                datos.append(f"recibidos {ev.get('recibidos')}, faltan {ev.get('faltantes')}")
            if ev.get("horas_al_corte") is not None:
                datos.append(f"horas al corte {ev.get('horas_al_corte')}")
            if ev.get("herramientas"):
                datos.append("consultó: " + ", ".join(map(str, ev["herramientas"])))
            if datos:
                st.caption(" · ".join(datos))
            st.caption(f"Skill {p.get('skill')} v{p.get('skill_version')} · corrida {p.get('corrida_id')} · propuesta ACC-{pid}")

        c1, c2, c3 = st.columns([1.4, 2.2, 1.1], vertical_alignment="bottom")
        with c1:
            if st.button(boton, key=f"ok_{pid}-lila", type="primary", icon=ico, use_container_width=True,
                         disabled=deshabilitar or not puede):
                try:
                    ok, msg = ag.aprobar(pid, actor, ed)
                except Exception as e:  # noqa: BLE001
                    _mostrar_error(e)
                else:
                    st.session_state["sirea_bandeja_flash"] = (ok, msg)
                    st.session_state.pop("_obs_contador", None)     # contador del menú «Observaciones»
                    st.rerun()
            if not puede:
                st.caption(f"La aprueba un {requiere}.")
        with c2:
            motivo = st.text_input("Motivo del rechazo", key=f"r_{pid}", placeholder="Por qué no (mejora la skill)",
                                   label_visibility="collapsed")
        with c3:
            if st.button("Rechazar", key=f"no_{pid}", icon=":material/close:", use_container_width=True):
                ok, msg = ag.rechazar(pid, actor, motivo)
                st.session_state["sirea_bandeja_flash"] = (ok, msg)
                st.rerun()



def _detalle_recordatorio(pid, pay: Dict, ev: Dict, ed: Dict):
    """SIREA 3.2: qué falta por tipo, lo interno (solo para el admin), destinatarios, borrador formal y vista previa."""
    por_tipo = pay.get("pendientes_por_tipo") or []
    tono = "atraso (el corte ya venció)" if pay.get("tono") == "ATRASADO" else "preventivo (antes del corte)"
    if por_tipo:
        filas = "".join(f"<tr><td>{esc(x.get('centro'), 90)}</td><td>{esc(', '.join(x.get('recibidos') or []) or '—', 90)}</td>"
                        f"<td><b>{esc(', '.join(x.get('faltan') or []), 90)}</b></td></tr>" for x in por_tipo[:30])
        mostrar('<div class="sirea-prop-dato"><b>Lo que falta, por tipo de reporte</b> (datos del sistema)</div>'
                '<table class="sirea-falta"><tr><th>Centro</th><th>Ya llegó</th><th>Falta</th></tr>' + filas + "</table>")
    else:
        mostrar(f'<div class="sirea-prop-dato"><b>Centros pendientes:</b> {esc(", ".join(pay.get("centros_pendientes") or []), 600)}</div>')
    mostrar(f'<div class="sirea-prop-dato"><b>Tono:</b> {tono} — lo fija el reloj del sistema</div>')
    interno = []
    if ev.get("perfil"):
        interno.append(esc(ev["perfil"], 300))
    ctx = ev.get("contexto_interno") or {}
    if ctx.get("redes_total"):
        if ctx.get("es_la_unica_red_con_pendientes"):
            interno.append(f"Es la única red con pendientes esta semana ({ctx.get('redes_completas')} de {ctx.get('redes_total')} completaron).")
        elif ctx.get("redes_completas") is not None:
            interno.append(f"{ctx.get('redes_completas')} de {ctx.get('redes_total')} redes ya completaron la semana.")
    if interno:
        mostrar('<div class="sirea-interno"><span class="sirea-interno-tit">Solo para usted · no va en el correo</span>'
                + "<br>".join(interno) + "</div>")
    if pay.get("aviso_mensaje"):
        mostrar(aviso("warn", "Se cambió el párrafo propuesto por la IA", esc(pay["aviso_mensaje"], 300)))
    c1, c2 = st.columns(2)
    ed["destinatario"] = c1.text_input("Para (responsable del envío)", value=pay.get("destinatario") or "", key=f"d_{pid}",
                                       help=pay.get("destinatario_origen") or "")
    ed["nombre_destinatario"] = c2.text_input("Nombre", value=pay.get("nombre_destinatario") or "", key=f"n_{pid}")
    ed["copias"] = st.text_input("En copia (otros responsables que enviaron por la red; separe con comas)",
                                 value=pay.get("copias") or "", key=f"cc_{pid}")
    origen = "Redactado por la IA" if pay.get("mensaje_origen") == "ia" else "Borrador estándar del sistema"
    ed["mensaje_personalizado"] = st.text_area(f"Borrador del mensaje · {origen} (formal; puede editarlo antes de enviar)",
                                               value=pay.get("mensaje_personalizado") or "", key=f"m_{pid}", max_chars=900, height=140)
    with st.expander("Vista previa del correo", expanded=False):
        try:
            from src.agentes.acciones import vista_previa_recordatorio
            asunto, texto = vista_previa_recordatorio({**pay, **{k: v for k, v in ed.items() if v is not None}})
            mostrar(f'<div class="sirea-preview"><b>Asunto:</b> {esc(asunto)}<hr>{_multilinea(texto)}</div>')
        except Exception as e:  # noqa: BLE001
            st.caption(f"No se pudo armar la vista previa ({type(e).__name__}).")


# ------------------------------------------------------------
# Patrones (SIREA 3.2): calculados por el sistema, uso interno
# ------------------------------------------------------------

_TTL_PATRONES = 120


def _historial_patrones(forzar: bool = False, anio: Optional[int] = None, semana: Optional[int] = None):
    """SIREA 3.3: de la semana elegida en el filtro (por defecto la activa); se recalcula al cambiarla."""
    import time
    from src.agentes import patrones
    cache = st.session_state.get("sirea_patrones")
    clave = (anio, semana)
    if forzar or not cache or cache[-1] != clave or time.time() - cache[0] > _TTL_PATRONES:
        h = patrones.Historial(int(anio), int(semana), patrones.SEMANAS_HISTORIAL) if anio and semana \
            else patrones.historial_semana_activa()
        perfiles = {r: h.perfil(r) for r in h.redes() if h.centros(r)}
        faltas = {r: h.faltantes_por_tipo(r) for r in perfiles}
        cache = (time.time(), h, perfiles, faltas, h.panorama(), clave)
        st.session_state["sirea_patrones"] = cache
    return cache[1:5]


def _chip_patron(p: Dict) -> str:
    if not p["hay_datos_suficientes"]:
        return chip("Sin datos", "mute")
    if p["suele_atrasarse"]:
        return chip("Suele atrasarse", "bad")
    if p["tendencia"] == "empeora":
        return chip("Empeora: vigilar", "warn")
    if p["tipo_que_suele_faltar"]:
        return chip(f"Suele faltar {p['tipo_que_suele_faltar']['tipo']}", "warn")
    if p["tendencia"] == "mejora":
        return chip("Mejorando", "ok")
    return chip("A tiempo", "ok")


def _tab_patrones():
    from src.agentes import patrones
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.caption("Lo calcula el SISTEMA con lo que de verdad llegó (sin IA): qué reportes manda cada centro, qué le falta esta "
               "semana y cómo viene cada red. Es información interna para priorizar: nunca va en un correo a la red.")
    forzar = c2.button("Actualizar", key="pat_actualizar", icon=":material/refresh:", use_container_width=True)
    from app_pages.filtro_periodo import filtro_periodo
    periodo = filtro_periodo("pat", ayuda="Los patrones miran las 8 semanas anteriores a la semana elegida.")
    try:
        with st.spinner("Calculando patrones…"):
            h, perfiles, faltas, pan = _historial_patrones(forzar, periodo.anio, periodo.semana)
    except Exception as e:  # noqa: BLE001
        _mostrar_error(e)
        return
    perfiles_vista = {r: p for r, p in perfiles.items() if not periodo.red or r == periodo.red}
    con_patron = [p for p in perfiles.values() if p["suele_atrasarse"]]
    mejoran = [p for p in perfiles.values() if p["tendencia"] == "mejora"]
    sin_datos = [p for p in perfiles.values() if not p["hay_datos_suficientes"]]
    kpis([
        kpi(f"Semana {pan['semana']}/{pan['anio']}", f"{pan['redes_completas']} de {pan['redes_total']}",
            "redes completas (todos sus reportes)", tono="ok" if not pan["redes_pendientes"] else "warn", ico="check"),
        kpi("Suelen atrasarse", len(con_patron), f"en las últimas {patrones.SEMANAS_HISTORIAL} semanas", tono="bad" if con_patron else "ok",
            ico="reloj"),
        kpi("Vienen mejorando", len(mejoran), "últimas 3 semanas mejor que las anteriores", tono="ok", ico="barras"),
        kpi("Sin datos suficientes", len(sin_datos), f"se necesitan {patrones.MIN_SEMANAS} semanas con datos", tono="mute", ico="info"),
    ])
    if sin_datos and len(sin_datos) == len(perfiles):
        mostrar(aviso("info", "Todavía no hay historial suficiente",
                      f"Los patrones aparecen cuando hay al menos {patrones.MIN_SEMANAS} semanas con envíos en SIREA. "
                      "Mientras tanto se muestra qué falta por tipo esta semana."))
    tendencia = {"empeora": chip("Empeora", "bad"), "mejora": chip("Mejora", "ok"), "estable": chip("Estable", "mute"),
                 "sin datos suficientes": chip("Sin datos", "mute")}
    filas = []
    for red, p in sorted(perfiles_vista.items(), key=lambda x: (not x[1]["suele_atrasarse"], -x[1]["semanas_con_problema"], x[0])):
        f = faltas.get(red) or []
        semana = chip("Completa", "ok") if not f else chip(f"{len(f)} centro(s) con pendientes", "warn")  # de la semana elegida
        tipo = p["tipo_que_suele_faltar"]
        filas.append([esc(red, 40), semana, f"{p['semanas_con_problema']} de {p['semanas_analizadas']}" if p["hay_datos_suficientes"] else "—",
                      esc(f"{tipo['tipo']} ({tipo['semanas']} de {tipo['de']})" if tipo else "—"),
                      tendencia.get(p["tendencia"], esc(p["tendencia"])),
                      "Sí" if p["suele_esperar_recordatorio"] else "No",
                      _chip_patron(p)])
    mostrar_tabla(pd.DataFrame(filas, columns=["Red", f"Semana {pan['semana']}", "Tarde o incompletas", "Lo que más falta",
                                               "Tendencia", "Espera el recordatorio", "Patrón"]),
                  crudas=(f"Semana {pan['semana']}", "Tendencia", "Patrón"))
    red = periodo.red if periodo.red in perfiles else st.selectbox("Ver el detalle de una red", options=list(perfiles), key="pat_red")
    if red:
        p = perfiles[red]
        mostrar(f'<div class="sirea-interno"><span class="sirea-interno-tit">Solo para usted · no va en el correo</span>{esc(p["texto"])}'
                + (f'<br>Semanas tarde: {esc(", ".join(p["lista_semanas_tarde"]) or "—")}' if p["lista_semanas_tarde"] else "")
                + (f'<br>Semanas sin envío: {esc(", ".join(p["lista_semanas_sin_envio"]))}' if p["lista_semanas_sin_envio"] else "")
                + (f'<br>{p["semanas_justificadas_excluidas"]} semana(s) justificada(s) no se cuentan.' if p["semanas_justificadas_excluidas"] else "")
                + "</div>")
        f = faltas.get(red) or []
        if f:
            mostrar_tabla(pd.DataFrame([[esc(x["centro"], 80), esc(", ".join(x["recibidos"]) or "—"), esc(", ".join(x["faltan"]))]
                                        for x in f], columns=["Centro", "Ya llegó", "Falta"]))
        else:
            st.success(f"Esta red tiene todos sus reportes de la semana {pan['semana']}/{pan['anio']}.")
    with st.expander("Marcar un atraso como justificado (deja de contar en los patrones)", expanded=False):
        st.caption("Para atrasos con una causa válida: feriado regional, caída del sistema, corte de internet avisado. "
                   "Queda registrado con su nombre.")
        with st.form("form_justificado", clear_on_submit=True):
            c1, c2 = st.columns(2)
            red_j = c1.selectbox("Red", options=list(perfiles))
            semana_j = c2.selectbox("Semana", options=h.previas, format_func=lambda x: f"Semana {x[1]}/{x[0]}")
            motivo = st.text_input("Motivo", max_chars=300)
            if st.form_submit_button("Marcar como justificado", type="primary", icon=":material/verified:"):
                ok, msg = patrones.marcar_justificado(red_j, semana_j[0], semana_j[1], motivo, _usuario_actual()["usuario"])
                (st.success if ok else st.error)(msg)
                if ok:
                    st.session_state.pop("sirea_patrones", None)
        just = patrones.justificados()
        if just:
            mostrar_tabla(pd.DataFrame([[j["id"], esc(j.get("red"), 30), f"{j.get('semana')}/{j.get('anio')}", esc(j.get("motivo"), 120),
                                         esc(j.get("creado_por"), 24)] for j in just],
                                       columns=["N.°", "Red", "Semana", "Motivo", "Registró"]))
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            quitar = c1.selectbox("Quitar una justificación", options=[j["id"] for j in just], format_func=lambda i: f"N.° {i}",
                                  key="just_quitar")
            if c2.button("Quitar", key="just_quitar_btn", icon=":material/undo:", use_container_width=True):
                patrones.quitar_justificado(quitar, _usuario_actual()["usuario"])
                st.session_state.pop("sirea_patrones", None)
                st.rerun()


# ------------------------------------------------------------
# Informe semanal (SIREA 3.2)
# ------------------------------------------------------------

def _tab_informe():
    from src.agentes import informe_semanal as inf
    if not inf.disponible():
        mostrar(aviso("bad", "Falta la tabla de informes", "Ejecute <b>sql/54_sirea_3_2.sql</b> en Supabase y recargue."))
        return
    st.caption("El sistema arma los datos y un texto base; la IA propone una redacción más clara y el sistema verifica que no "
               "invente cifras. Usted elige, edita y aprueba. Los viernes queda un borrador listo automáticamente.")
    from app_pages.filtro_periodo import filtro_periodo
    periodo = filtro_periodo("inf", con_red=False)
    elegida = (periodo.anio, periodo.semana)
    flash = st.session_state.pop("sirea_inf_flash", None)
    if flash:
        (st.success if flash[0] else st.error)(flash[1])
    if st.button(f"Preparar borrador de la semana {elegida[1]}/{elegida[0]}", key="inf_preparar-lila", type="primary", icon=":material/edit_note:"):
        listo = False
        with st.spinner("Armando los datos y redactando…"):
            try:
                inf.preparar(elegida[0], elegida[1], _usuario_actual()["usuario"])
                listo = True
            except Exception as e:  # noqa: BLE001
                _mostrar_error(e)
        if listo:
            st.session_state["sirea_inf_flash"] = (True, "Borrador listo: revíselo abajo.")
            st.rerun()
    todos = inf.listar(200)
    de_semana = [f for f in todos if (int(f["anio"]), int(f["semana"])) == tuple(elegida)]
    borrador = next((f for f in de_semana if f.get("estado") == "BORRADOR"), None)
    aprobado = next((f for f in de_semana if f.get("estado") == "APROBADO"), None)
    if borrador:
        _tarjeta_informe(borrador)
    elif not aprobado:
        mostrar(aviso("info", "Aún no hay informe para esta semana", "Use «Preparar borrador»."))
    if aprobado:
        _informe_aprobado(aprobado)
    m = inf.metricas()
    if m["aprobados"]:
        st.caption(f"Proporcionalidad: de {m['aprobados']} informe(s) aprobado(s), {m['con_texto_ia']} usaron la redacción de la IA "
                   f"({m['ia_sin_editar']} sin editar) y {m['con_texto_sistema']} la del sistema. Si casi siempre gana la del sistema, "
                   "la IA de este informe debería retirarse.")


def _tarjeta_informe(f: Dict):
    from src.agentes import informe_semanal as inf
    d = f.get("datos") or {}
    with st.container(key=f"prop_inf_{f['id']}"):
        mostrar(f'<div class="sirea-prop-cab"><div><div class="sirea-prop-tit">Borrador del informe · semana {f["semana"]}/{f["anio"]}</div>'
                f'<div class="sirea-prop-sub">{_fecha_corta(f.get("creado_at"))} · preparado por {esc(f.get("creado_por"), 24)}</div></div>'
                f'<div style="display:flex;gap:6px;flex-wrap:wrap">{tema_ia.chip_ia("Redacción de la IA disponible") if f.get("texto_ia") else chip("Solo texto del sistema", "mute", "info")}'
                f'{tema_ia.chip_proveedor(*(str(f.get("proveedor")).split(":", 1))) if f.get("proveedor") and ":" in str(f.get("proveedor")) else ""}</div></div>')
        mostrar(f'<div class="sirea-prop-dato"><b>Datos del sistema:</b> {d.get("redes_completas")} de {d.get("redes_total")} redes completas · '
                f'{d.get("redes_con_pendientes")} con pendientes · {len(d.get("redes_a_vigilar") or [])} a vigilar · '
                f'{d.get("recordatorios_enviados_en_la_semana")} recordatorio(s) en la semana</div>')
        if not f.get("texto_ia") and f.get("nota_ia"):
            mostrar(aviso("info", "Se usará el texto del sistema", "La redacción de la IA no está disponible: " + esc(f["nota_ia"], 300)))
        opciones = (["ia"] if f.get("texto_ia") else []) + ["sistema"]
        origen = st.radio("Redacción", options=opciones, horizontal=True, key=f"inf_origen_{f['id']}",
                          format_func=lambda o: "Propuesta de la IA (cifras verificadas)" if o == "ia" else "Texto del sistema (sin IA)")
        texto = st.text_area("Texto del informe (puede editarlo)", value=f.get("texto_ia") if origen == "ia" else f.get("texto_sistema"),
                             key=f"inf_texto_{f['id']}_{origen}", height=360, max_chars=6000)
        _boton_pdf(f, texto, borrador=True)
        c1, c2, c3 = st.columns([1.4, 2.2, 1.1], vertical_alignment="bottom")
        if c1.button("Aprobar informe", key=f"inf_ok_{f['id']}-lila", type="primary", icon=":material/check:", use_container_width=True):
            st.session_state["sirea_inf_flash"] = inf.aprobar(f["id"], texto, origen, _usuario_actual())
            st.rerun()
        motivo = c2.text_input("Motivo", key=f"inf_mot_{f['id']}", placeholder="Por qué lo descarta", label_visibility="collapsed")
        if c3.button("Descartar", key=f"inf_no_{f['id']}", icon=":material/close:", use_container_width=True):
            st.session_state["sirea_inf_flash"] = inf.descartar(f["id"], motivo, _usuario_actual())
            st.rerun()


def _boton_pdf(f: Dict, texto: Optional[str], borrador: bool):
    """PDF corporativo (logos EsSalud/OIIS, marca de agua; «BORRADOR» si aún no está aprobado)."""
    from src.agentes import informe_semanal as inf
    nombre = f"informe_sirea_semana_{f['semana']}_{f['anio']}{'_BORRADOR' if borrador else ''}.pdf"
    try:
        datos_pdf = inf.a_pdf(f, texto=texto, borrador=borrador)
    except Exception as e:  # noqa: BLE001
        st.caption("No se pudo generar el PDF (¿falta reportlab? revise requirements.txt): " + esc(str(e), 120))
        return
    st.download_button("Descargar borrador en PDF" if borrador else "Descargar PDF", data=datos_pdf, file_name=nombre,
                       mime="application/pdf", key=f"inf_pdf_{f['id']}_{'b' if borrador else 'a'}",
                       icon=":material/picture_as_pdf:", use_container_width=not borrador,
                       help="Formato institucional con la marca de agua de la OIIS. "
                            + ("Sale marcado como BORRADOR hasta que lo apruebe." if borrador else ""))


def _informe_aprobado(f: Dict):
    from src.agentes import informe_semanal as inf
    with st.container(border=True):
        mostrar(f'<div class="sirea-prop-cab"><div class="sirea-prop-tit">Informe aprobado · semana {f["semana"]}/{f["anio"]}</div>'
                f'{chip("Validado por una persona", "ok", "check")}</div>'
                f'<div class="sirea-preview">{_multilinea(f.get("texto_final"))}</div>'
                f'<div class="sirea-prop-sub" style="margin-top:6px">{esc(inf.leyenda(f))}</div>')
        c0, c1, c2 = st.columns(3)
        with c0:
            _boton_pdf(f, f.get("texto_final"), borrador=False)
        try:
            c1.download_button("Descargar en Word", data=inf.a_word(f), file_name=f"informe_sirea_semana_{f['semana']}_{f['anio']}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               key=f"inf_docx_{f['id']}", icon=":material/description:", use_container_width=True)
        except Exception:
            c1.caption("Para descargar en Word instale python-docx (requirements.txt).")
        c2.download_button("Descargar texto", data=(str(f.get("texto_final")) + "\n\n" + inf.leyenda(f)).encode("utf-8"),
                           file_name=f"informe_sirea_semana_{f['semana']}_{f['anio']}.txt", mime="text/plain",
                           key=f"inf_txt_{f['id']}", icon=":material/download:", use_container_width=True)
        with st.form(f"inf_envio_{f['id']}", clear_on_submit=False, border=False):
            c1, c2 = st.columns([3, 1.2], vertical_alignment="bottom")
            dest = c1.text_input("Enviar por correo a (por ejemplo, la Jefatura de la OIIS)", value=str(Config.ADMIN_EMAIL or ""))
            if c2.form_submit_button("Enviar", icon=":material/send:", use_container_width=True):
                ok, msg = inf.enviar(f, dest, _usuario_actual())
                (st.success if ok else st.error)("Informe enviado." if ok else msg)

# ------------------------------------------------------------
# Corridas
# ------------------------------------------------------------

def _tab_corridas():
    from src.agentes import agente_operativo as ag
    from src.agentes.skills import cargar_todas
    no_opera = _aviso_no_operativo()
    skills = list(cargar_todas().values())
    st.caption("Una corrida revisa los casos, decide con la skill y deja propuestas en la Bandeja. No ejecuta nada por sí sola.")
    cols = st.columns(len(skills) or 1)
    for col, sk in zip(cols, skills):
        with col:
            if st.button(f"Correr «{sk.nombre}» ahora", key=f"run_{sk.id}-lila", type="primary", use_container_width=True,
                         icon=":material/play_arrow:", disabled=no_opera):
                with st.spinner("El agente está revisando los casos…"):
                    try:
                        r = ag.ejecutar_corrida(sk.id, disparo="manual", usuario=_usuario_actual()["usuario"])
                    except Exception as e:  # noqa: BLE001
                        _mostrar_error(e)
                        r = None
                if r:
                    if r.get("estado") == "BLOQUEADA":
                        st.warning("Corrida bloqueada: " + str(r.get("motivo")))
                    else:
                        st.success(f"{r['resumen']}. Revise la Bandeja.")
    corr = ag.corridas(30)
    if not corr:
        st.info("Todavía no hay corridas.")
        return
    nombres = {k: v.nombre for k, v in cargar_todas().items()}
    filas = [[c["id"], _fecha_corta(c.get("inicio")), esc(nombres.get(c.get("skill"), c.get("skill")), 40), esc(c.get("disparo")),
              chip(esc(c.get("estado")), {"COMPLETADA": "ok", "PARCIAL": "warn", "FALLIDA": "bad", "BLOQUEADA": "bad"}.get(c.get("estado"), "info")),
              c.get("n_casos"), c.get("n_propuestas"), c.get("n_sin_accion"), c.get("n_descartadas"),
              esc(c.get("proveedor") or ("—" if c.get("estado") == "BLOQUEADA" else "reglas"), 40)] for c in corr]
    mostrar_tabla(pd.DataFrame(filas, columns=["N.°", "Inicio", "Skill", "Disparo", "Estado", "Casos", "Propuestas",
                                               "Sin acción", "Descartadas", "Proveedor"]),
                  crudas=("Estado",), derecha=("Casos", "Propuestas", "Sin acción", "Descartadas"))
    por_id = {c["id"]: c for c in corr}
    elegida = st.selectbox("Ver qué hizo el agente en la corrida", options=[c["id"] for c in corr],
                           format_func=lambda i: f"N.° {i} · {nombres.get(por_id[i].get('skill'), '')} · {por_id[i].get('estado')}",
                           key="traza_corrida")
    c = por_id.get(elegida) or {}
    if c.get("error"):
        mostrar(aviso("warn" if c.get("estado") == "BLOQUEADA" else "bad",
                      "Corrida bloqueada" if c.get("estado") == "BLOQUEADA" else "Errores en la corrida", esc(c["error"], 600)))
    else:
        _mostrar_traza(ag.traza(elegida))


def _mostrar_traza(pasos: List[Dict]):
    if not pasos:
        st.caption("Sin pasos registrados.")
        return
    por_caso = defaultdict(list)
    for t in pasos:
        por_caso[t.get("caso") or "(general)"].append(t)
    etiqueta = {"CASO": "Vio", "HERRAMIENTA": "Consultó", "PROPUESTA": "Propuso", "DESCARTADA": "Descartado por las reglas",
                "SIN_ACCION": "Decidió no actuar", "REGLA": "Sin IA (reglas)", "ERROR": "Error"}
    for caso, lista in por_caso.items():
        with st.expander(str(caso), expanded=False):
            for t in lista:
                d = t.get("detalle") or {}
                if t["tipo"] == "CASO":
                    txt = ", ".join(f"{k}: {v}" for k, v in d.items() if k in ("porcentaje", "faltantes", "horas_al_corte", "motivo",
                                                                              "texto_de_la_red", "memoria", "solicitud_password_abierta"))
                elif t["tipo"] == "HERRAMIENTA":
                    txt = str(d.get("herramienta"))
                elif t["tipo"] == "PROPUESTA":
                    txt = f"{d.get('tipo')} — {d.get('justificacion')}"
                elif t["tipo"] == "DESCARTADA":
                    txt = f"{d.get('tipo')}: {d.get('motivo')}"
                elif t["tipo"] == "SIN_ACCION":
                    txt = str(d.get("justificacion"))
                else:
                    txt = str(d.get("motivo") or d.get("error") or d)
                mostrar(f'<div class="sirea-traza"><b>{esc(etiqueta.get(t["tipo"], t["tipo"]))}:</b> {esc(txt, 700)}</div>')


# ------------------------------------------------------------
# Skills
# ------------------------------------------------------------

def _tab_skills():
    from src.agentes import evals
    from src.agentes.skills import cargar_todas, errores_de_carga
    for err in errores_de_carga():
        mostrar(aviso("bad", "Skill con errores (no se carga)", esc(err)))
    st.caption("Una skill es un procedimiento escrito y aprobado por la OIIS que el agente sigue al pie de la letra. "
               "Si su texto cambia, cambia su huella y debe volver a pasar las evaluaciones antes de operar.")
    for sk in cargar_todas().values():
        ok, motivo = evals.habilitada(sk)
        with st.container(border=True):
            aprendida = sk.metadatos.get("origen") == "aprendida"
            mostrar(f'<div class="sirea-prop-cab"><div><div class="sirea-prop-tit">{esc(sk.nombre)}</div>'
                    f'<div class="sirea-prop-sub">versión {esc(sk.version)} · huella #{esc(sk.huella_corta)} · '
                    f'aprobada por {esc(sk.aprobada_por)} ({esc(sk.fecha_aprobacion)})</div></div>'
                    f'<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">{tema_ia.semaforo(sk.nivel)}'
                    + (tema_ia.chip_ia("Versión aprendida") if aprendida else "")
                    + f'{chip("Habilitada" if ok else "Bloqueada", "ok" if ok else "bad", "check" if ok else "candado")}</div></div>')
            mostrar(f'<div class="sirea-prop-dato"><b>Puede proponer:</b> {esc(", ".join(CORTO.get(a, a) for a in sk.acciones_permitidas))}</div>'
                    f'<div class="sirea-prop-dato"><b>Puede consultar:</b> {esc(", ".join(sk.herramientas) or "—")}</div>'
                    f'<div class="sirea-prop-dato"><b>Aprueba sus propuestas:</b> {esc(sk.quien_aprueba)} · '
                    f'<b>Casos por corrida:</b> {sk.max_casos} · <b>Cuándo corre:</b> {esc(sk.disparador)}</div>'
                    f'<div class="sirea-prop-dato"><b>Evaluación:</b> {esc(motivo)}</div>')
            with st.expander("Leer el procedimiento completo", expanded=False):
                st.markdown(sk.cuerpo)
            _bloque_mejora(sk)


def _bloque_mejora(sk):
    """Aprender de los rechazos: propuesta de ajustes, decisión del SUPER_ADMIN, historial de versiones."""
    from src.agentes import mejora
    if not mejora.disponible():
        st.caption("Aprender de los rechazos: falta ejecutar sql/53_skill_versiones.sql.")
        return
    actor = _usuario_actual()
    sup = actor["rol"] == "SUPER_ADMIN"
    pend = mejora.propuesta_pendiente(sk.id)
    flash = st.session_state.pop(f"sirea_mejora_flash_{sk.id}", None)
    if flash:
        (st.success if flash[0] else st.warning)(flash[1])
    if pend:
        ev = pend.get("evidencia") or {}
        items = "".join(f"<li><b>{esc(a.get('regla'))}</b><br><span style='color:#566573'>{esc(a.get('por_que'))}</span></li>"
                        for a in pend.get("ajustes") or [])
        with st.container(key=f"prop_mejora_{pend['id']}"):
            mostrar(f'<div class="sirea-prop-cab"><div class="sirea-prop-tit">Mejora propuesta: versión {esc(pend["version"])}</div>'
                    f'{tema_ia.chip_ia("Propuesta de la IA")}</div>'
                    f'<div class="sirea-prop-just">{esc(ev.get("diagnostico") or "")}</div>'
                    f'<div class="sirea-prop-dato"><b>Se agregaría al procedimiento:</b></div><ul class="sirea-pend-lista">{items}</ul>'
                    f'<div class="sirea-prop-sub">Basada en {len(ev.get("rechazos") or [])} rechazo(s). El resto del procedimiento, '
                    f'las acciones permitidas y quién aprueba no cambian.</div>')
            if sup:
                c1, c2, c3 = st.columns([1.3, 2.2, 1], vertical_alignment="bottom")
                if c1.button("Aprobar mejora", key=f"mej_ok_{pend['id']}-lila", type="primary", icon=":material/check:",
                             use_container_width=True):
                    st.session_state[f"sirea_mejora_flash_{sk.id}"] = mejora.aprobar(pend["id"], actor)
                    st.rerun()
                motivo = c2.text_input("Motivo", key=f"mej_mot_{pend['id']}", placeholder="Por qué no",
                                       label_visibility="collapsed")
                if c3.button("Rechazar", key=f"mej_no_{pend['id']}", icon=":material/close:", use_container_width=True):
                    st.session_state[f"sirea_mejora_flash_{sk.id}"] = mejora.rechazar(pend["id"], actor, motivo)
                    st.rerun()
            else:
                st.caption("La decide un SUPER_ADMIN.")
    else:
        n = len(mejora.rechazos_nuevos(sk))
        c1, c2 = st.columns([3, 1.4], vertical_alignment="center")
        c1.caption(f"Aprender de los rechazos: {n} rechazo(s) nuevo(s) con motivo; con {mejora.MIN_RECHAZOS} o más el agente "
                   "propone ajustes al procedimiento (los lunes, o ahora).")
        if sup and c2.button("Proponer mejoras ahora", key=f"mej_run_{sk.id}", icon=":material/auto_fix_high:",
                             use_container_width=True, disabled=n < mejora.MIN_RECHAZOS or not estado.esta_operativo(OPERATIVO)):
            with st.spinner("El agente está leyendo los rechazos…"):
                try:
                    r = mejora.proponer(sk.id, actor["usuario"])
                except Exception as e:  # noqa: BLE001
                    _mostrar_error(e)
                    r = None
            if r:
                st.session_state[f"sirea_mejora_flash_{sk.id}"] = (r.get("estado") == "PROPUESTA", {
                    "PROPUESTA": "Mejora propuesta: revísela aquí mismo."}.get(r.get("estado"), r.get("motivo") or r.get("estado")))
                st.rerun()
    vers = mejora.versiones(sk.id, 10)
    if vers or sk.metadatos.get("origen") == "aprendida":
        with st.expander("Versiones de esta skill", expanded=False):
            if vers:
                filas = [[esc(v["version"]), chip(esc(v["estado"]), {"APROBADA": "ok", "PROPUESTA": "ia", "RECHAZADA": "mute",
                                                                   "REEMPLAZADA": "mute"}.get(v["estado"], "info")),
                          _fecha_corta(v.get("creada_at")), esc(v.get("decidida_por") or "—", 24),
                          esc(v.get("motivo_decision") or "", 80)] for v in vers]
                mostrar_tabla(pd.DataFrame(filas, columns=["Versión", "Estado", "Propuesta", "Decidió", "Nota"]), crudas=("Estado",))
            if sk.metadatos.get("origen") == "aprendida":
                actual = next((v for v in vers if str(v["id"]) == sk.metadatos.get("version_id")), None)
                if actual:
                    st.download_button("Descargar el texto vigente (.md) para guardarlo en el repositorio",
                                       data=actual["texto"].encode("utf-8"), file_name=f"{sk.id}.md", mime="text/markdown",
                                       key=f"mej_dl_{sk.id}", icon=":material/download:")
                if sup and st.button(f"Volver a la versión del repositorio (v{sk.metadatos.get('version_repositorio')})",
                                     key=f"mej_repo_{sk.id}", icon=":material/undo:"):
                    st.session_state[f"sirea_mejora_flash_{sk.id}"] = mejora.volver_al_repositorio(sk.id, actor)
                    st.rerun()


# ------------------------------------------------------------
# Evaluaciones
# ------------------------------------------------------------

def _tab_evaluaciones():
    from src.agentes import evals
    from src.agentes.skills import cargar_todas
    skills = cargar_todas()
    if not skills:
        st.info("No hay skills cargadas.")
        return
    st.caption("Casos ficticios que una persona de la OIIS resolvió a mano. Se corren con la IA y con reglas simples (sin IA): "
               "la diferencia muestra cuánto aporta la IA. Una skill solo opera si su versión exacta alcanza su umbral con IA.")
    sid = st.selectbox("Skill", options=list(skills), format_func=lambda k: skills[k].nombre, key="eval_skill")
    sk = skills[sid]
    if _es_super_admin():
        if st.button("Correr las evaluaciones (sin IA y con IA)", key="eval_correr-lila", type="primary",
                     icon=":material/science:", disabled=not Config.tiene_ia()):
            with st.spinner("Corriendo los casos… (con IA puede tardar un minuto)"):
                try:
                    evals.correr_ambos(sid, _usuario_actual()["usuario"], pausa_s=0.4)
                except Exception as e:  # noqa: BLE001
                    _mostrar_error(e)
            st.rerun()
    else:
        st.caption("Solo un SUPER_ADMIN puede correr las evaluaciones.")

    u_ia, u_sin = evals.ultima(sk, "ia"), evals.ultima(sk, "sin_ia")
    ok, motivo = evals.habilitada(sk)
    kpis([
        kpi("Con IA", f"{u_ia['aprobados']}/{u_ia['total']}" if u_ia else "—",
            f"{_pct(u_ia['puntaje'])} · {esc(u_ia.get('proveedor') or '')}" if u_ia else "Sin evaluar en esta versión", tono="ia", ico="ia"),
        kpi("Sin IA (reglas)", f"{u_sin['aprobados']}/{u_sin['total']}" if u_sin else "—",
            _pct(u_sin["puntaje"]) if u_sin else "Sin evaluar en esta versión", tono="mute", ico="info"),
        kpi("Compuerta", "Habilitada" if ok else "Bloqueada", f"Umbral {round(sk.umbral_eval * 100)} % · versión {sk.version}",
            tono="ok" if ok else "bad", ico="check" if ok else "candado"),
    ])
    casos = evals.casos(sid)
    det_ia = {d["id"]: d for d in (u_ia or {}).get("detalle") or []}
    det_sin = {d["id"]: d for d in (u_sin or {}).get("detalle") or []}

    def _celda(d):
        if not d:
            return "—"
        clase = "sirea-eval-ok" if d.get("aprobado") else "sirea-eval-no"
        return (f'<span class="{clase}">{"✓" if d.get("aprobado") else "✗"}</span> '
                f'{esc(" + ".join(CORTO.get(t, t) for t in d.get("obtenido") or []) or "—", 80)}')

    filas = []
    for c in casos:
        esp = c.get("espera") or {}
        filas.append([esc(c["id"]), esc(c.get("titulo")), esc(" o ".join(CORTO.get(t, t) for t in esp.get("alguno_de") or [])),
                      _celda(det_sin.get(c["id"])), _celda(det_ia.get(c["id"])), esc(c.get("por_que") or "", 140)])
    mostrar_tabla(pd.DataFrame(filas, columns=["Caso", "Situación", "Se espera", "Sin IA", "Con IA", "Por qué importa"]),
                  crudas=("Sin IA", "Con IA"))
    fallidos = [d for d in det_ia.values() if not d.get("aprobado")]
    if fallidos:
        with st.expander(f"Casos que la IA no resolvió ({len(fallidos)})", expanded=False):
            for d in fallidos:
                st.markdown(f"**{esc(d['id'])} · {esc(d.get('titulo'))}** — {esc(d.get('motivo'))}", unsafe_allow_html=True)
                if d.get("razonamiento"):
                    st.caption("Razonamiento: " + str(d["razonamiento"]))
                for x in d.get("descartadas") or []:
                    st.caption("Descartada por las reglas: " + str(x))
    hist = evals.historial(sid, 20)
    if hist:
        with st.expander("Historial de evaluaciones", expanded=False):
            filas = [[_fecha_corta(h.get("fecha")), esc(h.get("skill_version")), esc(str(h.get("skill_hash") or "")[:10]),
                      "Con IA" if h.get("modo") == "ia" else "Sin IA", f"{h.get('aprobados')}/{h.get('total')}",
                      _pct(h.get("puntaje")), esc(h.get("proveedor") or "—", 40), esc(h.get("usuario"), 24)] for h in hist]
            mostrar_tabla(pd.DataFrame(filas, columns=["Fecha", "Versión", "Huella", "Modo", "Aciertos", "Puntaje", "Proveedor", "Usuario"]))


# ------------------------------------------------------------
# Memoria
# ------------------------------------------------------------

def _tab_memoria():
    from src.agentes import memoria
    st.caption("Datos breves sobre una red que el agente lee antes de decidir (por ejemplo, «avisó que envía los jueves por "
               "falta de internet»). Vencen solos. No escriba datos personales.")
    if not memoria.disponible():
        mostrar(aviso("bad", "Falta la tabla de memoria", "Ejecute sql/52_agente_operativo.sql en Supabase."))
        return
    notas = memoria.vigentes()
    if notas:
        filas = [[n["id"], esc(n.get("red"), 30), esc(n.get("nota"), 300), "Agente (aprobada)" if n.get("fuente") == "agente" else "Persona",
                  esc(n.get("creada_por"), 24), str(n.get("vigente_hasta") or "—")[:10]] for n in notas]
        mostrar_tabla(pd.DataFrame(filas, columns=["N.°", "Red", "Nota", "Origen", "Registró", "Vigente hasta"]))
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        quitar = c1.selectbox("Quitar una nota", options=[n["id"] for n in notas],
                              format_func=lambda i: f"N.° {i}", key="mem_quitar")
        if c2.button("Quitar", key="mem_quitar_btn", icon=":material/delete:", use_container_width=True):
            memoria.desactivar(quitar, _usuario_actual()["usuario"])
            st.rerun()
    else:
        st.info("No hay notas vigentes.")
    with st.form("form_memoria", clear_on_submit=True):
        try:
            from src.agentes.herramientas import listar_redes
            redes = listar_redes()
        except Exception:
            redes = []
        red = st.selectbox("Red", options=redes) if redes else st.text_input("Red")
        nota = st.text_area("Nota", max_chars=300, height=70)
        dias = st.number_input("Vigencia (días)", min_value=7, max_value=180, value=30)
        if st.form_submit_button("Agregar nota", type="primary", icon=":material/bookmark_add:"):
            ok = memoria.agregar(red, nota, fuente="humano", creada_por=_usuario_actual()["usuario"], vigencia_dias=int(dias))
            (st.success if ok else st.error)("Nota agregada." if ok else "No se agregó: revise que no tenga datos personales y que tenga al menos 5 caracteres.")


# ------------------------------------------------------------
# Estado
# ------------------------------------------------------------

def _tab_estado(res: estado.ResumenEstado):
    rol = _usuario_actual()["rol"]
    c1, c2 = st.columns([3.2, 1.2], vertical_alignment="center")
    with c1:
        mostrar(aviso("info", "Botón de detención",
                      "Cualquier administrador puede detener TODA la IA de inmediato. Reactivarla exige un SUPER_ADMIN y queda registrado."))
    with c2:
        if res.global_ == estado.EN_REVISION:
            st.button("La IA está detenida", key="btn_panico", disabled=True, use_container_width=True)
        elif st.button("Detener la IA", key="btn_panico-rojo", type="primary", use_container_width=True, icon=":material/pause_circle:"):
            ok, msg = estado.boton_de_panico(rol, f"Detención de emergencia desde el panel por {_usuario_actual()['usuario']}")
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    ca, cb = st.columns(2)
    with ca:
        if _es_super_admin():
            pendientes = [a for a in estado.AGENTES if res.efectivo[a] != estado.ACTIVO_HITL]
            if st.button("Activar la IA" + (f" ({len(pendientes)} pendientes)" if pendientes else " · ya activa"),
                         key="btn_activar_todos-lila", type="primary", use_container_width=True, icon=":material/play_circle:",
                         disabled=not pendientes):
                mensajes = []
                if res.global_ != estado.ACTIVO_HITL:
                    mensajes.append(("General",) + estado.cambiar_estado(None, estado.ACTIVO_HITL, rol, "Activación desde el panel"))
                for a in estado.AGENTES:
                    if estado.estado_individual(a) != estado.ACTIVO_HITL:
                        mensajes.append((estado.CATALOGO[a].nombre,) + estado.cambiar_estado(a, estado.ACTIVO_HITL, rol, "Activación desde el panel"))
                st.session_state["sirea_activar_msgs"] = mensajes
                st.rerun()
        else:
            st.caption("Solo un SUPER_ADMIN puede activar la IA.")
    with cb:
        if st.button("Probar los proveedores de IA", key="btn_probar_prov", use_container_width=True, icon=":material/network_check:"):
            from src.agentes import proveedores
            with st.spinner("Consultando a cada proveedor…"):
                st.session_state["sirea_diag_prov"] = proveedores.diagnostico()
    for nombre, ok, msg in st.session_state.pop("sirea_activar_msgs", []) or []:
        (st.success if ok else st.warning)(f"{nombre}: {msg}")
    for d in st.session_state.get("sirea_diag_prov") or []:
        mostrar(aviso("ok" if d["ok"] else "bad", f"{d['proveedor'].capitalize()} · {esc(d.get('modelo') or '—')} · {d.get('ms', 0)} ms",
                      esc(d["mensaje"], 400)))


    with st.expander("Administrar el ciclo de vida (SUPER_ADMIN)", expanded=False):
        if not _es_super_admin():
            st.info("Solo un SUPER_ADMIN puede activar, inactivar o desactivar. Cualquier administrador puede usar el botón de detención.")
        else:
            with st.form("form_ciclo_vida", border=False):
                c1, c2 = st.columns(2)
                objetivo = c1.selectbox("Qué cambiar", options=[None] + estado.AGENTES,
                                        format_func=lambda k: "Estado general (toda la IA)" if k is None else estado.CATALOGO[k].nombre)
                nuevo = c2.selectbox("Nuevo estado", options=estado.ESTADOS,
                                     format_func=lambda e: f"{estado.ETIQUETA_UI[e]} — {estado.DESCRIPCION[e]}")
                just = st.text_input("Justificación (obligatoria para desactivar o reactivar)", max_chars=300)
                if st.form_submit_button("Aplicar cambio", type="primary", icon=":material/check:"):
                    ok, msg = estado.cambiar_estado(objetivo, nuevo, rol, just)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
            st.caption("La IA nace INACTIVA; activarla es una decisión explícita que queda en la auditoría. "
                       "El Agente Operativo, además, exige al menos una skill que haya pasado sus evaluaciones.")


# ------------------------------------------------------------
# Auditoría
# ------------------------------------------------------------

def _tab_auditoria():
    """Historial de IA: TODO lo que la IA hizo, en palabras simples, con filtros y descarga."""
    from datetime import timedelta, timezone
    st.caption("Cada consulta al asistente, cada propuesta o borrador, cada aprobación, rechazo y envío, cada bloqueo de un "
               "control y cada cambio de estado de la IA. Es de solo inserción: nadie puede modificarlo ni borrarlo.")
    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.5, 1.6])
    periodo = c1.selectbox("Período", options=[1, 7, 30, 90], index=1, key="aud_periodo",
                           format_func=lambda d: {1: "Hoy (24 h)", 7: "Últimos 7 días", 30: "Últimos 30 días", 90: "Últimos 90 días"}[d])
    funciones = ["Todas", "Quipu (asistente de consulta)", "Agente Operativo", "Informe semanal", "Mejora de procedimientos", "Estado de la IA"]
    funcion = c2.selectbox("Función", options=funciones, key="aud_funcion")
    evento = c3.selectbox("Qué pasó", options=[None] + list(auditoria.EVENTO_SIMPLE), key="aud_evento",
                          format_func=lambda e: "Todo" if e is None else auditoria.EVENTO_SIMPLE[e])
    buscar = c4.text_input("Buscar (red, usuario, texto)", key="aud_buscar", placeholder="Ej.: ALMENARA")
    desde = (datetime.now(timezone.utc) - timedelta(days=int(periodo))).isoformat()
    registros = auditoria.obtener_registros(limite=20000, evento=evento, desde=desde)
    if funcion != "Todas":
        registros = [r for r in registros if auditoria.funcion_de(r) == funcion]
    if buscar.strip():
        b = buscar.strip().lower()
        registros = [r for r in registros if b in " ".join(str(r.get(k) or "") for k in ("usuario", "entrada", "salida", "referencia")).lower()]
    cuenta = defaultdict(int)
    for r in registros:
        cuenta[r.get("evento")] += 1
    kpis([
        kpi("Registros", len(registros), "en el período y filtro elegidos", tono="info", ico="barras"),
        kpi("Consultas", cuenta[auditoria.EVENTO_CONSULTA], "preguntas respondidas", tono="ia", ico="ia"),
        kpi("Propuestas y borradores", cuenta[auditoria.EVENTO_BORRADOR], "esperaron una decisión humana", tono="ia", ico="ia"),
        kpi("Aprobadas / rechazadas", f"{cuenta[auditoria.EVENTO_APROBACION]} / {cuenta[auditoria.EVENTO_RECHAZO]}",
            f"envíos tras aprobar: {cuenta[auditoria.EVENTO_ENVIO]}", tono="ok", ico="check"),
        kpi("Bloqueos de control", cuenta[auditoria.EVENTO_BLOQUEO], f"errores técnicos: {cuenta[auditoria.EVENTO_ERROR]}",
            tono="warn" if cuenta[auditoria.EVENTO_BLOQUEO] else "mute", ico="escudo"),
    ])
    if not registros:
        st.info("Sin registros para ese filtro.")
        return
    tono = {"APROBACION": "ok", "RECHAZO": "bad", "BLOQUEO_GUARDRAIL": "warn", "ERROR": "bad", "CAMBIO_ESTADO": "info", "ENVIO": "ok"}
    mostrados = registros[:300]
    filas = [[_fecha_corta(r.get("fecha")), esc(r.get("usuario"), 24), esc(auditoria.funcion_de(r), 30),
              chip(esc(auditoria.EVENTO_SIMPLE.get(r.get("evento"), r.get("evento"))), tono.get(r.get("evento"), "ia")),
              esc((r.get("entrada") or "")[:140], 140), esc((r.get("salida") or "")[:140], 140),
              esc(r.get("modelo") or "—", 34), esc(r.get("referencia") or "", 16)] for r in mostrados]
    mostrar_tabla(pd.DataFrame(filas, columns=["Fecha", "Quién", "Función", "Qué pasó", "Pidió / entrada", "Respondió / salida",
                                               "Proveedor:modelo", "Ref."]), crudas=("Qué pasó",))
    if len(registros) > len(mostrados):
        st.caption(f"Se muestran los {len(mostrados)} más recientes de {len(registros)}; la descarga incluye todos.")
    from utils.tema_admin import descargas
    df = pd.DataFrame([{"fecha": r.get("fecha"), "usuario": r.get("usuario"), "rol": r.get("rol"), "funcion": auditoria.funcion_de(r),
                        "evento": r.get("evento"), "que_paso": auditoria.EVENTO_SIMPLE.get(r.get("evento"), r.get("evento")),
                        "proveedor_modelo": r.get("modelo"), "referencia": r.get("referencia"), "aprobado_por": r.get("aprobado_por"),
                        "herramientas": ", ".join(r.get("herramientas") or []) if isinstance(r.get("herramientas"), list) else r.get("herramientas"),
                        "control": r.get("guardrail_categoria"), "entrada": r.get("entrada"), "salida": r.get("salida"),
                        "duracion_ms": r.get("duracion_ms")} for r in registros])
    descargas(df, f"historial_ia_{periodo}_dias", hoja="Historial de IA", key="aud_dl")
    with st.expander("Ver un registro completo", expanded=False):
        por_id = {r.get("id"): r for r in mostrados if r.get("id") is not None}
        if por_id:
            rid = st.selectbox("Registro", options=list(por_id), key="aud_registro",
                               format_func=lambda i: f"{_fecha_corta(por_id[i].get('fecha'))} · {auditoria.funcion_de(por_id[i])} · "
                                                     f"{auditoria.EVENTO_SIMPLE.get(por_id[i].get('evento'), por_id[i].get('evento'))}")
            r = por_id[rid]
            mostrar(f'<div class="sirea-preview"><b>Entrada:</b><br>{_multilinea(r.get("entrada") or "—")}<br><br><b>Salida:</b><br>'
                    f'{_multilinea(r.get("salida") or "—")}</div>')
            extra = [f"Herramientas: {', '.join(r.get('herramientas') or [])}" if r.get("herramientas") else "",
                     f"Control: {r.get('guardrail_categoria')} ({r.get('guardrail_motivo')})" if r.get("guardrail_categoria") else "",
                     f"Duración: {r.get('duracion_ms')} ms" if r.get("duracion_ms") else ""]
            st.caption(" · ".join(x for x in extra if x))
    st.caption("Registro de solo inserción: la base de datos rechaza modificar o borrar filas (sql/50_auditoria_agentes_ia.sql).")
