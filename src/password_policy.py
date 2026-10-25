# src/password_policy.py
"""
Política de contraseñas de SIREA (Sistema de Recepción de Reportes
Epidemiológicos) - EsSalud / OIIS.

Un solo lugar define qué es una contraseña aceptable. Lo usan el cambio de
contraseña de las redes, el alta y la edición de administradores, la
asignación de contraseñas temporales y el script resetear_password_admin.py.

Cada requisito lleva su *motivo* escrito en lenguaje sencillo, para que la
pantalla pueda explicarle a la persona por qué se le pide, no solo qué se le
pide.

Requisitos:
  1. Al menos 10 caracteres.
  2. Mayúsculas, minúsculas, números y un símbolo.
  3. No ser una contraseña muy usada (ni una variante simple de ellas).
  4. No contener el usuario, la red, el nombre ni palabras de la institución.
  5. Sin secuencias (1234, abcd, qwerty) ni caracteres repetidos (aaaa).
  6. Distinta de la contraseña actual o temporal.

Las contraseñas nunca se guardan ni se registran aquí: este módulo solo las
evalúa en memoria.
"""

import re
import secrets
import string
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

LONGITUD_MINIMA = 10
# Tope por la forma en que se cifran las contraseñas (bcrypt: 72 bytes; las tildes y la ñ ocupan 2).
LONGITUD_MAXIMA = 64
BYTES_MAXIMOS = 72

# Símbolos que se aceptan (y que usa el generador). Cualquier carácter que no
# sea letra ni número cuenta como símbolo.
SIMBOLOS_GENERADOR = "!@#$%&*?+-_="

# Palabras de la institución que no deben formar parte de una contraseña.
_PALABRAS_INSTITUCION = ("essalud", "oiis", "sire", "winepi", "epidemiologia", "reporte", "reportes")

# Contraseñas muy usadas (en minúsculas y sin tildes). Incluye las más
# frecuentes en español y las que suelen armarse con el nombre de la
# institución o con el año.
_COMUNES = {
    "123456", "1234567", "12345678", "123456789", "1234567890", "12345", "111111", "000000", "121212",
    "654321", "112233", "123123", "123321", "666666", "696969", "159753", "147258", "789456", "987654321",
    "password", "password1", "password123", "passw0rd", "contrasena", "contrasena1", "contrasena123",
    "clave", "clave123", "claveclave", "secreto", "secret", "admin", "admin123", "admin1234", "administrador",
    "administrator", "root", "toor", "usuario", "usuario1", "user", "user123", "test", "test123", "prueba",
    "prueba123", "demo", "demo123", "temporal", "temporal1", "temporal123", "temp123", "cambiar", "cambiame",
    "cambio123", "bienvenido", "bienvenido1", "welcome", "welcome1", "login", "letmein", "iloveyou", "te amo",
    "teamo", "tequiero", "dios", "diosmio", "jesus", "amor", "amor123", "mivida", "princesa", "angel",
    "peru", "peru123", "peru2024", "peru2025", "peru2026", "lima", "lima123", "lima2026", "essalud",
    "essalud1", "essalud123", "essalud2023", "essalud2024", "essalud2025", "essalud2026", "oiis", "oiis123",
    "oiis2024", "oiis2025", "oiis2026", "sire", "sire123", "sire2026", "winepi", "winepi123", "reportes",
    "reportes123", "epidemiologia", "salud", "salud123", "salud2026", "hospital", "hospital123", "red123",
    "qwerty", "qwerty1", "qwerty123", "qwertyuiop", "qazwsx", "asdfgh", "asdfghjkl", "zxcvbnm", "1q2w3e4r",
    "1qaz2wsx", "q1w2e3r4", "abc123", "abcd1234", "abcdef", "abcdefgh", "a1b2c3", "aaaaaa", "monkey",
    "dragon", "football", "futbol", "alianza", "alianzalima", "universitario", "cristal", "sportingcristal",
    "boca", "river", "barcelona", "realmadrid", "colocolo", "carlos", "maria", "jose", "luis", "juan",
    "enero2026", "febrero2026", "marzo2026", "abril2026", "mayo2026", "junio2026", "julio2026",
    "agosto2026", "setiembre2026", "septiembre2026", "octubre2026", "noviembre2026", "diciembre2026",
    "verano2026", "invierno2026", "primavera2026", "otono2026",
}

_COMUNES_LARGAS = tuple(sorted(c for c in {re.sub(r'[^a-z0-9]', '', c) for c in _COMUNES} if len(c) >= 7))

# Teclados y alfabetos para detectar secuencias (en los dos sentidos).
_SECUENCIAS = (
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1qaz2wsx3edc",
)

# Sustituciones típicas ("p@ssw0rd" -> "password") para detectar variantes simples.
_LEET = str.maketrans({"@": "a", "4": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s", "5": "s", "7": "t", "€": "e"})


# ============================================================
# NORMALIZACIÓN
# ============================================================

def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes."""
    return _sin_tildes(texto).lower()


def _solo_alfanum(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalizar(texto))


def _destransformar(texto: str) -> str:
    """Quita las sustituciones tipo leet y todo lo que no sea letra o número."""
    return re.sub(r"[^a-z0-9]", "", _normalizar(texto).translate(_LEET))


def _fragmentos_contexto(contexto: Iterable[str]) -> List[str]:
    """
    Trozos del usuario, la red, el nombre o el correo que no deben aparecer en
    la contraseña: el valor completo y cada palabra de 4 o más letras
    (del correo se usa solo la parte anterior a la arroba).
    """
    trozos = []
    for valor in contexto or []:
        v = str(valor or "").strip()
        if not v:
            continue
        if "@" in v:
            v = v.split("@", 1)[0]
        completo = _solo_alfanum(v)
        if len(completo) >= 4:
            trozos.append(completo)
        for palabra in re.split(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", v):
            p = _solo_alfanum(palabra)
            if len(p) >= 4 and not p.isdigit():
                trozos.append(p)
    return list(dict.fromkeys(trozos))


# ============================================================
# COMPROBACIONES
# ============================================================

def _tiene_secuencia(password: str, largo: int = 4) -> bool:
    """Cuatro o más caracteres seguidos de un alfabeto, número o teclado (hacia adelante o atrás)."""
    p = _normalizar(password)
    for base in _SECUENCIAS:
        for sec in (base, base[::-1]):
            for i in range(len(sec) - largo + 1):
                if sec[i:i + largo] in p:
                    return True
    return False


def _tiene_repeticion(password: str, largo: int = 3) -> bool:
    """El mismo carácter tres o más veces seguidas (aaa, 111) o un patrón corto repetido (abab, 1212)."""
    if re.search(r"(.)\1{%d,}" % (largo - 1), password):
        return True
    return bool(re.search(r"(..)\1{1,}", password)) and len(set(password)) <= 4


def _es_comun(password: str) -> bool:
    n = _normalizar(password)
    candidatos = {n, _solo_alfanum(password), _destransformar(password)}
    # También sin los dígitos o símbolos finales ("Clave2026!" -> "clave").
    base = re.sub(r"[^a-z]+$", "", _destransformar(password))
    if base:
        candidatos.add(base)
    sin_anio = re.sub(r"(19|20)\d{2}$", "", _destransformar(password))
    if sin_anio:
        candidatos.add(sin_anio)
    if any(c in _COMUNES for c in candidatos if c):
        return True
    # Una contraseña común escondida dentro de otra ("xPassword123y").
    variantes = (_solo_alfanum(password), _destransformar(password))
    return any(c in v for c in _COMUNES_LARGAS for v in variantes)


def _contiene_institucion(password: str) -> Optional[str]:
    plano = _destransformar(password)
    for palabra in _PALABRAS_INSTITUCION:
        if palabra in plano:
            return palabra
    return None


@dataclass
class Requisito:
    clave: str
    texto: str      # lo que se le pide a la persona
    motivo: str     # por qué se le pide
    cumple: bool


def evaluar(
    password: str,
    contexto: Sequence[str] = (),
    actual: Optional[str] = None,
) -> List[Requisito]:
    """
    Evalúa una contraseña contra todos los requisitos.

    contexto: usuario, red, nombre o correo de quien la usará (no deben
              aparecer dentro de la contraseña).
    actual:   contraseña vigente o temporal (la nueva debe ser distinta).
    """
    p = password or ""
    fragmentos = _fragmentos_contexto(contexto)
    plano = _destransformar(p)
    usa_contexto = any(f in plano for f in fragmentos)

    reqs = [
        Requisito(
            "largo", f"Al menos {LONGITUD_MINIMA} caracteres",
            "Cada carácter adicional multiplica el tiempo que tardaría un programa en adivinarla. "
            "Con menos de 10 caracteres se puede descubrir en minutos.",
            len(p) >= LONGITUD_MINIMA,
        ),
        Requisito(
            "largo_max", f"No más de {LONGITUD_MAXIMA} caracteres",
            "El sistema solo puede cifrar las primeras 72 posiciones (las tildes y la ñ cuentan doble); "
            "lo que sobre no protegería nada.",
            len(p) <= LONGITUD_MAXIMA and len(p.encode("utf-8")) <= BYTES_MAXIMOS,
        ),
        Requisito(
            "mayus_minus", "Mayúsculas y minúsculas",
            "Mezclar ambas obliga a probar muchas más combinaciones.",
            bool(re.search(r"[A-ZÁÉÍÓÚÜÑ]", p)) and bool(re.search(r"[a-záéíóúüñ]", p)),
        ),
        Requisito(
            "numero", "Al menos un número",
            "Los números amplían las combinaciones posibles y evitan que sea una simple palabra.",
            bool(re.search(r"\d", p)),
        ),
        Requisito(
            "simbolo", "Al menos un símbolo (por ejemplo ! @ # $ % &)",
            "Un símbolo la aleja de las palabras del diccionario que los programas prueban primero.",
            bool(re.search(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]", p)),
        ),
        Requisito(
            "comun", "No ser una contraseña muy usada",
            "Las contraseñas como «123456», «Essalud2026» o «admin123» están en las listas que se usan en los ataques. "
            "Son lo primero que se prueba.",
            bool(p) and not _es_comun(p),
        ),
        Requisito(
            "contexto", "No contener su usuario, su red ni palabras como «EsSalud» u «OIIS»",
            "Quien intente entrar probará primero datos que conoce: el nombre de la red, el usuario o la institución.",
            bool(p) and not usa_contexto and _contiene_institucion(p) is None,
        ),
        Requisito(
            "patron", "Sin secuencias ni repeticiones (1234, abcd, qwerty, aaaa)",
            "Los patrones fáciles de teclear también son fáciles de adivinar, aunque la contraseña sea larga.",
            bool(p) and not _tiene_secuencia(p) and not _tiene_repeticion(p),
        ),
    ]
    if actual is not None:
        reqs.append(Requisito(
            "distinta", "Distinta de la contraseña actual o temporal",
            "La contraseña temporal la conoce quien la entregó; si no se cambia por una nueva, deja de ser privada.",
            bool(p) and p != actual,
        ))
    return reqs


def validar(
    password: str,
    contexto: Sequence[str] = (),
    actual: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Devuelve (True, "") si la contraseña es aceptable o (False, mensaje) con
    todos los requisitos que no cumple.
    """
    if not password:
        return False, "Escriba una contraseña."
    faltan = [r.texto for r in evaluar(password, contexto, actual) if not r.cumple]
    if not faltan:
        return True, ""
    return False, "La contraseña no es suficientemente segura. Falta o debe corregir: " + "; ".join(faltan) + "."


def fuerza(password: str, contexto: Sequence[str] = (), actual: Optional[str] = None) -> Tuple[int, str]:
    """
    Nivel de 0 a 4 y su etiqueta, para mostrar una barra de fortaleza:
    0 Vacía, 1 Muy débil, 2 Débil, 3 Aceptable, 4 Fuerte.
    Una contraseña que no cumple todos los requisitos nunca pasa de «Débil».
    """
    if not password:
        return 0, "Sin escribir"
    reqs = evaluar(password, contexto, actual)
    cumplidos = sum(1 for r in reqs if r.cumple)
    todos = all(r.cumple for r in reqs)
    if todos:
        return (4, "Fuerte") if len(password) >= 14 else (3, "Aceptable")
    if cumplidos >= len(reqs) - 2:
        return 2, "Débil"
    return 1, "Muy débil"


# ============================================================
# GENERADOR
# ============================================================

# Sin caracteres que se confunden al leerlos (0/O, 1/l/I).
_MAYUS = "".join(c for c in string.ascii_uppercase if c not in "OI")
_MINUS = "".join(c for c in string.ascii_lowercase if c not in "ol")
_NUMS = "".join(c for c in string.digits if c not in "01")


def generar(longitud: int = 14) -> str:
    """
    Contraseña aleatoria que cumple la política (usa `secrets`, no `random`).
    Pensada para contraseñas temporales: es legible y se puede dictar.
    """
    longitud = max(longitud, LONGITUD_MINIMA + 2)
    todos = _MAYUS + _MINUS + _NUMS + SIMBOLOS_GENERADOR
    for _ in range(200):
        chars = [
            secrets.choice(_MAYUS), secrets.choice(_MINUS),
            secrets.choice(_NUMS), secrets.choice(SIMBOLOS_GENERADOR),
        ]
        chars += [secrets.choice(todos) for _ in range(longitud - len(chars))]
        secrets.SystemRandom().shuffle(chars)
        candidata = "".join(chars)
        if validar(candidata)[0]:
            return candidata
    raise RuntimeError("No se pudo generar una contraseña que cumpla la política.")


# ============================================================
# USUARIOS: SUGERENCIAS
# ============================================================

# Nombres de usuario demasiado genéricos: se rechazan aunque estén libres.
USUARIOS_GENERICOS = {
    "admin", "administrador", "administrator", "root", "usuario", "user", "test", "prueba", "demo",
    "oiis", "sire", "essalud", "invitado", "guest", "supervisor", "soporte", "operador", "sistema",
    "system", "superadmin", "super_admin", "admin1", "admin123", "usuario1", "temporal",
}


def usuario_demasiado_comun(usuario: str) -> bool:
    n = _solo_alfanum(usuario)
    return n in {_solo_alfanum(u) for u in USUARIOS_GENERICOS} or n.isdigit()


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalizar(texto))


def sugerir_usuarios(nombre_completo: str, email: str = "", ocupados: Iterable[str] = (), maximo: int = 4) -> List[str]:
    """
    Propone nombres de usuario libres a partir del nombre y del correo:
    inicial + apellido (mquispe), nombre.apellido, apellido + inicial, y la
    parte del correo anterior a la arroba. Si el usuario ya existe, agrega un
    número. Nunca devuelve uno ocupado ni demasiado genérico.
    """
    ocupados_n = {_slug(o) for o in ocupados}
    partes = [_slug(p) for p in re.split(r"\s+", str(nombre_completo or "").strip()) if _slug(p)]
    candidatos: List[str] = []
    if len(partes) >= 2:
        nombre, apellido = partes[0], partes[1] if len(partes) == 2 else partes[-2]
        candidatos += [
            f"{nombre[0]}{apellido}",
            f"{nombre}.{apellido}",
            f"{apellido}{nombre[0]}",
            f"{nombre}{apellido[0]}",
        ]
        if len(partes) >= 3:
            candidatos.append(f"{nombre[0]}{partes[-2]}{partes[-1][0]}")
    elif len(partes) == 1:
        candidatos.append(partes[0])
    local = str(email or "").split("@", 1)[0].strip().lower()
    if local:
        local = re.sub(r"[^a-z0-9._-]", "", _normalizar(local))
        if local:
            candidatos.append(local)

    salida: List[str] = []
    for c in candidatos:
        base = c.strip("._-")
        if len(base) < 3 or usuario_demasiado_comun(base):
            continue
        final = base
        n = 2
        while _slug(final) in ocupados_n:
            final = f"{base}{n}"
            n += 1
        if final not in salida:
            salida.append(final)
        if len(salida) >= maximo:
            break
    return salida
