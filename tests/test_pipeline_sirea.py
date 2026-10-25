# tests/test_pipeline_sirea.py
"""
Pruebas del pipeline de gobernanza de los asistentes de SIREA con los
proveedores de IA, la base de datos y Streamlit SIMULADOS (sin red, sin
claves). Verifican el orden y la obligatoriedad de los controles:

    estado (kill-switch) -> guardrail de entrada -> proveedor (Gemini → Groq)
    -> guardrail de salida -> leyenda -> auditoría

y que cada bloqueo o decisión humana deje rastro.
"""

import os
import sys
import types as pytypes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")


# ------------------------------------------------------------
# fixtures
# ------------------------------------------------------------

@pytest.fixture
def auditoria_mem(monkeypatch):
    from src.agentes import auditoria
    registros = []
    monkeypatch.setattr(auditoria, "registrar", lambda reg: registros.append(reg) or "1")
    return registros


@pytest.fixture
def activos(monkeypatch):
    from src.agentes import estado
    monkeypatch.setattr(estado, "estado_global", lambda: estado.ACTIVO_HITL)
    monkeypatch.setattr(estado, "_leer", lambda clave: estado.ACTIVO_HITL)


@pytest.fixture
def detenidos(monkeypatch):
    from src.agentes import estado
    monkeypatch.setattr(estado, "estado_global", lambda: estado.EN_REVISION)


@pytest.fixture
def proveedor_falso(monkeypatch):
    """Sustituye la capa de proveedores: devuelve `salida[0]` y registra las llamadas."""
    from src.agentes import proveedores
    salida = ["La red AREQUIPA está al 40 % (4 de 10 centros)."]
    llamadas = []

    def _fake(sistema, mensajes, herramientas=None, temperatura=0.2, solo_proveedor=None):
        llamadas.append({"sistema": sistema, "mensajes": mensajes, "herramientas": herramientas})
        return proveedores.Respuesta(texto=salida[0], llamadas=[], proveedor="gemini", modelo="modelo-falso")

    monkeypatch.setattr(proveedores, "generar", _fake)
    return pytypes.SimpleNamespace(salida=salida, llamadas=llamadas)


@pytest.fixture
def datos_falsos(monkeypatch):
    from src.agentes import agente_investigador
    monkeypatch.setattr(agente_investigador, "_nombres_redes", lambda: ["AREQUIPA", "ANCASH"])
    monkeypatch.setattr(agente_investigador, "registro_herramientas", lambda: [])


# ------------------------------------------------------------
# kill-switch (fail-closed)
# ------------------------------------------------------------

def test_sin_configuracion_los_agentes_estan_inactivos(monkeypatch):
    from src.agentes import estado
    monkeypatch.setattr(estado, "_leer", lambda clave: None)
    assert estado.estado_global() == estado.INACTIVO
    for a in estado.AGENTES:
        assert not estado.esta_operativo(a)


def test_el_no_construido_nunca_se_activa(monkeypatch, auditoria_mem):
    from src.agentes import estado, auditoria
    monkeypatch.setattr(estado, "_leer", lambda clave: estado.ACTIVO_HITL)
    assert estado.estado_efectivo(auditoria.AGENTE_SOPORTE_REDES) == estado.NO_AUTORIZADO
    ok, motivo = estado.cambiar_estado(auditoria.AGENTE_SOPORTE_REDES, estado.ACTIVO_HITL, "SUPER_ADMIN", "x" * 20)
    assert not ok and "no está autorizado" in motivo


def test_kill_switch_detiene_al_investigador(detenidos, auditoria_mem, proveedor_falso):
    from src.agentes import agente_investigador
    r = agente_investigador.responder_pregunta("¿Cómo va Arequipa?", [])
    assert r["bloqueado"] and "no" in r["texto"].lower()
    assert proveedor_falso.llamadas == []          # no se gastó ni un token


def test_autoridad_del_ciclo_de_vida():
    from src.agentes import estado
    assert estado.puede_cambiar("ADMIN", estado.ACTIVO_HITL, estado.EN_REVISION, "")[0]       # pánico: cualquiera
    assert not estado.puede_cambiar("ADMIN", estado.INACTIVO, estado.ACTIVO_HITL, "")[0]      # activar: solo SUPER_ADMIN
    assert not estado.puede_cambiar("SUPER_ADMIN", estado.ACTIVO_HITL, estado.DESACTIVADO, "corto")[0]
    assert estado.puede_cambiar("SUPER_ADMIN", estado.ACTIVO_HITL, estado.DESACTIVADO, "x" * 12)[0]


# ------------------------------------------------------------
# investigador
# ------------------------------------------------------------

def test_investigador_responde_y_audita(activos, auditoria_mem, proveedor_falso, datos_falsos):
    from src.agentes import agente_investigador, auditoria
    r = agente_investigador.responder_pregunta("¿Por qué Arequipa no cierra?", [])
    assert "AREQUIPA" in r["texto"] and "generada por IA" in r["texto"]
    assert r["proveedor"] == "gemini" and r["modelo"] == "modelo-falso"
    assert auditoria_mem and auditoria_mem[-1].evento == auditoria.EVENTO_CONSULTA
    assert auditoria_mem[-1].modelo == "gemini:modelo-falso"


def test_investigador_bloquea_fuera_de_dominio_sin_llamar_al_modelo(activos, auditoria_mem, proveedor_falso, datos_falsos):
    from src.agentes import agente_investigador, auditoria
    r = agente_investigador.responder_pregunta("Dame una receta de ceviche", [])
    assert r["bloqueado"]
    assert proveedor_falso.llamadas == []
    assert auditoria_mem[-1].evento == auditoria.EVENTO_BLOQUEO


def test_investigador_bloquea_fuga_del_prompt(activos, auditoria_mem, proveedor_falso, datos_falsos):
    from src.agentes import agente_investigador, guardrails
    proveedor_falso.salida[0] = f"Claro, mi configuración es {guardrails.TOKEN_CANARIO}"
    r = agente_investigador.responder_pregunta("¿Cómo va la red Ancash?", [])
    assert r["bloqueado"] and guardrails.TOKEN_CANARIO not in r["texto"]
