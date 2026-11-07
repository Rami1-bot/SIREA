# app_pages/admin_salud.py
"""
Salud del sistema (SIREA 3.5) · solo SUPER_ADMIN.

Ejecuta desde el panel las mismas revisiones de `verificar_despliegue.py`
(configuración, entorno, credencial de Google, Supabase y RLS, Drive, correo e IA)
sin abrir una consola. Es de solo lectura, salvo dos pruebas que se eligen a mano:
escribir y quitar un archivo de prueba en las carpetas de Drive y consultar a los
proveedores de IA (consume cuota). Nunca muestra claves.
"""

import json
import threading
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.config import Config
from src.db_manager import get_db_manager
from app_pages.admin_helpers import actor_actual
from utils.tema import mostrar, aviso, chip, kpi
from utils.tema_admin import esc, panel_cab, descargas

CLAVE_ULTIMA = "salud_ultima_revision"
_CANDADO = threading.Lock()          # verificar_despliegue guarda sus resultados en variables del módulo
_NIVEL = {"OK": ("Correcto", "ok", "check"), "AVISO": ("Aviso", "warn", "alerta"),
          "FALLA": ("Falla", "bad", "alerta"), "INFO": ("Dato", "info", None)}


def _fecha_lima(iso: str) -> str:
    try:
        from src.solicitudes_password import fecha_lima
        return fecha_lima(iso)
    except Exception:
        return str(iso or "—")[:16]


def _resumen_guardado():
    try:
        v = get_db_manager().obtener_configuracion(CLAVE_ULTIMA)
        return json.loads(v) if v else None
    except Exception:
        return None


def _latido():
    try:
        from app_pages.admin_cierres import _estado_latido
        return _estado_latido()
    except Exception:
        return "warn", "Sin dato del proceso programado", ""


def _ultimo_respaldo():
    try:
        from src.respaldos import get_respaldos
        filas = get_respaldos().listar(limite=1)
        return filas[0] if filas else None
    except Exception:
        return None


def _tarjetas():
    tono_l, tit_l, _ = _latido()
    resp = _ultimo_respaldo()
    from src import secretos
    est = secretos.estado(Config.BASE_DIR)
    fuente = "secrets.toml" if est["secrets_toml"] else (".env" if est["env"] else "Sistema")
    ultima = st.session_state.get("salud_resultado") or {}
    guardada = _resumen_guardado()
    r = (ultima.get("resultados") if ultima else None) or (guardada or {}).get("resultados")
    cuando = (ultima.get("cuando") if ultima else None) or (guardada or {}).get("cuando")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mostrar(kpi("Proceso programado", {"ok": "Activo", "bad": "Detenido"}.get(tono_l, "Sin señal"),
                    esc(tit_l), {"ok": "ok", "bad": "bad"}.get(tono_l, "warn"), "reloj"))
    with c2:
        if resp:
            ok = str(resp.get("estado") or "").upper() == "COMPLETADO"
            mostrar(kpi("Último respaldo", "Correcto" if ok else esc(str(resp.get("estado") or "—").title()),
                        _fecha_lima(resp.get("fecha_creacion")), "ok" if ok else "warn", "check"))
        else:
            mostrar(kpi("Último respaldo", "—", "Aún no hay respaldos", "warn", "alerta"))
    with c3:
        mostrar(kpi("Secretos", fuente, "Fuente principal de la configuración",
                    "ok" if fuente != ".env" else "warn", "candado"))
    with c4:
        if r:
            tono = "bad" if r.get("FALLA") else ("warn" if r.get("AVISO") else "ok")
            mostrar(kpi("Última revisión", f"{r.get('FALLA', 0)} falla(s)",
                        f"{r.get('OK', 0)} correctas · {r.get('AVISO', 0)} avisos · {_fecha_lima(cuando)}", tono, "escudo"))
        else:
            mostrar(kpi("Última revisión", "—", "Pulse «Revisar ahora»", None, "escudo"))


def _ejecutar(con_red: bool, drive: bool, ia: bool, correo: str):
    import verificar_despliegue as vd
    with _CANDADO:
        res = vd.ejecutar(con_red=con_red, prueba_correo=correo.strip(), drive=drive, ia=ia, imprimir=False)
    res["cuando"] = datetime.now(timezone.utc).isoformat()
    res["alcance"] = {"con_red": con_red, "drive": drive, "ia": ia, "correo": bool(correo.strip())}
    st.session_state["salud_resultado"] = res
    actor = actor_actual()
    r = res["resultados"]
    db = get_db_manager()
    try:
        db.guardar_configuracion(CLAVE_ULTIMA, json.dumps(
            {"resultados": r, "cuando": res["cuando"], "por": actor.get("usuario")}, ensure_ascii=False))
    except Exception:
        pass
    try:
        db.registrar_log(usuario=actor.get("usuario", "?"), accion="REVISION_SALUD",
                         detalle=f"{r.get('OK', 0)} OK · {r.get('AVISO', 0)} avisos · {r.get('FALLA', 0)} fallas"
                                 + ("" if con_red else " (solo configuración local)"))
    except Exception:
        pass


def _fila(item) -> str:
    texto, tono, ico = _NIVEL.get(item["nivel"], _NIVEL["INFO"])
    det = f'<div class="sirea-salud-det">{esc(item["detalle"])}</div>' if item.get("detalle") else ""
    return (f'<div class="sirea-salud-fila sirea-salud-{tono}"><div class="sirea-salud-chip">{chip(texto, tono, ico)}</div>'
            f'<div><div class="sirea-salud-tit">{esc(item["titulo"])}</div>{det}</div></div>')


def _resultados(res):
    reg = res.get("registro") or []
    if not reg:
        return
    r = res["resultados"]
    if r.get("FALLA"):
        mostrar(aviso("bad", f"{r['FALLA']} falla(s) por corregir",
                      "Corríjalas antes de abrir el sistema al personal. Cada fila dice qué hacer."))
    elif r.get("AVISO"):
        mostrar(aviso("warn", "Sin fallas", f"Revise los {r['AVISO']} aviso(s) y decida si aplican."))
    else:
        mostrar(aviso("ok", "Todo en verde", "Configuración, base de datos, Drive y correo responden como se espera."))

    solo_problemas = st.toggle("Ver solo avisos y fallas", value=bool(r.get("FALLA") or r.get("AVISO")), key="salud_solo")
    secciones = []
    for it in reg:
        if it["seccion"] not in secciones:
            secciones.append(it["seccion"])
    for sec in secciones:
        items = [i for i in reg if i["seccion"] == sec]
        if solo_problemas:
            items = [i for i in items if i["nivel"] in ("AVISO", "FALLA")]
        if not items:
            continue
        n_f = sum(1 for i in items if i["nivel"] == "FALLA")
        n_a = sum(1 for i in items if i["nivel"] == "AVISO")
        etiqueta = sec.split(". ", 1)[-1] if ". " in sec else sec
        with st.container(key=f"panel_salud_{secciones.index(sec)}"):
            panel_cab(etiqueta, (f"{n_f} falla(s) · " if n_f else "") + (f"{n_a} aviso(s)" if n_a else
                                                                         ("Sin problemas" if not n_f else "")))
            mostrar('<div class="sirea-salud">' + "".join(_fila(i) for i in items) + "</div>")

    df = pd.DataFrame([{"Sección": i["seccion"], "Resultado": _NIVEL.get(i["nivel"], ("", ""))[0],
                        "Revisión": i["titulo"], "Detalle": i["detalle"]} for i in reg])
    descargas(df, f"salud_sirea_{datetime.now().strftime('%Y%m%d_%H%M')}", "Salud del sistema", key="salud_dl",
              titulo="Salud del sistema")


def mostrar_salud():
    """Pantalla «Salud del sistema»."""
    from app_pages.admin_helpers import requerir_admin
    requerir_admin(permiso_super_admin=True)
    _tarjetas()

    with st.container(key="panel_salud_revisar"):
        panel_cab("Revisar el sistema", "Las mismas comprobaciones de verificar_despliegue.py, sin abrir una consola. "
                                        "No muestra claves ni cambia datos.")
        c1, c2 = st.columns([1.3, 1])
        with c1:
            drive = st.checkbox("Probar escritura en las carpetas de Drive", value=False, key="salud_drive",
                                help="Sube un archivo de prueba a cada carpeta y lo quita enseguida.")
            ia = st.checkbox("Probar los proveedores de IA", value=False, key="salud_ia",
                             help="Hace una pregunta mínima a Gemini y Groq (consume una pequeña parte de la cuota).")
        with c2:
            correo = st.text_input("Enviar un correo de prueba a (opcional)", key="salud_correo",
                                   placeholder="nombre@essalud.gob.pe")
        b1, b2, _ = st.columns([1.2, 1.4, 2])
        with b1:
            completa = st.button("Revisar ahora", type="primary", icon=":material/health_and_safety:",
                                 key="salud_btn", use_container_width=True)
        with b2:
            rapida = st.button("Solo configuración local", icon=":material/bolt:", key="salud_btn_rapida",
                               use_container_width=True, help="Sin conectarse a Supabase, Drive ni al correo.")
        if completa or rapida:
            with st.spinner("Revisando el sistema…"):
                _ejecutar(con_red=bool(completa), drive=bool(completa and drive), ia=bool(completa and ia),
                          correo=correo if completa else "")
            st.rerun()

    res = st.session_state.get("salud_resultado")
    if res:
        alc = res.get("alcance") or {}
        st.caption(f"Revisión del {_fecha_lima(res.get('cuando'))} · "
                   + ("completa" if alc.get("con_red") else "solo configuración local")
                   + (" · con prueba de Drive" if alc.get("drive") else "") + (" · con IA" if alc.get("ia") else ""))
        _resultados(res)
    else:
        mostrar('<div class="sire-vacio">Pulse «Revisar ahora» para ver el estado de cada componente.</div>')
