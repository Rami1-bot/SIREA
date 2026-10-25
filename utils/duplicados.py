# utils/duplicados.py
"""
Envíos duplicados.

Cuando una red vuelve a enviar un centro que ya envió en la misma semana,
el archivo no se mezcla con el envío original: se guarda en la carpeta de
duplicados de Drive y el registro queda marcado. La marca va al comienzo de
la observación del envío (no hace falta ninguna columna nueva en la base de
datos), y desde aquí se reconoce en todo el sistema.
"""

from typing import Dict, Iterable, List

PREFIJO_DUPLICADO = "ENVÍO DUPLICADO"


def es_duplicado(envio: Dict) -> bool:
    """True si el envío fue registrado como duplicado."""
    observacion = str((envio or {}).get("observacion") or "").strip().upper()
    return observacion.startswith(PREFIJO_DUPLICADO)


PREFIJO_REEMPLAZADO = "ENVÍO REEMPLAZADO"


def es_reemplazado(envio: Dict) -> bool:
    """True si el envío fue reemplazado por otro posterior (su archivo quedó en la carpeta REEMPLAZADOS)."""
    observacion = str((envio or {}).get("observacion") or "").strip().upper()
    return observacion.startswith(PREFIJO_REEMPLAZADO)


def solo_originales(envios: Iterable[Dict]) -> List[Dict]:
    """Los envíos vigentes: ni duplicados ni reemplazados (los que cuentan para el avance de la red)."""
    return [e for e in (envios or []) if not es_duplicado(e) and not es_reemplazado(e)]


def observacion_duplicado(codigos_previos: Iterable[str], tardio: bool = False, extra: str = "") -> str:
    """Texto de la observación con la que se registra un envío duplicado."""
    codigos = [str(c) for c in codigos_previos if c and c != "N/A"]
    texto = f"{PREFIJO_DUPLICADO} · repite un envío ya recibido"
    if codigos:
        texto += f" ({', '.join(codigos)})"
    texto += ". El archivo se guardó en la carpeta de duplicados para revisión de la OIIS."
    if tardio:
        texto += " Además, se envió después de la fecha de corte."
    if extra:
        texto += f" | {extra}"
    return texto
