# src/security.py
"""
Utilidades de hashing de contraseñas (bcrypt).

Antes esta misma logica estaba duplicada dentro de AuthManager
(src/auth.py). Se extrae aqui para que el nuevo login por red
(src/auth_red.py) la reutilice en vez de copiarla de nuevo.
"""

import logging

import bcrypt

# bcrypt solo procesa los primeros 72 BYTES de la contraseña (una letra con tilde o la «ñ» ocupan 2).
# La versión 5 de la librería rechaza lo que exceda en lugar de truncarlo en silencio.
MAX_BYTES_BCRYPT = 72

_log = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """
    Genera un hash bcrypt de la contraseña.
    bcrypt genera un salt aleatorio automáticamente (rounds=12,
    buen balance entre seguridad y rendimiento).
    Lanza ValueError si la contraseña supera los 72 bytes (la política de contraseñas ya lo impide).
    """
    if len(password.encode('utf-8')) > MAX_BYTES_BCRYPT:
        raise ValueError("La contraseña es demasiado larga (máximo 72 bytes, unos 64 caracteres).")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verificar_password(password: str, hash_almacenado: str) -> bool:
    """
    Verifica si la contraseña coincide con el hash bcrypt almacenado.
    """
    try:
        if not hash_almacenado:
            return False
        datos = password.encode('utf-8')
        if len(datos) > MAX_BYTES_BCRYPT:      # nunca pudo guardarse una contraseña así: no coincide
            return False
        return bcrypt.checkpw(datos, hash_almacenado.encode('utf-8'))
    except Exception as e:
        # Sin el mensaje de la excepción: solo el tipo de problema (por ejemplo un hash dañado en la base de datos).
        _log.warning("No se pudo verificar una contraseña (%s)", type(e).__name__)
        return False
