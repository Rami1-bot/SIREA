# src/logging_config.py
"""
Configuración centralizada de logging del sistema.

El proyecto ya definía LOG_LEVEL / LOG_FORMAT / LOG_MAX_BYTES /
LOG_BACKUP_COUNT en Config (src/config.py) pero nada los usaba: la
mayoría del código escribe con print(), que no queda en ningún archivo
y desaparece en cuanto el proceso se reinicia (importante para un
sistema que debe poder auditar accesos e incidentes).

Este módulo agrega un RotatingFileHandler que escribe en
storage/logs/app.log (rotando según LOG_MAX_BYTES/LOG_BACKUP_COUNT) y
lo registra en el logger raíz, además de un handler de consola. Se
llama una sola vez al arrancar la aplicación (ver app.py).

No reemplaza el log de auditoría de negocio que ya vive en la tabla
`logs` de Supabase (db_manager.registrar_log) -- ese sigue siendo la
fuente de verdad para "quién hizo qué". Este logging es a nivel de
proceso/infraestructura: errores no capturados, tracebacks, y
diagnósticos que no tiene sentido mostrarle a un usuario final ni
guardar en la tabla de negocio.
"""

import logging
import logging.handlers
from pathlib import Path

_configurado = False

# Librerías que, en INFO, registran cada petición HTTP completa (URL con filtros incluidos).
_LIBRERIAS_RUIDOSAS = ("httpx", "httpcore", "hpack", "h2", "urllib3", "postgrest", "supabase", "gotrue", "storage3", "realtime")


def configurar_logging() -> logging.Logger:
    """
    Configura el logging raíz del proceso. Es seguro llamarla más de
    una vez (solo configura handlers la primera vez).
    """
    global _configurado
    logger_raiz = logging.getLogger()

    if _configurado:
        return logger_raiz

    try:
        from src.config import Config
        nivel = getattr(logging, Config.LOG_LEVEL, logging.INFO)
        formato = Config.LOG_FORMAT
        max_bytes = Config.LOG_MAX_BYTES
        backup_count = Config.LOG_BACKUP_COUNT
        logs_dir = Config.LOGS_DIR
    except Exception:
        # Si Config no está disponible todavía (p. ej. se importa este
        # módulo antes de tener .env cargado), usar valores por defecto
        # razonables en vez de fallar el arranque de la app por esto.
        nivel = logging.INFO
        formato = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        max_bytes = 10 * 1024 * 1024
        backup_count = 5
        logs_dir = Path(__file__).resolve().parent.parent / "storage" / "logs"

    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    formateador = logging.Formatter(formato)

    logger_raiz.setLevel(nivel)

    try:
        archivo_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "app.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        archivo_handler.setFormatter(formateador)
        archivo_handler.setLevel(nivel)
        logger_raiz.addHandler(archivo_handler)
    except Exception as e:
        # Si por algún motivo no se puede escribir a disco (permisos,
        # filesystem de solo lectura en algunos hosting), seguir solo
        # con el handler de consola en vez de tumbar el arranque.
        print(f"⚠️ No se pudo configurar el log a archivo ({logs_dir}): {e}")

    consola_handler = logging.StreamHandler()
    consola_handler.setFormatter(formateador)
    consola_handler.setLevel(nivel)
    logger_raiz.addHandler(consola_handler)

    # Las librerías de red escriben cada consulta (con sus filtros: usuarios, correos, códigos)
    # en nivel INFO. Eso llenaría app.log de datos personales y de ruido: solo avisos y errores.
    for nombre in _LIBRERIAS_RUIDOSAS:
        logging.getLogger(nombre).setLevel(logging.WARNING)

    _configurado = True
    return logger_raiz


def obtener_logger(nombre: str) -> logging.Logger:
    """
    Devuelve un logger con nombre, asegurando que el logging global ya
    esté configurado (idempotente).
    """
    configurar_logging()
    return logging.getLogger(nombre)
