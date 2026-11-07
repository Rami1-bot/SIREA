# src/zip_seguridad.py
"""
Revisión de seguridad de los ZIP que envían las redes (v7.5).

El SIREA recibe archivos de muchas personas y luego el personal del panel los
descarga y abre. Por eso un ZIP no basta con tener la extensión correcta:
aquí se revisa también QUÉ HAY DENTRO, sin ejecutar nada.

Qué se bloquea
--------------
Estructura del ZIP
  * ZIP que no empieza como un ZIP (por ejemplo un ejecutable con un ZIP pegado).
  * Archivos protegidos con contraseña (no se pueden revisar).
  * Enlaces simbólicos, rutas absolutas, «..», unidades (C:\\) o caracteres de control.
  * Nombres repetidos dentro del mismo ZIP.
  * Dobles extensiones peligrosas («reporte.exe.062», «datos.php.csv»).
  * «ZIP bomba»: demasiadas entradas, tamaño declarado que no coincide con el real o
    una compresión desproporcionada.

Contenido de cada archivo (las extensiones numéricas o de código de centro, como
«.062», se siguen aceptando: son archivos binarios del sistema que genera el
reporte; lo que se bloquea es lo que SE PARECE a un programa o a un script)
  * Ejecutables de Windows, Linux y macOS, bibliotecas, accesos directos (.lnk).
  * Scripts (shell, PowerShell, PHP, JavaScript, HTML, SVG, .reg, .bat).
  * Archivos comprimidos dentro del ZIP (ZIP, RAR, 7z, gzip, tar, cab...).
  * Documentos de Office con macros, PDF y RTF.
  * Hojas de cálculo (.xlsx / .xls) con macros, objetos incrustados o controles ActiveX.
  * Fórmulas peligrosas en texto (.csv): «=cmd|...», «=HYPERLINK(...)».

Todas las funciones trabajan en memoria y nunca extraen ni ejecutan el contenido.
"""

import hashlib
import io
import os
import re
import stat
import unicodedata
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------- límites

MAX_ENTRADAS = 1000                      # entradas del ZIP (archivos + carpetas)
MAX_ARCHIVOS_XLSX_INTERNOS = 2000
MAX_BYTES_REVISION_COMPLETA = 64 * 1024 * 1024   # un .xlsx/.xls más grande no se puede revisar a fondo
MAX_RATIO_ENTRADA = max(20, int(os.getenv("ZIP_MAX_RATIO", "200") or "200"))   # tamaño real / tamaño comprimido
MAX_BYTES_RATIO_ENTRADA = 20 * 1024 * 1024       # el ratio solo preocupa si el archivo es grande
MAX_RATIO_TOTAL = 150
MAX_BYTES_RATIO_TOTAL = 100 * 1024 * 1024
LARGO_MAX_NOMBRE = 255
PROFUNDIDAD_MAX = 12
BYTES_CABECERA = 64 * 1024               # lo que se mira al inicio de cada archivo
CHUNK = 1024 * 1024

EXT_COMPRIMIDAS = {".zip", ".rar", ".7z", ".gz", ".tgz", ".tar", ".bz2", ".xz", ".cab", ".z", ".zst", ".lz", ".arj", ".ace"}
# Extensiones que, escondidas en medio del nombre, delatan un disfraz («reporte.exe.062»).
EXT_DISFRAZ_EXTRA = EXT_COMPRIMIDAS | {".pdf", ".rtf", ".doc", ".docx", ".ppt", ".pptx", ".dot", ".dotm",
                                       ".xlsb", ".xlam", ".pptm", ".ps1", ".psm1", ".bat", ".cmd", ".vbs",
                                       ".jar", ".class", ".so", ".dylib", ".app", ".dmg", ".pkg", ".deb", ".rpm", ".msix"}

MOTIVO_ESTRUCTURA = "estructura"
MOTIVO_CONTENIDO = "contenido"

# ---------------------------------------------------------------- firmas (primeros bytes)

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_FIRMAS_SIEMPRE = (
    (b"\x7fELF", "programa ejecutable de Linux (ELF)"),
    (b"\xfe\xed\xfa\xce", "programa ejecutable de macOS"),
    (b"\xfe\xed\xfa\xcf", "programa ejecutable de macOS"),
    (b"\xce\xfa\xed\xfe", "programa ejecutable de macOS"),
    (b"\xcf\xfa\xed\xfe", "programa ejecutable de macOS"),
    (b"\xca\xfe\xba\xbe", "programa de Java o de macOS"),
    (b"\x00asm", "módulo WebAssembly"),
    (b"#!", "script (empieza con #!)"),
    (b"%PDF-", "documento PDF"),
    (b"{\\rtf", "documento RTF"),
    (b"L\x00\x00\x00\x01\x14\x02\x00", "acceso directo de Windows (.lnk)"),
    (b"Rar!\x1a\x07", "archivo comprimido RAR dentro del ZIP"),
    (b"7z\xbc\xaf\x27\x1c", "archivo comprimido 7z dentro del ZIP"),
    (b"\x1f\x8b", "archivo comprimido gzip dentro del ZIP"),
    (b"\xfd7zXZ\x00", "archivo comprimido xz dentro del ZIP"),
    (b"MSCF\x00\x00\x00\x00", "archivo comprimido CAB dentro del ZIP"),
    (b"\x28\xb5\x2f\xfd", "archivo comprimido zstd dentro del ZIP"),
)

# Texto que delata scripts o páginas web. Solo se busca en archivos de texto
# (sin bytes nulos) y en los primeros BYTES_CABECERA.
_PATRON_SCRIPT = re.compile(
    rb"(<\?php|<script[\s>]|<html[\s>]|<!doctype\s+html|<iframe[\s>]|<svg[\s>]|<hta:application|"
    rb"@echo\s+off|windows\s+registry\s+editor|\[autorun\]|powershell(\.exe)?\s+-|"
    rb"invoke-expression|invoke-webrequest|iex\s*\(|frombase64string|wscript\.shell|"
    rb"createobject\s*\(|cmd(\.exe)?\s+/c\b|mshta(\.exe)?\s|certutil(\.exe)?\s+-|bitsadmin\s|"
    rb"regsvr32(\.exe)?\s|rundll32(\.exe)?\s|javascript:|vbscript:|\bos\.system\s*\(|\bsubprocess\.)",
    re.IGNORECASE,
)

# Fórmulas de hoja de cálculo que ejecutan programas o sacan datos (.csv y otros textos).
_PATRON_FORMULA = re.compile(
    rb"(?:^|[,;\t\"'|])\s*[=+\-@]\s*(?:cmd|powershell|mshta|wscript|cscript|rundll32|regsvr32|msiexec|certutil|bitsadmin|calc)\b"
    rb"|(?:^|[,;\t\"'|])\s*[=+@]\s*(?:hyperlink|importxml|importdata|importhtml|importfeed|webservice|dde)\s*\(",
    re.IGNORECASE | re.MULTILINE,
)

_PARTES_OFFICE_PELIGROSAS = (
    "vbaproject", "/activex/", "/embeddings/", "oleobject", "macrosheets/", "/macros/", "xl/externallinks/oleobject",
)

_VBA_UTF16 = "_VBA_PROJECT".encode("utf-16-le")
_VBA_ASCII = b"_VBA_PROJECT"


# ---------------------------------------------------------------- utilidades

def _ext(nombre: str) -> str:
    base = nombre.replace("\\", "/").rsplit("/", 1)[-1]
    return ("." + base.rsplit(".", 1)[1].lower()) if "." in base else ""


def _es_texto(cabecera: bytes) -> bool:
    """True si parece texto (sin bytes nulos; UTF-16 con BOM también cuenta como texto)."""
    if cabecera.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True
    return b"\x00" not in cabecera


def _es_pe(cabecera: bytes) -> bool:
    """Ejecutable de Windows: «MZ» y, en la posición que indica el offset 0x3C, la marca «PE\\0\\0»."""
    if not cabecera.startswith(b"MZ") or len(cabecera) < 0x40:
        return False
    off = int.from_bytes(cabecera[0x3C:0x40], "little")
    if 0 < off <= len(cabecera) - 4:
        return cabecera[off:off + 4] == b"PE\x00\x00"
    return off > len(cabecera) and off < 0x10000000   # encabezado PE más allá de lo leído: se trata como ejecutable


def _es_tar(cabecera: bytes) -> bool:
    return len(cabecera) >= 262 and cabecera[257:262] == b"ustar"


def tipo_real(cabecera: bytes) -> str:
    """'zip' | 'ole' | 'pe' | 'texto' | 'binario' según los primeros bytes."""
    if cabecera.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "zip"
    if cabecera.startswith(_OLE):
        return "ole"
    if _es_pe(cabecera):
        return "pe"
    return "texto" if _es_texto(cabecera[:4096]) else "binario"


# ---------------------------------------------------------------- nombres

def problema_de_nombre(nombre: str, extensiones_bloqueadas: Iterable[str]) -> Optional[str]:
    """Motivo por el que un nombre de archivo del ZIP no es seguro (o None)."""
    if not nombre or not nombre.strip():
        return "nombre vacío"
    if len(nombre) > LARGO_MAX_NOMBRE:
        return "nombre demasiado largo"
    for c in nombre:
        cat = unicodedata.category(c)
        if cat in ("Cc", "Cf") or c == "\x00":     # controles y marcas de dirección (U+202E y similares)
            return "el nombre contiene caracteres de control u ocultos"
    limpio = nombre.replace("\\", "/")
    if limpio.startswith("/") or re.match(r"^[A-Za-z]:", limpio) or limpio.startswith("//"):
        return "ruta absoluta o de unidad (C:\\)"
    partes = [p for p in limpio.split("/") if p != ""]
    if any(p == ".." for p in partes):
        return "ruta que sale de la carpeta («..»)"
    if len(partes) > PROFUNDIDAD_MAX:
        return "demasiadas carpetas anidadas"
    base = partes[-1] if partes else ""
    if base.endswith((".", " ")):
        return "el nombre termina en punto o espacio (truco para ocultar la extensión)"
    bloqueadas = {e.lower() for e in extensiones_bloqueadas} | EXT_COMPRIMIDAS | EXT_DISFRAZ_EXTRA
    trozos = base.lower().split(".")
    for t in trozos[1:-1]:          # la última es la extensión real: de esa se ocupa el validador
        if t and ("." + t) in bloqueadas:
            return f"doble extensión sospechosa («.{t}» dentro del nombre)"
    return None


# ---------------------------------------------------------------- estructura del ZIP

def revisar_estructura(archivo_bytes: bytes, zf: zipfile.ZipFile, extensiones_bloqueadas: Iterable[str],
                       max_archivos: int, max_bytes_descomprimido: int) -> List[Dict]:
    """
    Problemas de estructura del ZIP. Devuelve [{"archivo", "motivo"}]; vacío si está bien.
    No abre el contenido de los archivos.
    """
    problemas: List[Dict] = []

    def add(archivo: str, motivo: str):
        problemas.append({"archivo": archivo, "motivo": motivo, "tipo": MOTIVO_ESTRUCTURA})

    if not archivo_bytes.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        add("(archivo ZIP)", "el archivo no empieza como un ZIP (puede traer otro programa pegado)")
        return problemas

    infos = zf.infolist()
    if len(infos) > MAX_ENTRADAS:
        add("(archivo ZIP)", f"trae demasiadas entradas ({len(infos)}); el máximo es {MAX_ENTRADAS}")
        return problemas

    vistos: Dict[str, str] = {}
    total_real = 0
    for info in infos:
        nombre = info.filename
        if info.is_dir():
            if problema_de_nombre(nombre.rstrip("/") or "x", extensiones_bloqueadas) in ("ruta que sale de la carpeta («..»)",
                                                                                         "ruta absoluta o de unidad (C:\\)"):
                add(nombre, "carpeta con ruta insegura")
            continue
        mot = problema_de_nombre(nombre, extensiones_bloqueadas)
        if mot:
            add(nombre, mot)
        clave = nombre.replace("\\", "/").strip("/").lower()
        if clave in vistos:
            add(nombre, "hay dos archivos con el mismo nombre en el ZIP")
        vistos[clave] = nombre
        if info.flag_bits & 0x1:
            add(nombre, "está protegido con contraseña y no se puede revisar")
        modo = (info.external_attr >> 16) & 0xFFFF
        if modo and stat.S_ISLNK(modo):
            add(nombre, "es un enlace simbólico")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            add(nombre, "método de compresión no admitido")
        comprimido = max(info.compress_size, 1)
        if info.file_size > MAX_BYTES_RATIO_ENTRADA and info.file_size / comprimido > MAX_RATIO_ENTRADA:
            add(nombre, "compresión desproporcionada (posible ZIP bomba)")
        total_real += info.file_size

    if len(archivo_bytes) and total_real > MAX_BYTES_RATIO_TOTAL and total_real / len(archivo_bytes) > MAX_RATIO_TOTAL:
        add("(archivo ZIP)", "compresión total desproporcionada (posible ZIP bomba)")
    if total_real > max_bytes_descomprimido:
        add("(archivo ZIP)", f"el tamaño descomprimido supera {max_bytes_descomprimido // (1024 * 1024)} MB")
    n_archivos = sum(1 for i in infos if not i.is_dir())
    if n_archivos > max_archivos:
        add("(archivo ZIP)", f"trae {n_archivos} archivos; el máximo es {max_archivos}")
    return problemas


# ---------------------------------------------------------------- contenido

def _revisar_xlsx(datos: bytes) -> Optional[str]:
    """Motivo por el que un .xlsx (que por dentro es un ZIP) no es seguro, o None."""
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            infos = z.infolist()
            if len(infos) > MAX_ARCHIVOS_XLSX_INTERNOS:
                return "la hoja de cálculo trae demasiadas partes internas"
            total = 0
            for i in infos:
                n = i.filename.lower().replace("\\", "/")
                if i.flag_bits & 0x1:
                    return "la hoja de cálculo está protegida con contraseña y no se puede revisar"
                if ".." in n.split("/") or n.startswith("/"):
                    return "la hoja de cálculo trae rutas internas inseguras"
                if any(p in n for p in _PARTES_OFFICE_PELIGROSAS):
                    return "la hoja de cálculo trae macros, objetos incrustados o controles ActiveX"
                total += i.file_size
                if i.file_size > MAX_BYTES_RATIO_ENTRADA and i.file_size / max(i.compress_size, 1) > MAX_RATIO_ENTRADA:
                    return "la hoja de cálculo trae una parte con compresión desproporcionada"
            if total > 1024 * 1024 * 1024:
                return "la hoja de cálculo es desproporcionadamente grande al descomprimirse"
            try:
                tipos = z.read("[Content_Types].xml")[:200000].lower()
                if b"macroenabled" in tipos or b"vbaproject" in tipos:
                    return "la hoja de cálculo está habilitada para macros"
            except KeyError:
                pass
    except zipfile.BadZipFile:
        return "la hoja de cálculo está dañada o no es un .xlsx real"
    return None


def revisar_contenido(nombre: str, cabecera: bytes, datos_completos: Optional[bytes]) -> Optional[str]:
    """
    Motivo por el que el CONTENIDO de un archivo no es seguro (o None).
    `cabecera`: primeros bytes; `datos_completos`: el archivo entero, solo si hace falta
    (hojas de cálculo) y cabe en memoria.
    """
    ext = _ext(nombre)
    tipo = tipo_real(cabecera)

    if tipo == "pe":
        return "programa ejecutable de Windows (.exe/.dll)"
    for firma, texto in _FIRMAS_SIEMPRE:
        if cabecera.startswith(firma):
            return texto
    if _es_tar(cabecera):
        return "archivo comprimido TAR dentro del ZIP"
    if cabecera.startswith(b"BZh") and cabecera[4:10] == b"1AY&SY":
        return "archivo comprimido bzip2 dentro del ZIP"
    if cabecera[:3] == b"\xef\xbb\xbf" and cabecera[3:5] == b"#!":
        return "script (empieza con #!)"

    if tipo == "zip":
        if ext not in (".xlsx", ".xls"):
            return "archivo comprimido (o documento de Office) dentro del ZIP"
        if datos_completos is None:
            return "la hoja de cálculo es demasiado grande para revisarla con seguridad"
        return _revisar_xlsx(datos_completos)

    if tipo == "ole":
        if ext != ".xls":
            return "documento de Office antiguo o instalador (OLE) que no es una hoja .xls"
        if datos_completos is None:
            return "la hoja de cálculo es demasiado grande para revisarla con seguridad"
        if _VBA_UTF16 in datos_completos or _VBA_ASCII in datos_completos:
            return "la hoja de cálculo (.xls) trae macros"
        return None

    if ext == ".xlsx" and tipo != "zip":
        return "dice ser .xlsx pero no es una hoja de cálculo real"

    if tipo == "texto":
        if _PATRON_SCRIPT.search(cabecera):
            return "contiene código de un script o de una página web"
        if _PATRON_FORMULA.search(cabecera):
            return "contiene fórmulas que podrían ejecutar programas al abrirse en Excel"
    return None


def leer_y_revisar(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> Tuple[str, int, Optional[str]]:
    """
    Lee un archivo del ZIP por partes y devuelve (sha256, bytes_leidos, problema).
    Comprueba además que el tamaño real coincida con el declarado (anti ZIP bomba).
    El contenido completo solo se guarda en memoria si es una hoja de cálculo (≤ 64 MB).
    """
    declarado = info.file_size
    ext = _ext(info.filename)
    necesita_todo = ext in (".xlsx", ".xls")
    guardar_todo = necesita_todo and declarado <= MAX_BYTES_REVISION_COMPLETA
    h = hashlib.sha256()
    cabecera = b""
    partes: List[bytes] = []
    leidos = 0
    try:
        with zf.open(info) as f:
            while True:
                bloque = f.read(CHUNK)
                if not bloque:
                    break
                leidos += len(bloque)
                if leidos > declarado:
                    return h.hexdigest(), leidos, "el tamaño real no coincide con el declarado (posible ZIP bomba)"
                h.update(bloque)
                if len(cabecera) < BYTES_CABECERA:
                    cabecera += bloque[:BYTES_CABECERA - len(cabecera)]
                if guardar_todo:
                    partes.append(bloque)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError) as e:
        return h.hexdigest(), leidos, f"no se pudo leer el archivo ({type(e).__name__})"
    if leidos != declarado:
        return h.hexdigest(), leidos, "el tamaño real no coincide con el declarado"
    datos = b"".join(partes) if guardar_todo else None
    return h.hexdigest(), leidos, revisar_contenido(info.filename, cabecera, datos)


def resumen_problemas(problemas: List[Dict], limite: int = 4) -> str:
    """Texto para la persona: «archivo: motivo; archivo: motivo…»."""
    partes = [f"«{p['archivo']}»: {p['motivo']}" for p in problemas[:limite]]
    extra = len(problemas) - limite
    if extra > 0:
        partes.append(f"y {extra} más")
    return "; ".join(partes)
