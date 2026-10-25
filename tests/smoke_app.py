# tests/smoke_app.py
"""
Arranca SIREA con un Supabase SIMULADO (sin red ni claves) para revisar las
pantallas en un navegador:

    python -m streamlit run tests/smoke_app.py

Acceso al panel: usuario `oiis.winepi` · contraseña `Sirea-Demo-2026!`
Acceso de red:   red `ANCASH`    · contraseña `Red-Ancash-2026!`
"""
import os
import runpy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "demo")
os.environ.setdefault("STORAGE_MODE", "local")
os.environ.setdefault("ENVIRONMENT", "development")
if os.environ.get("SIREA_IA_SIMULADA", "1") == "1":
    os.environ.setdefault("GEMINI_API_KEY", "simulada")

from tests.fake_supabase import instalar  # noqa: E402

_FAKE = instalar()

# SIREA 3.2: 10 semanas de historial SIMULADO (patrones, informe, recordatorio preventivo).
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("sembrar_demo", RAIZ / "scripts" / "sembrar_historial_demo.py")
_sem = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_sem)
_sem.sembrar(10)

# Agente Operativo listo para recorrer: activo y con la skill de seguimiento evaluada.
from datetime import datetime as _dt, timezone as _tz  # noqa: E402
from src.agentes.skills import cargar_todas as _skills  # noqa: E402
_FAKE.tablas["configuracion"].append({"id": 50, "clave": "agentes_ia_estado_operativo", "valor": "ACTIVO_HITL"})
# Tres rechazos con motivo (para recorrer «aprender de los rechazos»).
for _k in range(3):
    _FAKE.tablas["agente_acciones"].append({
        "id": 901 + _k, "skill": "seguimiento_red", "skill_version": "1.0.0", "tipo": "RECORDATORIO_RED", "red": "ANCASH",
        "semana": 39, "anio": 2026, "clave_unica": f"demo-{_k}", "payload": {}, "justificacion": "faltan centros",
        "evidencia": {}, "origen": "ia", "estado": "RECHAZADA", "motivo_decision": "La red ya avisó por teléfono",
        "decidida_por": "oiis.winepi", "decidida_at": _dt.now(_tz.utc).isoformat(), "creada_at": _dt.now(_tz.utc).isoformat(),
        "editada": False})
for _i, (_sid, _ia, _sin) in enumerate((("seguimiento_red", 8, 5), ("revision_observacion", 8, 1))):
    _s = _skills()[_sid]
    for _modo, _ok in (("sin_ia", _sin), ("ia", _ia)):
        _FAKE.tablas["agente_evals"].append({
            "id": len(_FAKE.tablas["agente_evals"]) + 1, "fecha": _dt.now(_tz.utc).isoformat(), "skill": _sid,
            "skill_version": _s.version, "skill_hash": _s.huella, "usuario": "oiis.winepi", "modo": _modo,
            "proveedor": "gemini:simulado" if _modo == "ia" else None, "total": 8, "aprobados": _ok, "puntaje": _ok / 8,
            "detalle": []})

# Proveedor de IA simulado (sin red): respuestas fijas para recorrer las pantallas.
if os.environ.get("SIREA_IA_SIMULADA", "1") == "1":
    from src.agentes import proveedores as _P

    def _simulado(sistema, mensajes, herramientas=None, temperatura=0.2, solo_proveedor=None):
        ultimo = mensajes[-1] if mensajes else None
        if "auditor de calidad" in sistema:
            import json as _j
            return _P.Respuesta(_j.dumps({"diagnostico": "Las redes avisan por teléfono y el agente no lo sabe.", "ajustes": [
                {"regla": "Antes de recordar, revise si la memoria registra un aviso telefónico reciente de la red.",
                 "por_que": "Tres rechazos por redes que ya habían avisado por teléfono.", "rechazos": [901, 902, 903]}]},
                ensure_ascii=False), [], "gemini", "demo")
        if "# SKILL:" in sistema:
            return _P.Respuesta(_decision_simulada(ultimo.contenido if ultimo else ""), [], "gemini", "demo")
        if "redactor del informe semanal" in sistema:
            import json as _j
            t = ultimo.contenido if ultimo else ""
            ini, fin = t.rfind("<datos_sistema>"), t.rfind("</datos_sistema>")
            d = _j.loads(t[ini + len("<datos_sistema>"):fin]) if 0 <= ini < fin else {}
            vig = ", ".join(v["red"] for v in d.get("redes_a_vigilar") or []) or "ninguna"
            return _P.Respuesta(
                f"Situación de la semana\n- {d.get('redes_completas')} de {d.get('redes_total')} redes completaron la semana {d.get('semana')}.\n"
                f"Lo destacado\n- Las redes con pendientes reciben hoy su recordatorio, previa aprobación.\n"
                f"Patrones a vigilar\n- Tendencia a enviar después del corte: {vig}.\n"
                f"Recomendaciones\n- Recordar antes del corte a las redes con esa tendencia y ofrecer apoyo con el reporte que suele faltar.",
                [], "gemini", "demo")
        if herramientas and ultimo is not None and ultimo.rol == "usuario":
            return _P.Respuesta("", [_P.LlamadaHerramienta("s1", "progreso_de_una_red", {"red": "ANCASH"})], "gemini", "demo")
        if "Sugerencia" in sistema or "pre-evaluador" in sistema:
            return _P.Respuesta("Sugerencia: APROBAR\nResumen del sustento: la contraseña fue compartida con personal que ya no labora.\n"
                                "Fundamento:\n- Motivo de seguridad válido\n- Texto claro y completo\nVerificar antes de decidir:\n- Confirmar con la red el cambio de responsable", [], "gemini", "demo")
        if "Analista de control" in sistema:
            return _P.Respuesta("Periodo sin acciones registradas: 0 acciones, 0 con señal. Cadena de auditoría íntegra.\n- No hay señales que revisar.\n"
                                "Preguntas de seguimiento:\n- Ninguna.\nInforme de apoyo; la revisión y las decisiones corresponden al SUPER_ADMIN principal.", [], "groq", "demo")
        return _P.Respuesta("Situación: la red ANCASH va al 33.3 % en la semana 40 (1 de 3 centros).\nQué encontré:\n- Faltan 2 centros.\n"
                            "- Sin envíos tardíos ni duplicados.\nQué conviene revisar:\n- Recordar a la red los centros pendientes antes del corte.", [], "gemini", "demo")

    _P.generar = _simulado

    class _ProvSim:
        def __init__(self, nombre, falla=None):
            self.nombre, self.falla = nombre, falla
        def disponible(self):
            return True
        def generar(self, sistema, mensajes, herramientas, temperatura):
            if self.falla:
                raise self.falla
            if "# SKILL:" in sistema:
                return _P.Respuesta(_decision_simulada(mensajes[-1].contenido), [], self.nombre, "demo")
            return _P.Respuesta("OK", [], self.nombre, "demo")

    def _decision_simulada(texto):
        """Decisión fija y razonable para el recorrido de pantallas (no es una evaluación)."""
        import json as _j
        ini, fin = texto.rfind("<datos_sistema>"), texto.rfind("</datos_sistema>")
        try:
            exp = _j.loads(texto[ini + len("<datos_sistema>"):fin]) if 0 <= ini < fin else {}
        except Exception:
            exp = {}
        def _acc(tipo, **k):
            just = {"RECORDATORIO_RED": "Faltan centros, el corte está cerca o vencido y la red no recibió recordatorio en las últimas 20 horas.",
                    "ESCALAR": "El caso necesita el criterio de una persona antes de actuar.",
                    "MARCAR_REVISADA": "El comentario de la red solo explica la situación y no pide nada a la OIIS.",
                    "SOLICITAR_CORRECCION": "El sistema detectó un dato que la red debe corregir para que el envío sea válido.",
                    "REINTENTAR_FALLA": "Falla técnica que el sistema puede reintentar sin intervención de la red.",
                    "NOTA_MEMORIA": "Dato que conviene recordar en las próximas semanas.",
                    "SIN_ACCION": "No corresponde actuar todavía."}.get(tipo, "Según la skill.")
            return dict({"tipo": tipo, "justificacion": just}, **k)
        if exp.get("tipo_caso") == "red":
            previas = [x for x in exp.get("acciones_previas") or [] if x.get("tipo") == "RECORDATORIO_RED" and x.get("estado") == "EJECUTADA"]
            horas = exp.get("horas_al_corte")
            if exp.get("solicitud_password_abierta"):
                acc = [_acc("ESCALAR", motivo="Verificar el acceso de la red antes de recordar.")]
            elif exp.get("memoria") and (horas is None or horas > 0):
                acc = [_acc("SIN_ACCION")]
            elif len(previas) >= 2:
                acc = [_acc("ESCALAR", motivo="Dos recordatorios sin avance: requiere gestión de la Jefatura.")]
            elif any(str(x.get("ejecutada_at") or "") >= _dt.now(_tz.utc).replace(microsecond=0).isoformat()[:10] for x in previas) \
                    and previas and horas is not None and horas > 0:
                acc = [_acc("SIN_ACCION")]
            elif horas is not None and horas > 72:
                acc = [_acc("SIN_ACCION")]
            else:
                pend = list(dict.fromkeys((exp.get("faltantes") or []) + [x["centro"] for x in exp.get("pendientes_por_tipo") or []]))
                acc = [_acc("RECORDATORIO_RED", centros_pendientes=pend,
                            mensaje_personalizado="Como parte del seguimiento semanal, le informamos que quedarían pendientes los "
                                                  "reportes indicados en el detalle. Le agradeceremos realizar el envío a través de "
                                                  "SIREA a la brevedad. Quedamos atentos por si requiere apoyo.")]
        else:
            texto = str(exp.get("texto_de_la_red") or "").lower()
            if exp.get("motivo") == "FALLA":
                acc = [_acc("REINTENTAR_FALLA")] if exp.get("reintentable") else [_acc("ESCALAR", motivo="Falla técnica no reintentable.")]
            elif any(w in texto for w in ("asistente", "ignore", "reglas")):
                acc = [_acc("ESCALAR", motivo="El texto de la red contiene instrucciones para el agente.")]
            elif any(w in texto for w in ("por favor", "anulen", "soliciten", "necesitamos")):
                acc = [_acc("ESCALAR", motivo="La red pide una acción a la OIIS.")]
            elif exp.get("motivo") == "SUSTENTO" or texto:
                acc = [_acc("MARCAR_REVISADA", nota="La red explicó la situación; no requiere acción.")]
                if "hasta" in texto:
                    acc.append(_acc("NOTA_MEMORIA", nota="Un centro de la red está cerrado temporalmente por obras.", vigencia_dias=60))
            else:
                acc = [_acc("SOLICITAR_CORRECCION",
                            motivo_correccion="El sistema detectó un problema en el envío según su observación. "
                                              "Corrija los archivos indicados y vuelva a enviar el ZIP.")]
        return _j.dumps({"razonamiento": "Decisión tomada siguiendo el procedimiento aprobado (datos de demostración).", "acciones": acc}, ensure_ascii=False)

    _P._PROVEEDORES = {"gemini": _ProvSim("gemini"),
                       "groq": _ProvSim("groq", _P.ErrorProveedor("groq", 404, "GROQ_MODEL no existe o fue retirado: (simulado)."))}

runpy.run_path(str(RAIZ / "app.py"), run_name="__main__")
