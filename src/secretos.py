# src/secretos.py
"""
Carga de secretos de SIREA desde `.streamlit/secrets.toml` (SIREA 3.5).

Orden de prioridad (el primero que tenga el valor gana):
  1. Variables de entorno reales del sistema / contenedor / Streamlit Cloud.
  2. `.streamlit/secrets.toml` (o la ruta de SIREA_SECRETS_PATH).
  3. `.env` (respaldo heredado de SIRE; se carga después en src/config.py sin pisar nada).

Por qué se lee el archivo aquí y no con `st.secrets`:
  * src/config.py lee todo con os.getenv() al importarse, ANTES de que Streamlit
    exponga los secretos como variables de entorno;
  * el proceso programado (python -m src.programador) no corre dentro de Streamlit.

Formato admitido:
  * claves en la raíz:            SUPABASE_URL = "https://…"
  * secciones (solo para ordenar): [supabase]  URL = "…"  →  SUPABASE_URL
    (el nombre final es SECCION_CLAVE, salvo que la clave ya empiece por la sección)
  * [gcp_service_account]: la cuenta de servicio de Google tal cual; se convierte en
    GOOGLE_CREDENTIALS_JSON (src/config.py la escribe en credentials/ si hace falta).

Nunca imprime valores: solo dice qué archivo usó y cuántas claves cargó.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SECCION_GOOGLE = "gcp_service_account"


def _leer_toml(ruta: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
        with open(ruta, "rb") as f:
            return tomllib.load(f)
    except ModuleNotFoundError:  # Python 3.10: el paquete «toml» viene con Streamlit
        import toml
        return toml.load(str(ruta))


def _texto(valor: Any) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (list, tuple)):
        return ",".join(_texto(v) for v in valor)
    return str(valor)


def google_completa(sec: Dict[str, Any]) -> bool:
    """True si la sección [gcp_service_account] tiene una llave real (no la de la plantilla)."""
    clave = str(sec.get("private_key") or "")
    return ("BEGIN PRIVATE KEY" in clave and "\n...\n" not in clave and len(clave) > 200
            and "@" in str(sec.get("client_email") or ""))


def aplanar(datos: Dict[str, Any]) -> Dict[str, str]:
    """Convierte el contenido del TOML en {VARIABLE: texto}."""
    plano: Dict[str, str] = {}
    for clave, valor in datos.items():
        if isinstance(valor, dict):
            if clave.lower() == SECCION_GOOGLE:
                if google_completa(valor):          # la plantilla sin llenar se ignora
                    plano["GOOGLE_CREDENTIALS_JSON"] = json.dumps(dict(valor), ensure_ascii=False, separators=(",", ":"))
                continue
            prefijo = clave.upper()
            for k, v in valor.items():
                if isinstance(v, dict):
                    continue
                k_may = str(k).upper()
                nombre = k_may if k_may.startswith(prefijo + "_") or k_may == prefijo else f"{prefijo}_{k_may}"
                plano[nombre] = _texto(v)
        else:
            plano[str(clave)] = _texto(valor)
    return plano


def ruta_secrets(base_dir: Path) -> Path:
    personalizada = os.getenv("SIREA_SECRETS_PATH", "").strip()
    return Path(personalizada) if personalizada else base_dir / ".streamlit" / "secrets.toml"


def cargar(base_dir: Path) -> Tuple[Optional[Path], int]:
    """
    Pone en os.environ las claves de secrets.toml que no estén ya definidas.
    Devuelve (archivo usado o None, cantidad de claves cargadas).
    """
    ruta = ruta_secrets(base_dir)
    if not ruta.is_file():
        return None, 0
    try:
        plano = aplanar(_leer_toml(ruta))
    except Exception as e:  # noqa: BLE001  un TOML mal escrito no debe tumbar el arranque sin explicar
        print(f"[secretos] No se pudo leer {ruta.name}: {type(e).__name__}: {e}. Revise comillas y signos «=».")
        return ruta, 0
    n = 0
    for k, v in plano.items():
        if k and v != "" and k not in os.environ:
            os.environ[k] = v
            n += 1
    return ruta, n


def estado(base_dir: Path) -> Dict[str, Any]:
    """Resumen para «Salud del sistema» (sin valores)."""
    ruta = ruta_secrets(base_dir)
    env = base_dir / ".env"
    return {"secrets_toml": ruta.is_file(), "ruta": str(ruta), "env": env.is_file()}
