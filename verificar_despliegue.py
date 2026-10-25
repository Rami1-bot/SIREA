#!/usr/bin/env python3
"""
SIREA – Verificación previa al despliegue (solo lectura; no modifica nada).

Uso (dentro de Docker, que es donde importa):
    docker compose exec app python verificar_despliegue.py
    docker compose exec app python verificar_despliegue.py --enviar-prueba correo@dominio.pe
    docker compose exec app python verificar_despliegue.py --sin-red        # solo revisa configuración local

No imprime nunca claves, contraseñas ni tokens: solo dice si existen y si funcionan.
Código de salida: 0 = sin fallas; 1 = hay al menos una FALLA.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SECRETOS = ("SUPABASE_KEY", "EMAIL_PASSWORD", "DB_PASSWORD")
resultados = {"OK": 0, "AVISO": 0, "FALLA": 0}


def limpiar(texto) -> str:
    """Quita de cualquier mensaje los valores secretos antes de mostrarlo."""
    t = str(texto)
    for nombre in SECRETOS:
        v = os.environ.get(nombre, "")
        if len(v) >= 6:
            t = t.replace(v, "***")
    return t[:300]


def mostrar(nivel: str, titulo: str, detalle: str = ""):
    resultados[nivel] += 1
    marca = {"OK": "[ OK  ]", "AVISO": "[AVISO]", "FALLA": "[FALLA]"}[nivel]
    print(f"{marca} {titulo}" + (f"\n         {limpiar(detalle)}" if detalle else ""))


def seccion(nombre: str):
    print(f"\n=== {nombre} ===")


PLACEHOLDERS = ("completar", "xxxx", "tu-", "tu_", "example", "ejemplo", "nombre-o-ip", "pegue", "cambiar")


def es_placeholder(v: str) -> bool:
    b = (v or "").strip().lower()
    return (not b) or any(p in b for p in PLACEHOLDERS)


def revisar_variables():
    seccion("1. Variables del .env")
    obligatorias = {
        "SUPABASE_URL": "dirección del proyecto Supabase",
        "SUPABASE_KEY": "clave de Supabase",
        "GOOGLE_DRIVE_FOLDER_ID": "carpeta principal de envíos en Drive",
        "EMAIL_REMITENTE": "correo remitente",
        "EMAIL_PASSWORD": "contraseña de aplicación del correo",
    }
    sm = os.getenv("STORAGE_MODE", "").strip().lower()
    if sm not in ("drive", "local"):
        mostrar("AVISO", "STORAGE_MODE sin definir", "Se usará Drive; conviene dejar STORAGE_MODE=drive explícito.")
    for k, desc in obligatorias.items():
        v = os.getenv(k, "")
        if not v.strip():
            mostrar("FALLA", f"{k} está vacía", f"Falta {desc}.")
        elif es_placeholder(v):
            mostrar("FALLA", f"{k} parece un valor de ejemplo", f"Reemplace el marcador por {desc}.")
        else:
            mostrar("OK", f"{k} definida")
    recomendadas = {
        "GOOGLE_DRIVE_FOLDER_BACKUPS_ID": "carpeta de respaldos en Drive",
        "GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID": "carpeta de duplicados en Drive (si no, se usa una subcarpeta)",
        "GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID": "carpeta de envíos reemplazados en Drive (si no, se usa una subcarpeta)",
        "AUDITORIA_COPIA_EMAIL": "buzón que recibe copia oculta de los acuses de auditoría",
        "EMAIL_ADMINS": "correos de los administradores que reciben alertas",
    }
    for k, desc in recomendadas.items():
        if es_placeholder(os.getenv(k, "")):
            mostrar("AVISO", f"{k} sin definir", f"Recomendado: {desc}.")
        else:
            mostrar("OK", f"{k} definida")


def revisar_entorno():
    seccion("2. Entorno y seguridad")
    modo = os.getenv("STORAGE_MODE", "").strip().lower()
    if modo == "local":
        mostrar("AVISO", "STORAGE_MODE=local", "Los envíos se guardan solo en el servidor, no en Drive. Úselo únicamente en pruebas.")
    if os.getenv("STORAGE_FALLBACK_LOCAL", "").strip().lower() in ("1", "true", "si", "sí", "yes"):
        mostrar("AVISO", "STORAGE_FALLBACK_LOCAL=true", "Si Drive falla, los envíos irían al servidor en silencio. Debe ser false en producción.")
    else:
        mostrar("OK", "Sin modo local de emergencia (STORAGE_FALLBACK_LOCAL=false)")
    uid_pid1 = None
    try:
        for linea in Path("/proc/1/status").read_text().splitlines():
            if linea.startswith("Uid:"):
                uid_pid1 = int(linea.split()[1])
    except Exception:
        pass
    if uid_pid1 is not None:
        if uid_pid1 == 0:
            mostrar("FALLA", "El proceso principal del contenedor corre como root", "Debe correr sin privilegios (revise docker-entrypoint.sh).")
        else:
            mostrar("OK", f"El proceso principal corre sin privilegios (uid {uid_pid1})")
    if hasattr(os, "getuid") and os.getuid() == 0:
        mostrar("AVISO", "Esta verificación se ejecuta como root",
                "Use «docker compose exec -u sire app python verificar_despliegue.py»: como root se leería la credencial aunque la aplicación no pudiera.")
    proxy = os.getenv("PROXY_CONFIABLE", "false").strip().lower() in ("1", "true", "si", "sí", "yes")
    bind = os.getenv("APP_BIND", "0.0.0.0").strip()
    if proxy and bind not in ("127.0.0.1", "localhost"):
        mostrar("FALLA", "PROXY_CONFIABLE=true pero la app es alcanzable sin el proxy (APP_BIND≠127.0.0.1)",
                "Cualquiera podría falsificar su IP en la auditoría. Use APP_BIND=127.0.0.1 con HTTPS, o PROXY_CONFIABLE=false.")
    elif proxy:
        mostrar("OK", "HTTPS/proxy: PROXY_CONFIABLE=true con APP_BIND=127.0.0.1")
    else:
        mostrar("OK", f"Acceso directo (sin proxy): APP_BIND={bind}, PROXY_CONFIABLE=false")
    entorno = os.getenv("ENVIRONMENT", "").strip().lower()
    if entorno and entorno not in ("production", "produccion", "producción", "prod", "pilot", "piloto"):
        mostrar("AVISO", f"ENVIRONMENT={entorno}", "No parece un entorno de piloto/producción.")
    from src.config import Config
    for d in (Config.STORAGE_DIR, Config.LOGS_DIR, Config.TEMP_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
            prueba = d / ".escritura_prueba"
            prueba.write_text("x")
            prueba.unlink()
            mostrar("OK", f"Se puede escribir en {d.name}/")
        except Exception as e:
            mostrar("FALLA", f"No se puede escribir en {d}", f"{type(e).__name__}: {e}")
    # El .env o sus copias no deben estar dentro de la imagen
    sospechosos = [p.name for p in Config.BASE_DIR.glob(".env*") if p.name != ".env.example"]
    if sospechosos:
        mostrar("FALLA", "Hay archivos .env* dentro de la aplicación", ", ".join(sospechosos) + " (revise .dockerignore).")
    else:
        mostrar("OK", "No hay copias del .env dentro de la aplicación")


def revisar_credencial_drive():
    seccion("3. Credencial de Google (cuenta de servicio)")
    from src.config import Config
    ruta = Config.BASE_DIR / Config.GOOGLE_CREDENTIALS_PATH
    if not ruta.exists():
        mostrar("FALLA", "No se encuentra la credencial", f"Ruta esperada dentro del contenedor: {ruta}")
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except PermissionError:
        mostrar("FALLA", "La credencial existe pero no se puede leer (Permission denied)", "Revise docker-entrypoint.sh y el montaje de credentials/.")
        return None
    except Exception as e:
        mostrar("FALLA", "La credencial no es un JSON válido", f"{type(e).__name__}")
        return None
    faltan = [k for k in ("type", "client_email", "private_key", "token_uri") if not datos.get(k)]
    if datos.get("type") != "service_account" or faltan:
        mostrar("FALLA", "El JSON no es de una cuenta de servicio completa", f"Campos que faltan: {', '.join(faltan) or 'type'}")
        return None
    mostrar("OK", "Credencial legible y con formato de cuenta de servicio")
    print(f"         Cuenta de servicio: {datos['client_email']}  (las carpetas de Drive deben estar compartidas con este correo)")
    return datos


def revisar_supabase():
    seccion("4. Base de datos (Supabase)")
    try:
        from src.db_manager import get_db_manager
        db = get_db_manager()
    except Exception as e:
        mostrar("FALLA", "No se pudo crear el cliente de Supabase", f"{type(e).__name__}: {e}")
        return
    try:
        db.supabase.table("administradores").select("*").limit(1).execute()
        mostrar("OK", "Conexión con Supabase y clave aceptadas")
    except Exception as e:
        mostrar("FALLA", "Supabase rechazó la conexión o la clave", f"{type(e).__name__}: {e}")
        return
    tablas = {
        "administradores": True, "envios": True, "configuracion": True, "anios_epidemiologicos": True,
        "centros_excluidos": True, "redes": True,
        "solicitudes_password": True,          # migración 09
        "cierres_corte": True, "respaldos": True,   # migración 10
        "auditoria_acciones": True, "permisos_operaciones": True, "descargas_masivas": True,
        "solicitudes_retiro": True, "retiros_archivos": True,   # migración 11
        "auditoria_agentes_ia": True,                           # SIREA: migración 50
        "sesiones_app": True, "intentos_login": True,           # SIREA: migración 51
        "observaciones_envio": True,                            # migración 13 (SIRE v7)
        "agente_corridas": True, "agente_traza": True, "agente_acciones": True,      # SIREA 3.0: migración 52
        "agente_memoria_red": True, "agente_evals": True,
        "agente_skill_versiones": True,                          # SIREA 3.1: migración 53
        "agente_atrasos_justificados": True, "agente_informes": True,   # SIREA 3.2: migración 54
    }
    migraciones = {"solicitudes_password": "09", "cierres_corte": "10", "respaldos": "10",
                   "auditoria_acciones": "11", "permisos_operaciones": "11", "descargas_masivas": "11",
                   "solicitudes_retiro": "11", "retiros_archivos": "11", "auditoria_agentes_ia": "50",
                   "sesiones_app": "51", "intentos_login": "51", "observaciones_envio": "13",
                   "agente_corridas": "52", "agente_traza": "52", "agente_acciones": "52",
                   "agente_memoria_red": "52", "agente_evals": "52", "agente_skill_versiones": "53",
                   "agente_atrasos_justificados": "54", "agente_informes": "54"}
    for t in tablas:
        try:
            db.supabase.table(t).select("*").limit(1).execute()
        except Exception as e:
            mig = migraciones.get(t)
            if t in ("redes",):          # opcional: el respaldo y la app funcionan sin ella
                mostrar("AVISO", f"La tabla opcional «{t}» no existe", "No es obligatoria.")
                continue
            if t in ("sesiones_app", "intentos_login"):   # sin ellas el bloqueo de login queda solo en memoria
                mostrar("AVISO", f"Falta la tabla «{t}»",
                        "Ejecute sql/51_sesiones_e_intentos_login.sql: sin ella los bloqueos se pierden al reiniciar.")
                continue
            mostrar("FALLA", f"Falta la tabla «{t}» o no es accesible",
                    (f"Ejecute sql/{mig}_*.sql en Supabase. " if mig else "") + f"{type(e).__name__}")
    try:
        db.supabase.table("envios").select("detalle_archivos").limit(1).execute()
        mostrar("OK", "Columna envios.detalle_archivos presente (duplicados exactos por centro + tipo)")
    except Exception as e:
        mostrar("AVISO", "Falta la columna envios.detalle_archivos",
                "Ejecute sql/12_envios_detalle_archivos.sql en Supabase. Sin ella todo funciona, pero los "
                "duplicados se detectan con menos precisión y no se comparan huellas entre semanas.")
    try:
        admins = db.obtener_administradores()
        activos = [a for a in admins if a.get("activo")]
        from src.config import Config
        principal = Config.SUPERADMIN_PRINCIPAL
        if not any((a.get("usuario") or "").lower() == principal and a.get("activo") for a in admins):
            mostrar("FALLA", f"El principal «{principal}» no existe o está inactivo")
        else:
            mostrar("OK", f"Administrador principal «{principal}» activo")
        mostrar("OK", f"Administradores activos: {len(activos)} de {len(admins)}")
        print("         Revise que no queden cuentas de prueba activas: " + ", ".join(sorted((a.get('usuario') or '?') for a in activos)))
        sin_correo = [a.get("usuario") for a in activos if not (a.get("email") or "").strip()]
        if sin_correo:
            mostrar("AVISO", "Administradores activos sin correo", ", ".join(sin_correo))
    except Exception as e:
        mostrar("AVISO", "No se pudo listar administradores", f"{type(e).__name__}")
    try:
        from src.auditoria import get_auditoria
        res = get_auditoria().verificar_cadena()
        if res.get("ok"):
            mostrar("OK", f"Cadena de auditoría íntegra ({res.get('filas', 0)} fila(s))")
        else:
            mostrar("FALLA", "La cadena de auditoría no es íntegra", f"Fila {res.get('id_roto')}: {res.get('motivo')}")
    except Exception as e:
        mostrar("AVISO", "No se pudo verificar la auditoría", f"{type(e).__name__}")


def revisar_drive():
    seccion("5. Google Drive")
    from src.config import Config
    if os.getenv("STORAGE_MODE", "").strip().lower() == "local":
        mostrar("AVISO", "Modo local: no se revisa Drive")
        return
    try:
        from src.drive_manager import get_drive_manager
        drive = get_drive_manager()
    except Exception as e:
        mostrar("FALLA", "No se pudo conectar con Drive", f"{type(e).__name__}: {e}")
        return
    ok, msg = drive.verificar_conexion()
    mostrar("OK" if ok else "FALLA", "Conexión con Drive" + ("" if ok else " fallida"), "" if ok else msg)
    carpetas = [("principal (envíos)", Config.GOOGLE_DRIVE_FOLDER_ID, True),
                ("duplicados", Config.GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID, False),
                ("reemplazados", Config.GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID, False),
                ("respaldos", Config.GOOGLE_DRIVE_FOLDER_BACKUPS_ID, False)]
    for nombre, fid, obligatoria in carpetas:
        if not fid:
            mostrar("FALLA" if obligatoria else "AVISO", f"Carpeta {nombre}: sin ID")
            continue
        r = drive.probar_carpeta(fid)
        if r.get("ok") and r.get("papelera"):
            mostrar("OK", f"Carpeta {nombre} «{r.get('nombre','')}»: escribir y quitar archivos")
        elif r.get("ok"):
            mostrar("AVISO", f"Carpeta {nombre} «{r.get('nombre','')}»", r.get("detalle", ""))
        else:
            mostrar("FALLA", f"Carpeta {nombre}", r.get("detalle", ""))


def revisar_correo(destino: str = ""):
    seccion("6. Correo (SMTP)")
    try:
        from src.email_sender import EmailSender
        es = EmailSender()
        ok, msg = es.verificar_configuracion()
        mostrar("OK" if ok else "FALLA", "Inicio de sesión SMTP" + ("" if ok else " fallido"), "" if ok else msg)
        if ok and destino:
            ok2, msg2 = es.enviar_correo_prueba(destino)
            mostrar("OK" if ok2 else "FALLA", f"Correo de prueba a {destino}", "" if ok2 else msg2)
        elif ok:
            mostrar("AVISO", "No se envió correo de prueba", "Use --enviar-prueba su.correo@dominio.pe para comprobar la entrega.")
    except Exception as e:
        mostrar("FALLA", "No se pudo comprobar el correo", f"{type(e).__name__}: {e}")


def revisar_ia():
    """SIREA: proveedores de IA configurados (sin mostrar claves) y prueba mínima opcional."""
    seccion("Agente de IA")
    try:
        from src.config import Config
        provs = Config.proveedores_ia_disponibles()
    except Exception as e:
        mostrar("FALLA", "No se pudo leer la configuración de IA", f"{type(e).__name__}")
        return
    if not provs:
        mostrar("AVISO", "Sin proveedor de IA", "Agregue GEMINI_API_KEY y/o GROQ_API_KEY. El sistema funciona; el agente no responderá.")
        return
    mostrar("OK", "Proveedores configurados", " → ".join(provs))
    try:
        from src.agentes.proveedores import diagnostico
        for d in diagnostico():
            mostrar("OK" if d["ok"] else "AVISO", f"{d['proveedor']} · {d.get('modelo') or '—'}", limpiar(d["mensaje"])[:300])
    except Exception as e:
        mostrar("AVISO", "No se pudo probar los proveedores", f"{type(e).__name__}")


def main():
    ap = argparse.ArgumentParser(description="Verificación previa al despliegue de SIREA (solo lectura).")
    ap.add_argument("--enviar-prueba", metavar="CORREO", default="", help="envía un correo de prueba a esta dirección")
    ap.add_argument("--sin-red", action="store_true", help="solo revisa configuración local (sin Supabase/Drive/SMTP)")
    a = ap.parse_args()
    print("SIREA – verificación previa al despliegue (no muestra secretos y no modifica datos)")
    revisar_variables()
    revisar_entorno()
    cred = revisar_credencial_drive()
    if not a.sin_red:
        revisar_supabase()
        if cred is not None or os.getenv("STORAGE_MODE", "").strip().lower() == "local":
            revisar_drive()
        revisar_correo(a.enviar_prueba)
        revisar_ia()
    print(f"\nResumen: {resultados['OK']} OK · {resultados['AVISO']} aviso(s) · {resultados['FALLA']} falla(s)")
    if resultados["FALLA"]:
        print("Hay FALLAS: corríjalas antes de abrir el sistema al personal.")
    elif resultados["AVISO"]:
        print("Sin fallas. Revise los avisos y decida si aplican.")
    else:
        print("Todo en verde.")
    sys.exit(1 if resultados["FALLA"] else 0)


if __name__ == "__main__":
    main()
