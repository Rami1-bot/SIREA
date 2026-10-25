# src/agentes/skills.py
"""
Skills del Agente Operativo: procedimientos de la OIIS escritos como
documentos (Markdown con encabezado de metadatos) en src/agentes/skills/.

Por qué así
-----------
* El "cómo se hace" no está escondido en el código ni en un prompt: está
  en un documento que lee y aprueba la Jefatura, y que cualquiera puede
  auditar en el repositorio (con su historial de cambios).
* Cada skill declara qué acciones puede proponer, qué herramientas puede
  consultar, su clasificación de uso y quién aprueba sus propuestas. El
  harness (agente_operativo.py) hace cumplir esa declaración: una acción
  fuera de la lista se descarta aunque el modelo la proponga.
* La huella SHA-256 del archivo identifica la versión exacta. Si el texto
  cambia, cambia la huella y la skill debe volver a pasar las
  evaluaciones antes de operar (compuerta en evals.py).
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional

CARPETA = Path(__file__).resolve().parent / "skills"
_ENCABEZADO = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


@dataclass(frozen=True)
class Skill:
    id: str
    nombre: str
    version: str
    nivel: str                      # permitido | restringido
    estado: str                     # APROBADA | BORRADOR | RETIRADA
    aprobada_por: str
    fecha_aprobacion: str
    disparador: str
    acciones_permitidas: tuple
    herramientas: tuple
    max_casos: int
    umbral_eval: float
    quien_aprueba: str              # ADMIN | SUPER_ADMIN (rol mínimo para aprobar sus propuestas)
    cuerpo: str
    huella: str
    ruta: str
    metadatos: Dict[str, str] = field(default_factory=dict)

    @property
    def huella_corta(self) -> str:
        return self.huella[:10]

    @property
    def etiqueta(self) -> str:
        return f"{self.id}@{self.version}#{self.huella_corta}"


def _lista(valor: str) -> tuple:
    return tuple(x.strip() for x in str(valor or "").strip("[] ").split(",") if x.strip())


def _parsear(ruta: Path) -> Skill:
    return parsear_texto(ruta.read_text(encoding="utf-8"), str(ruta), ruta.name)


def parsear_texto(texto: str, ruta: str = "(texto)", nombre: str = "skill") -> Skill:
    m = _ENCABEZADO.match(texto.replace("\r\n", "\n"))
    if not m:
        raise ValueError(f"La skill {nombre} no tiene encabezado de metadatos (--- ... ---).")
    meta: Dict[str, str] = {}
    for linea in m.group(1).splitlines():
        if ":" in linea and not linea.strip().startswith("#"):
            k, v = linea.split(":", 1)
            meta[k.strip()] = v.strip()
    faltan = [k for k in ("id", "nombre", "version", "nivel", "estado", "acciones_permitidas") if not meta.get(k)]
    if faltan:
        raise ValueError(f"La skill {nombre} no declara: {', '.join(faltan)}.")
    return Skill(
        id=meta["id"], nombre=meta["nombre"], version=meta["version"], nivel=meta["nivel"],
        estado=meta["estado"].upper(), aprobada_por=meta.get("aprobada_por", ""),
        fecha_aprobacion=meta.get("fecha_aprobacion", ""), disparador=meta.get("disparador", ""),
        acciones_permitidas=_lista(meta["acciones_permitidas"]), herramientas=_lista(meta.get("herramientas", "")),
        max_casos=int(meta.get("max_casos", "10") or 10), umbral_eval=float(meta.get("umbral_eval", "0.85") or 0.85),
        quien_aprueba=(meta.get("quien_aprueba") or "ADMIN").upper(),
        cuerpo=m.group(2).strip(), huella=hashlib.sha256(texto.encode("utf-8")).hexdigest(), ruta=ruta,
        metadatos=meta,
    )


# ------------------------------------------------------------
# Versiones aprendidas (sql/53): una versión APROBADA en la base reemplaza
# a la del repositorio. Se verifica su huella; si no coincide, se ignora.
# ------------------------------------------------------------

_CACHE_VERSIONES: Dict[str, object] = {"t": 0.0, "filas": []}
_TTL_VERSIONES = 15


def invalidar_cache() -> None:
    _CACHE_VERSIONES["t"] = 0.0


def _versiones_aprobadas() -> List[Dict]:
    if os.getenv("SIREA_SKILLS_SOLO_REPOSITORIO", "").strip() in ("1", "true"):
        return []
    if time.time() - float(_CACHE_VERSIONES["t"]) < _TTL_VERSIONES:
        return list(_CACHE_VERSIONES["filas"])  # type: ignore[arg-type]
    try:
        from src.db_manager import get_db_manager
        filas = (get_db_manager().supabase.table("agente_skill_versiones").select("*")
                 .eq("estado", "APROBADA").limit(50).execute().data or [])
    except Exception:
        filas = []
    _CACHE_VERSIONES.update(t=time.time(), filas=filas)
    return filas


def cargar_todas(carpeta: Optional[Path] = None) -> Dict[str, Skill]:
    """
    Todas las skills por id. Las que tienen errores se omiten (y se informan
    en errores_de_carga). Con la carpeta por defecto, si una skill tiene una
    versión aprendida APROBADA en la base, se usa esa.
    """
    out: Dict[str, Skill] = {}
    for ruta in sorted((carpeta or CARPETA).glob("*.md")):
        try:
            s = _parsear(ruta)
            out[s.id] = s
        except Exception:
            continue
    if carpeta is None:
        for fila in _versiones_aprobadas():
            try:
                s = parsear_texto(fila["texto"], f"base de datos · versión aprendida N.° {fila['id']}", fila["skill"])
                if s.id not in out or s.id != fila["skill"] or s.huella != fila.get("huella"):
                    continue      # solo reemplaza skills del repositorio y con su huella íntegra
                out[s.id] = replace(s, aprobada_por=str(fila.get("decidida_por") or ""),
                                    fecha_aprobacion=str(fila.get("decidida_at") or "")[:10],
                                    metadatos={**s.metadatos, "version_id": str(fila["id"]), "origen": "aprendida",
                                               "version_repositorio": out[s.id].version})
            except Exception:
                continue
    return out


def errores_de_carga(carpeta: Optional[Path] = None) -> List[str]:
    errores = []
    for ruta in sorted((carpeta or CARPETA).glob("*.md")):
        try:
            _parsear(ruta)
        except Exception as e:  # noqa: BLE001
            errores.append(f"{ruta.name}: {e}")
    return errores


def obtener(skill_id: str) -> Skill:
    s = cargar_todas().get(skill_id)
    if s is None:
        raise KeyError(f"No existe la skill «{skill_id}».")
    return s
