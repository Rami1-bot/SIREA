# app_pages/filtro_periodo.py
"""
SIREA 3.3 · Filtro común de Año, Semana y Red para todos los módulos.

  * Lo que elige en un módulo se mantiene al pasar a otro (y al refrescar
    la página: se guarda en la dirección como ?fa=2026&fs=38&fr=...).
  * Mientras no elija nada, sigue a la semana ACTIVA (si el panel cierra la
    semana y abre la siguiente, el filtro se mueve solo).
  * «Volver a la semana activa» deshace la elección.

Uso:
    from app_pages.filtro_periodo import filtro_periodo
    p = filtro_periodo("dash")                # p.anio, p.semana, p.red (None = todas), p.es_activa
    p = filtro_periodo("inf", con_red=False)
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional

import streamlit as st

TODAS = "Todas las redes"
_CLAVE = "sirea_periodo"
_QP = {"anio": "fa", "semana": "fs", "red": "fr"}


class Periodo(NamedTuple):
    anio: int
    semana: int
    red: Optional[str]          # None = todas las redes
    es_activa: bool
    anio_activo: int
    semana_activa: int


def _activo():
    from src.config import Config
    return int(Config.get_anio_actual()), int(Config.get_semana_actual())


def _anios(anio_activo: int) -> List[int]:
    try:
        from src.db_manager import get_db_manager
        anios = sorted({int(a["anio"]) for a in (get_db_manager().obtener_anios_epidemiologicos() or []) if a.get("anio")},
                       reverse=True)
    except Exception:
        anios = []
    if anio_activo not in anios:
        anios.insert(0, anio_activo)
    return [a for a in anios if a <= anio_activo] or [anio_activo]


def _semanas(anio: int, anio_activo: int, semana_activa: int) -> List[int]:
    from src.agentes.patrones import semanas_del_anio
    tope = semana_activa if anio == anio_activo else semanas_del_anio(anio)   # no hay datos de semanas futuras
    return list(range(1, max(1, int(tope)) + 1))


def _estado() -> dict:
    est = st.session_state.get(_CLAVE)
    if est is None:
        est = {"fijado": False, "anio": None, "semana": None, "red": None}
        qp = st.query_params
        try:
            if qp.get(_QP["anio"]) and qp.get(_QP["semana"]):
                est.update(fijado=True, anio=int(qp[_QP["anio"]]), semana=int(qp[_QP["semana"]]))
        except (TypeError, ValueError):
            pass
        if qp.get(_QP["red"]):
            est["red"] = str(qp[_QP["red"]])[:80]
        st.session_state[_CLAVE] = est
    return est


def _sincronizar_url(est: dict):
    qp = st.query_params
    for k in ("anio", "semana"):
        v = str(est[k]) if est["fijado"] and est.get(k) else None
        if v and qp.get(_QP[k]) != v:
            qp[_QP[k]] = v
        elif not v and _QP[k] in qp:
            del qp[_QP[k]]
    if est.get("red"):
        if qp.get(_QP["red"]) != est["red"]:
            qp[_QP["red"]] = est["red"]
    elif _QP["red"] in qp:
        del qp[_QP["red"]]


def periodo_actual() -> Periodo:
    """El período elegido (o la semana activa) sin dibujar nada."""
    a_act, s_act = _activo()
    est = _estado()
    anio = est["anio"] if est["fijado"] and est.get("anio") else a_act
    semana = est["semana"] if est["fijado"] and est.get("semana") else s_act
    if anio > a_act or (anio == a_act and semana > s_act):
        anio, semana = a_act, s_act
    return Periodo(int(anio), int(semana), est.get("red") or None, (anio, semana) == (a_act, s_act), a_act, s_act)


def _al_cambiar(pantalla: str, campo: str):
    est = _estado()
    valor = st.session_state.get(f"fp_{pantalla}_{campo}")
    if campo == "red":
        est["red"] = None if valor in (None, TODAS) else valor
        return
    p = periodo_actual()
    est.update(fijado=True, anio=p.anio, semana=p.semana)
    est[campo] = int(valor)
    if campo == "anio":     # al cambiar de año, la semana se ajusta al tope de ese año
        semanas = _semanas(est["anio"], p.anio_activo, p.semana_activa)
        est["semana"] = min(int(est["semana"]), semanas[-1])
    if (est["anio"], est["semana"]) == (p.anio_activo, p.semana_activa):
        est["fijado"] = False


def _volver(pantalla: str):
    _estado().update(fijado=False, anio=None, semana=None)


def filtro_periodo(pantalla: str, con_red: bool = True, con_semana: bool = True, redes: Optional[List[str]] = None,
                   ayuda: str = "") -> Periodo:
    """Dibuja Año · Semana · Red y devuelve el período elegido."""
    p = periodo_actual()
    est = _estado()
    if con_red and redes is None:
        try:
            from src.data_loader import get_data_loader
            redes = list(get_data_loader().obtener_redes() or [])
        except Exception:
            redes = []
    redes = sorted(redes or [])
    if est.get("red") and est["red"] not in redes:
        est["red"] = None
    anios = _anios(p.anio_activo)
    semanas = _semanas(p.anio, p.anio_activo, p.semana_activa)
    # valores de los controles a partir del estado común (así se comparte entre módulos)
    st.session_state[f"fp_{pantalla}_anio"] = p.anio
    st.session_state[f"fp_{pantalla}_semana"] = min(p.semana, semanas[-1])
    st.session_state[f"fp_{pantalla}_red"] = est.get("red") or TODAS

    anchos = [1, 1.2] if con_semana else [1]
    anchos += [2] if con_red else []
    anchos += [1.5] if not p.es_activa else ([2] if not con_red else [])
    cols = st.columns(anchos, vertical_alignment="bottom")
    i = 0
    cols[i].selectbox("Año", options=anios, key=f"fp_{pantalla}_anio", on_change=_al_cambiar, args=(pantalla, "anio"))
    i += 1
    if con_semana:
        cols[i].selectbox("Semana", options=semanas, key=f"fp_{pantalla}_semana", on_change=_al_cambiar, args=(pantalla, "semana"),
                          format_func=lambda s: f"Semana {s}" + (" (activa)" if (p.anio, s) == (p.anio_activo, p.semana_activa) else ""))
        i += 1
    if con_red:
        cols[i].selectbox("Red", options=[TODAS] + redes, key=f"fp_{pantalla}_red", on_change=_al_cambiar, args=(pantalla, "red"))
        i += 1
    if not p.es_activa:
        with cols[i]:
            st.button("Semana activa", key=f"fp_{pantalla}_volver", icon=":material/today:", on_click=_volver, args=(pantalla,),
                      use_container_width=True, help=f"Volver a la semana {p.semana_activa}/{p.anio_activo}")
    if not p.es_activa:
        st.caption(f"Está viendo la semana {p.semana}/{p.anio}, no la activa ({p.semana_activa}/{p.anio_activo}). "
                   "La elección se mantiene en los demás módulos." + (f" {ayuda}" if ayuda else ""))
    elif ayuda:
        st.caption(ayuda)
    _sincronizar_url(est)
    return periodo_actual()


def filtro_red(pantalla: str, redes: List[str], etiqueta: str = "Red") -> Optional[str]:
    """Solo la Red (comparte la elección con el filtro común). Para listas que no dependen de la semana."""
    est = _estado()
    redes = sorted({r for r in redes if r})
    if est.get("red") and est["red"] not in redes:
        redes.append(est["red"])
    st.session_state[f"fp_{pantalla}_red"] = est.get("red") or TODAS
    st.selectbox(etiqueta, options=[TODAS] + redes, key=f"fp_{pantalla}_red", on_change=_al_cambiar, args=(pantalla, "red"))
    _sincronizar_url(est)
    return est.get("red") or None
