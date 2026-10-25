# src/programador.py
"""
Proceso programado de SIREA (se ejecuta en su propio contenedor, aparte de la web).

Cada minuto, en horario de Lima:
  1. Cierre de corte: cuando pasa la fecha de corte, propone y aplica de forma
     provisional la semana siguiente y avisa a los administradores (src/cierres.py).
  2. Recordatorios (hasta 3) mientras nadie valide, y el aviso «ya validado».
  3. Respaldo a la carpeta BACKUPS cada N cortes, con acuse por correo (src/respaldos.py).

Todo es idempotente: si el proceso se reinicia o hay dos copias, no se duplican
los correos ni los respaldos (las bases reservan cada paso antes de ejecutarlo).

Uso:
    python -m src.programador              # bucle continuo (contenedor)
    python -m src.programador --una-vez    # un solo ciclo (pruebas o tarea programada del sistema)
"""

import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from src.config import Config

INTERVALO_SEGUNDOS = 60
CLAVE_LATIDO = "programador_ultimo_latido"
_detener = False


def _senal(signo, _marco):
    global _detener
    _detener = True
    print(f"[programador] señal {signo}: terminando después del ciclo actual.", flush=True)


def ciclo(ahora: Optional[datetime] = None, cierres=None, respaldos=None, db=None) -> Dict:
    """Un ciclo completo. Un fallo en una tarea no impide las demás."""
    from src.cierres import get_cierres
    from src.respaldos import Respaldos
    cierres = cierres or get_cierres()
    if respaldos is None:
        respaldos = Respaldos(db=cierres.db, sender=cierres.sender, destinatarios_fn=cierres.destinatarios)
    resultado: Dict = {}
    def _agente(ahora_):
        from src.agentes.agente_operativo import procesar_programado
        return procesar_programado(ahora_)
    for nombre, tarea in (("cierres", cierres.procesar), ("respaldos", respaldos.procesar), ("agente", _agente)):
        try:
            r = tarea(ahora)
            if r:
                resultado[nombre] = r
        except Exception as e:
            resultado[nombre] = {"error": str(e)}
            print(f"[programador] error en {nombre}: {e}", flush=True)
            traceback.print_exc()
    try:
        # Latido: la pantalla de administración avisa si el proceso dejó de funcionar.
        (db or cierres.db).guardar_configuracion(CLAVE_LATIDO, datetime.now(timezone.utc).isoformat())
        Path(Config.LOGS_DIR).mkdir(parents=True, exist_ok=True)
        (Path(Config.LOGS_DIR) / "programador.latido").write_text(str(int(time.time())))
    except Exception as e:
        print(f"[programador] no se pudo registrar el latido: {e}", flush=True)
    return resultado


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    una_vez = "--una-vez" in argv
    signal.signal(signal.SIGTERM, _senal)
    signal.signal(signal.SIGINT, _senal)
    print(f"[programador] iniciado (zona horaria {os.environ.get('TZ', 'del sistema')}).", flush=True)
    while True:
        inicio = time.time()
        r = ciclo()
        if r:
            print(f"[programador] {datetime.now():%Y-%m-%d %H:%M:%S} {r}", flush=True)
        if una_vez or _detener:
            return 0
        # Espera hasta el comienzo del siguiente minuto, en pasos cortos para atender las señales.
        espera = max(1.0, INTERVALO_SEGUNDOS - (time.time() - inicio))
        fin = time.time() + espera
        while time.time() < fin and not _detener:
            time.sleep(min(1.0, fin - time.time()))
        if _detener:
            return 0


if __name__ == "__main__":
    sys.exit(main())
