# src/excel_corporativo.py
"""
Excel con formato corporativo (EsSalud · OIIS) para cualquier tabla del panel.

    xlsx = generar_excel_df(df, hoja="Tabla de control", titulo="Tabla de control", subtitulo="Semana 41 · 2026")

Mismo estilo que el resto de los Excel del SIREA (auditoría, resumen por red): cinta con la institución,
título, encabezado azul, filas alternadas, bordes finos, números y fechas con su formato real (se pueden
ordenar y sumar), porcentajes con color (verde / ámbar / rojo), estados con color, filtros, paneles
inmovilizados y página lista para imprimir (horizontal, ajustada al ancho, con encabezado repetido y
número de página). Los textos nunca se interpretan como fórmulas.
"""

import io
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

LIMA = timezone(timedelta(hours=-5))

NAVY, AZUL, CLARO, LINEA = "1D3F76", "006DB0", "F4F6F8", "D5DDE4"
ZEBRA = "F8FAFC"
VERDE_BG, VERDE_FG = "E7F3EA", "1E6B3A"
AMBAR_BG, AMBAR_FG = "FBF3E4", "7A5A00"
ROJO_BG, ROJO_FG = "FDECEA", "B42318"
GRIS_BG, GRIS_FG = "EEF1F4", "4A5560"

FILA_ENCABEZADO = 5
_lado = Side(style="thin", color=LINEA)
_borde = Border(left=_lado, right=_lado, top=_lado, bottom=_lado)

_PCT = re.compile(r"^-?\d+(?:[.,]\d+)?\s*%$")
_FECHA_HORA = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_COL_SEMANA = re.compile(r"^S\d{1,2}$")

_VERDE = {"completo", "enviado", "aprobado", "recibido a tiempo", "ok", "correcto", "activo", "ejecutada", "descargada", "vigente", "aprobada"}
_AMBAR = {"parcial", "pendiente", "observado", "en proceso", "por aprobar", "solo preparada", "vencido", "excepcional"}
_ROJO = {"bajo", "atrasado", "envío tardío", "sin envíos", "error", "con error", "rechazado", "rechazada", "revocado"}
_GRIS = {"excluido", "inactivo", "cancelada", "—"}


def _tono_texto(valor: str):
    v = valor.strip().lower()
    if v in _VERDE:
        return VERDE_BG, VERDE_FG
    if v in _AMBAR:
        return AMBAR_BG, AMBAR_FG
    if v in _ROJO:
        return ROJO_BG, ROJO_FG
    if v in _GRIS and v != "—":
        return GRIS_BG, GRIS_FG
    return None


def _tono_pct(p: float):
    """p en puntos porcentuales (0–100)."""
    if p >= 90:
        return VERDE_BG, VERDE_FG
    if p >= 60:
        return AMBAR_BG, AMBAR_FG
    return ROJO_BG, ROJO_FG


def _limpio(texto: str) -> str:
    return ILLEGAL_CHARACTERS_RE.sub("", texto)


def _es_numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _vacio(v) -> bool:
    if v is None:
        return True
    try:
        return v != v      # NaN
    except Exception:
        return False


def _convertir(v):
    """(valor para la celda, formato, tipo) donde tipo ∈ texto | numero | pct | fecha | vacio."""
    if _vacio(v):
        return None, None, "vacio"
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()          # numpy → Python
        except Exception:
            pass
    if isinstance(v, bool):
        return ("Sí" if v else "No"), None, "texto"
    if _es_numero(v):
        entero = float(v) == int(v)
        return v, ("#,##0" if entero else "#,##0.0"), "numero"
    if isinstance(v, datetime):
        return (v.replace(tzinfo=None) if v.tzinfo else v), "dd/mm/yyyy hh:mm", "fecha"
    s = _limpio(str(v)).strip()
    if s in ("", "—", "-"):
        return None, None, "vacio"
    if _PCT.match(s):
        n = float(s.replace("%", "").replace(",", ".").strip())
        return n / 100.0, ("0%" if n == int(n) else "0.0%"), "pct"
    m = _FECHA_HORA.match(s)
    if m:
        d, mes, a, h, mi, se = m.groups()
        try:
            f = datetime(int(a), int(mes), int(d), int(h or 0), int(mi or 0), int(se or 0))
            return f, ("dd/mm/yyyy hh:mm" if h is not None else "dd/mm/yyyy"), "fecha"
        except ValueError:
            pass
    return s, None, "texto"


def _col_pct_puntos(titulo: str) -> bool:
    t = titulo.strip()
    return bool(_COL_SEMANA.match(t)) or t.lower() in ("promedio",) or "%" in t or "porcentaje" in t.lower()


def _humanizar(nombre_base: str) -> str:
    """'tabla_control_semana_41_2026' → 'Semana 41 · 2026' (solo lo que se puede deducir con seguridad)."""
    partes = []
    m = re.search(r"semana_?(\d{1,2})", nombre_base or "", re.I)
    if m:
        partes.append(f"Semana {int(m.group(1))}")
    a = re.search(r"(20\d{2})", nombre_base or "")
    if a:
        partes.append(a.group(1))
    return " · ".join(partes)


def _banner(ws, fila: int, n_col: int, texto: str, tam: int, color: str, fondo: Optional[str], alto: int):
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=n_col)
    c = ws.cell(row=fila, column=1)
    c.value = texto
    c.data_type = "s"
    c.font = Font(name="Calibri", size=tam, bold=True, color=color)
    if fondo:
        for col in range(1, n_col + 1):
            ws.cell(row=fila, column=col).fill = PatternFill("solid", fgColor=fondo)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[fila].height = alto


def generar_excel_df(df, hoja: str = "Datos", titulo: Optional[str] = None, subtitulo: Optional[str] = None,
                     nota: Optional[str] = None) -> bytes:
    """Excel corporativo de un DataFrame de pandas. Devuelve los bytes del .xlsx."""
    columnas = [str(c) for c in df.columns]
    filas = [list(f) for f in df.itertuples(index=False, name=None)]
    n_col = max(1, len(columnas))
    n_fil = len(filas)
    titulo = titulo or hoja
    ahora = datetime.now(LIMA)

    wb = Workbook()
    ws = wb.active
    ws.title = _limpio(re.sub(r"[\\/*?:\[\]]", " ", hoja)).strip()[:31] or "Datos"
    ws.sheet_view.showGridLines = False
    wb.properties.title = titulo
    wb.properties.creator = "SIREA · OIIS EsSalud"

    # ---- convertir y medir
    convertidas, anchos = [], [len(c) + 4 for c in columnas]
    tipos_col = [set() for _ in columnas]
    for f in filas:
        fila_c = []
        for j, v in enumerate(f):
            val, fmt, tipo = _convertir(v)
            fila_c.append((val, fmt, tipo))
            tipos_col[j].add(tipo)
            largo = {"fecha": 17, "pct": 8, "numero": min(len(str(val)) + 2, 14)}.get(tipo, len(str(val)) if val is not None else 1)
            anchos[j] = max(anchos[j], min(largo + 2, 48))
        convertidas.append(fila_c)

    # ---- cinta y título
    _banner(ws, 1, n_col, "EsSalud · Oficina de Inteligencia e Información Sanitaria (OIIS)", 10, "FFFFFF", AZUL, 20)
    _banner(ws, 2, n_col, f"SIREA · {titulo}", 16, "FFFFFF", NAVY, 30)
    sub = subtitulo or _humanizar(titulo)
    sub = f"{sub} · " if sub else ""
    _banner(ws, 3, n_col, f"{sub}{n_fil:,} registro{'s' if n_fil != 1 else ''} · Generado el {ahora:%d/%m/%Y %H:%M} (hora de Lima)".replace(",", " "),
            10, NAVY, CLARO, 22)
    ws.row_dimensions[4].height = 8

    # ---- encabezado
    for j, t in enumerate(columnas, 1):
        c = ws.cell(row=FILA_ENCABEZADO, column=j)
        c.value = _limpio(t)
        c.data_type = "s"
        c.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _borde
    ws.row_dimensions[FILA_ENCABEZADO].height = 32

    # ---- cuerpo
    for i, fila_c in enumerate(convertidas):
        r = FILA_ENCABEZADO + 1 + i
        zebra = ZEBRA if i % 2 else None
        for j, (val, fmt, tipo) in enumerate(fila_c, 1):
            c = ws.cell(row=r, column=j)
            c.value = val if tipo != "vacio" else "—"
            if tipo in ("texto", "vacio"):
                c.data_type = "s"
            fondo, color, negrita = zebra, "14202B", False
            if tipo == "pct":
                fondo, color = _tono_pct(val * 100)
                negrita = True
            elif tipo == "numero" and _col_pct_puntos(columnas[j - 1]) and 0 <= val <= 100:
                fondo, color = _tono_pct(float(val))
                c.number_format = '0.0"%"' if float(val) != int(val) else '0"%"'
                negrita = True
            elif tipo == "texto":
                t = _tono_texto(val)
                if t:
                    fondo, color = t
                    negrita = True
            if fmt and not c.number_format.endswith('"%"'):
                c.number_format = fmt
            alinea = "left" if tipo in ("texto", "vacio") else ("center" if tipo in ("fecha", "pct") else "right")
            if tipo == "vacio":
                alinea, color = "center", "8A96A3"
            if tipo == "texto" and _tono_texto(val):
                alinea = "center"
            c.font = Font(name="Calibri", size=10, bold=negrita, color=color)
            if fondo:
                c.fill = PatternFill("solid", fgColor=fondo)
            c.alignment = Alignment(horizontal=alinea, vertical="center", wrap_text=(tipo == "texto"))
            c.border = _borde

    # ---- anchos, filtros, paneles
    for j, a in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(j)].width = max(10, min(a, 48))
    ultima = FILA_ENCABEZADO + max(n_fil, 1)
    if n_fil:
        ws.auto_filter.ref = f"A{FILA_ENCABEZADO}:{get_column_letter(n_col)}{ultima}"
    ws.freeze_panes = ws.cell(row=FILA_ENCABEZADO + 1, column=2 if n_col > 6 else 1)

    # ---- pie
    pie = FILA_ENCABEZADO + n_fil + 2
    ws.merge_cells(start_row=pie, start_column=1, end_row=pie, end_column=n_col)
    p = ws.cell(row=pie, column=1)
    p.value = nota or "Documento generado por el Sistema de Recepción de Reportes Epidemiológicos (SIREA). Información de uso interno de EsSalud."
    p.data_type = "s"
    p.font = Font(name="Calibri", size=9, italic=True, color="566573")
    p.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[pie].height = 28

    # ---- impresión
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.print_title_rows = f"{FILA_ENCABEZADO}:{FILA_ENCABEZADO}"
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top, ws.page_margins.bottom = 0.6, 0.6
    ws.oddFooter.left.text = "SIREA · EsSalud OIIS"
    ws.oddFooter.left.size = 8
    ws.oddFooter.right.text = "Página &P de &N"
    ws.oddFooter.right.size = 8

    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()
