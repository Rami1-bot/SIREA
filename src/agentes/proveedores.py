# src/agentes/proveedores.py
"""
Capa de proveedores de IA de SIREA: Gemini (principal) y Groq (respaldo),
detrás de UNA sola interfaz neutra, con conmutación automática y registro
de quién respondió.

Por qué existe
--------------
* Gemini a veces no está disponible (cuota, "high demand", cortes). Si
  todos sus modelos fallan, se prueba con Groq (API compatible con OpenAI),
  sin intervención manual.
* La gobernanza no depende del proveedor: los guardrails, la auditoría y la
  supervisión humana se aplican ANTES y DESPUÉS de esta capa. A ambos
  proveedores les llega exactamente el mismo contenido (ya sin datos
  personales) y la auditoría registra `proveedor:modelo` en cada llamada.
* Las herramientas (function-calling) se declaran una vez en formato neutro
  (nombre, descripción, esquema JSON, función Python) y cada proveedor las
  traduce a su propio formato. El bucle de llamadas a herramientas lo
  controla SIREA (tope `IA_MAX_TOOL_CALLS`), no el SDK.

Uso
---
    r = generar(sistema="...", mensajes=[Mensaje.usuario("hola")])
    r.texto, r.proveedor, r.modelo

    # con herramientas (bucle manual en el agente):
    r = generar(sistema, mensajes, herramientas=[Herramienta(...)])
    for ll in r.llamadas: ...  # ejecutar y añadir Mensaje.resultado_herramienta(...)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from src.config import Config


class ProveedorNoDisponibleError(Exception):
    """Ningún proveedor configurado o todos fallaron."""


class ErrorProveedor(Exception):
    """Respuesta de error de un proveedor, ya traducida a un mensaje legible."""

    def __init__(self, proveedor: str, codigo: Optional[int], mensaje: str):
        self.proveedor, self.codigo, self.mensaje = proveedor, codigo, mensaje
        super().__init__(f"{proveedor}: {mensaje}")


def _explicar_groq(status: int, cuerpo: str) -> str:
    detalle = ""
    try:
        detalle = (json.loads(cuerpo).get("error") or {}).get("message") or ""
    except Exception:
        detalle = (cuerpo or "")[:200]
    if status == 401:
        return "GROQ_API_KEY inválida o vencida (revise la clave en console.groq.com)."
    if status == 404 or (status == 400 and "model" in detalle.lower()):
        return f"GROQ_MODEL no existe o fue retirado: {detalle or 'revise el catálogo vigente en console.groq.com'}."
    if status == 429:
        return "Groq: cuota o límite de velocidad agotado; espere e intente de nuevo."
    if status >= 500:
        return "Groq: servidores no disponibles en este momento."
    return f"Groq respondió HTTP {status}: {detalle or 'sin detalle'}"


# ------------------------------------------------------------
# Tipos neutros
# ------------------------------------------------------------

@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: Dict[str, Any]          # esquema JSON ({"type":"object","properties":{...}})
    fn: Callable[..., Any]


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    args: Dict[str, Any]


@dataclass
class Mensaje:
    rol: str                                    # usuario | asistente | herramienta
    contenido: str = ""
    llamadas: List[LlamadaHerramienta] = field(default_factory=list)   # solo rol=asistente
    id_llamada: Optional[str] = None            # solo rol=herramienta
    nombre: Optional[str] = None                # solo rol=herramienta
    bruto: Any = None                           # turno original del proveedor (p. ej. Content de Gemini)

    @staticmethod
    def usuario(texto: str) -> "Mensaje":
        return Mensaje("usuario", texto)

    @staticmethod
    def asistente(texto: str = "", llamadas: Optional[List[LlamadaHerramienta]] = None, bruto: Any = None) -> "Mensaje":
        return Mensaje("asistente", texto, llamadas or [], bruto=bruto)

    @staticmethod
    def resultado_herramienta(llamada: LlamadaHerramienta, resultado: Any) -> "Mensaje":
        return Mensaje("herramienta", json.dumps(resultado, ensure_ascii=False, default=str),
                       id_llamada=llamada.id, nombre=llamada.nombre)


@dataclass
class Respuesta:
    texto: str
    llamadas: List[LlamadaHerramienta]
    proveedor: str
    modelo: str
    bruto: Any = None   # turno original del proveedor, para devolverlo intacto en la siguiente vuelta

    @property
    def etiqueta_modelo(self) -> str:
        """Lo que se guarda en la auditoría: 'gemini:gemini-3.6-flash'."""
        return f"{self.proveedor}:{self.modelo}"


# ------------------------------------------------------------
# Errores transitorios (reintentar / cambiar de proveedor)
# ------------------------------------------------------------

def _es_transitorio(e: BaseException) -> bool:
    if isinstance(e, ErrorProveedor):
        return e.codigo in (408, 429, 500, 502, 503, 504)
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, TimeoutError)):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (408, 409, 425, 429, 500, 502, 503, 504)
    try:
        from google.genai import errors as genai_errors
        if isinstance(e, genai_errors.ServerError):
            return True
        if isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) in (408, 429):
            return True
    except Exception:
        pass
    nombre = type(e).__name__.lower()
    return any(k in nombre for k in ("timeout", "connection", "unavailable", "resourceexhausted"))


# ------------------------------------------------------------
# Gemini
# ------------------------------------------------------------

class _Gemini:
    nombre = "gemini"

    def disponible(self) -> bool:
        return bool(Config.GEMINI_API_KEY)

    def generar(self, sistema: str, mensajes: List[Mensaje], herramientas: Optional[List[Herramienta]],
                temperatura: float) -> Respuesta:
        from google.genai import types
        from src.agentes.cliente_ia import generar_contenido_con_modelo, get_cliente_gemini, modelo_por_defecto

        contents: List[types.Content] = []
        for m in mensajes:
            if m.rol == "usuario":
                contents.append(types.Content(role="user", parts=[types.Part(text=m.contenido or " ")]))
            elif m.rol == "asistente":
                # Gemini 2.5/3.x exige devolver SU turno tal cual (incluye las
                # "thought signatures"); reconstruirlo a mano produce 400.
                if isinstance(m.bruto, types.Content):
                    contents.append(m.bruto)
                    continue
                partes = []
                if m.contenido:
                    partes.append(types.Part(text=m.contenido))
                for ll in m.llamadas:
                    partes.append(types.Part.from_function_call(name=ll.nombre, args=ll.args))
                if partes:
                    contents.append(types.Content(role="model", parts=partes))
            elif m.rol == "herramienta":
                try:
                    datos = json.loads(m.contenido)
                except Exception:
                    datos = m.contenido
                if not isinstance(datos, dict):
                    datos = {"resultado": datos}
                fr = types.FunctionResponse(name=m.nombre or "herramienta", response=datos,
                                            id=(m.id_llamada if m.id_llamada and not str(m.id_llamada).startswith("g") else None))
                parte = types.Part(function_response=fr)
                # Gemini exige que TODAS las respuestas de herramientas de un turno
                # vayan juntas en un solo mensaje (tantas partes como llamadas).
                ultimo = contents[-1] if contents else None
                if ultimo is not None and ultimo.role == "user" and ultimo.parts and all(
                        getattr(pp, "function_response", None) is not None for pp in ultimo.parts):
                    ultimo.parts.append(parte)
                else:
                    contents.append(types.Content(role="user", parts=[parte]))

        config = dict(system_instruction=sistema, temperature=temperatura)
        if herramientas:
            decls = [types.FunctionDeclaration(name=h.nombre, description=h.descripcion, parameters=h.parametros)
                     for h in herramientas]
            config["tools"] = [types.Tool(function_declarations=decls)]
            config["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)

        respuesta, modelo = generar_contenido_con_modelo(
            get_cliente_gemini(), model=modelo_por_defecto(), contents=contents,
            config=types.GenerateContentConfig(**config),
        )
        texto, llamadas = "", []
        bruto = None
        try:
            bruto = respuesta.candidates[0].content
            partes = bruto.parts or []
        except Exception:
            partes = []
        for i, p in enumerate(partes):
            fc = getattr(p, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                llamadas.append(LlamadaHerramienta(id=getattr(fc, "id", None) or f"g{i}", nombre=fc.name,
                                                   args=dict(fc.args or {})))
            elif getattr(p, "text", None) and not getattr(p, "thought", False):
                texto += p.text   # se omiten las partes de "pensamiento" del modelo
        if not texto and not llamadas:
            texto = getattr(respuesta, "text", "") or ""
        return Respuesta(texto=texto, llamadas=llamadas, proveedor=self.nombre, modelo=str(modelo), bruto=bruto)


# ------------------------------------------------------------
# Groq (API compatible con OpenAI, vía httpx)
# ------------------------------------------------------------

class _Groq:
    nombre = "groq"
    _cache_modelos: Optional[List[str]] = None
    _cache_ts: float = 0.0

    def disponible(self) -> bool:
        return bool(Config.GROQ_API_KEY)

    # --- catálogo de modelos accesibles con la clave (GET /models), cache de 10 min ---
    def modelos_disponibles(self) -> List[str]:
        if self._cache_modelos is not None and time.time() - self._cache_ts < 600:
            return self._cache_modelos
        ids: List[str] = []
        try:
            with httpx.Client(timeout=min(Config.IA_TIMEOUT_SEGUNDOS, 15)) as cli:
                r = cli.get(f"{Config.GROQ_BASE_URL.rstrip('/')}/models",
                            headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}"})
                if r.status_code < 400:
                    ids = [str(m.get("id")) for m in (r.json().get("data") or []) if m.get("id")]
        except Exception:
            ids = []
        _Groq._cache_modelos, _Groq._cache_ts = ids, time.time()
        return ids

    def modelo_efectivo(self) -> Tuple[str, Optional[str]]:
        """
        Devuelve (modelo_a_usar, aviso). Usa GROQ_MODEL si existe en el
        catálogo; si no, el primero de GROQ_MODELOS_RESPALDO que sí exista
        (y lo avisa). Si el catálogo no se pudo leer, confía en GROQ_MODEL.
        """
        configurado = (Config.GROQ_MODEL or "").strip()
        disponibles = self.modelos_disponibles()
        if not disponibles:
            return (configurado or (Config.GROQ_MODELOS_RESPALDO[0] if Config.GROQ_MODELOS_RESPALDO else "")), None
        if configurado and configurado in disponibles:
            return configurado, None
        for m in Config.GROQ_MODELOS_RESPALDO:
            if m in disponibles:
                aviso = (f"GROQ_MODEL={configurado!r} no existe en Groq; se usó automáticamente {m}."
                         if configurado else f"GROQ_MODEL vacío; se usó automáticamente {m}.")
                return m, aviso
        texto = [m for m in disponibles if any(k in m for k in ("llama", "gpt-oss", "qwen", "mixtral", "gemma"))
                 and not any(k in m for k in ("whisper", "guard", "tts", "orpheus"))]
        if texto:
            return texto[0], f"GROQ_MODEL={configurado!r} no existe en Groq; se usó {texto[0]} (primero del catálogo)."
        return configurado, None

    def generar(self, sistema: str, mensajes: List[Mensaje], herramientas: Optional[List[Herramienta]],
                temperatura: float) -> Respuesta:
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": sistema}]
        for m in mensajes:
            if m.rol == "usuario":
                msgs.append({"role": "user", "content": m.contenido})
            elif m.rol == "asistente":
                fila: Dict[str, Any] = {"role": "assistant", "content": m.contenido or None}
                if m.llamadas:
                    fila["tool_calls"] = [{
                        "id": ll.id, "type": "function",
                        "function": {"name": ll.nombre, "arguments": json.dumps(ll.args, ensure_ascii=False)},
                    } for ll in m.llamadas]
                msgs.append(fila)
            elif m.rol == "herramienta":
                msgs.append({"role": "tool", "tool_call_id": m.id_llamada, "name": m.nombre, "content": m.contenido})
        modelo, _ = self.modelo_efectivo()
        cuerpo: Dict[str, Any] = {"model": modelo, "messages": msgs, "temperature": temperatura}
        if herramientas:
            cuerpo["tools"] = [{"type": "function", "function": {
                "name": h.nombre, "description": h.descripcion, "parameters": h.parametros}} for h in herramientas]
            cuerpo["tool_choice"] = "auto"
        with httpx.Client(timeout=Config.IA_TIMEOUT_SEGUNDOS) as cli:
            r = cli.post(f"{Config.GROQ_BASE_URL.rstrip('/')}/chat/completions", json=cuerpo,
                         headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}", "Content-Type": "application/json"})
            if r.status_code >= 400:
                raise ErrorProveedor("groq", r.status_code, _explicar_groq(r.status_code, r.text))
            datos = r.json()
        msg = (datos.get("choices") or [{}])[0].get("message") or {}
        llamadas = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            llamadas.append(LlamadaHerramienta(id=str(tc.get("id") or f"q{len(llamadas)}"), nombre=str(fn.get("name")), args=args))
        return Respuesta(texto=str(msg.get("content") or ""), llamadas=llamadas, proveedor=self.nombre,
                         modelo=str(datos.get("model") or modelo))


_PROVEEDORES = {"gemini": _Gemini(), "groq": _Groq()}


def explicar_error(nombre: str, e: BaseException) -> str:
    """Mensaje breve y accionable en español para un fallo de un proveedor."""
    if isinstance(e, ErrorProveedor):
        return e.mensaje
    if nombre == "gemini":
        try:
            from google.genai import errors as genai_errors
            if isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) == 400:
                detalle = getattr(e, "message", None) or str(e)
                return f"Gemini rechazó la solicitud (400): {str(detalle)[:300]}"
        except Exception:
            pass
        try:
            from src.agentes.cliente_ia import mensaje_error_amigable
            return mensaje_error_amigable(e)
        except Exception:
            pass
    if isinstance(e, (httpx.TimeoutException, TimeoutError)):
        return f"{nombre}: no respondió dentro de {Config.IA_TIMEOUT_SEGUNDOS} s (IA_TIMEOUT_SEGUNDOS)."
    if isinstance(e, (httpx.ConnectError, httpx.RemoteProtocolError)):
        return f"{nombre}: sin conexión de red hacia el proveedor."
    return f"{nombre}: {type(e).__name__}: {str(e)[:200]}"


def diagnostico() -> List[Dict[str, Any]]:
    """
    Prueba cada proveedor configurado con una consulta mínima y devuelve
    [{proveedor, modelo, ok, mensaje, ms}]. Lo usa el panel («Probar los
    proveedores de IA»). No pasa por guardrails ni auditoría: es una
    verificación técnica de conectividad y de nombres de modelo.
    """
    salida: List[Dict[str, Any]] = []
    for nombre in Config.IA_PROVEEDOR_ORDEN:
        prov = _PROVEEDORES.get(nombre)
        if prov is None:
            salida.append({"proveedor": nombre, "modelo": "—", "ok": False, "mensaje": "Proveedor desconocido en IA_PROVEEDOR_ORDEN.", "ms": 0})
            continue
        if not prov.disponible():
            falta = "GEMINI_API_KEY" if nombre == "gemini" else "GROQ_API_KEY"
            salida.append({"proveedor": nombre, "modelo": "—", "ok": False, "mensaje": f"Sin configurar: falta {falta} en el .env.", "ms": 0})
            continue
        t0 = time.time()
        aviso_modelo = None
        if nombre == "groq" and hasattr(prov, "modelo_efectivo"):
            try:
                _, aviso_modelo = prov.modelo_efectivo()
            except Exception:
                aviso_modelo = None
        try:
            r = prov.generar("Responde únicamente con la palabra OK.", [Mensaje.usuario("Prueba de conexión.")], None, 0.0)
            msg = f"Respondió «{(r.texto or '').strip()[:40]}»"
            if aviso_modelo:
                msg += f" · {aviso_modelo} Para fijarlo, ponga GROQ_MODEL={r.modelo} en el .env."
            salida.append({"proveedor": nombre, "modelo": r.modelo, "ok": True, "mensaje": msg, "ms": int((time.time() - t0) * 1000)})
        except Exception as e:  # noqa: BLE001
            msg = explicar_error(nombre, e)
            if nombre == "groq" and hasattr(prov, "modelos_disponibles"):
                try:
                    disp = prov.modelos_disponibles()[:8]
                except Exception:
                    disp = []
                if disp:
                    msg += " Modelos disponibles con su clave: " + ", ".join(disp) + "."
            salida.append({"proveedor": nombre, "modelo": Config.GEMINI_MODEL if nombre == "gemini" else Config.GROQ_MODEL,
                           "ok": False, "mensaje": msg, "ms": int((time.time() - t0) * 1000)})
    return salida


# ------------------------------------------------------------
# Punto de entrada con conmutación
# ------------------------------------------------------------

def proveedores_configurados() -> List[str]:
    return [p for p in Config.IA_PROVEEDOR_ORDEN if p in _PROVEEDORES and _PROVEEDORES[p].disponible()]


def generar(sistema: str, mensajes: List[Mensaje], herramientas: Optional[List[Herramienta]] = None,
            temperatura: float = 0.2, solo_proveedor: Optional[str] = None) -> Respuesta:
    """
    Llama al primer proveedor disponible; si falla por una causa transitoria
    (o por cualquier causa, cuando hay otro proveedor detrás), pasa al
    siguiente. Devuelve la respuesta con `proveedor` y `modelo` reales.
    """
    orden = [solo_proveedor] if solo_proveedor else proveedores_configurados()
    orden = [p for p in orden if p in _PROVEEDORES and _PROVEEDORES[p].disponible()]
    if not orden:
        raise ProveedorNoDisponibleError(
            "No hay proveedor de IA configurado: agregue GEMINI_API_KEY (y opcionalmente GROQ_API_KEY + GROQ_MODEL) en el .env.")
    errores: List[str] = []
    for i, nombre in enumerate(orden):
        prov = _PROVEEDORES[nombre]
        try:
            return prov.generar(sistema, mensajes, herramientas, temperatura)
        except Exception as e:  # noqa: BLE001
            errores.append(f"{nombre}: {explicar_error(nombre, e)}")
            ultimo = i == len(orden) - 1
            if ultimo:
                break
            # Con otro proveedor detrás, se conmuta ante cualquier fallo del
            # anterior (transitorio o no): el objetivo es no dejar sin
            # respuesta a la persona. El detalle queda en la auditoría.
            time.sleep(0.5)
            continue
    raise ProveedorNoDisponibleError("Todos los proveedores fallaron → " + " | ".join(errores))


def ejecutar_con_herramientas(sistema: str, mensajes: List[Mensaje], herramientas: List[Herramienta],
                              temperatura: float = 0.1, max_llamadas: Optional[int] = None):
    """
    Bucle de function-calling controlado por SIREA (no por el SDK):
      modelo -> ¿pide herramientas? -> se ejecutan (solo lectura) -> se
      devuelven los resultados -> modelo ... hasta que responde con texto o
      se alcanza el tope. Devuelve (Respuesta final, nombres de herramientas usadas).

    La conversación sigue con el proveedor que contestó primero (los turnos
    del modelo se devuelven en su formato nativo). Si ese proveedor falla a
    mitad de la conversación, se reinicia desde cero con el siguiente.
    """
    tope = max_llamadas or Config.IA_MAX_TOOL_CALLS
    por_nombre = {h.nombre: h for h in herramientas}

    def _ejecutar(ll: LlamadaHerramienta, usadas: List[str]) -> Any:
        h = por_nombre.get(ll.nombre)
        if h is None:
            return {"error": f"herramienta desconocida: {ll.nombre}"}
        try:
            resultado = h.fn(**(ll.args or {}))
        except TypeError:
            resultado = {"error": "argumentos no válidos para la herramienta"}
        except Exception as e:  # noqa: BLE001
            resultado = {"error": f"la herramienta falló: {type(e).__name__}"}
        usadas.append(ll.nombre)
        return resultado

    def _bucle(solo: Optional[str]):
        usadas: List[str] = []
        hist = list(mensajes)
        fijo = solo
        for _ in range(tope + 1):
            r = generar(sistema, hist, herramientas, temperatura, solo_proveedor=fijo)
            fijo = r.proveedor   # una vez que un proveedor contestó, la conversación sigue con él
            if not r.llamadas or len(usadas) >= tope:
                if r.llamadas and not r.texto:
                    r.texto = ("No pude completar la consulta dentro del límite de verificaciones permitido. "
                               "Intente con una pregunta más acotada.")
                return r, usadas
            hist.append(Mensaje.asistente(r.texto, r.llamadas, bruto=r.bruto))
            for ll in r.llamadas:
                hist.append(Mensaje.resultado_herramienta(ll, _ejecutar(ll, usadas)))
        return Respuesta("No pude completar la consulta dentro del límite permitido.", [], fijo or "—", "—"), usadas

    orden = proveedores_configurados()
    errores: List[str] = []
    intentos = [None] + [p for p in orden[1:]]   # primero automático; luego los de respaldo desde cero
    for solo in intentos:
        try:
            return _bucle(solo)
        except ProveedorNoDisponibleError as e:
            errores.append(str(e))
        except Exception as e:  # noqa: BLE001
            nombre = solo or (orden[0] if orden else "?")
            errores.append(f"{nombre}: {explicar_error(nombre, e)}")
    raise ProveedorNoDisponibleError("Todos los proveedores fallaron → " + " | ".join(errores))
