# utils/tema_admin.py
"""
Componentes visuales del panel de administracion (SIREA).

Complementa utils/tema.py con lo que solo usa el panel: etiquetas de estado
de los envios, tablas HTML, barras horizontales, paneles con cabecera y el
encabezado de pagina con la semana activa y la hora de Lima.

Seguridad: todo texto que viene de la base de datos o de un usuario pasa por
`esc()` (escape HTML idempotente) antes de incrustarse en una tabla o en un
panel. Solo se deja crudo el HTML que arma este mismo modulo.
"""

import html as _html
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import streamlit as st

from utils.tema import TONOS, NAVY, chip, icono, kpi, mostrar, barra, aviso, mostrar_aviso

# ============================================================
# TEXTO SEGURO
# ============================================================

def esc(valor) -> str:
    """Escapa HTML sin doble escape (acepta texto ya saneado con sanitizar_html)."""
    if valor is None:
        return ""
    return _html.escape(_html.unescape(str(valor)), quote=True)


# ============================================================
# ESTADOS DE ENVIO
# ============================================================
# El valor guardado en la base de datos no cambia (APROBADO, OBSERVADO,
# ATRASADO); solo cambia como se le muestra a quien administra.

_ESTADOS = {
    "APROBADO": ("Recibido a tiempo", "ok", "check"),
    "OBSERVADO": ("Observado", "warn", "alerta"),
    "ATRASADO": ("Envío tardío", "bad", "reloj"),
    "PENDIENTE": ("Pendiente", "mute", "reloj"),
}


def etiqueta_estado(estado) -> str:
    """Texto que se muestra para un estado de envio (sin HTML)."""
    clave = str(estado or "").strip().upper()
    if clave in _ESTADOS:
        return _ESTADOS[clave][0]
    return str(estado).strip() if estado else "—"


def chip_estado(estado) -> str:
    """Chip con icono y texto para un estado de envio."""
    clave = str(estado or "").strip().upper()
    if clave in _ESTADOS:
        texto, tono, ico = _ESTADOS[clave]
        return chip(texto, tono, ico)
    return chip(esc(estado) if estado else "—", "mute")


def tono_porcentaje(pct: float) -> str:
    return "ok" if pct >= 90 else ("warn" if pct >= 60 else "bad")


def chip_porcentaje(valor) -> str:
    """Chip con el porcentaje escrito (verde >=90, ambar >=60, rojo <60)."""
    try:
        pct = float(str(valor).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return chip("—", "mute")
    texto = f"{int(pct) if pct == int(pct) else round(pct, 1)} %"
    return chip(texto, tono_porcentaje(pct))


def chip_nivel(pct) -> str:
    """Completo / Parcial / Bajo, con icono y texto (nunca solo color)."""
    try:
        p = float(str(pct).replace("%", "").strip())
    except (TypeError, ValueError):
        return chip("—", "mute")
    if p >= 100:
        return chip("Completo", "ok", "check")
    if p >= 50:
        return chip("Parcial", "warn", "reloj")
    return chip("Bajo", "bad", "alerta")


# ============================================================
# TABLAS
# ============================================================

def tabla_html(
    columnas: Sequence[str],
    filas: Iterable[Sequence],
    chips: Optional[Dict[str, Callable]] = None,
    crudas: Sequence[str] = (),
    derecha: Sequence[str] = (),
    vacio: str = "Sin registros para mostrar.",
    alto: Optional[int] = None,
) -> str:
    """
    Tabla HTML con el estilo del panel.

    - chips: {columna: funcion(valor) -> html} para columnas con etiqueta.
    - crudas: columnas cuyo contenido ya es HTML confiable.
    - derecha: columnas numericas alineadas a la derecha.
    El resto de celdas se escapa.
    """
    chips = chips or {}
    columnas = list(columnas)
    cab = "".join(
        f'<th class="{"num" if c in derecha else ""}">{esc(c)}</th>' for c in columnas
    )
    cuerpo = []
    for fila in filas:
        celdas = []
        for c, v in zip(columnas, fila):
            if c in chips:
                cont = chips[c](v)
            elif c in crudas:
                cont = "" if v is None else str(v)
            else:
                cont = esc(v) if v not in (None, "") else "—"
            celdas.append(f'<td class="{"num" if c in derecha else ""}">{cont}</td>')
        cuerpo.append("<tr>" + "".join(celdas) + "</tr>")
    if not cuerpo:
        return f'<div class="sire-vacio">{esc(vacio)}</div>'
    estilo = f' style="max-height:{int(alto)}px;overflow-y:auto"' if alto else ""
    return (
        f'<div class="sire-tabla-wrap"{estilo}><table class="sire-tabla"><thead><tr>'
        + cab + "</tr></thead><tbody>" + "".join(cuerpo) + "</tbody></table></div>"
    )


def tabla_df(df, chips=None, crudas=(), derecha=(), vacio="Sin registros para mostrar.", alto=None) -> str:
    """Igual que tabla_html pero a partir de un DataFrame de pandas."""
    columnas = [str(c) for c in df.columns]
    filas = df.itertuples(index=False, name=None)
    return tabla_html(columnas, filas, chips=chips, crudas=crudas, derecha=derecha, vacio=vacio, alto=alto)


def mostrar_tabla(df, **kw):
    mostrar(tabla_df(df, **kw))


# ============================================================
# BARRAS Y LISTAS
# ============================================================

def barras_h(items: List[Tuple[str, float]], tono: str = "info", sufijo: str = "") -> str:
    """Barras horizontales con etiqueta a la izquierda y valor a la derecha."""
    if not items:
        return '<div class="sire-vacio">Sin datos para mostrar.</div>'
    maximo = max((float(v) for _, v in items), default=1) or 1
    color = {"info": "#0077C8", "bad": "#B42318", "ok": "#1E6B3A", "warn": "#7A5A00"}[tono]
    filas = "".join(
        f'<div class="sire-hb"><span class="sire-hb-k">{esc(k)}</span>'
        f'<span class="sire-hb-pista"><span style="width:{max(2, float(v) / maximo * 100):.1f}%;background:{color}"></span></span>'
        f'<span class="sire-hb-v">{int(v) if float(v) == int(float(v)) else v}{sufijo}</span></div>'
        for k, v in items
    )
    return f'<div class="sire-hbars">{filas}</div>'


def lista_cumplimiento(items: List[Tuple[str, int, int]], detalle: str = "centros") -> str:
    """
    Lista de redes con barra de cumplimiento.
    items = [(nombre, enviados, total)].
    """
    if not items:
        return '<div class="sire-vacio">Sin datos para mostrar.</div>'
    out = []
    for nombre, env, tot in items:
        pct = (env / tot * 100) if tot else 0
        out.append(
            f'<div class="sire-cum"><div class="sire-cum-h"><span>{esc(nombre)}</span>'
            f'<span class="sire-cum-d">{env} de {tot} {detalle}</span></div>'
            f'{barra(pct)}</div>'
        )
    return '<div class="sire-cums">' + "".join(out) + "</div>"


# ============================================================
# CABECERAS
# ============================================================

def panel_cab(titulo: str, subtitulo: str = ""):
    """Titulo de un panel (usar dentro de st.container(key='panel_*'))."""
    s = f'<div class="sire-panel-s">{subtitulo}</div>' if subtitulo else ""
    mostrar(f'<div class="sire-panel-h"><h2>{titulo}</h2>{s}</div>')


def vacio(texto: str):
    mostrar(f'<div class="sire-vacio">{esc(texto)}</div>')


def hora_lima() -> str:
    from utils.helpers import obtener_fecha_actual
    return obtener_fecha_actual().strftime("%H:%M")


def semana_activa_info() -> Tuple[Optional[int], Optional[int]]:
    """(semana, anio) activos, o (None, None) si no se pueden leer."""
    try:
        from src.config import Config
        return Config.get_semana_actual(), Config.get_anio_actual()
    except Exception:
        return None, None


def encabezado_admin(titulo: str, subtitulo: str = "", grupo: str = ""):
    """Cabecera de cada seccion del panel: migas, titulo, subtitulo y etiquetas."""
    semana, anio = semana_activa_info()
    etiquetas = ""
    if semana:
        etiquetas += chip(f"Semana activa {semana} · {anio}", "info")
    etiquetas += chip(f"Hora de Lima {hora_lima()}", "info")
    migas = "Panel de administración" + (f" / {esc(titulo)}" if titulo else "")
    s = f'<p class="sire-sub">{esc(subtitulo)}</p>' if subtitulo else ""
    mostrar(
        '<div class="sire-admin-top"><div class="sire-titulo"><div>'
        f'<div class="sire-migas">{migas}</div><h1>{esc(titulo)}</h1>{s}</div>'
        f'<div class="sire-titulo-der">{etiquetas}</div></div></div>'
    )


def kpis(tarjetas: List[str]):
    """Fila de KPIs (cada elemento es el HTML de utils.tema.kpi)."""
    cols = st.columns(len(tarjetas))
    for col, html in zip(cols, tarjetas):
        with col:
            mostrar(html)


def descargas(df, nombre_base: str, hoja: str = "Datos", key: str = "dl"):
    """Dos botones de descarga (CSV y Excel) para un DataFrame, uno junto al otro."""
    import io
    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
    c1, c2, _ = st.columns([1, 1, 2.2])
    with c1:
        st.download_button(
            "Descargar CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{nombre_base}.csv", mime="text/csv",
            icon=":material/download:", key=f"{key}_csv", use_container_width=True,
        )
    with c2:
        try:
            salida = io.BytesIO()
            import pandas as pd
            with pd.ExcelWriter(salida, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name=hoja[:31])
            st.download_button(
                "Descargar Excel", data=salida.getvalue(),
                file_name=f"{nombre_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:", key=f"{key}_xlsx", use_container_width=True,
            )
        except Exception:
            st.caption("No se pudo generar el archivo de Excel.")
