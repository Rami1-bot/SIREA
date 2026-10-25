# src/agentes/memoria.py
"""
Memoria por red del Agente Operativo (tabla agente_memoria_red, sql/52).

Notas breves que el agente lee en cada corrida ("la red avisó que envía
los lunes por conectividad"). Las escribe una persona desde el panel o el
propio agente mediante una acción NOTA_MEMORIA que una persona aprobó.
Vencen solas (vigente_hasta). Sin la tabla, el agente opera sin memoria.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

TABLA = "agente_memoria_red"


def _t():
    from src.db_manager import get_db_manager
    return get_db_manager().supabase.table(TABLA)


def disponible() -> bool:
    try:
        _t().select("id").limit(1).execute()
        return True
    except Exception:
        return False


def vigentes(red: Optional[str] = None, limite: int = 200) -> List[Dict]:
    try:
        q = _t().select("*").eq("activa", True)
        if red:
            q = q.eq("red", red)
        filas = q.order("creada_at", desc=True).limit(limite).execute().data or []
    except Exception:
        return []
    hoy = date.today().isoformat()
    return [f for f in filas if not f.get("vigente_hasta") or str(f["vigente_hasta"])[:10] >= hoy]


def agregar(red: str, nota: str, fuente: str = "humano", creada_por: str = "SYSTEM",
            vigencia_dias: int = 60, accion_id: Optional[int] = None) -> bool:
    from src.agentes import guardrails
    if guardrails.detectar_pii(str(nota or "")):      # se rechaza (no se guarda redactada)
        return False
    nota = guardrails.sanitizar_texto_usuario(str(nota or "")).strip()[:300]
    if not red or len(nota) < 5:
        return False
    try:
        _t().insert({"red": red, "nota": nota, "fuente": fuente, "creada_por": creada_por, "accion_id": accion_id,
                     "vigente_hasta": (date.today() + timedelta(days=max(1, int(vigencia_dias)))).isoformat(),
                     "activa": True}).execute()
        return True
    except Exception:
        return False


def desactivar(nota_id, usuario: str) -> bool:
    try:
        r = _t().update({"activa": False}).eq("id", nota_id).execute()
        from src.db_manager import get_db_manager
        get_db_manager().registrar_log(usuario=usuario, accion="AGENTE_MEMORIA_DESACTIVAR", detalle=f"nota {nota_id}")
        return bool(r.data)
    except Exception:
        return False
