# utils/tabla_navegable.py
"""
Tabla navegable para el panel y las pantallas de las redes: encabezado azul claro, búsqueda, filtros
(por estado, por lista y por rango de fechas), orden, columnas visibles, cantidad de filas por página
(10, 25, 50 o todas) y paginación.

Se dibuja dentro de un fragmento de Streamlit: al buscar, filtrar o cambiar de página solo se
redibuja la tabla, no toda la pantalla (y no se vuelve a consultar la base de datos).

Uso:

    tabla_navegable(
        "red_centros", ["Centro", "Estado"], filas,
        chips={"Estado": chip_estado}, crudas=(), derecha=(),
        filtro={"columna": "Estado", "opciones": ["Enviado", "Pendiente"], "etiqueta": "Estado"},
        filtros=[{"columna": "Red", "etiqueta": "Red"},               # lista desplegable (opciones automáticas)
                 {"columna": "Centro", "depende_de": "Red"}],         # sus opciones se acotan a la red elegida
        fechas={"columna": "Fecha", "etiqueta": "Fecha"},              # desde / hasta
        columnas_elegibles=True, ocultas=("Código",),                  # botón «Columnas»
        unidad="centros", descarga=("centros_JAEN_sem39", "Centros"),
    )

Las filas son listas con un valor por columna. Una columna en `chips` recibe el valor y
devuelve el HTML de la etiqueta; una en `crudas` ya contiene HTML confiable; el resto se
escapa (como en tabla_html).
"""

import html as _html
import re
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd
import streamlit as st

from utils.tema import mostrar
from utils.tema_admin import descargas, tabla_html

_ETIQUETAS = re.compile(r"<[^>]*>")
_FECHA_DMA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_FECHA_AMD = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
OPCIONES_FILAS = (10, 25, 50, "Todas")
TODAS = "Todas"


def _texto(valor: Any) -> str:
    """Texto visible de una celda (sin etiquetas HTML ni entidades)."""
    if valor is None:
        return ""
    return _html.unescape(_ETIQUETAS.sub("", str(valor))).strip()


def _num(valor: Any) -> Optional[float]:
    try:
        return float(str(valor).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _clave_orden(valor: Any):
    """Los números se ordenan como números y el resto como texto sin distinguir mayúsculas."""
    n = _num(_texto(valor))
    return (0, n, "") if n is not None else (1, 0.0, _texto(valor).lower())


def _a_fecha(valor: Any) -> Optional[date]:
    """Fecha de una celda con formato dd/mm/aaaa (con o sin hora) o aaaa-mm-dd. None si no hay fecha."""
    t = _texto(valor)
    m = _FECHA_DMA.search(t)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = _FECHA_AMD.search(t)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return None


def _opciones_orden(columnas, derecha, personalizadas):
    """Lista de (etiqueta, columna, descendente). La primera es el orden original."""
    ops = [("Orden original", None, False)]
    if personalizadas:
        return ops + list(personalizadas)
    for c in columnas:
        if c in derecha:
            ops += [(f"{c}: de menor a mayor", c, False), (f"{c}: de mayor a menor", c, True)]
        else:
            ops += [(f"{c}: A → Z", c, False), (f"{c}: Z → A", c, True)]
    return ops


def _limpiar(vacios: Dict[str, Any], quitar: Sequence[str]):
    """Devuelve los controles de filtro a su estado inicial (se ejecuta antes de volver a dibujar)."""
    for k, v in vacios.items():
        st.session_state[k] = v
    for k in quitar:
        st.session_state.pop(k, None)


def _chip_aplicado(etiqueta: str, valor: str) -> str:
    return (f'<span class="sire-fchip"><b>{_html.escape(etiqueta)}:</b> {_html.escape(valor)}</span>')


@st.fragment
def tabla_navegable(
    clave: str,
    columnas: Sequence[str],
    filas: Sequence[Sequence],
    *,
    chips: Optional[Dict[str, Callable]] = None,
    crudas: Sequence[str] = (),
    derecha: Sequence[str] = (),
    vacio: str = "Sin registros para mostrar.",
    unidad: str = "registros",
    buscar: bool = True,
    placeholder: str = "Escriba para buscar",
    filtro: Optional[dict] = None,
    filtros: Sequence[dict] = (),
    fechas: Optional[dict] = None,
    columnas_elegibles: bool = False,
    ocultas: Sequence[str] = (),
    orden_opciones: Optional[Sequence] = None,
    orden_inicial: Optional[str] = None,
    claves_orden: Optional[Dict[str, Callable]] = None,
    por_pagina_inicial: int = 10,
    descarga: Optional[tuple] = None,
    nowrap: bool = False,
    alto: Optional[int] = None,
    formato_descarga: Optional[Dict[str, Callable]] = None,
):
    """Dibuja los controles, la tabla de la página actual y el pie con la paginación."""
    columnas = list(columnas)
    filas = [list(f) for f in filas]
    derecha = tuple(derecha)
    claves_orden = claves_orden or {}
    k_q, k_f, k_o, k_pp = f"{clave}_q", f"{clave}_f", f"{clave}_o", f"{clave}_pp"
    k_pag, k_firma, k_cols = f"{clave}_pag", f"{clave}_firma", f"{clave}_cols"
    k_desde, k_hasta = f"{clave}_desde", f"{clave}_hasta"
    filtros = list(filtros or [])
    aplicados: List[str] = []                      # etiquetas HTML de los filtros que están activos
    vacios: Dict[str, Any] = {}                    # estado inicial de cada control de filtro
    quitar: List[str] = []

    # ---------------- controles ----------------
    with st.container(key=f"tnav_{clave}"):
        # filtro por estado (botones con conteo)
        opcion_filtro = None
        if filtro:
            ic = columnas.index(filtro["columna"])
            textos = [_texto(f[ic]).lower() for f in filas]
            conteos = {o: sum(1 for t in textos if t == o.lower()) for o in filtro["opciones"]}
            opciones_f = [o for o in filtro["opciones"] if conteos[o]]      # no se muestran las que no tienen casos
            nombres = filtro.get("nombres") or {}
            etiquetas = [f"Todos ({len(filas)})"] + [f"{nombres.get(o, o)} ({conteos[o]})" for o in opciones_f]
            sel = st.segmented_control(
                filtro.get("etiqueta", "Estado"), etiquetas, default=etiquetas[0],
                key=k_f, label_visibility="collapsed", width="content",
            )
            sel = sel or etiquetas[0]
            opcion_filtro = None if sel not in etiquetas[1:] else opciones_f[etiquetas.index(sel) - 1]
            quitar.append(k_f)
            if opcion_filtro is not None:
                aplicados.append(_chip_aplicado(filtro.get("etiqueta", "Estado"), nombres.get(opcion_filtro, opcion_filtro)))

        # fila de búsqueda y filtros de lista
        n_sup = (1 if buscar else 0) + len(filtros)
        valores_lista: List[Optional[str]] = []
        if n_sup:
            anchos = ([2.4] if buscar else []) + [1.2] * len(filtros)
            cols = st.columns(anchos, gap="medium", vertical_alignment="bottom")
            i = 0
            if buscar:
                with cols[i]:
                    consulta = st.text_input("Buscar", key=k_q, placeholder=placeholder, icon=":material/search:")
                vacios[k_q] = ""
                i += 1
            else:
                consulta = ""
            for n, fl in enumerate(filtros):
                ic = columnas.index(fl["columna"])
                opts = fl.get("opciones")
                if opts is None:
                    base = filas
                    dep = fl.get("depende_de")          # p. ej. los centros se acotan a la red ya elegida
                    if dep and dep in columnas:
                        for m, fp in enumerate(filtros[:n]):
                            if fp["columna"] == dep and valores_lista[m] is not None:
                                ip = columnas.index(dep)
                                base = [f for f in filas if _texto(f[ip]) == valores_lista[m]]
                    vistos = {_texto(f[ic]) for f in base if _texto(f[ic])}
                    opts = sorted(vistos, key=lambda x: x.lower())
                k_l = f"{clave}_l{n}"
                if st.session_state.get(k_l, TODAS) not in [TODAS] + list(opts):
                    st.session_state[k_l] = TODAS       # el valor guardado ya no existe en la lista: se limpia
                with cols[i + n]:
                    val = st.selectbox(fl.get("etiqueta", fl["columna"]), [TODAS] + list(opts), key=k_l)
                vacios[k_l] = TODAS
                if val != TODAS:
                    valores_lista.append(val)
                    aplicados.append(_chip_aplicado(fl.get("etiqueta", fl["columna"]), val))
                else:
                    valores_lista.append(None)
        else:
            consulta = ""

        # rango de fechas
        desde = hasta = None
        if fechas:
            fc1, fc2, _ = st.columns([1.2, 1.2, 3], gap="medium")
            etq = fechas.get("etiqueta", "Fecha")
            with fc1:
                desde = st.date_input(f"{etq}: desde", value=None, key=k_desde, format="DD/MM/YYYY")
            with fc2:
                hasta = st.date_input(f"{etq}: hasta", value=None, key=k_hasta, format="DD/MM/YYYY")
            vacios[k_desde] = None
            vacios[k_hasta] = None
            if desde and hasta and desde > hasta:
                desde, hasta = hasta, desde
            if desde or hasta:
                txt = (f"{desde:%d/%m/%Y}" if desde else "…") + " – " + (f"{hasta:%d/%m/%Y}" if hasta else "…")
                aplicados.append(_chip_aplicado(etq, txt))

        ops = _opciones_orden(columnas, derecha, orden_opciones)
        etiquetas_orden = [o[0] for o in ops]
        idx_orden = etiquetas_orden.index(orden_inicial) if orden_inicial in etiquetas_orden else 0

        anchos = [2.0, 1.1] + ([1.1] if columnas_elegibles else [])
        cols = st.columns(anchos, gap="medium", vertical_alignment="bottom")
        with cols[0]:
            orden_sel = st.selectbox("Ordenar por", etiquetas_orden, index=idx_orden, key=k_o)
        with cols[1]:
            etiquetas_pp = [str(o) for o in OPCIONES_FILAS]
            pp_ini = str(por_pagina_inicial) if str(por_pagina_inicial) in etiquetas_pp else "10"
            pp_sel = st.selectbox("Filas por página", etiquetas_pp, index=etiquetas_pp.index(pp_ini), key=k_pp)
        visibles_cols = columnas
        if columnas_elegibles:
            with cols[2]:
                with st.popover("Columnas", icon=":material/view_column:", use_container_width=True):
                    por_defecto = [c for c in columnas if c not in ocultas]
                    elegidas = st.multiselect("Columnas visibles", columnas, default=por_defecto, key=k_cols)
            visibles_cols = [c for c in columnas if c in (elegidas or columnas)]

        # filtros aplicados + limpiar
        if (consulta or "").strip():
            aplicados.insert(0, _chip_aplicado("Texto", consulta.strip()))
        if aplicados:
            ca, cb = st.columns([5, 1.2], vertical_alignment="center")
            with ca:
                mostrar('<div class="sire-fchips"><span class="sire-fchips-t">Aplicados:</span>' + "".join(aplicados) + "</div>")
            with cb:
                st.button("Limpiar filtros", key=f"{clave}_limpiar", icon=":material/filter_alt_off:",
                          on_click=_limpiar, args=(dict(vacios), list(quitar)), use_container_width=True)

    # ---------------- filtrar y ordenar ----------------
    visibles = filas
    if opcion_filtro is not None:
        ic = columnas.index(filtro["columna"])
        visibles = [f for f in visibles if _texto(f[ic]).lower() == opcion_filtro.lower()]
    for fl, val in zip(filtros, valores_lista):
        if val is not None:
            ic = columnas.index(fl["columna"])
            visibles = [f for f in visibles if _texto(f[ic]) == val]
    if fechas and (desde or hasta):
        ic = columnas.index(fechas["columna"])
        def _en_rango(f):
            d = _a_fecha(f[ic])
            if d is None:
                return False
            return (not desde or d >= desde) and (not hasta or d <= hasta)
        visibles = [f for f in visibles if _en_rango(f)]
    q = (consulta or "").strip().lower()
    if q:
        terminos = q.split()
        visibles = [f for f in visibles
                    if all(any(t in _texto(v).lower() for v in f) for t in terminos)]
    _, col_orden, desc = ops[etiquetas_orden.index(orden_sel)]
    if col_orden is not None:
        ic = columnas.index(col_orden)
        clave_fn = claves_orden.get(col_orden)
        visibles = sorted(visibles, key=(lambda f: clave_fn(f)) if clave_fn else (lambda f: _clave_orden(f[ic])),
                          reverse=desc)

    # ---------------- paginación ----------------
    total = len(visibles)
    por_pagina = (total or 1) if pp_sel == "Todas" else int(pp_sel)
    paginas = max(1, -(-total // por_pagina))
    firma = (q, opcion_filtro, tuple(valores_lista), desde, hasta, orden_sel, pp_sel, len(filas))
    if st.session_state.get(k_firma) != firma:      # cambió la búsqueda, un filtro, el orden o los datos: página 1
        st.session_state[k_firma] = firma
        st.session_state[k_pag] = 1
    pagina = min(max(1, int(st.session_state.get(k_pag, 1))), paginas)
    st.session_state[k_pag] = pagina
    ini = (pagina - 1) * por_pagina
    pagina_filas = visibles[ini:ini + por_pagina]

    # ---------------- tabla ----------------
    if not filas:
        mostrar(f'<div class="sire-vacio">{_html.escape(vacio)}</div>')
        return
    if not visibles:
        mostrar('<div class="sire-vacio">Ningún registro coincide con la búsqueda o los filtros elegidos.</div>')
    else:
        idx_vis = [columnas.index(c) for c in visibles_cols]
        filas_vis = [[f[i] for i in idx_vis] for f in pagina_filas]
        html_tabla = tabla_html(visibles_cols, filas_vis, chips=chips, crudas=crudas, derecha=derecha,
                                vacio=vacio, alto=alto,
                                variante="sire-tabla-azul" + (" sire-nowrap" if nowrap else ""))
        mostrar(html_tabla)

    # ---------------- pie: conteo y paginación ----------------
    def _ir(delta: int):
        st.session_state[k_pag] = st.session_state.get(k_pag, 1) + delta

    with st.container(key=f"tpie_{clave}"):
        izq, der = st.columns([3, 2.4], vertical_alignment="center")
        with izq:
            if total:
                fin = min(ini + por_pagina, total)
                filtrado = f" (de {len(filas)} en total)" if total != len(filas) else ""
                texto = f"Mostrando <b>{ini + 1}–{fin}</b> de <b>{total}</b> {_html.escape(unidad)}{filtrado}"
            else:
                texto = f"0 {_html.escape(unidad)}"
            mostrar(f'<div class="sire-tpie-n">{texto}</div>')
        with der:
            if paginas > 1:
                b1, b2, b3 = st.columns([1, 1.25, 1], vertical_alignment="center")
                with b1:
                    st.button("Anterior", key=f"{clave}_ant", on_click=_ir, args=(-1,), disabled=pagina <= 1,
                              icon=":material/chevron_left:", use_container_width=True)
                with b2:
                    mostrar(f'<div class="sire-tpie-p">Página <b>{pagina}</b> de <b>{paginas}</b></div>')
                with b3:
                    st.button("Siguiente", key=f"{clave}_sig", on_click=_ir, args=(1,), disabled=pagina >= paginas,
                              icon=":material/chevron_right:", icon_position="right", use_container_width=True)

    # ---------------- descarga (todo lo filtrado, no solo la página) ----------------
    if descarga and visibles:
        nombre_base, hoja = descarga
        formato_descarga = formato_descarga or {}
        def _celda(c, v):
            if c in formato_descarga:
                return formato_descarga[c](v)
            if (c in crudas or c in (chips or {})) and not isinstance(v, (int, float)):
                return _texto(v)
            return v
        df = pd.DataFrame(
            [[_celda(c, v) for c, v in zip(columnas, f)] for f in visibles],
            columns=columnas,
        )
        descargas(df, nombre_base, hoja, key=f"{clave}_dl")


def tabla_navegable_df(clave: str, df, **kw):
    """Igual que tabla_navegable, a partir de un DataFrame de pandas."""
    columnas = [str(c) for c in df.columns]
    filas = [list(f) for f in df.itertuples(index=False, name=None)]
    return tabla_navegable(clave, columnas, filas, **kw)
