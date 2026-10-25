# src/informe_pdf.py
"""
SIREA 3.3 · Informe semanal en PDF con formato corporativo (EsSalud · OIIS).

  * Cabecera con los logos de EsSalud y de la OIIS, pie con la leyenda de
    validación (o de borrador) y el número de página.
  * Marca de agua: el logo de la OIIS, muy tenue, en el centro de cada hoja.
    Si el informe aún no está aprobado, además dice «BORRADOR» en diagonal.
  * Un recuadro con las cifras del sistema (las mismas que usó el informe).
  * Todo el texto viene del informe (títulos «Situación de la semana»,
    «Lo destacado», «Patrones a vigilar», «Recomendaciones» y viñetas «- »);
    se escapa para que no se interprete como marcado.
"""

from __future__ import annotations

import io
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from xml.sax.saxutils import escape

ASSETS = Path(__file__).resolve().parent.parent / "assets"
AZUL = "#0077C8"
NAVY = "#12324F"
GRIS = "#5B6B7A"
TITULOS = ("Situación de la semana", "Lo destacado", "Patrones a vigilar", "Recomendaciones")


@lru_cache(maxsize=4)
def _marca_de_agua(opacidad: float = 0.07) -> Optional[bytes]:
    """Logo de la OIIS aclarado (PNG) para usar de fondo."""
    try:
        from PIL import Image
        im = Image.open(ASSETS / "oiis-azul.png").convert("RGBA")
        r, g, b, a = im.split()
        a = a.point(lambda v: int(v * opacidad))
        im = Image.merge("RGBA", (r, g, b, a))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return None


def _imagen(nombre: str):
    from reportlab.lib.utils import ImageReader
    ruta = ASSETS / nombre
    return ImageReader(str(ruta)) if ruta.exists() else None


def generar(fila: Dict, texto: Optional[str] = None, borrador: Optional[bool] = None) -> bytes:
    """
    PDF del informe. `fila` es la fila de agente_informes. `texto` permite
    previsualizar lo que la persona está editando; si falta se usa el texto
    aprobado (o el del sistema). `borrador` por defecto: estado != APROBADO.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    es_borrador = (fila.get("estado") != "APROBADO") if borrador is None else bool(borrador)
    texto = texto if texto is not None else (fila.get("texto_final") or fila.get("texto_ia") or fila.get("texto_sistema") or "")
    semana, anio = fila.get("semana"), fila.get("anio")
    datos = fila.get("datos") or {}
    ancho, alto = A4

    from src.agentes.informe_semanal import leyenda
    pie = ("BORRADOR — pendiente de validación por la OIIS. No difundir." if es_borrador else leyenda(fila))
    marca = _marca_de_agua()
    logo_essalud, logo_oiis = _imagen("essalud-azul.png"), _imagen("oiis-azul.png")

    def _fondo(c, doc):
        c.saveState()
        if marca:
            lado = 120 * mm
            c.drawImage(ImageReader(io.BytesIO(marca)), (ancho - lado) / 2, (alto - lado) / 2 - 10 * mm, lado, lado,
                        mask="auto", preserveAspectRatio=True)
        if es_borrador:
            c.setFillColor(colors.HexColor("#B42318"))
            c.setFillAlpha(0.10)
            c.setFont("Helvetica-Bold", 86)
            c.translate(ancho / 2, alto / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, "BORRADOR")
            c.rotate(-35)
            c.translate(-ancho / 2, -alto / 2)
            c.setFillAlpha(1)
        # cabecera
        c.setFillColor(colors.HexColor(AZUL))
        c.rect(0, alto - 6 * mm, ancho, 6 * mm, stroke=0, fill=1)
        if logo_essalud:
            c.drawImage(logo_essalud, 18 * mm, alto - 30 * mm, 34 * mm, 21 * mm, mask="auto", preserveAspectRatio=True)
        if logo_oiis:
            c.drawImage(logo_oiis, ancho - 40 * mm, alto - 31 * mm, 22 * mm, 22 * mm, mask="auto", preserveAspectRatio=True)
        c.setFillColor(colors.HexColor(NAVY))
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(ancho / 2, alto - 17 * mm, "SEGURO SOCIAL DE SALUD — ESSALUD")
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor(GRIS))
        c.drawCentredString(ancho / 2, alto - 22 * mm, "Oficina de Inteligencia e Información Sanitaria (OIIS)")
        c.setStrokeColor(colors.HexColor("#DCE3EA"))
        c.line(18 * mm, alto - 34 * mm, ancho - 18 * mm, alto - 34 * mm)
        # pie
        c.line(18 * mm, 18 * mm, ancho - 18 * mm, 18 * mm)
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(colors.HexColor("#B42318" if es_borrador else GRIS))
        c.drawString(18 * mm, 13 * mm, pie[:150])
        c.setFillColor(colors.HexColor(GRIS))
        c.setFont("Helvetica", 7.5)
        c.drawRightString(ancho - 18 * mm, 13 * mm, f"SIREA · Documento interno · Página {doc.page}")
        c.restoreState()

    est = {
        "titulo": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor(NAVY),
                                 spaceAfter=2),
        "sub": ParagraphStyle("s", fontName="Helvetica", fontSize=10, leading=13, textColor=colors.HexColor(GRIS), spaceAfter=10),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor(AZUL),
                            spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#1F2D3A"), alignment=TA_LEFT),
        "meta": ParagraphStyle("m", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#33424F")),
    }
    cuerpo: List = [Paragraph(f"Informe semanal de cumplimiento — Semana {escape(str(semana))}/{escape(str(anio))}", est["titulo"]),
                    Paragraph("Remisión de reportes epidemiológicos semanales por red asistencial (SIREA)", est["sub"])]

    fecha_elab = str(fila.get("creado_at") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    meta = [["Fecha de elaboración", fecha_elab, "Estado", "Borrador" if es_borrador else "Aprobado"],
            ["Preparado por", str(fila.get("creado_por") or "—"), "Validado por",
             "—" if es_borrador else f"{fila.get('aprobado_por') or '—'} ({str(fila.get('aprobado_at') or '')[:10]})"]]
    t = Table([[Paragraph(f"<b>{escape(a)}</b>", est["meta"]), Paragraph(escape(b), est["meta"]),
                Paragraph(f"<b>{escape(c)}</b>", est["meta"]), Paragraph(escape(d), est["meta"])] for a, b, c, d in meta],
              colWidths=[34 * mm, 52 * mm, 28 * mm, 60 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FA")),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DCE3EA")),
                           ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E6ECF1")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    cuerpo += [t, Spacer(1, 8)]

    if datos:
        cifras = [("Redes completas", f"{datos.get('redes_completas')} de {datos.get('redes_total')}"),
                  ("Redes con pendientes", str(datos.get("redes_con_pendientes", "—"))),
                  ("Redes a vigilar", str(len(datos.get("redes_a_vigilar") or []))),
                  ("Recordatorios en la semana", str(datos.get("recordatorios_enviados_en_la_semana", "—")))]
        celdas = [[Paragraph(f'<font size="8" color="{GRIS}">{escape(k)}</font><br/><font size="14" color="{NAVY}">'
                             f'<b>{escape(v)}</b></font>', est["p"]) for k, v in cifras]]
        tk = Table(celdas, colWidths=[43.5 * mm] * 4)
        tk.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DCE3EA")),
                                ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.HexColor("#DCE3EA")),
                                ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor(AZUL)),
                                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        cuerpo += [tk, Paragraph('<font size="7.5" color="#5B6B7A">Cifras calculadas por el sistema con los envíos registrados '
                                 '(no por la IA).</font>', est["p"]), Spacer(1, 4)]

    viñetas: List[str] = []

    def _cerrar():
        if viñetas:
            cuerpo.append(ListFlowable([ListItem(Paragraph(escape(v), est["p"]), leftIndent=10) for v in viñetas],
                                       bulletType="bullet", start="•", leftIndent=12, bulletColor=colors.HexColor(AZUL)))
            viñetas.clear()

    for linea in str(texto).splitlines():
        s = linea.strip()
        if not s:
            continue
        if s in TITULOS:
            _cerrar()
            cuerpo.append(Paragraph(escape(s), est["h"]))
        elif s.startswith("- "):
            viñetas.append(s[2:])
        else:
            _cerrar()
            cuerpo.append(Paragraph(escape(s), est["p"]))
    _cerrar()
    cuerpo += [Spacer(1, 14), KeepTogether([Paragraph(
        '<font size="8" color="#5B6B7A">Las cifras provienen de SIREA. Los patrones son de uso interno de la OIIS: no '
        'constituyen una calificación ni una sanción a ninguna red. La decisión sobre las acciones corresponde a la Jefatura.</font>',
        est["p"])])]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=40 * mm, bottomMargin=24 * mm,
                            title=f"Informe semanal SIREA - Semana {semana}/{anio}", author="OIIS - EsSalud",
                            subject="Informe semanal de cumplimiento", creator="SIREA")
    doc.build(cuerpo, onFirstPage=_fondo, onLaterPages=_fondo)
    return buf.getvalue()
