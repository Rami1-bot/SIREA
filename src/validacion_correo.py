# src/validacion_correo.py
"""
Verificación del correo del responsable del envío.

El acuse de recibo se manda al correo que se escribe en el formulario; si
tiene un error de tipeo, el acuse nunca llega. Por eso:

  1. el correo se escribe dos veces y deben coincidir;
  2. el correo institucional esperado es «usuario@essalud.gob.pe»; cualquier
     otro dominio (por ejemplo gmail.com, en casos excepcionales) exige una
     confirmación expresa;
  3. si el dominio se parece a uno conocido pero está mal escrito
     («essalud.gob.pe», «gmail.com»...), se propone la corrección.

Son funciones puras (sin Streamlit) para poder probarlas.
"""

import re
from difflib import SequenceMatcher
from typing import Dict, Optional

DOMINIO_INSTITUCIONAL = "essalud.gob.pe"

# Proveedores comunes de correo personal: se aceptan, pero con confirmación.
DOMINIOS_PERSONALES = (
    "gmail.com", "hotmail.com", "hotmail.es", "outlook.com", "outlook.es",
    "yahoo.com", "yahoo.es", "live.com", "icloud.com",
)

_PATRON = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)+\Z")


def normalizar(correo: Optional[str]) -> str:
    """Quita espacios y pasa a minúsculas (los correos no distinguen mayúsculas)."""
    return (correo or "").strip().lower()


def formato_valido(correo: str) -> bool:
    """Formato razonable de correo (sin puntos consecutivos ni al borde del usuario)."""
    c = normalizar(correo)
    if not _PATRON.match(c) or len(c) > 254:
        return False
    usuario, dominio = c.rsplit("@", 1)
    if usuario.startswith(".") or usuario.endswith(".") or ".." in usuario or ".." in dominio:
        return False
    return len(dominio.rsplit(".", 1)[-1]) >= 2


def dominio(correo: str) -> str:
    c = normalizar(correo)
    return c.rsplit("@", 1)[-1] if "@" in c else ""


def es_institucional(correo: str) -> bool:
    return dominio(correo) == DOMINIO_INSTITUCIONAL


def _distancia(a: str, b: str) -> int:
    """Distancia de edición (Levenshtein) entre dos cadenas cortas."""
    if a == b:
        return 0
    previa = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (ca != cb)))
        previa = actual
    return previa[-1]


def sugerir_correccion(correo: str) -> Optional[str]:
    """
    Si el dominio no es uno conocido pero se parece mucho a uno (error de
    tipeo), devuelve el correo corregido; si no, None.
    """
    c = normalizar(correo)
    if "@" not in c:
        return None
    usuario, dom = c.rsplit("@", 1)
    conocidos = (DOMINIO_INSTITUCIONAL,) + DOMINIOS_PERSONALES
    if not usuario or not dom or dom in conocidos:
        return None
    # «essalud.pe», «essalud.com», «essalud.gob.pe.com»...: casi seguro es el institucional.
    if "essalud" in dom or "esalud" in dom:
        return f"{usuario}@{DOMINIO_INSTITUCIONAL}"
    mejor, mejor_d = None, 99
    for k in conocidos:
        d = _distancia(dom, k)
        # Tolerancia: hasta 2 cambios, y que se parezcan de verdad.
        if d <= 2 and SequenceMatcher(None, dom, k).ratio() >= 0.8 and d < mejor_d:
            mejor, mejor_d = k, d
    return f"{usuario}@{mejor}" if mejor else None


def evaluar(correo: str, repetido: str, confirmado_no_institucional: bool = False) -> Dict:
    """
    Evalúa el correo y su repetición.

    Devuelve un diccionario con:
      estado:      'pendiente' | 'error' | 'ok'
      mensaje:     texto corto para la lista de validaciones
      detalle:     explicación para mostrar bajo el campo (puede ser '')
      sugerencia:  correo corregido propuesto (o None)
      requiere_confirmacion: True si es un dominio no institucional
    """
    c, r = normalizar(correo), normalizar(repetido)
    res = {"estado": "pendiente", "mensaje": "Campo obligatorio", "detalle": "",
           "sugerencia": None, "requiere_confirmacion": False}

    if not c:
        return res
    sug = sugerir_correccion(c)
    if sug and formato_valido(sug):
        res.update(estado="error", mensaje="Posible error en el dominio", sugerencia=sug,
                   detalle=f"El dominio «{dominio(c)}» no parece correcto.")
        return res

    if not formato_valido(c):
        res.update(estado="error", mensaje="Formato inválido",
                   detalle="Revise el correo: debe tener la forma nombre@essalud.gob.pe.")
        return res

    if not r:
        res.update(estado="pendiente", mensaje="Repita el correo para confirmarlo")
        return res
    if c != r:
        res.update(estado="error", mensaje="Los correos no coinciden",
                   detalle="El correo y su repetición deben ser idénticos; el acuse se enviará a esa dirección.")
        return res

    if not es_institucional(c):
        res["requiere_confirmacion"] = True
        if not confirmado_no_institucional:
            res.update(estado="pendiente", mensaje="Confirme que el correo es correcto",
                       detalle=("Los envíos suelen hacerse con el correo institucional (nombre@essalud.gob.pe). "
                                "Si usará una dirección distinta, confirme que es correcta."))
            return res

    res.update(estado="ok", mensaje="Válido", detalle="")
    return res
