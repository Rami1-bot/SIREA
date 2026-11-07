# src/cambios_configuracion.py
"""
Cambios de configuración protegidos (v7.5).

Todo lo que modifica cómo funciona el sistema para las redes pasa por aquí:

  · semana activa, fecha de corte y tamaño máximo del ZIP,
  · años epidemiológicos (crear, editar, activar, eliminar) y años permitidos,
  · centros excluidos (excluir, reincorporar, limpiar una red),
  · carpetas de Drive (agregar, activar, eliminar).

Cada cambio, sin excepción:
  1. exige el permiso «CONFIGURACION» (el SUPER_ADMIN principal siempre lo tiene y es
     el único que lo reparte, en «Permisos»),
  2. exige un MOTIVO escrito (mínimo 8 caracteres),
  3. cumple reglas de sentido común (corte futuro y no demasiado lejano, no se elimina
     un año con envíos, semana que no retrocede sin confirmación expresa...),
  4. deja constancia en la auditoría ANTES de hacerse, con el valor anterior y el nuevo
     (si no se puede dejar constancia, el cambio NO se hace),
  5. avisa por correo a quien lo hizo y al SUPER_ADMIN principal.

Las pantallas solo llaman a estos métodos; no escriben en la base de datos directamente.
Todos devuelven (ok: bool, mensaje: str).
"""

import os
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from src.auditoria import AuditoriaError, ahora_lima, get_auditoria
from src.config import Config
from src.permisos import es_principal, get_permisos

MOTIVO_MIN = 8
MOTIVO_MAX = 300
PERMISO = "CONFIGURACION"
FORMATO_CORTE = "%Y-%m-%d %H:%M:%S"

Resultado = Tuple[bool, str]


def _t(valor) -> str:
    return "" if valor is None else str(valor)


def _parsear_corte(texto) -> Optional[datetime]:
    if isinstance(texto, datetime):
        return texto.replace(tzinfo=None)
    t = _t(texto).strip()
    for f in (FORMATO_CORTE, "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            continue
    return None


def _a_fecha(valor) -> Optional[date]:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(_t(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


class CambiosConfiguracion:
    def __init__(self, db=None, auditoria=None, permisos=None, sender=None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._aud, self._permisos, self._sender = auditoria, permisos, sender

    # ------------------------------------------------------------ piezas

    @property
    def aud(self):
        if self._aud is None:
            self._aud = get_auditoria()
        return self._aud

    @property
    def permisos(self):
        if self._permisos is None:
            self._permisos = get_permisos()
        return self._permisos

    def puede(self, actor: Optional[Dict]) -> bool:
        """True si la persona puede cambiar la configuración (principal o con el permiso vigente)."""
        if not actor or not actor.get("usuario"):
            return False
        return es_principal(actor) or self.permisos.tiene(actor, PERMISO)

    @staticmethod
    def motivo_valido(motivo: str) -> Tuple[bool, str]:
        m = " ".join(_t(motivo).split())
        if len(m) < MOTIVO_MIN:
            return False, f"Escriba el motivo del cambio (mínimo {MOTIVO_MIN} caracteres). Queda registrado en la auditoría."
        return True, m[:MOTIVO_MAX]

    def _autorizar(self, actor: Optional[Dict], accion: str, objeto: str, motivo: str) -> Tuple[Optional[str], str]:
        """(error, motivo_limpio). Verifica permiso y motivo."""
        if not self.puede(actor):
            try:
                self.aud.registrar((actor or {}).get("usuario", "?"), "ACCESO_DENEGADO", "CONFIGURACION",
                                   rol=(actor or {}).get("rol"), objeto=objeto, resultado="RECHAZADO",
                                   detalle={"intento": accion})
            except Exception:
                pass
            return ("No tiene el permiso para cambiar la configuración. Pídalo al SUPER_ADMIN principal "
                    "(sección «Permisos»)."), ""
        ok, m = self.motivo_valido(motivo)
        if not ok:
            return m, ""
        return None, m

    def _correo(self, actor: Dict, titulo: str, objeto: str, cambios: List[Tuple[str, str, str]], motivo: str,
                alertas: Optional[List[str]] = None) -> None:
        try:
            from src.email_auditoria import enviar_aviso_configuracion
            sender = self._sender
            if sender is None:
                from src.email_sender import get_email_sender
                sender = get_email_sender()
            enviar_aviso_configuracion(sender, self.db, actor.get("usuario", ""), actor.get("nombre") or actor.get("usuario", ""), {
                "titulo": titulo, "objeto": objeto, "cambios": cambios, "motivo": motivo,
                "cuando": ahora_lima().strftime("%d/%m/%Y %H:%M:%S"), "alertas": alertas or []})
        except Exception as e:
            print(f"No se pudo avisar del cambio de configuración: {e}")

    def _ejecutar(self, actor: Dict, accion: str, titulo: str, objeto: str, motivo: str, detalle: Dict,
                  cambios: List[Tuple[str, str, str]], hacer, exito: str) -> Resultado:
        """
        Constancia obligatoria → cambio → aviso. `hacer()` devuelve (ok, mensaje_error).
        Si el cambio falla, queda además un registro con resultado ERROR.
        """
        det = dict(detalle)
        det["motivo"] = motivo
        det["cambios"] = [list(c) for c in cambios]
        try:
            self.aud.registrar(actor["usuario"], accion, "CONFIGURACION", rol=actor.get("rol"), objeto=objeto,
                               detalle=det, obligatorio=True)
        except AuditoriaError as e:
            return False, f"No se hizo el cambio porque no se pudo dejar constancia en la auditoría. {e}"
        try:
            ok, error = hacer()
        except Exception as e:                       # nunca dejar pasar un error sin registro
            ok, error = False, f"{type(e).__name__}: {e}"
        if not ok:
            try:
                self.aud.registrar(actor["usuario"], accion, "CONFIGURACION", rol=actor.get("rol"), objeto=objeto,
                                   resultado="ERROR", detalle={"motivo": motivo, "error": _t(error)[:300]})
            except Exception:
                pass
            return False, error or "No se pudo guardar el cambio."
        from src.auditoria import evaluar_alertas
        self._correo(actor, titulo, objeto, cambios, motivo, evaluar_alertas(accion, det))
        return True, exito

    def _guardar_claves(self, pares: List[Tuple[str, str, str]]) -> Resultado:
        """pares = [(clave, nuevo, previo)]. Si una falla, devuelve las anteriores a su valor (no deja el cambio a medias)."""
        hechos: List[Tuple[str, str]] = []
        for clave, nuevo, previo in pares:
            ok, det = self.db.guardar_configuracion(clave, nuevo)
            if not ok:
                for c, p in hechos:
                    try:
                        self.db.guardar_configuracion(c, p)
                    except Exception:
                        pass
                return False, det
            hechos.append((clave, previo))
        return True, ""

    def _contar_envios_anio(self, anio: int) -> Optional[int]:
        """Envíos registrados del año (None si no se pudo comprobar: se trata como «no se sabe»)."""
        try:
            r = self.db.supabase.table("envios").select("id", count="exact").eq("anio", anio).limit(1).execute()
            n = getattr(r, "count", None)
            return int(n) if n is not None else len(r.data or [])
        except Exception as e:
            print(f"No se pudo contar los envíos del año {anio}: {e}")
            return None

    # ------------------------------------------------------------ semana, corte y tamaño del ZIP

    def guardar_parametros(self, actor: Dict, semana: int, corte, tamano_zip_mb: int, motivo: str,
                           excepcional: bool = False) -> Resultado:
        semana_prev = self.db.obtener_configuracion("semana_activa")
        corte_prev_txt = self.db.obtener_configuracion("fecha_corte") or Config.get_fecha_corte()
        tam_prev = self.db.obtener_configuracion("tamano_maximo_zip_mb") or str(Config.get_tamano_maximo_zip_mb())
        try:
            semana_prev_n = int(semana_prev) if semana_prev else Config.get_semana_actual()
        except (TypeError, ValueError):
            semana_prev_n = Config.get_semana_actual()
        corte_nuevo = _parsear_corte(corte)
        if corte_nuevo is None:
            return False, "La fecha de corte no es válida."
        corte_prev = _parsear_corte(corte_prev_txt)
        corte_nuevo_txt = corte_nuevo.strftime(FORMATO_CORTE)

        cambios: List[Tuple[str, str, str]] = []
        if int(semana) != semana_prev_n:
            cambios.append(("Semana activa", str(semana_prev_n), str(int(semana))))
        if corte_prev is None or corte_nuevo_txt != corte_prev.strftime(FORMATO_CORTE):
            cambios.append(("Fecha de corte", corte_prev.strftime(FORMATO_CORTE) if corte_prev else "—", corte_nuevo_txt))
        if int(tamano_zip_mb) != int(tam_prev or 0):
            cambios.append(("Tamaño máximo del ZIP (MB)", _t(tam_prev), str(int(tamano_zip_mb))))
        if not cambios:
            return True, "No había cambios que guardar."

        err, m = self._autorizar(actor, "CONFIG_PARAMETROS", "Parámetros generales", motivo)
        if err:
            return False, err

        # --- reglas (solo sobre lo que cambia)
        anio_activo = self.db.obtener_anio_activo_epidemiologico() or {}
        maximo_semanas = int(anio_activo.get("semanas") or 53)
        es_excepcional = False
        if int(semana) != semana_prev_n:
            if not 1 <= int(semana) <= maximo_semanas:
                return False, f"La semana debe estar entre 1 y {maximo_semanas}."
            if int(semana) < semana_prev_n or int(semana) > semana_prev_n + 2:
                es_excepcional = True
                if not excepcional:
                    return False, ("Cambiar la semana activa hacia atrás, o saltar más de 2 semanas, es excepcional. "
                                   "Marque «Es un cambio excepcional» para continuar.")
        ahora = ahora_lima()
        if any(c[0] == "Fecha de corte" for c in cambios):
            if corte_nuevo <= ahora:
                return False, "La fecha de corte debe ser posterior a este momento."
            limite = ahora + timedelta(days=Config.CORTE_MAX_DIAS_FUTURO)
            if corte_nuevo > limite:
                return False, (f"La fecha de corte no puede pasar de {Config.CORTE_MAX_DIAS_FUTURO} días desde hoy "
                               f"(hasta el {limite:%d/%m/%Y}).")
        if any(c[0].startswith("Tamaño") for c in cambios) and not 10 <= int(tamano_zip_mb) <= 200:
            return False, "El tamaño máximo del ZIP debe estar entre 10 y 200 MB."

        pares = []
        for campo, antes, despues in cambios:
            clave = {"Semana activa": "semana_activa", "Fecha de corte": "fecha_corte",
                     "Tamaño máximo del ZIP (MB)": "tamano_maximo_zip_mb"}[campo]
            pares.append((clave, despues, antes if antes != "—" else ""))

        def hacer():
            ok, det = self._guardar_claves(pares)
            if ok:
                self._copia_env(int(semana), corte_nuevo_txt, int(tamano_zip_mb))
            return ok, det

        return self._ejecutar(actor, "CONFIG_PARAMETROS", "Cambio de semana, corte o tamaño del ZIP", "Parámetros generales",
                              m, {"excepcional": es_excepcional}, cambios, hacer, "Parámetros guardados.")

    @staticmethod
    def _copia_env(semana: int, corte_txt: str, tamano: int) -> None:
        """Copia en .env solo como respaldo; en Docker puede ser de solo lectura."""
        try:
            from dotenv import set_key
            env_path = Config.BASE_DIR / ".env"
            if env_path.exists():
                set_key(str(env_path), "SEMANA_ACTUAL", str(semana))
                set_key(str(env_path), "FECHA_CORTE", corte_txt)
                set_key(str(env_path), "TAMANO_MAXIMO_ZIP_MB", str(tamano))
        except Exception:
            pass

    # ------------------------------------------------------------ años epidemiológicos

    @staticmethod
    def _validar_fechas_anio(inicio, fin, semanas) -> Optional[str]:
        i, f = _a_fecha(inicio), _a_fecha(fin)
        if i is None or f is None:
            return "Las fechas del año no son válidas."
        if f <= i:
            return "La fecha de fin debe ser posterior a la de inicio."
        dias = (f - i).days + 1
        if not 350 <= dias <= 380:
            return f"Un año epidemiológico dura unas 52 o 53 semanas; el rango elegido tiene {dias} días."
        if int(semanas) not in (52, 53):
            return "El año epidemiológico tiene 52 o 53 semanas."
        return None

    def crear_anio(self, actor: Dict, anio: int, semanas: int, inicio, fin, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "ANIO_CREADO", f"Año {anio}", motivo)
        if err:
            return False, err
        if not 2000 <= int(anio) <= 2100:
            return False, "El año debe estar entre 2000 y 2100."
        if self.db.obtener_anio_epidemiologico(int(anio)):
            return False, f"El año {anio} ya existe."
        e = self._validar_fechas_anio(inicio, fin, semanas)
        if e:
            return False, e
        i, f = _a_fecha(inicio), _a_fecha(fin)
        cambios = [("Año", "—", str(int(anio))), ("Semanas", "—", str(int(semanas))),
                   ("Inicio", "—", i.strftime("%d/%m/%Y")), ("Fin", "—", f.strftime("%d/%m/%Y"))]
        return self._ejecutar(
            actor, "ANIO_CREADO", f"Año epidemiológico {anio} creado", f"Año {anio}", m, {"anio": int(anio)}, cambios,
            lambda: (self.db.crear_anio_epidemiologico(int(anio), int(semanas), i.strftime("%Y-%m-%d"),
                                                       f.strftime("%Y-%m-%d"), activo=False), "No se pudo crear el año."),
            f"Año {anio} agregado.")

    def actualizar_anio(self, actor: Dict, anio: int, semanas: int, inicio, fin, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "ANIO_EDITADO", f"Año {anio}", motivo)
        if err:
            return False, err
        previo = self.db.obtener_anio_epidemiologico(int(anio))
        if not previo:
            return False, f"El año {anio} no existe."
        e = self._validar_fechas_anio(inicio, fin, semanas)
        if e:
            return False, e
        i, f = _a_fecha(inicio), _a_fecha(fin)
        cambios = []
        if int(previo.get("semanas") or 0) != int(semanas):
            cambios.append(("Semanas", _t(previo.get("semanas")), str(int(semanas))))
        if _a_fecha(previo.get("fecha_inicio")) != i:
            cambios.append(("Inicio", _t(previo.get("fecha_inicio")), i.strftime("%Y-%m-%d")))
        if _a_fecha(previo.get("fecha_fin")) != f:
            cambios.append(("Fin", _t(previo.get("fecha_fin")), f.strftime("%Y-%m-%d")))
        if not cambios:
            return True, "No había cambios que guardar."
        n = self._contar_envios_anio(int(anio))
        return self._ejecutar(
            actor, "ANIO_EDITADO", f"Año epidemiológico {anio} editado", f"Año {anio}", m,
            {"anio": int(anio), "tiene_envios": bool(n), "envios": n}, cambios,
            lambda: (self.db.actualizar_anio_epidemiologico(int(anio), semanas=int(semanas), fecha_inicio=i.strftime("%Y-%m-%d"),
                                                            fecha_fin=f.strftime("%Y-%m-%d")), "No se pudo actualizar el año."),
            f"Año {anio} actualizado.")

    def activar_anio(self, actor: Dict, anio: int, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "ANIO_ACTIVADO", f"Año {anio}", motivo)
        if err:
            return False, err
        if not self.db.obtener_anio_epidemiologico(int(anio)):
            return False, f"El año {anio} no existe."
        activo = (self.db.obtener_anio_activo_epidemiologico() or {}).get("anio")
        if activo == int(anio):
            return True, f"El año {anio} ya estaba activo."
        return self._ejecutar(
            actor, "ANIO_ACTIVADO", f"Año epidemiológico {anio} activado", f"Año {anio}", m, {"anio": int(anio)},
            [("Año activo", _t(activo) or "—", str(int(anio)))],
            lambda: (self.db.activar_anio_epidemiologico(int(anio)), "No se pudo activar el año."),
            f"Año {anio} activado.")

    def eliminar_anio(self, actor: Dict, anio: int, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "ANIO_ELIMINADO", f"Año {anio}", motivo)
        if err:
            return False, err
        previo = self.db.obtener_anio_epidemiologico(int(anio))
        if not previo:
            return False, f"El año {anio} no existe."
        if previo.get("activo"):
            return False, "No se puede eliminar el año activo."
        n = self._contar_envios_anio(int(anio))
        if n is None:
            return False, "No se pudo comprobar si el año tiene envíos, así que no se elimina. Intente de nuevo."
        if n > 0:
            return False, f"El año {anio} tiene {n} envío(s) registrado(s). Un año con envíos no se elimina."
        return self._ejecutar(
            actor, "ANIO_ELIMINADO", f"Año epidemiológico {anio} eliminado", f"Año {anio}", m,
            {"anio": int(anio), "semanas": previo.get("semanas"), "inicio": _t(previo.get("fecha_inicio")),
             "fin": _t(previo.get("fecha_fin"))},
            [("Año", str(int(anio)), "eliminado")],
            lambda: (self.db.eliminar_anio_epidemiologico(int(anio)), "No se pudo eliminar el año."),
            f"Año {anio} eliminado.")

    def guardar_anios_permitidos(self, actor: Dict, max_anteriores: int, permitir_anteriores: bool,
                                 permitir_adelantados: bool, motivo: str) -> Resultado:
        def _bool(v, defecto):
            return defecto if v in (None, "") else _t(v).strip().lower() == "true"
        prev_max = self.db.obtener_configuracion("años_anteriores_permitidos")
        prev_ant = _bool(self.db.obtener_configuracion("permitir_anios_anteriores"), True)
        prev_adel = _bool(self.db.obtener_configuracion("permitir_envios_adelantados"), False)
        prev_max_n = int(prev_max) if prev_max not in (None, "") else 2
        cambios = []
        if int(max_anteriores) != prev_max_n:
            cambios.append(("Años anteriores permitidos", str(prev_max_n), str(int(max_anteriores))))
        if bool(permitir_anteriores) != prev_ant:
            cambios.append(("Permitir envíos de años anteriores", "sí" if prev_ant else "no", "sí" if permitir_anteriores else "no"))
        if bool(permitir_adelantados) != prev_adel:
            cambios.append(("Permitir envíos adelantados", "sí" if prev_adel else "no", "sí" if permitir_adelantados else "no"))
        if not cambios:
            return True, "No había cambios que guardar."
        err, m = self._autorizar(actor, "ANIOS_PERMITIDOS", "Años permitidos para envío", motivo)
        if err:
            return False, err
        if not 0 <= int(max_anteriores) <= 5:
            return False, "Los años anteriores permitidos deben estar entre 0 y 5."
        pares = [("años_anteriores_permitidos", str(int(max_anteriores)), str(prev_max_n)),
                 ("permitir_anios_anteriores", str(bool(permitir_anteriores)).lower(), str(prev_ant).lower()),
                 ("permitir_envios_adelantados", str(bool(permitir_adelantados)).lower(), str(prev_adel).lower())]
        return self._ejecutar(actor, "ANIOS_PERMITIDOS", "Cambio en los años permitidos para envío", "Años permitidos",
                              m, {}, cambios, lambda: self._guardar_claves(pares), "Configuración de años guardada.")

    # ------------------------------------------------------------ centros excluidos

    def excluir_centro(self, actor: Dict, red: str, centro: str, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "EXCLUSION_AGREGADA", f"{red} · {centro}", motivo)
        if err:
            return False, err
        if not red or not centro:
            return False, "Elija la red y el centro."
        nombre = actor.get("nombre") or actor.get("usuario", "")
        return self._ejecutar(
            actor, "EXCLUSION_AGREGADA", "Centro excluido de los totales", f"{red} · {centro}", m,
            {"red": red, "centro": centro}, [("Centro", "cuenta en los totales", "excluido")],
            lambda: (self.db.agregar_centro_excluido(red_nombre=red, centro_nombre=centro, motivo=m, creado_por=nombre),
                     f"Verifique que la red {red} exista."),
            f"Centro «{centro}» excluido de la red {red}.")

    def reincorporar_centro(self, actor: Dict, red: str, centro: str, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "EXCLUSION_QUITADA", f"{red} · {centro}", motivo)
        if err:
            return False, err
        return self._ejecutar(
            actor, "EXCLUSION_QUITADA", "Centro reincorporado a los totales", f"{red} · {centro}", m,
            {"red": red, "centro": centro}, [("Centro", "excluido", "cuenta en los totales")],
            lambda: (self.db.eliminar_centro_excluido(red, centro), f"Verifique que la red {red} exista."),
            f"Centro «{centro}» reincorporado a la red {red}.")

    def limpiar_exclusiones(self, actor: Dict, red: str, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "EXCLUSIONES_LIMPIADAS", red, motivo)
        if err:
            return False, err
        n = self.db.contar_centros_excluidos(red)
        return self._ejecutar(
            actor, "EXCLUSIONES_LIMPIADAS", "Exclusiones de una red limpiadas", red, m,
            {"red": red, "centros": n}, [("Centros excluidos", str(n), "0")],
            lambda: (self.db.limpiar_centros_excluidos(red), "No se pudieron limpiar las exclusiones."),
            f"Se limpiaron las exclusiones de la red {red}.")

    # ------------------------------------------------------------ carpetas de Drive

    def crear_carpeta(self, actor: Dict, nombre: str, folder_id: str, capacidad_mb: int, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "CARPETA_DRIVE_CREADA", _t(nombre), motivo)
        if err:
            return False, err
        nombre, folder_id = _t(nombre).strip(), _t(folder_id).strip()
        if not nombre or not folder_id:
            return False, "Nombre e ID son obligatorios."
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", folder_id):
            return False, "El ID de la carpeta no tiene el formato de Google Drive (solo letras, números, guion y guion bajo)."
        return self._ejecutar(
            actor, "CARPETA_DRIVE_CREADA", "Carpeta de Drive agregada", nombre, m,
            {"folder_id": folder_id, "capacidad_mb": int(capacidad_mb)},
            [("Carpeta", "—", f"{nombre} ({folder_id})")],
            lambda: (self.db.crear_carpeta_drive(nombre, folder_id, int(capacidad_mb)), "No se pudo agregar la carpeta."),
            f"Carpeta {nombre} agregada.")

    def activar_carpeta(self, actor: Dict, carpeta_id: int, nombre: str, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "CARPETA_DRIVE_ACTIVADA", _t(nombre), motivo)
        if err:
            return False, err
        activa = (self.db.obtener_carpeta_activa() or {}).get("nombre")
        return self._ejecutar(
            actor, "CARPETA_DRIVE_ACTIVADA", "Carpeta de Drive activada", nombre, m, {"carpeta_id": carpeta_id},
            [("Carpeta activa", _t(activa) or "—", _t(nombre))],
            lambda: self.db.cambiar_carpeta_activa_detallado(carpeta_id), f"Carpeta «{nombre}» activada.")

    def eliminar_carpeta(self, actor: Dict, carpeta_id: int, nombre: str, motivo: str) -> Resultado:
        err, m = self._autorizar(actor, "CARPETA_DRIVE_ELIMINADA", _t(nombre), motivo)
        if err:
            return False, err
        return self._ejecutar(
            actor, "CARPETA_DRIVE_ELIMINADA", "Carpeta de Drive eliminada del sistema", nombre, m, {"carpeta_id": carpeta_id},
            [("Carpeta", _t(nombre), "eliminada del sistema")],
            lambda: (self.db.eliminar_carpeta_drive(carpeta_id), "No se pudo eliminar. Solo se pueden eliminar carpetas inactivas."),
            f"Carpeta «{nombre}» eliminada.")


_cambios = None


def get_cambios_configuracion() -> CambiosConfiguracion:
    global _cambios
    from src.db_manager import get_db_manager
    db = get_db_manager()
    if _cambios is None or _cambios.db is not db:
        _cambios = CambiosConfiguracion(db)
    return _cambios
