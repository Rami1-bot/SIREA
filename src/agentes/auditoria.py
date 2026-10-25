# src/agentes/auditoria.py
"""
Registro inmutable de auditoría de los agentes de IA.

Cumple el "Control Mínimo Exigible" del Riesgo 3 (Tabla 3.1) -- condición
de parada obligatoria del proyecto -- y el criterio "Logs Auditables" de la
Tabla 4.2.1: captura de usuario, hora, consulta, modelo, borrador y
aprobación de TODA interacción con un agente, incluidas las bloqueadas por
los guardrails y los cambios de estado (kill-switch).

Dónde se guarda
---------------
Tabla `auditoria_agentes_ia` en Supabase (ver sql/001_auditoria_agentes_ia.sql).
La tabla es de solo inserción: un trigger rechaza UPDATE/DELETE y las
políticas RLS solo permiten INSERT y SELECT. `limpiar_logs_antiguos()` de
db_manager NO la toca.

Si la tabla aún no existe (entorno sin migrar), se cae al log general
(`logs`, acción `AGENTE_IA_*`) para no perder la trazabilidad, y se deja
constancia en consola de que falta la migración.

Qué NO se guarda
----------------
Nunca datos personales: la consulta y la respuesta pasan por
`guardrails.redactar_pii` antes de persistirse. El usuario registrado es el
identificador institucional del administrador (ya existe en `logs`).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.agentes import guardrails

TABLA_AUDITORIA = "auditoria_agentes_ia"

# Eventos normalizados (se filtran en el visor del panel).
EVENTO_CONSULTA = "CONSULTA"              # pregunta al orquestador y su respuesta
EVENTO_BORRADOR = "BORRADOR"              # resumen o recomendación generada (pendiente)
EVENTO_APROBACION = "APROBACION"          # humano aprobó un borrador
EVENTO_RECHAZO = "RECHAZO"                # humano rechazó un borrador
EVENTO_ENVIO = "ENVIO"                    # notificación efectivamente enviada tras aprobación
EVENTO_BLOQUEO = "BLOQUEO_GUARDRAIL"      # entrada o salida bloqueada
EVENTO_ESTADO = "CAMBIO_ESTADO"           # kill-switch / ciclo de vida
EVENTO_ERROR = "ERROR"                    # fallo técnico (proveedor, red)

AGENTE_INVESTIGADOR = "investigador"     # Asistente 1: diagnóstico de cumplimiento (solo lectura)
AGENTE_RESUMEN = "resumen"               # retirado en SIREA 3.0 (se conserva por la auditoría histórica)
AGENTE_CONTROL = "control"               # retirado en SIREA 3.0 (se conserva por la auditoría histórica)
AGENTE_SOLICITUDES = "solicitudes"       # retirado en SIREA 3.0 (se conserva por la auditoría histórica)
AGENTE_SOPORTE_REDES = "soporte_redes"   # evaluado y no construido (solo catálogo)
AGENTE_OPERATIVO = "operativo"           # SIREA 3.0: Agente Operativo (skills, cola de acciones, memoria)
AGENTE_SISTEMA = "sistema"
# Compatibilidad con el código y las pruebas heredadas de SIGRE.
AGENTE_ORQUESTADOR = AGENTE_INVESTIGADOR
AGENTE_SEGUIMIENTO = AGENTE_CONTROL

_MAX_TEXTO = 6000


@dataclass
class RegistroAuditoria:
    usuario: str
    rol: str
    agente: str
    evento: str
    modelo: Optional[str] = None
    entrada: Optional[str] = None
    salida: Optional[str] = None
    herramientas: List[str] = field(default_factory=list)
    guardrail_categoria: Optional[str] = None
    guardrail_motivo: Optional[str] = None
    observaciones: List[str] = field(default_factory=list)
    aprobado_por: Optional[str] = None
    referencia: Optional[str] = None      # id del borrador al que se refiere una aprobación/envío
    duracion_ms: Optional[int] = None
    anio: Optional[int] = None
    semana: Optional[int] = None
    fecha: Optional[str] = None

    def como_fila(self) -> Dict[str, Any]:
        d = asdict(self)
        d["entrada"] = _preparar_texto(d["entrada"])
        d["salida"] = _preparar_texto(d["salida"])
        d["entrada_hash"] = guardrails.hash_texto(self.entrada or "")
        d["fecha"] = self.fecha or datetime.now(timezone.utc).isoformat()
        return d


def _preparar_texto(texto: Optional[str]) -> Optional[str]:
    if texto is None:
        return None
    t = guardrails.redactar_pii(str(texto))
    return t if len(t) <= _MAX_TEXTO else t[:_MAX_TEXTO] + "…[truncado]"


def _usuario_actual() -> Dict[str, str]:
    """
    Obtiene usuario y rol del administrador logueado desde la sesión de
    Streamlit. Si no hay sesión (tests, scripts), devuelve 'SYSTEM'.
    """
    try:
        import streamlit as st  # import tardío: los tests no requieren streamlit
        info = st.session_state.get("admin_usuario")
        if isinstance(info, dict):
            return {
                "usuario": str(info.get("usuario") or "SYSTEM"),
                "rol": str(info.get("rol") or "ADMIN"),
            }
    except Exception:
        pass
    return {"usuario": "SYSTEM", "rol": "SYSTEM"}


_aviso_migracion_mostrado = False


def registrar(registro: RegistroAuditoria) -> Optional[str]:
    """
    Persiste el registro. Devuelve el id de la fila insertada (str) o None.
    Nunca lanza: la auditoría no debe tumbar la operación, pero SÍ deja
    rastro en consola si falla.
    """
    global _aviso_migracion_mostrado
    fila = registro.como_fila()
    try:
        from src.db_manager import get_db_manager
        db = get_db_manager()
        try:
            resultado = db.supabase.table(TABLA_AUDITORIA).insert(fila).execute()
            if resultado.data:
                return str(resultado.data[0].get("id"))
            return None
        except Exception as e:
            # Tabla inexistente u otro error: fallback al log general.
            if not _aviso_migracion_mostrado:
                print(
                    f"[auditoria_ia] No se pudo escribir en '{TABLA_AUDITORIA}' ({e}). "
                    "Ejecuta sql/50_auditoria_agentes_ia.sql en Supabase. "
                    "Usando la tabla 'logs' como respaldo."
                )
                _aviso_migracion_mostrado = True
            detalle = json.dumps(
                {k: v for k, v in fila.items() if k not in ("usuario", "rol")},
                ensure_ascii=False, default=str,
            )
            db.registrar_log(
                usuario=fila["usuario"],
                accion=f"AGENTE_IA_{registro.evento}",
                detalle=detalle[:4000],
            )
            return None
    except Exception as e:
        print(f"[auditoria_ia] Fallo total al registrar auditoría: {e}")
        return None


# ------------------------------------------------------------
# Helpers de alto nivel usados por los agentes y el panel
# ------------------------------------------------------------

def registrar_consulta(
    agente: str,
    entrada: str,
    salida: str,
    modelo: Optional[str],
    herramientas: Optional[List[str]] = None,
    observaciones: Optional[List[str]] = None,
    duracion_ms: Optional[int] = None,
    anio: Optional[int] = None,
    semana: Optional[int] = None,
    evento: str = EVENTO_CONSULTA,
    referencia: Optional[str] = None,
) -> Optional[str]:
    u = _usuario_actual()
    return registrar(RegistroAuditoria(
        usuario=u["usuario"], rol=u["rol"], agente=agente, evento=evento,
        modelo=modelo, entrada=entrada, salida=salida,
        herramientas=list(herramientas or []), observaciones=list(observaciones or []),
        duracion_ms=duracion_ms, anio=anio, semana=semana, referencia=referencia,
    ))


def registrar_bloqueo(agente: str, entrada: str, resultado: guardrails.ResultadoGuardrail,
                      modelo: Optional[str] = None, salida: Optional[str] = None) -> Optional[str]:
    u = _usuario_actual()
    return registrar(RegistroAuditoria(
        usuario=u["usuario"], rol=u["rol"], agente=agente, evento=EVENTO_BLOQUEO,
        modelo=modelo, entrada=entrada, salida=salida,
        guardrail_categoria=resultado.categoria, guardrail_motivo=resultado.motivo,
        observaciones=list(resultado.observaciones),
    ))


def registrar_decision_humana(agente: str, referencia: Optional[str], aprobado: bool,
                              comentario: Optional[str] = None,
                              salida: Optional[str] = None,
                              anio: Optional[int] = None, semana: Optional[int] = None,
                              modelo: Optional[str] = None) -> Optional[str]:
    """Aprobación o rechazo explícito de un borrador por el responsable (HITL)."""
    u = _usuario_actual()
    return registrar(RegistroAuditoria(
        usuario=u["usuario"], rol=u["rol"], agente=agente,
        evento=EVENTO_APROBACION if aprobado else EVENTO_RECHAZO,
        entrada=comentario, salida=salida, referencia=referencia, modelo=modelo,
        aprobado_por=u["usuario"] if aprobado else None, anio=anio, semana=semana,
    ))


def ultima_aprobacion(agente: str, anio: Optional[int] = None, semana: Optional[int] = None,
                      referencia_prefijo: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Última APROBACION de un agente (opcionalmente de una semana o con un prefijo de referencia)."""
    try:
        from src.db_manager import get_db_manager
        q = get_db_manager().supabase.table(TABLA_AUDITORIA).select("*").eq("agente", agente).eq("evento", EVENTO_APROBACION)
        if anio is not None:
            q = q.eq("anio", int(anio))
        if semana is not None:
            q = q.eq("semana", int(semana))
        if referencia_prefijo:
            q = q.like("referencia", f"{referencia_prefijo}%")
        filas = q.order("fecha", desc=True).limit(1).execute().data or []
        return filas[0] if filas else None
    except Exception:
        return None


def registrar_envio(agente: str, referencia: Optional[str], red: str, exito: bool,
                    detalle: str, mensaje_final: str) -> Optional[str]:
    """Envío efectivo de una notificación (siempre posterior a una aprobación)."""
    u = _usuario_actual()
    return registrar(RegistroAuditoria(
        usuario=u["usuario"], rol=u["rol"], agente=agente, evento=EVENTO_ENVIO,
        entrada=f"red={red}; exito={exito}; {detalle}", salida=mensaje_final,
        referencia=referencia, aprobado_por=u["usuario"],
    ))


def registrar_cambio_estado(agente: str, estado_anterior: str, estado_nuevo: str,
                            justificacion: str) -> Optional[str]:
    u = _usuario_actual()
    return registrar(RegistroAuditoria(
        usuario=u["usuario"], rol=u["rol"], agente=agente, evento=EVENTO_ESTADO,
        entrada=f"{estado_anterior} -> {estado_nuevo}", salida=justificacion,
    ))


def registrar_error(agente: str, entrada: Optional[str], error: BaseException,
                    modelo: Optional[str] = None) -> Optional[str]:
    u = _usuario_actual()
    return registrar(RegistroAuditoria(
        usuario=u["usuario"], rol=u["rol"], agente=agente, evento=EVENTO_ERROR,
        modelo=modelo, entrada=entrada, salida=f"{type(error).__name__}: {error}",
    ))


def obtener_registros(limite: int = 100, agente: Optional[str] = None,
                      evento: Optional[str] = None, desde: Optional[str] = None,
                      usuario: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lee los últimos registros para el visor del panel (solo lectura). `desde`: fecha ISO."""
    try:
        from src.db_manager import get_db_manager
        db = get_db_manager()

        def _consulta():
            q = db.supabase.table(TABLA_AUDITORIA).select("*")
            if agente:
                q = q.eq("agente", agente)
            if evento:
                q = q.eq("evento", evento)
            if desde:
                q = q.gte("fecha", desde)
            if usuario:
                q = q.eq("usuario", usuario)
            return q.order("fecha", desc=True)

        # Supabase devuelve hasta 1000 filas por consulta: más que eso se pide en páginas
        out: List[Dict[str, Any]] = []
        for ini in range(0, max(1, limite), 1000):
            fin = min(ini + 1000, limite) - 1
            pagina = _consulta().range(ini, fin).execute().data or []
            out.extend(pagina)
            if len(pagina) < fin - ini + 1:
                break
        return out
    except Exception:
        # Fallback: registros de respaldo en 'logs'
        try:
            from src.db_manager import get_db_manager
            logs = get_db_manager().obtener_logs(limit=limite)
            return [l for l in logs if str(l.get("accion", "")).startswith("AGENTE_IA_")]
        except Exception:
            return []


def funcion_de(registro: Dict[str, Any]) -> str:
    """Para el Historial de IA: en qué parte de SIREA se usó la IA (en palabras simples)."""
    agente = registro.get("agente")
    ref = str(registro.get("referencia") or "")
    if agente == AGENTE_INVESTIGADOR:
        return "Quipu (asistente de consulta)"
    if agente == AGENTE_OPERATIVO:
        if ref.startswith("INF-"):
            return "Informe semanal"
        if ref.startswith("SKV-"):
            return "Mejora de procedimientos"
        return "Agente Operativo"
    if agente == AGENTE_SISTEMA:
        return "Estado de la IA"
    return f"Retirado ({agente})" if agente in (AGENTE_RESUMEN, AGENTE_CONTROL, AGENTE_SOLICITUDES) else str(agente or "—")


EVENTO_SIMPLE = {
    EVENTO_CONSULTA: "Consulta respondida", EVENTO_BORRADOR: "Propuesta o borrador", EVENTO_APROBACION: "Aprobado por una persona",
    EVENTO_RECHAZO: "Rechazado por una persona", EVENTO_ENVIO: "Enviado tras aprobación", EVENTO_BLOQUEO: "Bloqueado por un control",
    EVENTO_ESTADO: "Cambio de estado de la IA", EVENTO_ERROR: "Error técnico",
}


class Cronometro:
    """Mide la duración de una interacción para la auditoría."""
    def __init__(self):
        self._inicio = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self._inicio) * 1000)
