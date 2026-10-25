# src/email_auditoria.py
"""
Correos de la trazabilidad del repositorio: acuses de descarga masiva, solicitudes
y retiros de archivos, duplicados eliminados y cambios de permisos.

Quien actúa recibe su acuse; el SUPER_ADMIN principal recibe el mismo acuse
(con el Excel del registro cuando corresponde); y si AUDITORIA_COPIA_EMAIL está
definido, esa casilla institucional recibe copia oculta de todo.
Los textos que escribe una persona (motivos, notas) siempre se escapan.
"""

from typing import Dict, List, Optional, Tuple

from src import email_plantillas as P
from src.auditoria import LIMA
from src.config import Config
from src.solicitudes_password import fecha_lima
from src.validacion_correo import formato_valido, normalizar as normalizar_correo

_esc = P.esc


def _multilinea(texto: str) -> str:
    return _esc(texto or "").replace("\r\n", "\n").replace("\n", "<br>")


def _mb(n_bytes) -> str:
    n = float(n_bytes or 0)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.1f} MB"


def _persona(db, usuario: Optional[str]) -> Optional[Dict]:
    if not usuario:
        return None
    try:
        a = db.obtener_administrador(usuario)
    except Exception:
        a = None
    correo = normalizar_correo((a or {}).get("email"))
    if not a or not formato_valido(correo):
        return None
    return {"usuario": usuario, "nombre": a.get("nombre") or usuario, "email": correo}


def copia_institucional() -> Optional[str]:
    c = normalizar_correo(Config.AUDITORIA_COPIA_EMAIL)
    return c if formato_valido(c) else None


def destinos(db, actor_usuario: Optional[str], incluir_actor: bool = True) -> List[Dict]:
    """Quien actuó + el SUPER_ADMIN principal (sin repetir si es la misma persona)."""
    salida, vistos = [], set()
    nombres = ([actor_usuario] if incluir_actor else []) + [Config.SUPERADMIN_PRINCIPAL]
    for u in nombres:
        p = _persona(db, u)
        if p and p["email"] not in vistos:
            vistos.add(p["email"])
            p["es_actor"] = bool(actor_usuario) and str(u).lower() == str(actor_usuario).lower()
            salida.append(p)
    return salida


def _enviar(sender, p: Dict, asunto: str, html_: str, plano: str, adjuntos=None, copia: bool = False) -> Tuple[bool, str]:
    bcc = None
    c = copia_institucional()
    if copia and c and c != p["email"]:
        bcc = [c]
    try:
        return sender._enviar_correo(p["email"], asunto, html_, plano, adjuntos=adjuntos, bcc=bcc)
    except TypeError:    # remitentes de prueba sin bcc
        return sender._enviar_correo(p["email"], asunto, html_, plano, adjuntos=adjuntos)


def _enviar_a(sender, db, actor_usuario: str, asunto: str, construir, adjuntos=None) -> int:
    """`construir(persona, es_actor)` -> (html, plano). Devuelve cuántos correos salieron."""
    enviados, primero_principal = 0, True
    for p in destinos(db, actor_usuario):
        html_, plano = construir(p, p.get("es_actor", False))
        es_principal_dest = str(p["usuario"]).lower() == Config.SUPERADMIN_PRINCIPAL
        ok, _ = _enviar(sender, p, asunto, html_, plano, adjuntos, copia=es_principal_dest and primero_principal)
        if es_principal_dest:
            primero_principal = False
        enviados += 1 if ok else 0
    return enviados


def _alertas_html(alertas: List[str]) -> str:
    if not alertas:
        return ""
    return P.caja_aviso("bad", "Señales para revisar", P.lista([_esc(a) for a in alertas]))


def _selecc(redes, todas: bool) -> str:
    return "Todas las redes" if todas else ", ".join(redes or []) or "—"


# ---------------------------------------------------------------- descarga masiva

def enviar_acuse_descarga(sender, db, actor_usuario: str, info: Dict) -> int:
    """`info`: anio, semana, redes, todas, parte, total_partes, nombre_zip, n_envios, n_archivos, bytes, sha256, cuando, ip, usuario_nombre, alertas."""
    asunto = f"Acuse de descarga masiva – Semana {info['semana']} de {info['anio']} – SIREA"

    def construir(p, es_actor):
        intro = (f"Por medio del presente, se deja constancia de que <strong>{_esc(info.get('usuario_nombre') or actor_usuario)}</strong> "
                 f"descargó el ZIP masivo de la semana {info['semana']} del año {info['anio']}.")
        cuerpo = P.tabla_desde_pares([
            ("Responsable", f"{_esc(info.get('usuario_nombre') or actor_usuario)} ({_esc(actor_usuario)})"),
            ("Fecha y hora", f"{_esc(info.get('cuando'))} (hora de Lima)"),
            ("Semana y año", f"Semana {info['semana']} · {info['anio']}"),
            ("Redes", _esc(_selecc(info.get("redes"), info.get("todas")))),
            ("Archivo", f"{_esc(info['nombre_zip'])} · parte {info.get('parte', 1)} de {info.get('total_partes', 1)}"),
            ("Contenido", f"{info['n_archivos']} archivo(s) de {info['n_envios']} envío(s) · {_mb(info['bytes'])}"),
            ("Huella SHA-256", f"<span style=\"font-family:Consolas,monospace;font-size:12px\">{_esc(info.get('sha256') or '—')}</span>"),
            ("Equipo (IP)", _esc(info.get("ip") or "no disponible")),
        ])
        cuerpo += _alertas_html(info.get("alertas") or [])
        cuerpo += P.caja_aviso("info", "Para qué sirve este correo",
                               "Es el comprobante de la descarga. La huella permite comprobar más adelante que el archivo no fue modificado. "
                               "El registro completo está en el panel, sección «Control de actividad».")
        html_ = P.envolver("azul", "Acuse de descarga", "Descarga masiva registrada", P.saludo(_esc(p["nombre"]), intro), cuerpo)
        plano = (f"ACUSE DE DESCARGA MASIVA\n\nEstimado/a {p['nombre']}:\n\n{info.get('usuario_nombre') or actor_usuario} descargó "
                 f"{info['nombre_zip']} (semana {info['semana']} de {info['anio']}, {_selecc(info.get('redes'), info.get('todas'))}).\n"
                 f"Fecha: {info.get('cuando')}\nArchivos: {info['n_archivos']} ({_mb(info['bytes'])})\nSHA-256: {info.get('sha256')}\n")
        return html_, plano

    return _enviar_a(sender, db, actor_usuario, asunto, construir)


# ---------------------------------------------------------------- retiros

def _filas_solicitud(sol: Dict) -> List[tuple]:
    return [
        ("Solicitud", f"N.º {sol.get('id')}"),
        ("Semana y año", f"Semana {sol['semana']} · {sol['anio']}"),
        ("Redes", _esc(_selecc(sol.get("redes"), sol.get("todas_las_redes")))),
        ("Envíos", str(sol.get("n_envios", 0))),
        ("Motivo", f"<strong>{_esc(sol.get('motivo_categoria'))}</strong><br>{_multilinea(sol.get('motivo'))}"),
        ("Descarga previa", "Sí, descargados antes" if not sol.get("sin_descarga_previa") else "<strong>No: se retiran sin descarga previa</strong>"),
        ("Tipo de borrado", "Definitivo (no se puede recuperar)" if sol.get("definitivo") else "A la papelera de Drive (recuperable 30 días)"),
    ]


def enviar_aviso_solicitud_retiro(sender, db, sol: Dict, alertas: List[str]) -> int:
    """Al principal: hay una solicitud por aprobar. Al solicitante: acuse de que quedó registrada."""
    quien = sol.get("solicitado_nombre") or sol.get("solicitado_por")
    enviados = 0
    principal = _persona(db, Config.SUPERADMIN_PRINCIPAL)
    solicitante = _persona(db, sol.get("solicitado_por"))
    if principal:
        intro = (f"Por medio del presente, le comunicamos que <strong>{_esc(quien)}</strong> solicita retirar archivos del repositorio. "
                 "<strong>No se retirará nada hasta que usted lo apruebe.</strong>")
        cuerpo = P.tabla_desde_pares(_filas_solicitud(sol)) + _alertas_html(alertas)
        cuerpo += P.caja_aviso("warn", "Requiere su decisión", "Ingrese al panel, sección <strong>Descarga y limpieza</strong>, y apruebe o rechace la solicitud.")
        html_ = P.envolver("ambar", "Solicitud de retiro", "Retiro de archivos por aprobar", P.saludo(_esc(principal["nombre"]), intro), cuerpo)
        plano = f"SOLICITUD DE RETIRO N.º {sol.get('id')}\n\n{quien} solicita retirar archivos (semana {sol['semana']} de {sol['anio']}).\nMotivo: {sol.get('motivo')}\nApruebe o rechace en el panel: Descarga y limpieza."
        ok, _ = _enviar(sender, principal, f"Solicitud de retiro de archivos por aprobar – Semana {sol['semana']} – SIREA", html_, plano, copia=True)
        enviados += 1 if ok else 0
    if solicitante and (not principal or solicitante["email"] != principal["email"]):
        intro = "Por medio del presente, se deja constancia de que su solicitud de retiro quedó registrada y espera la aprobación del SUPER_ADMIN principal."
        cuerpo = P.tabla_desde_pares(_filas_solicitud(sol))
        html_ = P.envolver("ambar", "Solicitud registrada", "Su solicitud espera aprobación", P.saludo(_esc(solicitante["nombre"]), intro), cuerpo)
        plano = f"SOLICITUD DE RETIRO N.º {sol.get('id')} REGISTRADA\n\nEspera la aprobación del SUPER_ADMIN principal. No se retiró ningún archivo."
        ok, _ = _enviar(sender, solicitante, f"Solicitud de retiro N.º {sol.get('id')} registrada – SIREA", html_, plano)
        enviados += 1 if ok else 0
    return enviados


def enviar_acuse_retiro(sender, db, sol: Dict, resumen: Dict, adjuntos: List[Tuple[str, bytes, str]]) -> int:
    """
    Retiro ejecutado: acuse al solicitante y al principal con el Excel del registro.
    `resumen`: n_ok, n_error, cuando, ejecutado_por, ejecutado_nombre, alertas.
    """
    parcial = resumen.get("n_error", 0) > 0
    asunto = (f"Retiro de archivos {'parcial' if resumen.get('n_ok') else 'con error'}" if parcial else "Retiro de archivos completado")
    asunto += f" – Semana {sol['semana']} de {sol['anio']} – SIREA"
    actor = sol.get("solicitado_por")

    def construir(p, es_actor):
        intro = (f"Por medio del presente, se deja constancia de que se retiraron archivos del repositorio. "
                 f"Solicitó: <strong>{_esc(sol.get('solicitado_nombre') or actor)}</strong>. "
                 f"Aprobó/ejecutó: <strong>{_esc(resumen.get('ejecutado_nombre') or resumen.get('ejecutado_por'))}</strong>.")
        filas = _filas_solicitud(sol) + [
            ("Fecha y hora", f"{_esc(resumen.get('cuando'))} (hora de Lima)"),
            ("Resultado", f"{resumen.get('n_ok', 0)} archivo(s) retirado(s)" + (f" · <strong>{resumen['n_error']} con error</strong>" if parcial else "")),
        ]
        cuerpo = P.tabla_desde_pares(filas) + _alertas_html(resumen.get("alertas") or [])
        if parcial:
            cuerpo += P.caja_aviso("warn", "Algunos archivos no se pudieron retirar",
                                   "Siguen en Drive. El Excel adjunto indica el motivo de cada uno; se puede reintentar desde el panel.")
        cuerpo += P.caja_aviso("info", "Excel adjunto", "El registro archivo por archivo (código, red, centros, resultado) va en el Excel adjunto. "
                               "Los registros de recepción (quién envió y cuándo) se conservan en la base de datos.")
        html_ = P.envolver("rojo", "Retiro del repositorio", "Se retiraron archivos del repositorio", P.saludo(_esc(p["nombre"]), intro), cuerpo)
        plano = (f"RETIRO DE ARCHIVOS – SOLICITUD N.º {sol.get('id')}\n\nSemana {sol['semana']} de {sol['anio']}\n"
                 f"Retirados: {resumen.get('n_ok', 0)} · con error: {resumen.get('n_error', 0)}\nMotivo: {sol.get('motivo')}\n"
                 f"Solicitó: {sol.get('solicitado_por')} · Ejecutó: {resumen.get('ejecutado_por')}\nFecha: {resumen.get('cuando')}\n")
        return html_, plano

    return _enviar_a(sender, db, actor, asunto, construir, adjuntos)


def enviar_retiro_rechazado(sender, db, sol: Dict, por_nombre: str, nota: str) -> int:
    solicitante = _persona(db, sol.get("solicitado_por"))
    if not solicitante:
        return 0
    intro = f"Por medio del presente, le informamos que su solicitud de retiro N.º {sol.get('id')} <strong>no fue aprobada</strong>. No se retiró ningún archivo."
    cuerpo = P.tabla_desde_pares(_filas_solicitud(sol) + [("Respondió", _esc(por_nombre))])
    if (nota or "").strip():
        cuerpo += P.caja_aviso("info", "Mensaje", _multilinea(nota))
    html_ = P.envolver("ambar", "Solicitud de retiro", "Solicitud no aprobada", P.saludo(_esc(solicitante["nombre"]), intro), cuerpo)
    plano = f"SOLICITUD DE RETIRO N.º {sol.get('id')} NO APROBADA\n\n{nota or ''}"
    ok, _ = _enviar(sender, solicitante, f"Solicitud de retiro N.º {sol.get('id')} no aprobada – SIREA", html_, plano, copia=True)
    return 1 if ok else 0


# ---------------------------------------------------------------- duplicados

def enviar_acuse_duplicados(sender, db, actor_usuario: str, actor_nombre: str, info: Dict) -> int:
    """info: items [(codigo, red, resultado)], n_ok, n_error, borro_drive, cuando, alertas."""
    asunto = f"Duplicados eliminados ({info['n_ok']}) – SIREA"

    def construir(p, es_actor):
        intro = (f"Por medio del presente, se deja constancia de que <strong>{_esc(actor_nombre)}</strong> eliminó envíos duplicados "
                 "de la carpeta de duplicados.")
        filas = [("Responsable", f"{_esc(actor_nombre)} ({_esc(actor_usuario)})"), ("Fecha y hora", f"{_esc(info.get('cuando'))} (hora de Lima)"),
                 ("Eliminados", str(info["n_ok"])), ("Con error", str(info["n_error"])),
                 ("Archivos de Drive", "También se retiraron" if info.get("borro_drive") else "Se conservaron")]
        cuerpo = P.tabla_desde_pares(filas)
        items = [f"{_esc(c)} · {_esc(r)} · {_esc(res)}" for c, r, res in info.get("items", [])[:40]]
        if items:
            cuerpo += P.bloque_titulo("Detalle") + P.lista(items)
        cuerpo += _alertas_html(info.get("alertas") or [])
        html_ = P.envolver("rojo", "Duplicados", "Se eliminaron duplicados", P.saludo(_esc(p["nombre"]), intro), cuerpo)
        plano = f"DUPLICADOS ELIMINADOS\n\n{actor_nombre} eliminó {info['n_ok']} duplicado(s). Fecha: {info.get('cuando')}"
        return html_, plano

    return _enviar_a(sender, db, actor_usuario, asunto, construir)


# ---------------------------------------------------------------- permisos

def enviar_aviso_permiso(sender, adm: Dict, actor: Dict, tipo: str, permiso_nombre: str, redes, vence_en, nota) -> Tuple[bool, str]:
    correo = normalizar_correo(adm.get("email"))
    if not formato_valido(correo):
        return False, "sin correo"
    otorgado = tipo == "otorgado"
    intro = (f"Por medio del presente, le comunicamos que el SUPER_ADMIN principal le <strong>{'otorgó' if otorgado else 'retiró'}</strong> "
             f"el permiso <strong>{_esc(permiso_nombre)}</strong>.")
    filas = [("Permiso", _esc(permiso_nombre)), ("Estado", "Vigente" if otorgado else "Revocado")]
    if otorgado:
        filas += [("Redes", _esc(", ".join(redes)) if redes else "Todas"),
                  ("Vence", _esc(vence_en.astimezone(LIMA).strftime("%d/%m/%Y %H:%M")) if vence_en else "Sin vencimiento")]
    cuerpo = P.tabla_desde_pares(filas)
    if (nota or "").strip():
        cuerpo += P.caja_aviso("info", "Nota", _multilinea(nota))
    cuerpo += P.caja_aviso("warn", "Todo queda registrado",
                           "Cada descarga, retiro o eliminación que realice queda anotado con su usuario, fecha, hora y detalle, "
                           "y se avisa por correo al SUPER_ADMIN principal.") if otorgado else ""
    html_ = P.envolver("azul" if otorgado else "ambar", "Permisos", "Permiso otorgado" if otorgado else "Permiso retirado",
                       P.saludo(_esc(adm.get("nombre") or adm.get("usuario")), intro), cuerpo)
    plano = f"PERMISO {'OTORGADO' if otorgado else 'RETIRADO'}\n\n{permiso_nombre}\n"
    bcc = [copia_institucional()] if copia_institucional() else None
    try:
        return sender._enviar_correo(correo, f"Permiso {'otorgado' if otorgado else 'retirado'}: {permiso_nombre} – SIREA", html_, plano, bcc=bcc)
    except TypeError:
        return sender._enviar_correo(correo, f"Permiso {'otorgado' if otorgado else 'retirado'}: {permiso_nombre} – SIREA", html_, plano)
