# src/agentes/estado.py
"""
Catálogo, clasificación de uso y ciclo de vida de la IA de SIREA, más el
kill-switch global.

Catálogo (semáforo de usos, SIREA 3.0)
--------------------------------------
  🟢 permitido    investigador   Diagnóstico de cumplimiento (solo lectura).
  🟢/🟡           operativo      Agente Operativo: trabaja con SKILLS. Cada skill
                                 declara su propio nivel:
                                   seguimiento_red      🟢 permitido
                                   revision_observacion 🟡 restringido (piloto,
                                                           aprueba un SUPER_ADMIN)
                                 Propone acciones; una persona aprueba y el
                                 sistema ejecuta. Solo opera si alguna skill
                                 pasó sus evaluaciones (evals.py).
  🔴 no permitido soporte_redes  Chatbot para usuarios externos. Evaluado y NO
                                 construido.
  ⚪ retirado     resumen, control, solicitudes
                                 Asistentes de SIREA 2.x retirados por
                                 proporcionalidad: una sola llamada al modelo
                                 cuyo resultado una regla o la persona lograba
                                 casi igual. Se conservan en el catálogo y en la
                                 auditoría histórica como decisión documentada.

Ciclo de vida (por agente y global)
-----------------------------------
  INACTIVO      configurado pero deshabilitado (estado inicial SIEMPRE).
  ACTIVO_HITL   operativo: propone bajo supervisión humana.
  EN_REVISION   suspendido temporalmente (pausa de emergencia).
  DESACTIVADO   retirado de servicio (exige justificación).

* El estado se guarda en la tabla `configuracion` de Supabase:
      agentes_ia_estado            -> estado GLOBAL (kill-switch)
      agentes_ia_estado_<agente>   -> estado individual
  El estado EFECTIVO es el más restrictivo entre el global y el individual.
* FAIL-CLOSED: si no se puede leer la configuración, el agente se
  considera INACTIVO. Un agente nunca opera "por defecto".
* Cada cambio queda en la auditoría inmutable (usuario, antes, después,
  justificación).

Autoridad:
      EN_REVISION  <- cualquier ADMIN o SUPER_ADMIN (pausa inmediata / pánico)
      ACTIVO_HITL  <- solo SUPER_ADMIN (el operativo, además, con una skill evaluada)
      INACTIVO     <- solo SUPER_ADMIN
      DESACTIVADO  <- solo SUPER_ADMIN + justificación obligatoria
      'soporte_redes' y los retirados no pueden activarse: no hay código que ejecutar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.agentes import auditoria

INACTIVO = "INACTIVO"
ACTIVO_HITL = "ACTIVO_HITL"
EN_REVISION = "EN_REVISION"
DESACTIVADO = "DESACTIVADO"
NO_AUTORIZADO = "NO_AUTORIZADO"   # evaluado y no construido
RETIRADO = "RETIRADO"             # existió y se retiró por proporcionalidad (SIREA 3.0)

ESTADOS: List[str] = [INACTIVO, ACTIVO_HITL, EN_REVISION, DESACTIVADO]

# Orden de restricción (mayor = más restrictivo). ACTIVO es el único que opera.
_RESTRICCION = {ACTIVO_HITL: 0, EN_REVISION: 1, INACTIVO: 2, DESACTIVADO: 3}

DESCRIPCION: Dict[str, str] = {
    INACTIVO: "Configurado pero deshabilitado (estado inicial, mantenimiento o actualización).",
    ACTIVO_HITL: "Operativo: produce borradores bajo supervisión humana obligatoria.",
    EN_REVISION: "Suspendido temporalmente por una pausa de emergencia o inconsistencias detectadas.",
    DESACTIVADO: "Retirado de servicio.",
    NO_AUTORIZADO: "Evaluado y no autorizado en esta fase.",
    RETIRADO: "Retirado por proporcionalidad (decisión documentada).",
}

ETIQUETA_UI: Dict[str, str] = {
    INACTIVO: "Inactivo",
    ACTIVO_HITL: "Activo · supervisión humana",
    EN_REVISION: "En revisión",
    DESACTIVADO: "Desactivado",
    NO_AUTORIZADO: "No autorizado",
    RETIRADO: "Retirado",
}

TONO_UI: Dict[str, str] = {
    INACTIVO: "mute",
    ACTIVO_HITL: "ok",
    EN_REVISION: "warn",
    DESACTIVADO: "bad",
    NO_AUTORIZADO: "bad",
    RETIRADO: "mute",
}

CLAVE_GLOBAL = "agentes_ia_estado"


# ------------------------------------------------------------
# Catálogo
# ------------------------------------------------------------

@dataclass(frozen=True)
class FichaAgente:
    clave: str
    nombre: str
    rol: str                 # línea corta sobre el nombre
    descripcion: str         # qué hace, en una frase
    nivel: str               # permitido | restringido | no_permitido
    construido: bool = True
    solo_principal: bool = False   # solo lo usa el SUPER_ADMIN principal (oiis.winepi)
    punto_de_control: str = ""     # paso humano de SIREA al que se engancha
    riesgos: Tuple[str, ...] = field(default_factory=tuple)
    controles: Tuple[str, ...] = field(default_factory=tuple)
    marcos: str = ""               # COBIT / ITIL / TOGAF / PRINCE2 / OCDE
    condiciones_futuras: Tuple[str, ...] = field(default_factory=tuple)


_MOTIVO_RETIRO = ("Retirado en SIREA 3.0 por proporcionalidad: hacía una sola llamada al modelo y su plan B "
                  "sin IA lograba casi lo mismo; el costo de gobernarlo superaba su aporte.")

CATALOGO: Dict[str, FichaAgente] = {
    auditoria.AGENTE_INVESTIGADOR: FichaAgente(
        clave=auditoria.AGENTE_INVESTIGADOR,
        nombre="Quipu · asistente de consulta",
        rol="Consulta · solo lectura · en todas las pantallas",
        descripcion="Responde preguntas rápidas de los administradores desde cualquier pantalla («¿qué le falta a la red X?», "
                    "«¿qué redes suelen atrasarse?», «¿qué hizo la IA hoy?») leyendo solo lo necesario de la base con "
                    "herramientas de solo lectura. No envía ni cambia nada.",
        nivel="permitido",
        punto_de_control="Quipu, asistente de bolsillo en todas las pantallas del panel (consulta de administradores).",
        riesgos=("Respuesta con cifras inventadas", "Pregunta fuera del dominio o inyección de instrucciones",
                 "Exposición de datos personales de remitentes"),
        controles=("Herramientas de solo lectura con lista blanca de campos (sin nombres, correos ni IP)",
                   "Guardrail de entrada (dominio, inyección) y de salida (PII, token canario)",
                   "Tope de consultas a herramientas por pregunta", "Toda consulta queda en la auditoría inmutable"),
        marcos="COBIT (monitoreo DSS/MEA) · ITIL (gestión del conocimiento) · OCDE (transparencia)",
    ),
    auditoria.AGENTE_OPERATIVO: FichaAgente(
        clave=auditoria.AGENTE_OPERATIVO,
        nombre="Agente Operativo",
        rol="Propone acciones · una persona aprueba",
        descripcion="Cada día hábil revisa las redes con centros pendientes y la bandeja de observaciones siguiendo "
                    "procedimientos escritos (skills). Propone recordatorios, pedidos de corrección, reintentos o "
                    "escalamientos; una persona aprueba, edita o rechaza y solo entonces el sistema ejecuta.",
        nivel="permitido",
        punto_de_control="Progreso por red (recordatorios) y Observaciones (revisión) — SIRE v7.",
        riesgos=("Correo a la red equivocada o con centros inventados", "Molestar a una red que ya avisó o cumplió",
                 "Dar por revisada una observación que pedía algo", "Texto de la red que intenta manipular al agente",
                 "Aprobación por inercia sin leer la propuesta"),
        controles=("Acciones con esquema fijo y validación determinística (centros reales, enfriamiento, topes)",
                   "Destinatario resuelto por el sistema, nunca por el modelo; editable antes de aprobar",
                   "Cola con aprobación humana; las propuestas vencen a las 48 h",
                   "Skills versionadas por huella y habilitadas solo si pasan sus evaluaciones",
                   "Traza de cada corrida y auditoría inmutable de cada decisión"),
        marcos="COBIT (BAI/DSS/MEA) · ITIL (gestión de eventos y solicitudes) · TOGAF (capa de aplicación) · "
               "PRINCE2 (gestión por excepción) · OCDE (supervisión humana, robustez)",
    ),
    auditoria.AGENTE_SOPORTE_REDES: FichaAgente(
        clave=auditoria.AGENTE_SOPORTE_REDES,
        nombre="Soporte a las redes (chatbot público)",
        rol="Evaluado · no construido",
        descripcion="Un chatbot para que las redes pregunten «¿por qué mi acuse salió rojo?» o «¿cómo cambio mi "
                    "contraseña?». Se evaluó y NO se habilita en esta fase.",
        nivel="no_permitido",
        construido=False,
        punto_de_control="Portal de la red (usuarios externos).",
        riesgos=("Usuarios externos sin autenticación fuerte", "Exposición de datos personales de remitentes y acuses",
                 "Respuestas incorrectas sobre plazos con efecto en el cumplimiento",
                 "Sin capacidad de supervisión humana en tiempo real"),
        controles=("Decisión: no habilitar. Las redes siguen con el correo de consultas y el portal determinístico",),
        marcos="OCDE (seguridad y robustez) · Ley 29733 (datos personales) · ITIL (mesa de servicio: nivel 0 humano)",
        condiciones_futuras=("Autenticación de la red reforzada (segundo factor)", "Base de conocimiento aprobada por la OIIS",
                             "Guardrails probados con red-team externo", "Aprobación formal de la Jefatura OIIS y TI"),
    ),
    auditoria.AGENTE_RESUMEN: FichaAgente(
        clave=auditoria.AGENTE_RESUMEN, nombre="Redactor del informe semanal", rol="Retirado en SIREA 3.0",
        descripcion="Redactaba el texto que acompaña al Excel del cierre. La plantilla fija del cierre cumple la misma función.",
        nivel="retirado", construido=False, controles=(_MOTIVO_RETIRO,),
    ),
    auditoria.AGENTE_CONTROL: FichaAgente(
        clave=auditoria.AGENTE_CONTROL, nombre="Analista de control", rol="Retirado en SIREA 3.0",
        descripcion="Describía las señales del control de actividad. Las señales ya las calcula SIRE; la persona las lee directo.",
        nivel="retirado", construido=False, controles=(_MOTIVO_RETIRO,),
    ),
    auditoria.AGENTE_SOLICITUDES: FichaAgente(
        clave=auditoria.AGENTE_SOLICITUDES, nombre="Pre-evaluador de solicitudes", rol="Retirado en SIREA 3.0",
        descripcion="Sugería aprobar o rechazar cambios de contraseña. Riesgo alto (decisión sobre personas) y poco volumen.",
        nivel="retirado", construido=False, controles=(_MOTIVO_RETIRO,),
    ),
}

AGENTES: List[str] = [a for a, f in CATALOGO.items() if f.construido]
NOMBRE_AGENTE: Dict[str, str] = {a: f.nombre for a, f in CATALOGO.items()}


class AgenteNoDisponibleError(Exception):
    """El agente no está en estado ACTIVO_HITL; la operación no se ejecuta."""

    def __init__(self, agente: str, estado: str):
        self.agente = agente
        self.estado = estado
        super().__init__(f"Asistente '{agente}' en estado {estado}: operación no permitida.")


# ------------------------------------------------------------
# Persistencia (tabla `configuracion`)
# ------------------------------------------------------------

def _clave(agente: Optional[str]) -> str:
    return CLAVE_GLOBAL if not agente else f"{CLAVE_GLOBAL}_{agente}"


def _leer(clave: str) -> Optional[str]:
    try:
        from src.db_manager import get_db_manager
        valor = get_db_manager().obtener_configuracion(clave)
        if valor and valor.strip().upper() in ESTADOS:
            return valor.strip().upper()
        return None
    except Exception:
        return None


def _escribir(clave: str, valor: str) -> bool:
    try:
        from src.db_manager import get_db_manager
        db = get_db_manager()
        fila = {"clave": clave, "valor": valor, "fecha_actualizacion": db._obtener_fecha_actual_iso()}
        resultado = db.supabase.table("configuracion").upsert(fila, on_conflict="clave").execute()
        if hasattr(db, "invalidar_cache"):
            db.invalidar_cache()   # SIRE v6.1+ recuerda la configuración 10 s
        return bool(resultado.data)
    except Exception as e:
        print(f"[estado_ia] No se pudo guardar {clave}={valor}: {e}")
        return False


# ------------------------------------------------------------
# Consultas de estado
# ------------------------------------------------------------

def estado_global() -> str:
    """Estado global (kill-switch). FAIL-CLOSED: sin dato => INACTIVO."""
    return _leer(CLAVE_GLOBAL) or INACTIVO


def estado_individual(agente: str) -> str:
    """Estado propio del agente. El no construido siempre es NO_AUTORIZADO; el resto arranca INACTIVO."""
    ficha = CATALOGO.get(agente)
    if ficha and not ficha.construido:
        return RETIRADO if ficha.nivel == "retirado" else NO_AUTORIZADO
    return _leer(_clave(agente)) or INACTIVO


def estado_efectivo(agente: str) -> str:
    """El más restrictivo entre el estado global y el individual."""
    i = estado_individual(agente)
    if i in (NO_AUTORIZADO, RETIRADO):
        return i
    g = estado_global()
    return g if _RESTRICCION[g] >= _RESTRICCION[i] else i


def esta_operativo(agente: str) -> bool:
    return estado_efectivo(agente) == ACTIVO_HITL


def exigir_operativo(agente: str) -> None:
    """Lanza AgenteNoDisponibleError si el agente no puede operar. Llamar al inicio de cada agente."""
    est = estado_efectivo(agente)
    if est != ACTIVO_HITL:
        raise AgenteNoDisponibleError(agente, est)


def mensaje_no_disponible(agente: str) -> str:
    from src.agentes.guardrails import MENSAJE_AGENTE_NO_DISPONIBLE
    est = estado_efectivo(agente)
    texto_estado = {
        INACTIVO: "inactivos (todavía no activados o en mantenimiento)",
        EN_REVISION: "en revisión (suspendidos temporalmente)",
        DESACTIVADO: "desactivados",
        NO_AUTORIZADO: "no autorizados en esta fase",
        RETIRADO: "retirados",
    }.get(est, est.lower())
    return MENSAJE_AGENTE_NO_DISPONIBLE.format(estado=texto_estado)


# ------------------------------------------------------------
# Cambios de estado
# ------------------------------------------------------------

def puede_cambiar(rol: str, estado_actual: str, estado_nuevo: str, justificacion: str,
                  agente: Optional[str] = None) -> Tuple[bool, str]:
    """Reglas de autoridad. Devuelve (permitido, motivo)."""
    rol = (rol or "").upper()
    ficha = CATALOGO.get(agente) if agente else None
    if ficha and not ficha.construido:
        return False, ("Este asistente fue retirado: no se puede activar." if ficha.nivel == "retirado"
                       else "Este asistente fue evaluado y no está autorizado: no se puede activar.")
    if estado_nuevo not in ESTADOS:
        return False, "Estado no válido."
    if estado_nuevo == estado_actual:
        return False, "El asistente ya se encuentra en ese estado."
    if rol not in ("ADMIN", "SUPER_ADMIN"):
        return False, "Sin permisos."
    if estado_nuevo == EN_REVISION:
        return True, "ok"  # pausa de emergencia: cualquier administrador
    if rol != "SUPER_ADMIN":
        return False, "Solo un SUPER_ADMIN puede activar, inactivar o desactivar los asistentes."
    if (estado_nuevo == DESACTIVADO or estado_actual == DESACTIVADO) and len((justificacion or "").strip()) < 10:
        return False, "Desactivar (o reactivar un asistente desactivado) exige una justificación de al menos 10 caracteres."
    if agente == auditoria.AGENTE_OPERATIVO and estado_nuevo == ACTIVO_HITL:
        try:
            from src.agentes.evals import alguna_habilitada
            ok, motivo = alguna_habilitada()
        except Exception as e:  # noqa: BLE001  (fail-closed)
            ok, motivo = False, f"No se pudo verificar las evaluaciones ({type(e).__name__})."
        if not ok:
            return False, "El Agente Operativo solo se activa con al menos una skill evaluada. " + motivo
    return True, "ok"


def cambiar_estado(agente: Optional[str], estado_nuevo: str, rol: str, justificacion: str = "") -> Tuple[bool, str]:
    """
    Cambia el estado global (agente=None) o de un agente, validando la
    autoridad y registrando el cambio en la auditoría inmutable.
    """
    estado_nuevo = (estado_nuevo or "").upper()
    actual = estado_global() if agente is None else estado_individual(agente)
    ok, motivo = puede_cambiar(rol, actual, estado_nuevo, justificacion, agente)
    if not ok:
        return False, motivo
    if not _escribir(_clave(agente), estado_nuevo):
        return False, "No se pudo guardar el estado en la base de datos."
    auditoria.registrar_cambio_estado(
        agente=agente or auditoria.AGENTE_SISTEMA,
        estado_anterior=actual,
        estado_nuevo=estado_nuevo,
        justificacion=justificacion or "(sin justificación)",
    )
    return True, f"Estado actualizado a {ETIQUETA_UI.get(estado_nuevo, estado_nuevo)}."


def boton_de_panico(rol: str, justificacion: str = "Detención de emergencia") -> Tuple[bool, str]:
    """Kill-switch: pone el estado GLOBAL en EN_REVISION. Cualquier administrador puede usarlo."""
    return cambiar_estado(None, EN_REVISION, rol, justificacion)


@dataclass
class ResumenEstado:
    global_: str
    por_agente: Dict[str, str]
    efectivo: Dict[str, str]


def resumen() -> ResumenEstado:
    g = estado_global()
    ind = {a: estado_individual(a) for a in CATALOGO}
    ef = {a: (ind[a] if ind[a] in (NO_AUTORIZADO, RETIRADO) else (g if _RESTRICCION[g] >= _RESTRICCION[ind[a]] else ind[a]))
          for a in CATALOGO}
    return ResumenEstado(global_=g, por_agente=ind, efectivo=ef)
