# src/respaldos.py
"""
Respaldo del control de lo recibido en la carpeta BACKUPS de Drive.

Qué se respalda (archivos JSON, y un CSV legible de los envíos):
  envíos (control de lo recibido), configuración, exclusiones de centros,
  años epidemiológicos, redes y el historial de cierres de corte.

Qué NO se respalda: contraseñas ni claves cifradas (administradores y
credenciales de las redes) ni los archivos ZIP (ya están en su carpeta de Drive).

Cada respaldo crea una subcarpeta dentro de BACKUPS con la fecha y hora exactas,
p. ej. «RESPALDO_2026-10-20_23-59-59» (la hora del corte, en horario de Lima), y
deja un registro en la tabla «respaldos». Se hace cada N cortes cerrados
(RESPALDO_CADA_N_CORTES, por defecto 2) y se avisa por correo a los
administradores. Si falla, se reintenta hasta 3 veces con 30 minutos de espera
y recién entonces se avisa del error.

Sin Drive configurado (modo local) se guarda en storage/backups/.
"""

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

from src.calendario_epi import parsear_corte
from src.config import Config

LIMA = timezone(timedelta(hours=-5))
FORMATO = "%Y-%m-%d %H:%M:%S"
TABLAS = ("envios", "configuracion", "centros_excluidos", "anios_epidemiologicos", "redes", "cierres_corte",
          "auditoria_acciones", "permisos_operaciones", "descargas_masivas", "solicitudes_retiro", "retiros_archivos")
# Tablas que pueden no existir todavía (se omiten sin fallar el respaldo).
TABLAS_OPCIONALES = ("redes", "cierres_corte", "auditoria_acciones", "permisos_operaciones",
                     "descargas_masivas", "solicitudes_retiro", "retiros_archivos")
MAX_INTENTOS = 3
ESPERA_REINTENTO_MIN = 30
PAGINA = 1000


def _ahora_lima() -> datetime:
    return datetime.now(LIMA).replace(tzinfo=None)


def nombre_respaldo(momento: datetime) -> str:
    """'RESPALDO_2026-10-20_23-59-59' (sin «:» para que sea un nombre de carpeta válido)."""
    return "RESPALDO_" + momento.strftime("%Y-%m-%d_%H-%M-%S")


class Respaldos:
    def __init__(self, db=None, drive=None, sender=None, destinatarios_fn: Optional[Callable] = None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._drive = drive
        self._sender = sender
        self._dest_fn = destinatarios_fn
        self._disp = None

    # ------------------------------------------------------------ utilidades

    @property
    def drive(self):
        if self._drive is None:
            from src.drive_manager import get_drive_manager
            self._drive = get_drive_manager()
        return self._drive

    @property
    def sender(self):
        if self._sender is None:
            from src.email_sender import get_email_sender
            self._sender = get_email_sender()
        return self._sender

    def _t(self, nombre: str):
        return self.db.supabase.table(nombre)

    def disponible(self) -> bool:
        """True si la migración 10 (tabla respaldos) ya se ejecutó."""
        ahora = datetime.now().timestamp()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t("respaldos").select("id").limit(1).execute()
            ok = True
        except Exception as e:
            print(f"Respaldos no disponibles (¿falta sql/10?): {e}")
            ok = False
        self._disp = (ok, ahora)
        return ok

    def destinatarios(self) -> List[Dict]:
        if self._dest_fn:
            return self._dest_fn()
        from src.cierres import get_cierres
        return get_cierres().destinatarios()

    def listar(self, limite: int = 20) -> List[Dict]:
        if not self.disponible():
            return []
        return self._t("respaldos").select("*").order("id", desc=True).limit(limite).execute().data or []

    def destino_configurado(self) -> Tuple[bool, str]:
        """(listo, motivo): si hay dónde guardar el respaldo."""
        if self._es_local():
            return True, "Modo local: se guarda en storage/backups/ del servidor."
        if not Config.GOOGLE_DRIVE_FOLDER_BACKUPS_ID:
            return False, "Falta el ID de la carpeta BACKUPS (GOOGLE_DRIVE_FOLDER_BACKUPS_ID en el .env)."
        return True, "Carpeta BACKUPS de Drive."

    def _es_local(self) -> bool:
        if os.getenv("STORAGE_MODE", "").lower() == "local":
            return True
        try:
            return type(self.drive).__name__ == "LocalDriveManager"
        except Exception:
            return False  # Drive no disponible: el respaldo intentará Drive y quedará registrado como fallido

    # ------------------------------------------------------------ contenido

    def _filas(self, tabla: str) -> List[Dict]:
        """Todas las filas de una tabla, por páginas."""
        filas: List[Dict] = []
        desde = 0
        while True:
            try:       # con orden estable por id (las tablas sin columna id se leen sin orden)
                pagina = self._t(tabla).select("*").order("id").range(desde, desde + PAGINA - 1).execute().data or []
            except Exception:
                pagina = self._t(tabla).select("*").range(desde, desde + PAGINA - 1).execute().data or []
            filas.extend(pagina)
            if len(pagina) < PAGINA:
                return filas
            desde += PAGINA

    def _paquete(self, nombre: str, momento: datetime, origen: str) -> Tuple[List[Tuple[str, bytes, str]], Dict[str, int]]:
        archivos: List[Tuple[str, bytes, str]] = []
        conteos: Dict[str, int] = {}
        hashes: Dict[str, str] = {}
        for tabla in TABLAS:
            try:
                filas = self._filas(tabla)
            except Exception as e:
                if tabla in TABLAS_OPCIONALES:      # tablas opcionales
                    continue
                raise RuntimeError(f"No se pudo leer «{tabla}»: {e}")
            datos = json.dumps(filas, ensure_ascii=False, default=str, indent=1).encode("utf-8")
            archivos.append((f"{tabla}.json", datos, "application/json"))
            conteos[tabla] = len(filas)
            hashes[f"{tabla}.json"] = hashlib.sha256(datos).hexdigest()
            if tabla == "envios":
                buf = io.StringIO()
                columnas = sorted({k for f in filas for k in f})
                w = csv.DictWriter(buf, fieldnames=columnas, extrasaction="ignore")
                w.writeheader()
                for f in filas:
                    w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                                for k, v in f.items()})
                contenido = buf.getvalue().encode("utf-8-sig")
                archivos.append(("envios.csv", contenido, "text/csv"))
                hashes["envios.csv"] = hashlib.sha256(contenido).hexdigest()
        manifiesto = {
            "respaldo": nombre, "momento_lima": momento.strftime(FORMATO), "origen": origen,
            "generado_lima": _ahora_lima().strftime(FORMATO), "filas_por_tabla": conteos, "sha256": hashes,
            "no_incluye": ["administradores (contraseñas)", "credenciales_red (contraseñas)", "archivos ZIP (están en Drive)"],
        }
        archivos.append(("MANIFIESTO.json", json.dumps(manifiesto, ensure_ascii=False, indent=1).encode("utf-8"),
                         "application/json"))
        return archivos, conteos

    # ------------------------------------------------------------ guardar

    def _subir(self, nombre: str, archivos: List[Tuple[str, bytes, str]]) -> Tuple[str, str]:
        """Guarda los archivos. Devuelve (destino, carpeta_id_o_ruta)."""
        if self._es_local():
            carpeta = Config.BACKUP_DIR / nombre
            carpeta.mkdir(parents=True, exist_ok=True)
            for nom, contenido, _ in archivos:
                (carpeta / nom).write_bytes(contenido)
            return "LOCAL", str(carpeta)
        raiz = Config.GOOGLE_DRIVE_FOLDER_BACKUPS_ID
        if not raiz:
            raise RuntimeError("Falta el ID de la carpeta BACKUPS (GOOGLE_DRIVE_FOLDER_BACKUPS_ID).")
        carpeta_id = self.drive.obtener_o_crear_ruta(nombre, raiz)
        for nom, contenido, mime in archivos:
            self.drive.subir_desde_bytes(contenido, nom, nombre, mimetype=mime, raiz_id=raiz)
        return "DRIVE", carpeta_id

    # ------------------------------------------------------------ ejecutar

    def ejecutar(self, momento: datetime, origen: str = "AUTOMATICO", creado_por: str = "SISTEMA",
                 corte_referencia: Optional[str] = None, nombre: Optional[str] = None,
                 notificar: bool = True) -> Dict:
        """
        Hace un respaldo completo. `momento` es la hora (Lima) que identifica el respaldo.
        Devuelve {ok, nombre, destino, total_filas, archivos, cuando, motivo, id}.
        """
        nombre = nombre or nombre_respaldo(momento)
        info: Dict = {"ok": False, "nombre": nombre, "destino": None, "total_filas": 0, "archivos": [],
                      "cuando": momento.strftime("%d/%m/%Y %H:%M:%S"), "motivo": None, "id": None}
        registro_id = None
        if self.disponible():
            try:
                r = self._t("respaldos").insert({
                    "nombre": nombre, "corte_referencia": corte_referencia, "estado": "EN_CURSO",
                    "origen": origen, "creado_por": creado_por}).execute().data
                registro_id = r[0]["id"] if r else None
            except Exception as e:
                print(f"No se pudo registrar el respaldo: {e}")
        info["id"] = registro_id
        try:
            listo, motivo = self.destino_configurado()
            if not listo:
                raise RuntimeError(motivo)
            archivos, conteos = self._paquete(nombre, momento, origen)
            destino, carpeta = self._subir(nombre, archivos)
            info.update(ok=True, destino=("Drive · BACKUPS · " + nombre) if destino == "DRIVE" else f"Local · {carpeta}",
                        total_filas=sum(conteos.values()),
                        archivos=[f"{n} ({conteos[n[:-5]]} registros)" if n.endswith(".json") and n[:-5] in conteos else n
                                  for n, _, _ in archivos])
            if registro_id:
                self._t("respaldos").update({
                    "estado": "COMPLETADO", "destino": destino, "carpeta_id": carpeta,
                    "detalle": ", ".join(f"{k}: {v}" for k, v in conteos.items()), "total_filas": info["total_filas"],
                    "fecha_fin": datetime.now(timezone.utc).isoformat()}).eq("id", registro_id).execute()
            self.db.registrar_log(usuario=creado_por, accion="RESPALDO",
                                  detalle=f"Respaldo {nombre} completado ({info['total_filas']} registros, {destino})")
        except Exception as e:
            info["motivo"] = str(e)
            print(f"Respaldo {nombre} falló: {e}")
            if registro_id:
                try:
                    self._t("respaldos").update({
                        "estado": "ERROR", "detalle": str(e)[:900],
                        "fecha_fin": datetime.now(timezone.utc).isoformat()}).eq("id", registro_id).execute()
                except Exception:
                    pass
            self.db.registrar_log(usuario=creado_por, accion="RESPALDO_ERROR",
                                  detalle=f"Respaldo {nombre} con error: {str(e)[:300]}")
        if notificar and (info["ok"] or origen == "MANUAL"):
            self.avisar(info)
        return info

    def avisar(self, info: Dict) -> int:
        """Acuse por correo a administradores y SUPER_ADMIN."""
        from src import email_cierres as correos
        enviados = 0
        for d in self.destinatarios():
            ok, _ = correos.enviar_acuse_respaldo(self.sender, d["email"], d["nombre"], info)
            enviados += 1 if ok else 0
        return enviados

    # ------------------------------------------------------------ automático

    def _cierres_hasta(self, cierre_id) -> int:
        filas = self._t("cierres_corte").select("id").execute().data or []
        return sum(1 for f in filas if f["id"] <= cierre_id)

    def procesar(self, ahora: Optional[datetime] = None) -> Dict:
        """Un ciclo: respalda los cortes que toca (cada N) y reintenta los que fallaron."""
        acc: Dict = {}
        if not self.disponible():
            return acc
        try:
            self._t("cierres_corte").select("id").limit(1).execute()
        except Exception:
            return acc
        n = Config.RESPALDO_CADA_N_CORTES
        pendientes = (self._t("cierres_corte").select("*").eq("respaldo_evaluado", False)
                      .order("id").execute().data or [])
        for c in pendientes:
            r = (self._t("cierres_corte").update({"respaldo_evaluado": True}).eq("id", c["id"])
                 .eq("respaldo_evaluado", False).execute().data)
            if not r:
                continue                       # otra copia lo reservó
            if self._cierres_hasta(c["id"]) % n != 0:
                continue
            corte = parsear_corte(c["corte_cerrado"]) or (ahora or _ahora_lima())
            info = self.ejecutar(corte, "AUTOMATICO", "SISTEMA", c["corte_cerrado"], notificar=False)
            acc.setdefault("respaldos", []).append(info["nombre"] + (" OK" if info["ok"] else " ERROR"))
            if info["ok"]:
                self.avisar(info)
        self._reintentar(ahora or _ahora_lima(), acc)
        return acc

    def _reintentar(self, ahora: datetime, acc: Dict):
        filas = (self._t("respaldos").select("*").eq("origen", "AUTOMATICO").order("id").execute().data or [])
        por_corte: Dict[str, List[Dict]] = {}
        for f in filas:
            if f.get("corte_referencia"):
                por_corte.setdefault(f["corte_referencia"], []).append(f)
        for corte_txt, lista in por_corte.items():
            if any(f["estado"] in ("COMPLETADO", "EN_CURSO") for f in lista):
                continue
            intentos = len(lista)
            ultimo = lista[-1]
            fin = ultimo.get("fecha_fin") or ultimo.get("fecha_creacion")
            try:
                t = datetime.fromisoformat(str(fin).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - t < timedelta(minutes=ESPERA_REINTENTO_MIN):
                    continue
            except ValueError:
                pass
            if intentos >= MAX_INTENTOS:
                continue
            corte = parsear_corte(corte_txt) or ahora
            base = nombre_respaldo(corte)
            info = self.ejecutar(corte, "AUTOMATICO", "SISTEMA", corte_txt,
                                 nombre=f"{base}_intento{intentos + 1}", notificar=False)
            acc.setdefault("reintentos", []).append(info["nombre"] + (" OK" if info["ok"] else " ERROR"))
            if info["ok"] or intentos + 1 >= MAX_INTENTOS:
                info["motivo"] = info["motivo"] or ""
                self.avisar(info)


_respaldos = None


def get_respaldos() -> Respaldos:
    global _respaldos
    if _respaldos is None:
        _respaldos = Respaldos()
    return _respaldos
