# src/feriados_pe.py
"""
Feriados nacionales del Perú (orientativos).

Sirve solo para ADVERTIR cuando la fecha de corte propuesta o un recordatorio
caen en feriado. La lista puede cambiar por decreto (feriados puente, días no
laborables), así que nunca se usa para decidir sola: la persona que valida
siempre puede corregir.

Fechas fijas + Jueves y Viernes Santo (calculados desde la Pascua).
"""

from datetime import date, timedelta
from typing import Dict, Optional

_FIJOS = {
    (1, 1): "Año Nuevo",
    (5, 1): "Día del Trabajo",
    (6, 7): "Batalla de Arica y Día de la Bandera",
    (6, 29): "San Pedro y San Pablo",
    (7, 23): "Día de la Fuerza Aérea del Perú",
    (7, 28): "Fiestas Patrias",
    (7, 29): "Fiestas Patrias",
    (8, 6): "Batalla de Junín",
    (8, 30): "Santa Rosa de Lima",
    (10, 8): "Combate de Angamos",
    (11, 1): "Día de Todos los Santos",
    (12, 8): "Inmaculada Concepción",
    (12, 9): "Batalla de Ayacucho",
    (12, 25): "Navidad",
}


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def feriados(anio: int) -> Dict[date, str]:
    """Todos los feriados del año: {fecha: nombre}."""
    res = {date(anio, m, d): n for (m, d), n in _FIJOS.items()}
    p = _pascua(anio)
    res[p - timedelta(days=3)] = "Jueves Santo"
    res[p - timedelta(days=2)] = "Viernes Santo"
    return res


def nombre_feriado(fecha: date) -> Optional[str]:
    """Nombre del feriado si `fecha` lo es; None si no."""
    return feriados(fecha.year).get(fecha)


def es_habil(fecha: date) -> bool:
    """Lunes a viernes que no es feriado."""
    return fecha.weekday() < 5 and nombre_feriado(fecha) is None


def siguiente_habil(fecha: date) -> date:
    """El primer día hábil DESPUÉS de `fecha`."""
    d = fecha + timedelta(days=1)
    while not es_habil(d):
        d += timedelta(days=1)
    return d
