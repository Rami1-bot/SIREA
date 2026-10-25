# src/agentes/cliente_ia.py
"""
Cliente compartido de Gemini (Google AI Studio) para los 3 agentes.
"""

import time
from typing import Any, List, Optional, Tuple

import httpx
from google import genai
from google.genai import errors as genai_errors

from src.config import Config

# Errores TRANSITORIOS de Gemini que normalmente se resuelven solos con un
# reintento AL MISMO MODELO: ServerError cubre los 5xx (503 "high demand"
# es el que mas aparece), y los de httpx cubren cortes de red a mitad de
# la solicitud.
_ERRORES_GEMINI_TRANSITORIOS = (
    genai_errors.ServerError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)

# Modelos de RESPALDO si el modelo pedido (GEMINI_MODEL) se queda sin
# cuota (429) o ya no existe -- Google los retira cada cierto tiempo
# (ej. gemini-2.0-flash fue retirado; el 404 de esa vez ya recomendaba
# usar gemini-3.6-flash). Se prueban en este orden, saltando el que ya
# se pidio como principal. Revisar/actualizar esta lista de vez en
# cuando en https://ai.google.dev/gemini-api/docs/models si vuelve a
# pasar.
MODELOS_RESPALDO_DEFECTO: List[str] = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
]


class AgenteNoConfiguradoError(Exception):
    """
    Se lanza cuando se intenta usar un agente sin GEMINI_API_KEY configurada
    en el .env. Las páginas de agentes deben capturar esto y mostrar un
    aviso amigable (st.warning) en vez de dejar que truene con un traceback.
    """
    pass


_cliente: Optional["genai.Client"] = None


def get_cliente_gemini() -> "genai.Client":
    """
    Devuelve un cliente de Gemini reutilizable (se crea una sola vez por
    sesión del proceso). Lanza AgenteNoConfiguradoError si falta la key.
    """
    global _cliente

    if not Config.gemini_configurado():
        raise AgenteNoConfiguradoError(
            "Falta GEMINI_API_KEY en el archivo .env. Consigue una clave "
            "gratuita en https://aistudio.google.com/app/apikey, agrégala "
            "como GEMINI_API_KEY=tu_clave en el .env de este proyecto (el "
            "de la versión demo, no el de producción) y reinicia la app."
        )

    if _cliente is None:
        _cliente = genai.Client(api_key=Config.GEMINI_API_KEY)

    return _cliente


def modelo_por_defecto() -> str:
    return Config.GEMINI_MODEL


def _es_error_de_cuota_o_modelo_retirado(error: BaseException) -> bool:
    """
    429 (RESOURCE_EXHAUSTED: se acabo la cuota de ESE modelo) o 404
    (NOT_FOUND: Google retiro ese modelo). En ambos casos reintentar el
    MISMO modelo no sirve de nada, pero probar el SIGUIENTE modelo de
    la cadena de respaldo si puede funcionar.
    """
    return (
        isinstance(error, genai_errors.ClientError)
        and getattr(error, "code", None) in (429, 404)
    )


def generar_contenido(
    cliente: "genai.Client",
    intentos: int = 3,
    espera_inicial: float = 2.0,
    modelos_respaldo: Optional[List[str]] = None,
    **kwargs: Any,
):
    """Compatibilidad: igual que generar_contenido_con_modelo pero devuelve solo la respuesta."""
    respuesta, _ = generar_contenido_con_modelo(
        cliente, intentos=intentos, espera_inicial=espera_inicial,
        modelos_respaldo=modelos_respaldo, **kwargs,
    )
    return respuesta


def generar_contenido_con_modelo(
    cliente: "genai.Client",
    intentos: int = 3,
    espera_inicial: float = 2.0,
    modelos_respaldo: Optional[List[str]] = None,
    **kwargs: Any,
) -> Tuple[Any, str]:
    """
    Igual que generar_contenido pero devuelve (respuesta, modelo_usado):
    la auditoría exige registrar el modelo que REALMENTE respondió, que
    puede ser uno de respaldo si el principal estaba sin cuota.

    Llama a cliente.models.generate_content(**kwargs) con dos capas de
    resiliencia:

    1) Reintentos con backoff exponencial (2s, 4s...) ante errores
       TRANSITORIOS del modelo pedido (503 "high demand", cortes de
       red) -- se reintenta el MISMO modelo.
    2) Si el modelo pedido esta sin cuota (429) o fue retirado por
       Google (404), prueba automaticamente con el siguiente modelo de
       MODELOS_RESPALDO_DEFECTO, sin intervencion manual.

    kwargs debe incluir 'model' (como antes lo pasaban los agentes). El
    modelo pedido siempre se intenta primero.

    Los 3 agentes deben llamar esta funcion en vez de
    cliente.models.generate_content directamente.
    """
    modelo_pedido = kwargs.pop("model", None)
    cadena_respaldo = (
        modelos_respaldo if modelos_respaldo is not None
        else (getattr(Config, "GEMINI_MODELOS_RESPALDO", None) or MODELOS_RESPALDO_DEFECTO)
    )
    modelos_a_probar = ([modelo_pedido] if modelo_pedido else []) + [
        m for m in cadena_respaldo if m != modelo_pedido
    ]

    ultimo_error: Optional[BaseException] = None
    for modelo in modelos_a_probar:
        for intento in range(max(intentos, 1)):
            try:
                return cliente.models.generate_content(model=modelo, **kwargs), modelo
            except _ERRORES_GEMINI_TRANSITORIOS as e:
                ultimo_error = e
                if intento < intentos - 1:
                    time.sleep(espera_inicial * (2 ** intento))
            except genai_errors.ClientError as e:
                ultimo_error = e
                if _es_error_de_cuota_o_modelo_retirado(e):
                    break  # no reintentar este modelo: pasar al siguiente
                raise  # otro 4xx (ej. API key invalida): no se arregla cambiando de modelo

    raise ultimo_error if ultimo_error is not None else RuntimeError(
        "generar_contenido: no se pudo completar la solicitud (sin excepcion capturada)"
    )


def mensaje_error_amigable(error: BaseException) -> str:
    """
    Traduce las excepciones tecnicas de Gemini (JSON crudo, codigos
    HTTP) a un mensaje breve y accionable en español para mostrar en la
    interfaz. El detalle tecnico completo (str(error)) sigue
    disponible para quien lo necesite -- las paginas lo muestran aparte
    en un expander, no lo escondas del todo.
    """
    if isinstance(error, AgenteNoConfiguradoError):
        return str(error)

    if isinstance(error, genai_errors.ClientError):
        codigo = getattr(error, "code", None)
        if codigo == 429:
            return (
                "🚫 Se agotó la cuota gratuita de Gemini por hoy para el "
                "modelo configurado (y también para los de respaldo). "
                "Espera a que se reinicie mañana, o revisa tus límites en "
                "https://aistudio.google.com/rate-limit."
            )
        if codigo == 404:
            return (
                "⚠️ El modelo configurado en GEMINI_MODEL ya no existe "
                "(Google lo retiró) y tampoco funcionó ninguno de los "
                "modelos de respaldo. Revisa los modelos vigentes en "
                "https://ai.google.dev/gemini-api/docs/models y actualiza "
                "tu .env."
            )
        if codigo == 400:
            detalle = str(getattr(error, "message", None) or error)[:300]
            if "model" in detalle.lower() and ("not found" in detalle.lower() or "invalid" in detalle.lower()):
                return (
                    "⚠️ El nombre del modelo en GEMINI_MODEL no es válido "
                    f"(revisa comillas o espacios en el .env). Detalle: {detalle}"
                )
            return f"⚠️ Gemini rechazó la solicitud (400): {detalle}"
        if codigo == 403:
            return (
                "🔒 Tu API key de Gemini no tiene permiso para esta "
                "operación. Revisa GEMINI_API_KEY en tu .env en "
                "https://aistudio.google.com/app/apikey."
            )
        return f"⚠️ Gemini rechazó la solicitud (código {codigo}): {getattr(error, 'message', None) or error}"

    if isinstance(error, genai_errors.ServerError):
        return (
            "⏳ Los servidores de Gemini están saturados en este momento. "
            "Ya se reintentó automáticamente varias veces sin éxito -- "
            "intenta de nuevo en un minuto."
        )

    if isinstance(error, (httpx.RemoteProtocolError, httpx.ConnectError,
                          httpx.ReadTimeout, httpx.ConnectTimeout)):
        return (
            "📶 Se cortó la conexión de red hacia Gemini o la base de "
            "datos. Ya se reintentó automáticamente -- revisa tu conexión "
            "a internet e intenta de nuevo."
        )

    return f"❌ Ocurrió un error inesperado: {error}"