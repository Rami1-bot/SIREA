# src/calendario_epi.py
"""
Calendario epidemiológico (semanas de domingo a sábado).

Regla estándar (CDC / MINSA): la semana 1 de un año es la primera semana que
tiene al menos 4 días dentro de ese año; es decir, la que contiene el 4 de
enero. Con eso el calendario se calcula solo para cualquier año:

    2025 -> semana 1 empieza el 29/12/2024   (52 semanas)
    2026 -> semana 1 empieza el 04/01/2026   (52 semanas)
    2027 -> semana 1 empieza el 03/01/2027   (52 semanas)

OJO: esto solo SUGIERE las fechas de un año nuevo. La SEMANA ACTIVA y la FECHA
DE CORTE nunca se calculan: las define una persona del panel (hay feriados que
mueven el corte).

Funciones puras (sin Streamlit ni base de datos) para poder probarlas.
"""

from datetime import date, datetime, timedelta
from typing import Optional, Tuple, Union

_Fecha = Union[date, datetime, str]


def _a_fecha(valor: _Fecha) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def inicio_anio_epi(anio: int) -> date:
    """Domingo con el que empieza la semana 1 del año epidemiológico."""
    cuatro_enero = date(int(anio), 1, 4)
    # weekday(): lunes=0 ... domingo=6 -> días que hay que retroceder hasta el domingo
    return cuatro_enero - timedelta(days=(cuatro_enero.weekday() + 1) % 7)


def semanas_anio_epi(anio: int) -> int:
    """52 o 53, según cuándo empieza el año siguiente."""
    return (inicio_anio_epi(int(anio) + 1) - inicio_anio_epi(int(anio))).days // 7


def fin_anio_epi(anio: int) -> date:
    """Último día (sábado) de la última semana del año epidemiológico."""
    return inicio_anio_epi(int(anio)) + timedelta(days=7 * semanas_anio_epi(anio) - 1)


def fin_desde_inicio(inicio: _Fecha, semanas: int) -> date:
    """Sábado que cierra la última semana de un año que empieza en `inicio`."""
    return _a_fecha(inicio) + timedelta(days=7 * int(semanas) - 1)


def rango_semana(inicio_anio: _Fecha, semana: int) -> Tuple[date, date]:
    """(domingo, sábado) de la semana `semana` de un año que empieza en `inicio_anio`."""
    desde = _a_fecha(inicio_anio) + timedelta(days=(int(semana) - 1) * 7)
    return desde, desde + timedelta(days=6)


def semana_de_fecha(fecha: _Fecha, inicio_anio: _Fecha, semanas: int) -> Optional[int]:
    """Semana (1..semanas) a la que pertenece `fecha`, o None si cae fuera del año."""
    n = (_a_fecha(fecha) - _a_fecha(inicio_anio)).days // 7 + 1
    return n if 1 <= n <= int(semanas) else None


def formatear_rango(desde: date, hasta: date) -> str:
    """'27/09 – 03/10/2026'."""
    return f"{desde:%d/%m} – {hasta:%d/%m/%Y}"


def parsear_corte(texto) -> Optional[datetime]:
    """
    Fecha de corte guardada como texto -> datetime SIN zona (hora de Lima).
    Acepta 'AAAA-MM-DD HH:MM:SS', 'AAAA-MM-DD HH:MM' y 'AAAA-MM-DD' (esta última
    se toma como 23:59:59). Devuelve None si no se entiende.
    """
    t = str(texto or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(t, fmt)
            return dt.replace(hour=23, minute=59, second=59) if fmt == "%Y-%m-%d" else dt
        except ValueError:
            continue
    return None
