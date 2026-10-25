# src/agentes/acciones.py
"""
Catálogo de ACCIONES que el Agente Operativo puede proponer.

El modelo no escribe correos ni toca la base: propone acciones con un
esquema fijo. Cada tipo de acción tiene aquí:

  normalizar(cruda, exp)  convierte la propuesta del modelo en un payload
                          limpio, completando red/semana/año desde el
                          expediente (el modelo no los decide).
  validar(payload, exp)   reglas determinísticas: si devuelve un motivo,
                          la propuesta se DESCARTA y queda en la traza.
  preparar(payload, exp)  datos que resuelve el SISTEMA, no el modelo
                          (p. ej. a qué correo va el recordatorio). La
                          persona los ve y puede corregirlos antes de aprobar.
  clave(payload)          identidad para no proponer dos veces lo mismo.
  ejecutar(payload, actor) la acción real, solo tras la aprobación humana.

Reglas transversales: ningún texto con datos personales, enlaces ni el
token canario; longitudes acotadas; tipos fuera de la skill, descartados.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agentes import guardrails

_URL = re.compile(r"https?://|www\.", re.I)


def _texto(valor: Any, maximo: int) -> str:
    """
    Limpia caracteres de control y etiquetas falsas, pero NO redacta datos
    personales: si el modelo los escribió, la propuesta debe DESCARTARSE
    (validar), no enviarse con «[CORREO OMITIDO]» en el texto.
    """
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(valor or ""))
    t = re.sub(r"<\s*/?\s*(system|instruction|instrucciones|tool|function|prompt|datos_sistema)[^>]*>", "", t, flags=re.I)
    return re.sub(r"[ \t]+", " ", t).strip()[:maximo]


def _problema_de_texto(etiqueta: str, texto: str) -> Optional[str]:
    if not texto:
        return None
    if guardrails.detectar_pii(texto):
        return f"{etiqueta} contiene datos personales"
    if _URL.search(texto):
        return f"{etiqueta} contiene un enlace"
    if guardrails.TOKEN_CANARIO in texto:
        return f"{etiqueta} filtra la configuración interna"
    return None


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _parse(valor) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ------------------------------------------------------------
# Destinatarios (los resuelve el sistema, nunca el modelo)
# ------------------------------------------------------------

def responsables_de_red(red: str, semanas: int = 8, maximo: int = 3) -> List[Dict[str, Any]]:
    """
    Responsables del envío de la red: las personas que de verdad enviaron
    por ella en las últimas `semanas` (sin repetir), la más reciente
    primero. [{'correo', 'nombre', 'envios', 'ultimo'}]. Los resuelve el
    SISTEMA desde los envíos; el modelo nunca elige ni escribe correos.
    """
    try:
        from src.db_manager import get_db_manager
        envios = get_db_manager().obtener_envios(red=red, limit=200) or []
    except Exception:
        return []
    limite = _ahora() - timedelta(weeks=semanas)
    vistos: Dict[str, Dict[str, Any]] = {}
    for e in sorted(envios, key=lambda e: str(e.get("fecha_envio") or ""), reverse=True):
        correo = str(e.get("correo_usuario") or "").strip().lower()
        f = _parse(e.get("fecha_envio"))
        if not correo or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo) or (f and f < limite):
            continue
        if correo not in vistos:
            nombre = f"{e.get('nombre_usuario') or ''} {e.get('apellido_usuario') or ''}".strip() or "responsable de la red"
            vistos[correo] = {"correo": correo, "nombre": nombre, "envios": 0, "ultimo": str(e.get("fecha_envio") or "")[:10],
                              "nombres": str(e.get("nombre_usuario") or "").strip(),
                              "apellidos": str(e.get("apellido_usuario") or "").strip()}
        vistos[correo]["envios"] += 1
    return list(vistos.values())[:maximo]


def responsable_de_red(red: str, semanas: int = 8) -> Dict[str, str]:
    """Quien envió más recientemente por esa red (últimas `semanas`): {'correo', 'nombre'} o vacío."""
    lista = responsables_de_red(red, semanas, 1)
    return {"correo": lista[0]["correo"], "nombre": lista[0]["nombre"]} if lista else {}


# ------------------------------------------------------------
# Borrador formal y control de tono (SIREA 3.2)
# ------------------------------------------------------------

def _unir(items: List[str]) -> str:
    items = [str(x) for x in items if x]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1] if items else ""


def borrador_formal(pendientes_por_tipo: List[Dict], vencido: bool, preventivo_por_historial: bool = False) -> str:
    """
    Párrafo formal y respetuoso que el sistema arma con los datos exactos
    (sin IA). Es el borrador por defecto: la IA puede proponer otro y la
    persona siempre puede editarlo antes de enviar.
    """
    partes = ["Como parte del seguimiento semanal que realiza la OIIS, le informamos lo siguiente."]
    parciales = [p for p in pendientes_por_tipo if not p.get("sin_ningun_envio")]
    if parciales:
        recibidos = [f"{_unir(p.get('recibidos') or [])} del {p['centro']}" for p in parciales[:3] if p.get("recibidos")]
        if recibidos:
            partes.append("A la fecha hemos recibido los reportes de " + "; ".join(recibidos) + ".")
    pend = [f"{_unir(p.get('faltan') or [])} del {p['centro']}" for p in pendientes_por_tipo[:6]]
    if pend:
        extra = len(pendientes_por_tipo) - 6
        partes.append("Quedaría pendiente: " + "; ".join(pend) + (f"; y {extra} centro(s) más (ver el detalle)" if extra > 0 else "") + ".")
    if vencido:
        partes.append("Le agradeceremos regularizar el envío a través de SIREA a la brevedad posible.")
    else:
        partes.append("Le agradeceremos realizar el envío a través de SIREA antes de la fecha límite.")
    if preventivo_por_historial:
        partes.append("Quedamos atentos por si requiere apoyo con alguno de estos reportes.")
    else:
        partes.append("Si tuviera algún inconveniente, no dude en comunicarse con nosotros.")
    return " ".join(partes)[:900]


# Lo interno (comparaciones, historial de atrasos) es SOLO para el administrador: nunca va en un correo a la red.
_RE_COMPARACION = re.compile(
    r"\b(unica|unicas|ultima|ultimas) (red|redes)\b|\b(demas|otras|resto de (las )?) ?redes\b|\bresto de las redes\b"
    r"|\branking\b|\bcompar(a|o)|\ben relacion (a|con) (las )?redes\b|\bpromedio de (las )?redes\b"
    r"|\b\d+ de (las )?(ultimas )?\d+ semanas\b|\b(suele|de nuevo|otra vez|nuevamente|reiterad|reincid|habitualmente|con frecuencia)"
    r"|\bsemanas? (anteriores|pasadas) (tarde|con atraso)|\bhistorial de (atraso|incumplimiento)"
    r"|\bla unica que\b|\btodas las (demas )?redes\b|\bvarias semanas\b|\bya son \w+ semanas\b|\bcomo (otras|las demas)\b"
    r"|\bsemana tras semana\b|\buna vez mas\b", re.I)


def problema_de_tono(texto: str, red: str = "", otras_redes: Optional[List[str]] = None) -> Optional[str]:
    """Motivo si el párrafo compara a la red, le reprocha su historial o usa un tono inadecuado; si no, None."""
    if not texto:
        return None
    t = guardrails.normalizar(texto)
    if _RE_COMPARACION.search(t):
        return "compara a la red con otras o le recuerda su historial (eso es solo para el administrador)"
    propia = guardrails.normalizar(red or "")
    for otra in otras_redes or []:
        n = guardrails.normalizar(str(otra))
        if n and n != propia and len(n) >= 4 and re.search(r"\b" + re.escape(n) + r"\b", t):
            return "menciona a otra red"
    for palabra in guardrails._TONO_NORM:
        if palabra and re.search(r"\b" + re.escape(palabra), t):
            return "usa un tono inadecuado para una red hermana"
    return None


# ------------------------------------------------------------
# Registro único de recordatorios (Notificaciones + agente)
# ------------------------------------------------------------

_RE_LOG_RED = re.compile(r"Red:\s*(.+?)\s+-\s+Semana\s+(\d+)/(\d+)", re.I)


def detalle_log_recordatorio(correo: str, red: str, semana, anio, tipo: str, referencia: str = "") -> str:
    """Formato ÚNICO del log ENVIO_RECORDATORIO (lo usan Notificaciones y el agente)."""
    ref = f" - {referencia}" if referencia else ""
    return f"Recordatorio enviado a {correo} - Red: {red} - Semana {semana}/{anio} - Tipo: {tipo}{ref}"


def recordatorios_manuales(red: Optional[str] = None, dias: int = 14) -> List[Dict]:
    """
    Recordatorios enviados A MANO desde «Notificaciones» (tabla logs,
    acción ENVIO_RECORDATORIO). Los que envió el agente llevan «ACC-n» y se
    omiten aquí porque ya están en agente_acciones. Un envío a «Todas las
    redes» cuenta para cada red.
    """
    try:
        from src.db_manager import get_db_manager
        desde = (_ahora() - timedelta(days=dias)).isoformat()
        filas = (get_db_manager().supabase.table("logs").select("fecha,detalle,usuario")
                 .eq("accion", "ENVIO_RECORDATORIO").gte("fecha", desde).order("fecha", desc=True)
                 .limit(500).execute().data or [])
    except Exception:
        return []
    out = []
    for f in filas:
        det = str(f.get("detalle") or "")
        if re.search(r"\bACC-\d+", det):
            continue
        m = _RE_LOG_RED.search(det)
        if not m:
            continue
        red_log = m.group(1).strip()
        if red and red_log not in (red, "Todas las redes", "Todas"):
            continue
        out.append({"tipo": "RECORDATORIO_RED", "estado": "EJECUTADA", "origen": "manual",
                    "semana": int(m.group(2)), "anio": int(m.group(3)), "red": red_log,
                    "creada_at": str(f.get("fecha") or ""), "ejecutada_at": str(f.get("fecha") or ""),
                    "por": f.get("usuario")})
    return out


def ultimo_recordatorio(red: str, dias: int = 7) -> Optional[Dict]:
    """El recordatorio más reciente a la red (manual o del agente ya ejecutado), o None."""
    lista = list(recordatorios_manuales(red, dias))
    try:
        from src.db_manager import get_db_manager
        desde = (_ahora() - timedelta(days=dias)).isoformat()
        for f in (get_db_manager().supabase.table("agente_acciones").select("ejecutada_at,semana,decidida_por")
                  .eq("tipo", "RECORDATORIO_RED").eq("estado", "EJECUTADA").eq("red", red)
                  .gte("ejecutada_at", desde).limit(50).execute().data or []):
            lista.append({"origen": "agente", "ejecutada_at": f.get("ejecutada_at"), "semana": f.get("semana"),
                          "por": f.get("decidida_por")})
    except Exception:
        pass
    lista = [x for x in lista if _parse(x.get("ejecutada_at"))]
    return max(lista, key=lambda x: _parse(x["ejecutada_at"])) if lista else None


# ------------------------------------------------------------
# Definición de tipos
# ------------------------------------------------------------

@dataclass
class TipoAccion:
    nombre: str
    titulo: str
    descripcion: str
    contexto: str                                   # 'red' | 'observacion' | 'cualquiera'
    normalizar: Callable[[Dict, Dict], Dict]
    validar: Callable[[Dict, Dict], Optional[str]]
    clave: Callable[[Dict], str]
    preparar: Callable[[Dict, Dict], Dict]
    ejecutar: Optional[Callable[[Dict, Dict], Tuple[bool, str]]]
    en_cola: bool = True                            # SIN_ACCION no entra a la cola


def _base(cruda: Dict, exp: Dict) -> Dict:
    return {"red": exp.get("red"), "semana": exp.get("semana"), "anio": exp.get("anio"),
            "justificacion": _texto(cruda.get("justificacion"), 400)}


# ---- RECORDATORIO_RED ------------------------------------------------------

def _pendientes_de(exp: Dict) -> List[Dict]:
    return [x for x in (exp.get("pendientes_por_tipo") or []) if isinstance(x, dict) and x.get("centro")]


def _norm_recordatorio(c: Dict, exp: Dict) -> Dict:
    p = _base(c, exp)
    reales = list(exp.get("faltantes") or []) + [x["centro"] for x in _pendientes_de(exp)]
    por_minus = {f.strip().lower(): f for f in reales}
    pedidos = c.get("centros_pendientes") or []
    if isinstance(pedidos, str):
        pedidos = [x for x in pedidos.split(",")]
    p["centros_pendientes"] = list(dict.fromkeys(por_minus.get(str(x).strip().lower(), str(x).strip())
                                                 for x in pedidos if str(x).strip()))
    vencido = (exp.get("horas_al_corte") is not None and exp["horas_al_corte"] < 0)
    p["tono"] = "ATRASADO" if vencido else "PREVENTIVO"          # el tono lo fija el reloj, no el modelo
    p["tono_propuesto"] = str(c.get("tono") or "").upper()
    # El detalle por tipo lo pone el SISTEMA (datos exactos), solo de los centros del recordatorio
    elegidos = {x.lower() for x in p["centros_pendientes"]}
    p["pendientes_por_tipo"] = [{k: x.get(k) for k in ("centro", "faltan", "recibidos", "sin_ningun_envio")}
                                for x in _pendientes_de(exp) if x["centro"].lower() in elegidos][:200]
    if p["pendientes_por_tipo"]:   # un centro pendiente sin detalle por tipo no puede quedar fuera del correo
        con_detalle = {x["centro"].lower() for x in p["pendientes_por_tipo"]}
        p["pendientes_por_tipo"] += [{"centro": c, "faltan": ["todos sus reportes"], "recibidos": [], "sin_ningun_envio": True}
                                     for c in p["centros_pendientes"] if c.lower() not in con_detalle]
    perfil = exp.get("perfil_red") or {}
    preventivo_hist = bool(perfil.get("suele_atrasarse") or perfil.get("suele_esperar_recordatorio")
                           or perfil.get("tipo_que_suele_faltar"))
    mensaje = _texto(c.get("mensaje_personalizado"), 900)
    p["mensaje_origen"] = "ia" if mensaje else "plantilla"
    motivo_tono = problema_de_tono(mensaje, exp.get("red") or "", exp.get("_otras_redes"))
    if motivo_tono:
        p["aviso_mensaje"] = f"Se reemplazó el párrafo de la IA por el borrador del sistema: {motivo_tono}."
        mensaje, p["mensaje_origen"] = "", "plantilla"
    if not mensaje:
        mensaje = borrador_formal(p["pendientes_por_tipo"] or [{"centro": x, "faltan": ["todos sus reportes"],
                                                                "sin_ningun_envio": True} for x in p["centros_pendientes"]],
                                  vencido, preventivo_hist)
    p["mensaje_personalizado"] = mensaje
    return p


def _val_recordatorio(p: Dict, exp: Dict) -> Optional[str]:
    if exp.get("tipo_caso") != "red":
        return "un recordatorio solo aplica a una red"
    if not p["centros_pendientes"]:
        return "el recordatorio no indica centros pendientes"
    reales = set(exp.get("faltantes") or []) | {x["centro"] for x in _pendientes_de(exp)}
    inventados = [c for c in p["centros_pendientes"] if c not in reales]
    if inventados:
        return f"centros que no están pendientes según el sistema: {', '.join(inventados[:3])}"
    if not reales:
        return "la red ya no tiene centros pendientes"
    for a in exp.get("acciones_previas") or []:
        if a.get("tipo") == "RECORDATORIO_RED" and a.get("estado") in ("EJECUTADA", "PROPUESTA"):
            hace = _ahora() - (_parse(a.get("ejecutada_at") or a.get("creada_at")) or _ahora() - timedelta(days=99))
            if hace < timedelta(hours=20):
                return "ya hay un recordatorio a esta red en las últimas 20 horas"
    if sum(1 for a in exp.get("acciones_previas") or []
           if a.get("tipo") == "RECORDATORIO_RED" and a.get("estado") == "EJECUTADA"
           and a.get("semana") == exp.get("semana")) >= 3:
        return "ya se enviaron 3 recordatorios esta semana: corresponde escalar"
    return _problema_de_texto("El mensaje", p["mensaje_personalizado"])


def _prep_recordatorio(p: Dict, exp: Dict) -> Dict:
    resp = responsables_de_red(p["red"]) if p.get("red") else []
    if not resp:
        return {"destinatario": "", "nombre_destinatario": "", "copias": "",
                "destinatario_origen": "sin envíos recientes de la red: escriba el correo"}
    return {"destinatario": resp[0]["correo"], "nombre_destinatario": resp[0]["nombre"],
            "copias": ", ".join(r["correo"] for r in resp[1:]),
            "destinatario_origen": (f"quien envió por la red más recientemente ({resp[0]['ultimo']})"
                                    + (f"; en copia, {len(resp) - 1} responsable(s) más que enviaron en las últimas 8 semanas"
                                       if len(resp) > 1 else ""))}


def lista_copias(valor) -> List[str]:
    if isinstance(valor, (list, tuple)):
        items = valor
    else:
        items = re.split(r"[,;\s]+", str(valor or ""))
    return list(dict.fromkeys(x.strip().lower() for x in items if x and x.strip()))


def _args_recordatorio(p: Dict) -> Dict[str, Any]:
    from src.config import Config
    return dict(destinatario=p["destinatario"], nombre_usuario=p.get("nombre_destinatario") or "responsable de la red",
                red=p["red"], semana=int(p["semana"]), fecha_limite=Config.get_fecha_corte(),
                centros_pendientes=p["centros_pendientes"], anio=int(p["anio"]), tipo=p["tono"],
                mensaje_adicional=p.get("mensaje_personalizado") or None,
                pendientes_por_tipo=p.get("pendientes_por_tipo") or None,
                cc=[c for c in lista_copias(p.get("copias")) if c != str(p["destinatario"]).lower()] or None)


def vista_previa_recordatorio(p: Dict) -> Tuple[str, str]:
    """(asunto, texto) exactamente como lo recibirá la red, para que la persona lo revise antes de aprobar."""
    from src.email_sender import get_email_sender
    args = _args_recordatorio({**p, "destinatario": p.get("destinatario") or "destinatario@por-definir"})
    args.pop("destinatario")
    cc = args.pop("cc")
    asunto, _html, plano = get_email_sender().componer_recordatorio(**args)
    if cc:
        plano = f"Con copia a: {', '.join(cc)}\n\n" + plano
    return asunto, plano


def _ejec_recordatorio(p: Dict, actor: Dict) -> Tuple[bool, str]:
    if not p.get("destinatario"):
        return False, "Falta el correo del destinatario."
    from src.email_sender import get_email_sender
    ok, msg = get_email_sender().enviar_recordatorio(**_args_recordatorio(p))
    if ok:   # mismo registro que «Notificaciones»: así ninguno de los dos repite
        try:
            from src.db_manager import get_db_manager
            get_db_manager().registrar_log(usuario=actor.get("usuario", "SYSTEM"), accion="ENVIO_RECORDATORIO",
                                           detalle=detalle_log_recordatorio(p["destinatario"], p["red"], p["semana"],
                                                                            p["anio"], p["tono"], f"ACC-{p.get('_accion_id')}"))
        except Exception:
            pass
    return ok, msg


# ---- SOLICITAR_CORRECCION --------------------------------------------------

def _norm_correccion(c: Dict, exp: Dict) -> Dict:
    p = _base(c, exp)
    p.update(observacion_id=exp.get("observacion_id"), codigo=exp.get("codigo"),
             motivo_correccion=_texto(c.get("motivo_correccion"), 700))
    return p


def _val_correccion(p: Dict, exp: Dict) -> Optional[str]:
    if exp.get("tipo_caso") != "observacion":
        return "una solicitud de corrección solo aplica a una observación"
    if exp.get("motivo") == "FALLA":
        return "una falla técnica no se corrige pidiéndole algo a la red"
    if len(p["motivo_correccion"]) < 40:
        return "el pedido de corrección es demasiado corto para que la red sepa qué hacer"
    return _problema_de_texto("El pedido de corrección", p["motivo_correccion"])


def _prep_correccion(p: Dict, exp: Dict) -> Dict:
    return {"destinatario": exp.get("_correo_remitente", ""), "nombre_destinatario": exp.get("_remitente", ""),
            "destinatario_origen": "quien hizo el envío observado"}


def _ejec_correccion(p: Dict, actor: Dict) -> Tuple[bool, str]:
    if not p.get("destinatario"):
        return False, "Falta el correo del destinatario."
    from src.email_sender import get_email_sender
    ok, msg = get_email_sender().enviar_solicitud_correccion(
        p["destinatario"], p.get("nombre_destinatario") or "responsable del envío", int(p["semana"] or 0),
        p["motivo_correccion"], str(p.get("codigo") or ""), anio=int(p["anio"]) if p.get("anio") else None)
    if ok and p.get("observacion_id"):
        from src.observaciones import get_observaciones
        get_observaciones().marcar_revisadas([p["observacion_id"]], actor.get("usuario", "SYSTEM"))
    return ok, msg


# ---- MARCAR_REVISADA -------------------------------------------------------

def _norm_revisada(c: Dict, exp: Dict) -> Dict:
    p = _base(c, exp)
    p.update(observacion_id=exp.get("observacion_id"), codigo=exp.get("codigo"), nota=_texto(c.get("nota"), 300))
    return p


def _val_revisada(p: Dict, exp: Dict) -> Optional[str]:
    if exp.get("tipo_caso") != "observacion":
        return "solo se marcan observaciones"
    if exp.get("motivo") == "FALLA":
        return "una falla técnica no se da por revisada: se reintenta o se escala"
    if len(p["nota"]) < 10:
        return "falta la nota que explica por qué se da por revisada"
    return _problema_de_texto("La nota", p["nota"])


def _ejec_revisada(p: Dict, actor: Dict) -> Tuple[bool, str]:
    from src.observaciones import get_observaciones
    n = get_observaciones().marcar_revisadas([p["observacion_id"]], actor.get("usuario", "SYSTEM"))
    return (n > 0), ("Observación marcada como revisada." if n else "La observación ya estaba revisada.")


# ---- REINTENTAR_FALLA ------------------------------------------------------

def _norm_reintento(c: Dict, exp: Dict) -> Dict:
    p = _base(c, exp)
    p.update(observacion_id=exp.get("observacion_id"), codigo=exp.get("codigo"))
    return p


def _val_reintento(p: Dict, exp: Dict) -> Optional[str]:
    if exp.get("motivo") != "FALLA":
        return "solo se reintentan fallas técnicas"
    if not exp.get("reintentable"):
        return "esta falla no se puede reintentar automáticamente"
    return None


def _ejec_reintento(p: Dict, actor: Dict) -> Tuple[bool, str]:
    from src.observaciones import get_observaciones
    obs = get_observaciones()
    fila = next((f for f in obs.listar(revisada=False, limite=500) if str(f.get("id")) == str(p["observacion_id"])), None)
    if not fila:
        return False, "La falla ya no está pendiente."
    from app_pages.usuario_logica import reintentar_reemplazo
    ok, msg = reintentar_reemplazo(fila, actor.get("usuario", "SYSTEM"))
    if ok:
        obs.marcar_revisadas([fila.get("id")], actor.get("usuario", "SYSTEM"))
    return ok, msg


# ---- ESCALAR ---------------------------------------------------------------

def _norm_escalar(c: Dict, exp: Dict) -> Dict:
    p = _base(c, exp)
    p.update(observacion_id=exp.get("observacion_id"), codigo=exp.get("codigo"), motivo=_texto(c.get("motivo"), 400))
    return p


def _val_escalar(p: Dict, exp: Dict) -> Optional[str]:
    if len(p["motivo"]) < 10:
        return "falta explicar qué debe decidir la persona"
    return _problema_de_texto("El motivo", p["motivo"])


def _ejec_escalar(p: Dict, actor: Dict) -> Tuple[bool, str]:
    from src.db_manager import get_db_manager
    get_db_manager().registrar_log(usuario=actor.get("usuario", "SYSTEM"), accion="AGENTE_ESCALAMIENTO_ASUMIDO",
                                   detalle=f"red={p.get('red')}; {p.get('motivo')}"[:500])
    return True, "Escalamiento asumido por una persona (queda en el historial)."


# ---- NOTA_MEMORIA ----------------------------------------------------------

def _norm_nota(c: Dict, exp: Dict) -> Dict:
    p = _base(c, exp)
    try:
        dias = int(c.get("vigencia_dias") or 60)
    except (TypeError, ValueError):
        dias = 60
    p.update(nota=_texto(c.get("nota"), 300), vigencia_dias=max(7, min(dias, 180)))
    return p


def _val_nota(p: Dict, exp: Dict) -> Optional[str]:
    if not p.get("red"):
        return "una nota de memoria debe ser de una red"
    if len(p["nota"]) < 15:
        return "la nota es demasiado corta para ser útil"
    return _problema_de_texto("La nota", p["nota"])


def _ejec_nota(p: Dict, actor: Dict) -> Tuple[bool, str]:
    from src.agentes import memoria
    ok = memoria.agregar(p["red"], p["nota"], fuente="agente", creada_por=actor.get("usuario", "SYSTEM"),
                         vigencia_dias=p["vigencia_dias"], accion_id=p.get("_accion_id"))
    return ok, ("Nota guardada en la memoria de la red." if ok else "No se pudo guardar la nota.")


# ---- SIN_ACCION ------------------------------------------------------------

def _norm_sin(c: Dict, exp: Dict) -> Dict:
    return _base(c, exp)


TIPOS: Dict[str, TipoAccion] = {
    "RECORDATORIO_RED": TipoAccion(
        "RECORDATORIO_RED", "Recordatorio a la red", "Correo oficial de recordatorio con los centros pendientes.",
        "red", _norm_recordatorio, _val_recordatorio,
        lambda p: f"RECORDATORIO_RED|{p['red']}|{p['anio']}|{p['semana']}", _prep_recordatorio, _ejec_recordatorio),
    "SOLICITAR_CORRECCION": TipoAccion(
        "SOLICITAR_CORRECCION", "Pedir corrección", "Correo de solicitud de corrección a quien hizo el envío.",
        "observacion", _norm_correccion, _val_correccion,
        lambda p: f"OBS|{p['observacion_id']}", _prep_correccion, _ejec_correccion),
    "MARCAR_REVISADA": TipoAccion(
        "MARCAR_REVISADA", "Dar por revisada", "Cierra la observación con una nota.",
        "observacion", _norm_revisada, _val_revisada,
        lambda p: f"OBS|{p['observacion_id']}", lambda p, e: {}, _ejec_revisada),
    "REINTENTAR_FALLA": TipoAccion(
        "REINTENTAR_FALLA", "Reintentar falla técnica", "Reintenta mover los archivos del reemplazo.",
        "observacion", _norm_reintento, _val_reintento,
        lambda p: f"OBS|{p['observacion_id']}", lambda p, e: {}, _ejec_reintento),
    "ESCALAR": TipoAccion(
        "ESCALAR", "Escalar a una persona", "Caso que requiere decisión humana; el agente no propone ejecutar nada.",
        "cualquiera", _norm_escalar, _val_escalar,
        lambda p: f"ESCALAR|{p.get('observacion_id') or p.get('red')}|{p.get('anio')}|{p.get('semana')}",
        lambda p, e: {}, _ejec_escalar),
    "NOTA_MEMORIA": TipoAccion(
        "NOTA_MEMORIA", "Nota de memoria", "Guarda un dato útil sobre la red para próximas corridas.",
        "cualquiera", _norm_nota, _val_nota,
        lambda p: f"NOTA|{p['red']}|{hashlib.sha256(p['nota'].lower().encode()).hexdigest()[:12]}", lambda p, e: {}, _ejec_nota),
    "SIN_ACCION": TipoAccion(
        "SIN_ACCION", "Sin acción", "El agente decidió no actuar (queda en la traza con su razón).",
        "cualquiera", _norm_sin, lambda p, e: None, lambda p: "", lambda p, e: {}, None, en_cola=False),
}


def procesar_propuesta(cruda: Dict, exp: Dict, permitidas: tuple,
                       preparar: bool = True) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Convierte una propuesta del modelo en una acción lista para la cola.
    Devuelve (accion, None) o (None, motivo_de_descarte).
    """
    tipo = str((cruda or {}).get("tipo") or "").strip().upper()
    if tipo not in TIPOS:
        return None, f"tipo de acción desconocido: {tipo or '(vacío)'}"
    if tipo not in permitidas:
        return None, f"la skill no permite la acción {tipo}"
    t = TIPOS[tipo]
    if t.contexto not in ("cualquiera", exp.get("tipo_caso")):
        return None, f"{tipo} no aplica a este tipo de caso"
    try:
        payload = t.normalizar(cruda, exp)
    except Exception as e:  # noqa: BLE001
        return None, f"propuesta mal formada ({type(e).__name__})"
    motivo = t.validar(payload, exp)
    if motivo:
        return None, motivo
    if preparar:          # en las evaluaciones no se consulta la base (casos ficticios)
        payload.update(t.preparar(payload, exp))
    return {"tipo": tipo, "payload": payload, "clave_unica": t.clave(payload), "en_cola": t.en_cola,
            "justificacion": payload.get("justificacion", "")}, None


def revalidar_para_ejecutar(tipo: str, payload: Dict) -> Optional[str]:
    """Antes de ejecutar (puede haber pasado tiempo o la persona editó): reglas de texto de nuevo."""
    for campo in ("mensaje_personalizado", "motivo_correccion", "nota", "motivo"):
        m = _problema_de_texto(campo, str(payload.get(campo) or ""))
        if m:
            return m
    patron = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if tipo in ("RECORDATORIO_RED", "SOLICITAR_CORRECCION") and not re.match(patron, str(payload.get("destinatario") or "")):
        return "el correo del destinatario no es válido"
    malos = [c for c in lista_copias(payload.get("copias")) if not re.match(patron, c)]
    if malos:
        return f"correo en copia no válido: {malos[0]}"
    if len(lista_copias(payload.get("copias"))) > 5:
        return "como máximo 5 correos en copia"
    return None
