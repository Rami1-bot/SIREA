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
    petróleo (#1D3F76) para titulos. Tipografía IBM Plex Sans + Bricolage Grotesque (SIREA 3.5).
  * Tarjetas redondeadas, degradado azul en la cabecera del inicio y en
    los acuses (rojo para el envio tardio), sin emojis y sin iconos
    cargados desde internet (todo es SVG incrustado).
  * El estado nunca se indica solo con color: siempre lleva texto.
"""

import base64
import re
from contextlib import contextmanager, nullcontext
from pathlib import Path

import streamlit as st

# ============================================================
# COLORES
# ============================================================

# SIREA 3.5 · paleta original de EsSalud: azul institucional para acciones y estructura,
# azul marino suave para títulos, celeste de acompañante y, para dar vida sin cansar la vista,
# Estilo corporativo: azul EsSalud, azul marca, celeste y blanco. El color va en los bordes de las tarjetas;
# los rellenos de color quedan solo para los estados (a tiempo, observado, tardío, duplicado).
AZUL = "#0077C8"        # azul EsSalud: botones, enlaces, acciones
AZUL_HOVER = "#005C9C"
TURQUESA = AZUL         # nombre heredado
PETROLEO = "#1D3F76"    # azul estructura: títulos y marca (nombre heredado)
PETROLEO_PROFUNDO = "#0B5A9E"   # fondo de la banda pública (degradado EsSalud)
NAVY = PETROLEO
AGUAMARINA = "#41B6E6"        # acento: celeste EsSalud (nudo de la marca, bordes); nombre heredado
AGUAMARINA_HOVER = "#2FA3D4"
AGUAMARINA_OSCURA = "#0077C8" # el acento sobre fondo blanco
AGUAMARINA_TEXTO = "#005C9C"  # el acento como texto sobre fondo claro
AGUAMARINA_SUAVE = "#EAF3FB"
OCRE = AGUAMARINA       # nombres heredados (antes amarillo)
SOL = OCRE
SOL_TEXTO = AGUAMARINA_TEXTO
CORAL_TEXTO = SOL_TEXTO
OCRE_SUAVE = AGUAMARINA_SUAVE
MARCA_ESSALUD = "#0077C8"   # azul institucional (solo marca)
CELESTE = "#41B6E6"     # celeste EsSalud, acompañante
CELESTE_SUAVE = "#E6F4FB"
VERDE_SALUD = "#1E9E63"  # verde salud (accesos y cuerdas del quipu)
VERDE_SUAVE = "#E3F5EC"
# Colores de las cuerdas del quipu (como en los quipus reales, cada cuerda con su color).
CUERDAS = ("#0077C8", "#1D3F76", "#41B6E6")
# Lila = "Diagnostico" en la senaletica de EsSalud. En SIREA marca TODO lo que
# produjo un asistente de IA (borradores, chips, panel de agentes) hasta que
# una persona lo valida; al validarse pasa a verde ("Tratamiento").
LILA = "#6E3FA3"
LILA_HOVER = "#5A2F8A"
LILA_SUAVE = "#F3EDFA"
LILA_BORDE = "#CDB8E8"
TINTA = "#13213A"
MUTE = "#4B5875"
LINEA = "#D9E7F3"
FONDO = "#F4F8FC"

# tono -> (texto, fondo, borde)
TONOS = {
    "ok":   ("#1E6B3A", "#E6F4EA", "#A9D8BA"),
    "warn": ("#96500A", "#FFF3E3", "#F5C892"),
    "bad":  ("#9E2B2B", "#FDE8E8", "#F0B8B8"),
    "info": ("#005C9C", "#E3F0FA", "#B6CAF4"),
    "mute": ("#33424F", "#EEF1F4", "#C9D1D8"),
    "dup":  ("#9C2465", "#FCE8F2", "#F0B3D3"),   # duplicado: magenta (el naranja quedó para «observado»)
    "ia":   ("#5A2F8A", "#F3EDFA", "#D9C7F2"),   # generado por IA, pendiente de validar
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
    """
    Marca de SIREA (3.5): un quipu. Cuerda principal con cuatro cuerdas colgantes que dibujan
    la curva epidémica; el nudo de la más alta, en aguamarina, es la semana que se está vigilando.
    `invertida`: fondo blanco y cuerdas petróleo (para fondos oscuros).
    """
    fondo, cuerda = (("#FFFFFF", PETROLEO) if invertida else (PETROLEO, "#FFFFFF"))
    colg = ((11, 21), (17, 26), (23, 31), (29, 24))
    lineas = "".join(f'<line class="q-c" x1="{x}" y1="11" x2="{x}" y2="{y}" stroke="{cuerda}" stroke-width="2" stroke-linecap="round"/>'
                     for x, y in colg)
    nudos = "".join(f'<circle class="q-n" cx="{x}" cy="{y}" r="2.1" fill="{cuerda}"/>' for x, y in colg if x != 23)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 40 40" role="img" aria-label="SIREA" style="flex:none">'
        f'<rect width="40" height="40" rx="11" fill="{fondo}"/>'
        f'<line class="q-c" x1="7.5" y1="11" x2="32.5" y2="11" stroke="{cuerda}" stroke-width="2.6" stroke-linecap="round"/>'
        f'{lineas}{nudos}<circle cx="23" cy="31" r="2.9" fill="{AGUAMARINA_OSCURA if invertida else AGUAMARINA}"/></svg>'
    )


def quipu_semanas(semana: int, total: int = 52, anio: int = None, oscuro: bool = True, alto: int = 74,
                  ancho: int = 1000) -> str:
    """
    La firma visual de SIREA: el año epidemiológico como un quipu. Cada semana es una cuerda
    colgante con su nudo: las cerradas, llenas y de colores (un color por mes, como en los quipus
    reales); la activa, larga y con el nudo aguamarina; las que vienen, apenas marcadas.
    Hitos en S1, S13, S26, S39 y la última.
    """
    try:
        semana, total = int(semana), max(1, int(total or 52))
    except (TypeError, ValueError):
        return ""
    ancho = max(400, int(ancho or 1000))   # más ancho = cuerda más baja al ocupar todo el ancho
    f_txt = min(1.6, ancho / 1000)          # la letra crece con el ancho para seguir legible
    x0, x1 = round(14 * f_txt), ancho - round(14 * f_txt)
    paso = (x1 - x0) / max(1, total - 1)
    cuerda = "rgba(255,255,255,.55)" if oscuro else "rgba(10,60,120,.45)"
    # Sobre el azul, tonos claros; sobre blanco, tonos firmes (contraste de gráfico ≥ 3:1).
    # Sobria: dos tonos que se alternan por mes (blanco y celeste claro en la banda; azul y azul marca en blanco).
    colores = (("#FFFFFF", "#BFE3F7") if oscuro else ("#0077C8", "#1D3F76"))
    nudo = "#FFFFFF" if oscuro else "#0077C8"
    tenue = "rgba(255,255,255,.28)" if oscuro else "rgba(10,60,120,.22)"
    texto = "#FFFFFF" if oscuro else MUTE
    hitos = {1, 13, 26, 39, total}
    partes = [f'<line x1="{x0}" y1="12" x2="{x1}" y2="12" stroke="{cuerda}" stroke-width="2.4" stroke-linecap="round"/>']
    for s in range(1, total + 1):
        x = round(x0 + (s - 1) * paso, 1)
        if s < semana:
            largo = 22 + (s % 4) * 3
            lleno = colores[((s - 1) // 4) % len(colores)]
            partes.append(f'<line x1="{x}" y1="12" x2="{x}" y2="{12 + largo}" stroke="{lleno}" stroke-width="2"/>'
                          f'<circle cx="{x}" cy="{12 + largo}" r="3" fill="{lleno}"/>')
        elif s == semana:
            partes.append(f'<line x1="{x}" y1="12" x2="{x}" y2="50" stroke="{nudo}" stroke-width="2.6"/>'
                          f'<circle cx="{x}" cy="50" r="7" fill="{nudo}" stroke="{"#0067B0" if oscuro else "#FFFFFF"}" stroke-width="2.5"/>'
                          f'<circle cx="{x}" cy="50" r="12" fill="none" stroke="{nudo}" stroke-opacity=".6" stroke-width="2"/>')
        else:
            partes.append(f'<line x1="{x}" y1="12" x2="{x}" y2="22" stroke="{tenue}" stroke-width="1.4" stroke-dasharray="2 2"/>'
                          f'<circle cx="{x}" cy="24" r="2" fill="none" stroke="{tenue}" stroke-width="1.2"/>')
        if s in hitos and abs(s - semana) > 2:
            partes.append(f'<text x="{x}" y="{alto - 2}" text-anchor="middle" font-size="{12 * f_txt:.0f}" fill="{texto}" '
                          f'font-family="IBM Plex Sans, sans-serif">S{s}</text>')
    partes.append(f'<text x="{round(x0 + (semana - 1) * paso, 1)}" y="{alto - 2}" text-anchor="middle" font-size="{13 * f_txt:.0f}" '
                  f'font-weight="700" fill="{"#004F85" if not oscuro else "#FFFFFF"}" font-family="IBM Plex Sans, sans-serif">S{semana}</text>')
    etiqueta = f"Semana {semana} de {total}" + (f" del año {anio}" if anio else "")
    return (f'<svg class="sirea-quipu" viewBox="0 0 {ancho} {alto}" role="img" '
            f'aria-label="{etiqueta}" style="width:100%;height:auto;display:block">{"".join(partes)}</svg>')


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


def hero_acuse(tono: str, titulo: str, subtitulo: str, codigo: str = "", migas: str = "", contenedor=None) -> None:
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
    html_acuse = (
        f'<div class="sire-acuse sire-acuse-{tono}"><span class="sire-tono sire-tono-{tono}"></span><div class="sire-acuse-in">'
        f'<div class="sire-acuse-txt">{m}<div class="sire-acuse-ico">{ico}</div>'
        f'<span class="sire-acuse-eye">Acuse de recibo</span><h1>{titulo}</h1><p>{subtitulo}</p></div>{cod}'
        f'</div></div>'
    )
    # `contenedor`: la banda azul de la pantalla (encabezado + acuse en un mismo fondo)
    with (contenedor if contenedor is not None else nullcontext()):
        mostrar(html_acuse)


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


_ESTADO_SECCION = {
    "ok": ("Completo", "ok", "check"),
    "falta": ("Falta un dato", "info", None),  # incompleto no es alerta: azul, no amarillo
    "error": ("Revisar", "bad", "alerta"),
    "opc": ("Opcional", "info", None),
    "sin_red": ("Sin conexión", "mute", None),
}


def _html_seccion(num, titulo: str, estado: str = None) -> str:
    badge = ""
    if estado in _ESTADO_SECCION:
        txt, tono, ic = _ESTADO_SECCION[estado]
        fg, bg, _ = TONOS[tono]
        i = icono(ic, 14, fg, 3) if ic else ""
        badge = f'<span class="sire-sec-estado" style="background:{bg};color:{fg}">{i}{txt}</span>'
    return f'<div class="sire-sec-h"><span class="sire-sec-n">{num}</span><h2>{titulo}</h2>{badge}</div>'


def seccion(num, titulo: str, estado: str = None, reservar: bool = False):
    """
    Cabecera numerada de una tarjeta de formulario (usar dentro de un container con key 'sec_*').
    `estado`: 'ok' | 'falta' | 'error' | 'opc' muestra una etiqueta a la derecha.
    `reservar=True` devuelve un marcador para poner la etiqueta después (actualizar_seccion).
    """
    html = _html_seccion(num, titulo, estado)
    if reservar:
        ph = st.empty()
        ph.markdown(compactar(html), unsafe_allow_html=True)
        return ph
    mostrar(html)


def actualizar_seccion(ph, num, titulo: str, estado: str):
    """Pone (o cambia) la etiqueta de estado de una cabecera creada con reservar=True."""
    if ph is not None:
        ph.markdown(compactar(_html_seccion(num, titulo, estado)), unsafe_allow_html=True)


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
            # sin columna vacia a la derecha: el menu llega hasta el borde
            c_marca, c1, c2, c3, c4 = st.columns([3.6, 1.1, 1.5, 1.4, 1.6], vertical_alignment="center")
            c5 = None
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
        if c5 is not None:
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
        <span class="sire-foot-sub">SIRE<span class="sire-a-foot">A</span> · Sistema de Recepción de Reportes Epidemiológicos con Agentes · v3.5 · © 2026 EsSalud</span>
      </div>
    </div></div>
    """)


# ============================================================
# CSS GLOBAL
# ============================================================

_CSS = """
<style>
@font-face{ font-family:'IBM Plex Sans'; font-style:normal; font-weight:400; font-display:swap; src:url('/app/static/fonts/ibm-plex-sans-latin-400-normal.woff2') format('woff2'); }
@font-face{ font-family:'IBM Plex Sans'; font-style:normal; font-weight:500; font-display:swap; src:url('/app/static/fonts/ibm-plex-sans-latin-500-normal.woff2') format('woff2'); }
@font-face{ font-family:'IBM Plex Sans'; font-style:normal; font-weight:600; font-display:swap; src:url('/app/static/fonts/ibm-plex-sans-latin-600-normal.woff2') format('woff2'); }
@font-face{ font-family:'IBM Plex Sans'; font-style:normal; font-weight:700; font-display:swap; src:url('/app/static/fonts/ibm-plex-sans-latin-700-normal.woff2') format('woff2'); }
@font-face{ font-family:'Bricolage Grotesque'; font-style:normal; font-weight:200 800; font-display:swap; src:url('/app/static/fonts/bricolage-grotesque-latin-wght-normal.woff2') format('woff2'); }

:root{
  --ink:#14202B; --mute:#4F6070; --line:#D9E7F3; --bg:#F4F8FC;
  --azul:#0077C8; --azul-h:#005C9C; --navy:#1D3F76;
  --ok:#1E6B3A; --ok-bg:#E6F4EA; --ok-bd:#A9D8BA;
  --warn:#96500A; --warn-bg:#FFF3E3; --warn-bd:#F5C892;
  --bad:#B42318; --bad-t:#9E2B2B; --bad-bg:#FDE8E8; --bad-bd:#F0B8B8;
  --r:12px; --r-lg:16px; --sombra:0 1px 2px rgba(20,60,100,.04);
}

/* ---------- base ---------- */
html, body, .stApp{ background:var(--bg) !important; color:var(--ink); }
.stApp, .stApp p, .stApp label, .stApp li, .stApp td, .stApp th, .stApp input,
.stApp textarea, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp [data-baseweb] , .stApp [data-testid="stMarkdownContainer"]{
  font-family:'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
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
.block-container, [data-testid="stMainBlockContainer"]{ max-width:100% !important; padding:0 clamp(20px, 4vw, 72px) 0 !important; }
[data-testid="stMain"], [data-testid="stAppViewContainer"]{ overflow-x:hidden; }
a{ color:var(--azul); }
a:hover{ color:var(--azul-h); }
:focus-visible{ outline:3px solid rgba(0,119,200,.35) !important; outline-offset:2px; }

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
  box-shadow:0 8px 18px rgba(0,119,200,.26) !important;
}
.stButton > button[kind="primary"] *, [data-testid="stBaseButton-primary"] *, [data-testid="stBaseButton-primaryFormSubmit"] *{ color:#FFFFFF !important; }
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover{
  background:var(--azul-h) !important; border-color:var(--azul-h) !important;
}
button:disabled, [data-testid^="stBaseButton"]:disabled{
  background:#E3EAF1 !important; color:#4A5560 !important; border-color:#E3EAF1 !important; cursor:not-allowed !important; box-shadow:none !important;
}
button:disabled *{ color:#4A5560 !important; }
/* botones bloqueados por falta de permiso: ámbar, borde punteado y candado (v7.6) */
[class*="st-key-bloq_"] button:disabled, [class*="st-key-bloq_"] [data-testid^="stBaseButton"]:disabled{
  background:#FFF3E3 !important; color:#8A4A06 !important; border:1.5px dashed #E8A14F !important; opacity:1 !important;
}
[class*="st-key-bloq_"] button:disabled *{ color:#8A4A06 !important; }

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
  border-color:var(--azul) !important; box-shadow:0 0 0 3px rgba(0,119,200,.22) !important;
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
.react-aria-ComboBox > [role="group"]:focus-within{ border-color:var(--azul) !important; box-shadow:0 0 0 3px rgba(0,119,200,.22) !important; }
[data-baseweb="tag"], span[data-tag]{ background:#E3F0FA !important; color:var(--navy) !important; border-radius:8px !important; }
[data-baseweb="tag"] span, [data-baseweb="tag"] svg, span[data-tag] span, span[data-tag] svg, span[data-tag] button{ color:var(--navy) !important; fill:var(--navy) !important; }
[data-baseweb="menu"] li, [data-baseweb="popover"] [role="option"], [data-testid="stSelectboxVirtualDropdown"] li{ font-size:15px !important; }
[data-testid="stFileUploaderDropzone"]{
  background:#F4F8FC !important; border:2px dashed #9CC3E3 !important; border-radius:var(--r-lg) !important; padding:28px 20px !important;
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
[data-testid="stMetricLabel"] p{ font-size:12.5px !important; font-weight:800 !important; letter-spacing:0; text-transform:none; color:var(--mute) !important; }
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
.info-card h4{ color:var(--mute) !important; font-size:12.5px !important; text-transform:none; letter-spacing:0; margin:0 0 6px !important; }
.info-card h2{ color:var(--navy) !important; font-size:28px !important; margin:0 !important; }
.icon-circle{ display:none !important; }
.alerta-roja, .alerta-amarilla, .zip-warning, .info-message, .excluidos-info{
  border-radius:var(--r) !important; padding:12px 16px !important; font-size:14px; color:var(--ink);
}
.alerta-roja{ background:var(--bad-bg) !important; border:1px solid var(--bad-bd) !important; border-left:5px solid var(--bad) !important; }
.alerta-amarilla, .zip-warning{ background:var(--warn-bg) !important; border:1px solid var(--warn-bd) !important; border-left:5px solid #E08A1E !important; }
.info-message, .excluidos-info{ background:#E8F1F8 !important; border:1px solid #B9D4EC !important; border-left:5px solid var(--azul) !important; }

/* ---------- componentes SIREA ---------- */
/* ---------- SIREA: identidad de la "A" (agentes) ---------- */
.sire-brand-txt b .sire-a{ color:#0077C8; }
.sire-a-foot{ color:#D9C7F2; font-weight:800; }
/* ---------- SIREA: componentes de IA (lila = diagnostico, pendiente de validar) ---------- */
.sirea-borrador{ position:relative; background:#FBF9FE; border:1.5px dashed #D9C7F2; border-radius:var(--r-lg); padding:18px 20px 16px; margin:8px 0 14px; color:#1F2A37; font-size:14.5px; line-height:1.55; }
.sirea-borrador.validado{ background:#F4FBF6; border:1.5px solid #A9D8BA; }
.sirea-borrador-cab{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.sirea-borrador-meta{ font-size:12px; color:var(--mute); font-weight:600; }
.sirea-borrador p{ margin:0 0 8px; }
.sirea-borrador ul{ margin:4px 0 8px 18px; }
.sirea-pie-ia{ margin-top:10px; padding-top:8px; border-top:1px solid #E8E0F3; font-size:12px; color:#5A2F8A; font-weight:700; display:flex; align-items:center; gap:6px; }
.sirea-agente{ background:#FFFFFF; border:1px solid var(--line); border-left:5px solid #6E3FA3; border-radius:var(--r-lg); padding:16px 18px 14px; box-shadow:var(--sombra); min-height:196px; display:flex; flex-direction:column; gap:8px; margin-bottom:14px; }
.sirea-agente.verde{ border-left-color:#1E6B3A; }
.sirea-agente.ambar{ border-left-color:#C9A000; }
.sirea-agente.rojo{ border-left-color:#B42318; }
.sirea-agente.gris{ border-left-color:#9AA6B2; background:#F7F9FB; }
.sirea-agente-cab{ display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
.sirea-agente-nom{ font-size:15.5px; font-weight:800; color:var(--navy); line-height:1.2; }
.sirea-agente-sub{ font-size:12px; color:var(--mute); font-weight:700; letter-spacing:0; text-transform:none; }
.sirea-agente-txt{ font-size:13.5px; color:#33424F; line-height:1.5; flex:1; }
.sirea-agente-pie{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.sirea-semaforo{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:800; letter-spacing:0; text-transform:none; }
.sirea-semaforo i{ width:10px; height:10px; border-radius:999px; display:inline-block; }
.sirea-prov{ display:inline-flex; align-items:center; gap:5px; font-size:11.5px; font-weight:700; color:#5A2F8A; background:#F3EDFA; border:1px solid #D9C7F2; border-radius:999px; padding:2px 9px; }
.sirea-chat-u{ background:#E3F0FA; border-radius:14px 14px 4px 14px; padding:10px 14px; margin:6px 0 6px 18%; font-size:14px; }
.sirea-chat-a{ background:#FBF9FE; border:1px solid #E8E0F3; border-radius:14px 14px 14px 4px; padding:12px 14px; margin:6px 18% 10px 0; font-size:14px; line-height:1.55; }
.sirea-chat-a .sirea-pie-ia{ margin-top:8px; }
/* SIREA 3.0: propuestas del Agente Operativo (lila punteado = propuesta de la IA pendiente) */
[class*="st-key-prop_"]{ background:#FBF9FE; border:1.5px dashed #D9C7F2; border-radius:var(--r-lg); padding:14px 18px 10px; margin:0 0 14px; }
.sirea-prop-cab{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.sirea-prop-tit{ font-size:16px; font-weight:800; color:var(--navy); }
.sirea-prop-sub{ font-size:12.5px; color:var(--mute); font-weight:600; margin-top:2px; }
.sirea-prop-just{ margin:8px 0 4px; font-size:14px; color:#1F2A37; line-height:1.5; }
.sirea-prop-dato{ font-size:13.5px; color:#33424F; margin:2px 0; }
.sirea-prop-dato b{ color:var(--navy); }
.sirea-traza{ border-left:3px solid #D9C7F2; padding:4px 0 4px 12px; margin:0 0 6px; font-size:13.5px; }
.sirea-traza b{ color:#5A2F8A; }
/* SIREA 3.2: recordatorio por tipo, información interna, vista previa, asistente */
table.sirea-falta{ width:100%; border-collapse:collapse; margin:4px 0 10px; font-size:13.5px; }
table.sirea-falta th{ text-align:left; background:#F2F6FA; color:#34495E; font-weight:600; padding:6px 8px; border-bottom:1px solid #DCE3EA; }
table.sirea-falta td{ padding:6px 8px; border-bottom:1px solid #EEF2F6; vertical-align:top; }
.sirea-interno{ background:#F7F3FC; border:1px dashed #B79AD9; border-radius:10px; padding:10px 12px; margin:6px 0 10px; font-size:13.5px; color:#3D2A5C; }
.sirea-interno-tit{ display:block; font-size:11.5px; font-weight:700; letter-spacing:0; text-transform:none; color:#6E3FA3; margin-bottom:4px; }
.sirea-preview{ background:#FFFFFF; border:1px solid #DCE3EA; border-radius:10px; padding:12px 14px; font-size:13.5px; white-space:pre-wrap; color:#1F2D3A; max-height:420px; overflow:auto; }
.sirea-preview hr{ border:none; border-top:1px solid #EEF2F6; margin:8px 0; }
.sirea-pasos{ display:flex; flex-direction:column; gap:10px; margin:4px 0 14px; }
.sirea-paso{ display:flex; gap:14px; align-items:flex-start; background:#FFFFFF; border:1px solid #DCE3EA; border-radius:12px; padding:12px 14px; font-size:14px; color:#1F2D3A; }
.sirea-paso-n{ flex:0 0 32px; height:32px; border-radius:50%; background:#EDE4F8; color:#5A2F8A; font-weight:800; display:flex; align-items:center; justify-content:center; }
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
.st-key-quipu_fab div.stButton button:hover{ background:#5A2F8A !important; transform:translateY(-1px); }
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
  background:linear-gradient(135deg,#1D3F76,#0077C8); color:#FFFFFF; flex:0 0 auto; }
.quipu-nombre{ font-size:17px; font-weight:800; color:#2B2140; line-height:1.1; }
.quipu-sub{ font-size:12px; color:#6B5E80; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.quipu-cab > div{ min-width:0; }
.quipu-vacio{ font-size:13.5px; color:#33424F; background:#FBF9FE; border:1px dashed #DCCFEE; border-radius:12px; padding:10px 12px; }
.st-key-quipu_caja [class*="st-key-quipu_sug_"] button, .st-key-quipu_caja_grande [class*="st-key-quipu_sug_"] button{
  justify-content:flex-start; text-align:left; border-radius:12px; border-color:#E4DAF1; color:#5A2F8A; font-size:13.5px; }
.quipu-chat{ display:flex; flex-direction:column-reverse; overflow-y:auto; overscroll-behavior:contain; padding-right:4px; }
.st-key-quipu_caja .quipu-chat{ max-height:min(330px, calc(100vh - 360px)); }
.st-key-quipu_caja_grande .quipu-chat{ max-height:calc(100vh - 380px); }
.st-key-quipu_tam button, .st-key-quipu_nueva button{ min-height:34px !important; height:34px; width:34px !important;
  padding:0 !important; border-radius:10px !important; border-color:#E4DAF1 !important; color:#5A2F8A !important; }
.st-key-quipu_tam, .st-key-quipu_nueva{ display:flex; justify-content:flex-end; }
@media (max-width: 640px){
  .st-key-quipu_fab{ right:14px; bottom:14px; }
  .st-key-quipu_caja, .st-key-quipu_caja_grande{ right:12px; left:12px; width:auto !important; bottom:74px; }
}
/* botones rojo/lila: incluir "-rojo" o "-lila" en la key del boton */
[class*="st-key-"][class*="-rojo"] div.stButton button{ background:#B42318 !important; border-color:#B42318 !important; color:#FFFFFF !important; }
[class*="st-key-"][class*="-rojo"] div.stButton button:hover{ background:#8E1B12 !important; border-color:#8E1B12 !important; }
[class*="st-key-"][class*="-lila"] div.stButton button, [class*="st-key-"][class*="-lila"] div.stFormSubmitButton button{ background:#6E3FA3 !important; border-color:#6E3FA3 !important; color:#FFFFFF !important; }
[class*="st-key-"][class*="-lila"] div.stButton button:hover, [class*="st-key-"][class*="-lila"] div.stFormSubmitButton button:hover{ background:#5A2F8A !important; border-color:#5A2F8A !important; }

.sire-chip{ display:inline-flex; align-items:center; gap:6px; padding:3px 11px; border-radius:999px; font-size:12.5px; font-weight:800; white-space:nowrap; }
.sire-bar{ display:flex; align-items:center; gap:10px; width:100%; }
.sire-bar-pista{ flex:1; height:10px; border-radius:999px; background:#E3F0FA; overflow:hidden; }
.sire-bar-pista > div{ height:100%; border-radius:999px; }
.sire-bar-n{ flex:none; min-width:44px; text-align:right; font-size:14px; font-weight:800; font-variant-numeric:tabular-nums; }
.sire-kpi{ position:relative; overflow:hidden; background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:18px 22px 18px 26px; min-height:168px; box-shadow:var(--sombra); }
.sire-kpi::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:5px; background:var(--k,#0077C8); }
.sire-kpi-top{ display:flex; align-items:center; justify-content:space-between; gap:12px; font-size:12px; font-weight:800; letter-spacing:0; text-transform:none; color:var(--mute); }
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
.sire-card-h{ padding:16px 24px; border-bottom:1px solid var(--line); background:#F4F8FC; font-size:16px; font-weight:800; color:var(--navy); }
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
.sire-codigo{ background:#F4F8FC; border:1px solid #D9E7F3; border-radius:14px; padding:16px 22px; margin:0 0 20px; display:flex; flex-direction:column; gap:2px; }
.sire-codigo-k{ font-size:12px; color:var(--mute); font-weight:800; letter-spacing:0; text-transform:none; }
.sire-codigo-v{ font-size:30px; font-weight:800; color:var(--navy); letter-spacing:.02em; font-variant-numeric:tabular-nums; }
.sire-scroll{ max-height:300px; overflow-y:auto; }
.sire-nota{ margin:4px 0 8px; font-size:13.5px; color:var(--mute); }
.sire-avance-n{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-top:12px; }
.sire-avance-n b{ font-size:28px; font-weight:800; color:var(--navy); font-variant-numeric:tabular-nums; }
.sire-avance-n span{ font-size:14px; color:var(--mute); }
.sire-avance-n span strong{ color:var(--ink); }
.sire-avance-pista{ margin:10px 0 4px; height:12px; border-radius:999px; background:#E3F0FA; overflow:hidden; }
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
.sire-sec-n{ width:34px; height:34px; border-radius:50%; background:var(--azul); color:#FFFFFF; font-size:16px; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; box-shadow:0 6px 14px rgba(0,119,200,.26); }
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
.sire-acuse-ambar{ background:linear-gradient(135deg,#8A5206 0%,#E08A1E 100%); }
.sire-acuse-naranja{ background:linear-gradient(135deg,#A94A08 0%,#D9680F 100%); }
.sire-acuse-in{ max-width:none; margin:0; padding:40px 0 44px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:28px; }
.sire-acuse-txt{ flex:1 1 520px; min-width:0; }
.sire-acuse-migas{ font-size:14px; font-weight:700; color:rgba(255,255,255,.85); margin-bottom:18px; }
.sire-acuse-ico{ width:64px; height:64px; border-radius:50%; background:rgba(255,255,255,.18); border:1.5px solid rgba(255,255,255,.4); display:flex; align-items:center; justify-content:center; margin-bottom:16px; }
.sire-acuse-eye{ display:block; font-size:13px; font-weight:800; letter-spacing:0; text-transform:none; color:rgba(255,255,255,.88); margin-bottom:6px; }
.stApp .sire-acuse h1{ color:#FFFFFF !important; font-size:38px !important; line-height:1.15 !important; margin:0 0 10px !important; padding:0 !important; }
.sire-acuse p{ margin:0; font-size:17px; line-height:1.5; color:#FFFFFF; max-width:640px; }
.sire-acuse-cod{ flex:0 0 auto; background:#FFFFFF; color:var(--ink); border-radius:18px; padding:20px 28px; box-shadow:0 14px 34px rgba(0,0,0,.18); min-width:300px; }
.sire-acuse-cod span{ display:block; font-size:12.5px; font-weight:800; letter-spacing:0; text-transform:none; color:var(--mute); margin-bottom:4px; }
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
.sire-pildora{ align-self:flex-start; display:inline-flex; align-items:center; gap:8px; border-radius:999px; padding:6px 14px; font-size:12.5px; font-weight:800; letter-spacing:0; text-transform:none; }
.st-key-sire_split_claro .sire-pildora{ background:#FFFFFF; color:#005C9C; box-shadow:0 2px 6px rgba(10,60,120,.12); }
.st-key-sire_split_oscuro .sire-pildora{ background:rgba(255,255,255,.16); color:#FFFFFF; border:1px solid rgba(255,255,255,.3); }
.sire-pt{ display:grid; grid-template-columns:34px minmax(0,1fr); gap:14px; align-items:flex-start; }
.sire-pt b{ width:34px; height:34px; border-radius:50%; background:#FFFFFF; color:var(--azul); display:inline-flex; align-items:center; justify-content:center; font-weight:800; font-size:15px; box-shadow:0 2px 6px rgba(10,60,120,.14); }
.sire-pt p{ font-size:16px !important; }
.sire-ck{ display:grid; grid-template-columns:20px minmax(0,1fr); gap:12px; align-items:flex-start; font-size:16px; line-height:1.4; color:#FFFFFF; }
.sire-ck svg{ margin-top:2px; }
.sire-split-in .sire-ck span{ color:#F0F7FC; }
.sire-split-logo{ height:72px; width:auto; align-self:flex-start; display:block; margin-bottom:36px; }
.sire-split-pie{ font-size:14px; font-weight:700; color:#E3F0FA; position:relative; margin-top:48px; }
.sire-vista{ position:relative; background:#FFFFFF; border-radius:18px; padding:20px 22px; max-width:440px; box-shadow:0 14px 34px rgba(0,70,130,.16); display:flex; flex-direction:column; gap:14px; color:var(--ink); }
.sire-vista-h{ display:flex; justify-content:space-between; align-items:center; gap:12px; font-weight:800; color:var(--navy); }
.sire-vista-h small{ font-size:12px; letter-spacing:0; text-transform:none; color:var(--mute); }
.sire-vista-n{ display:flex; align-items:baseline; gap:10px; }
.sire-vista-n b{ font-size:34px; font-weight:800; line-height:1; }
.sire-vista-n span{ font-size:14px; color:var(--mute); }
.sire-marca-agua{ position:absolute; right:-130px; bottom:-160px; width:540px; opacity:.1; pointer-events:none; }
[class*="st-key-sire_split"] [data-testid="stForm"]{ border-radius:20px !important; padding:34px !important; box-shadow:0 16px 40px rgba(20,70,120,.10); width:100%; }
.sire-form-t{ margin:0 !important; font-size:26px !important; line-height:1.2 !important; color:var(--navy) !important; }
.sire-form-s{ margin:6px 0 4px; font-size:16px; color:var(--mute); }
.sire-form-nota{ display:grid; grid-template-columns:20px minmax(0,1fr); gap:10px; background:#F4F8FC; border-radius:var(--r); padding:12px 14px; font-size:14px; color:var(--mute); margin-top:6px; }
.sire-form-nota svg{ margin-top:2px; }

.st-key-sire_login_admin [data-testid="stForm"], .st-key-sire_login_red [data-testid="stForm"]{ padding:28px !important; }
.stApp .sire-login-t{ margin:0 !important; font-size:26px !important; line-height:1.2 !important; color:var(--navy) !important; }
.sire-login-s{ margin:8px 0 24px; font-size:16px; color:var(--mute); }
.sire-login-n{ margin:16px 0 0; font-size:14px; color:var(--mute); display:flex; align-items:center; gap:8px; }
.sire-eye{ margin:0 0 8px; font-size:13px; font-weight:800; letter-spacing:0; text-transform:none; color:var(--mute); }

/* ---------- enlaces con forma de boton de texto ---------- */
[class*="st-key-link_"] .stButton > button{ background:transparent !important; border:0 !important; box-shadow:none !important; color:var(--azul) !important; min-height:auto; padding:0 !important; font-weight:800 !important; text-decoration:underline; justify-content:flex-start; }
[class*="st-key-link_"] .stButton > button *{ color:var(--azul) !important; }
[class*="st-key-link_"] .stButton > button:hover{ background:transparent !important; color:var(--azul-h) !important; }
.st-key-sire_form_card{ background:#FFFFFF; border:1px solid var(--line); border-radius:20px; padding:34px !important; box-shadow:0 16px 40px rgba(20,70,120,.10); width:100%; }
.sire-pie-form{ border-top:1px solid #EAF1F8; padding-top:16px; margin-top:8px; font-size:14px; color:var(--mute); }

/* ---------- requisitos de contrasena ---------- */
.sire-req{ background:#F4F8FC; border-radius:var(--r); padding:14px 16px; display:flex; flex-direction:column; gap:8px; margin:4px 0 12px; }
.sire-req-t{ font-weight:800; font-size:14px; color:var(--navy); margin-bottom:2px; }
.sire-req-i{ display:flex; align-items:flex-start; gap:10px; font-size:14.5px; color:#33485A; line-height:1.35; }
.sire-req-i svg{ margin-top:1px; }
.sire-req-i.ok{ color:var(--ok); font-weight:700; }
.sire-fuerza{ display:flex; align-items:center; gap:12px; margin:2px 0 4px; }
.sire-fuerza-p{ flex:1; display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
.sire-fuerza-p i{ height:8px; border-radius:999px; background:#E3F0FA; }
.sire-fuerza-n{ font-size:13.5px; font-weight:800; min-width:96px; text-align:right; }
.sire-porque{ font-size:14px; color:#33485A; line-height:1.5; }
.sire-porque b{ color:var(--navy); }
.sire-porque ul{ margin:6px 0 0; padding-left:20px; }
.sire-porque li{ margin:0 0 6px !important; }

/* ---------- sugerencias de usuario ---------- */
.st-key-sire_sugerencias{ background:#F4F8FC; border:1px solid #D9E7F3; border-radius:var(--r); padding:12px 16px !important; gap:12px !important; margin-bottom:8px; }
.st-key-sire_sugerencias .sire-req-i span{ display:block; line-height:1.45; }
.sire-req-i.mal{ color:#9E2B2B; font-weight:700; }
.sire-req-m{ display:none; font-weight:400; color:#5C3A3A; font-size:13.5px; margin-top:2px; }
.sire-req-i.mal .sire-req-m{ display:block; }
.sire-req-ico{ display:inline-flex; flex:0 0 auto; }
.sire-req-x{ color:#4F6070; font-weight:600; }
.sire-req-listo{ margin-top:4px; padding:10px 12px; border-radius:10px; background:#E3F0FA; color:#33485A; font-size:14px; font-weight:700; }
.sire-req-listo.ok{ background:#E3F4EA; color:#1E6B3A; }
.sire-req-vivo{ margin-top:0; }
.sire-req-vivo .sire-req-i[data-req="largo_max"]:not(.mal){ display:none; }
.st-key-sire_sugerencias .stButton > button{ min-height:36px; padding:0 14px; font-size:14px !important; border-radius:999px !important; }

/* ---------- usuarios frecuentes y verificación de correo ---------- */
.st-key-sire_frec_wrap{ position:absolute !important; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; margin:0 !important; }
.st-key-sire_frecuentes{ background:#F4F8FC; border:1px solid #D9E7F3; border-radius:var(--r); padding:14px 16px !important; gap:8px !important; margin-bottom:12px; }
.st-key-sire_frecuentes [data-testid="stHorizontalBlock"]{ gap:8px !important; }
.sire-frec-t{ font-weight:800; color:var(--navy); font-size:15px; }
.sire-frec-s{ color:#33485A; font-size:13.5px; line-height:1.45; margin-bottom:4px; }
.st-key-sire_frecuentes .stButton > button{ min-height:38px; font-size:14px !important; justify-content:flex-start; }
.st-key-sire_frecuentes [class*="st-key-frec_quitar"] .stButton > button{ min-width:38px; padding:0; justify-content:center; }
.st-key-sire_sugerencias_correo{ gap:10px !important; margin-bottom:8px; }
.sire-correo-ok{ display:flex; align-items:center; gap:8px; color:#1E5E34; font-size:14px; margin:-2px 0 6px; }

/* ---------- intercambio de mensajes (solicitudes de contraseña) ---------- */
.sire-hilo{ display:flex; flex-direction:column; gap:12px; padding:14px; background:#F4F8FC; border:1px solid #D9E7F3; border-radius:var(--r); max-height:560px; overflow-y:auto; }
.sire-msg{ max-width:100%; border-radius:14px; padding:10px 14px; font-size:14.5px; line-height:1.5; }
.sire-msg-cab{ display:flex; flex-wrap:wrap; gap:4px 10px; align-items:baseline; margin-bottom:4px; }
.sire-msg-cab b{ font-size:13.5px; }
.sire-msg-cab span{ font-size:12px; opacity:.8; }
.sire-msg-otro{ align-self:flex-start; background:#FFFFFF; border:1px solid #D5DDE4; color:#14202B; border-bottom-left-radius:4px; }
.sire-msg-yo{ align-self:flex-end; background:#0077C8; color:#FFFFFF; border-bottom-right-radius:4px; }
.sire-msg-yo .sire-msg-cab span{ color:#E3F0FA; opacity:1; }
/* SIREA 3.5: mensajes a todo el ancho del hilo (sin hueco al costado); el color distingue quién escribe */
.sire-msg-otro, .sire-msg-yo{ align-self:stretch !important; }
.sire-msg-sis{ align-self:center; text-align:center; }
.sire-msg-sis span{ display:inline-block; background:#E3F0FA; color:#33485A; font-size:12.5px; padding:3px 12px; border-radius:999px; }
.st-key-sire_solicitud_red{ background:#F4F8FC; border:1px solid #D9E7F3; border-radius:var(--r); padding:16px 18px !important; margin-bottom:12px; }

/* dato suelto (etiqueta + valor) */
.sire-dato small{ display:block; color:#4F6070; font-size:12.5px; font-weight:700; letter-spacing:0; text-transform:none; margin-bottom:4px; }
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
.sire-hero-per{ font-size:14px; font-weight:700; letter-spacing:0; text-transform:none; opacity:.9; }
.stApp .sire-hero-h1{ margin:4px 0 14px !important; font-size:44px !important; line-height:1.1 !important; font-weight:800 !important; color:#FFFFFF !important; letter-spacing:-.01em; }
.sire-hero-p{ margin:0 0 22px; font-size:17px; line-height:1.55; max-width:520px; color:#F0F7FC; }
.sire-glass{ background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.3); border-radius:20px; padding:26px 28px; display:flex; flex-direction:column; gap:18px; backdrop-filter:blur(6px); }
.sire-glass-top{ display:flex; justify-content:space-between; align-items:flex-end; gap:12px; }
.sire-glass-k{ font-size:13px; font-weight:800; letter-spacing:0; text-transform:none; opacity:.9; display:block; }
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
[class*="st-key-op_"]:hover{ border-color:var(--azul); box-shadow:0 10px 26px rgba(0,119,200,.14); transform:translateY(-2px); }
.sire-op{ min-height:250px; }
.sire-op-ico{ width:52px; height:52px; border-radius:14px; display:flex; align-items:center; justify-content:center; margin-bottom:14px; }
.sire-op-eye{ margin:0 0 4px; font-size:12px; font-weight:800; letter-spacing:0; text-transform:none; color:var(--mute); }
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
.sire-franja{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:14px; padding:24px 0 4px; font-size:15px; }
.sire-franja span{ display:flex; align-items:center; justify-content:center; gap:10px; font-weight:700; border-radius:14px; padding:16px 18px; }
.sire-franja span:nth-child(1){ background:#E6F4FB; color:#005C9C; }
.sire-franja span:nth-child(2){ background:#E3F5EC; color:#15784B; }
.sire-franja span:nth-child(3){ background:#F3EDFA; color:#5A2F8A; }
.sire-franja span svg{ stroke:currentColor !important; }
@media (max-width: 760px){ .sire-franja{ grid-template-columns:minmax(0,1fr); } }

/* ---------- pie de pagina ---------- */
.sire-foot{ position:relative; isolation:isolate; margin-top:56px; }
.sire-foot::before{
  content:""; position:absolute; z-index:-1; top:0; bottom:0; left:50%; width:100vw; margin-left:-50vw; background:#0B5A9E;
}
.sire-foot-in{ display:flex; flex-wrap:wrap; gap:16px 40px; align-items:center; justify-content:space-between; padding:28px 0; color:#FFFFFF; }
.sire-foot-logos{ display:flex; align-items:center; gap:20px; }
.sire-foot-sep{ width:1px; height:40px; background:rgba(255,255,255,.35); }
.sire-foot-essalud{ height:48px; width:auto; display:block; }
.sire-foot-oiis{ height:60px; width:auto; display:block; }
.sire-foot-txt{ flex:1 1 360px; display:flex; flex-direction:column; text-align:right; font-size:13.5px; line-height:1.6; }
.sire-foot-txt b{ color:#FFFFFF; font-weight:800; font-size:14.5px; }
.sire-foot-sub{ color:#FFFFFF; }

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
:root{ --navy:#1D3F76; }
/* ---------- estructura del panel ---------- */
[data-testid="stMainBlockContainer"], .block-container{ max-width:100% !important; padding:0 40px 0 !important; }
[data-testid="stSidebar"]{
  background:#E3F0FA !important; border-right:1px solid #D9E7F3;
  min-width:272px !important; max-width:272px !important; width:272px !important;
  transform:none !important; margin-left:0 !important; visibility:visible !important;
}
[data-testid="stSidebar"] > div, [data-testid="stSidebarContent"]{ background:#E3F0FA !important; }
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"]{ display:none !important; }
[data-testid="stSidebarHeader"]{ display:none !important; }
[data-testid="stSidebarContent"]{ padding:0 12px 16px !important; }
[data-testid="stSidebarUserContent"]{ padding:22px 0 0 !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{ gap:2px !important; }
[data-testid="stSidebar"] .stButton{ margin:0 !important; }
[data-testid="stSidebar"] .stButton > button{
  position:relative; min-height:42px; width:100%; justify-content:flex-start; background:transparent !important; border:0 !important;
  border-radius:10px !important; color:#25445E !important; font-weight:700 !important; font-size:14.5px !important; padding:0 14px !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] .stButton > button *{ color:inherit !important; }
[data-testid="stSidebar"] .stButton > button:hover{ background:#D4E9FA !important; color:#1D3F76 !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"]{
  background:#FFFFFF !important; color:#1D3F76 !important; font-weight:800 !important; box-shadow:0 1px 4px rgba(10,60,120,.14) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]::before{
  content:""; position:absolute; left:-12px; top:9px; bottom:9px; width:4px; border-radius:0 4px 4px 0; background:#0077C8;
}
[data-testid="stSidebar"] .stButton > button > div{ justify-content:flex-start !important; gap:12px; }
[data-testid="stSidebar"] .stButton > button p{ text-align:left; }
[data-testid="stSidebar"] [class*="st-key-nav_salir"] button{
  border:1.5px solid #B9D4EC !important; color:#1D3F76 !important; justify-content:center; font-weight:800 !important; margin-top:6px; min-height:44px; background:#FFFFFF !important;
}
[data-testid="stSidebar"] [class*="st-key-nav_salir"] button > div{ justify-content:center !important; }
[data-testid="stSidebar"] [class*="st-key-nav_salir"] button:hover{ background:#D4E9FA !important; }
.sire-side-brand{ display:flex; align-items:center; gap:12px; padding:0 14px 18px; border-bottom:1px solid #D9E7F3; margin-bottom:14px; }
.sire-side-brand b{ display:block; font-size:21px; font-weight:800; letter-spacing:.05em; color:#1D3F76; line-height:1.15; }
.sire-side-brand small{ display:block; font-size:12.5px; color:#4F6F8A; font-weight:600; }
.sire-side-grupo{ padding:16px 14px 10px; font-size:11.5px; font-weight:800; letter-spacing:0; text-transform:none; color:#5A7D99; }
.sire-side-user{ display:flex; align-items:center; gap:12px; padding:18px 6px 12px; border-top:1px solid #D9E7F3; margin-top:22px; }
.sire-avatar{ width:42px; height:42px; border-radius:50%; background:#0077C8; color:#FFFFFF; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; }
.sire-side-user b{ display:block; font-size:15px; font-weight:800; color:#1B3347; line-height:1.25; margin-bottom:4px; }
.sire-side-user .sire-chip{ background:#FFFFFF !important; color:#1D3F76 !important; border:1px solid #B9D4EC !important; font-size:11.5px; padding:1px 9px; letter-spacing:.05em; }
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
.sire-vacio{ padding:28px 16px; text-align:center; color:var(--mute); font-size:15px; border:1.5px dashed #C4D6E6; border-radius:var(--r); background:#FAFCFE; }

/* ---------- tablas ---------- */
[data-testid="stElementContainer"]:has(.sire-tabla-wrap), [data-testid="stMarkdownContainer"]:has(.sire-tabla-wrap){ min-width:0; max-width:100%; }
.sire-nowrap .sire-tabla th, .sire-nowrap .sire-tabla td{ white-space:nowrap; }
.sire-tabla-wrap{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--r); background:#FFFFFF; }
.stApp table.sire-tabla{ width:100%; border-collapse:collapse; font-size:14px; color:var(--ink); margin:0; }
.stApp table.sire-tabla th{
  background:#D4E9FA !important; color:#1D3F76 !important; font-weight:800; font-size:12.5px; letter-spacing:.03em; text-align:left;
  padding:12px 14px; border:0 !important; border-bottom:1px solid var(--line) !important; white-space:nowrap;
}
.stApp table.sire-tabla td{ padding:12px 14px; border:0 !important; border-bottom:1px solid #EAF1F8 !important; vertical-align:middle; background:#FFFFFF; }
.stApp table.sire-tabla tr:last-child td{ border-bottom:0 !important; }
.stApp table.sire-tabla tbody tr:nth-child(even) td{ background:#FAFCFE; }
.stApp table.sire-tabla tbody tr:hover td{ background:#F4F8FC; }
.stApp table.sire-tabla .num{ text-align:right; font-variant-numeric:tabular-nums; }

/* ---------- barras horizontales y cumplimiento ---------- */
.sire-hbars{ display:flex; flex-direction:column; gap:12px; padding:6px 0; }
.sire-hb{ display:grid; grid-template-columns:minmax(90px,150px) 1fr 40px; align-items:center; gap:12px; font-size:14px; }
.sire-hb-k{ text-align:right; color:#33485A; overflow-wrap:anywhere; }
.sire-hb-pista{ height:14px; border-radius:999px; background:#E3F0FA; overflow:hidden; display:block; }
.sire-hb-pista > span{ display:block; height:100%; border-radius:999px; }
.sire-hb-v{ font-weight:800; font-variant-numeric:tabular-nums; }
.sire-cums{ display:flex; flex-direction:column; gap:16px; padding:4px 0; }
.sire-cum-h{ display:flex; justify-content:space-between; gap:12px; font-size:14px; margin-bottom:4px; font-weight:700; }
.sire-cum-d{ color:var(--mute); font-weight:400; }

/* ---------- avisos con boton (contenedores con key "banner_*") ---------- */
[class*="st-key-banner"]{ border-radius:var(--r); padding:14px 18px !important; margin:8px 0; }
.st-key-banner_warn{ background:#FFF6EC; border:1px solid var(--warn-bd); border-left:5px solid #E08A1E; }
.st-key-banner_bad{ background:var(--bad-bg); border:1px solid var(--bad-bd); border-left:5px solid var(--bad); }
.st-key-banner_info{ background:#E8F1F8; border:1px solid #B9D4EC; border-left:5px solid var(--azul); }
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
  background:#F4F8FC; border:1px solid var(--line); border-radius:var(--r); padding:12px 16px; margin:0 0 16px;
  display:flex; flex-wrap:wrap; gap:8px 24px; font-size:14px; color:#33485A;
}
.resumen-card strong{ color:var(--ink); }
.dataframe-container{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--r); margin-bottom:16px; }
</style>
"""


_CSS_RED = """
<style>
:root{ --navy:#1D3F76; }
/* Pantallas de las redes: paneles, tablas (encabezado azul claro) y controles de las tablas navegables.
   Las reglas de tablas y paneles son las mismas del panel de administración; aquí se repiten porque
   esas solo se cargan en el panel. */
[class*="st-key-red_panel"]{
  background:#FFFFFF; border:1px solid var(--line); border-radius:var(--r-lg); padding:22px 24px 24px !important; margin:16px 0 !important; box-shadow:var(--sombra);
}
.sire-panel-h h2{ margin:0 !important; font-size:20px !important; font-weight:800 !important; color:var(--navy) !important; padding:0 !important; }
.sire-panel-s{ margin-top:2px; font-size:14px; color:var(--mute); }
.sire-panel-h{ margin-bottom:12px; }
.sire-vacio{ padding:28px 16px; text-align:center; color:var(--mute); font-size:15px; border:1.5px dashed #C4D6E6; border-radius:var(--r); background:#FAFCFE; }

/* ---------- tablas ---------- */
[data-testid="stElementContainer"]:has(.sire-tabla-wrap), [data-testid="stMarkdownContainer"]:has(.sire-tabla-wrap){ min-width:0; max-width:100%; }
.sire-nowrap .sire-tabla th, .sire-nowrap .sire-tabla td{ white-space:nowrap; }
.sire-tabla-wrap{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--r); background:#FFFFFF; }
.stApp table.sire-tabla{ width:100%; border-collapse:collapse; font-size:14px; color:var(--ink); margin:0; }
.stApp table.sire-tabla th{
  background:#D4E9FA !important; color:#1D3F76 !important; font-weight:800; font-size:12.5px; letter-spacing:.03em; text-align:left;
  padding:12px 14px; border:0 !important; border-bottom:1px solid var(--line) !important; white-space:nowrap;
}
.stApp table.sire-tabla td{ padding:12px 14px; border:0 !important; border-bottom:1px solid #EAF1F8 !important; vertical-align:middle; background:#FFFFFF; }
.stApp table.sire-tabla tr:last-child td{ border-bottom:0 !important; }
.stApp table.sire-tabla tbody tr:nth-child(even) td{ background:#FAFCFE; }
.stApp table.sire-tabla tbody tr:hover td{ background:#F4F8FC; }
.stApp table.sire-tabla .num{ text-align:right; font-variant-numeric:tabular-nums; }

/* tablas de las redes: encabezado azul claro, filas legibles */
.stApp .sire-tabla-azul table.sire-tabla th{
  background:#D4E9FA !important; color:#1D3F76 !important; border-bottom:2px solid #B9D4EC !important; font-size:13px;
}
.stApp .sire-tabla-azul table.sire-tabla tbody tr:nth-child(even) td{ background:#F4F8FC; }
.stApp .sire-tabla-azul table.sire-tabla tbody tr:hover td{ background:#E3F0FA; }
.sire-tabla-azul{ border-color:#B9D4EC; }
[class*="st-key-tnav_"]{ background:#F4F8FC; border:1px solid #D9E7F3; border-radius:14px; padding:14px 16px !important; gap:10px !important; margin-bottom:10px; }
[class*="st-key-tnav_"] label p{ font-size:13px !important; font-weight:700 !important; color:var(--navy) !important; }
[class*="st-key-tpie_"]{ margin:8px 0 6px; }
.sire-tpie-n{ font-size:14px; color:#33485A; }
.sire-tpie-p{ font-size:14px; color:#33485A; text-align:center; white-space:nowrap; }
[class*="st-key-tpie_"] .stButton > button{ min-height:38px; padding:0 12px; font-size:14px !important; }

.sire-tabla-azul .sire-bar{ min-width:170px; }

/* filtros aplicados */
.sire-fchips{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.sire-fchips-t{ font-size:13px; font-weight:800; color:#4F6070; margin-right:2px; }
.sire-fchip{ display:inline-flex; align-items:center; gap:4px; background:#D4E9FA; color:#1D3F76; border-radius:999px; padding:3px 12px; font-size:13px; max-width:100%; overflow-wrap:anywhere; }
.sire-fchip b{ font-weight:800; }
[class*="st-key-tnav_"] [data-testid="stDateInput"] input{ font-size:14px; }

/* responsables de la red (Notificaciones) */
[class*="st-key-resp_card"]{ border:1px solid #D5E3EF; border-radius:12px; padding:10px 14px !important; background:#FFFFFF; margin-bottom:8px; }
.sire-resp b{ font-size:15px; margin-right:6px; }
.sire-resp-m{ font-size:14px; color:var(--mute); margin-top:2px; }
.sire-resp-c{ font-size:13px; color:#4F6070; margin-top:4px; }
.sire-res{ display:grid; grid-template-columns:auto 1fr; gap:6px 14px; font-size:14px; padding:10px 0; }
.sire-res-k{ color:var(--mute); }
.sire-res-v{ font-weight:800; text-align:right; overflow-wrap:anywhere; }
.sire-res-l{ margin:4px 0 6px 18px; padding:0; font-size:14px; }
.sire-res-l span{ display:block; color:var(--mute); font-size:13px; }
</style>
"""



# ============================================================
# BANDA AZUL DE LAS PANTALLAS PÚBLICAS (encabezado + cabecera, con el búho de la OIIS de marca de agua)
# ============================================================

_CSS_BANDA = """
<style>
.st-key-sire_banda{
  position:relative; isolation:isolate; overflow:hidden; color:#FFFFFF;
  width:100vw !important; max-width:100vw !important; margin-left:calc(50% - 50vw) !important; margin-bottom:-80px !important;
  padding:0 clamp(20px, 4vw, 72px) 110px !important;
  background:
    radial-gradient(900px 480px at 82% 18%, rgba(65,182,230,.50) 0%, rgba(65,182,230,0) 60%),
    radial-gradient(760px 480px at 0% 100%, rgba(10,60,120,.50) 0%, rgba(10,60,120,0) 65%),
    linear-gradient(135deg, #005C9C 0%, #0077C8 45%, #13213A 100%);
}
.st-key-sire_banda:has(.sire-tono-rojo){ background:radial-gradient(900px 480px at 82% 18%, rgba(255,170,160,.40) 0%, rgba(255,170,160,0) 60%), linear-gradient(135deg, #8E1F1F 0%, #B93232 100%); }
.st-key-sire_banda:has(.sire-tono-ambar){ background:radial-gradient(900px 480px at 82% 18%, rgba(255,215,140,.40) 0%, rgba(255,215,140,0) 60%), linear-gradient(135deg, #8A5206 0%, #E08A1E 100%); }
.st-key-sire_banda:has(.sire-tono-naranja){ background:radial-gradient(900px 480px at 82% 18%, rgba(255,200,150,.40) 0%, rgba(255,200,150,0) 60%), linear-gradient(135deg, #A94A08 0%, #D9680F 100%); }
.st-key-sire_banda::before{
  content:""; position:absolute; z-index:-1; right:-90px; top:40px; width:min(640px,60vw); aspect-ratio:1296/1176; opacity:.13; pointer-events:none;
  background:url("__MARCA__") no-repeat center / contain;
}
.st-key-sire_banda::after{
  content:""; position:absolute; z-index:-1; inset:0; pointer-events:none;
  background:linear-gradient(112deg, rgba(255,255,255,.16) 0%, rgba(255,255,255,.05) 30%, rgba(255,255,255,0) 31%);
}
.st-key-sire_banda ~ *, .stApp:has(.st-key-sire_banda) [class*="st-key-sec_"], .stApp:has(.st-key-sire_banda) .st-key-sire_enviar,
.stApp:has(.st-key-sire_banda) [class*="st-key-red_panel"]{ position:relative; z-index:1; }
/* encabezado sobre el azul */
.st-key-sire_banda .st-key-sire_hdr::before{ background:transparent; border:0; }
.st-key-sire_banda .sire-brand-essalud{ filter:brightness(0) invert(1); }
.st-key-sire_banda .sire-brand-sep{ background:rgba(255,255,255,.45); }
.st-key-sire_banda .sire-brand-txt b{ color:#FFFFFF; }
.st-key-sire_banda .sire-brand-txt b .sire-a{ color:#D9C7F2; }   /* SIREA: la «A» lila clara sobre el azul */
.st-key-sire_banda .sire-brand-txt small{ color:#E3F0FA; }
.st-key-sire_banda .sire-brand svg rect:first-child{ fill:#FFFFFF; }
.st-key-sire_banda .sire-brand svg rect:nth-child(n+2){ fill:#0077C8; }
.st-key-sire_banda .sire-semana-chip{ display:none; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button{
  min-height:44px; padding:0 12px !important; white-space:nowrap; border-radius:999px !important; border:1px solid rgba(255,255,255,.55) !important; color:#FFFFFF !important;
  background:linear-gradient(135deg, rgba(255,255,255,.30), rgba(255,255,255,.10)) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.55), 0 6px 16px rgba(10,60,120,.18) !important; backdrop-filter:blur(10px); font-weight:700 !important;
}
.st-key-sire_banda .st-key-sire_hdr .stButton > button *{ color:#FFFFFF !important; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button:hover{ background:linear-gradient(135deg, rgba(255,255,255,.42), rgba(255,255,255,.18)) !important; color:#FFFFFF !important; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button[kind="primary"]{ background:#FFFFFF !important; border-color:#FFFFFF !important; box-shadow:0 6px 16px rgba(10,60,120,.25) !important; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button[kind="primary"] *{ color:#0077C8 !important; }
.st-key-sire_banda .st-key-sire_hdr [class*="st-key-nav_pub_admin"] .stButton > button{
  background:linear-gradient(135deg, #1D3F76, #13213A) !important; border-color:rgba(255,255,255,.45) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(10,60,120,.35) !important; }
/* cabecera de la pantalla */
.st-key-sire_hero_pag{ padding:20px 0 0 !important; }
.sire-bp{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(320px,1fr); align-items:center; gap:28px 40px; }
.sire-bp:not(:has(.sire-bp-tile)){ grid-template-columns:minmax(0,1fr); }
.sire-bp-txt{ min-width:0; }
@media (max-width: 900px){ .sire-bp{ grid-template-columns:minmax(0,1fr); } }
.stApp .sire-bp-h1{ margin:18px 0 0 !important; padding:0 !important; font-size:46px !important; line-height:1.06 !important; font-weight:800 !important; color:#FFFFFF !important; letter-spacing:-.02em; }
.stApp .sire-bp-p{ margin:14px 0 0 !important; font-size:18px; line-height:1.5; color:#EAF4FC; max-width:none; }
.st-key-sire_banda .sire-hero-chip{ background:rgba(255,255,255,.20); border:1px solid rgba(255,255,255,.55); backdrop-filter:blur(10px); display:inline-flex; align-items:center; gap:10px; border-radius:999px; padding:7px 16px 7px 12px; font-size:13.5px; font-weight:700; }
.st-key-sire_banda .sire-hero-chip i{ width:9px; height:9px; border-radius:50%; background:#8CF0B4; box-shadow:0 0 0 4px rgba(140,240,180,.3); }
.st-key-sire_banda .sire-hero-chip.cerrada i{ background:#FFB4B4; box-shadow:0 0 0 4px rgba(255,180,180,.3); }
.sire-cristal{
  background:linear-gradient(112deg, rgba(255,255,255,.30) 0%, rgba(255,255,255,.08) 42%, rgba(255,255,255,.04) 43%, rgba(255,255,255,.14) 100%), rgba(10,60,120,.22);
  border:1px solid rgba(255,255,255,.5); box-shadow:inset 0 1px 0 rgba(255,255,255,.6), 0 20px 40px rgba(10,60,120,.28);
  backdrop-filter:blur(16px); border-radius:24px; color:#FFFFFF;
}
.sire-bp-tile{ width:100%; box-sizing:border-box; min-width:0; padding:24px 28px; display:flex; align-items:center; gap:22px; }
.sire-bp-num{ font-size:76px; font-weight:800; line-height:.85; letter-spacing:-.04em; }
.sire-bp-tile small{ display:block; font-size:13px; font-weight:800; letter-spacing:0; text-transform:none; color:#EAF4FC; }
.sire-bp-tile b{ display:block; font-size:18px; margin-top:3px; }
.sire-bp-tile em{ display:block; font-style:normal; margin-top:8px; font-size:14px; font-weight:700; color:#FFFFFF; }
.sire-bp-ring{ position:relative; width:130px; height:130px; flex:none; }
.sire-bp-ring > div{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; font-size:30px; font-weight:800; line-height:1; }
.sire-bp-ring > div span{ font-size:12px; font-weight:600; margin-top:3px; }
.sire-bp-3{ display:flex; gap:10px; margin-top:10px; }
.sire-bp-3 div{ flex:1; background:rgba(255,255,255,.14); border-radius:14px; padding:10px 12px; font-size:12.5px; color:#EAF4FC; }
.sire-bp-3 b{ display:block; font-size:26px; line-height:1; margin:0 0 2px; }
.st-key-sire_banda [class*="st-key-sire_hero_pag"] .stButton > button{
  min-height:48px; border-radius:14px !important; font-weight:700 !important; border:1px solid rgba(255,255,255,.6) !important; color:#FFFFFF !important;
  background:linear-gradient(135deg, rgba(255,255,255,.30), rgba(255,255,255,.10)) !important; box-shadow:inset 0 1px 0 rgba(255,255,255,.55) !important; backdrop-filter:blur(10px);
}
.st-key-sire_banda [class*="st-key-sire_hero_pag"] .stButton > button *{ color:#FFFFFF !important; }
/* acuse de recibo dentro de la banda */
.st-key-sire_banda .sire-acuse{ width:auto; margin:0; background:transparent !important; }
.st-key-sire_banda .sire-acuse-in{ padding:20px 0 0; max-width:none; }
.st-key-sire_banda .sire-acuse-migas{ display:none; }
.st-key-sire_banda .sire-acuse-cod{ background:linear-gradient(112deg, rgba(255,255,255,.30) 0%, rgba(255,255,255,.08) 42%, rgba(255,255,255,.04) 43%, rgba(255,255,255,.14) 100%), rgba(10,60,120,.22);
  border:1px solid rgba(255,255,255,.5); box-shadow:inset 0 1px 0 rgba(255,255,255,.6), 0 20px 40px rgba(10,60,120,.28); backdrop-filter:blur(16px); border-radius:24px; color:#FFFFFF; }
.st-key-sire_banda .sire-acuse-cod span{ color:#EAF4FC; }
.st-key-sire_banda .sire-acuse-cod b{ color:#FFFFFF !important; font-size:32px; letter-spacing:.04em; }
.sire-tono{ display:none; }
/* tarjetas y tablas de estas pantallas: más redondeadas, con sombra suave y acento de color */
.stApp:has(.st-key-sire_banda) [class*="st-key-sec_"]{ border-radius:24px; box-shadow:0 16px 40px rgba(10,60,120,.12); border-color:#E1EAF3; }
.stApp:has(.st-key-sire_banda) .sire-sec-n{ width:36px; height:36px; }
.stApp:has(.st-key-sire_banda) .sire-card, .stApp:has(.st-key-sire_banda) .sire-panel, .stApp:has(.st-key-sire_banda) .sire-kpi{ border-radius:24px; box-shadow:0 16px 40px rgba(10,60,120,.12); border-color:#E1EAF3; }
.stApp:has(.st-key-sire_banda) .sire-kpi{ box-shadow:0 24px 48px rgba(10,60,120,.18); }
.stApp:has(.st-key-sire_banda) [class*="st-key-red_panel"]{ border-radius:24px; border-color:#E1EAF3; box-shadow:inset 0 6px 0 #0077C8, 0 16px 40px rgba(10,60,120,.12); padding-top:30px !important; }
.stApp:has(.st-key-sire_banda) .st-key-red_panel_quien{ box-shadow:inset 0 6px 0 #1E6B3A, 0 16px 40px rgba(10,60,120,.12); }
.stApp:has(.st-key-sire_banda) .st-key-red_panel_obs{ box-shadow:inset 0 6px 0 #E8A14F, 0 16px 40px rgba(10,60,120,.12); }
.stApp:has(.st-key-sire_banda) .sire-card-h{ background:#FFFFFF; font-size:17px; }
.stApp:has(.st-key-sire_banda) .stApp .sire-h2, .stApp:has(.st-key-sire_banda) .sire-h2{ font-size:28px !important; letter-spacing:-.01em; margin-top:48px !important; }
.stApp:has(.st-key-sire_banda) table.sire-tabla th, .stApp:has(.st-key-sire_banda) .sire-tabla-azul table.sire-tabla th{ background:#1D3F76 !important; color:#FFFFFF !important; border-bottom:0 !important; }
.stApp:has(.st-key-sire_banda) table.sire-tabla tbody tr:nth-child(even) td{ background:#F7F9FE; }

/* ===== v8.0: más cerca del diseño aprobado ===== */
.sire-sec-estado{ margin-left:auto; display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:5px 12px; font-size:13px; font-weight:800; white-space:nowrap; }
.stApp:has(.st-key-sire_banda) .sire-sec-h{ padding:22px 28px 18px; }
.stApp:has(.st-key-sire_banda) .sire-sec-n{ width:38px; height:38px; font-size:17px; }
.stApp:has(.st-key-sire_banda) .stApp .sire-sec-h h2, .stApp:has(.st-key-sire_banda) .sire-sec-h h2{ font-size:21px !important; }
/* campos */
.stApp:has(.st-key-sire_banda) div[data-baseweb="select"] > div, .stApp:has(.st-key-sire_banda) [data-testid="stTextInputRootElement"],
.stApp:has(.st-key-sire_banda) [data-testid="stTextAreaRootElement"]{ border:1.5px solid #C4D6E6 !important; border-radius:12px !important; min-height:50px; background:#FFFFFF; }
.stApp:has(.st-key-sire_banda) [data-testid="stTextAreaRootElement"]{ min-height:110px; }
.stApp:has(.st-key-sire_banda) [data-baseweb="tag"], .stApp:has(.st-key-sire_banda) span[data-tag]{ background:#0077C8 !important; color:#FFFFFF !important; border-radius:999px !important; padding:3px 6px 3px 12px !important; font-weight:600; }
.stApp:has(.st-key-sire_banda) [data-baseweb="tag"] span, .stApp:has(.st-key-sire_banda) [data-baseweb="tag"] svg,
.stApp:has(.st-key-sire_banda) span[data-tag] span, .stApp:has(.st-key-sire_banda) span[data-tag] svg{ color:#FFFFFF !important; fill:#FFFFFF !important; }
.stApp:has(.st-key-sire_banda) [data-testid="stFileUploaderDropzone"]{ border:2px dashed #B9D4EC !important; border-radius:18px !important; background:#F4F8FC !important; padding:26px !important; }
/* tipo de reporte como tarjetas */
.st-key-tipos_cards [data-testid="stElementContainer"]{ width:100% !important; }
.st-key-tipos_cards [data-testid="stButtonGroup"]{ display:block !important; width:100%; }
.st-key-tipos_cards [role="toolbar"]{ display:grid !important; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:14px; margin-top:8px; width:100% !important; max-width:100% !important; flex-wrap:nowrap !important; }
.st-key-tipos_cards button[data-variant]{
  min-height:92px; height:auto; border-radius:16px !important; border:2px solid #D9E7F3 !important; background:#FFFFFF !important; color:#1D3F76 !important;
  padding:16px 18px !important; font-weight:800 !important; font-size:16px !important; width:100%; justify-content:flex-start !important; align-items:flex-start !important;
}
.st-key-tipos_cards button[data-variant] > div, .st-key-tipos_cards button[data-variant] span[data-has-shortcut]{ flex-direction:column; align-items:flex-start; text-align:left; gap:6px; }
.st-key-tipos_cards button[data-variant]:hover{ border-color:#0077C8 !important; }
.st-key-tipos_cards button[aria-pressed="true"]{ background:#E3F0FA !important; border-color:#0077C8 !important; box-shadow:0 8px 20px rgba(0,119,200,.15); }
.st-key-tipos_cards button[data-variant] span[data-testid="stIconMaterial"]{ font-size:30px !important; color:#0077C8 !important; }
/* botón de envío */
.st-key-sire_enviar [data-testid="stFormSubmitButton"] button{ border-radius:14px !important; min-height:56px; font-size:17px !important; font-weight:800 !important; }
.st-key-sire_enviar [data-testid="stFormSubmitButton"] button[kind="primary"]:not(:disabled){ background:linear-gradient(135deg,#005C9C,#0077C8) !important; box-shadow:0 12px 28px rgba(0,119,200,.3) !important; }
.st-key-sire_enviar [data-testid="stFormSubmitButton"] button:disabled{ background:#D5DEE8 !important; color:#7C8B99 !important; border-color:#D5DEE8 !important; }
/* resumen del envío (anillo + lista de pendientes) */
.sire-resumen{ background:#FFFFFF; border:1px solid #E1EAF3; border-radius:24px; box-shadow:0 16px 40px rgba(10,60,120,.12); padding:24px 26px; margin-bottom:16px; }
.sire-resumen-top{ display:flex; align-items:center; gap:18px; }
.sire-resumen-top h3{ margin:0 !important; font-size:20px !important; color:#1D3F76 !important; line-height:1.2; }
.sire-resumen-top small{ font-size:14px; color:#566573; }
.sire-ring{ position:relative; width:92px; height:92px; flex:none; }
.sire-ring > b{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:20px; color:#1D3F76; }
.sire-ck{ display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid #E8EDF6; }
.sire-ck:last-child{ border-bottom:0; }
.sire-ck-i{ width:24px; height:24px; border-radius:50%; flex:none; display:flex; align-items:center; justify-content:center; background:#E6F4EA; }
.sire-ck-i.falta{ background:#E6F4FB; border:2px dashed #41B6E6; box-sizing:border-box; }
.sire-ck-i.error{ background:#FDE8E8; border:2px solid #D9534F; box-sizing:border-box; }
.sire-ck small{ display:block; font-size:13px; color:#566573; }
.sire-ck b{ display:block; font-size:15px; color:#14202B; word-break:break-word; }
.sire-ck b.falta{ color:#005C9C; } .sire-ck b.error{ color:#9E2B2B; }
/* indicadores con ícono grande */
.stApp:has(.st-key-sire_banda) .sire-kpi{ display:grid; grid-template-columns:60px minmax(0,1fr); column-gap:18px; align-items:center; min-height:0; padding:22px 24px; }
.stApp:has(.st-key-sire_banda) .sire-kpi:not(:has(.sire-kpi-ico)){ display:block; }
.stApp:has(.st-key-sire_banda) .sire-kpi::before{ display:none; }
.stApp:has(.st-key-sire_banda) .sire-kpi-top{ display:contents; }
.stApp:has(.st-key-sire_banda) .sire-kpi-top > span:first-child{ grid-column:2; grid-row:1; }
.stApp:has(.st-key-sire_banda) .sire-kpi-ico{ grid-column:1; grid-row:1 / span 3; width:60px; height:60px; border-radius:18px; }
.stApp:has(.st-key-sire_banda) .sire-kpi-ico svg{ width:30px; height:30px; }
.stApp:has(.st-key-sire_banda) .sire-kpi-val{ grid-column:2; grid-row:2; margin-top:2px; }
.stApp:has(.st-key-sire_banda) .sire-kpi-sub{ grid-column:2; grid-row:3; }
/* gráfico con meta y leyenda */
.sire-chart{ position:relative; }
/* v8.1 · enlace «Cambiar contraseña» de la banda y bloque propio debajo de las tarjetas */
html{ scroll-behavior:smooth; }
.sire-ancla{ height:0; scroll-margin-top:24px; }
.st-key-sire_banda [class*="st-key-sire_hero_pag"] .stButton > button p{ font-weight:700 !important; }
.st-key-sire_banda [class*="st-key-sire_hero_pag"] [data-testid="stHorizontalBlock"]{ margin-top:12px; }
.st-key-sire_banda .sire-btn-clave, .sire-btn-clave{
  display:flex; align-items:center; justify-content:center; gap:10px; min-height:48px; padding:0 14px; border-radius:14px; font-weight:700; font-size:15px;
  text-decoration:none !important; color:#FFFFFF !important; border:1px solid rgba(255,255,255,.6);
  background:linear-gradient(135deg, rgba(255,255,255,.30), rgba(255,255,255,.10)); box-shadow:inset 0 1px 0 rgba(255,255,255,.55); backdrop-filter:blur(10px); white-space:nowrap;
}
.sire-btn-clave:hover{ background:linear-gradient(135deg, rgba(255,255,255,.42), rgba(255,255,255,.18)); color:#FFFFFF !important; }
.st-key-sire_clave{ position:relative; z-index:1; background:#FFFFFF; border:1px solid #E1EAF3; border-left:6px solid #0077C8; border-radius:24px;
  box-shadow:0 16px 40px rgba(10,60,120,.12); padding:4px 24px 8px; margin:34px 0 6px; }
.st-key-sire_clave [data-testid="stExpander"], .st-key-sire_clave details{ border:0 !important; background:transparent !important; box-shadow:none !important; }
.st-key-sire_clave summary{ display:flex; align-items:center; gap:0; padding:16px 0 !important; font-weight:800 !important; font-size:20px !important; color:#1D3F76 !important; }
.st-key-sire_clave summary::before{ content:""; flex:none; width:52px; height:52px; margin-right:16px; border-radius:16px;
  background:#E3F0FA url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28' viewBox='0 0 24 24' fill='none' stroke='%230077C8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='8' cy='15' r='4'/><path d='M11 12l9-9M16 7l3 3M14 9l2 2'/></svg>") center/28px no-repeat; }
.st-key-sire_clave summary p{ font-size:20px !important; font-weight:800 !important; color:#1D3F76 !important; }
/* v8.1 · aviso de posible duplicado */
.sire-dup-prev{ margin:14px 0 6px; border:1px solid #D9E7F3; border-radius:16px; overflow:hidden; background:#FFFFFF; }
.sire-dup-t{ padding:11px 16px; background:#1D3F76; color:#FFFFFF; font-weight:800; font-size:13px; letter-spacing:0; text-transform:none; }
.sire-dup-sc{ overflow-x:auto; }
.sire-dup-prev table{ width:100%; border-collapse:collapse; font-size:14px; }
.sire-dup-prev th{ text-align:left; padding:9px 16px; font-size:12px; letter-spacing:0; text-transform:none; color:#566573; background:#F4F8FC; }
.sire-dup-prev td{ padding:10px 16px; border-top:1px solid #E3E9F4; color:#1F2D3A; }
.sire-dup-est{ display:inline-block; padding:3px 10px; border-radius:999px; background:#E6F4EA; color:#1E6B3A; font-weight:700; font-size:12.5px; }
[class*="st-key-dup_op_"]{ border:1.5px solid #D9E7F3; border-radius:18px; padding:16px 16px 14px; background:#FFFFFF; height:100%; }
.st-key-dup_op_1{ box-shadow:inset 0 5px 0 #E8A14F; } .st-key-dup_op_2{ box-shadow:inset 0 5px 0 #0077C8; } .st-key-dup_op_3{ box-shadow:inset 0 5px 0 #8A99A8; }
.sire-dup-op-h{ display:flex; align-items:center; gap:10px; margin:6px 0 8px; color:#1D3F76; font-size:15.5px; }
.sire-dup-op-h span{ width:34px; height:34px; border-radius:11px; display:inline-flex; align-items:center; justify-content:center; flex:none; }
.sire-dup-naranja span{ background:#FFF3E3; color:#96500A; } .sire-dup-azul span{ background:#E3F0FA; color:#0077C8; } .sire-dup-gris span{ background:#EEF2F6; color:#566573; }
.sire-dup-op-p{ font-size:13.5px; line-height:1.5; color:#3F4E5B; margin-bottom:12px; min-height:124px; }
.sire-card-b .sire-nota{ margin:14px 0 4px !important; font-size:13.5px !important; line-height:1.45 !important; color:#5B6B7C !important; }
.sire-meta{ position:absolute; left:0; right:0; border-top:2px dashed #1E6B3A; opacity:.55; pointer-events:none; }
.sire-meta span{ position:absolute; right:0; top:-22px; font-size:12px; font-weight:700; color:#1E6B3A; background:#FFFFFF; padding:0 6px; }
.sire-leyenda{ display:flex; flex-wrap:wrap; gap:8px 18px; margin:-8px 0 14px; font-size:13.5px; color:#3F4E5B; }
.sire-leyenda span{ display:inline-flex; align-items:center; gap:8px; }
.sire-leyenda i{ width:12px; height:12px; border-radius:4px; display:inline-block; }
.sire-minis{ display:flex; flex-wrap:wrap; gap:14px; margin:6px 0 8px; }
.sire-mini{ flex:1 1 200px; border-radius:16px; padding:14px 18px; background:#F4F8FC; }
.sire-mini small{ display:block; font-size:12.5px; font-weight:800; letter-spacing:0; text-transform:none; color:#566573; }
.sire-mini b{ display:block; font-size:26px; line-height:1.2; color:#1D3F76; }
.sire-mini.ok{ background:#F1FAF4; } .sire-mini.ok b{ color:#1E6B3A; }
.sire-mini.bad{ background:#FDF1F0; } .sire-mini.bad b{ color:#B3261E; }
@media (max-width: 900px){ .st-key-sire_banda{ padding-bottom:96px !important; } .stApp .sire-bp-h1{ font-size:36px !important; } }
</style>
"""


# ------------------------------------------------------------
# SIREA 3.5 · trama de figuritas de salud para los fondos
# ------------------------------------------------------------
# Íconos de trazo (24×24) dibujados aquí mismo: nada se descarga de internet.
_ICONOS_SALUD = {
    "cruz": '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>',
    "corazon": '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>'
               '<path d="M4 12h4l2-3 3 6 2-3h5"/>',
    "estetoscopio": '<path d="M5 3v6a5 5 0 0 0 10 0V3"/><path d="M10 14v2a5 5 0 0 0 10 0v-3"/><circle cx="20" cy="11" r="2"/>',
    "gota": '<path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z"/>',
    "termometro": '<path d="M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0z"/><path d="M12 9v7"/>',
    "lupa": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
    "curva": '<path d="M3 20h18"/><path d="M4 18c3 0 4-12 8-12s5 12 8 12"/>',
    "microbio": '<circle cx="12" cy="12" r="4"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4M5 5l3 3M16 16l3 3M19 5l-3 3M8 16l-3 3"/>',
    "vacuna": '<path d="M18 2l4 4M17 3l4 4M19 5l-9 9M14 6l4 4M8 12l4 4M10 14l-6 6M3 21l1-1"/>',
    "pastilla": '<rect x="2.5" y="8.5" width="19" height="7" rx="3.5" transform="rotate(-35 12 12)"/><path d="M9 7.5l6 9"/>',
    "reporte": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M8 10h8M8 14h8M8 18h5"/>',
}
# (ícono, x, y, tamaño, giro) dentro de un mosaico de 360×360 que se repite
_MOSAICO = (("cruz", 18, 22, 30, 0), ("corazon", 120, 8, 34, -10), ("estetoscopio", 238, 30, 36, 12),
            ("gota", 318, 96, 26, 0), ("curva", 40, 112, 40, 0), ("termometro", 168, 104, 32, 18),
            ("microbio", 262, 168, 34, 0), ("lupa", 92, 198, 32, -8), ("vacuna", 10, 272, 34, 20),
            ("pastilla", 186, 230, 34, 0), ("reporte", 300, 280, 32, 6), ("cruz", 210, 318, 22, 0),
            ("corazon", 128, 316, 24, 8))


def patron_salud(color: str = "#FFFFFF", opacidad: float = 0.14, trazo: float = 1.6) -> str:
    """Trama de figuritas de salud como url(data:image/svg+xml,…) lista para `background-image`."""
    from urllib.parse import quote
    partes = []
    for nombre, x, y, tam, giro in _MOSAICO:
        esc_ = tam / 24
        partes.append(f'<g transform="translate({x} {y}) rotate({giro} {tam / 2} {tam / 2}) scale({esc_:.3f})">'
                      f'{_ICONOS_SALUD[nombre]}</g>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360" fill="none" '
           f'stroke="{color}" stroke-opacity="{opacidad}" stroke-width="{trazo}" stroke-linecap="round" '
           f'stroke-linejoin="round">{"".join(partes)}</svg>')
    return 'url("data:image/svg+xml,' + quote(svg, safe="") + '")'


# ============================================================
# SIREA 3.5 · CAPA DE IDENTIDAD (va después de todo lo demás)
# ============================================================
# Lo que hace a SIREA distinguible de SIRE: azul EsSalud + celeste + verde + aguamarina + lila (quipu), Bricolage Grotesque
# en los títulos, barra lateral oscura, etiquetas en minúscula inicial, menos sombras y bordes finos,
# un radio distinto según la jerarquía (paneles 14 · controles 8 · chips redondos). Paleta: docs/DISENO_SIREA.md.

_CSS_SIREA = """
<style>
:root{
  --navy:#1D3F76; --azul:#0077C8; --azul-h:#005C9C; --ocre:#41B6E6; --ocre-s:#EAF3FB;
  --ink:#0F1A33; --mute:#4B5875; --line:#D9E7F3; --bg:#F4F8FC;
  --r:8px; --r-lg:14px; --sombra:none;
  --titulo:'Bricolage Grotesque', 'IBM Plex Sans', system-ui, sans-serif;
}
.stApp{ background:#F4F8FC __PATRON_FONDO__ repeat 0 0 / 360px 360px; }
[data-testid="stMain"] .block-container{ font-variant-numeric:tabular-nums; }

/* títulos con carácter */
.stApp h1, .stApp h2, .stApp h3, .sire-h2, .sire-panel-h h2, .sire-form-t, .sire-op h3, .sire-card-h,
.sire-kpi-val, .sire-bp-h1, .sire-hero-h1, .sirea-hero h1, .sirea-quien h2{
  font-family:var(--titulo) !important; letter-spacing:-.012em;
}
.stApp .sire-admin-top h1{ font-size:34px !important; font-weight:700 !important; color:#1D3F76 !important; }
.sire-migas{ color:#4B5875 !important; font-weight:500 !important; }
.sire-kpi-val{ font-weight:700 !important; font-variant-numeric:tabular-nums; }

/* encabezado del panel: blanco con la cuerda de semanas debajo */
.sire-admin-top::before{ background:#FFFFFF !important; border-bottom:1px solid #D9E7F3 !important; }
.sirea-quipu-admin{ margin:16px 0 -8px; max-width:none; width:100%; }

/* barra lateral clara (como la original): celeste muy suave, texto azul marino, ítem activo en blanco */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div, [data-testid="stSidebarContent"]{
  background:#EAF4FC !important; border-right:1px solid #D4E9FA !important;
}
.stApp [data-testid="stSidebar"] div.stButton > button, .stApp [data-testid="stSidebar"] div.stButton > button[kind="secondary"]{
  color:#1D3F76 !important; font-weight:500 !important; background:transparent !important; border:0 !important;
}
.stApp [data-testid="stSidebar"] div.stButton > button *{ color:inherit !important; }
.stApp [data-testid="stSidebar"] div.stButton > button:hover{ background:#D4E9FA !important; color:#0B2E5C !important; }
.stApp [data-testid="stSidebar"] div.stButton > button[kind="primary"]{
  background:#FFFFFF !important; color:#0B2E5C !important; font-weight:700 !important; box-shadow:0 1px 3px rgba(10,60,120,.14) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]::before{ background:#0077C8 !important; width:4px !important; }
[data-testid="stSidebar"] .stButton > button:focus-visible{ outline:2px solid #0077C8 !important; outline-offset:2px; }
.sire-side-brand{ border-bottom:1px solid #D4E9FA !important; }
.sire-side-brand b{ color:#1D3F76 !important; font-family:var(--titulo); letter-spacing:.01em !important; }
.sire-side-brand b .sire-a{ color:#0077C8; }
.sire-side-brand small{ color:#3D5A80 !important; }
.sire-side-grupo{ color:#3D5A80 !important; font-size:12.5px !important; font-weight:700 !important; padding-top:18px !important; }
.sire-side-user{ border-top:1px solid #D4E9FA !important; }
.sire-side-user b{ color:#1D3F76 !important; }
.sire-avatar{ background:#0077C8 !important; color:#FFFFFF !important; font-weight:700 !important; }
.sire-side-user .sire-chip{ background:#FFFFFF !important; color:#1D3F76 !important; border:1px solid #B9D4EC !important; }
.stApp [data-testid="stSidebar"] [class*="st-key-nav_salir"] div.stButton > button{
  background:#FFFFFF !important; border:1px solid #B9D4EC !important; color:#1D3F76 !important;
}
.stApp [data-testid="stSidebar"] [class*="st-key-nav_salir"] div.stButton > button:hover{ background:#D4E9FA !important; }

/* paneles y tarjetas: borde fino, sin sombra; la jerarquía la da el radio y el espacio */
[class*="st-key-panel"], [class*="st-key-sec_"], [data-testid="stExpander"], .sire-card, .sire-panel{
  box-shadow:none !important; border-color:#D9E7F3 !important; border-radius:14px !important;
}
.sire-kpi{ box-shadow:none !important; border-radius:12px !important; border:1px solid #D9E7F3 !important; }
.sire-kpi::before{ width:3px !important; }

/* botones */
.stApp div.stButton > button, .stApp div.stDownloadButton > button, .stApp div.stFormSubmitButton > button{
  border-radius:8px !important; font-weight:600 !important;
}
.stApp div.stButton > button[kind="primary"], .stApp div.stFormSubmitButton > button[kind="primary"]{
  background:#0077C8 !important; border-color:#0077C8 !important; box-shadow:none !important;
}
.stApp div.stButton > button[kind="primary"]:hover, .stApp div.stFormSubmitButton > button[kind="primary"]:hover{
  background:#005C9C !important; border-color:#005C9C !important;
}
.stApp div.stButton > button[kind="secondary"]{ border-color:#B9D4EC !important; color:#1D3F76 !important; }
.stApp div.stButton > button:focus-visible, .stApp a:focus-visible, .stApp input:focus-visible{
  outline:3px solid #0077C8 !important; outline-offset:2px !important;
}
.stApp .st-key-sire_banda div.stButton > button:focus-visible, .stApp .st-key-sire_banda a:focus-visible{ outline-color:#FFFFFF !important; }

/* tablas: cabecera sobria y cifras alineadas */
.stApp table.sire-tabla th{ background:#EEF5FB !important; color:#1D3F76 !important; font-weight:600 !important;
  font-size:13px !important; letter-spacing:0 !important; border-bottom:1px solid #C9D5EE !important; }
.stApp table.sire-tabla td{ font-variant-numeric:tabular-nums; }
.stApp table.sire-tabla tbody tr:hover td{ background:#F1F7FC !important; }

/* Salud del sistema */
.sirea-salud{ display:flex; flex-direction:column; }
.sirea-salud-fila{ display:grid; grid-template-columns:120px minmax(0,1fr); gap:14px; padding:12px 2px; border-bottom:1px solid #E3E9F4; }
.sirea-salud-fila:last-child{ border-bottom:0; }
.sirea-salud-tit{ font-weight:600; color:#0F1A33; }
.sirea-salud-det{ font-size:13.5px; color:#4B5875; margin-top:2px; overflow-wrap:anywhere; }
.sirea-salud-bad{ background:linear-gradient(90deg, rgba(158,43,43,.06), transparent 40%); }
.sirea-salud-warn{ background:linear-gradient(90deg, rgba(255,184,28,.07), transparent 40%); }

/* el ítem activo de la barra lateral no toma el color de los botones primarios al pasar el mouse */
.stApp [data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover{ background:#FFFFFF !important; border-color:transparent !important; }
.stApp [data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover{ background:#D4E9FA !important; }

.stApp [data-testid="stBaseButton-pillsActive"], .stApp [data-testid="stBaseButton-segmented_controlActive"],
.stApp [data-testid="stBaseButton-pillsActive"] *, .stApp [data-testid="stBaseButton-segmented_controlActive"] *{ color:#004F85 !important; }
.stApp [data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"],
.stApp [data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"] *{ color:#004F85 !important; }

@media (prefers-reduced-motion: reduce){
  *, *::before, *::after{ animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
</style>
"""

# En las pantallas públicas: banda petróleo sólida (sin el degradado ni el efecto cristal de SIRE),
# cuerda de semanas al pie y el botón del panel en ocre.
_CSS_SIREA_BANDA = """
<style>
.st-key-sire_banda{
  background:__PATRON_BANDA__ repeat 0 0 / 360px 360px,
             radial-gradient(700px 360px at 100% -20%, rgba(65,182,230,.30) 0%, rgba(65,182,230,0) 60%),
             radial-gradient(800px 460px at 0% 110%, rgba(30,158,99,.22) 0%, rgba(30,158,99,0) 60%),
             linear-gradient(135deg, #0071BE 0%, #0067B0 55%, #00579A 100%) !important;
}
.st-key-sire_banda:has(.sire-tono-rojo){ background:linear-gradient(135deg, #B42323 0%, #D93636 100%) !important; }
.st-key-sire_banda:has(.sire-tono-ambar){ background:linear-gradient(135deg, #B86E00 0%, #E08A00 100%) !important; }
.st-key-sire_banda:has(.sire-tono-naranja){ background:linear-gradient(135deg, #C2530A 0%, #EA6A12 100%) !important; }
.st-key-sire_banda::before{ opacity:.045 !important; }
.st-key-sire_banda::after{ display:none !important; }
.st-key-sire_banda .sire-brand svg rect:first-child{ fill:#FFFFFF !important; }
.st-key-sire_banda .sire-brand svg rect:nth-child(n+2){ fill:none !important; }
.st-key-sire_banda .sire-brand svg .q-c{ stroke:#1D3F76 !important; }
.st-key-sire_banda .sire-brand svg .q-n{ fill:#1D3F76 !important; }
.st-key-sire_banda .sire-brand-txt b .sire-a{ color:#9FD6F0 !important; background:none; padding:0; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button{
  background:transparent !important; border:1px solid rgba(255,255,255,.30) !important; box-shadow:none !important; backdrop-filter:none !important;
  font-weight:500 !important;
}
.st-key-sire_banda .st-key-sire_hdr .stButton > button:hover{ background:rgba(255,255,255,.08) !important; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button[kind="primary"]{ background:#FFFFFF !important; border-color:#FFFFFF !important; }
.st-key-sire_banda .st-key-sire_hdr .stButton > button[kind="primary"] *{ color:#1D3F76 !important; }
.st-key-sire_banda .st-key-sire_hdr [class*="st-key-nav_pub_admin"] .stButton > button{
  background:transparent !important; border:1px solid rgba(255,255,255,.38) !important; box-shadow:none !important;
}
.st-key-sire_banda .st-key-sire_hdr [class*="st-key-nav_pub_admin"] .stButton > button *{ color:#FFFFFF !important; font-weight:600 !important; }
.sire-cristal, .st-key-sire_banda .sire-acuse-cod{
  background:rgba(255,255,255,.06) !important; border:1px solid rgba(255,255,255,.16) !important;
  box-shadow:none !important; backdrop-filter:none !important; border-radius:14px !important;
}
.st-key-sire_banda .sire-brand-txt small, .st-key-sire_banda .sire-brand-txt span, .stApp .st-key-sire_banda .sire-bp-p,
.st-key-sire_banda .sire-hero-p, .st-key-sire_banda .sire-cristal span, .st-key-sire_banda .sire-cristal small,
.st-key-sire_banda .sire-cristal div{ color:#FFFFFF !important; }
.st-key-sire_banda .sire-bp-tile em{ color:#FFFFFF !important; }
.sire-cristal, .st-key-sire_banda .sire-acuse-cod{ background:rgba(0,40,90,.28) !important; }
.st-key-sire_banda .sire-hero-chip{ background:rgba(0,40,90,.35) !important; border:1px solid rgba(255,255,255,.22) !important; backdrop-filter:none !important; }
.st-key-sire_banda [class*="st-key-sire_hero_pag"] .stButton > button, .st-key-sire_banda .sire-btn-clave{
  background:transparent !important; border:1px solid rgba(255,255,255,.32) !important; box-shadow:none !important; backdrop-filter:none !important;
  border-radius:10px !important;
}
.st-key-sire_banda .sire-bp-h1{ font-family:var(--titulo) !important; font-weight:700 !important; }
.stApp .st-key-sire_banda div.stButton > button[kind="primary"]{ background:#FFFFFF !important; border-color:#FFFFFF !important; }
.stApp .st-key-sire_banda div.stButton > button[kind="primary"] *{ color:#1D3F76 !important; }
.stApp .st-key-sire_banda div.stButton > button[kind="primary"]:hover{ background:#E3F0FA !important; }
.stApp .st-key-sire_banda div.stButton > button[kind="secondary"]{
  background:transparent !important; border:1px solid rgba(255,255,255,.34) !important; color:#FFFFFF !important;
  box-shadow:none !important; backdrop-filter:none !important;
}
.stApp .st-key-sire_banda div.stButton > button[kind="secondary"] *{ color:#FFFFFF !important; }
.stApp .st-key-sire_banda div.stButton > button[kind="secondary"]:hover{ background:rgba(255,255,255,.08) !important; }
.stApp .st-key-sire_banda [class*="st-key-nav_pub_admin"] div.stButton > button{ background:transparent !important; border-color:rgba(255,255,255,.38) !important; }
.stApp .st-key-sire_banda [class*="st-key-nav_pub_admin"] div.stButton > button *{ color:#FFFFFF !important; font-weight:600 !important; }
.stApp .st-key-sire_banda [class*="st-key-nav_pub_admin"] div.stButton > button:hover{ background:rgba(255,255,255,.12) !important; border-color:#FFFFFF !important; }
.sirea-quipu-banda{ margin:28px 0 0; opacity:.98; }
.stApp:has(.st-key-sire_banda) [class*="st-key-sec_"], .stApp:has(.st-key-sire_banda) .sire-card,
.stApp:has(.st-key-sire_banda) .sire-panel, .stApp:has(.st-key-sire_banda) .sire-kpi, .sire-resumen,
.stApp:has(.st-key-sire_banda) [class*="st-key-red_panel"], .st-key-sire_clave{
  box-shadow:0 1px 0 rgba(10,60,120,.04) !important; border-radius:14px !important; border-color:#D9E7F3 !important;
}
.stApp:has(.st-key-sire_banda) [class*="st-key-red_panel"]{ box-shadow:inset 0 3px 0 #0077C8 !important; }
.stApp:has(.st-key-sire_banda) .st-key-red_panel_quien{ box-shadow:inset 0 3px 0 #1E6B3A !important; }
.stApp:has(.st-key-sire_banda) .st-key-red_panel_obs{ box-shadow:inset 0 3px 0 #E08A1E !important; }
.stApp:has(.st-key-sire_banda) table.sire-tabla th{ background:#1D3F76 !important; color:#FFFFFF !important; }
.st-key-sire_enviar [data-testid="stFormSubmitButton"] button[kind="primary"]:not(:disabled){
  background:#0077C8 !important; box-shadow:none !important;
}
.st-key-tipos_cards button[aria-pressed="true"]{ background:#E3F0FA !important; border-color:#0077C8 !important; box-shadow:none !important; }
</style>
"""

_CSS_SIREA = _CSS_SIREA.replace("__PATRON_FONDO__", patron_salud("#0077C8", 0.07, 1.4))
_CSS_SIREA_BANDA = _CSS_SIREA_BANDA.replace("__PATRON_BANDA__", patron_salud("#FFFFFF", 0.16, 1.5))

# ============================================================
# SIREA 3.5 · ESTILO CORPORATIVO (capa final, va después de todo lo demás)
# Azul EsSalud y blanco; el color va en los bordes (barra superior de las tarjetas), no en rellenos.
# Sin marca de agua ni brillo diagonal en la banda. Figuras de salud también sobre el fondo claro.
# ============================================================
_CSS_CORP = """
<style>
/* fondo claro con figuras de salud (la regla base pintaba el fondo encima y las tapaba) */
html body .stApp{ background:#F5F8FB __PATRON_CLARO__ repeat 0 0 / 360px 360px !important; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"], [data-testid="stBottomBlockContainer"]{ background:transparent !important; }

/* banda: azul EsSalud parejo, sin sello de fondo ni reflejo */
.stApp .st-key-sire_banda:not(:has(.sire-tono-rojo, .sire-tono-ambar, .sire-tono-naranja)){
  background:__PATRON_BANDA2__ repeat 0 0 / 360px 360px, linear-gradient(135deg, #0071BE 0%, #0067B0 55%, #00579A 100%) !important;
}
.stApp .st-key-sire_banda::before, .stApp .st-key-sire_banda::after, .sire-marca-agua{ display:none !important; }

/* marca: la «A» en azul, sin recuadro de color */
.stApp .sire-brand-txt b .sire-a, .stApp .sire-side-brand b .sire-a{ color:#0077C8 !important; background:none !important; padding:0 !important; border-radius:0 !important; }
.stApp .st-key-sire_banda .sire-brand-txt b .sire-a{ color:#9FD6F0 !important; }
.sire-a-foot{ color:#9FD6F0 !important; }

/* menú superior sobre fondo blanco (pantallas sin banda) */
.stApp .st-key-sire_hdr div.stButton > button{
  min-height:44px !important; border-radius:10px !important; background:#FFFFFF !important; border:1px solid #D6E2EE !important;
  box-shadow:none !important; padding:0 14px !important;
}
.stApp .st-key-sire_hdr div.stButton > button *{ color:#1D3F76 !important; font-weight:600 !important; }
.stApp .st-key-sire_hdr div.stButton > button:hover{ border-color:#0077C8 !important; }
.stApp .st-key-sire_hdr div.stButton > button[kind="primary"]{ background:#0077C8 !important; border-color:#0077C8 !important; }
.stApp .st-key-sire_hdr div.stButton > button[kind="primary"] *{ color:#FFFFFF !important; font-weight:700 !important; }

/* menú superior sobre la banda: todos iguales; el de la página actual, blanco */
.stApp .st-key-sire_banda .st-key-sire_hdr div.stButton > button,
.stApp .st-key-sire_banda [class*="st-key-nav_pub_admin"] div.stButton > button:not([kind="primary"]){
  background:transparent !important; border:1px solid rgba(255,255,255,.38) !important; box-shadow:none !important;
}
.stApp .st-key-sire_banda .st-key-sire_hdr div.stButton > button *,
.stApp .st-key-sire_banda [class*="st-key-nav_pub_admin"] div.stButton > button:not([kind="primary"]) *{ color:#FFFFFF !important; font-weight:600 !important; }
.stApp .st-key-sire_banda .st-key-sire_hdr div.stButton > button:hover,
.stApp .st-key-sire_banda [class*="st-key-nav_pub_admin"] div.stButton > button:not([kind="primary"]):hover{ background:rgba(255,255,255,.12) !important; border-color:#FFFFFF !important; }
.stApp .st-key-sire_banda .st-key-sire_hdr div.stButton > button[kind="primary"]{ background:#FFFFFF !important; border-color:#FFFFFF !important; }
.stApp .st-key-sire_banda .st-key-sire_hdr div.stButton > button[kind="primary"] *{ color:#004F85 !important; font-weight:700 !important; }

/* textos de acento sobre la banda: blancos */
.stApp .st-key-sire_banda .sire-bp-tile em{ color:#FFFFFF !important; }
.stApp .st-key-sire_banda .sire-bp-3 b{ color:#FFFFFF !important; }

/* tarjetas: blancas, borde fino y barra superior azul */
.sire-tarjeta2, .sire-resumen, .sire-panel, .sire-card, .stApp [class*="st-key-sec_"], .st-key-sire_clave,
.stApp [class*="st-key-red_panel"]{ border-top:4px solid #0077C8 !important; }
.sire-tarjeta2, .sire-resumen, .stApp [class*="st-key-sec_"]{ border-radius:14px !important; box-shadow:0 8px 24px rgba(0,50,100,.08) !important; }

/* franja final: tarjetas blancas con borde azul a la izquierda */
.sire-franja span{ background:#FFFFFF !important; color:#1D3F76 !important; border:1px solid #D6E2EE; border-left:4px solid #0077C8; justify-content:flex-start !important; }
.sire-franja span svg{ stroke:#0077C8 !important; }

/* foco de teclado */
.stApp div.stButton > button:focus-visible, .stApp a:focus-visible, .stApp input:focus-visible{ outline:3px solid #0077C8 !important; outline-offset:2px !important; }
.stApp .st-key-sire_banda div.stButton > button:focus-visible, .stApp .st-key-sire_banda a:focus-visible{ outline-color:#FFFFFF !important; }

/* asistente Quipu: azul marca */
.st-key-quipu_fab div.stButton button{ background:#1D3F76 !important; }
.st-key-quipu_fab div.stButton button:hover{ background:#0B2E5C !important; }

/* aviso de conexión */
.sire-sin-red{ width:100vw; margin:0 0 0 calc(50% - 50vw); box-sizing:border-box; padding:12px clamp(20px, 4vw, 72px);
  background:#1D3F76; border-bottom:4px solid #E08A1E; color:#FFFFFF; font-size:15px; line-height:1.5; position:relative; z-index:5; }
.sire-sin-red-in{ display:flex; gap:12px; align-items:flex-start; }
.sire-sin-red-in > svg{ flex:none; margin-top:2px; }
.sire-sin-red b{ color:#FFFFFF; }
.sire-sin-red code{ background:rgba(255,255,255,.16); color:#FFFFFF; padding:1px 6px; border-radius:5px; font-size:13px; }
.sire-sin-red details{ margin-top:6px; font-size:13.5px; }
.sire-sin-red summary{ cursor:pointer; font-weight:700; color:#FFFFFF; text-decoration:underline; text-underline-offset:3px; }
.sire-sin-red details p{ margin:6px 0 0 !important; color:#FFFFFF !important; }
[data-testid="stElementContainer"]:has(.sire-sin-red){ margin-bottom:-1rem; }
.st-key-sire_aviso_red:not(:has(.sire-sin-red)){ display:none !important; }
.st-key-sire_aviso_red{ gap:0 !important; }
.stApp:has([data-testid="stSidebar"]) .sire-sin-red{ width:auto; margin:16px 0 4px; border-radius:12px; padding:14px 20px; }

/* ---------- accesos (red y panel) sobre la banda ---------- */
.stApp .st-key-sire_banda:has(.st-key-sire_login){ margin-bottom:0 !important; padding-bottom:0 !important; }
.st-key-sire_login{ padding:28px 0 72px !important; }
.sire-login-txt .sire-bp-h1{ margin-top:18px !important; }
.sire-login-pasos{ list-style:none; margin:26px 0 30px; padding:0; display:flex; flex-direction:column; gap:14px; }
.sire-login-pasos li{ display:flex; gap:14px; align-items:center; font-size:16.5px; line-height:1.5; color:#FFFFFF; }
.sire-login-pasos b{ flex:none; width:34px; height:34px; border-radius:50%; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.5);
  display:inline-flex; align-items:center; justify-content:center; font-weight:700; color:#FFFFFF; }
.st-key-sire_login .sire-vista{ max-width:540px; border-radius:14px; border-top:4px solid #41B6E6; box-shadow:0 18px 40px rgba(0,30,70,.28); }
.st-key-sire_login .sire-vista *{ color:inherit; }
.st-key-sire_login .sire-vista-h span, .st-key-sire_login .sire-vista-n b{ color:#1D3F76 !important; }
.st-key-sire_login .sire-vista-n span, .st-key-sire_login .sire-vista-h small{ color:#4B5875 !important; }
.st-key-sire_login [data-testid="stColumn"]:nth-child(2) > [data-testid="stVerticalBlock"]{ max-width:560px; margin-left:auto; width:100%; }
.st-key-sire_login [data-testid="stForm"]{
  background:#FFFFFF !important; border:1px solid #D6E2EE !important; border-top:4px solid #0077C8 !important; border-radius:16px !important;
  padding:34px 34px 28px !important; box-shadow:0 22px 48px rgba(0,30,70,.30) !important;
}
.st-key-sire_login [data-testid="stForm"] label, .st-key-sire_login [data-testid="stForm"] label *,
.st-key-sire_login [data-testid="stForm"] h2, .st-key-sire_login [data-testid="stForm"] p{ color:#1D3F76 !important; }
.st-key-sire_login [data-testid="stForm"] .sire-form-s, .st-key-sire_login [data-testid="stForm"] .sire-form-nota span{ color:#3D4F66 !important; }
.st-key-sire_login [data-testid="stForm"] input{ color:#13213A !important; background:#FFFFFF !important; }
.st-key-sire_login [data-testid="stFormSubmitButton"] button{ background:#0077C8 !important; border-color:#0077C8 !important; min-height:48px; }
.st-key-sire_login [data-testid="stFormSubmitButton"] button *{ color:#FFFFFF !important; font-weight:700 !important; }
.st-key-sire_login [data-testid="stFormSubmitButton"] button:hover{ background:#005C9C !important; }
.st-key-sire_login .sire-pie-form{ color:#FFFFFF !important; font-weight:600; margin:22px 0 6px; }
.st-key-sire_login [data-testid="stAlert"] *{ color:inherit !important; }
@media (max-width: 900px){ .st-key-sire_login [data-testid="stColumn"]:nth-child(2) > [data-testid="stVerticalBlock"]{ max-width:none; } }
.stApp .sire-login-pasos{ padding-left:0 !important; margin-left:0 !important; }
.stApp .sire-login-pasos li{ margin:0 !important; padding:0 !important; }
.stApp .sire-login-pasos li::marker{ content:""; }
/* enlaces bajo el formulario: botones con contorno blanco, uno junto al otro */
.st-key-sire_login [class*="st-key-link_"]{ display:inline-flex; width:auto !important; margin-right:10px; }
.stApp .st-key-sire_login [class*="st-key-link_"] .stButton > button{
  background:transparent !important; border:1px solid rgba(255,255,255,.55) !important; border-radius:10px !important;
  padding:8px 18px !important; min-height:42px !important; text-decoration:none !important; }
.stApp .st-key-sire_login [class*="st-key-link_"] .stButton > button *{ color:#FFFFFF !important; font-weight:600 !important; text-decoration:none !important; }
.stApp .st-key-sire_login [class*="st-key-link_"] .stButton > button:hover{ background:rgba(255,255,255,.12) !important; border-color:#FFFFFF !important; }
.st-key-sire_login .sire-pie-form{ border-top:1px solid rgba(255,255,255,.25); padding-top:18px; }
.stApp:has(.st-key-sire_login) div[data-testid="stElementContainer"]:has(.sire-foot){ margin-top:-1rem !important; }
</style>
"""
_CSS_CORP = (_CSS_CORP.replace("__PATRON_CLARO__", patron_salud("#0B5A9E", 0.075, 1.4))
             .replace("__PATRON_BANDA2__", patron_salud("#FFFFFF", 0.13, 1.5)))
_CSS_SIREA = _CSS_SIREA + _CSS_CORP
_CSS_SIREA_BANDA = _CSS_SIREA_BANDA + _CSS_CORP



def css_banda() -> str:
    """CSS de la banda azul (con el búho de la OIIS en la marca de agua)."""
    return _CSS_BANDA.replace("__MARCA__", logo_uri("oiis-blanco.svg")) + _CSS_SIREA_BANDA


@contextmanager
def banda_publica(activo: str, titulo: str, subtitulo: str = "", chip: str = "", chip_cerrada: bool = False,
                  derecha: str = "", nav: bool = True):
    """
    Banda azul de la pantalla: encabezado + cabecera (chip, título grande, subtítulo y, a la derecha, una
    ficha de cristal con datos). Se usa con `with`: lo que se dibuje dentro (botones) queda en la banda.
    El contenido que sigue sube un poco sobre el azul.
    """
    st.markdown(css_banda(), unsafe_allow_html=True)
    with st.container(key="sire_banda"):
        encabezado_publico(activo, nav=nav)
        with st.container(key="sire_hero_pag"):
            chip_html = (f'<span class="sire-hero-chip{" cerrada" if chip_cerrada else ""}"><i></i>{chip}</span>'
                         if chip else "")
            sub = f'<p class="sire-bp-p">{subtitulo}</p>' if subtitulo else ""
            mostrar(f'<div class="sire-bp"><div class="sire-bp-txt">{chip_html}'
                    f'<h1 class="sire-bp-h1">{titulo}</h1>{sub}</div>{derecha}</div>')
            yield


def aplicar_tema(admin: bool = False):
    """Inyecta el CSS del tema. Llamar una vez por ejecucion, al inicio de cada pantalla."""
    st.markdown(_CSS, unsafe_allow_html=True)
    if admin:
        st.markdown(_CSS_ADMIN, unsafe_allow_html=True)
        st.markdown(_CSS_RED, unsafe_allow_html=True)      # controles de las tablas navegables
    st.markdown(_CSS_SIREA, unsafe_allow_html=True)         # SIREA 3.5: identidad propia (siempre al final)


def aplicar_css_red():
    """Estilos de paneles y tablas de las pantallas de las redes (el panel de administración ya los trae)."""
    st.markdown(_CSS_RED, unsafe_allow_html=True)
    st.markdown(_CSS_SIREA, unsafe_allow_html=True)
