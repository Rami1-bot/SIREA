"""
SIREA 3.2 · Historial SIMULADO para la demostración de patrones.

Sin historial no hay patrones: con una base demo recién creada, la pestaña
«Patrones», el recordatorio preventivo y el informe semanal no tienen nada
que mostrar. Este script carga N semanas de envíos SIMULADOS para las redes
y centros que ya existen en su base, con comportamientos realistas:

  * algunas redes suelen enviar la Emergencia después del corte,
  * alguna viene mejorando y otra empeorando,
  * el resto envía a tiempo,
  * los hospitales mandan Consulta Externa + Hospitalización + Emergencia;
    los CAP, policlínicos y postas, solo Consulta Externa.

Todo queda MARCADO: código de seguimiento «DEMO-SIM-…», observación
«[DEMO SIMULADO]» y correo del remitente en example.org (dominio reservado:
si alguien aprueba un recordatorio en la demo, no le llega a nadie real).

Uso (carpeta del proyecto, entorno virtual activado, .env de la base DEMO):

    python scripts/sembrar_historial_demo.py --confirmo-base-demo
    python scripts/sembrar_historial_demo.py --confirmo-base-demo --semanas 10
    python scripts/sembrar_historial_demo.py --confirmo-base-demo --borrar

NUNCA lo ejecute contra la base de producción. Antes de pasar a producción,
borre lo simulado con --borrar (y revise 99_limpieza_previa_a_produccion.sql).
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PREFIJO = "DEMO-SIM-"
MARCA = "[DEMO SIMULADO] historial de prueba para la demostración de patrones (SIREA 3.2)"


def _tipos_de(nombre: str) -> list:
    n = (nombre or "").upper()
    if "HOSPITAL" in n or n.startswith("H.") or " H.N." in n or "CLINICA" in n:
        return ["c", "h", "e"]
    if "CENTRO MEDICO" in n or "C.M." in n:
        return ["c", "e"]
    return ["c"]


def _perfiles(redes: list, rnd: random.Random) -> dict:
    redes = list(redes)
    rnd.shuffle(redes)
    n = len(redes)
    out = {}
    for i, r in enumerate(redes):
        if i < max(1, n // 4):
            out[r] = "suele_atrasarse"
        elif i < max(1, n // 4) + max(1, n // 8):
            out[r] = "mejora"
        elif i < max(1, n // 4) + max(1, n // 8) + max(1, n // 10):
            out[r] = "empeora"
        else:
            out[r] = "puntual"
    return out


def _tarde(perfil: str, k: int, n: int, rnd: random.Random) -> bool:
    """k = 0 la semana más antigua … n-1 la más reciente."""
    if perfil == "suele_atrasarse":
        return rnd.random() < 0.7
    if perfil == "mejora":
        return k < n - 3 and rnd.random() < 0.8
    if perfil == "empeora":
        return k >= n - 3 and rnd.random() < 0.85
    return rnd.random() < 0.05


def sembrar(semanas: int, semilla: int = 2026) -> int:
    from src.agentes.patrones import semanas_atras
    from src.agentes.herramientas import info_semana_actual
    from src.data_loader import get_data_loader
    from src.db_manager import get_db_manager
    db, dl = get_db_manager(), get_data_loader()
    info = info_semana_actual()
    anio, semana = int(info["anio"]), int(info["semana_activa"])
    rnd = random.Random(semilla)
    redes = [r for r in dl.obtener_redes() if dl.obtener_centros(r)]
    if not redes:
        print("No hay redes con centros en la base: cargue primero redes y centros.")
        return 0
    perfiles = _perfiles(redes, rnd)
    lista = list(reversed(semanas_atras(anio, semana, semanas)))      # de la más antigua a la más reciente
    filas = []
    for k, (a, s) in enumerate(lista):
        inicio = datetime(a, 1, 4, 12, tzinfo=timezone.utc) + timedelta(weeks=s - 1)
        for red in redes:
            perfil = perfiles[red]
            centros = dl.obtener_centros(red)
            tarde = _tarde(perfil, k, len(lista), rnd)
            a_tiempo, tardio = [], []
            for c in centros:
                for letra in _tipos_de(c.get("nombre")):
                    destino = tardio if (tarde and (letra == "e" or perfil != "suele_atrasarse") and rnd.random() < 0.8) else a_tiempo
                    destino.append((c, letra))
            correo = f"responsable.{''.join(ch for ch in red.lower() if ch.isalnum())[:20]}@example.org"
            for grupo, es_tarde in ((a_tiempo, False), (tardio, True)):
                if not grupo:
                    continue
                fecha = inicio + timedelta(days=9 if es_tarde else 3, hours=rnd.randint(0, 8))
                detalle = [{"archivo": f"p{l}{s:02d}{a % 100:02d}sim.{c.get('codigo')}", "codigo": c.get("codigo"),
                            "centro": c.get("nombre"), "tipo": l, "semana": s, "anio": a} for c, l in grupo]
                filas.append({
                    "nombre_usuario": "Responsable", "apellido_usuario": "Demo", "correo_usuario": correo, "red": red,
                    "centros": sorted({f"{c.get('codigo')} {c.get('nombre')}" for c, _ in grupo}), "semana": s, "anio": a,
                    "tipo_reporte": sorted({{"c": "Consulta Externa", "h": "Hospitalizacion", "e": "Emergencia"}[l] for _, l in grupo}),
                    "ruta_zip": None, "drive_file_id": None, "cantidad_archivos": len(grupo), "estado": "ATRASADO" if es_tarde else "APROBADO",
                    "observacion": MARCA, "es_atrasado": es_tarde, "semana_activa_envio": s + (1 if es_tarde else 0),
                    "dias_atraso_envio": 3 if es_tarde else 0, "codigo_seguimiento": f"{PREFIJO}{a}{s:02d}-{len(filas) + 1:05d}",
                    "fecha_envio": fecha.isoformat(), "fecha_actualizacion": fecha.isoformat(), "detalle_archivos": detalle,
                })
    total = 0
    for i in range(0, len(filas), 200):
        lote = filas[i:i + 200]
        try:
            db.supabase.table("envios").insert(lote).execute()
        except Exception as e:  # noqa: BLE001  base sin sql/12: sin detalle por archivo
            if "detalle_archivos" not in str(e):
                raise
            for f in lote:
                f.pop("detalle_archivos", None)
            db.supabase.table("envios").insert(lote).execute()
        total += len(lote)
    print(f"Listo: {total} envíos simulados en {len(lista)} semanas para {len(redes)} redes.")
    for red, p in sorted(perfiles.items()):
        print(f"  {red}: {p.replace('_', ' ')}")
    return total


def borrar() -> int:
    from src.db_manager import get_db_manager
    r = get_db_manager().supabase.table("envios").delete().like("codigo_seguimiento", f"{PREFIJO}%").execute()
    n = len(r.data or [])
    print(f"Se borraron {n} envíos simulados.")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Historial SIMULADO para la demo de patrones (solo base DEMO).")
    ap.add_argument("--confirmo-base-demo", action="store_true", help="confirma que el .env apunta a la base de DEMO")
    ap.add_argument("--semanas", type=int, default=10, help="semanas hacia atrás (4 a 20)")
    ap.add_argument("--borrar", action="store_true", help="borra lo simulado (código DEMO-SIM-…)")
    args = ap.parse_args()
    if not args.confirmo_base_demo:
        print("Por seguridad agregue --confirmo-base-demo (y verifique que su .env es el de la base DEMO).")
        return 2
    if args.borrar:
        borrar()
        return 0
    sembrar(max(4, min(args.semanas, 20)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
