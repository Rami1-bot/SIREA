# utils/tema.py
"""
Tema visual compartido de SIREA (Sistema de Recepcion de Reportes Epidemiologicos con Agentes (SIREA)
Epidemiologicos) - EsSalud / OIIS.

Un solo lugar para: colores, iconos, CSS global, encabezado, pie de
pagina con los logos y los componentes pequenos (tarjetas de cifra,
etiquetas de estado, avisos, barras de avance) que usan todas las
pantallas. Asi las pantallas de las redes y el panel de administracion
se ven como un mismo sistema.

Reglas del diseno:
  * Azul EsSalud (#0077C8) para acciones y pie de pagina; azul del
    sello OIIS (#1D3F76) para titulos. Tipografia Nunito Sans.
  * Tarjetas redondeadas, degradado azul en la cabecera del inicio y en
    los acuses (rojo para el envio tardio), sin emojis y sin iconos
    cargados desde internet (todo es SVG incrustado).
  * El estado nunca se indica solo con color: siempre lleva texto.
"""

import base64
import re
from pathlib import Path

import streamlit as st

# ============================================================
# COLORES
# ============================================================

AZUL = "#0077C8"        # azul EsSalud oficial (Pantone 3005C): botones, enlaces, pie
AZUL_HOVER = "#005C9C"
NAVY = "#1D3F76"        # azul del sello OIIS (titulos)
CELESTE = "#41B6E6"     # celeste EsSalud (Pantone 298C): acentos y fondos suaves
CELESTE_SUAVE = "#E6F4FB"
# Lila = "Diagnostico" en la senaletica de EsSalud. En SIREA marca TODO lo que
# produjo un asistente de IA (borradores, chips, panel de agentes) hasta que
# una persona lo valida; al validarse pasa a verde ("Tratamiento").
LILA = "#6E3FA3"
LILA_HOVER = "#55307F"
LILA_SUAVE = "#F3EDFA"
LILA_BORDE = "#CDB8E8"
TINTA = "#14202B"
MUTE = "#4F6070"
LINEA = "#D9E7F3"
FONDO = "#F4F8FC"

# tono -> (texto, fondo, borde)
TONOS = {
    "ok":   ("#1E6B3A", "#E6F4EA", "#A9D8BA"),
    "warn": ("#7A5A00", "#FFF4D6", "#EBD08A"),
    "bad":  ("#9E2B2B", "#FDE8E8", "#F0B8B8"),
    "info": ("#004F85", "#E3F0FA", "#B6D6EC"),
    "mute": ("#33424F", "#EEF1F4", "#C9D1D8"),
    "dup":  ("#8A3F05", "#FFF1E4", "#F0B27A"),
    "ia":   ("#55307F", "#F3EDFA", "#CDB8E8"),   # generado por IA, pendiente de validar
}

_RAIZ = Path(__file__).resolve().parent.parent
_ASSETS = _RAIZ / "assets"


# ============================================================
# UTILIDADES
# ============================================================

def compactar(html: str) -> str:
    """
    Quita sangrias y lineas vacias de un bloque HTML.

    Markdown corta el HTML en una linea vacia y trata 4+ espacios de
    sangria como codigo; compactar evita ambas cosas.
    """
    partes = []
    for linea in html.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        # Si una frase continua en la linea siguiente se conserva el espacio.
        if partes and not partes[-1].endswith(">") and not linea.startswith("<"):
            partes.append(" ")
        partes.append(linea)
    return "".join(partes)


def mostrar(html: str):
    """Renderiza un bloque HTML (compactado) en la pagina."""
    st.markdown(compactar(html), unsafe_allow_html=True)


_cache_uri = {}


def logo_uri(nombre: str) -> str:
    """Devuelve un archivo de assets/ como data URI (o '' si no existe)."""
    if nombre in _cache_uri:
        return _cache_uri[nombre]
    ruta = _ASSETS / nombre
    uri = ""
    try:
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg",
            ".svg": "image/svg+xml", ".ico": "image/x-icon",
        }.get(ruta.suffix.lower(), "application/octet-stream")
        uri = f"data:{mime};base64,{base64.b64encode(ruta.read_bytes()).decode()}"
    except Exception:
        uri = ""
    _cache_uri[nombre] = uri
    return uri


def ruta_favicon():
    """Ruta del favicon para st.set_page_config(page_icon=...)."""
    ruta = _ASSETS / "favicon.png"
    return str(ruta) if ruta.exists() else None


# ============================================================
# DATOS COMUNES DE LA SEMANA
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def periodo_semana(anio: int, semana: int) -> str:
    """
    Texto del periodo de una semana epidemiologica (domingo a sabado),
    p. ej. '27/09 – 03/10/2026'. Devuelve '—' si no se puede calcular.
    """
    try:
        from datetime import datetime, timedelta
        from src.db_manager import get_db_manager
        info = get_db_manager().obtener_anio_epidemiologico(int(anio))
        inicio = datetime.strptime(str(info["fecha_inicio"])[:10], "%Y-%m-%d")
        desde = inicio + timedelta(days=(int(semana) - 1) * 7)
        hasta = desde + timedelta(days=6)
        return f"{desde:%d/%m} – {hasta:%d/%m/%Y}"
    except Exception:
        return "—"


def fecha_corte_info():
    """
    Fecha de corte configurada, lista para mostrar.

    Devuelve (texto 'dd/mm/aaaa hh:mm', datetime sin zona horaria o None).
    Si no hay fecha configurada devuelve ('No configurada', None).
    """
    from datetime import datetime
    try:
        from src.config import Config
        crudo = (Config.get_fecha_corte() or "").strip()
    except Exception:
        crudo = ""
    if not crudo:
        return "No configurada", None
    for formato in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
                    '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            dt = datetime.strptime(crudo, formato)
            if formato in ('%Y-%m-%d', '%d/%m/%Y'):
                dt = dt.replace(hour=23, minute=59)
            return dt.strftime('%d/%m/%Y %H:%M'), dt
        except ValueError:
            continue
    return crudo, None


def texto_dias_restantes(dt) -> str:
    """'faltan 4 días', 'vence hoy' o 'plazo vencido' respecto a la hora de Lima."""
    if dt is None:
        return ""
    try:
        from src.config import Config
        ahora = Config.obtener_fecha_actual().replace(tzinfo=None)
    except Exception:
        from datetime import datetime
        ahora = datetime.now()
    if ahora > dt:
        return "plazo vencido"
    dias = (dt.date() - ahora.date()).days
    if dias == 0:
        return "vence hoy"
    return "falta 1 día" if dias == 1 else f"faltan {dias} días"


_DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "setiembre", "octubre", "noviembre", "diciembre")


def fecha_larga_es(dt) -> str:
    """'martes 13 de octubre, 23:59' (vacío si dt es None)."""
    if dt is None:
        return ""
    return f"{_DIAS_ES[dt.weekday()]} {dt.day} de {_MESES_ES[dt.month - 1]}, {dt:%H:%M}"


def correo_contacto() -> str:
    """Correo de consultas de la OIIS ('' si no está configurado)."""
    try:
        from src.config import Config
        return (Config.CONTACTO_EMAIL or "").strip()
    except Exception:
        return ""


# ============================================================
# ICONOS (SVG incrustados, sin dependencias externas)
# ============================================================

_ICONOS = {
    "ia": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    "lupa": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "dash": '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "alerta": '<path d="M12 3 2.5 20h19L12 3z"/><path d="M12 10v4.5"/><path d="M12 17.5v.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8v.01"/>',
    "subir": '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    "barras": '<path d="M5 20V11M12 20V4M19 20v-6"/>',
    "escudo": '<path d="M12 3l7 3v5c0 5-3.2 8.4-7 10-3.8-1.6-7-5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    "candado": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    "nube": '<path d="M7 18a4 4 0 0 1-.6-7.96A6 6 0 0 1 18 9.5a4.2 4.2 0 0 1-.5 8.5H7z"/>',
    "flecha": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "basura": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "descarga": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    "calendario": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4m8-4v4M4 10h16"/>',
    "campana": '<path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "usuario": '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-3.5 3.6-6 8-6s8 2.5 8 6"/>',
    "correo": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>',
    "casa": '<path d="M4 20V8l8-4 8 4v12"/><path d="M9 20v-6h6v6M4 20h16"/>',
    "llave": '<path d="M8 15a4 4 0 1 1 3.9-5H21v3h-2v2h-3v-2h-4.1A4 4 0 0 1 8 15z"/>',
    "sal": '<path d="M14 7V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-2M10 12h10m-3-3 3 3-3 3"/>',
    "circulo": '<circle cx="12" cy="12" r="8"/>',
    "copia": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
    "mensaje": '<path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1z"/>',
    "lapiz": '<path d="M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1z"/><path d="M14 7l3 3"/>',
    "enviar": '<path d="M21 3 10 14"/><path d="M21 3l-7 18-4-7-7-4 18-7z"/>',
}


def icono(nombre: str, size: int = 18, color: str = "currentColor", sw: float = 2) -> str:
    """SVG de linea (24x24) listo para incrustar en HTML."""
    trazo = _ICONOS.get(nombre, "")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" '
        f'style="flex:none;vertical-align:middle">{trazo}</svg>'
    )


def marca_svg(size: int = 40, invertida: bool = False) -> str:
    """Marca del sistema: barras de una curva epidemiologica. `invertida`: fondo blanco, barras azules."""
    fondo, barra_c = (("#FFFFFF", AZUL) if invertida else (AZUL, "#FFFFFF"))
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 40 40" role="img" '
        f'aria-label="SIREA" style="flex:none"><rect width="40" height="40" rx="10" fill="{fondo}"/>'
        f'<rect x="9" y="21" width="4.5" height="9" rx="1" fill="{barra_c}"/>'
        f'<rect x="15.5" y="15" width="4.5" height="15" rx="1" fill="{barra_c}"/>'
        f'<rect x="22" y="9" width="4.5" height="21" rx="1" fill="{barra_c}"/>'
        f'<rect x="28.5" y="17" width="4.5" height="13" rx="1" fill="{barra_c}"/></svg>'
    )


# ============================================================
# COMPONENTES HTML PEQUENOS
# ============================================================

def chip(texto: str, tono: str = "info", ico: str = None) -> str:
    fg, bg, bd = TONOS[tono]
    i = icono(ico, 14, fg, 2.2) if ico else ""
    return (
        f'<span class="sire-chip" style="color:{fg};background:{bg};border:1px solid {bd}">'
        f'{i}{texto}</span>'
    )


def barra(pct: float, tono: str = None, ancho_texto: bool = True) -> str:
    """Barra de avance con el porcentaje escrito. Verde >=90, ambar >=60, rojo <60."""
    pct = max(0, min(100, float(pct)))
    if tono is None:
        tono = "ok" if pct >= 90 else ("warn" if pct >= 60 else "bad")
    fg = TONOS[tono][0]
    p = int(pct) if pct == int(pct) else round(pct, 1)
    txt = f'<span class="sire-bar-n" style="color:{fg}">{p} %</span>' if ancho_texto else ""
    return (
        f'<div class="sire-bar"><div class="sire-bar-pista" role="progressbar" '
        f'aria-valuenow="{p}" aria-valuemin="0" aria-valuemax="100">'
        f'<div style="width:{pct}%;background:{fg}"></div></div>{txt}</div>'
    )


def kpi(etiqueta: str, valor, sub: str = "", tono: str = None, ico: str = None) -> str:
    color = TONOS[tono][0] if tono else NAVY
    bg = TONOS[tono][1] if tono else "#E3F0FA"
    acento = TONOS[tono][0] if tono else AZUL
    i = f'<span class="sire-kpi-ico" style="background:{bg};color:{color}">{icono(ico, 18)}</span>' if ico else ""
    s = f'<div class="sire-kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="sire-kpi" style="--k:{acento}"><div class="sire-kpi-top"><span>{etiqueta}</span>{i}</div>'
        f'<div class="sire-kpi-val" style="color:{color}">{valor}</div>{s}</div>'
    )


def aviso(tono: str, titulo: str, texto: str = "") -> str:
    fg, bg, bd = TONOS[tono]
    ico = {"ok": "check", "warn": "alerta", "bad": "alerta", "info": "info", "mute": "info"}[tono]
    t = f'<div>{texto}</div>' if texto else ""
    return (
        f'<div class="sire-aviso" role="note" style="background:{bg};border:1px solid {bd};'
        f'border-left:4px solid {fg}">{icono(ico, 20, fg)}'
        f'<div><div class="sire-aviso-t" style="color:{fg}">{titulo}</div>{t}</div></div>'
    )


def mostrar_aviso(tono: str, titulo: str, texto: str = ""):
    mostrar(aviso(tono, titulo, texto))


def titulo_pagina(titulo: str, subtitulo: str = "", migas: str = "", derecha: str = ""):
    """Cabecera de pagina: migas, titulo, subtitulo y (opcional) etiquetas a la derecha."""
    m = f'<div class="sire-migas">{migas}</div>' if migas else ""
    s = f'<p class="sire-sub">{subtitulo}</p>' if subtitulo else ""
    d = f'<div class="sire-titulo-der">{derecha}</div>' if derecha else ""
    mostrar(f'<div class="sire-titulo"><div>{m}<h1>{titulo}</h1>{s}</div>{d}</div>')


def hero_acuse(tono: str, titulo: str, subtitulo: str, codigo: str = "", migas: str = "") -> None:
    """
    Cabecera a todo lo ancho de la pantalla de acuse: azul (recibido a tiempo),
    roja (envío tardío) o ámbar (con observaciones). Muestra el código de seguimiento.
    """
    ico = {"azul": icono("check", 34, "#FFFFFF", 2.6), "rojo": icono("reloj", 34, "#FFFFFF", 2.4),
           "ambar": icono("alerta", 34, "#FFFFFF", 2.4), "naranja": icono("copia", 34, "#FFFFFF", 2.2)}.get(tono, "")
    cod = (
        f'<div class="sire-acuse-cod"><span>Código de seguimiento</span><b>{codigo}</b></div>' if codigo else ""
    )
    m = f'<div class="sire-acuse-migas">{migas}</div>' if migas else ""
    mostrar(
        f'<div class="sire-acuse sire-acuse-{tono}"><div class="sire-acuse-in">'
        f'<div class="sire-acuse-txt">{m}<div class="sire-acuse-ico">{ico}</div>'
        f'<span class="sire-acuse-eye">Acuse de recibo</span><h1>{titulo}</h1><p>{subtitulo}</p></div>{cod}'
        f'</div></div>'
    )


def tarjeta(titulo: str, cuerpo: str, extra_clase: str = "") -> str:
    """Tarjeta con cabecera gris (titulo) y cuerpo. Devuelve HTML."""
    return (
        f'<div class="sire-card {extra_clase}"><div class="sire-card-h">{titulo}</div>'
        f'<div class="sire-card-b">{cuerpo}</div></div>'
    )


def filas(pares) -> str:
    """Filas 'etiqueta ... valor' separadas por una linea fina. pares = [(etiqueta, valor_html)]."""
    return "".join(
        f'<div class="sire-fila"><span>{a}</span><span>{b}</span></div>' for a, b in pares
    )


def detalle(pares) -> str:
    """Tabla de detalle (etiqueta a la izquierda, valor en negrita). pares = [(etiqueta, valor_html)]."""
    return '<div class="sire-det">' + "".join(
        f'<div class="sire-det-f"><div class="sire-det-k">{a}</div><div class="sire-det-v">{b}</div></div>'
        for a, b in pares
    ) + '</div>'


def codigo_box(etiqueta: str, codigo: str) -> str:
    return (
        f'<div class="sire-codigo"><div class="sire-codigo-k">{etiqueta}</div>'
        f'<div class="sire-codigo-v">{codigo}</div></div>'
    )


def seccion(num, titulo: str):
    """Cabecera numerada de una tarjeta de formulario (usar dentro de un container con key 'sec_*')."""
    mostrar(f'<div class="sire-sec-h"><span class="sire-sec-n">{num}</span><h2>{titulo}</h2></div>')


def lista_estado(items) -> str:
    """
    Lista de centros con su estado. items = [(texto, tono, etiqueta)] con
    tono 'ok' (enviado) | 'warn' (pendiente) | 'bad' (atrasado).
    El estado siempre lleva icono y texto.
    """
    ico = {"ok": "check", "warn": "reloj", "bad": "alerta", "mute": "info", "info": "info"}
    lis = "".join(
        f'<li>{icono(ico[t], 18, TONOS[t][0], 2.2)}<span class="grow">{texto}</span>'
        f'<span style="font-size:13px;font-weight:600;color:{TONOS[t][0]}">{etq}</span></li>'
        for texto, t, etq in items
    )
    return f'<ul class="sire-lista">{lis}</ul>'


# ============================================================
# ENCABEZADO Y PIE (pantallas de las redes)
# ============================================================

def _ir(pagina: str, seccion: str = None):
    # Al cambiar de pantalla se descarta lo que quedara a medias del envio.
    st.session_state.usuario_envio_exitoso = False
    st.session_state.usuario_datos_envio = {}
    st.session_state.pop('_dup_envio_pendiente', None)
    if pagina != 'usuario':
        st.session_state.usuario_red_seleccionada = None
        st.session_state.usuario_centros_disponibles = []
        st.session_state.usuario_autocompletado = None
    if pagina != 'red_progreso' and st.session_state.get('red_logueada'):
        # Al salir de "Mi progreso" se cierra la sesion de la red.
        try:
            from src.auth_red import get_red_auth_manager
            if st.session_state.get('red_token'):
                get_red_auth_manager().logout(st.session_state.red_token)
        except Exception:
            pass
        st.session_state.red_logueada = False
        st.session_state.red_token = None
        st.session_state.red_actual = None
    st.session_state.pagina = pagina
    if seccion:
        st.session_state.seccion_admin = seccion
    st.rerun()


def chip_semana() -> str:
    """Etiqueta 'Semana N · AAAA' de la semana activa ('' si no se puede leer)."""
    try:
        from src.config import Config
        semana, anio = Config.get_semana_actual(), Config.get_anio_actual()
        if semana and anio:
            return f'<span class="sire-semana-chip">{icono("calendario", 14, "currentColor", 2.4)}Semana {semana} · {anio}</span>'
    except Exception:
        pass
    return ""


def encabezado_publico(activo: str = "inicio", nav: bool = True):
    """
    Barra superior de las pantallas de las redes: logo EsSalud (azul, sin
    fondo) + marca SIREA a la izquierda, navegacion y semana activa a la derecha.

    activo: 'inicio' | 'enviar' | 'progreso' | 'admin'
    nav: False muestra solo la marca (pantallas sin navegacion).
    """
    logo = logo_uri("essalud-azul.png")
    with st.container(key="sire_hdr"):
        if nav:
            c_marca, c1, c2, c3, c4, c5 = st.columns([4.4, 0.9, 1.5, 1.3, 1.7, 1.9], vertical_alignment="center")
        else:
            c_marca, c5 = st.columns([5, 1.9], vertical_alignment="center")
        with c_marca:
            mostrar(f"""
            <div class="sire-brand">
              <img src="{logo}" alt="EsSalud" class="sire-brand-essalud">
              <span class="sire-brand-sep"></span>
              {marca_svg(40)}
              <div class="sire-brand-txt"><b>SIRE<span class="sire-a">A</span></b><small>Sistema de Recepción de Reportes Epidemiológicos con Agentes</small></div>
            </div>
            """)
        with c5:
            semana_html = chip_semana()
            if semana_html:
                mostrar(f'<div style="display:flex;justify-content:flex-end">{semana_html}</div>')
        if not nav:
            return
        items = [
            (c1, "inicio", "Inicio", "landing", None),
            (c2, "enviar", "Enviar reporte", "usuario", None),
            (c3, "progreso", "Mi progreso", "red_progreso", None),
            (c4, "admin", "Administración", "admin", "Dashboard"),
        ]
        for col, clave, texto, pagina, seccion in items:
            with col:
                if st.button(
                    texto,
                    key=f"nav_pub_{clave}",
                    type="primary" if clave == activo else "secondary",
                    use_container_width=True,
                ):
                    _ir(pagina, seccion)


def pie_pagina(margen: int = 56):
    """Pie de pagina azul con los logos de EsSalud (blanco) y de la OIIS."""
    mostrar(f"""
    <div class="sire-foot" style="margin-top:{int(margen)}px"><div class="sire-foot-in">
      <div class="sire-foot-logos">
        <img src="{logo_uri('essalud-blanco.png')}" alt="EsSalud" class="sire-foot-essalud">
        <span class="sire-foot-sep"></span>
        <img src="{logo_uri('oiis-blanco.svg')}" alt="OIIS - Oficina de Inteligencia e Información Sanitaria" class="sire-foot-oiis">
      </div>
      <div class="sire-foot-txt">
        <b>EsSalud · Oficina de Inteligencia e Información Sanitaria (OIIS)</b>
        <span>Seguro Social de Salud del Perú</span>
        <span class="sire-foot-sub">SIRE<span class="sire-a-foot">A</span> · Sistema de Recepción de Reportes Epidemiológicos con Agentes · v3.3 · © 2026 EsSalud</span>
      </div>
    </div></div>
    """)


# ============================================================
# CSS GLOBAL
# ============================================================

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&display=swap');

:root{
  --ink:#14202B; --mute:#4F6070; --line:#D9E7F3; --bg:#F4F8FC;
  --azul:#0077C8; --azul-h:#005C9C; --navy:#1D3F76;
  --ok:#1E6B3A; --ok-bg:#E6F4EA; --ok-bd:#A9D8BA;
  --warn:#7A5A00; --warn-bg:#FFF4D6; --warn-bd:#EBD08A;
  --bad:#B42318; --bad-t:#9E2B2B; --bad-bg:#FDE8E8; --bad-bd:#F0B8B8;
  --r:12px; --r-lg:16px; --sombra:0 1px 2px rgba(20,60,100,.04);
}

/* ---------- base ---------- */
html, body, .stApp{ background:var(--bg) !important; color:var(--ink); }
.stApp, .stApp p, .stApp label, .stApp li, .stApp td, .stApp th, .stApp input,
.stApp textarea, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp [data-baseweb] , .stApp [data-testid="stMarkdownContainer"]{
  font-family:'Nunito Sans', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}
.stApp{ font-variant-numeric:tabular-nums; }
.stApp [data-testid="stIconMaterial"], .stApp [data-testid="stIconMaterial"] *{
  font-family:'Material Symbols Rounded','Material Icons' !important;
}
/* los iconos de Font Awesome ya no se cargan: se ocultan los restos */
i.fas, i.far, i.fab, i.fa{ display:none !important; }

div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdown"] style),
div[data-testid="stElementContainer"]:has(style){ display:none !important; }
[data-testid="stHeader"]{ display:none !important; }
[data-testid="stHeaderActionElements"]{ display:none !important; }
[data-testid="stMainBlockContainer"]{ min-height:100vh; }
div[data-testid="stElementContainer"]:has(.sire-foot){ margin-top:auto; }
[data-testid="stToolbar"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stDecoration"], #MainMenu, footer{ display:none !important; }
.block-container, [data-testid="stMainBlockContainer"]{ max-width:1240px; padding:0 24px 0 !important; }
[data-testid="stMain"], [data-testid="stAppViewContainer"]{ overflow-x:hidden; }
a{ color:var(--azul); }
a:hover{ color:var(--azul-h); }
:focus-visible{ outline:3px solid rgba(0,109,176,.35) !important; outline-offset:2px; }

h1,h2,h3,h4,.stApp h1,.stApp h2,.stApp h3,.stApp h4{ color:var(--navy); letter-spacing:0; font-weight:800 !important; }
h1{ font-size:32px !important; line-height:1.2 !important; }
h2{ font-size:22px !important; }
h3{ font-size:18px !important; }
[data-testid="stCaptionContainer"], .stCaption{ color:var(--mute) !important; font-size:13.5px !important; }
hr{ border:0 !important; border-top:1px solid var(--line) !important; margin:24px 0 !important; }

/* ---------- botones ---------- */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button,
[data-testid^="stBaseButton"]{
  min-height:46px; border-radius:var(--r) !important; font-weight:800 !important; font-size:15px !important;
  box-shadow:none !important; transform:none !important; text-shadow:none !important;
  letter-spacing:0 !important; transition:background .15s, border-color .15s, box-shadow .15s;
}
.stButton > button[kind="secondary"], .stDownloadButton > button, [data-testid="stBaseButton-secondary"],
[data-testid="stFormSubmitButton"] > button[kind="secondary"]{
  background:#FFFFFF !important; color:var(--azul-h) !important; border:1.5px solid var(--azul) !important;
}
.stButton > button[kind="secondary"]:hover, .stDownloadButton > button:hover, [data-testid="stBaseButton-secondary"]:hover{
  background:#EEF6FC !important; border-color:var(--azul) !important; color:var(--azul-h) !important;
}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"],
[data-testid="stFormSubmitButton"] > button[kind="primary"]{
  background:var(--azul) !important; color:#FFFFFF !important; border:1.5px solid var(--azul) !important;
  box-shadow:0 8px 18px rgba(0,109,176,.26) !important;
}
.stButton > button[kind="primary"] *, [data-testid="stBaseButton-primary"] *, [data-testid="stBaseButton-primaryFormSubmit"] *{ color:#FFFFFF !important; }
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover{
  background:var(--azul-h) !important; border-color:var(--azul-h) !important;
}
button:disabled, [data-testid^="stBaseButton"]:disabled{
  background:#E3EAF1 !important; color:#4A5560 !important; border-color:#E3EAF1 !important; cursor:not-allowed !important; box-shadow:none !important;
}
button:disabled *{ color:#4A5560 !important; }

/* ---------- campos ---------- */
[data-testid="stWidgetLabel"] p, label[data-testid="stWidgetLabel"] p{
  font-size:14px !important; font-weight:800 !important; color:var(--navy) !important;
}
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"]{
  background:#FFFFFF !important; border-radius:var(--r) !important;
}
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"]{
  border:1.5px solid #C4D6E6 !important; min-height:48px;
}
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within, div[data-baseweb="textarea"]:focus-within{
  border-color:var(--azul) !important; box-shadow:0 0 0 3px rgba(0,109,176,.22) !important;
}
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea{ font-size:16px !important; font-weight:600 !important; color:var(--ink) !important; }
.stApp input, .stApp textarea{ background:#FFFFFF !important; }
.stApp input::placeholder, .stApp textarea::placeholder{ color:#6B7C8C !important; font-weight:400 !important; }
/* Streamlit 1.5x+ (react-aria): el borde lo lleva el contenedor del campo */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"],
.react-aria-ComboBox > [role="group"], [data-testid="stDateInputField"], [data-testid="stTimeInputField"]{
  background:#FFFFFF !important; border:1.5px solid #C4D6E6 !important; border-radius:var(--r) !important; min-height:48px;
}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
.react-aria-ComboBox > [role="group"]:focus-within{ border-color:var(--azul) !important; box-shadow:0 0 0 3px rgba(0,109,176,.22) !important; }
[data-baseweb="tag"], span[data-tag]{ background:#E3F0FA !important; color:var(--navy) !important; border-radius:8px !important; }
[data-baseweb="tag"] span, [data-baseweb="tag"] svg, span[data-tag] span, span[data-tag] svg, span[data-tag] button{ color:var(--navy) !important; fill:var(--navy) !important; }
[data-baseweb="menu"] li, [data-baseweb="popover"] [role="option"], [data-testid="stSelectboxVirtualDropdown"] li{ font-size:15px !important; }
[data-testid="stFileUploaderDropzone"]{
  background:#F1F8FD !important; border:2px dashed #9CC3E3 !important; border-radius:var(--r-lg) !important; padding:28px 20px !important;
}
[data-testid="stFileUploaderDropzone"]{ flex-direction:column; align-items:center; text-align:center; gap:12px; }
[data-testid="stFileUploaderDropzoneInstructions"]{ flex-direction:column; align-items:center; }
[data-testid="stFileUploaderDropzoneInstructions"] > *{ display:none !important; }
[data-testid="stFileUploaderDropzoneInstructions"]::before{ content:"Arrastre su archivo aquí · Formato ZIP"; font-size:16px; font-weight:700; color:var(--navy); }
.st-key-panel_cred_masiva [data-testid="stFileUploaderDropzoneInstructions"]::before{ content:"Arrastre su archivo aquí · CSV o Excel"; }
[data-testid="stFileUploaderDropzone"] button{ min-height:44px; }
[data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] > *{ display:none !important; }
[data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"]::after{ content:"Seleccionar archivo"; font-size:15px; font-weight:800; color:var(--azul-h); }
[data-testid="stCheckbox"] label, [data-testid="stRadio"] label{ font-size:15px; }

/* ---------- tarjetas, formularios y expanders ---------- */
[data-testid="stForm"]{ background:#FFFFFF; border:1px solid var(--line) !important; border-radius:var(--r-lg) !important; padding:24px !important; box-shadow:var(--sombra); }
[data-testid="stExpander"]{ background:#FFFFFF; border:1px solid var(--line) !important; border-radius:var(--r-lg) !important; box-shadow:var(--sombra); overflow:hidden; }
[data-testid="stExpander"] summary{ font-weight:800; color:var(--navy); }
[data-testid="stMetric"]{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:16px 20px; }
[data-testid="stMetricLabel"] p{ font-size:12.5px !important; font-weight:800 !important; letter-spacing:.07em; text-transform:uppercase; color:var(--mute) !important; }
[data-testid="stMetricValue"]{ color:var(--navy); font-weight:800; font-variant-numeric:tabular-nums; }
[data-testid="stAlert"]{ border-radius:var(--r) !important; border:1px solid var(--line); }
[data-testid="stAlert"] p{ font-size:15px !important; }
[data-testid="stDataFrame"], [data-testid="stTable"]{ border:1px solid var(--line); border-radius:var(--r); overflow:hidden; background:#FFFFFF; }
[data-testid="stTabs"] [role="tab"]{ font-weight:800; }
[data-testid="stTabs"] [aria-selected="true"]{ color:var(--navy) !important; }
[data-testid="stPlotlyChart"]{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:8px; }

/* ---------- clases del markup existente (restyle sin tocar cada pagina) ---------- */
.main-header{
  background:#FFFFFF !important; border:1px solid var(--line); border-left:5px solid var(--azul);
  border-radius:var(--r-lg) !important; padding:18px 24px !important; margin:0 0 24px !important; box-shadow:var(--sombra) !important;
}
.main-header h1{ color:var(--navy) !important; font-size:26px !important; margin:0 !important; display:block !important; }
.main-header p{ color:var(--mute) !important; margin:4px 0 0 !important; font-size:15px !important; }
.section-title{
  color:var(--navy) !important; background:transparent !important; border:0 !important;
  border-bottom:1px solid var(--line) !important; border-radius:0 !important;
  padding:0 0 8px !important; margin:32px 0 16px !important; font-size:20px !important; font-weight:800 !important;
  display:block !important;
}
.table-title{
  color:var(--navy) !important; background:#FFFFFF !important; border:1px solid var(--line) !important;
  border-bottom:0 !important; border-radius:var(--r-lg) var(--r-lg) 0 0 !important; padding:14px 20px !important; margin:24px 0 0 !important;
  font-size:17px !important; font-weight:800 !important; display:block !important;
}
.stat-card, .info-card{
  background:#FFFFFF !important; border:1px solid var(--line) !important; border-radius:var(--r-lg) !important;
  box-shadow:var(--sombra) !important; transform:none !important; padding:16px 20px !important; margin:0 !important;
}
.stat-card h3{ color:var(--navy); font-size:30px !important; font-weight:800 !important; }
.stat-card p, .info-card p{ color:var(--mute); font-size:14px !important; }
.info-card h4{ color:var(--mute) !important; font-size:12.5px !important; text-transform:uppercase; letter-spacing:.07em; margin:0 0 6px !important; }
.info-card h2{ color:var(--navy) !important; font-size:28px !important; margin:0 !important; }
.icon-circle{ display:none !important; }
.alerta-roja, .alerta-amarilla, .zip-warning, .info-message, .excluidos-info{
  border-radius:var(--r) !important; padding:12px 16px !important; font-size:14px; color:var(--ink);
}
.alerta-roja{ background:var(--bad-bg) !important; border:1px solid var(--bad-bd) !important; border-left:5px solid var(--bad) !important; }
.alerta-amarilla, .zip-warning{ background:var(--warn-bg) !important; border:1px solid var(--warn-bd) !important; border-left:5px solid #B7791F !important; }
.info-message, .excluidos-info{ background:#E8F1F8 !important; border:1px solid #B6D6EC !important; border-left:5px solid var(--azul) !important; }

/* ---------- componentes SIREA ---------- */
/* ---------- SIREA: identidad de la "A" (agentes) ---------- */
.sire-brand-txt b .sire-a{ color:#6E3FA3; }
.sire-a-foot{ color:#D9C7F2; font-weight:800; }
/* ---------- SIREA: componentes de IA (lila = diagnostico, pendiente de validar) ---------- */
.sirea-borrador{ position:relative; background:#FBF9FE; border:1.5px dashed #CDB8E8; border-radius:var(--r-lg); padding:18px 20px 16px; margin:8px 0 14px; color:#1F2A37; font-size:14.5px; line-height:1.55; }
.sirea-borrador.validado{ background:#F4FBF6; border:1.5px solid #A9D8BA; }
.sirea-borrador-cab{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.sirea-borrador-meta{ font-size:12px; color:var(--mute); font-weight:600; }
.sirea-borrador p{ margin:0 0 8px; }
.sirea-borrador ul{ margin:4px 0 8px 18px; }
.sirea-pie-ia{ margin-top:10px; padding-top:8px; border-top:1px solid #E8E0F3; font-size:12px; color:#55307F; font-weight:700; display:flex; align-items:center; gap:6px; }
.sirea-agente{ background:#FFFFFF; border:1px solid var(--line); border-left:5px solid #6E3FA3; border-radius:var(--r-lg); padding:16px 18px 14px; box-shadow:var(--sombra); min-height:196px; display:flex; flex-direction:column; gap:8px; margin-bottom:14px; }
.sirea-agente.verde{ border-left-color:#1E6B3A; }
.sirea-agente.ambar{ border-left-color:#C9A000; }
.sirea-agente.rojo{ border-left-color:#B42318; }
.sirea-agente.gris{ border-left-color:#9AA6B2; background:#F7F9FB; }
.sirea-agente-cab{ display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
.sirea-agente-nom{ font-size:15.5px; font-weight:800; color:var(--navy); line-height:1.2; }
.sirea-agente-sub{ font-size:12px; color:var(--mute); font-weight:700; letter-spacing:.05em; text-transform:uppercase; }
.sirea-agente-txt{ font-size:13.5px; color:#33424F; line-height:1.5; flex:1; }
.sirea-agente-pie{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.sirea-semaforo{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
.sirea-semaforo i{ width:10px; height:10px; border-radius:999px; display:inline-block; }
.sirea-prov{ display:inline-flex; align-items:center; gap:5px; font-size:11.5px; font-weight:700; color:#55307F; background:#F3EDFA; border:1px solid #CDB8E8; border-radius:999px; padding:2px 9px; }
.sirea-chat-u{ background:#E6F4FB; border-radius:14px 14px 4px 14px; padding:10px 14px; margin:6px 0 6px 18%; font-size:14px; }
.sirea-chat-a{ background:#FBF9FE; border:1px solid #E8E0F3; border-radius:14px 14px 14px 4px; padding:12px 14px; margin:6px 18% 10px 0; font-size:14px; line-height:1.55; }
.sirea-chat-a .sirea-pie-ia{ margin-top:8px; }
/* SIREA 3.0: propuestas del Agente Operativo (lila punteado = propuesta de la IA pendiente) */
[class*="st-key-prop_"]{ background:#FBF9FE; border:1.5px dashed #CDB8E8; border-radius:var(--r-lg); padding:14px 18px 10px; margin:0 0 14px; }
.sirea-prop-cab{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.sirea-prop-tit{ font-size:16px; font-weight:800; color:var(--navy); }
.sirea-prop-sub{ font-size:12.5px; color:var(--mute); font-weight:600; margin-top:2px; }
.sirea-prop-just{ margin:8px 0 4px; font-size:14px; color:#1F2A37; line-height:1.5; }
.sirea-prop-dato{ font-size:13.5px; color:#33424F; margin:2px 0; }
.sirea-prop-dato b{ color:var(--navy); }
.sirea-traza{ border-left:3px solid #CDB8E8; padding:4px 0 4px 12px; margin:0 0 6px; font-size:13.5px; }
.sirea-traza b{ color:#55307F; }
/* SIREA 3.2: recordatorio por tipo, información interna, vista previa, asistente */
table.sirea-falta{ width:100%; border-collapse:collapse; margin:4px 0 10px; font-size:13.5px; }
table.sirea-falta th{ text-align:left; background:#F2F6FA; color:#34495E; font-weight:600; padding:6px 8px; border-bottom:1px solid #DCE3EA; }
table.sirea-falta td{ padding:6px 8px; border-bottom:1px solid #EEF2F6; vertical-align:top; }
.sirea-interno{ background:#F7F3FC; border:1px dashed #B79AD9; border-radius:10px; padding:10px 12px; margin:6px 0 10px; font-size:13.5px; color:#3D2A5C; }
.sirea-interno-tit{ display:block; font-size:11.5px; font-weight:700; letter-spacing:.02em; text-transform:uppercase; color:#6B3FA0; margin-bottom:4px; }
.sirea-preview{ background:#FFFFFF; border:1px solid #DCE3EA; border-radius:10px; padding:12px 14px; font-size:13.5px; white-space:pre-wrap; color:#1F2D3A; max-height:420px; overflow:auto; }
.sirea-preview hr{ border:none; border-top:1px solid #EEF2F6; margin:8px 0; }
.sirea-pasos{ display:flex; flex-direction:column; gap:10px; margin:4px 0 14px; }
.sirea-paso{ display:flex; gap:14px; align-items:flex-start; background:#FFFFFF; border:1px solid #DCE3EA; border-radius:12px; padding:12px 14px; font-size:14px; color:#1F2D3A; }
.sirea-paso-n{ flex:0 0 32px; height:32px; border-radius:50%; background:#EDE4F8; color:#55307F; font-weight:800; display:flex; align-items:center; justify-content:center; }
.sirea-asist .sirea-chat-u{ margin-left:8%; font-size:13.5px; color:#12324F; }
.sirea-asist .sirea-chat-a{ margin-right:4%; font-size:13.5px; color:#2B2140; }
.sirea-pend{ padding:2px 0 0 12px; }
.sirea-pend-cifra{ font-size:30px; font-weight:800; line-height:1.1; margin:6px 0 2px; font-variant-numeric:tabular-nums; }
.sirea-pend-lista{ margin:4px 0 6px 18px; font-size:13.5px; color:#33424F; }
.sirea-pend-lista li{ margin:2px 0; }
.sirea-eval-ok{ color:#1E6B3A; font-weight:800; }
.sirea-eval-no{ color:#B42318; font-weight:800; }

/* ---------- SIREA 3.3 · Quipu, asistente de bolsillo (flotante) ---------- */
.st-key-quipu_fab{ position:fixed !important; right:22px; bottom:22px; z-index:1000002; width:auto !important; }
.st-key-quipu_fab div.stButton button{ border-radius:999px !important; background:#6E3FA3 !important; border:0 !important;
  color:#FFFFFF !important; padding:10px 20px 10px 16px !important; min-height:48px; font-weight:700; letter-spacing:.2px;
  box-shadow:0 10px 26px rgba(85,48,127,.38), 0 2px 6px rgba(43,33,64,.18); }
.st-key-quipu_fab div.stButton button:hover{ background:#55307F !important; transform:translateY(-1px); }
.st-key-quipu_caja, .st-key-quipu_caja_grande{ position:fixed !important; right:22px; bottom:84px; z-index:1000001;
  background:#FFFFFF; border:1px solid #E4DAF1; border-radius:18px; padding:12px 14px 10px !important;
  box-shadow:0 22px 54px rgba(43,33,64,.24), 0 3px 10px rgba(43,33,64,.10); overflow-y:auto; overflow-x:hidden;
  flex-wrap:nowrap !important;
  animation:quipu-in .18s ease-out; gap:.55rem !important; }
.st-key-quipu_caja{ width:min(390px, calc(100vw - 32px)) !important; max-height:min(600px, calc(100vh - 110px)); }
.st-key-quipu_caja_grande{ width:min(820px, calc(100vw - 32px)) !important; height:calc(100vh - 110px); max-height:calc(100vh - 110px); }
@keyframes quipu-in{ from{ opacity:0; transform:translateY(10px) scale(.985); } to{ opacity:1; transform:none; } }
.quipu-cab{ display:flex; align-items:center; gap:10px; }
.quipu-logo{ display:inline-flex; width:38px; height:38px; border-radius:12px; align-items:center; justify-content:center;
  background:linear-gradient(135deg,#6E3FA3,#0077C8); color:#FFFFFF; flex:0 0 auto; }
.quipu-nombre{ font-size:17px; font-weight:800; color:#2B2140; line-height:1.1; }
.quipu-sub{ font-size:12px; color:#6B5E80; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.quipu-cab > div{ min-width:0; }
.quipu-vacio{ font-size:13.5px; color:#33424F; background:#FBF9FE; border:1px dashed #DCCFEE; border-radius:12px; padding:10px 12px; }
.st-key-quipu_caja [class*="st-key-quipu_sug_"] button, .st-key-quipu_caja_grande [class*="st-key-quipu_sug_"] button{
  justify-content:flex-start; text-align:left; border-radius:12px; border-color:#E4DAF1; color:#55307F; font-size:13.5px; }
.quipu-chat{ display:flex; flex-direction:column-reverse; overflow-y:auto; overscroll-behavior:contain; padding-right:4px; }
.st-key-quipu_caja .quipu-chat{ max-height:min(330px, calc(100vh - 360px)); }
.st-key-quipu_caja_grande .quipu-chat{ max-height:calc(100vh - 380px); }
.st-key-quipu_tam button, .st-key-quipu_nueva button{ min-height:34px !important; height:34px; width:34px !important;
  padding:0 !important; border-radius:10px !important; border-color:#E4DAF1 !important; color:#55307F !important; }
.st-key-quipu_tam, .st-key-quipu_nueva{ display:flex; justify-content:flex-end; }
@media (max-width: 640px){
  .st-key-quipu_fab{ right:14px; bottom:14px; }
  .st-key-quipu_caja, .st-key-quipu_caja_grande{ right:12px; left:12px; width:auto !important; bottom:74px; }
}
/* botones rojo/lila: incluir "-rojo" o "-lila" en la key del boton */
[class*="st-key-"][class*="-rojo"] div.stButton button{ background:#B42318 !important; border-color:#B42318 !important; color:#FFFFFF !important; }
[class*="st-key-"][class*="-rojo"] div.stButton button:hover{ background:#8E1B12 !important; border-color:#8E1B12 !important; }
[class*="st-key-"][class*="-lila"] div.stButton button, [class*="st-key-"][class*="-lila"] div.stFormSubmitButton button{ background:#6E3FA3 !important; border-color:#6E3FA3 !important; color:#FFFFFF !important; }
[class*="st-key-"][class*="-lila"] div.stButton button:hover, [class*="st-key-"][class*="-lila"] div.stFormSubmitButton button:hover{ background:#55307F !important; border-color:#55307F !important; }

.sire-chip{ display:inline-flex; align-items:center; gap:6px; padding:3px 11px; border-radius:999px; font-size:12.5px; font-weight:800; white-space:nowrap; }
.sire-bar{ display:flex; align-items:center; gap:10px; width:100%; }
.sire-bar-pista{ flex:1; height:10px; border-radius:999px; background:#E3EEF7; overflow:hidden; }
.sire-bar-pista > div{ height:100%; border-radius:999px; }
.sire-bar-n{ flex:none; min-width:44px; text-align:right; font-size:14px; font-weight:800; font-variant-numeric:tabular-nums; }
.sire-kpi{ position:relative; overflow:hidden; background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:18px 22px 18px 26px; min-height:168px; box-shadow:var(--sombra); }
.sire-kpi::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:5px; background:var(--k,#0077C8); }
.sire-kpi-top{ display:flex; align-items:center; justify-content:space-between; gap:12px; font-size:12px; font-weight:800; letter-spacing:.07em; text-transform:uppercase; color:var(--mute); }
.sire-kpi-ico{ width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; }
.sire-kpi-val{ margin-top:8px; font-size:34px; line-height:1.1; font-weight:800; font-variant-numeric:tabular-nums; }
.sire-kpi-sub{ margin-top:4px; font-size:14px; color:var(--mute); }
.sire-aviso{ display:flex; gap:12px; align-items:flex-start; padding:14px 18px; border-radius:var(--r); font-size:14px; color:#1F3347; margin:8px 0 16px; }
.sire-aviso svg{ margin-top:2px; }
.sire-aviso-t{ font-weight:800; }
.sire-titulo{ display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between; gap:16px; margin:32px 0 24px; }
.stApp .sire-titulo h1{ margin:0 !important; color:var(--navy) !important; font-size:34px !important; letter-spacing:-.01em; }
.sire-migas{ font-size:14px; color:var(--mute); margin-bottom:6px; font-weight:600; }
.sire-sub{ margin:6px 0 0; font-size:17px; color:var(--mute); }
.sire-titulo-der{ display:flex; gap:8px; flex-wrap:wrap; }
.stApp .sire-lista{ list-style:none; margin:0 !important; padding:0 !important; }
.stApp .sire-lista li{ margin:0 !important; display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid #EAF1F8; font-size:15px; }
.sire-lista li:last-child{ border-bottom:0; }
.sire-lista li .grow{ flex:1; }
.sire-panel{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:20px 24px; margin-bottom:16px; box-shadow:var(--sombra); }
.stApp .sire-panel h3{ margin:0 0 12px !important; padding:0 !important; color:var(--navy) !important; font-size:16px !important; }


/* ---------- tarjetas con cabecera, filas de detalle, codigo ---------- */
.sire-card{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); margin-bottom:16px; box-shadow:var(--sombra); overflow:hidden; }
.sire-card-h{ padding:16px 24px; border-bottom:1px solid var(--line); background:#F1F7FC; font-size:16px; font-weight:800; color:var(--navy); }
.sire-card-b{ padding:8px 24px 14px; }
.sire-fila{ display:flex; justify-content:space-between; gap:16px; padding:12px 0; border-bottom:1px solid #EAF1F8; font-size:15px; }
.sire-fila:last-child{ border-bottom:0; }
.sire-fila span:first-child{ color:var(--mute); font-size:14px; }
.sire-fila span:last-child{ font-weight:800; font-variant-numeric:tabular-nums; text-align:right; }
.sire-det{ border-top:0; }
.sire-det-f{ display:flex; gap:16px; padding:13px 0; border-bottom:1px solid #EAF1F8; }
.sire-det-f:last-child{ border-bottom:0; }
.sire-det-k{ flex:0 0 190px; font-size:15px; color:var(--mute); }
.sire-det-v{ flex:1; min-width:0; font-size:15px; font-weight:800; overflow-wrap:anywhere; }
.sire-codigo{ background:#F1F7FC; border:1px solid #D5E5F2; border-radius:14px; padding:16px 22px; margin:0 0 20px; display:flex; flex-direction:column; gap:2px; }
.sire-codigo-k{ font-size:12px; color:var(--mute); font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.sire-codigo-v{ font-size:30px; font-weight:800; color:var(--navy); letter-spacing:.02em; font-variant-numeric:tabular-nums; }
.sire-scroll{ max-height:300px; overflow-y:auto; }
.sire-nota{ margin:4px 0 8px; font-size:13.5px; color:var(--mute); }
.sire-avance-n{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-top:12px; }
.sire-avance-n b{ font-size:28px; font-weight:800; color:var(--navy); font-variant-numeric:tabular-nums; }
.sire-avance-n span{ font-size:14px; color:var(--mute); }
.sire-avance-n span strong{ color:var(--ink); }
.sire-avance-pista{ margin:10px 0 4px; height:12px; border-radius:999px; background:#E3EEF7; overflow:hidden; }
.sire-avance-pista > div{ height:100%; border-radius:999px; }


/* ---------- grafico de barras y tarjetas de lista ---------- */
.stApp .sire-h2{ margin:40px 0 16px !important; font-size:22px !important; font-weight:800 !important; color:var(--navy) !important; }
.st-key-sec_evolucion{ padding-top:24px !important; }
.sire-chart{ display:flex; align-items:flex-end; gap:12px; height:216px; border-bottom:1px solid var(--line); margin:8px 0 20px; }
.sire-col{ flex:1 1 0; min-width:0; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:6px; }
.sire-col > div{ width:100%; max-width:56px; border-radius:10px 10px 4px 4px; }
.sire-col .pct{ font-size:13px; font-weight:700; font-variant-numeric:tabular-nums; }
.sire-col .sem{ font-size:13px; color:var(--mute); }
.sire-col.act .pct, .sire-col.act .sem{ font-weight:800; color:var(--ink); }
.sire-chart.denso{ gap:3px; }
.sire-chart.denso .pct{ display:none; }
.sire-chart.denso .sem{ font-size:10px; }
.sire-lcard{ background:#FFFFFF; border:1px solid var(--line); border-top:5px solid var(--azul); border-radius:var(--r-lg); padding:6px 24px 12px; box-shadow:var(--sombra); }
.sire-lcard-h{ margin:14px 0 4px; font-size:18px; font-weight:800; color:var(--navy); }
.sire-lcard-h span{ color:var(--mute); font-weight:600; }

/* ---------- secciones numeradas del formulario ---------- */
[class*="st-key-sec_"]{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:0 28px 24px !important; gap:1rem; box-shadow:var(--sombra); }
.sire-sec-h{ display:flex; align-items:center; gap:14px; padding:18px 28px; margin:0 -28px 6px; border-bottom:1px solid #EAF1F8; }
.sire-sec-n{ width:34px; height:34px; border-radius:50%; background:var(--azul); color:#FFFFFF; font-size:16px; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; box-shadow:0 6px 14px rgba(0,109,176,.26); }
.stApp .sire-sec-h h2{ margin:0 !important; padding:0 !important; font-size:19px !important; font-weight:800 !important; color:var(--navy) !important; }
.st-key-sire_enviar [data-testid="stForm"]{ background:transparent !important; border:0 !important; padding:0 !important; box-shadow:none !important; }
.st-key-sire_enviar [data-testid="stFormSubmitButton"] button{ min-height:52px; font-size:16px !important; }

/* ---------- encabezado de las redes ---------- */
.st-key-sire_hdr{ position:relative; isolation:isolate; padding:0; margin-bottom:8px; min-height:72px; display:flex; flex-direction:column; justify-content:center; }
.st-key-sire_hdr::before{
  content:""; position:absolute; z-index:-1; top:0; bottom:0; left:50%; width:100vw; margin-left:-50vw;
  background:#FFFFFF; border-bottom:1px solid var(--line);
}
.sire-brand{ display:flex; align-items:center; gap:14px; }
.sire-brand-essalud{ height:46px; width:auto; display:block; }
.sire-brand-sep{ width:1px; height:32px; background:var(--line); }
.sire-brand-txt{ display:flex; flex-direction:column; line-height:1.1; }
.sire-brand-txt b{ font-size:21px; font-weight:800; letter-spacing:.04em; color:var(--navy); }
.sire-brand-txt small{ font-size:12px; color:var(--mute); font-weight:600; }
.sire-semana-chip{ display:inline-flex; align-items:center; gap:8px; background:#E3F0FA; color:#004F85; border-radius:999px; padding:6px 14px; font-size:13px; font-weight:800; white-space:nowrap; }
.st-key-sire_hdr .stButton > button{
  min-height:72px; background:transparent !important; border:0 !important; border-bottom:3px solid transparent !important;
  border-radius:0 !important; color:#33485A !important; font-weight:700 !important; font-size:14.5px !important; padding:0 6px !important;
  box-shadow:none !important;
}
.st-key-sire_hdr .stButton > button:hover{ background:transparent !important; color:var(--azul) !important; }
.st-key-sire_hdr .stButton > button[kind="primary"]{
  background:transparent !important; color:var(--azul) !important; font-weight:800 !important; border-bottom:3px solid var(--azul) !important; box-shadow:none !important;
}
.st-key-sire_hdr .stButton > button[kind="primary"] *{ color:var(--azul) !important; }

/* ---------- acuse de recibo en pantalla ---------- */
.sire-acuse{ width:100vw; margin:-8px 0 28px calc(50% - 50vw); color:#FFFFFF; }
.sire-acuse-azul{ background:linear-gradient(135deg,#005A9C 0%,#0B7BC4 100%); }
.sire-acuse-rojo{ background:linear-gradient(135deg,#8E1F1F 0%,#B93232 100%); }
.sire-acuse-ambar{ background:linear-gradient(135deg,#8A5206 0%,#B7791F 100%); }
.sire-acuse-naranja{ background:linear-gradient(135deg,#A94A08 0%,#D9680F 100%); }
.sire-acuse-in{ max-width:1192px; margin:0 auto; padding:40px 0 44px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:28px; }
.sire-acuse-txt{ flex:1 1 520px; min-width:0; }
.sire-acuse-migas{ font-size:14px; font-weight:700; color:rgba(255,255,255,.85); margin-bottom:18px; }
.sire-acuse-ico{ width:64px; height:64px; border-radius:50%; background:rgba(255,255,255,.18); border:1.5px solid rgba(255,255,255,.4); display:flex; align-items:center; justify-content:center; margin-bottom:16px; }
.sire-acuse-eye{ display:block; font-size:13px; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:rgba(255,255,255,.88); margin-bottom:6px; }
.stApp .sire-acuse h1{ color:#FFFFFF !important; font-size:38px !important; line-height:1.15 !important; margin:0 0 10px !important; padding:0 !important; }
.sire-acuse p{ margin:0; font-size:17px; line-height:1.5; color:#FFFFFF; max-width:640px; }
.sire-acuse-cod{ flex:0 0 auto; background:#FFFFFF; color:var(--ink); border-radius:18px; padding:20px 28px; box-shadow:0 14px 34px rgba(0,0,0,.18); min-width:300px; }
.sire-acuse-cod span{ display:block; font-size:12.5px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--mute); margin-bottom:4px; }
.sire-acuse-cod b{ display:block; font-size:28px; letter-spacing:.02em; color:var(--navy); }
.sire-acuse-azul .sire-acuse-cod b{ color:#005C9C; }
.sire-acuse-rojo .sire-acuse-cod b{ color:#8E1F1F; }
.sire-acuse-ambar .sire-acuse-cod b{ color:#7A4A05; }
.sire-acuse-naranja .sire-acuse-cod b{ color:#A94A08; }

/* ---------- inicios de sesion: panel dividido ---------- */
[class*="st-key-sire_split"]{ position:relative; width:100vw; margin-left:calc(50% - 50vw); margin-bottom:0; }
[class*="st-key-sire_split"] > [data-testid="stHorizontalBlock"]{ gap:0 !important; align-items:stretch; }
[class*="st-key-sire_split"] [data-testid="stColumn"]:nth-child(1){ padding:56px 64px !important; min-height:640px; position:relative; overflow:hidden; }
[class*="st-key-sire_split"] [data-testid="stColumn"]:nth-child(1) > [data-testid="stVerticalBlock"]{ height:100%; justify-content:space-between; gap:36px; }
[class*="st-key-sire_split"] [data-testid="stColumn"]:nth-child(2){ padding:48px 24px !important; background:var(--bg); display:flex; flex-direction:column; justify-content:center; align-items:center; }
[class*="st-key-sire_split"] [data-testid="stColumn"]:nth-child(2) > div{ width:100%; max-width:456px; }
.st-key-sire_split_claro [data-testid="stColumn"]:nth-child(1){ background:linear-gradient(160deg,#E8F3FB 0%,#CFE4F5 100%); }
.st-key-sire_split_oscuro [data-testid="stColumn"]:nth-child(1){ background:linear-gradient(160deg,#005A9C 0%,#0B7BC4 100%); color:#FFFFFF; }
.sire-split-in{ display:flex; flex-direction:column; gap:18px; max-width:480px; position:relative; }
.sire-split-in h1{ margin:0 !important; font-size:38px !important; line-height:1.15 !important; }
.st-key-sire_split_claro .sire-split-in h1{ color:#123A6B !important; }
.st-key-sire_split_oscuro .sire-split-in h1{ color:#FFFFFF !important; }
.sire-split-in p{ margin:0; font-size:17px; line-height:1.55; }
.st-key-sire_split_claro .sire-split-in p{ color:#1F3347; }
.st-key-sire_split_oscuro .sire-split-in p{ color:#F0F7FC; }
.sire-pildora{ align-self:flex-start; display:inline-flex; align-items:center; gap:8px; border-radius:999px; padding:6px 14px; font-size:12.5px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.st-key-sire_split_claro .sire-pildora{ background:#FFFFFF; color:#005C9C; box-shadow:0 2px 6px rgba(0,80,140,.12); }
.st-key-sire_split_oscuro .sire-pildora{ background:rgba(255,255,255,.16); color:#FFFFFF; border:1px solid rgba(255,255,255,.3); }
.sire-pt{ display:grid; grid-template-columns:34px minmax(0,1fr); gap:14px; align-items:flex-start; }
.sire-pt b{ width:34px; height:34px; border-radius:50%; background:#FFFFFF; color:var(--azul); display:inline-flex; align-items:center; justify-content:center; font-weight:800; font-size:15px; box-shadow:0 2px 6px rgba(0,80,140,.14); }
.sire-pt p{ font-size:16px !important; }
.sire-ck{ display:grid; grid-template-columns:20px minmax(0,1fr); gap:12px; align-items:flex-start; font-size:16px; line-height:1.4; color:#FFFFFF; }
.sire-ck svg{ margin-top:2px; }
.sire-split-in .sire-ck span{ color:#F0F7FC; }
.sire-split-logo{ height:72px; width:auto; align-self:flex-start; display:block; margin-bottom:36px; }
.sire-split-pie{ font-size:14px; font-weight:700; color:#E3F0FA; position:relative; margin-top:48px; }
.sire-vista{ position:relative; background:#FFFFFF; border-radius:18px; padding:20px 22px; max-width:440px; box-shadow:0 14px 34px rgba(0,70,130,.16); display:flex; flex-direction:column; gap:14px; color:var(--ink); }
.sire-vista-h{ display:flex; justify-content:space-between; align-items:center; gap:12px; font-weight:800; color:var(--navy); }
.sire-vista-h small{ font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--mute); }
.sire-vista-n{ display:flex; align-items:baseline; gap:10px; }
.sire-vista-n b{ font-size:34px; font-weight:800; line-height:1; }
.sire-vista-n span{ font-size:14px; color:var(--mute); }
.sire-marca-agua{ position:absolute; right:-130px; bottom:-160px; width:540px; opacity:.1; pointer-events:none; }
[class*="st-key-sire_split"] [data-testid="stForm"]{ border-radius:20px !important; padding:34px !important; box-shadow:0 16px 40px rgba(20,70,120,.10); width:100%; }
.sire-form-t{ margin:0 !important; font-size:26px !important; line-height:1.2 !important; color:var(--navy) !important; }
.sire-form-s{ margin:6px 0 4px; font-size:16px; color:var(--mute); }
.sire-form-nota{ display:grid; grid-template-columns:20px minmax(0,1fr); gap:10px; background:#F1F7FC; border-radius:var(--r); padding:12px 14px; font-size:14px; color:var(--mute); margin-top:6px; }
.sire-form-nota svg{ margin-top:2px; }

.st-key-sire_login_admin [data-testid="stForm"], .st-key-sire_login_red [data-testid="stForm"]{ padding:28px !important; }
.stApp .sire-login-t{ margin:0 !important; font-size:26px !important; line-height:1.2 !important; color:var(--navy) !important; }
.sire-login-s{ margin:8px 0 24px; font-size:16px; color:var(--mute); }
.sire-login-n{ margin:16px 0 0; font-size:14px; color:var(--mute); display:flex; align-items:center; gap:8px; }
.sire-eye{ margin:0 0 8px; font-size:13px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; color:var(--mute); }

/* ---------- enlaces con forma de boton de texto ---------- */
[class*="st-key-link_"] .stButton > button{ background:transparent !important; border:0 !important; box-shadow:none !important; color:var(--azul) !important; min-height:auto; padding:0 !important; font-weight:800 !important; text-decoration:underline; justify-content:flex-start; }
[class*="st-key-link_"] .stButton > button *{ color:var(--azul) !important; }
[class*="st-key-link_"] .stButton > button:hover{ background:transparent !important; color:var(--azul-h) !important; }
.st-key-sire_form_card{ background:#FFFFFF; border:1px solid var(--line); border-radius:20px; padding:34px !important; box-shadow:0 16px 40px rgba(20,70,120,.10); width:100%; }
.sire-pie-form{ border-top:1px solid #EAF1F8; padding-top:16px; margin-top:8px; font-size:14px; color:var(--mute); }

/* ---------- requisitos de contrasena ---------- */
.sire-req{ background:#F1F7FC; border-radius:var(--r); padding:14px 16px; display:flex; flex-direction:column; gap:8px; margin:4px 0 12px; }
.sire-req-t{ font-weight:800; font-size:14px; color:var(--navy); margin-bottom:2px; }
.sire-req-i{ display:flex; align-items:flex-start; gap:10px; font-size:14.5px; color:#33485A; line-height:1.35; }
.sire-req-i svg{ margin-top:1px; }
.sire-req-i.ok{ color:var(--ok); font-weight:700; }
.sire-fuerza{ display:flex; align-items:center; gap:12px; margin:2px 0 4px; }
.sire-fuerza-p{ flex:1; display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
.sire-fuerza-p i{ height:8px; border-radius:999px; background:#E3EEF7; }
.sire-fuerza-n{ font-size:13.5px; font-weight:800; min-width:96px; text-align:right; }
.sire-porque{ font-size:14px; color:#33485A; line-height:1.5; }
.sire-porque b{ color:var(--navy); }
.sire-porque ul{ margin:6px 0 0; padding-left:20px; }
.sire-porque li{ margin:0 0 6px !important; }

/* ---------- sugerencias de usuario ---------- */
.st-key-sire_sugerencias{ background:#F1F7FC; border:1px solid #D5E5F2; border-radius:var(--r); padding:12px 16px !important; gap:12px !important; margin-bottom:8px; }
.st-key-sire_sugerencias .sire-req-i span{ display:block; line-height:1.45; }
.sire-req-i.mal{ color:#9E2B2B; font-weight:700; }
.sire-req-m{ display:block; font-weight:400; color:#5C3A3A; font-size:13.5px; margin-top:2px; }
.st-key-sire_sugerencias .stButton > button{ min-height:36px; padding:0 14px; font-size:14px !important; border-radius:999px !important; }

/* ---------- usuarios frecuentes y verificación de correo ---------- */
.st-key-sire_frec_wrap{ position:absolute !important; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; margin:0 !important; }
.st-key-sire_frecuentes{ background:#F1F7FC; border:1px solid #D5E5F2; border-radius:var(--r); padding:14px 16px !important; gap:8px !important; margin-bottom:12px; }
.st-key-sire_frecuentes [data-testid="stHorizontalBlock"]{ gap:8px !important; }
.sire-frec-t{ font-weight:800; color:var(--navy); font-size:15px; }
.sire-frec-s{ color:#33485A; font-size:13.5px; line-height:1.45; margin-bottom:4px; }
.st-key-sire_frecuentes .stButton > button{ min-height:38px; font-size:14px !important; justify-content:flex-start; }
.st-key-sire_frecuentes [class*="st-key-frec_quitar"] .stButton > button{ min-width:38px; padding:0; justify-content:center; }
.st-key-sire_sugerencias_correo{ gap:10px !important; margin-bottom:8px; }
.sire-correo-ok{ display:flex; align-items:center; gap:8px; color:#1E5E34; font-size:14px; margin:-2px 0 6px; }

/* ---------- intercambio de mensajes (solicitudes de contraseña) ---------- */
.sire-hilo{ display:flex; flex-direction:column; gap:12px; padding:14px; background:#F4F8FC; border:1px solid #D5E5F2; border-radius:var(--r); max-height:560px; overflow-y:auto; }
.sire-msg{ max-width:82%; border-radius:14px; padding:10px 14px; font-size:14.5px; line-height:1.5; }
.sire-msg-cab{ display:flex; flex-wrap:wrap; gap:4px 10px; align-items:baseline; margin-bottom:4px; }
.sire-msg-cab b{ font-size:13.5px; }
.sire-msg-cab span{ font-size:12px; opacity:.8; }
.sire-msg-otro{ align-self:flex-start; background:#FFFFFF; border:1px solid #D5DDE4; color:#14202B; border-bottom-left-radius:4px; }
.sire-msg-yo{ align-self:flex-end; background:#0077C8; color:#FFFFFF; border-bottom-right-radius:4px; }
.sire-msg-yo .sire-msg-cab span{ color:#E3F0FA; opacity:1; }
.sire-msg-sis{ align-self:center; text-align:center; }
.sire-msg-sis span{ display:inline-block; background:#E3EEF7; color:#33485A; font-size:12.5px; padding:3px 12px; border-radius:999px; }
.st-key-sire_solicitud_red{ background:#F1F7FC; border:1px solid #D5E5F2; border-radius:var(--r); padding:16px 18px !important; margin-bottom:12px; }

/* dato suelto (etiqueta + valor) */
.sire-dato small{ display:block; color:#4F6070; font-size:12.5px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; margin-bottom:4px; }
.sire-dato b{ color:#14202B; font-size:15px; word-break:break-word; }

/* ---------- inicio ---------- */
.st-key-sire_hero{ position:relative; overflow:hidden; border-radius:24px; background:linear-gradient(135deg,#005A9C 0%,#0B7BC4 100%); color:#FFFFFF; padding:44px 48px !important; margin-top:32px; box-shadow:0 18px 40px rgba(0,90,156,.22); }
.st-key-sire_hero > [data-testid="stHorizontalBlock"]{ gap:40px !important; align-items:center; }
.st-key-sire_hero .stButton > button[kind="primary"]{ background:#FFFFFF !important; color:var(--azul-h) !important; border-color:#FFFFFF !important; box-shadow:0 6px 18px rgba(0,40,80,.22) !important; }
.st-key-sire_hero .stButton > button[kind="primary"] *{ color:var(--azul-h) !important; }
.st-key-sire_hero .stButton > button[kind="primary"]:hover{ background:#EEF6FC !important; }
.st-key-sire_hero .stButton > button[kind="secondary"]{ background:rgba(255,255,255,.14) !important; color:#FFFFFF !important; border:1.5px solid rgba(255,255,255,.55) !important; }
.st-key-sire_hero .stButton > button[kind="secondary"] *{ color:#FFFFFF !important; }
.st-key-sire_hero .stButton > button[kind="secondary"]:hover{ background:rgba(255,255,255,.24) !important; }
.sire-hero-chip{ display:inline-flex; align-items:center; gap:10px; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.3); border-radius:999px; padding:7px 16px 7px 12px; font-size:13.5px; font-weight:700; margin-bottom:16px; }
.sire-hero-chip i{ width:9px; height:9px; border-radius:50%; background:#7CE0A3; box-shadow:0 0 0 4px rgba(124,224,163,.25); }
.sire-hero-chip.cerrada i{ background:#FFB4B4; box-shadow:0 0 0 4px rgba(255,180,180,.25); }
.sire-hero-per{ font-size:14px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; opacity:.9; }
.stApp .sire-hero-h1{ margin:4px 0 14px !important; font-size:44px !important; line-height:1.1 !important; font-weight:800 !important; color:#FFFFFF !important; letter-spacing:-.01em; }
.sire-hero-p{ margin:0 0 22px; font-size:17px; line-height:1.55; max-width:520px; color:#F0F7FC; }
.sire-glass{ background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.3); border-radius:20px; padding:26px 28px; display:flex; flex-direction:column; gap:18px; backdrop-filter:blur(6px); }
.sire-glass-top{ display:flex; justify-content:space-between; align-items:flex-end; gap:12px; }
.sire-glass-k{ font-size:13px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; opacity:.9; display:block; }
.sire-glass-s{ font-size:15px; opacity:.92; display:block; }
.sire-glass-pct{ font-size:54px; font-weight:800; line-height:.95; letter-spacing:-.02em; }
.sire-glass-bar{ height:12px; background:rgba(255,255,255,.26); border-radius:6px; overflow:hidden; }
.sire-glass-bar i{ display:block; height:100%; background:#FFFFFF; border-radius:6px; }
.sire-glass-3{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.sire-glass-3 div{ background:rgba(255,255,255,.12); border-radius:12px; padding:12px 14px; }
.sire-glass-3 b{ display:block; font-size:26px; font-weight:800; line-height:1.1; }
.sire-glass-3 span{ font-size:13px; opacity:.92; }
.sire-glass-pie{ font-size:13.5px; opacity:.92; margin:0; }
.sire-seccion-t{ margin:36px 0 4px; font-size:24px !important; color:var(--navy) !important; }
.sire-seccion-s{ margin:0 0 18px; color:var(--mute); font-size:16px; }
[class*="st-key-op_"]{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:24px !important; height:100%; box-shadow:var(--sombra); transition:border-color .15s, box-shadow .15s, transform .15s; }
[class*="st-key-op_"]:hover{ border-color:var(--azul); box-shadow:0 10px 26px rgba(0,109,176,.14); transform:translateY(-2px); }
.sire-op{ min-height:250px; }
.sire-op-ico{ width:52px; height:52px; border-radius:14px; display:flex; align-items:center; justify-content:center; margin-bottom:14px; }
.sire-op-eye{ margin:0 0 4px; font-size:12px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--mute); }
.sire-op h3{ margin:0 0 8px !important; font-size:20px !important; color:var(--navy) !important; }
.sire-op p{ margin:0 0 12px; font-size:15px; color:var(--mute); line-height:1.5; }
[class*="st-key-op_"] .stButton > button{ background:transparent !important; border:0 !important; box-shadow:none !important; color:var(--azul) !important; justify-content:flex-start; padding:0 !important; min-height:32px; font-weight:800 !important; }
[class*="st-key-op_"] .stButton > button *{ color:var(--azul) !important; }
[class*="st-key-op_"] .stButton > button:hover{ background:transparent !important; color:var(--azul-h) !important; }
.sire-tarjeta2{ background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:28px 30px; box-shadow:var(--sombra); height:100%; box-sizing:border-box; }
.sire-tarjeta2 h2{ margin:0 !important; font-size:21px !important; color:var(--navy) !important; }
.sire-tarjeta2 .sub{ margin:2px 0 20px; font-size:14px; color:var(--mute); }
.sire-paso{ display:grid; grid-template-columns:44px minmax(0,1fr); gap:16px; margin-bottom:20px; }
.sire-paso b{ width:44px; height:44px; border-radius:50%; background:#E3F0FA; color:#005C9C; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:17px; }
.sire-paso h3{ margin:0 0 2px !important; font-size:16px !important; color:var(--navy) !important; }
.sire-paso p, .sire-plazo p{ margin:0; font-size:14px; color:var(--mute); }
.sire-plazo{ display:grid; grid-template-columns:40px minmax(0,1fr); gap:14px; margin-bottom:18px; }
.sire-plazo > span{ width:40px; height:40px; border-radius:12px; display:flex; align-items:center; justify-content:center; }
.sire-plazo h3{ margin:0 0 2px !important; font-size:16px !important; color:var(--navy) !important; }
.sire-franja{ display:flex; flex-wrap:wrap; gap:12px 36px; justify-content:center; padding:20px 0 4px; font-size:14px; color:var(--mute); }
.sire-franja span{ display:inline-flex; align-items:center; gap:10px; font-weight:700; }

/* ---------- pie de pagina ---------- */
.sire-foot{ position:relative; isolation:isolate; margin-top:56px; }
.sire-foot::before{
  content:""; position:absolute; z-index:-1; top:0; bottom:0; left:50%; width:100vw; margin-left:-50vw; background:var(--azul);
}
.sire-foot-in{ display:flex; flex-wrap:wrap; gap:16px 40px; align-items:center; justify-content:space-between; padding:28px 0; color:#FFFFFF; }
.sire-foot-logos{ display:flex; align-items:center; gap:20px; }
.sire-foot-sep{ width:1px; height:40px; background:rgba(255,255,255,.35); }
.sire-foot-essalud{ height:48px; width:auto; display:block; }
.sire-foot-oiis{ height:60px; width:auto; display:block; }
.sire-foot-txt{ flex:1 1 360px; display:flex; flex-direction:column; text-align:right; font-size:13.5px; line-height:1.6; }
.sire-foot-txt b{ color:#FFFFFF; font-weight:800; font-size:14.5px; }
.sire-foot-sub{ color:#E1EFF8; }

@media (max-width:900px){
  .st-key-sire_hero{ padding:28px 22px !important; }
  .st-key-sire_split [data-testid="stColumn"]:nth-child(1){ padding:32px 24px !important; min-height:0; }
}
@media (max-width:760px){
  .block-container, [data-testid="stMainBlockContainer"]{ padding:0 16px !important; }
  .sire-foot-txt{ text-align:left; }
  .sire-brand-essalud{ height:38px; }
  .stApp .sire-hero-h1{ font-size:32px !important; }
}
</style>
"""

_CSS_ADMIN = """
<style>
/* ---------- estructura del panel ---------- */
[data-testid="stMainBlockContainer"], .block-container{ max-width:100% !important; padding:0 40px 0 !important; }
[data-testid="stSidebar"]{
  background:#0E3E73 !important; border-right:0;
  min-width:272px !important; max-width:272px !important; width:272px !important;
  transform:none !important; margin-left:0 !important; visibility:visible !important;
}
[data-testid="stSidebar"] > div, [data-testid="stSidebarContent"]{ background:#0E3E73 !important; }
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"]{ display:none !important; }
[data-testid="stSidebarHeader"]{ display:none !important; }
[data-testid="stSidebarContent"]{ padding:0 12px 16px !important; }
[data-testid="stSidebarUserContent"]{ padding:22px 0 0 !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{ gap:2px !important; }
[data-testid="stSidebar"] .stButton{ margin:0 !important; }
[data-testid="stSidebar"] .stButton > button{
  position:relative; min-height:42px; width:100%; justify-content:flex-start; background:transparent !important; border:0 !important;
  border-radius:10px !important; color:#D3E6F7 !important; font-weight:700 !important; font-size:14.5px !important; padding:0 14px !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] .stButton > button *{ color:inherit !important; }
[data-testid="stSidebar"] .stButton > button:hover{ background:rgba(255,255,255,.09) !important; color:#FFFFFF !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"]{
  background:rgba(255,255,255,.16) !important; color:#FFFFFF !important; font-weight:800 !important; box-shadow:none !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]::before{
  content:""; position:absolute; left:-12px; top:9px; bottom:9px; width:4px; border-radius:0 4px 4px 0; background:#FFFFFF;
}
[data-testid="stSidebar"] .stButton > button > div{ justify-content:flex-start !important; gap:12px; }
[data-testid="stSidebar"] .stButton > button p{ text-align:left; }
[data-testid="stSidebar"] [class*="st-key-nav_salir"] button{
  border:1.5px solid rgba(255,255,255,.4) !important; color:#FFFFFF !important; justify-content:center; font-weight:800 !important; margin-top:6px; min-height:44px;
}
[data-testid="stSidebar"] [class*="st-key-nav_salir"] button > div{ justify-content:center !important; }
[data-testid="stSidebar"] [class*="st-key-nav_salir"] button:hover{ background:rgba(255,255,255,.12) !important; }
.sire-side-brand{ display:flex; align-items:center; gap:12px; padding:0 14px 18px; border-bottom:1px solid rgba(255,255,255,.14); margin-bottom:14px; }
.sire-side-brand b{ display:block; font-size:21px; font-weight:800; letter-spacing:.05em; color:#FFFFFF; line-height:1.15; }
.sire-side-brand small{ display:block; font-size:12.5px; color:#B8D5EE; font-weight:600; }
.sire-side-grupo{ padding:16px 14px 10px; font-size:11.5px; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:#8FB7DB; }
.sire-side-user{ display:flex; align-items:center; gap:12px; padding:18px 6px 12px; border-top:1px solid rgba(255,255,255,.14); margin-top:22px; }
.sire-avatar{ width:42px; height:42px; border-radius:50%; background:#E3F0FA; color:#0E3E73; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; }
.sire-side-user b{ display:block; font-size:15px; font-weight:800; color:#FFFFFF; line-height:1.25; margin-bottom:4px; }
.sire-side-user .sire-chip{ background:rgba(255,255,255,.16) !important; color:#FFFFFF !important; border:0 !important; font-size:11.5px; padding:1px 9px; letter-spacing:.05em; }
.sire-admin-top{ position:relative; isolation:isolate; padding:26px 0 22px; margin:0 0 24px; }
.sire-admin-top::before{
  content:""; position:absolute; z-index:-1; top:0; bottom:0; left:-40px; right:-40px; background:#FFFFFF; border-bottom:1px solid var(--line);
}
.sire-admin-top .sire-titulo{ margin:0; }
.stApp .sire-admin-top h1{ padding:0 !important; }
.sire-foot::before{ left:-40px; right:-40px; width:auto; margin-left:0; }

/* ---------- paneles (contenedores con key "panel_*") ---------- */
[class*="st-key-panel"]{
  background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:22px 24px 24px !important; margin-bottom:8px; box-shadow:var(--sombra);
}
.sire-panel-h h2{ margin:0 !important; font-size:20px !important; font-weight:800 !important; color:var(--navy) !important; padding:0 !important; }
.sire-panel-s{ margin-top:2px; font-size:14px; color:var(--mute); }
.sire-panel-h{ margin-bottom:12px; }
[class*="st-key-sec_"] [data-testid="stForm"]{ border:0 !important; padding:0 !important; background:transparent !important; box-shadow:none !important; }
[class*="st-key-panel"] [data-testid="stForm"]{ border:0 !important; padding:0 !important; background:transparent !important; box-shadow:none !important; }
[data-testid="stMainBlockContainer"] .sire-kpi{ margin-bottom:16px; }
[class*="st-key-panel"]{ margin-bottom:16px !important; }
.sire-vacio{ padding:28px 16px; text-align:center; color:var(--mute); font-size:15px; border:1.5px dashed #C4D6E6; border-radius:var(--r); background:#F8FBFE; }

/* ---------- tablas ---------- */
[data-testid="stElementContainer"]:has(.sire-tabla-wrap), [data-testid="stMarkdownContainer"]:has(.sire-tabla-wrap){ min-width:0; max-width:100%; }
.sire-nowrap .sire-tabla th, .sire-nowrap .sire-tabla td{ white-space:nowrap; }
.sire-tabla-wrap{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--r); background:#FFFFFF; }
.stApp table.sire-tabla{ width:100%; border-collapse:collapse; font-size:14px; color:var(--ink); margin:0; }
.stApp table.sire-tabla th{
  background:#EAF3FA !important; color:var(--navy) !important; font-weight:800; font-size:12.5px; letter-spacing:.03em; text-align:left;
  padding:12px 14px; border:0 !important; border-bottom:1px solid var(--line) !important; white-space:nowrap;
}
.stApp table.sire-tabla td{ padding:12px 14px; border:0 !important; border-bottom:1px solid #EAF1F8 !important; vertical-align:middle; background:#FFFFFF; }
.stApp table.sire-tabla tr:last-child td{ border-bottom:0 !important; }
.stApp table.sire-tabla tbody tr:nth-child(even) td{ background:#FAFCFE; }
.stApp table.sire-tabla tbody tr:hover td{ background:#F1F8FD; }
.stApp table.sire-tabla .num{ text-align:right; font-variant-numeric:tabular-nums; }

/* ---------- barras horizontales y cumplimiento ---------- */
.sire-hbars{ display:flex; flex-direction:column; gap:12px; padding:6px 0; }
.sire-hb{ display:grid; grid-template-columns:minmax(90px,150px) 1fr 40px; align-items:center; gap:12px; font-size:14px; }
.sire-hb-k{ text-align:right; color:#33485A; overflow-wrap:anywhere; }
.sire-hb-pista{ height:14px; border-radius:999px; background:#E3EEF7; overflow:hidden; display:block; }
.sire-hb-pista > span{ display:block; height:100%; border-radius:999px; }
.sire-hb-v{ font-weight:800; font-variant-numeric:tabular-nums; }
.sire-cums{ display:flex; flex-direction:column; gap:16px; padding:4px 0; }
.sire-cum-h{ display:flex; justify-content:space-between; gap:12px; font-size:14px; margin-bottom:4px; font-weight:700; }
.sire-cum-d{ color:var(--mute); font-weight:400; }

/* ---------- avisos con boton (contenedores con key "banner_*") ---------- */
[class*="st-key-banner"]{ border-radius:var(--r); padding:14px 18px !important; margin:8px 0; }
.st-key-banner_warn{ background:#FFF8E1; border:1px solid var(--warn-bd); border-left:5px solid #B7791F; }
.st-key-banner_bad{ background:var(--bad-bg); border:1px solid var(--bad-bd); border-left:5px solid var(--bad); }
.st-key-banner_info{ background:#E8F1F8; border:1px solid #B6D6EC; border-left:5px solid var(--azul); }
[class*="st-key-banner"] .sire-aviso{ background:transparent !important; border:0 !important; padding:0 !important; margin:0 !important; }

/* ---------- confirmaciones de acciones destructivas ---------- */
[class*="st-key-peligro"]{
  background:#FFF6F6; border:1.5px solid #E5A3A3; border-radius:var(--r-lg); padding:20px 24px !important;
}
[class*="st-key-peligro"] button[kind="primary"], [class*="st-key-peligro"] [data-testid="stBaseButton-primary"], [class*="st-key-peligro"] [data-testid="stBaseButton-primaryFormSubmit"]{ background:var(--bad) !important; border-color:var(--bad) !important; box-shadow:none !important; }
[class*="st-key-peligro"] [data-testid="stForm"]{ border:0 !important; padding:0 !important; background:transparent !important; box-shadow:none !important; }
[class*="st-key-peligro"] button[kind="primary"]:hover{ background:#8E1B12 !important; border-color:#8E1B12 !important; }
.btn-eliminar button{ background:var(--bad) !important; color:#FFFFFF !important; border:0 !important; }

/* ---------- clases heredadas (se ven con el tema nuevo sin tocar cada pagina) ---------- */
.badge-success, .estado-aprobado, .porcentaje-alto{ background:var(--ok-bg); color:var(--ok); border:1px solid var(--ok-bd); }
.badge-warning, .estado-observado, .porcentaje-medio{ background:var(--warn-bg); color:var(--warn); border:1px solid var(--warn-bd); }
.badge-danger, .estado-atrasado, .porcentaje-bajo{ background:var(--bad-bg); color:var(--bad-t); border:1px solid var(--bad-bd); }
.badge-secondary, .estado-pendiente{ background:#EEF1F4; color:#33424F; border:1px solid #C9D1D8; }
.badge-success, .badge-warning, .badge-danger, .badge-secondary, .estado-aprobado, .estado-observado, .estado-atrasado, .estado-pendiente,
.porcentaje-alto, .porcentaje-medio, .porcentaje-bajo{
  display:inline-block; padding:2px 10px; border-radius:999px; font-size:13px; font-weight:800;
}
.resumen-card{
  background:#F1F7FC; border:1px solid var(--line); border-radius:var(--r); padding:12px 16px; margin:0 0 16px;
  display:flex; flex-wrap:wrap; gap:8px 24px; font-size:14px; color:#33485A;
}
.resumen-card strong{ color:var(--ink); }
.dataframe-container{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--r); margin-bottom:16px; }
</style>
"""


def aplicar_tema(admin: bool = False):
    """Inyecta el CSS del tema. Llamar una vez por ejecucion, al inicio de cada pantalla."""
    st.markdown(_CSS, unsafe_allow_html=True)
    if admin:
        st.markdown(_CSS_ADMIN, unsafe_allow_html=True)
