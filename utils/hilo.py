# utils/hilo.py
"""
Intercambio de mensajes entre una red y la OIIS (solicitudes de cambio de
contraseña), dibujado como conversación. Se usa en las dos pantallas: la de la
red y la del administrador; cada una ve sus propios mensajes a la derecha.
"""

import html
from typing import Dict, List

from src.solicitudes_password import fecha_lima


def _texto(valor) -> str:
    return html.escape(str(valor or ""), quote=True).replace("\r\n", "\n").replace("\n", "<br>")


def hilo_html(mensajes: List[Dict], propio: str) -> str:
    """
    mensajes: filas de solicitudes_password_mensajes.
    propio:   'RED' o 'ADMIN' = quién está mirando (sus mensajes salen a la derecha).
    """
    if not mensajes:
        return '<div class="sire-vacio">Aún no hay mensajes.</div>'
    out = []
    for m in mensajes:
        tipo = str(m.get("autor_tipo", "")).upper()
        fecha = fecha_lima(m.get("fecha"))
        if tipo == "SISTEMA":
            out.append(f'<div class="sire-msg-sis"><span>{_texto(m.get("mensaje"))} · {fecha}</span></div>')
            continue
        lado = "yo" if tipo == propio else "otro"
        rol = "Red asistencial" if tipo == "RED" else "OIIS"
        out.append(
            f'<div class="sire-msg sire-msg-{lado}"><div class="sire-msg-cab"><b>{_texto(m.get("autor"))}</b>'
            f'<span>{rol} · {fecha}</span></div><div class="sire-msg-txt">{_texto(m.get("mensaje"))}</div></div>'
        )
    return f'<div class="sire-hilo">{"".join(out)}</div>'
