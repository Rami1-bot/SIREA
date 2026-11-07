# src/avance_nacional.py
"""
Avance nacional de la semana para la portada (SIREA 3.5).

Antes la portada hacía dos consultas por red (catálogo de centros y envíos) en cada visita.
Ahora:
  * `calcular()` hace TRES consultas en total (catálogo de centros, exclusiones y envíos
    de la semana, de 1000 en 1000) y reparte en memoria con la misma regla que «Mi progreso»;
  * el proceso programado lo deja precalculado cada 5 minutos en la tabla configuracion
    (`guardar_en_cache`), y la portada lo lee de ahí si tiene menos de 10 minutos.

Solo cifras agregadas: la portada es pública y no muestra redes individuales.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

CLAVE_CACHE = "avance_nacional_cache"
VIGENCIA = timedelta(minutes=10)
CADA = timedelta(minutes=5)


def _paginado(consulta_fn, por_pagina: int = 1000) -> List[Dict]:
    filas, desde = [], 0
    while True:
        lote = consulta_fn(desde, desde + por_pagina - 1) or []
        filas.extend(lote)
        if len(lote) < por_pagina:
            return filas
        desde += por_pagina


def calcular(anio: int, semana: int, db=None) -> Optional[Dict]:
    """Cifras de la semana o None si no hay centros (o si algo falla)."""
    try:
        from src.db_manager import get_db_manager
        from src.data_loader import get_data_loader
        from app_pages.usuario_logica import _lista_centros_red, avance_desde
        db = db or get_db_manager()
        catalogo = _paginado(lambda a, b: db.supabase.table("centros_con_red").select("*")
                             .order("id").range(a, b).execute().data)
        por_red: Dict[str, List[Dict]] = {}
        for c in catalogo:
            por_red.setdefault(str(c.get("red_nombre") or ""), []).append(c)
        excluidos = db.obtener_todas_las_exclusiones_agrupadas() or {}
        envios = _paginado(lambda a, b: db.supabase.table("envios").select("red,centros")
                           .eq("anio", anio).eq("semana", semana).order("id").range(a, b).execute().data)
        envios_por_red: Dict[str, List[Dict]] = {}
        for e in envios:
            envios_por_red.setdefault(str(e.get("red") or ""), []).append(e)

        total = enviados = completas = proceso = sin_envio = 0
        for red in get_data_loader().obtener_redes():
            excl = excluidos.get(red, [])
            activos = _lista_centros_red(red, excl, centros_db=por_red.get(red, []))
            if not activos:
                continue
            av = avance_desde(activos, envios_por_red.get(red, []), len(excl))
            n_total, n_env = av["total"], len(av["enviados"])
            total += n_total
            enviados += n_env
            if n_env >= n_total:
                completas += 1
            elif n_env > 0:
                proceso += 1
            else:
                sin_envio += 1
        if total == 0:
            return None
        return {"total": total, "enviados": enviados, "pct": int(round(enviados * 100 / total)),
                "redes_completas": completas, "redes_proceso": proceso, "redes_sin_envio": sin_envio}
    except Exception as e:  # noqa: BLE001  la portada se muestra igual, sin cifras
        print(f"[avance] no se pudo calcular el avance nacional: {type(e).__name__}: {e}")
        return None


def leer_cache(anio: int, semana: int, db=None, ahora: Optional[datetime] = None) -> Optional[Dict]:
    """Cifras precalculadas por el proceso programado, si son de esa semana y tienen menos de 10 minutos."""
    try:
        from src.db_manager import get_db_manager
        v = (db or get_db_manager()).obtener_configuracion(CLAVE_CACHE)
        if not v:
            return None
        d = json.loads(v)
        if int(d.get("anio") or 0) != int(anio) or int(d.get("semana") or 0) != int(semana):
            return None
        cuando = datetime.fromisoformat(str(d.get("calculado")))
        if (ahora or datetime.now(timezone.utc)) - cuando > VIGENCIA:
            return None
        return d.get("datos")
    except Exception:
        return None


def guardar_en_cache(anio: int, semana: int, db=None, ahora: Optional[datetime] = None) -> Optional[Dict]:
    """Lo llama el proceso programado. Devuelve las cifras guardadas (o None)."""
    from src.db_manager import get_db_manager
    db = db or get_db_manager()
    datos = calcular(anio, semana, db=db)
    if datos is None:
        return None
    marca = (ahora or datetime.now(timezone.utc)).isoformat()
    db.guardar_configuracion(CLAVE_CACHE, json.dumps({"anio": anio, "semana": semana, "calculado": marca,
                                                      "datos": datos}, ensure_ascii=False))
    return datos


def obtener(anio: int, semana: int, db=None) -> Optional[Dict]:
    """Lo que usa la portada: primero lo precalculado; si no hay o está viejo, se calcula al momento."""
    return leer_cache(anio, semana, db=db) or calcular(anio, semana, db=db)


def tarea_programada(ahora: datetime, db=None) -> Optional[Dict]:
    """Para src/programador.py: recalcula a lo sumo cada 5 minutos la semana activa."""
    from src.config import Config
    from src.db_manager import get_db_manager
    db = db or get_db_manager()
    anio, semana = Config.get_anio_actual(), Config.get_semana_actual()
    try:
        v = db.obtener_configuracion(CLAVE_CACHE)
        d = json.loads(v) if v else {}
        previo = datetime.fromisoformat(str(d.get("calculado"))) if d.get("calculado") else None
        ahora_utc = ahora.astimezone(timezone.utc) if ahora.tzinfo else ahora.replace(tzinfo=timezone.utc)
        if previo and d.get("anio") == anio and d.get("semana") == semana and ahora_utc - previo < CADA:
            return None
    except Exception:
        pass
    datos = guardar_en_cache(anio, semana, db=db)
    return {"avance": datos.get("pct")} if datos else None
