# src/email_cierres.py
"""
Correos del proceso programado: cierre de corte, recordatorios de validación,
aviso de «ya validado», resumen de cumplimiento y acuse de respaldo.

Cada función recibe el EmailSender (o cualquier objeto con `_enviar_correo`),
así se pueden probar sin servidor de correo. Los datos que escribe una persona
(nombres, mensajes) siempre se escapan.
"""

import re
from typing import Dict, List, Optional, Tuple

from src import email_plantillas as P
from src.solicitudes_password import fecha_lima

_esc = P.esc


def _plano(html_: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_ or "")).strip()


def _multilinea(texto: str) -> str:
    return _esc(texto or "").replace("\r\n", "\n").replace("\n", "<br>")


def _filas_propuesta(c: Dict) -> List[tuple]:
    """Filas de la tabla con la propuesta del sistema."""
    return [
        ("Semana cerrada", f"Semana {c.get('semana_cerrada')} · {_esc(P.fecha_legible(c.get('corte_cerrado'), True))}"),
        ("Semana activa ahora", f"Semana {c.get('semana_propuesta') or '—'}"
         + (" (provisional)" if c.get("estado") != "VALIDADA" else "")),
        ("Nuevo corte", _esc(P.fecha_legible(c.get("corte_propuesto"), True))),
    ]


def _aviso_notas(c: Dict) -> str:
    nota = (c.get("nota") or "").strip()
    return P.caja_aviso("warn", "Revise este punto", _multilinea(nota)) if nota else ""


# ---------------------------------------------------------------- cierre

def enviar_aviso_cierre(sender, correo: str, nombre: str, c: Dict, n_recordatorios: int,
                        adjuntos: Optional[List[Tuple[str, bytes, str]]] = None) -> Tuple[bool, str]:
    """Primer aviso: el corte se cerró y el sistema propone la nueva semana y el nuevo corte."""
    asunto = f"Cierre de la semana {c.get('semana_cerrada')} – Valide la semana propuesta – SIREA"
    aplicado = bool(c.get("aplicado"))
    intro = (
        f"Por medio del presente, le comunicamos que se cerró el corte de la <strong>semana {c.get('semana_cerrada')}</strong>."
        + (" El sistema ya cambió la configuración a la semana y al corte que se muestran abajo, "
           "<strong>de forma provisional</strong>." if aplicado else
           " El sistema <strong>no modificó</strong> la configuración y necesita que usted la defina.")
    )
    cuerpo = P.tabla_desde_pares(_filas_propuesta(c))
    cuerpo += _aviso_notas(c)
    cuerpo += P.caja_aviso(
        "warn", "Requiere su validación",
        "Ingrese al panel de administración, sección <strong>Validación de semana</strong>, y confirme o corrija "
        "la semana y la fecha de corte (los feriados pueden mover el corte). Basta con que <strong>una</strong> persona lo valide; "
        "las demás recibirán un aviso."
        f"<br>Si nadie lo valida, recibirá hasta <strong>{n_recordatorios} recordatorios</strong> el día hábil siguiente al corte.")
    if adjuntos:
        cuerpo += P.caja_aviso(
            "info", "Resumen de cumplimiento adjunto (borrador)",
            "Se adjunta el resumen por red de la semana cerrada. Aún puede haber envíos tardíos; "
            "<strong>no se enviará a la entidad externa hasta que una persona de la OIIS lo valide</strong> en el panel.")
    html_ = P.envolver("ambar", "Cierre de corte", f"Se cerró la semana {c.get('semana_cerrada')}",
                       P.saludo(_esc(nombre), intro), cuerpo)
    plano = (f"CIERRE DE LA SEMANA {c.get('semana_cerrada')}\n\nEstimado/a {nombre}:\n\n{_plano(intro)}\n\n"
             f"Semana activa ahora: {c.get('semana_propuesta')} (provisional)\n"
             f"Nuevo corte: {P.fecha_legible(c.get('corte_propuesto'), True)}\n\n"
             f"{c.get('nota') or ''}\n\nValide en el panel: Validación de semana.")
    return sender._enviar_correo(correo, asunto, html_, plano, adjuntos=adjuntos)


def enviar_recordatorio_validacion(sender, correo: str, nombre: str, c: Dict, numero: int, total: int) -> Tuple[bool, str]:
    asunto = f"Recordatorio {numero} de {total}: valide la semana propuesta – SIREA"
    intro = (f"Por medio del presente, le recordamos que la <strong>semana {c.get('semana_propuesta')}</strong> y su corte "
             "siguen <strong>sin validar</strong>. Rigen de forma provisional.")
    cuerpo = P.tabla_desde_pares(_filas_propuesta(c))
    cuerpo += _aviso_notas(c)
    cuerpo += P.caja_aviso(
        "warn", f"Recordatorio {numero} de {total}",
        "Ingrese al panel, sección <strong>Validación de semana</strong>. "
        + ("Este es el último recordatorio por correo; el aviso seguirá visible en el panel."
           if numero >= total else "Dejará de recibir recordatorios en cuanto alguien valide."))
    html_ = P.envolver("ambar", "Recordatorio", "Falta validar la semana",
                       P.saludo(_esc(nombre), intro), cuerpo)
    plano = (f"RECORDATORIO {numero} DE {total}\n\nEstimado/a {nombre}:\n\n{_plano(intro)}\n\n"
             f"Semana provisional: {c.get('semana_propuesta')}\nCorte: {P.fecha_legible(c.get('corte_propuesto'), True)}\n\n"
             "Valide en el panel: Validación de semana.")
    return sender._enviar_correo(correo, asunto, html_, plano)


def enviar_aviso_validado(sender, correo: str, nombre: str, c: Dict) -> Tuple[bool, str]:
    """Una sola vez: otra persona ya validó; no hay nada que hacer."""
    por = c.get("validado_por_nombre") or c.get("validado_por") or "otro administrador"
    cuando = fecha_lima(c.get("fecha_validacion"))
    asunto = f"Semana {c.get('semana_validada')} ya fue validada – SIREA"
    intro = (f"Por medio del presente, le informamos que <strong>{_esc(por)}</strong> ya validó la semana "
             f"<strong>{c.get('semana_validada')}</strong> el {_esc(cuando)} (hora de Lima). "
             "<strong>No necesita hacer nada.</strong>")
    filas = [("Semana activa", f"Semana {c.get('semana_validada')}"),
             ("Fecha de corte", _esc(P.fecha_legible(c.get("corte_validado"), True))),
             ("Validó", f"{_esc(por)} · {_esc(cuando)}")]
    cuerpo = P.tabla_desde_pares(filas)
    if c.get("hubo_correccion"):
        cuerpo += P.caja_aviso(
            "info", "Se corrigió la propuesta del sistema",
            f"El sistema había propuesto la semana {c.get('semana_propuesta')} con corte "
            f"{_esc(P.fecha_legible(c.get('corte_propuesto'), True))}.")
    html_ = P.envolver("azul", "Validación completada", "La semana ya fue validada",
                       P.saludo(_esc(nombre), intro), cuerpo)
    plano = (f"SEMANA {c.get('semana_validada')} YA VALIDADA\n\nEstimado/a {nombre}:\n\n{_plano(intro)}\n\n"
             f"Corte: {P.fecha_legible(c.get('corte_validado'), True)}")
    return sender._enviar_correo(correo, asunto, html_, plano)


# ---------------------------------------------------------------- resumen

def enviar_resumen(sender, correo: str, nombre: str, semana: int, anio: int, mensaje: str,
                   remitente: str, adjuntos: List[Tuple[str, bytes, str]],
                   borrador: bool = False) -> Tuple[bool, str]:
    """Resumen de cumplimiento por red (con el Excel adjunto). `mensaje` es texto libre."""
    asunto = (f"Resumen de cumplimiento por red – Semana {semana} de {anio}"
              + (" (borrador)" if borrador else "") + " – EsSalud")
    intro = (f"Por medio del presente, se remite el <strong>resumen de cumplimiento por red</strong> de la "
             f"semana {semana} del año {anio}.")
    cuerpo = ""
    if (mensaje or "").strip():
        cuerpo += P.caja_aviso("info", "Mensaje", _multilinea(mensaje))
    cuerpo += P.tabla_desde_pares([
        ("Semana", f"Semana {semana} · {anio}"),
        ("Archivo adjunto", _esc(adjuntos[0][0]) if adjuntos else "—"),
        ("Remite", _esc(remitente or "OIIS")),
    ])
    html_ = P.envolver("azul", "Resumen de cumplimiento", f"Semana {semana} · {anio}",
                       P.saludo(_esc(nombre), intro), cuerpo)
    plano = (f"RESUMEN DE CUMPLIMIENTO POR RED – SEMANA {semana} DE {anio}\n\nEstimado/a {nombre}:\n\n{_plano(intro)}\n\n"
             f"{mensaje or ''}\n\nRemite: {remitente or 'OIIS'}")
    return sender._enviar_correo(correo, asunto, html_, plano, adjuntos=adjuntos)


# ---------------------------------------------------------------- respaldo

def enviar_acuse_respaldo(sender, correo: str, nombre: str, info: Dict) -> Tuple[bool, str]:
    """Acuse del respaldo: `info` = {ok, nombre, destino, detalle, total_filas, archivos, cuando, motivo}."""
    ok = bool(info.get("ok"))
    asunto = (f"Respaldo completado – {info.get('nombre')} – SIREA" if ok
              else f"No se pudo completar el respaldo – {info.get('nombre')} – SIREA")
    intro = ("Por medio del presente, se informa que el respaldo programado del sistema <strong>se completó correctamente</strong>."
             if ok else
             "Por medio del presente, se informa que el respaldo programado <strong>no se pudo completar</strong>.")
    filas = [("Respaldo", _esc(info.get("nombre"))),
             ("Destino", _esc(info.get("destino") or "—")),
             ("Fecha y hora", _esc(info.get("cuando") or "—")),
             ("Registros", str(info.get("total_filas", 0)))]
    cuerpo = P.tabla_desde_pares(filas)
    if ok:
        items = [f"{_esc(a)}" for a in info.get("archivos", [])]
        if items:
            cuerpo += P.bloque_titulo("Contenido") + P.lista(items)
        cuerpo += P.caja_aviso("info", "Qué incluye",
                               "Envíos recibidos (control de lo recibido), configuración, exclusiones de centros y años epidemiológicos. "
                               "No incluye contraseñas ni claves cifradas; los archivos ZIP ya están en su carpeta de Drive.")
    else:
        cuerpo += P.caja_aviso("bad", "Motivo", _multilinea(info.get("motivo") or "Error no especificado."))
        cuerpo += P.caja_aviso("warn", "Qué hacer",
                               "Revise la carpeta BACKUPS y el permiso de la cuenta de servicio; el sistema ya agotó sus reintentos automáticos. "
                               "Puede respaldar manualmente desde la sección Respaldos.")
    html_ = P.envolver("azul" if ok else "rojo", "Respaldo",
                       "Respaldo completado" if ok else "Respaldo con error", P.saludo(_esc(nombre), intro), cuerpo)
    plano = (f"{'RESPALDO COMPLETADO' if ok else 'RESPALDO CON ERROR'}\n\nEstimado/a {nombre}:\n\n{_plano(intro)}\n\n"
             f"Respaldo: {info.get('nombre')}\nDestino: {info.get('destino')}\nRegistros: {info.get('total_filas', 0)}\n"
             + ("" if ok else f"Motivo: {info.get('motivo')}\n"))
    return sender._enviar_correo(correo, asunto, html_, plano)
