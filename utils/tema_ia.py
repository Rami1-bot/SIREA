# utils/tema_ia.py
"""
Componentes visuales de los asistentes de IA de SIREA.

Regla de color (manual de senaletica de EsSalud):
  * LILA  = "Diagnostico": todo lo que produjo un asistente de IA y todavia
            no valido una persona (borradores, chips, tarjetas de agente).
  * VERDE = "Tratamiento": lo que una persona ya valido.
  * GRIS  = agente evaluado y no autorizado / inactivo.

Todo texto que venga de datos o del modelo pasa por `esc()` antes de
insertarse en HTML. Los bloques se muestran con `tema.mostrar()` (compacta
el HTML para que Markdown no lo rompa).
"""

from __future__ import annotations

import html as _html
from typing import Iterable, Optional

from utils.tema import LILA, TONOS, chip, icono, mostrar


def esc(valor, maximo: Optional[int] = None) -> str:
    """Escapa HTML y, opcionalmente, recorta con puntos suspensivos."""
    texto = "" if valor is None else str(valor)
    if maximo and len(texto) > maximo:
        texto = texto[: maximo - 1].rstrip() + "…"
    return _html.escape(texto, quote=True)


def parrafos(texto: str) -> str:
    """Convierte texto plano (con saltos de linea) en parrafos y listas HTML seguros."""
    bloques, lista = [], []

    def cerrar_lista():
        nonlocal lista
        if lista:
            bloques.append("<ul>" + "".join(f"<li>{x}</li>" for x in lista) + "</ul>")
            lista = []

    for linea in (texto or "").splitlines():
        l = linea.strip()
        if not l:
            cerrar_lista()
            continue
        if l[:2] in ("- ", "* ", "• "):
            lista.append(esc(l[2:]))
        else:
            cerrar_lista()
            bloques.append(f"<p>{esc(l)}</p>")
    cerrar_lista()
    return "".join(bloques) or "<p>—</p>"


# ------------------------------------------------------------
# chips
# ------------------------------------------------------------

def chip_ia(texto: str = "Generado por IA") -> str:
    return chip(texto, "ia", "ia")


def chip_validado(texto: str = "Validado") -> str:
    return chip(texto, "ok", "check")


def chip_proveedor(proveedor: Optional[str], modelo: Optional[str] = None) -> str:
    """Chip pequeno que dice que proveedor/modelo respondio (transparencia)."""
    if not proveedor:
        return ""
    nombre = {"gemini": "Gemini", "groq": "Groq"}.get(str(proveedor).lower(), str(proveedor))
    detalle = f" · {esc(modelo, 40)}" if modelo else ""
    return f'<span class="sirea-prov">{icono("ia", 12, LILA, 2.2)}respondió {esc(nombre)}{detalle}</span>'


def semaforo(nivel: str) -> str:
    """nivel: 'permitido' | 'restringido' | 'no_permitido'."""
    color, texto = {
        "permitido": ("#1E6B3A", "Uso permitido"),
        "restringido": ("#C9A000", "Uso restringido · piloto"),
        "no_permitido": ("#B42318", "No permitido en esta fase"),
        "retirado": ("#6B7785", "Retirado"),
    }.get(nivel, ("#9AA6B2", "Sin clasificar"))
    return f'<span class="sirea-semaforo" style="color:{color}"><i style="background:{color}"></i>{texto}</span>'


# ------------------------------------------------------------
# bloques
# ------------------------------------------------------------

def chip_contingencia(texto: str = "Plantilla de contingencia · sin IA") -> str:
    return chip(texto, "mute", "alerta")


def borrador(texto: str, titulo: str = "Borrador generado por IA", meta: str = "",
             validado: bool = False, validado_por: Optional[str] = None,
             proveedor: Optional[str] = None, modelo: Optional[str] = None,
             contingencia: bool = False) -> str:
    """
    Tarjeta de borrador. Lila con borde punteado mientras esta pendiente;
    verde con borde continuo cuando una persona lo valido; gris si el texto
    salio de la plantilla de contingencia (ningun proveedor de IA respondio).
    """
    clase = "sirea-borrador validado" if validado else "sirea-borrador"
    if contingencia and not validado:
        estado = chip_contingencia()
        pie = ("Texto armado por el sistema con la plantilla de contingencia porque ningún proveedor de IA respondió. "
               "Pendiente de validación; no es un documento oficial hasta que una persona lo apruebe.")
        ico = "alerta"
    else:
        estado = chip_validado(f"Validado por {esc(validado_por, 40)}" if validado_por else "Validado") if validado else chip_ia()
        pie = ("Texto validado por una persona; puede usarse." if validado
               else "Borrador generado por IA — pendiente de validación. No es un documento oficial hasta que una persona lo apruebe.")
        ico = "check" if validado else "ia"
    return f"""
    <div class="{clase}">
      <div class="sirea-borrador-cab">
        <div><b>{esc(titulo)}</b>{(' <span class="sirea-borrador-meta">' + esc(meta) + '</span>') if meta else ''}</div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">{estado}{chip_proveedor(proveedor, modelo)}</div>
      </div>
      {parrafos(texto)}
      <div class="sirea-pie-ia">{icono(ico, 14, "#55307F" if not validado else "#1E6B3A", 2.2)}{pie}</div>
    </div>
    """


def tarjeta_agente(nombre: str, rol: str, descripcion: str, nivel: str,
                   estado_chip: str = "", extra_chips: Iterable[str] = (), gris: bool = False) -> str:
    """Tarjeta de un asistente en el panel: nombre, clasificacion de uso, estado."""
    clase = {"permitido": "verde", "restringido": "ambar", "no_permitido": "rojo", "retirado": "gris"}.get(nivel, "")
    if gris:
        clase = "gris"
    chips = "".join([estado_chip] + list(extra_chips))
    return f"""
    <div class="sirea-agente {clase}">
      <div class="sirea-agente-cab">
        <div><div class="sirea-agente-sub">{esc(rol)}</div><div class="sirea-agente-nom">{esc(nombre)}</div></div>
        {icono("ia", 22, "#9AA6B2" if gris else LILA, 2)}
      </div>
      <div class="sirea-agente-txt">{esc(descripcion)}</div>
      <div class="sirea-agente-pie">{semaforo(nivel)}{chips}</div>
    </div>
    """


def burbuja_usuario(texto: str) -> str:
    return f'<div class="sirea-chat-u">{esc(texto)}</div>'


def burbuja_asistente(texto: str, proveedor: Optional[str] = None, modelo: Optional[str] = None,
                      herramientas: Iterable[str] = ()) -> str:
    usadas = ", ".join(esc(h) for h in herramientas)
    pie = "Respuesta generada por IA sobre datos del sistema"
    if usadas:
        pie += f" · consultó: {usadas}"
    return (f'<div class="sirea-chat-a">{parrafos(texto)}'
            f'<div class="sirea-pie-ia">{icono("ia", 13, "#55307F", 2.2)}{pie} {chip_proveedor(proveedor, modelo)}</div></div>')


def mostrar_html(html: str) -> None:
    mostrar(html)
