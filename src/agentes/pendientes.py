# src/agentes/pendientes.py
"""
Centro de pendientes (SIREA 3.1): todo lo que hoy requiere a un
administrador, ordenado por secciones como un catálogo.

Regla de diseño: **las reglas detectan; la IA solo donde hace falta pensar.**
  * Redes atrasadas y Observaciones: además de detectar, el Agente
    Operativo ya dejó propuestas (IA).
  * Almacenamiento, Duplicados, Cierre, Respaldos, Solicitudes: los detecta
    una regla (rápido, gratis, sin errores) y se sugiere qué hacer.
  * Almacenamiento es de uso RESTRINGIDO: solo sugiere qué semanas se
    podrían retirar de Drive; el retiro se hace en «Descarga y limpieza»,
    con sus permisos, su aprobación y su papelera. Nada se borra desde aquí.

Este módulo no usa Streamlit ni llama a ningún modelo: devuelve datos que
la pantalla muestra. Si una sección falla, se informa y las demás siguen.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

UMBRAL_DRIVE_PCT = float(os.getenv("ALMACENAMIENTO_UMBRAL_PCT", "80") or 80)
SEMANAS_ANTIGUEDAD = int(os.getenv("ALMACENAMIENTO_SEMANAS_ANTIGUEDAD", "4") or 4)


@dataclass
class Pendiente:
    clave: str
    titulo: str
    destino: Optional[str]            # clave de sección del panel (admin.py) o None
    tono: str                         # ok | info | warn | bad | mute
    cifra: str                        # lo grande de la tarjeta
    resumen: str                      # una línea
    detalle: List[str] = field(default_factory=list)
    origen: str = "regla"             # regla | regla + IA
    nivel: str = "permitido"          # permitido | restringido
    accion: str = ""                  # texto del botón
    solo_super_admin: bool = False

    @property
    def requiere_atencion(self) -> bool:
        return self.tono in ("warn", "bad")


def _db():
    from src.db_manager import get_db_manager
    return get_db_manager()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _parse(v) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _propuestas(tipos) -> List[Dict]:
    try:
        from src.agentes import agente_operativo as ag
        return [p for p in ag.propuestas("PROPUESTA") if p.get("tipo") in set(tipos)]
    except Exception:
        return []


# ------------------------------------------------------------
# secciones
# ------------------------------------------------------------

def redes_atrasadas() -> Pendiente:
    from src.agentes.herramientas import info_semana_actual, progreso_de_todas_las_redes
    info = info_semana_actual()
    anio, semana = int(info["anio"]), int(info["semana_activa"])
    prog = [p for p in progreso_de_todas_las_redes(anio, semana) if p.get("total_centros")]
    incompletas = sorted([p for p in prog if (p.get("porcentaje") or 0) < 100], key=lambda p: p.get("porcentaje") or 0)
    sug = _propuestas(["RECORDATORIO_RED"])
    horas = None
    try:
        from src.agentes.agente_operativo import _horas_al_corte
        horas = _horas_al_corte()
    except Exception:
        pass
    if not incompletas:
        return Pendiente("redes", "Redes atrasadas", "Notificaciones", "ok", "0",
                         f"Todas las redes completaron la semana {semana}.", origen="regla + IA", accion="Ir a Notificaciones")
    vencido = horas is not None and horas < 0
    resumen = (f"{len(incompletas)} de {len(prog)} redes no completan la semana {semana}"
               + (" y el corte ya venció." if vencido else (f"; faltan {int(horas)} h para el corte." if horas is not None else ".")))
    detalle = [f"{p['red']}: {p.get('recibidos', 0)} de {p.get('total_centros')} centros ({p.get('porcentaje', 0)} %)"
               for p in incompletas[:5]]
    if sug:
        detalle.insert(0, f"El agente dejó {len(sug)} recordatorio(s) listos para revisar en Notificaciones.")
    try:   # SIREA 3.2: las que suelen atrasarse conviene recordarlas antes del corte
        from src.agentes import patrones
        con_patron = [p["red"] for p in patrones.redes_con_patron() if p.get("suele_atrasarse")]
        if con_patron:
            detalle.append(f"Suelen atrasarse (ver «Patrones»): {', '.join(con_patron[:5])}.")
    except Exception:
        pass
    tono = "bad" if vencido else ("warn" if horas is not None and horas <= 48 else "info")
    return Pendiente("redes", "Redes atrasadas", "Notificaciones", tono, str(len(incompletas)), resumen, detalle,
                     origen="regla + IA", accion="Ir a Notificaciones")


def observaciones() -> Pendiente:
    from src.observaciones import get_observaciones
    obs = get_observaciones()
    if not obs.disponible():
        return Pendiente("observaciones", "Observaciones", "Observaciones", "mute", "—",
                         "Falta la tabla de observaciones (sql/13).", accion="Ir a Observaciones")
    c = obs.contadores()
    total = int(c.get("normales", 0)) + int(c.get("fallas", 0))
    sug = _propuestas(["SOLICITAR_CORRECCION", "MARCAR_REVISADA", "REINTENTAR_FALLA"])
    detalle = []
    if c.get("fallas"):
        detalle.append(f"{c['fallas']} falla(s) técnica(s) por reintentar o escalar.")
    if c.get("normales"):
        detalle.append(f"{c['normales']} comentario(s) o envío(s) por revisar.")
    if sug:
        detalle.insert(0, f"El agente ya propuso qué hacer con {len(sug)} de ellas.")
    tono = "ok" if not total else ("bad" if c.get("fallas") else "warn")
    return Pendiente("observaciones", "Observaciones", "Observaciones", tono, str(total),
                     "Nada pendiente en la bandeja." if not total else f"{total} sin revisar.", detalle,
                     origen="regla + IA", accion="Ir a Observaciones")


def _uso_drive() -> Optional[Dict]:
    try:
        from src.drive_manager import get_drive_manager
        q = get_drive_manager().obtener_espacio_usado() or {}
        limite, usado = int(q.get("limite_bytes") or 0), int(q.get("usado_bytes") or 0)
        return {"limite": limite, "usado": usado, "pct": round(100 * usado / limite, 1) if limite else None}
    except Exception:
        return None


def semanas_para_liberar(anio: int, semana_activa: int, antiguedad: int = SEMANAS_ANTIGUEDAD) -> List[Dict]:
    """
    Semanas antiguas (anteriores a semana_activa - antiguedad) que aún tienen
    archivos en Drive, con cuántos ya se descargaron. Solo LECTURA.
    [{'anio','semana','en_drive','descargados','lista'}] ordenado de la más antigua.
    """
    from src.repositorio import tiene_archivo
    from utils.duplicados import es_duplicado, es_reemplazado
    limite = semana_activa - antiguedad
    if limite < 1:
        return []
    t = _db().supabase.table
    envios: List[Dict] = []
    offset = 0
    while True:
        lote = (t("envios").select("id,semana,anio,drive_file_id,observacion").eq("anio", anio)
                .lte("semana", limite).range(offset, offset + 999).execute().data or [])
        envios.extend(lote)
        if len(lote) < 1000 or offset > 20000:
            break
        offset += 1000
    try:
        retirados = {f["envio_id"] for f in t("retiros_archivos").select("envio_id").eq("resultado", "OK")
                     .limit(50000).execute().data or []}
    except Exception:
        retirados = set()
    try:
        descargados = set()
        for f in (t("descargas_masivas").select("envio_ids").eq("anio", anio).eq("estado", "DESCARGADA")
                  .limit(5000).execute().data or []):
            descargados.update(f.get("envio_ids") or [])
    except Exception:
        descargados = set()
    por_semana: Dict[int, Dict] = {}
    for e in envios:
        if not tiene_archivo(e) or e.get("id") in retirados:
            continue
        s = por_semana.setdefault(int(e["semana"]), {"anio": anio, "semana": int(e["semana"]), "en_drive": 0,
                                                       "descargados": 0, "duplicados": 0})
        s["en_drive"] += 1
        s["descargados"] += int(e.get("id") in descargados)
        s["duplicados"] += int(es_duplicado(e) or es_reemplazado(e))
    out = sorted(por_semana.values(), key=lambda x: x["semana"])
    for s in out:
        s["lista"] = s["descargados"] >= s["en_drive"] - s["duplicados"]
    return out


def almacenamiento() -> Pendiente:
    from src.config import Config
    uso = _uso_drive()
    semanas = []
    try:
        semanas = semanas_para_liberar(Config.get_anio_actual(), Config.get_semana_actual())
    except Exception:
        pass
    listas = [s for s in semanas if s["lista"]]
    sin_bajar = [s for s in semanas if not s["lista"]]
    pct = uso.get("pct") if uso else None
    cifra = f"{pct:.0f} %" if pct is not None else "—"
    if pct is None:
        resumen = "Drive no informa un límite de espacio (unidad compartida o modo local)."
        tono = "info"
    elif pct >= 90:
        resumen, tono = f"Drive al {pct:.0f} %: conviene liberar espacio pronto.", "bad"
    elif pct >= UMBRAL_DRIVE_PCT:
        resumen, tono = f"Drive al {pct:.0f} %: planifique liberar espacio.", "warn"
    else:
        resumen, tono = f"Drive al {pct:.0f} %: espacio suficiente.", "ok"
    detalle = []

    def _rango(lista):
        a, b = lista[0]["semana"], lista[-1]["semana"]
        return f"semana {a}" if a == b else f"semanas {a} a {b}"

    if listas:
        n = sum(s["en_drive"] for s in listas)
        detalle.append(f"Sugerencia: {_rango(listas)} ({n} archivos) ya se descargaron; se pueden retirar de Drive "
                       "(van a la papelera, recuperables ~30 días).")
    if sin_bajar:
        n = sum(s["en_drive"] for s in sin_bajar)
        detalle.append(f"Antes de retirar {_rango(sin_bajar)} ({n} archivos), descárguelas: aún no tienen copia descargada.")
    if not semanas:
        detalle.append(f"No hay semanas con más de {SEMANAS_ANTIGUEDAD} semanas de antigüedad con archivos en Drive.")
    if tono == "ok" and listas:
        tono = "info"
    return Pendiente("almacenamiento", "Almacenamiento (Drive)", "Descarga y Limpieza", tono, cifra, resumen, detalle,
                     origen="regla", nivel="restringido", accion="Ir a Descarga y limpieza")


def duplicados() -> Pendiente:
    from src.config import Config
    from utils.duplicados import es_duplicado
    from src.repositorio import tiene_archivo
    anio, semana = Config.get_anio_actual(), Config.get_semana_actual()
    envios = _db().obtener_envios(semana=semana, anio=anio, limit=1000) or []
    dup = [e for e in envios if es_duplicado(e) and tiene_archivo(e)]
    redes = sorted({str(e.get("red")) for e in dup})
    if not dup:
        return Pendiente("duplicados", "Duplicados", "Control de Duplicados", "ok", "0",
                         f"Sin duplicados en la semana {semana}.", accion="Ir a Control de duplicados")
    return Pendiente("duplicados", "Duplicados", "Control de Duplicados", "warn", str(len(dup)),
                     f"{len(dup)} envío(s) duplicado(s) en la semana {semana} ocupan espacio en Drive.",
                     [f"Redes: {', '.join(redes[:6])}" + ("…" if len(redes) > 6 else ""),
                      "Revíselos y elimine los que repiten un envío ya recibido."], accion="Ir a Control de duplicados")


def cierre() -> Pendiente:
    from src.cierres import get_cierres
    c = get_cierres()
    detalle = []
    tono, cifra, resumen = "ok", "Al día", "La semana activa y su corte están en orden."
    if c.disponible():
        venc, pend = c.vencido_sin_cerrar(), c.pendiente()
        if venc and not pend:
            tono, cifra = "bad", "Vencido"
            resumen = f"El corte de la semana {venc['semana']} venció y no se cerró."
            detalle.append("Ciérrelo a mano en Configuración y valide la nueva semana.")
        elif pend:
            tono, cifra = "warn", "Por validar"
            resumen = f"La semana {pend.get('semana_propuesta')} quedó provisional: falta validarla."
            detalle.append("Confirme o corrija la semana y la fecha de corte.")
    try:
        v = _db().obtener_configuracion("programador_ultimo_latido")
        f = _parse(v) if v else None
        limite = int(os.getenv("PROGRAMADOR_LATIDO_MAX_MIN", "5") or 5)
        if not f:
            detalle.append("El proceso automático no ha dado señales (cierres y respaldos quedan manuales).")
            tono = "warn" if tono == "ok" else tono
        elif _ahora() - f > timedelta(minutes=limite):
            detalle.append(f"El proceso automático dejó de responder hace {int((_ahora() - f).total_seconds() // 60)} min.")
            tono = "warn" if tono == "ok" else tono
    except Exception:
        pass
    return Pendiente("cierre", "Cierre de semana", "Configuracion", tono, cifra, resumen, detalle, accion="Ir a Configuración")


def respaldos() -> Pendiente:
    from src.respaldos import get_respaldos
    r = get_respaldos()
    if not r.disponible():
        return Pendiente("respaldos", "Respaldos", "Respaldos", "mute", "—", "Falta la tabla de respaldos (sql/10).",
                         accion="Ir a Respaldos")
    ult = (r.listar(1) or [None])[0]
    if not ult:
        return Pendiente("respaldos", "Respaldos", "Respaldos", "warn", "Ninguno", "Todavía no hay respaldos.",
                         ["Haga uno con «Respaldar ahora»."], accion="Ir a Respaldos")
    f = _parse(ult.get("fecha_fin") or ult.get("fecha_creacion"))
    dias = (_ahora() - f).days if f else None
    if ult.get("estado") == "ERROR":
        return Pendiente("respaldos", "Respaldos", "Respaldos", "bad", "Falló", "El último respaldo terminó con error.",
                         [str(ult.get("detalle") or "")[:160]], accion="Ir a Respaldos")
    if dias is not None and dias > 8:
        return Pendiente("respaldos", "Respaldos", "Respaldos", "warn", f"{dias} días", "El último respaldo es antiguo.",
                         ["Haga uno nuevo con «Respaldar ahora»."], accion="Ir a Respaldos")
    return Pendiente("respaldos", "Respaldos", "Respaldos", "ok", "Al día",
                     f"Último respaldo hace {dias if dias is not None else '?'} día(s).", accion="Ir a Respaldos")


def solicitudes() -> Pendiente:
    from src.agentes.herramientas import solicitudes_abiertas
    pend = [s for s in solicitudes_abiertas() if s.get("estado") == "PENDIENTE"]
    return Pendiente("solicitudes", "Solicitudes de contraseña", "Solicitudes de Contraseña",
                     "warn" if pend else "ok", str(len(pend)),
                     f"{len(pend)} red(es) esperan respuesta." if pend else "Ninguna solicitud pendiente.",
                     [f"{s.get('red')} (desde {s.get('creada')})" for s in pend[:5]],
                     accion="Ir a Solicitudes", solo_super_admin=True)


def decisiones_del_agente() -> Pendiente:
    esc_ = _propuestas(["ESCALAR"])
    notas = _propuestas(["NOTA_MEMORIA"])
    total = len(esc_) + len(notas)
    detalle = [f"{p.get('red') or '—'}: {str((p.get('payload') or {}).get('motivo') or '')[:120]}" for p in esc_[:4]]
    if notas:
        detalle.append(f"{len(notas)} nota(s) de memoria sugeridas.")
    return Pendiente("agente", "Casos que el agente le pasa a usted", None, "warn" if esc_ else ("info" if notas else "ok"),
                     str(total), "El agente no sabe resolverlos solo: necesitan su criterio." if total
                     else "Nada escalado.", detalle, origen="regla + IA", accion="Ver en la Bandeja")


# ---------------------------------------------------------------- SIREA 3.5 (lo que trajo SIRE v7.5 – v7.6)

def permisos_pedidos() -> Pendiente:
    from src.agentes.herramientas import solicitudes_de_permiso_pendientes
    d = solicitudes_de_permiso_pendientes()
    if not d.get("disponible", True):
        return Pendiente("permisos", "Solicitudes de permiso", "Permisos de Operacion", "mute", "—",
                         "Falta la tabla de solicitudes (sql/17).", accion="Ir a Permisos", solo_super_admin=True)
    n = int(d.get("pendientes") or 0)
    return Pendiente("permisos", "Solicitudes de permiso", "Permisos de Operacion", "warn" if n else "ok", str(n),
                     f"{n} solicitud(es) esperan la respuesta del SUPER_ADMIN principal." if n else "Ninguna solicitud pendiente.",
                     [f"{k}: {v}" for k, v in (d.get("por_permiso") or {}).items()][:5]
                     + ([f"La más antigua es del {d['mas_antigua']}."] if d.get("mas_antigua") else []),
                     accion="Ir a Permisos", solo_super_admin=True)


def zip_bloqueados() -> Pendiente:
    from src.agentes.herramientas import zip_bloqueados_recientes
    d = zip_bloqueados_recientes(7)
    if not d.get("disponible", True):
        return Pendiente("seguridad", "ZIP bloqueados por seguridad", "Control de Actividad", "mute", "—",
                         "La auditoría no está disponible (sql/11).", accion="Ver en Control de actividad")
    n = int(d.get("total") or 0)
    detalle = [f"{r}: {c}" for r, c in list((d.get("por_red") or {}).items())[:4]]
    detalle += [f"Motivo «{m}»: {c}" for m, c in list((d.get("por_motivo") or {}).items())[:3]]
    if n:
        detalle.append("Si se repite en una red, llame a su responsable: puede tener un equipo infectado o un exportador mal configurado.")
    return Pendiente("seguridad", "ZIP bloqueados por seguridad", "Control de Actividad",
                     "warn" if n >= 3 else ("info" if n else "ok"), str(n),
                     f"{n} ZIP rechazado(s) en los últimos 7 días." if n else "Ningún ZIP peligroso en los últimos 7 días.",
                     detalle, accion="Ver en Control de actividad")


def cambios_configuracion() -> Pendiente:
    from src.agentes.herramientas import cambios_de_configuracion_recientes
    d = cambios_de_configuracion_recientes(7)
    if not d.get("disponible", True):
        return Pendiente("configuracion", "Cambios de configuración", "Control de Actividad", "mute", "—",
                         "La auditoría no está disponible (sql/11).", accion="Ver en Control de actividad")
    n, alertas = int(d.get("total") or 0), d.get("alertas") or {}
    serias = {k: v for k, v in alertas.items() if "excepcional" in k.lower() or "deshacer" in k.lower() or "envíos" in k.lower()}
    return Pendiente("configuracion", "Cambios de configuración", "Control de Actividad",
                     "warn" if serias else ("info" if n else "ok"), str(n),
                     (f"{n} cambio(s) en 7 días" + (f", {sum(serias.values())} con alerta." if serias else ".")) if n
                     else "Sin cambios de configuración en los últimos 7 días.",
                     [f"{k}: {v}" for k, v in list((d.get("por_tipo") or {}).items())[:4]]
                     + [f"⚠ {k}: {v}" for k, v in serias.items()], accion="Ver en Control de actividad",
                     solo_super_admin=True)


def salud_sistema() -> Pendiente:
    from src.agentes.herramientas import estado_salud_sistema
    d = estado_salud_sistema().get("ultima_revision") or {}
    if not d:
        return Pendiente("salud", "Salud del sistema", "Salud del Sistema", "info", "—",
                         "Aún no se revisó el sistema desde el panel.", ["Pulse «Revisar ahora» en Salud del sistema."],
                         accion="Ir a Salud del sistema", solo_super_admin=True)
    r = d.get("resultados") or {}
    f = _parse(d.get("cuando"))
    dias = (_ahora() - f).days if f else None
    fallas, avisos = int(r.get("FALLA") or 0), int(r.get("AVISO") or 0)
    tono = "bad" if fallas else ("info" if (dias or 0) > 14 or avisos else "ok")
    resumen = (f"{fallas} falla(s) en la última revisión." if fallas else
               f"Sin fallas · {avisos} aviso(s)." if avisos else "Todo en verde en la última revisión.")
    detalle = [f"Revisado hace {dias} día(s)." if dias is not None else ""]
    if (dias or 0) > 14:
        detalle.append("Conviene repetir la revisión: tiene más de dos semanas.")
    return Pendiente("salud", "Salud del sistema", "Salud del Sistema", tono, str(fallas) if fallas else "OK",
                     resumen, [x for x in detalle if x], accion="Ir a Salud del sistema", solo_super_admin=True)


SECCIONES: List[Callable[[], Pendiente]] = [redes_atrasadas, observaciones, decisiones_del_agente, almacenamiento,
                                            duplicados, cierre, respaldos, solicitudes,
                                            permisos_pedidos, zip_bloqueados, cambios_configuracion, salud_sistema]
_NOMBRES = {"redes_atrasadas": "Redes atrasadas", "observaciones": "Observaciones", "decisiones_del_agente": "Casos escalados",
            "almacenamiento": "Almacenamiento (Drive)", "duplicados": "Duplicados", "cierre": "Cierre de semana",
            "respaldos": "Respaldos", "solicitudes": "Solicitudes de contraseña",
            "permisos_pedidos": "Solicitudes de permiso", "zip_bloqueados": "ZIP bloqueados por seguridad",
            "cambios_configuracion": "Cambios de configuración", "salud_sistema": "Salud del sistema"}


def todos(rol: str = "ADMIN") -> List[Pendiente]:
    """Todas las secciones (las que fallan se informan sin detener las demás). Lo urgente primero."""
    out = []
    for fn in SECCIONES:
        try:
            p = fn()
        except Exception as e:  # noqa: BLE001
            p = Pendiente(fn.__name__, _NOMBRES.get(fn.__name__, fn.__name__), None, "mute", "—",
                          f"No se pudo revisar ({type(e).__name__}).")
        if p.solo_super_admin and (rol or "").upper() != "SUPER_ADMIN":
            continue
        out.append(p)
    orden = {"bad": 0, "warn": 1, "info": 2, "ok": 3, "mute": 4}
    return sorted(out, key=lambda p: orden.get(p.tono, 5))
