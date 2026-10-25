# src/email_plantillas.py
"""
Piezas HTML de los correos de SIREA (Sistema de Recepción de Reportes
Epidemiológicos) - EsSalud / OIIS.

Los clientes de correo (Outlook, Gmail, etc.) no entienden CSS moderno,
SVG ni fuentes externas, así que aquí todo es:
  * tablas con estilos en línea (no flex, no clases, no <style>),
  * imágenes PNG incrustadas por Content-ID (cid:...), que se adjuntan
    al enviar el correo (ver EmailSender._enviar_correo),
  * fuentes del sistema (Segoe UI / Arial).

El color de la cabecera indica el estado:
  azul   -> normal / preventivo      rojo  -> envío tardío
  ámbar  -> solicitud de corrección / observación
  naranja -> envío duplicado

Todas las funciones reciben HTML ya escapado en los parámetros que
terminan en `_html`; el texto plano se escapa con `esc()`.
"""

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

# ============================================================
# COLORES
# ============================================================

AZUL = "#0077C8"
ROJO = "#B42318"
AMBAR = "#A15C07"
NARANJA = "#C2570C"
NAVY = "#1D3F76"
TINTA = "#14202B"
MUTE = "#566573"
LINEA = "#D5DDE4"

# tono -> (texto, fondo, borde)
TONOS = {
    "ok":   ("#1E6B3A", "#E7F3EA", "#8CC4A0"),
    "warn": ("#7A5A00", "#FBF3E4", "#E3C98F"),
    "bad":  ("#B42318", "#FDECEA", "#E4A39D"),
    "info": (NAVY,      "#E8F1F8", "#A9D3EE"),
    "dup":  ("#8A3F05", "#FFF1E4", "#F0B27A"),
}

FUENTE = "'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Banda de cabecera -> (color, imagen de la marca)
BANDAS = {
    "azul": (AZUL, "sire-marca-azul"),
    "rojo": (ROJO, "sire-marca-rojo"),
    "ambar": (AMBAR, "sire-marca-ambar"),
    "naranja": (NARANJA, "sire-marca-naranja"),
}

# Content-ID -> archivo en assets/ (versiones PNG pequeñas hechas para correo)
IMAGENES = {
    "sire-essalud": "correo-essalud.png",
    "sire-essalud-blanco": "correo-essalud-blanco.png",
    "sire-oiis": "correo-oiis.png",
    "sire-marca-azul": "correo-marca-azul.png",
    "sire-marca-rojo": "correo-marca-rojo.png",
    "sire-marca-ambar": "correo-marca-ambar.png",
    "sire-marca-naranja": "correo-marca-naranja.png",
}
RUTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def imagenes_usadas(cuerpo_html: str) -> List[tuple]:
    """(content_id, ruta) de las imágenes cid: que aparecen en el HTML y existen en assets/."""
    usadas = []
    for cid in dict.fromkeys(re.findall(r'cid:([A-Za-z0-9_-]+)', cuerpo_html)):
        archivo = IMAGENES.get(cid)
        if archivo and (RUTA_ASSETS / archivo).is_file():
            usadas.append((cid, RUTA_ASSETS / archivo))
    return usadas


# ============================================================
# UTILIDADES
# ============================================================

def esc(valor) -> str:
    """Escapa un valor para insertarlo en HTML."""
    if valor is None:
        return ""
    return html.escape(str(valor), quote=True)


def fecha_legible(valor, con_segundos: bool = False) -> str:
    """
    Da formato dd/mm/aaaa hh:mm a una fecha (datetime o texto). Si no se
    puede interpretar, devuelve el texto tal cual.
    """
    if valor is None or valor == "":
        return "—"
    if isinstance(valor, datetime):
        return valor.strftime('%d/%m/%Y %H:%M:%S' if con_segundos else '%d/%m/%Y %H:%M')
    texto = str(valor).strip()
    for formato in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
                    '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            dt = datetime.strptime(texto, formato)
            if formato in ('%Y-%m-%d', '%d/%m/%Y'):
                dt = dt.replace(hour=23, minute=59)
            return dt.strftime('%d/%m/%Y %H:%M:%S' if con_segundos else '%d/%m/%Y %H:%M')
        except ValueError:
            continue
    return texto


# ============================================================
# BLOQUES
# ============================================================

def fila(etiqueta: str, valor_html: str, ultima: bool = False) -> str:
    borde = "" if ultima else f"border-bottom:1px solid #E4E9ED;"
    return (
        f'<tr><td width="150" valign="top" style="padding:12px 16px 12px 0;{borde}'
        f'font-size:14px;color:{MUTE};font-family:{FUENTE}">{etiqueta}</td>'
        f'<td valign="top" style="padding:12px 0;{borde}font-size:15px;font-weight:600;'
        f'color:{TINTA};font-family:{FUENTE}">{valor_html}</td></tr>'
    )


def tabla(filas_html: Iterable[str]) -> str:
    """Tabla de detalle. `filas_html`: resultado de fila(); la última no lleva línea inferior."""
    filas = list(filas_html)
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-top:1px solid {LINEA};margin-top:4px">{"".join(filas)}</table>'
    )


def tabla_desde_pares(pares: List[tuple]) -> str:
    """pares = [(etiqueta, valor_html)]; arma la tabla marcando la última fila."""
    return tabla(fila(a, b, ultima=(i == len(pares) - 1)) for i, (a, b) in enumerate(pares))


def chip(texto: str, tono: str) -> str:
    fg, bg, bd = TONOS[tono]
    return (
        f'<span style="display:inline-block;padding:2px 12px;border-radius:999px;background:{bg};'
        f'color:{fg};border:1px solid {bd};font-size:13px;font-weight:700;font-family:{FUENTE}">{texto}</span>'
    )


def caja_aviso(tono: str, titulo: str, texto_html: str = "") -> str:
    fg, bg, bd = TONOS[tono]
    cuerpo = (
        f'<div style="margin-top:2px;font-weight:400">{texto_html}</div>' if texto_html else ""
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-top:16px"><tr><td style="background:{bg};border:1px solid {bd};'
        f'border-left:4px solid {fg};border-radius:6px;padding:14px 16px;font-size:14px;'
        f'line-height:1.5;color:{TINTA};font-family:{FUENTE}">'
        f'<div style="font-weight:700;color:{fg}">{titulo}</div>{cuerpo}</td></tr></table>'
    )


def caja_codigo(codigo: str, etiqueta: str = "Código de seguimiento") -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:20px 0"><tr><td style="background:#F4F6F8;border:1px solid {LINEA};'
        f'border-radius:6px;padding:14px 18px;font-family:{FUENTE}">'
        f'<div style="font-size:12px;color:{MUTE};font-weight:600;letter-spacing:0.04em;'
        f'text-transform:uppercase">{etiqueta}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{NAVY};letter-spacing:0.02em">{codigo}</div>'
        f'</td></tr></table>'
    )


def chips_centros(items: List[str], tono: str = "info") -> str:
    fg, bg, bd = TONOS[tono]
    celdas = "".join(
        f'<span style="display:inline-block;margin:0 8px 8px 0;padding:4px 10px;border-radius:4px;'
        f'background:{bg};border:1px solid {bd};color:{fg};font-size:14px;font-weight:500;'
        f'font-family:{FUENTE}">{esc(i)}</span>'
        for i in items
    )
    return f'<div style="margin-top:8px">{celdas}</div>'


def bloque_titulo(texto: str) -> str:
    return (
        f'<div style="margin-top:20px;font-size:14px;font-weight:600;color:{TINTA};'
        f'font-family:{FUENTE}">{texto}</div>'
    )


def lista(items_html: List[str], ordenada: bool = False) -> str:
    etiqueta = "ol" if ordenada else "ul"
    lis = "".join(f'<li style="margin:0 0 6px">{i}</li>' for i in items_html)
    return (
        f'<{etiqueta} style="margin:8px 0 0;padding-left:22px;font-size:15px;color:#33424F;'
        f'font-family:{FUENTE}">{lis}</{etiqueta}>'
    )


def nota(texto_html: str) -> str:
    return (
        f'<p style="margin:24px 0 0;font-size:14px;color:#33424F;line-height:1.5;'
        f'font-family:{FUENTE}">{texto_html}</p>'
    )


def saludo(nombre_html: str, texto_html: str) -> str:
    """Saludo formal: «Estimado/a Nombre:» en su propia línea y luego el texto."""
    return (
        f'<span style="display:block;margin:0 0 10px;font-weight:600;color:{TINTA}">'
        f'Estimado/a {nombre_html}:</span>{texto_html}'
    )


def _correo_contacto() -> str:
    try:
        from src.config import Config
        return str(getattr(Config, "CONTACTO_EMAIL", "") or "").strip()
    except Exception:
        return ""


def cierre() -> str:
    """Despedida formal con la firma de la OIIS y el correo de consultas (si está configurado)."""
    contacto = _correo_contacto()
    consultas = (
        f'<div style="margin-top:10px;font-size:13px;color:{MUTE}">Para consultas, escriba a '
        f'<a href="mailto:{esc(contacto)}" style="color:{AZUL};text-decoration:underline">{esc(contacto)}</a>.</div>'
        if contacto else ""
    )
    return (
        f'<p style="margin:28px 0 0;font-size:15px;line-height:1.5;color:#33424F;font-family:{FUENTE}">'
        f'Atentamente,<br><strong style="color:{TINTA}">Oficina de Inteligencia e Información Sanitaria (OIIS)</strong><br>'
        f'EsSalud{consultas}</p>'
    )


def base_normativa(extra: str = "") -> str:
    return caja_aviso(
        "info", "Base normativa",
        "De conformidad con la <strong>Directiva N°17-GG-ESSALUD-2023</strong>, los reportes "
        "deben enviarse dentro del plazo establecido para cada semana epidemiológica." + extra
    )


# ============================================================
# ESTRUCTURA COMPLETA DEL CORREO
# ============================================================

def envolver(
    banda: str,
    eyebrow: str,
    titulo: str,
    intro_html: str,
    cuerpo_html: str,
    anio: Optional[int] = None,
) -> str:
    """
    Arma el correo completo: cabecera de color (azul/rojo/ámbar) con la
    marca SIREA, titular, contenido y pie con los logos de EsSalud y la OIIS.
    """
    color, marca = BANDAS.get(banda, BANDAS["azul"])
    anio = anio or datetime.now().year
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)}</title></head>
<body style="margin:0;padding:0;background:#E9EDF1">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#E9EDF1"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:640px;background:#FFFFFF;border:1px solid {LINEA};border-radius:8px">
<tr><td style="background:{color};padding:22px 32px;border-radius:8px 8px 0 0">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td valign="middle" width="1"><img src="cid:{marca}" width="40" height="40" alt="SIREA" style="display:block;border:0"></td>
<td valign="middle" style="padding-left:12px;font-family:{FUENTE}">
<div style="font-weight:700;font-size:20px;letter-spacing:0.04em;color:#FFFFFF;line-height:1.15">SIREA</div>
<div style="font-size:12px;color:#FFFFFF;line-height:1.3">Sistema de Recepción de Reportes Epidemiológicos con Agentes</div>
</td>
<td valign="middle" align="right"><img src="cid:sire-essalud-blanco" height="34" alt="EsSalud" style="display:block;border:0;height:34px;width:auto;margin-left:auto"></td>
</tr></table>
</td></tr>
<tr><td style="padding:32px;font-family:{FUENTE};color:{TINTA}">
<p style="margin:0 0 6px;font-size:13px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:{color}">{eyebrow}</p>
<h1 style="margin:0 0 12px;font-size:24px;line-height:1.25;font-weight:700;color:{NAVY};font-family:{FUENTE}">{titulo}</h1>
<p style="margin:0 0 4px;font-size:15px;line-height:1.5;color:#33424F">{intro_html}</p>
{cuerpo_html}
{cierre()}
</td></tr>
<tr><td style="background:#F4F6F8;border-top:1px solid {LINEA};padding:20px 32px;border-radius:0 0 8px 8px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td valign="middle" width="1" style="padding-right:16px"><img src="cid:sire-essalud" height="40" alt="EsSalud" style="display:block;border:0;height:40px;width:auto"></td>
<td valign="middle" width="1" style="padding-right:20px"><img src="cid:sire-oiis" height="48" alt="OIIS" style="display:block;border:0;height:48px;width:auto"></td>
<td valign="middle" style="font-size:13px;line-height:1.6;color:{MUTE};font-family:{FUENTE}">
<div style="font-weight:600;color:#33424F">EsSalud · Oficina de Inteligencia e Información Sanitaria (OIIS)</div>
<div>Sistema de Recepción de Reportes Epidemiológicos con Agentes · © {anio} EsSalud</div>
</td></tr></table>
</td></tr>
</table>
</td></tr></table>
</body></html>"""
