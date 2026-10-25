# src/agentes/evals.py
"""
Evaluaciones de las skills del Agente Operativo (compuerta de activación).

Qué son
-------
Casos de prueba ficticios (src/agentes/casos_eval/<skill>.json) que una persona
de la OIIS resolvió a mano: un expediente y lo que se espera que el agente
proponga (`alguno_de`) y lo que NO debe proponer nunca (`ninguno_de`).

Cada skill se evalúa en dos modos sobre los mismos casos:
  * ia      el agente real (skill + modelo + reglas de validación).
  * sin_ia  el modo degradado por reglas (lo que haría un script).
La diferencia entre ambos puntajes es la evidencia de cuánto aporta la IA.

Compuerta
---------
Una skill solo opera si su versión EXACTA (huella SHA-256) tiene una
evaluación en modo ia con puntaje >= umbral_eval de la skill. Si alguien
cambia el texto de la skill, cambia la huella y hay que volver a evaluar.
Fail-closed: sin tabla o sin dato, la skill no opera.

Los casos son ficticios: no se consulta la base (sin herramientas y sin
resolver destinatarios) y no se ejecuta ninguna acción.
"""

from __future__ import annotations

import copy
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.agentes.skills import Skill, obtener

CARPETA = Path(__file__).resolve().parent / "casos_eval"
TABLA = "agente_evals"


def _t():
    from src.db_manager import get_db_manager
    return get_db_manager().supabase.table(TABLA)


# ------------------------------------------------------------
# casos
# ------------------------------------------------------------

def casos(skill_id: str) -> List[Dict]:
    ruta = CARPETA / f"{skill_id}.json"
    if not ruta.exists():
        return []
    return list(json.loads(ruta.read_text(encoding="utf-8")).get("casos") or [])


def _materializar(exp: Dict) -> Dict:
    """Convierte 'hace_horas' de las acciones previas en fechas reales (relativas a ahora)."""
    e = copy.deepcopy(exp)
    ahora = datetime.now(timezone.utc)
    for a in e.get("acciones_previas") or []:
        h = a.pop("hace_horas", None)
        if h is not None:
            f = (ahora - timedelta(hours=float(h))).isoformat()
            a["creada_at"] = f
            if a.get("estado") == "EJECUTADA":
                a["ejecutada_at"] = f
    return e


def calificar(caso: Dict, res: Dict) -> Tuple[bool, List[str], str]:
    """(aprobado, tipos_obtenidos, motivo)."""
    tipos = sorted({a["tipo"] for a in res.get("aceptadas") or []})
    if res.get("sin_accion") or not tipos:
        tipos = sorted(set(tipos) | {"SIN_ACCION"})
    esp = caso.get("espera") or {}
    alguno = set(esp.get("alguno_de") or [])
    ninguno = set(esp.get("ninguno_de") or [])
    prohibidos = ninguno.intersection(tipos)
    if prohibidos:
        return False, tipos, f"propuso lo que no debía: {', '.join(sorted(prohibidos))}"
    if alguno and not alguno.intersection(tipos):
        return False, tipos, f"se esperaba {' o '.join(sorted(alguno))}"
    if esp.get("sin_comparar"):   # SIREA 3.2: el mensaje a la red no la compara ni le recuerda su historial
        for a in res.get("aceptadas") or []:
            aviso = (a.get("payload") or {}).get("aviso_mensaje")
            if a.get("tipo") == "RECORDATORIO_RED" and aviso:
                return False, tipos, "el mensaje no cumplió las reglas de tono: " + str(aviso)[:160]
    return True, tipos, "ok"


# ------------------------------------------------------------
# ejecución
# ------------------------------------------------------------

def correr(skill_id: str, modo: str = "ia", usuario: str = "SYSTEM", guardar: bool = True,
           pausa_s: float = 0.0) -> Dict[str, Any]:
    """
    Corre los casos de una skill en el modo indicado ('ia' o 'sin_ia').
    No ejecuta acciones ni consulta datos reales. Guarda el resultado en
    agente_evals (si guardar=True) y lo devuelve.
    """
    from src.agentes.agente_operativo import resolver_caso
    if modo not in ("ia", "sin_ia"):
        raise ValueError("modo debe ser 'ia' o 'sin_ia'")
    skill = obtener(skill_id)
    lista = casos(skill_id)
    if not lista:
        raise RuntimeError(f"La skill {skill_id} no tiene casos de evaluación.")
    detalle, aprobados, proveedores = [], 0, set()
    for i, c in enumerate(lista):
        exp = _materializar(c["expediente"])
        try:
            res = resolver_caso(skill, exp, usar_ia=(modo == "ia"), con_herramientas=False, preparar=False)
        except Exception as e:  # noqa: BLE001
            res = {"aceptadas": [], "sin_accion": [], "descartadas": [], "origen": "error",
                   "razonamiento": "", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        if modo == "ia" and res.get("origen") != "ia":
            ok, tipos, motivo = False, [], f"la IA no respondió ({res.get('error') or 'sin detalle'})"
        else:
            ok, tipos, motivo = calificar(c, res)
        if res.get("proveedor"):
            proveedores.add(f"{res['proveedor']}:{res.get('modelo')}")
        aprobados += int(ok)
        detalle.append({"id": c.get("id"), "titulo": c.get("titulo"), "por_que": c.get("por_que"),
                        "esperado": (c.get("espera") or {}).get("alguno_de"),
                        "prohibido": (c.get("espera") or {}).get("ninguno_de"),
                        "obtenido": tipos, "aprobado": ok, "motivo": motivo,
                        "razonamiento": str(res.get("razonamiento") or "")[:400],
                        "descartadas": [f"{t}: {m}" for t, m in (res.get("descartadas") or [])][:5]})
        if pausa_s and i < len(lista) - 1:
            time.sleep(pausa_s)
    total = len(lista)
    out = {"skill": skill.id, "skill_version": skill.version, "skill_hash": skill.huella, "usuario": usuario,
           "modo": modo, "proveedor": ", ".join(sorted(proveedores)) or None, "total": total,
           "aprobados": aprobados, "puntaje": round(aprobados / total, 4), "detalle": detalle}
    if guardar:
        try:
            fila = _t().insert(json.loads(json.dumps(out, ensure_ascii=False, default=str))).execute().data
            if fila:
                out["id"] = fila[0].get("id")
                out["fecha"] = fila[0].get("fecha")
        except Exception as e:  # noqa: BLE001
            out["error_guardado"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


def correr_ambos(skill_id: str, usuario: str = "SYSTEM", pausa_s: float = 0.0) -> Dict[str, Dict]:
    """Primero sin IA (instantáneo) y luego con IA, sobre los mismos casos."""
    return {"sin_ia": correr(skill_id, "sin_ia", usuario), "ia": correr(skill_id, "ia", usuario, pausa_s=pausa_s)}


# ------------------------------------------------------------
# lectura y compuerta
# ------------------------------------------------------------

def ultima(skill: Skill, modo: str = "ia") -> Optional[Dict]:
    try:
        filas = (_t().select("*").eq("skill", skill.id).eq("skill_hash", skill.huella).eq("modo", modo)
                 .order("fecha", desc=True).limit(1).execute().data or [])
        return filas[0] if filas else None
    except Exception:
        return None


def historial(skill_id: Optional[str] = None, limite: int = 30) -> List[Dict]:
    try:
        q = _t().select("id,fecha,skill,skill_version,skill_hash,usuario,modo,proveedor,total,aprobados,puntaje")
        if skill_id:
            q = q.eq("skill", skill_id)
        return q.order("fecha", desc=True).limit(limite).execute().data or []
    except Exception:
        return []


def habilitada(skill: Skill) -> Tuple[bool, str]:
    """¿Puede operar esta versión exacta de la skill? (bool, motivo legible)."""
    u = ultima(skill, "ia")
    if not u:
        return False, (f"La versión {skill.version} (#{skill.huella_corta}) de «{skill.nombre}» todavía no tiene "
                       "evaluación con IA. Corra las evaluaciones en la pestaña Evaluaciones.")
    puntaje = float(u.get("puntaje") or 0)
    if puntaje < skill.umbral_eval:
        return False, (f"La última evaluación obtuvo {puntaje:.0%} y la skill exige {skill.umbral_eval:.0%}. "
                       "Revise los casos fallidos y la redacción de la skill.")
    return True, f"Evaluada: {puntaje:.0%} (umbral {skill.umbral_eval:.0%})."


def alguna_habilitada() -> Tuple[bool, str]:
    from src.agentes.skills import cargar_todas
    motivos = []
    for s in cargar_todas().values():
        if s.estado != "APROBADA":
            continue
        ok, m = habilitada(s)
        if ok:
            return True, m
        motivos.append(m)
    return False, (motivos[0] if motivos else "No hay skills aprobadas.")
