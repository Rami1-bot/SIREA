# tests/test_proveedores.py
"""
Capa de proveedores: conmutación Gemini → Groq, bucle de herramientas
controlado por SIREA, tope de llamadas y registro de quién respondió.
Sin red: los proveedores se sustituyen por dobles.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")


class _Prov:
    def __init__(self, nombre, respuestas=None, falla=None):
        self.nombre, self.respuestas, self.falla, self.llamadas = nombre, list(respuestas or []), falla, 0

    def disponible(self):
        return True

    def generar(self, sistema, mensajes, herramientas, temperatura):
        from src.agentes.proveedores import Respuesta
        self.llamadas += 1
        if self.falla:
            raise self.falla
        r = self.respuestas.pop(0) if self.respuestas else ("ok", [])
        return Respuesta(texto=r[0], llamadas=r[1], proveedor=self.nombre, modelo=f"{self.nombre}-m")


@pytest.fixture
def dos_proveedores(monkeypatch):
    from src.agentes import proveedores
    from src.config import Config
    monkeypatch.setattr(Config, "IA_PROVEEDOR_ORDEN", ["gemini", "groq"])
    monkeypatch.setattr(Config, "IA_MAX_TOOL_CALLS", 3)
    return proveedores


def test_conmuta_a_groq_si_gemini_falla(dos_proveedores, monkeypatch):
    import httpx
    g = _Prov("gemini", falla=httpx.ConnectError("sin red"))
    q = _Prov("groq", respuestas=[("respondió groq", [])])
    monkeypatch.setattr(dos_proveedores, "_PROVEEDORES", {"gemini": g, "groq": q})
    r = dos_proveedores.generar("sys", [dos_proveedores.Mensaje.usuario("hola")])
    assert r.proveedor == "groq" and r.texto == "respondió groq" and r.etiqueta_modelo == "groq:groq-m"
    assert g.llamadas == 1 and q.llamadas == 1


def test_error_si_todos_fallan(dos_proveedores, monkeypatch):
    g = _Prov("gemini", falla=RuntimeError("x"))
    q = _Prov("groq", falla=RuntimeError("y"))
    monkeypatch.setattr(dos_proveedores, "_PROVEEDORES", {"gemini": g, "groq": q})
    with pytest.raises(dos_proveedores.ProveedorNoDisponibleError):
        dos_proveedores.generar("sys", [dos_proveedores.Mensaje.usuario("hola")])


def test_sin_claves_no_hay_proveedor(dos_proveedores, monkeypatch):
    from src.config import Config
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(Config, "GROQ_API_KEY", "")
    with pytest.raises(dos_proveedores.ProveedorNoDisponibleError):
        dos_proveedores.generar("sys", [dos_proveedores.Mensaje.usuario("hola")])


def test_bucle_de_herramientas_ejecuta_y_respeta_el_tope(dos_proveedores, monkeypatch):
    P = dos_proveedores
    ejecutadas = []
    h = P.Herramienta("progreso", "d", {"type": "object", "properties": {}}, lambda **k: ejecutadas.append(k) or {"pct": 40})
    pide = ("", [P.LlamadaHerramienta("1", "progreso", {"red": "ANCASH"})])
    g = _Prov("gemini", respuestas=[pide, pide, pide, pide, pide])   # nunca deja de pedir herramientas
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": g, "groq": _Prov("groq")})
    r, usadas = P.ejecutar_con_herramientas("sys", [P.Mensaje.usuario("¿cómo va?")], [h], max_llamadas=3)
    assert len(ejecutadas) == 3 and usadas == ["progreso"] * 3
    assert "límite" in r.texto


def test_bucle_termina_con_texto(dos_proveedores, monkeypatch):
    P = dos_proveedores
    h = P.Herramienta("info", "d", {"type": "object", "properties": {}}, lambda **k: {"semana": 40})
    g = _Prov("gemini", respuestas=[("", [P.LlamadaHerramienta("1", "info", {})]), ("Semana 40.", [])])
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": g, "groq": _Prov("groq")})
    r, usadas = P.ejecutar_con_herramientas("sys", [P.Mensaje.usuario("¿qué semana?")], [h])
    assert r.texto == "Semana 40." and usadas == ["info"] and g.llamadas == 2


def test_la_conversacion_sigue_con_el_proveedor_que_contesto(dos_proveedores, monkeypatch):
    """Si Gemini falla en la primera llamada y Groq contesta, las siguientes vueltas van a Groq (no se mezclan formatos)."""
    import httpx
    P = dos_proveedores
    h = P.Herramienta("info", "d", {"type": "object", "properties": {}}, lambda **k: {"semana": 40})
    g = _Prov("gemini", falla=httpx.ConnectError("sin red"))
    q = _Prov("groq", respuestas=[("", [P.LlamadaHerramienta("c1", "info", {})]), ("Semana 40 (groq).", [])])
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": g, "groq": q})
    r, _ = P.ejecutar_con_herramientas("sys", [P.Mensaje.usuario("¿qué semana?")], [h])
    assert r.proveedor == "groq" and g.llamadas == 1 and q.llamadas == 2


def test_herramienta_desconocida_no_rompe(dos_proveedores, monkeypatch):
    P = dos_proveedores
    g = _Prov("gemini", respuestas=[("", [P.LlamadaHerramienta("1", "borrar_todo", {})]), ("listo", [])])
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": g, "groq": _Prov("groq")})
    r, usadas = P.ejecutar_con_herramientas("sys", [P.Mensaje.usuario("x")], [])
    assert r.texto == "listo" and usadas == []


def test_groq_traduce_mensajes_y_tools(monkeypatch):
    """El cuerpo que va a Groq tiene el formato OpenAI (system/user/assistant+tool_calls/tool)."""
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(Config, "GROQ_MODEL", "modelo-x")
    capturado = {}

    class _Resp:
        status_code = 200
        text = ""
        def raise_for_status(self): pass
        def json(self): return {"model": "modelo-x", "choices": [{"message": {"content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "info", "arguments": "{\"red\": \"ANCASH\"}"}}]}}]}

    class _Cli:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None):
            capturado.update(url=url, json=json, headers=headers)
            return _Resp()

    monkeypatch.setattr(P.httpx, "Client", _Cli)
    monkeypatch.setattr(P._Groq, "modelos_disponibles", lambda self: ["modelo-x"])
    ll = P.LlamadaHerramienta("t0", "info", {})
    msgs = [P.Mensaje.usuario("hola"), P.Mensaje.asistente("", [ll]), P.Mensaje.resultado_herramienta(ll, {"semana": 40})]
    h = P.Herramienta("info", "d", {"type": "object", "properties": {"red": {"type": "string"}}}, lambda **k: {})
    r = P._Groq().generar("SYS", msgs, [h], 0.1)
    body = capturado["json"]
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][2]["tool_calls"][0]["function"]["name"] == "info"
    assert body["messages"][3]["role"] == "tool" and body["messages"][3]["tool_call_id"] == "t0"
    assert body["tools"][0]["function"]["name"] == "info"
    assert capturado["headers"]["Authorization"] == "Bearer k"
    assert r.llamadas[0].nombre == "info" and r.llamadas[0].args == {"red": "ANCASH"} and r.proveedor == "groq"


def test_gemini_traduce_mensajes_herramientas_y_respuesta(monkeypatch):
    """Construye los tipos reales del SDK de Gemini (sin red) y lee function_calls de la respuesta."""
    from google.genai import types
    from src.agentes import proveedores as P, cliente_ia
    from src.config import Config
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "k")
    capt = {}

    def _fake(cliente, **kwargs):
        capt.update(kwargs)
        fc = types.FunctionCall(name="info", args={"red": "ANCASH"})
        resp = types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
            role="model", parts=[types.Part(text="Consulto."), types.Part(function_call=fc)]))])
        return resp, "gemini-x"

    monkeypatch.setattr(P, "_Gemini", P._Gemini)  # no-op, claridad
    import src.agentes.cliente_ia as ci
    monkeypatch.setattr(ci, "generar_contenido_con_modelo", _fake)
    monkeypatch.setattr(ci, "get_cliente_gemini", lambda: object())
    ll = P.LlamadaHerramienta("g0", "info", {})
    msgs = [P.Mensaje.usuario("hola"), P.Mensaje.asistente("", [ll]), P.Mensaje.resultado_herramienta(ll, {"semana": 40})]
    h = P.Herramienta("info", "d", {"type": "object", "properties": {"red": {"type": "string"}}, "required": ["red"]}, lambda **k: {})
    r = P._Gemini().generar("SYS", msgs, [h], 0.1)
    assert r.proveedor == "gemini" and r.modelo == "gemini-x"
    assert r.texto == "Consulto." and r.llamadas[0].nombre == "info" and r.llamadas[0].args == {"red": "ANCASH"}
    assert capt["config"].system_instruction == "SYS"
    assert capt["config"].tools[0].function_declarations[0].name == "info"
    assert len(capt["contents"]) == 3 and capt["contents"][2].parts[0].function_response.name == "info"


def test_groq_error_legible(monkeypatch):
    """Un 404 de Groq se traduce a un mensaje accionable (modelo inexistente) y la auditoría lo guarda legible."""
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(Config, "GROQ_MODEL", "modelo-viejo")

    class _Resp:
        status_code = 404
        text = '{"error": {"message": "The model `modelo-viejo` does not exist", "type": "invalid_request_error"}}'
        def json(self): return {}

    class _Cli:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(P.httpx, "Client", _Cli)
    monkeypatch.setattr(P._Groq, "modelos_disponibles", lambda self: [])
    with pytest.raises(P.ErrorProveedor) as ex:
        P._Groq().generar("S", [P.Mensaje.usuario("hola")], None, 0.1)
    assert "GROQ_MODEL no existe" in ex.value.mensaje and "modelo-viejo" in ex.value.mensaje
    assert "modelo-viejo" in P.explicar_error("groq", ex.value)


def test_diagnostico_reporta_cada_proveedor(monkeypatch):
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "IA_PROVEEDOR_ORDEN", ["gemini", "groq"])
    g = _Prov("gemini", respuestas=[("OK", [])])
    q = _Prov("groq", falla=P.ErrorProveedor("groq", 401, "GROQ_API_KEY inválida o vencida (revise la clave en console.groq.com)."))
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": g, "groq": q})
    d = P.diagnostico()
    assert d[0]["proveedor"] == "gemini" and d[0]["ok"] and "OK" in d[0]["mensaje"]
    assert d[1]["proveedor"] == "groq" and not d[1]["ok"] and "GROQ_API_KEY" in d[1]["mensaje"]


def test_cliente_gemini_se_construye_con_clave(monkeypatch):
    """Regresión: get_cliente_gemini usaba Config.gemini_configurado(), que SIRE no tenía."""
    from src.config import Config
    from src.agentes import cliente_ia
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "clave-de-prueba")
    cliente_ia._cliente = None
    assert Config.gemini_configurado()
    assert cliente_ia.get_cliente_gemini() is not None   # construir el cliente no hace red


def test_groq_elige_modelo_disponible_si_el_configurado_no_existe(monkeypatch):
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(Config, "GROQ_MODEL", "gpt-4o-mini")      # nombre de OpenAI, no de Groq
    monkeypatch.setattr(Config, "GROQ_MODELOS_RESPALDO", ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"])
    g = P._Groq()
    P._Groq._cache_modelos, P._Groq._cache_ts = None, 0.0
    monkeypatch.setattr(g, "modelos_disponibles", lambda: ["whisper-large-v3", "openai/gpt-oss-120b", "llama-3.1-8b-instant"])
    modelo, aviso = g.modelo_efectivo()
    assert modelo == "openai/gpt-oss-120b" and "gpt-4o-mini" in aviso and "no existe" in aviso


def test_groq_respeta_el_modelo_configurado_si_existe(monkeypatch):
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(Config, "GROQ_MODEL", "llama-3.1-8b-instant")
    g = P._Groq()
    monkeypatch.setattr(g, "modelos_disponibles", lambda: ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"])
    assert g.modelo_efectivo() == ("llama-3.1-8b-instant", None)


def test_groq_sin_catalogo_confia_en_lo_configurado(monkeypatch):
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(Config, "GROQ_MODEL", "llama-3.3-70b-versatile")
    g = P._Groq()
    monkeypatch.setattr(g, "modelos_disponibles", lambda: [])
    assert g.modelo_efectivo()[0] == "llama-3.3-70b-versatile"


def test_gemini_devuelve_su_turno_intacto_y_agrupa_respuestas(monkeypatch):
    """Regresión del 400 de Gemini 3: se reenvía el turno original (con thought_signature)
    y las respuestas de varias herramientas van juntas en un solo mensaje."""
    from google.genai import types
    import src.agentes.cliente_ia as ci
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "k")
    llamadas_api = []

    def _fake(cliente, **kwargs):
        llamadas_api.append(kwargs["contents"])
        if len(llamadas_api) == 1:
            parts = [types.Part(function_call=types.FunctionCall(name="a", args={}), thought_signature=b"firma-1"),
                     types.Part(function_call=types.FunctionCall(name="b", args={}))]
            return types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(role="model", parts=parts))]), "gemini-x"
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
            role="model", parts=[types.Part(text="pensando…", thought=True), types.Part(text="Listo.")]))]), "gemini-x"

    monkeypatch.setattr(ci, "generar_contenido_con_modelo", _fake)
    monkeypatch.setattr(ci, "get_cliente_gemini", lambda: object())
    monkeypatch.setattr(Config, "IA_PROVEEDOR_ORDEN", ["gemini"])
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": P._Gemini(), "groq": P._Groq()})
    hs = [P.Herramienta(n, "d", {"type": "object", "properties": {}}, lambda **k: {"ok": 1}) for n in ("a", "b")]
    r, usadas = P.ejecutar_con_herramientas("SYS", [P.Mensaje.usuario("hola")], hs)
    assert r.texto == "Listo." and usadas == ["a", "b"]
    segunda = llamadas_api[1]
    assert segunda[1].parts[0].thought_signature == b"firma-1"          # turno del modelo intacto
    assert len(segunda) == 3 and len(segunda[2].parts) == 2              # 2 respuestas en 1 mensaje


def test_si_gemini_falla_a_mitad_de_conversacion_responde_groq(monkeypatch):
    from src.agentes import proveedores as P
    from src.config import Config
    monkeypatch.setattr(Config, "IA_PROVEEDOR_ORDEN", ["gemini", "groq"])
    pide = ("", [P.LlamadaHerramienta("1", "info", {})])
    g = _Prov("gemini", respuestas=[pide])
    orig = g.generar
    def gen(*a, **k):
        if g.llamadas >= 1:
            g.llamadas += 1
            raise RuntimeError("400 a mitad")
        return orig(*a, **k)
    g.generar = gen
    q = _Prov("groq", respuestas=[("Respuesta de Groq.", [])])
    monkeypatch.setattr(P, "_PROVEEDORES", {"gemini": g, "groq": q})
    h = P.Herramienta("info", "d", {"type": "object", "properties": {}}, lambda **k: {})
    r, _ = P.ejecutar_con_herramientas("S", [P.Mensaje.usuario("x")], [h])
    assert r.proveedor == "groq" and r.texto == "Respuesta de Groq."
