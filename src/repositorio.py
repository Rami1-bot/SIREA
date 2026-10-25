# src/repositorio.py
"""
Descarga masiva y limpieza del repositorio de archivos (Drive).

Qué hace
--------
1. DESCARGA MASIVA: junta los ZIP recibidos de una semana (todas las redes o
   las elegidas) en un solo ZIP ordenado por red, con un MANIFIESTO (qué es cada
   archivo y su huella SHA-256). Si pesa más del tope (DESCARGA_MASIVA_MAX_MB) se
   divide en partes. Cada ZIP preparado queda registrado con su huella y, al
   descargarlo, se envía un acuse al responsable y al SUPER_ADMIN principal.
2. RETIRO DEL REPOSITORIO: quita los archivos de Drive (por defecto a la
   PAPELERA, recuperable ~30 días). Quien tiene el permiso lo SOLICITA y el
   SUPER_ADMIN principal lo APRUEBA (si lo pide él mismo, se ejecuta directo).
   Se conserva siempre el registro de recepción en la base de datos: solo se
   quita el archivo.
3. Todo queda en la auditoría (solo escritura) y se envía un Excel con el
   detalle archivo por archivo.

Reglas de seguridad
-------------------
* Cada operación exige el permiso correspondiente (src/permisos.py) y respeta
  su alcance por redes.
* Si no se puede dejar constancia en la auditoría, la operación NO se hace.
* Un retiro solo se ejecuta una vez (reserva condicional), aunque se haga clic dos veces.
* El borrado definitivo (sin papelera) solo lo puede decidir el SUPER_ADMIN principal.
"""

import csv
import hashlib
import io
import os
import re
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.auditoria import AuditoriaError, ahora_lima, evaluar_alertas, get_auditoria
from src.config import Config
from src.permisos import PERMISOS, es_principal, get_permisos
from utils.duplicados import es_duplicado, es_reemplazado
from utils.helpers import sanitizar_nombre

MOTIVOS_RETIRO = [
    "Ya descargado y respaldado",
    "Liberar espacio y mantener la operatividad del repositorio",
    "Envío errado o de prueba",
    "Reemplazado por un envío corregido",
    "Otro (explique en el detalle)",
]
MOTIVO_DESCARGADO = MOTIVOS_RETIRO[0]
MOTIVO_MIN = 15
_CHUNK = 200


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nombre_archivo(envio: Dict) -> str:
    base = os.path.basename(str(envio.get("ruta_zip") or "").replace("\\", "/"))
    stem = re.sub(r"\.zip$", "", base, flags=re.I) or str(envio.get("codigo_seguimiento") or envio.get("id"))
    return f"{sanitizar_nombre(stem)}.zip"


def _centros_texto(envio: Dict) -> str:
    c = envio.get("centros") or []
    return ", ".join(str(x) for x in c) if isinstance(c, list) else str(c)


def _persona(envio: Dict) -> str:
    return f"{envio.get('nombre_usuario', '')} {envio.get('apellido_usuario', '')}".strip()


def tiene_archivo(envio: Dict) -> bool:
    v = str(envio.get("drive_file_id") or "").strip()
    return bool(v) and v.upper() != "LOCAL"


def validar_motivo(texto: str) -> Optional[str]:
    t = (texto or "").strip()
    if len(t) < MOTIVO_MIN:
        return f"Explique el motivo con al menos {MOTIVO_MIN} caracteres."
    if len(set(t.lower())) < 5:
        return "Explique el motivo con palabras claras."
    return None


def _en_lotes(valores: List, n: int = _CHUNK):
    for i in range(0, len(valores), n):
        yield valores[i:i + n]


class RepositorioError(Exception):
    pass


class Repositorio:
    def __init__(self, db=None, drive=None, sender=None, permisos=None, auditoria=None, auth=None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._drive, self._sender, self._permisos, self._aud, self._auth = drive, sender, permisos, auditoria, auth
        self._disp = None

    # ------------------------------------------------------------ dependencias

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

    @property
    def permisos(self):
        if self._permisos is None:
            self._permisos = get_permisos()
        return self._permisos

    @property
    def aud(self):
        if self._aud is None:
            self._aud = get_auditoria()
        return self._aud

    @property
    def auth(self):
        if self._auth is None:
            from src.auth import get_auth_manager
            self._auth = get_auth_manager()
        return self._auth

    def _t(self, nombre: str):
        return self.db.supabase.table(nombre)

    def disponible(self) -> bool:
        """True si la migración 11 ya se ejecutó."""
        ahora = time.time()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            for t in ("descargas_masivas", "solicitudes_retiro", "retiros_archivos"):
                self._t(t).select("id").limit(1).execute()
            ok = self.aud.disponible() and self.permisos.disponible()
        except Exception as e:
            print(f"Repositorio no disponible (¿falta sql/11?): {e}")
            ok = False
        self._disp = (ok, ahora)
        return ok

    # ------------------------------------------------------------ selección

    def redes_con_permiso(self, actor: Dict, permiso: str, todas_las_redes: List[str]) -> List[str]:
        tiene, alcance = self.permisos.alcance(actor, permiso)
        if not tiene:
            return []
        return [r for r in todas_las_redes if alcance is None or r in alcance]

    def envios_de(self, anio: int, semana: int, redes: Optional[List[str]], incluir_duplicados: bool = False,
                  permitidas: Optional[List[str]] = None) -> List[Dict]:
        """
        Envíos de la semana. `redes` None = todas. `permitidas` (alcance de la persona)
        limita siempre el resultado.
        """
        filas: List[Dict] = []
        consultas = [None] if redes is None else list(redes)
        for red in consultas:
            offset = 0
            while True:
                lote = self.db.obtener_envios(semana=semana, anio=anio, red=red, limit=1000, offset=offset)
                filas.extend(lote)
                if len(lote) < 1000:
                    break
                offset += 1000
        vistos, salida = set(), []
        for e in filas:
            if e.get("id") in vistos:
                continue
            vistos.add(e.get("id"))
            if permitidas is not None and e.get("red") not in permitidas:
                continue
            if not incluir_duplicados and (es_duplicado(e) or es_reemplazado(e)):
                continue
            salida.append(e)
        salida.sort(key=lambda e: (str(e.get("red", "")), str(e.get("fecha_envio", ""))))
        return salida

    def retirados_ids(self, envio_ids: List[int]) -> set:
        """Envíos cuyo archivo ya fue retirado con éxito."""
        listos = set()
        for lote in _en_lotes(list(envio_ids)):
            for f in self._t("retiros_archivos").select("envio_id").eq("resultado", "OK").in_("envio_id", lote).execute().data or []:
                listos.add(f["envio_id"])
        return listos

    def descargados_ids(self, anio: int, semana: int) -> set:
        """Envíos que ya se descargaron en un ZIP masivo."""
        listos = set()
        for f in self._t("descargas_masivas").select("envio_ids").eq("anio", anio).eq("semana", semana) \
                .eq("estado", "DESCARGADA").execute().data or []:
            listos.update(f.get("envio_ids") or [])
        return listos

    # ------------------------------------------------------------ descarga masiva

    def _carpeta_temporal(self) -> Path:
        d = Path(Config.TEMP_DIR) / "masivas"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def limpiar_temporales(self, horas: float = 2.0, usuario: Optional[str] = None) -> int:
        """Borra ZIP masivos temporales viejos (y los de `usuario`, para no acumular)."""
        n, limite = 0, time.time() - horas * 3600
        for p in self._carpeta_temporal().glob("*.zip"):
            try:
                propio = usuario and p.name.startswith(f"{sanitizar_nombre(usuario)}__")
                if propio or p.stat().st_mtime < limite:
                    p.unlink()
                    n += 1
            except OSError:
                pass
        return n

    def _leer_archivo(self, envio: Dict) -> Tuple[Optional[bytes], str]:
        ident = str(envio.get("drive_file_id") or "")
        if ident.startswith(("/", "\\")) or (len(ident) > 2 and ident[1] == ":"):
            # Envío guardado en el servidor (modo local) y no en Drive: se lee de storage/ (nunca fuera de él).
            from src.drive_manager import LocalDriveManager
            datos = LocalDriveManager().descargar_archivo(ident)
            if datos is None:
                return None, "El envío se guardó en el servidor (no en Drive) y el archivo ya no está en storage/."
            return datos, ""
        try:
            detallado = getattr(self.drive, "descargar_archivo_detallado", None)
            if detallado:
                datos, motivo = detallado(str(envio.get("drive_file_id")))
                if datos is None:
                    return None, motivo or "Drive no devolvió el archivo (¿fue movido o eliminado?)."
                return datos, ""
            datos = self.drive.descargar_archivo(str(envio.get("drive_file_id")))
        except Exception as e:
            return None, f"Error al leer de Drive: {type(e).__name__}: {e}"
        if datos is None:
            return None, "Drive no devolvió el archivo (¿fue movido o eliminado?)."
        return datos, ""

    def preparar(self, actor: Dict, anio: int, semana: int, redes: Optional[List[str]],
                 incluir_duplicados: bool = False, progreso: Optional[Callable[[int, int, str], None]] = None) -> Dict:
        """
        Arma el/los ZIP masivos. `redes` None = todas las que la persona puede descargar.
        Devuelve {ok, partes:[...], fallos:[...], sin_archivo:[...], motivo}.
        """
        usuario = actor.get("usuario", "")
        tiene, alcance = self.permisos.alcance(actor, "DESCARGA_MASIVA")
        if not tiene:
            self.aud.registrar(usuario, "ACCESO_DENEGADO", "DESCARGAS", rol=actor.get("rol"),
                               objeto="Descarga masiva", detalle={"anio": anio, "semana": semana}, resultado="RECHAZADO")
            return {"ok": False, "motivo": "No tiene el permiso «Descarga masiva». Solicítelo a oiis.winepi.", "partes": []}
        if not self.disponible():
            return {"ok": False, "motivo": "Falta ejecutar sql/11_auditoria_permisos_repositorio.sql en Supabase.", "partes": []}
        todas = redes is None
        if not todas and alcance is not None and any(r not in alcance for r in redes):
            return {"ok": False, "motivo": "Eligió una red fuera de su alcance.", "partes": []}
        envios = self.envios_de(anio, semana, redes, incluir_duplicados, permitidas=alcance)
        con_archivo = [e for e in envios if tiene_archivo(e)]
        sin_archivo = [e for e in envios if not tiene_archivo(e)]
        if not con_archivo:
            return {"ok": False, "motivo": "No hay archivos para esa selección.", "partes": [], "sin_archivo": sin_archivo}

        self.limpiar_temporales(usuario=usuario)
        tope = Config.DESCARGA_MASIVA_MAX_MB * 1024 * 1024
        raiz = f"SEMANA_{int(semana):02d}_{int(anio)}"
        prefijo = f"{sanitizar_nombre(usuario)}__{uuid.uuid4().hex[:8]}"
        partes: List[Dict] = []
        fallos: List[Dict] = []
        actual: Optional[Dict] = None

        def abrir():
            n = len(partes) + 1
            ruta = self._carpeta_temporal() / f"{prefijo}_p{n}.zip"
            return {"n": n, "ruta": ruta, "zip": zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED, allowZip64=True),
                    "filas": [], "ids": [], "bytes": 0, "redes": set(), "nombres": set()}

        def cerrar(p):
            self._escribir_manifiesto(p, raiz, actor)
            p["zip"].close()
            partes.append(p)

        try:
            for i, e in enumerate(con_archivo, 1):
                if progreso:
                    progreso(i - 1, len(con_archivo), f"{e.get('red', '')} · {e.get('codigo_seguimiento', '')}")
                datos, motivo = self._leer_archivo(e)
                if datos is None:
                    fallos.append({"codigo": e.get("codigo_seguimiento"), "red": e.get("red"), "motivo": motivo, "id": e.get("id")})
                    continue
                if actual is not None and actual["bytes"] > 0 and actual["bytes"] + len(datos) > tope:
                    cerrar(actual)
                    actual = None
                if actual is None:
                    actual = abrir()
                carpeta = f"{raiz}/{sanitizar_nombre(str(e.get('red', 'SIN_RED')))}" + ("/DUPLICADOS" if es_duplicado(e) else "")
                nombre = f"{sanitizar_nombre(str(e.get('codigo_seguimiento') or e.get('id')))}_{_nombre_archivo(e)}"
                ruta_int, k = f"{carpeta}/{nombre}", 1
                while ruta_int in actual["nombres"]:
                    k += 1
                    ruta_int = f"{carpeta}/{k}_{nombre}"
                actual["nombres"].add(ruta_int)
                actual["zip"].writestr(zipfile.ZipInfo(ruta_int, date_time=time.localtime()[:6]), datos)
                actual["bytes"] += len(datos)
                actual["redes"].add(e.get("red"))
                actual["ids"].append(e.get("id"))
                actual["filas"].append({
                    "red": e.get("red"), "centros": _centros_texto(e), "codigo": e.get("codigo_seguimiento"),
                    "responsable": _persona(e), "correo": e.get("correo_usuario"),
                    "fecha_envio": e.get("fecha_envio"), "estado": e.get("estado"),
                    "duplicado": "Sí" if es_duplicado(e) else "No", "archivo": ruta_int, "bytes": len(datos),
                    "sha256": hashlib.sha256(datos).hexdigest()})
                del datos
            if actual is not None:
                cerrar(actual)
                actual = None
        except Exception as e:
            if actual is not None:
                try:
                    actual["zip"].close()
                except Exception:
                    pass
            self._borrar_partes(partes)
            return {"ok": False, "motivo": f"No se pudo armar el ZIP: {e}", "partes": []}

        if not partes:
            causa = (fallos[0].get("motivo") if fallos else "") or ""
            return {"ok": False, "motivo": "No se pudo leer ningún archivo de Drive." + (f" Motivo del primero: {causa}" if causa else ""),
                    "partes": [], "fallos": fallos}
        return self._registrar_partes(actor, anio, semana, redes, todas, incluir_duplicados, partes, fallos, sin_archivo, raiz)

    def _escribir_manifiesto(self, p: Dict, raiz: str, actor: Dict) -> None:
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow(["Red", "Centros", "Código de seguimiento", "Responsable", "Correo", "Fecha de envío", "Estado",
                    "Duplicado", "Archivo en este ZIP", "Tamaño (bytes)", "SHA-256 del archivo"])
        for f in p["filas"]:
            w.writerow([f["red"], f["centros"], f["codigo"], f["responsable"], f["correo"], f["fecha_envio"], f["estado"],
                        f["duplicado"], f["archivo"], f["bytes"], f["sha256"]])
        p["zip"].writestr(f"{raiz}/MANIFIESTO.csv", "﻿" + salida.getvalue())

    def _borrar_partes(self, partes: List[Dict]) -> None:
        for p in partes:
            try:
                Path(p["ruta"]).unlink()
            except OSError:
                pass

    @staticmethod
    def _sha256_archivo(ruta: Path) -> str:
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloque)
        return h.hexdigest()

    def _registrar_partes(self, actor, anio, semana, redes, todas, incluir_dup, partes, fallos, sin_archivo, raiz) -> Dict:
        usuario, rol = actor.get("usuario", ""), actor.get("rol")
        total = len(partes)
        sello = ahora_lima().strftime("%Y%m%d_%H%M")
        etiqueta = "TODAS" if todas else (sanitizar_nombre(redes[0]) if len(redes) == 1 else f"{len(redes)}_REDES")
        resultado: List[Dict] = []
        for p in partes:
            nombre = f"{raiz}_{etiqueta}_{sello}" + (f"_parte{p['n']}de{total}" if total > 1 else "") + ".zip"
            destino = Path(p["ruta"]).with_name(f"{Path(p['ruta']).stem}__{nombre}")
            try:
                Path(p["ruta"]).rename(destino)
            except OSError:
                destino = Path(p["ruta"])
            sha = self._sha256_archivo(destino)
            tamano = destino.stat().st_size
            fila = {"anio": anio, "semana": semana, "redes": sorted(r for r in p["redes"] if r), "todas_las_redes": bool(todas),
                    "incluye_duplicados": bool(incluir_dup), "parte": p["n"], "total_partes": total, "nombre_zip": nombre,
                    "n_envios": len(p["ids"]), "n_archivos": len(p["ids"]), "bytes": tamano, "sha256": sha,
                    "envio_ids": [i for i in p["ids"] if i is not None], "usuario": usuario,
                    "usuario_nombre": actor.get("nombre"), "rol": rol, "estado": "PREPARADA", "ip": self._ip()}
            try:
                self.aud.registrar(usuario, "DESCARGA_PREPARADA", "DESCARGAS", rol=rol, objeto=nombre, obligatorio=True,
                                   detalle={"anio": anio, "semana": semana, "redes": fila["redes"], "todas": bool(todas),
                                            "parte": p["n"], "total_partes": total, "n_archivos": len(p["ids"]),
                                            "bytes": tamano, "sha256": sha, "incluye_duplicados": bool(incluir_dup)})
                guardada = self._t("descargas_masivas").insert(fila).execute().data
                if not guardada:
                    raise RepositorioError("no se pudo guardar el registro de la descarga")
            except Exception as e:
                self._borrar_partes(partes)
                for r in resultado:
                    try:
                        Path(r["ruta"]).unlink()
                    except OSError:
                        pass
                return {"ok": False, "motivo": f"No se pudo dejar constancia de la descarga, por eso no se entrega el archivo: {e}", "partes": []}
            resultado.append({"descarga_id": guardada[0]["id"], "ruta": str(destino), "nombre_zip": nombre, "parte": p["n"],
                              "total_partes": total, "n_archivos": len(p["ids"]), "bytes": tamano, "sha256": sha,
                              "redes": fila["redes"]})
        return {"ok": True, "partes": resultado, "fallos": fallos, "sin_archivo": sin_archivo, "motivo": ""}

    @staticmethod
    def _ip() -> Optional[str]:
        from src.auditoria import ip_cliente
        return ip_cliente()

    def marcar_descargada(self, descarga_id: int, actor: Dict) -> Dict:
        """Se llama al hacer clic en «Descargar»: deja constancia y envía el acuse. Nunca lanza errores."""
        info: Dict = {"ok": False, "acuse": 0}
        try:
            fila = (self._t("descargas_masivas").select("*").eq("id", descarga_id).limit(1).execute().data or [None])[0]
            if not fila:
                return info
            # Solo la persona que preparó el ZIP puede registrarlo como descargado.
            if str(fila.get("usuario")).lower() != str(actor.get("usuario", "")).lower():
                return info
            ip = self._ip()
            self._t("descargas_masivas").update({"estado": "DESCARGADA", "fecha_descarga": _utc_iso(), "ip": ip or fila.get("ip")}) \
                .eq("id", descarga_id).execute()
            cuando = ahora_lima().strftime("%d/%m/%Y %H:%M:%S")
            alertas = evaluar_alertas("DESCARGA_MASIVA", {})
            self.aud.registrar(actor.get("usuario", ""), "DESCARGA_MASIVA", "DESCARGAS", rol=actor.get("rol"), objeto=fila["nombre_zip"],
                               detalle={"anio": fila["anio"], "semana": fila["semana"], "redes": fila.get("redes"),
                                        "todas": fila.get("todas_las_redes"), "parte": fila["parte"], "total_partes": fila["total_partes"],
                                        "n_archivos": fila["n_archivos"], "bytes": fila["bytes"], "sha256": fila["sha256"]}, ip=ip)
            info.update(ok=True)
            from src.email_auditoria import enviar_acuse_descarga
            info["acuse"] = enviar_acuse_descarga(self.sender, self.db, actor.get("usuario", ""), {
                "anio": fila["anio"], "semana": fila["semana"], "redes": fila.get("redes"), "todas": fila.get("todas_las_redes"),
                "parte": fila["parte"], "total_partes": fila["total_partes"], "nombre_zip": fila["nombre_zip"],
                "n_envios": fila["n_envios"], "n_archivos": fila["n_archivos"], "bytes": fila["bytes"], "sha256": fila["sha256"],
                "cuando": cuando, "ip": ip, "usuario_nombre": actor.get("nombre"), "alertas": alertas})
        except Exception as e:
            print(f"No se pudo registrar la descarga {descarga_id}: {e}")
        return info

    # ------------------------------------------------------------ retiro

    def evaluar_seleccion(self, anio: int, semana: int, envios: List[Dict]) -> Dict:
        """Clasifica una selección: retirables, ya retirados, sin archivo y cuántos no se descargaron antes."""
        ids = [e["id"] for e in envios]
        ya = self.retirados_ids(ids) if ids else set()
        desc = self.descargados_ids(anio, semana)
        retirables = [e for e in envios if tiene_archivo(e) and e["id"] not in ya]
        return {"retirables": retirables, "ya_retirados": [e for e in envios if e["id"] in ya],
                "sin_archivo": [e for e in envios if not tiene_archivo(e)],
                "sin_descarga": [e for e in retirables if e["id"] not in desc],
                "bytes": 0}

    def solicitar_retiro(self, actor: Dict, anio: int, semana: int, redes: Optional[List[str]], envios: List[Dict],
                         categoria: str, motivo: str, definitivo: bool = False) -> Dict:
        """
        Pide retirar los archivos de `envios` del repositorio. Si quien pide es el principal, se ejecuta de inmediato.
        Devuelve {ok, mensaje, solicitud, resultado}.
        """
        usuario, rol = actor.get("usuario", ""), actor.get("rol")
        tiene, alcance = self.permisos.alcance(actor, "RETIRO_REPOSITORIO")
        if not tiene:
            self.aud.registrar(usuario, "ACCESO_DENEGADO", "RETIROS", rol=rol, objeto="Retiro del repositorio",
                               detalle={"anio": anio, "semana": semana}, resultado="RECHAZADO")
            return {"ok": False, "mensaje": "No tiene el permiso «Retiro del repositorio». Solicítelo a oiis.winepi."}
        if not self.disponible():
            return {"ok": False, "mensaje": "Falta ejecutar sql/11_auditoria_permisos_repositorio.sql en Supabase."}
        if categoria not in MOTIVOS_RETIRO:
            return {"ok": False, "mensaje": "Elija un motivo de la lista."}
        err = validar_motivo(motivo)
        if err:
            return {"ok": False, "mensaje": err}
        if alcance is not None and any(e.get("red") not in alcance for e in envios):
            return {"ok": False, "mensaje": "La selección incluye redes fuera de su alcance."}
        principal = es_principal(actor)
        if definitivo and not principal:
            return {"ok": False, "mensaje": "El borrado definitivo solo lo puede decidir el SUPER_ADMIN principal."}
        ev = self.evaluar_seleccion(anio, semana, envios)
        retirables = ev["retirables"]
        if not retirables:
            return {"ok": False, "mensaje": "No hay archivos para retirar en esa selección (ya se retiraron o no tienen archivo)."}
        sin_desc = bool(ev["sin_descarga"])
        if categoria == MOTIVO_DESCARGADO and sin_desc:
            return {"ok": False, "mensaje": f"{len(ev['sin_descarga'])} envío(s) todavía no se descargaron en un ZIP masivo. "
                                            "Descárguelos primero o elija otro motivo."}
        bytes_est = 0
        sol = {"anio": anio, "semana": semana, "redes": sorted({e.get("red") for e in retirables if e.get("red")}),
               "todas_las_redes": redes is None, "envio_ids": [e["id"] for e in retirables], "n_envios": len(retirables),
               "bytes_estimados": bytes_est, "motivo_categoria": categoria, "motivo": motivo.strip()[:1000],
               "sin_descarga_previa": sin_desc, "definitivo": bool(definitivo), "solicitado_por": usuario,
               "solicitado_nombre": actor.get("nombre"), "rol_solicitante": rol, "estado": "PENDIENTE", "ip": self._ip()}
        alertas = evaluar_alertas("RETIRO_SOLICITADO", {"sin_descarga_previa": sin_desc, "n_envios": len(retirables), "definitivo": definitivo})
        try:
            self.aud.registrar(usuario, "RETIRO_SOLICITADO", "RETIROS", rol=rol, obligatorio=True,
                               objeto=f"Semana {semana}/{anio} · {len(retirables)} envío(s)",
                               detalle={"anio": anio, "semana": semana, "redes": sol["redes"], "n_envios": len(retirables),
                                        "motivo_categoria": categoria, "motivo": sol["motivo"], "sin_descarga_previa": sin_desc,
                                        "definitivo": bool(definitivo)})
            guardada = self._t("solicitudes_retiro").insert(sol).execute().data
            if not guardada:
                raise RepositorioError("no se pudo guardar la solicitud")
        except Exception as e:
            return {"ok": False, "mensaje": f"No se pudo registrar la solicitud: {e}"}
        sol = guardada[0]
        if principal:
            res = self._ejecutar(sol, actor, "Autorizado por el SUPER_ADMIN principal al solicitarlo.")
            return {"ok": res["ok"], "mensaje": res["mensaje"], "solicitud": res.get("solicitud", sol), "resultado": res}
        try:
            from src.email_auditoria import enviar_aviso_solicitud_retiro
            enviar_aviso_solicitud_retiro(self.sender, self.db, sol, alertas)
        except Exception as e:
            print(f"No se pudo avisar de la solicitud de retiro: {e}")
        return {"ok": True, "mensaje": "Solicitud registrada. Espera la aprobación de oiis.winepi; no se retiró ningún archivo.", "solicitud": sol}

    def cancelar_solicitud(self, actor: Dict, solicitud_id: int) -> Tuple[bool, str]:
        sol = self.obtener_solicitud(solicitud_id)
        if not sol or sol.get("estado") != "PENDIENTE":
            return False, "La solicitud ya no está pendiente."
        if str(sol.get("solicitado_por")).lower() != str(actor.get("usuario", "")).lower() and not es_principal(actor):
            return False, "Solo quien la hizo puede cancelarla."
        try:
            self.aud.registrar(actor.get("usuario", ""), "RETIRO_CANCELADO", "RETIROS", rol=actor.get("rol"),
                               objeto=f"Solicitud N.º {solicitud_id}", detalle={"solicitud": solicitud_id}, obligatorio=True)
        except AuditoriaError as e:
            return False, str(e)
        r = self._t("solicitudes_retiro").update({"estado": "CANCELADA", "fecha_decision": _utc_iso(), "decidido_por": actor.get("usuario"),
                                                  "decidido_nombre": actor.get("nombre"), "nota_decision": "Cancelada por quien la solicitó"}) \
            .eq("id", solicitud_id).eq("estado", "PENDIENTE").execute().data
        return (True, "Solicitud cancelada.") if r else (False, "La solicitud ya no estaba pendiente.")

    def decidir(self, token: str, solicitud_id: int, aprobar: bool, nota: str = "", definitivo: Optional[bool] = None) -> Dict:
        """Solo el SUPER_ADMIN principal. Aprobar = ejecutar el retiro."""
        if not self.auth.es_superadmin_principal(token):
            return {"ok": False, "mensaje": "Solo el SUPER_ADMIN principal puede aprobar o rechazar retiros."}
        actor = self.auth.obtener_usuario_actual(token) or {}
        sol = self.obtener_solicitud(solicitud_id)
        if not sol or sol.get("estado") != "PENDIENTE":
            return {"ok": False, "mensaje": "La solicitud ya fue resuelta o no existe."}
        if not aprobar:
            if validar_motivo(nota):
                return {"ok": False, "mensaje": "Para rechazar, explique el motivo (mínimo 15 caracteres)."}
            try:
                self.aud.registrar(actor.get("usuario", ""), "RETIRO_RECHAZADO", "RETIROS", rol=actor.get("rol"),
                                   objeto=f"Solicitud N.º {solicitud_id}", obligatorio=True,
                                   detalle={"solicitud": solicitud_id, "solicitante": sol.get("solicitado_por"), "nota": nota[:500]})
            except AuditoriaError as e:
                return {"ok": False, "mensaje": str(e)}
            r = self._t("solicitudes_retiro").update({"estado": "RECHAZADA", "decidido_por": actor.get("usuario"),
                                                      "decidido_nombre": actor.get("nombre"), "fecha_decision": _utc_iso(),
                                                      "nota_decision": nota[:500]}).eq("id", solicitud_id).eq("estado", "PENDIENTE").execute().data
            if not r:
                return {"ok": False, "mensaje": "La solicitud ya fue resuelta."}
            try:
                from src.email_auditoria import enviar_retiro_rechazado
                enviar_retiro_rechazado(self.sender, self.db, r[0], actor.get("nombre") or actor.get("usuario"), nota)
            except Exception as e:
                print(f"No se pudo avisar el rechazo: {e}")
            return {"ok": True, "mensaje": "Solicitud rechazada; se avisó a quien la hizo."}
        if definitivo is not None and bool(definitivo) != bool(sol.get("definitivo")):
            self._t("solicitudes_retiro").update({"definitivo": bool(definitivo)}).eq("id", solicitud_id).eq("estado", "PENDIENTE").execute()
            sol["definitivo"] = bool(definitivo)
        return self._ejecutar(sol, actor, nota)

    def _ejecutar(self, sol: Dict, ejecutor: Dict, nota: str = "") -> Dict:
        """Reserva la solicitud (una sola vez) y retira los archivos."""
        usuario = ejecutor.get("usuario", "")
        try:
            self.aud.registrar(usuario, "RETIRO_APROBADO", "RETIROS", rol=ejecutor.get("rol"), obligatorio=True,
                               objeto=f"Solicitud N.º {sol['id']}",
                               detalle={"solicitud": sol["id"], "solicitante": sol.get("solicitado_por"), "n_envios": sol.get("n_envios"),
                                        "sin_descarga_previa": bool(sol.get("sin_descarga_previa")), "definitivo": bool(sol.get("definitivo")),
                                        "nota": (nota or "")[:500]})
        except AuditoriaError as e:
            return {"ok": False, "mensaje": str(e)}
        reservada = self._t("solicitudes_retiro").update({"decidido_por": usuario, "decidido_nombre": ejecutor.get("nombre"),
                                                          "fecha_decision": _utc_iso(), "nota_decision": (nota or "")[:500] or None}) \
            .eq("id", sol["id"]).eq("estado", "PENDIENTE").is_("decidido_por", "null").execute().data
        if not reservada:
            return {"ok": False, "mensaje": "Otra persona ya resolvió esta solicitud."}
        sol = reservada[0]
        return self._procesar(sol, ejecutor, sol.get("envio_ids") or [])

    def reintentar(self, token: str, solicitud_id: int) -> Dict:
        """Reintenta los archivos que fallaron en un retiro PARCIAL o con ERROR (solo el principal)."""
        if not self.auth.es_superadmin_principal(token):
            return {"ok": False, "mensaje": "Solo el SUPER_ADMIN principal puede reintentar un retiro."}
        ejecutor = self.auth.obtener_usuario_actual(token) or {}
        sol = self.obtener_solicitud(solicitud_id)
        if not sol or sol.get("estado") not in ("PARCIAL", "ERROR"):
            return {"ok": False, "mensaje": "Esa solicitud no tiene archivos por reintentar."}
        hechos = {f["envio_id"] for f in self.archivos_de(solicitud_id) if f.get("resultado") == "OK"}
        faltan = [i for i in (sol.get("envio_ids") or []) if i not in hechos]
        if not faltan:
            return {"ok": False, "mensaje": "No quedan archivos pendientes."}
        try:
            self.aud.registrar(ejecutor.get("usuario", ""), "RETIRO_APROBADO", "RETIROS", rol=ejecutor.get("rol"), obligatorio=True,
                               objeto=f"Reintento de la solicitud N.º {solicitud_id}",
                               detalle={"solicitud": solicitud_id, "reintento": True, "n_envios": len(faltan)})
        except AuditoriaError as e:
            return {"ok": False, "mensaje": str(e)}
        return self._procesar(sol, ejecutor, faltan)

    def _procesar(self, sol: Dict, ejecutor: Dict, envio_ids: List[int]) -> Dict:
        usuario = ejecutor.get("usuario", "")
        definitivo = bool(sol.get("definitivo"))
        n_ok = n_error = 0
        codigos: List[str] = []
        for eid in envio_ids:
            e = self.db.obtener_envio(eid) or {"id": eid}
            if not tiene_archivo(e):
                ok, detalle = False, "El envío no tiene archivo asociado en Drive."
            else:
                try:
                    ok, detalle = self.drive.eliminar_archivo_detallado(str(e.get("drive_file_id")), definitivo)
                except Exception as ex:
                    ok, detalle = False, f"Error inesperado: {ex}"
            try:
                self._t("retiros_archivos").insert({
                    "solicitud_id": sol["id"], "envio_id": eid, "codigo_seguimiento": e.get("codigo_seguimiento"), "red": e.get("red"),
                    "semana": e.get("semana"), "anio": e.get("anio"), "centros": _centros_texto(e)[:500] or None,
                    "drive_file_id": e.get("drive_file_id"), "ruta_zip": e.get("ruta_zip"),
                    "resultado": "OK" if ok else "ERROR", "detalle": (detalle or "")[:500]}).execute()
            except Exception as ex:
                print(f"No se pudo registrar el retiro del envío {eid}: {ex}")
            if ok:
                n_ok += 1
                codigos.append(str(e.get("codigo_seguimiento") or eid))
            else:
                n_error += 1
        todos = list(sol.get("envio_ids") or [])
        hechos = {f.get("envio_id") for f in self.archivos_de(sol["id"]) if f.get("resultado") == "OK"}
        total_ok = len([i for i in todos if i in hechos])
        n_error = len(todos) - total_ok
        estado = "EJECUTADA" if n_error == 0 else ("PARCIAL" if total_ok else "ERROR")
        ahora = ahora_lima()
        self._t("solicitudes_retiro").update({"estado": estado, "n_ok": total_ok, "n_error": n_error,
                                              "fecha_ejecucion": _utc_iso()}).eq("id", sol["id"]).execute()
        sol = self.obtener_solicitud(sol["id"]) or sol
        alertas = evaluar_alertas("RETIRO_EJECUTADO", {"sin_descarga_previa": bool(sol.get("sin_descarga_previa")),
                                                       "n_envios": len(sol.get("envio_ids") or []), "definitivo": definitivo}, ahora)
        try:
            self.aud.registrar(usuario, "RETIRO_EJECUTADO", "RETIROS", rol=ejecutor.get("rol"),
                               objeto=f"Solicitud N.º {sol['id']} · semana {sol['semana']}/{sol['anio']}",
                               resultado="OK" if n_error == 0 else "ERROR",
                               detalle={"solicitud": sol["id"], "solicitante": sol.get("solicitado_por"), "n_ok": n_ok, "n_error": n_error,
                                        "n_envios": len(sol.get("envio_ids") or []), "redes": sol.get("redes"),
                                        "sin_descarga_previa": bool(sol.get("sin_descarga_previa")), "definitivo": definitivo,
                                        "motivo_categoria": sol.get("motivo_categoria"), "codigos": codigos[:300]})
        except Exception as ex:
            print(f"Retiro hecho pero no se pudo auditar: {ex}")
        resumen = {"n_ok": total_ok, "n_error": n_error, "cuando": ahora.strftime("%d/%m/%Y %H:%M:%S"),
                   "ejecutado_por": usuario, "ejecutado_nombre": ejecutor.get("nombre") or usuario, "alertas": alertas}
        acuse = 0
        try:
            from src.auditoria_excel import generar_excel_retiro, nombre_excel_retiro
            from src.email_auditoria import enviar_acuse_retiro
            xlsx = generar_excel_retiro(sol, self.archivos_de(sol["id"]), resumen)
            adj = [(nombre_excel_retiro(sol), xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
            acuse = enviar_acuse_retiro(self.sender, self.db, sol, resumen, adj)
        except Exception as ex:
            print(f"No se pudo enviar el acuse del retiro: {ex}")
        if n_error == 0:
            msg = f"Se retiraron {total_ok} archivo(s) {'definitivamente' if definitivo else 'a la papelera de Drive'}. Se envió el acuse."
        elif total_ok:
            msg = f"Se retiraron {total_ok} archivo(s); {n_error} fallaron y se pueden reintentar."
        else:
            msg = f"No se pudo retirar ningún archivo ({n_error} con error). Revise el detalle."
        return {"ok": n_error == 0 or total_ok > 0, "mensaje": msg, "solicitud": sol, "n_ok": total_ok, "n_error": n_error, "acuses": acuse}

    # ------------------------------------------------------------ consulta

    def obtener_solicitud(self, solicitud_id: int) -> Optional[Dict]:
        r = self._t("solicitudes_retiro").select("*").eq("id", solicitud_id).limit(1).execute().data
        return r[0] if r else None

    def listar_solicitudes(self, estado: Optional[str] = None, solicitante: Optional[str] = None, limite: int = 100) -> List[Dict]:
        if not self.disponible():
            return []
        q = self._t("solicitudes_retiro").select("*")
        if estado:
            q = q.eq("estado", estado)
        if solicitante:
            q = q.eq("solicitado_por", solicitante)
        return q.order("id", desc=True).limit(limite).execute().data or []

    def pendientes(self) -> int:
        try:
            return len(self._t("solicitudes_retiro").select("id").eq("estado", "PENDIENTE").execute().data or [])
        except Exception:
            return 0

    def archivos_de(self, solicitud_id: int) -> List[Dict]:
        return self._t("retiros_archivos").select("*").eq("solicitud_id", solicitud_id).order("id").execute().data or []

    def listar_descargas(self, limite: int = 100, usuario: Optional[str] = None) -> List[Dict]:
        if not self.disponible():
            return []
        q = self._t("descargas_masivas").select("*")
        if usuario:
            q = q.eq("usuario", usuario)
        return q.order("id", desc=True).limit(limite).execute().data or []

    # ------------------------------------------------------------ duplicados

    def puede_gestionar_duplicados(self, actor: Dict) -> Tuple[bool, str]:
        """¿Puede eliminar duplicados? Exige el permiso «Retiro del repositorio» (el principal siempre puede)."""
        if es_principal(actor):
            return True, ""
        if not self.disponible():
            return False, "Falta ejecutar sql/11_auditoria_permisos_repositorio.sql; mientras tanto solo oiis.winepi puede eliminar duplicados."
        if not self.permisos.tiene(actor, "RETIRO_REPOSITORIO"):
            self.aud.registrar(actor.get("usuario", ""), "ACCESO_DENEGADO", "DUPLICADOS", rol=actor.get("rol"),
                               objeto="Eliminar duplicados", resultado="RECHAZADO")
            return False, "No tiene el permiso «Retiro del repositorio». Solicítelo a oiis.winepi."
        return True, ""

    def registrar_duplicados_eliminados(self, actor: Dict, items: List[Tuple[str, str, str]], n_ok: int, n_error: int,
                                        borro_drive: bool) -> None:
        """Auditoría y acuse de la eliminación de duplicados (items = [(código, red, resultado)])."""
        usuario = actor.get("usuario", "")
        alertas = evaluar_alertas("DUPLICADO_ELIMINADO", {"n_archivos": n_ok})
        self.aud.registrar(usuario, "DUPLICADO_ELIMINADO", "DUPLICADOS", rol=actor.get("rol"),
                           objeto=f"{n_ok} duplicado(s)", resultado="OK" if n_error == 0 else "ERROR",
                           detalle={"n_ok": n_ok, "n_error": n_error, "n_archivos": n_ok, "borro_drive": bool(borro_drive),
                                    "items": [list(i) for i in items[:200]]})
        try:
            from src.email_auditoria import enviar_acuse_duplicados
            enviar_acuse_duplicados(self.sender, self.db, usuario, actor.get("nombre") or usuario, {
                "items": items, "n_ok": n_ok, "n_error": n_error, "borro_drive": borro_drive,
                "cuando": ahora_lima().strftime("%d/%m/%Y %H:%M:%S"), "alertas": alertas})
        except Exception as e:
            print(f"No se pudo enviar el acuse de duplicados: {e}")


_repositorio = None


def get_repositorio() -> Repositorio:
    global _repositorio
    from src.db_manager import get_db_manager
    db = get_db_manager()
    if _repositorio is None or _repositorio.db is not db:
        _repositorio = Repositorio(db)
    return _repositorio
