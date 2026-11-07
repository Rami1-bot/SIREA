# pages/red_detalle.py
"""
«Mi progreso» (vista de la red): detalle de lo enviado en una semana.

Muestra, solo para la red que inició sesión: quién envió y cuándo, qué estado tuvo cada envío, qué centros y
tipos de reporte (c/e/h) ya se recibieron, y las observaciones que la red dejó con su estado de revisión.
Es solo lectura: no hay acciones ni avisos para nadie.
"""

import re
from datetime import datetime

import pandas as pd
import streamlit as st

from src.db_manager import get_db_manager
from src.observaciones import get_observaciones
from utils.duplicados import es_duplicado, es_reemplazado
from utils.tema import chip, mostrar, aviso, kpi
from utils.tema_admin import panel_cab, esc
from utils.tabla_navegable import tabla_navegable
from app_pages.usuario_logica import (
    _lista_centros_red, _pares_de_envio, _clave_centro, obtener_centros_excluidos, extraer_nombre_limpio,
)

_TIPOS = (("c", "Consulta externa"), ("e", "Emergencia"), ("h", "Hospitalización"))
_MOTIVO = {"SUSTENTO": ("Comentario", "ok"), "OBSERVADO": ("Observado", "warn"),
           "DUPLICADO": ("Duplicado", "dup"), "REEMPLAZO": ("Reemplazo", "info")}


_TONO_ESTADO = {"A tiempo": "ok", "Tardío": "warn", "Con observaciones": "warn", "Duplicado": "dup", "Reemplazado": "mute"}


def _clave_fecha(fila) -> datetime:
    """Orden por fecha de la primera columna ('dd/mm/aaaa hh:mm'); lo que no se pueda leer va al final."""
    try:
        return datetime.strptime(str(fila[0]), "%d/%m/%Y %H:%M")
    except Exception:
        return datetime.min


def _fecha_lima(valor) -> str:
    try:
        return pd.to_datetime(valor, utc=True).tz_convert("America/Lima").strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def _estado(envio: dict):
    """(texto, tono) del estado del envío, pensado para quien lo envió."""
    if es_reemplazado(envio):
        return "Reemplazado", "mute"
    if es_duplicado(envio):
        return "Duplicado", "dup"
    if envio.get("es_atrasado") or envio.get("estado") == "ATRASADO":
        return "Tardío", "warn"
    if envio.get("estado") == "OBSERVADO":
        return "Con observaciones", "warn"
    return "A tiempo", "ok"


def _centros_txt(envio: dict) -> str:
    cs = envio.get("centros") or []
    nombres = [extraer_nombre_limpio(str(c.get("nombre", c) if isinstance(c, dict) else c)) for c in cs]
    return ", ".join(n for n in nombres if n) or "—"


def _tipos_txt(envio: dict) -> str:
    letras = sorted({t for _, t in _pares_de_envio(envio)})
    nombres = {l: n for l, n in _TIPOS}
    return ", ".join(nombres.get(l, l) for l in letras) or "—"


def mostrar_detalle_envios_red(red: str, anio: int, semana_activa: int):
    """Sección «Quién envió y qué se recibió» de «Mi progreso» (solo lectura)."""
    mostrar('<h2 class="sire-h2">Envíos y observaciones de su red</h2>')
    semanas = list(range(semana_activa, 0, -1)) or [semana_activa]
    c1, _ = st.columns([1, 3])
    with c1:
        semana = st.selectbox("Semana", options=semanas, key="red_detalle_semana",
                              help="Elija la semana que desea revisar.")

    try:
        envios = get_db_manager().obtener_envios(anio=anio, semana=semana, red=red, limit=500) or []
    except Exception:
        envios = []
    envios = sorted(envios, key=lambda e: str(e.get("fecha_envio") or ""), reverse=True)

    vigentes = [e for e in envios if not es_duplicado(e) and not es_reemplazado(e)]
    n_tard = sum(1 for e in vigentes if _estado(e)[1] == "warn" and _estado(e)[0] == "Tardío")
    n_dup = sum(1 for e in envios if es_duplicado(e))
    obs = []
    try:
        obs = [o for o in get_observaciones().listar(revisada=None, red=red, anio=anio, semana=semana, limite=200)
               if o.get('motivo') != 'FALLA']   # las fallas técnicas no se muestran a las redes
    except Exception:
        obs = []
    n_pend = sum(1 for o in obs if not o.get("revisada"))

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        mostrar(kpi("Envíos recibidos", len(vigentes), f"Semana {semana} · vigentes", None, "check"))
    with k2:
        mostrar(kpi("Tardíos", n_tard, "Después de la fecha de corte", "warn" if n_tard else None, "reloj"))
    with k3:
        mostrar(kpi("Duplicados", n_dup, "Reenvíos ya recibidos", None, "copia"))
    with k4:
        mostrar(kpi("Observaciones", len(obs), f"{n_pend} sin revisar" if n_pend else "Todas revisadas", "warn" if n_pend else None, "alerta"))

    if not envios:
        mostrar(aviso("info", f"Su red no tiene envíos en la semana {semana}", "Cuando envíe un reporte aparecerá aquí."))
        return

    # ---- Quién envió ----
    with st.container(key="red_panel_quien"):
        panel_cab("Quién envió", "Cada envío con su estado; el más reciente primero")
        columnas = ["Fecha y hora", "Enviado por", "Centros", "Tipos", "Archivos", "Código", "Estado"]
        filas = [[
            _fecha_lima(e.get("fecha_envio")),
            f"{e.get('apellido_usuario') or ''} {e.get('nombre_usuario') or ''}".strip(),
            _centros_txt(e), _tipos_txt(e), e.get("cantidad_archivos") or 0,
            str(e.get("codigo_seguimiento") or ""), _estado(e)[0],
        ] for e in envios]
        tabla_navegable(
            "red_quien", columnas, filas,
            chips={"Estado": lambda v: chip(esc(v), _TONO_ESTADO.get(v, "info"))},
            derecha=("Archivos",), unidad="envíos", placeholder="Buscar por persona, centro o código",
            filtro={"columna": "Estado", "opciones": list(_TONO_ESTADO), "etiqueta": "Estado del envío"},
            orden_opciones=[("Más reciente primero", "Fecha y hora", True), ("Más antiguo primero", "Fecha y hora", False),
                            ("Enviado por: A → Z", "Enviado por", False), ("Centros: A → Z", "Centros", False)],
            orden_inicial="Más reciente primero", claves_orden={"Fecha y hora": _clave_fecha},
            descarga=(f"envios_{red}_{anio}_sem{semana}".replace(" ", "_"), "Envíos"),
        )

    # ---- Centros × tipo ----
    try:
        excl = (obtener_centros_excluidos() or {}).get(red, [])
        activos = _lista_centros_red(red, excl)
    except Exception:
        activos = []
    if activos:
        recibido = set()
        for e in vigentes:
            recibido |= _pares_de_envio(e)
        filas = []
        for c in activos:
            nombre = (c.get("centro_nombre") or "").strip()
            clave = _clave_centro(nombre)
            fila = [f"{c.get('codigo', '')} {nombre}".strip()]
            for letra, _ in _TIPOS:
                fila.append(chip("Recibido", "ok") if (clave, letra) in recibido else '<span class="sire-nota">—</span>')
            filas.append(fila)
        with st.container(key="red_panel_matriz"):
            panel_cab("Qué se recibió por centro y tipo de reporte",
                      "Un guion no siempre es una falta: no todos los centros reportan los tres tipos")
            tabla_navegable(
                "red_matriz", ["Centro"] + [n for _, n in _TIPOS], filas, crudas=[n for _, n in _TIPOS],
                unidad="centros", placeholder="Buscar un centro",
                orden_opciones=[("Centro: A → Z", "Centro", False), ("Centro: Z → A", "Centro", True)],
                orden_inicial="Centro: A → Z",
            )

    # ---- Observaciones ----
    with st.container(key="red_panel_obs"):
        panel_cab("Observaciones de su red", "Lo que usted escribió y si la OIIS ya lo revisó")
        if not obs:
            mostrar('<div class="sire-vacio">No hay observaciones en esta semana.</div>')
        else:
            columnas_o = ["Fecha y hora", "Enviado por", "Código", "Tipo", "Observación", "Revisión"]
            filas_o = [[
                _fecha_lima(o.get("fecha_creacion")), str(o.get("remitente") or ""), str(o.get("codigo_seguimiento") or ""),
                chip(esc(_MOTIVO.get(o.get("motivo"), (o.get("motivo") or "", "info"))[0]),
                     _MOTIVO.get(o.get("motivo"), ("", "info"))[1]),
                str(o.get("texto") or o.get("detalle") or ""),
                chip("Revisada por la OIIS", "ok") if o.get("revisada") else chip("Pendiente de revisión", "warn"),
            ] for o in obs]
            tabla_navegable(
                "red_obs", columnas_o, filas_o, crudas=("Tipo", "Revisión"), unidad="observaciones",
                placeholder="Buscar en las observaciones",
                filtro={"columna": "Revisión", "opciones": ["Pendiente de revisión", "Revisada por la OIIS"], "etiqueta": "Revisión"},
                orden_opciones=[("Más reciente primero", "Fecha y hora", True), ("Más antigua primero", "Fecha y hora", False)],
                orden_inicial="Más reciente primero", claves_orden={"Fecha y hora": _clave_fecha},
            )
