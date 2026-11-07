#!/usr/bin/env python3
"""
SIREA · Robot de actividad («mantener despierto»)

Supabase (plan gratuito) PAUSA el proyecto si pasa ~7 días con poca actividad en la base de datos;
entonces SIREA no puede leer ni guardar y aparece «getaddrinfo failed». Este robot hace una consulta
mínima a la base para que eso no pase. No lee ni modifica datos: llama a la función `sirea_latido()`,
que solo devuelve la hora del servidor (sql/56_latido_robot.sql).

Opcionalmente también visita la dirección web de SIREA (SIREA_APP_URL) por si está en un servicio
que «duerme» la aplicación cuando nadie la usa.

Solo usa la biblioteca estándar de Python: corre en Windows, Linux o GitHub Actions sin instalar nada.
Respeta el proxy de la institución si HTTPS_PROXY está definido.

Uso:
    python scripts/mantener_activo.py            # una revisión (para el Programador de tareas o un cron)
    python scripts/mantener_activo.py --detalle  # además muestra de dónde leyó la configuración

Configuración (en este orden): variables de entorno → .streamlit/secrets.toml → .env
    SUPABASE_URL        https://xxxx.supabase.co
    SIREA_LATIDO_KEY    clave PÚBLICA (anon / sb_publishable_…) — recomendada para el robot
    SUPABASE_KEY        se usa si no hay SIREA_LATIDO_KEY
    SIREA_APP_URL       (opcional) dirección pública de SIREA

Salida: 0 = todo despierto · 1 = el servidor respondió con error · 2 = no se llega al servidor
(proyecto pausado, sin internet o dirección mal escrita).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent
CLAVES = ("SUPABASE_URL", "SIREA_LATIDO_KEY", "SUPABASE_ANON_KEY", "SUPABASE_KEY", "SIREA_APP_URL")
TIEMPO = 25


# ------------------------------------------------------------------ configuración
def _leer_secrets(ruta: Path) -> Dict[str, str]:
    if not ruta.exists():
        return {}
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover
        return {}
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}
    plano: Dict[str, str] = {}
    for k, v in datos.items():
        if isinstance(v, (str, int, float)) and str(v).strip():
            plano[k] = str(v).strip()
        elif isinstance(v, dict):                       # [supabase] url = ... → SUPABASE_URL
            for k2, v2 in v.items():
                if isinstance(v2, (str, int, float)) and str(v2).strip():
                    plano[f"{k}_{k2}".upper()] = str(v2).strip()
    return plano


def _leer_env(ruta: Path) -> Dict[str, str]:
    if not ruta.exists():
        return {}
    plano: Dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            plano[k.strip()] = v
    return plano


def cargar_config(base: Path = BASE) -> Tuple[Dict[str, str], Dict[str, str]]:
    """(valores, origen de cada valor)."""
    secrets_path = Path(os.getenv("SIREA_SECRETS_PATH", "") or base / ".streamlit" / "secrets.toml")
    fuentes = (("variable de entorno", dict(os.environ)), ("secrets.toml", _leer_secrets(secrets_path)),
               (".env", _leer_env(base / ".env")))
    valores: Dict[str, str] = {}
    origen: Dict[str, str] = {}
    for clave in CLAVES:
        for nombre, datos in fuentes:
            v = (datos.get(clave) or "").strip()
            if v:
                valores[clave], origen[clave] = v.strip('"').strip("'"), nombre
                break
    if "HTTPS_PROXY" not in os.environ:                 # proxy declarado en secrets.toml
        proxy = _leer_secrets(secrets_path).get("HTTPS_PROXY")
        if proxy:
            os.environ["HTTPS_PROXY"] = proxy
    return valores, origen


# ------------------------------------------------------------------ consultas
def _pedir(url: str, metodo: str = "GET", cabeceras: Optional[Dict[str, str]] = None,
           cuerpo: Optional[bytes] = None) -> Tuple[int, str]:
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(req, timeout=TIEMPO) as r:
            return r.status, r.read(400).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "ignore")


def _resuelve(host: str) -> Optional[str]:
    if any(os.getenv(v) for v in ("HTTPS_PROXY", "https_proxy")):
        return None                                      # con proxy, el nombre lo resuelve el proxy
    try:
        socket.getaddrinfo(host, 443)
        return None
    except OSError as e:
        return str(e)


def latir_supabase(url: str, clave: str) -> Tuple[int, str]:
    """(código, mensaje). 0 despierto · 1 respondió con error · 2 no se llega."""
    host = urlparse(url).hostname or ""
    if not host:
        return 2, f"SUPABASE_URL no es una dirección válida: «{url[:60]}»"
    error_dns = _resuelve(host)
    if error_dns:
        return 2, (f"No se encuentra «{host}» ({error_dns}). Lo más probable: el proyecto está PAUSADO. "
                   "Reactívelo en supabase.com → su proyecto → «Resume project». Si no, revise internet o el proxy.")
    cab = {"apikey": clave, "Authorization": f"Bearer {clave}", "Content-Type": "application/json",
           "User-Agent": "SIREA-robot-actividad"}
    try:
        estado, texto = _pedir(url.rstrip("/") + "/rest/v1/rpc/sirea_latido", "POST", cab, b"{}")
        if 200 <= estado < 300:
            return 0, f"Supabase despierto (hora del servidor {texto.strip()[:40]})"
        if estado == 404:   # aún no se creó la función: una lectura mínima también cuenta como actividad
            estado, texto = _pedir(url.rstrip("/") + "/rest/v1/configuracion?select=clave&limit=1", "GET", cab)
            if estado < 500:
                return 0, (f"Supabase despierto (respuesta {estado}). Sugerencia: ejecute sql/56_latido_robot.sql "
                           "para que el robot use la función de latido.")
        if estado in (401, 403):
            return 1, f"Supabase respondió {estado}: la clave no es válida para este proyecto."
        if estado >= 500:
            return 1, f"Supabase respondió {estado}: el proyecto puede estar reactivándose; reintente en unos minutos."
        return 0, f"Supabase respondió {estado}"
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return 2, f"No se pudo conectar con Supabase: {e}"


def visitar_app(url: str) -> Tuple[int, str]:
    try:
        estado, _ = _pedir(url, "GET", {"User-Agent": "SIREA-robot-actividad"})
        return (0 if estado < 500 else 1), f"SIREA web respondió {estado}"
    except Exception as e:
        return 1, f"SIREA web no respondió: {e}"


def _registrar(lineas) -> None:
    carpeta = BASE / "storage" / "logs"
    try:
        if carpeta.is_dir():
            with open(carpeta / "mantener_activo.log", "a", encoding="utf-8") as f:
                for l in lineas:
                    f.write(l + "\n")
    except Exception:
        pass


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cfg, origen = cargar_config()
    marca = datetime.now().strftime("%Y-%m-%d %H:%M")
    lineas = []
    url = cfg.get("SUPABASE_URL", "")
    clave = cfg.get("SIREA_LATIDO_KEY") or cfg.get("SUPABASE_ANON_KEY") or cfg.get("SUPABASE_KEY") or ""
    if "--detalle" in argv:
        for k in CLAVES:
            if k in cfg:
                print(f"  {k}: leído de {origen[k]}")
    if not url or not clave:
        lineas.append(f"{marca} ✗ Falta SUPABASE_URL o la clave (SIREA_LATIDO_KEY / SUPABASE_KEY).")
        codigo = 1
    else:
        codigo, msg = latir_supabase(url, clave)
        lineas.append(f"{marca} {'✓' if codigo == 0 else '✗'} {msg}")
    if cfg.get("SIREA_APP_URL"):
        c2, m2 = visitar_app(cfg["SIREA_APP_URL"])
        lineas.append(f"{marca} {'✓' if c2 == 0 else '✗'} {m2}")
        codigo = codigo or c2
    for l in lineas:
        print(l, flush=True)
    _registrar(lineas)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
