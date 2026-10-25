# pages/admin_observaciones.py
"""
Observaciones de los envíos.

Aquí llegan, sin avisos por correo ni carteles insistentes:
  · el sustento (texto opcional) que escribió quien envió,
  · los envíos observados y los duplicados,
  · los reemplazos de archivos ya enviados.
Todos los roles del panel pueden verlas y marcarlas como revisadas. El menú muestra solo un contador discreto.
"""

import time
from datetime import date

import pandas as pd
import streamlit as st

from src.observaciones import get_observaciones
from utils.tema import mostrar, aviso, chip
from utils.tema_admin import esc, tabla_df, panel_cab, descargas
from app_pages.admin_helpers import actor_actual, formatear_fecha_columna

_TONO_MOTIVO = {"OBSERVADO": "warn", "DUPLICADO": "dup", "REEMPLAZO": "info", "SUSTENTO": "ok", "FALLA": "bad"}
_NOMBRE_MOTIVO = {"SUSTENTO": "Comentario", "OBSERVADO": "Observado", "DUPLICADO": "Duplicado", "REEMPLAZO": "Reemplazo", "FALLA": "Falla técnica"}
_VISTA_CORTA = 110
_TTL_CONTADOR = 20  # segundos: el menú no consulta la base en cada interacción


def contadores_observaciones() -> dict:
    """{'normales': comentarios + envíos por revisar, 'fallas': fallas técnicas} sin revisar (memoria de 20 s)."""
    ahora = time.time()
    previo = st.session_state.get("_obs_contador")
    if previo and ahora - previo[0] < _TTL_CONTADOR:
        return previo[1]
    n = get_observaciones().contadores()
    st.session_state["_obs_contador"] = (ahora, n)
    return n


def pendientes_observaciones() -> int:
    return contadores_observaciones()["normales"]


def _invalidar_contador():
    st.session_state.pop("_obs_contador", None)


def _fecha_a_date(valor):
    try:
        return pd.to_datetime(valor, utc=True).tz_convert("America/Lima").date()
    except Exception:
        return None


def _corto(texto: str) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= _VISTA_CORTA else t[:_VISTA_CORTA].rstrip() + "…"


def _tabla(filas):
    vista = pd.DataFrame({
        "Fecha y hora": [formatear_fecha_columna(f.get("fecha_creacion", "")) for f in filas],
        "Enviado por": [f"{f.get('remitente') or ''} · {f.get('correo') or ''}".strip(" ·") for f in filas],
        "Red": [str(f.get("red") or "") for f in filas],
        "Código": [str(f.get("codigo_seguimiento") or "") for f in filas],
        "Semana": [f"{f.get('semana')}/{f.get('anio')}" for f in filas],
        "Motivo": [chip(_NOMBRE_MOTIVO.get(f.get("motivo"), str(f.get("motivo") or "")), _TONO_MOTIVO.get(f.get("motivo"), "info")) for f in filas],
        "Sustento": [_corto(f.get("texto") or f.get("detalle") or "") for f in filas],
    })
    mostrar(tabla_df(vista, crudas=("Motivo",)))
    return vista


def _detalle(filas, clave):
    """Texto completo de una observación elegida (todo escapado)."""
    etiquetas = {
        f"{f.get('codigo_seguimiento') or f.get('id')} · {f.get('red') or ''} · {f.get('motivo') or ''}": f
        for f in filas
    }
    elegido = st.selectbox("Ver observación completa", ["—"] + list(etiquetas), key=f"obs_ver_{clave}")
    if elegido == "—":
        return
    f = etiquetas[elegido]
    partes = []
    if f.get("texto"):
        partes.append(f"<strong>Lo que escribió quien envió:</strong><br>{esc(f['texto']).replace(chr(10), '<br>')}")
    if f.get("detalle"):
        partes.append(f"<strong>Detalle del sistema:</strong><br>{esc(f['detalle']).replace(chr(10), '<br>')}")
    if f.get("revisada"):
        partes.append(f"<em>Revisada por {esc(f.get('revisada_por') or '')} · {esc(formatear_fecha_columna(f.get('fecha_revision') or ''))}</em>")
    mostrar(aviso("info", f"Envío {esc(f.get('codigo_seguimiento') or '')}", "<br><br>".join(partes) or "Sin texto."))


def _filtros(clave):
    obs = get_observaciones()
    c1, c2, c3 = st.columns([1.4, 0.8, 1.6])
    with c1:
        red = st.text_input("Red (parte del nombre)", key=f"obs_red_{clave}", placeholder="Todas")
    with c2:
        semana = st.number_input("Semana", min_value=0, max_value=60, value=0, step=1, key=f"obs_sem_{clave}",
                                 help="0 = todas")
    with c3:
        rango = st.date_input("Fechas", value=(), key=f"obs_fec_{clave}", format="DD/MM/YYYY")
    return red.strip().lower(), int(semana), rango


def _aplicar_filtros(filas, red, semana, rango):
    res = []
    d1 = d2 = None
    if isinstance(rango, (tuple, list)):
        if len(rango) >= 1:
            d1 = rango[0]
        if len(rango) == 2:
            d2 = rango[1]
    elif isinstance(rango, date):
        d1 = rango
    for f in filas:
        if red and red not in str(f.get("red") or "").lower():
            continue
        if semana and int(f.get("semana") or 0) != semana:
            continue
        d = _fecha_a_date(f.get("fecha_creacion"))
        if d1 and d and d < d1:
            continue
        if d2 and d and d > d2:
            continue
        res.append(f)
    return res


def _exportar(filas, nombre, clave):
    df = pd.DataFrame({
        "Fecha y hora": [formatear_fecha_columna(f.get("fecha_creacion", "")) for f in filas],
        "Enviado por (nombre)": [f.get("remitente") or "" for f in filas],
        "Correo": [f.get("correo") or "" for f in filas],
        "Red": [f.get("red") or "" for f in filas],
        "Código de seguimiento": [f.get("codigo_seguimiento") or "" for f in filas],
        "Semana": [f.get("semana") for f in filas],
        "Año": [f.get("anio") for f in filas],
        "Categoría": [{"COMENTARIO": "Comentario de la red", "REVISION": "Envío por revisar", "FALLA": "Falla técnica"}[get_observaciones().categoria_de(f)] for f in filas],
        "Motivo": [_NOMBRE_MOTIVO.get(f.get("motivo"), f.get("motivo") or "") for f in filas],
        "Estado del envío": [f.get("estado_envio") or "" for f in filas],
        "Sustento": [f.get("texto") or "" for f in filas],
        "Detalle del sistema": [f.get("detalle") or "" for f in filas],
        "Revisada": ["Sí" if f.get("revisada") else "No" for f in filas],
        "Revisada por": [f.get("revisada_por") or "" for f in filas],
    })
    descargas(df, nombre, "Observaciones", key=clave)


def _acciones_marcar(obs, actor, vistas, clave):
    opciones = {
        f"{f.get('codigo_seguimiento') or f.get('id')} · {f.get('red') or ''} · {_NOMBRE_MOTIVO.get(f.get('motivo'), '')}": f.get("id")
        for f in vistas
    }
    elegidas = st.multiselect("Marcar como revisadas", list(opciones), key=f"obs_marcar_sel_{clave}",
                              placeholder="Elija una o más")
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        if st.button("Marcar seleccionadas", key=f"obs_btn_sel_{clave}", icon=":material/done:",
                     disabled=not elegidas, use_container_width=True):
            n = obs.marcar_revisadas([opciones[e] for e in elegidas], actor.get("usuario", ""))
            _invalidar_contador()
            st.toast(f"{n} marcada(s) como revisada(s).", icon=":material/check_circle:")
            st.rerun()
    with c2:
        if st.button("Marcar todas las mostradas", key=f"obs_btn_todas_{clave}", icon=":material/done_all:",
                     use_container_width=True):
            n = obs.marcar_revisadas([f.get("id") for f in vistas], actor.get("usuario", ""))
            _invalidar_contador()
            st.toast(f"{n} marcada(s) como revisada(s).", icon=":material/check_circle:")
            st.rerun()


def _pestana_lista(obs, actor, clave, titulo, subtitulo, vacio_titulo, vacio_texto, filtrar, revisada=False):
    todas = obs.listar(revisada=revisada, limite=500)
    filas = [f for f in todas if filtrar(f)]
    red, semana, rango = _filtros(clave)
    vistas = _aplicar_filtros(filas, red, semana, rango)
    with st.container(key=f"panel_obs_{clave}"):
        panel_cab(titulo, f"{len(vistas)} de {len(filas)} {subtitulo}")
        if not vistas:
            mostrar(aviso("ok" if not revisada else "info", vacio_titulo, vacio_texto))
            return
        _tabla(vistas)
        _detalle(vistas, clave)
        _exportar(vistas, f"observaciones_{clave}", f"obs_{clave}")
        if not revisada:
            _acciones_marcar(obs, actor, vistas, clave)


def _pestana_fallas(obs, actor):
    filas = [f for f in obs.listar(revisada=False, limite=500) if obs.categoria_de(f) == "FALLA"]
    with st.container(key="panel_obs_fallas"):
        panel_cab("Fallas técnicas por atender", f"{len(filas)} pendientes · no las ven las redes")
        if not filas:
            mostrar(aviso("ok", "No hay fallas técnicas pendientes", "Aquí aparece lo que el sistema no pudo completar, por ejemplo mover un archivo en Drive."))
            return
        mostrar(aviso("warn", "El envío de la red quedó registrado",
                      "Lo que falló fue una tarea interna. Corrija la causa (por ejemplo, el permiso de Drive) y use «Reintentar»."))
        _tabla(filas)
        _detalle(filas, "f")
        opciones = {
            f"{f.get('codigo_seguimiento')} · {f.get('red')} · {str(f.get('detalle') or '')[:60]}": f for f in filas
        }
        elegida = st.selectbox("Falla a atender", ["—"] + list(opciones), key="obs_falla_sel")
        c1, c2, _ = st.columns([1, 1.3, 2])
        with c1:
            reintentable = elegida != "—" and (opciones[elegida].get("datos") or {}).get("tipo") == "REEMPLAZO"
            if st.button("Reintentar", key="obs_falla_reintentar", icon=":material/refresh:", type="primary",
                         disabled=not reintentable, use_container_width=True):
                from app_pages.usuario_logica import reintentar_reemplazo
                f = opciones[elegida]
                with st.spinner("Reintentando..."):
                    ok_, msg = reintentar_reemplazo(f, actor.get("usuario", ""))
                if ok_:
                    obs.marcar_revisadas([f.get("id")], actor.get("usuario", ""))
                    _invalidar_contador()
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    mostrar(aviso("bad", "Sigue fallando", esc(msg)))
        with c2:
            if st.button("Marcar como atendida", key="obs_falla_marcar", icon=":material/done:",
                         disabled=elegida == "—", use_container_width=True):
                obs.marcar_revisadas([opciones[elegida].get("id")], actor.get("usuario", ""))
                _invalidar_contador()
                st.toast("Falla marcada como atendida.", icon=":material/check_circle:")
                st.rerun()
        if elegida != "—" and not reintentable:
            st.caption("Esta falla no se puede reintentar desde aquí: resuélvala a mano y márquela como atendida.")


def mostrar_observaciones():
    obs = get_observaciones()
    if not obs.disponible():
        mostrar(aviso(
            "warn", "El módulo de observaciones aún no está activo",
            "Falta crear su tabla en Supabase: ejecute el archivo <strong>sql/13_observaciones_envio.sql</strong> "
            "en el SQL Editor. Mientras tanto, los envíos funcionan con normalidad."))
        return

    actor = actor_actual()
    # SIREA 3.1: propuestas del Agente de IA sobre esta bandeja (se aprueban aquí mismo).
    from app_pages.agente_sugerencias import TIPOS_OBSERVACION, panel as panel_sugerencias
    panel_sugerencias(TIPOS_OBSERVACION, "Sugerencias del agente para esta bandeja", clave="obs")
    cont = obs.contadores()
    todas = obs.listar(revisada=False, limite=500)
    n_com = sum(1 for f in todas if obs.categoria_de(f) == "COMENTARIO")
    n_rev = sum(1 for f in todas if obs.categoria_de(f) == "REVISION")
    t_com, t_rev, t_fal, t_hist = st.tabs([
        f"Comentarios de las redes ({n_com})" if n_com else "Comentarios de las redes",
        f"Envíos por revisar ({n_rev})" if n_rev else "Envíos por revisar",
        f"Fallas técnicas ({cont['fallas']})" if cont["fallas"] else "Fallas técnicas",
        "Revisadas"])
    with t_com:
        _pestana_lista(obs, actor, "com", "Comentarios de las redes", "pendientes",
                       "No hay comentarios pendientes", "Lo que escriban las redes en «Observación» aparecerá aquí.",
                       lambda f: obs.categoria_de(f) == "COMENTARIO")
    with t_rev:
        _pestana_lista(obs, actor, "rev", "Envíos por revisar", "pendientes",
                       "No hay envíos por revisar", "Aquí llegan los envíos observados, duplicados o con reemplazo que no traen comentario.",
                       lambda f: obs.categoria_de(f) == "REVISION")
    with t_fal:
        _pestana_fallas(obs, actor)
    with t_hist:
        _pestana_lista(obs, actor, "hist", "Observaciones revisadas", "(las 500 más recientes)",
                       "Aún no hay observaciones revisadas", "Las que marque como revisadas pasarán aquí.",
                       lambda f: True, revisada=True)
