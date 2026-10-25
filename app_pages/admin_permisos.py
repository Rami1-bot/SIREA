# app_pages/admin_permisos.py
"""
«Permisos de operación»: solo el SUPER_ADMIN principal (oiis.winepi).

Aquí se decide quién puede descargar en masa, retirar archivos del repositorio,
hacer respaldos manuales o ver el control de actividad. Cada permiso se da por
persona (ADMIN o SUPER_ADMIN), con alcance opcional por redes y vencimiento.
"""

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from src.auditoria import LIMA
from src.auth import get_auth_manager
from src.db_manager import get_db_manager
from src.permisos import PERMISOS, get_permisos
from src.solicitudes_password import fecha_lima
from utils.tema import aviso, chip, kpi, mostrar
from utils.tema_admin import esc, panel_cab, tabla_df
from app_pages.admin_helpers import actor_actual


def _es_principal(token) -> bool:
    return bool(get_auth_manager().es_superadmin_principal(token))


def _redes():
    try:
        from src.data_loader import obtener_redes
        return list(obtener_redes())
    except Exception:
        return []


def _estado_permiso(f) -> str:
    if not f.get("activo"):
        return chip("Revocado", "mute")
    v = f.get("vence_en")
    if v:
        try:
            if datetime.fromisoformat(str(v).replace("Z", "+00:00")) <= datetime.now().astimezone():
                return chip("Vencido", "warn", "reloj")
        except Exception:
            pass
    return chip("Vigente", "ok", "check")


def mostrar_permisos_operacion():
    """Pantalla «Permisos de operación» (solo el principal)."""
    actor = actor_actual()
    token = st.session_state.get("admin_token")
    if not _es_principal(token):
        mostrar(aviso("warn", "Acceso restringido", "Solo el SUPER_ADMIN principal puede asignar permisos."))
        return
    permisos = get_permisos()
    if not permisos.disponible():
        mostrar(aviso("info", "Falta crear las tablas de auditoría y permisos",
                      "Ejecute <strong>sql/11_auditoria_permisos_repositorio.sql</strong> en el SQL Editor de Supabase."))
        return
    resultado = st.session_state.pop("perm_resultado", None)
    if resultado:
        mostrar(aviso(resultado[0], resultado[1], resultado[2] if len(resultado) > 2 else ""))

    db = get_db_manager()
    cuentas = [a for a in (db.obtener_administradores(solo_activos=True) or [])
               if str(a.get("usuario", "")).lower() != actor.get("usuario", "").lower()]
    filas = permisos.listar()
    vigentes = [f for f in filas if f.get("activo") and "Vigente" in _estado_permiso(f)]
    k1, k2, k3 = st.columns(3)
    with k1:
        mostrar(kpi("Permisos vigentes", len(vigentes), "Asignados a otras personas", None, "llave"))
    with k2:
        mostrar(kpi("Personas con permisos", len({f["usuario"] for f in vigentes}), "ADMIN y SUPER_ADMIN", None, "usuario"))
    with k3:
        mostrar(kpi("Con vencimiento", sum(1 for f in vigentes if f.get("vence_en")), "Se apagan solos", None, "reloj"))

    mostrar(aviso("info", "Cómo funciona",
                  "Nadie, salvo usted, tiene estos permisos por defecto: ni siquiera otro SUPER_ADMIN. "
                  "Cada asignación y cada uso quedan en el «Control de actividad» y se avisa por correo."))

    with st.container(key="panel_perm_dar"):
        panel_cab("Asignar permisos", "Elija a la persona, qué puede hacer y hasta cuándo")
        if not cuentas:
            mostrar('<div class="sire-vacio">No hay otras cuentas activas.</div>')
        else:
            etiquetas = {f"{a.get('nombre') or a['usuario']} · {a['usuario']} · {a.get('rol')}": a["usuario"] for a in cuentas}
            c1, c2 = st.columns([1.2, 1.8])
            with c1:
                quien = st.selectbox("Persona", list(etiquetas), key="perm_quien")
            with c2:
                cuales = st.multiselect("Permisos", list(PERMISOS), format_func=lambda p: PERMISOS[p][0], key="perm_cuales")
            for p in cuales:
                st.caption(f"**{PERMISOS[p][0]}**: {PERMISOS[p][1]}")
            c3, c4 = st.columns([1.8, 1.2])
            with c3:
                redes_ok = st.multiselect("Redes a las que aplica (vacío = todas)", _redes(), key="perm_redes",
                                          help="Limita la descarga y el retiro a esas redes. No afecta a «Ver auditoría» ni a «Respaldo manual».")
            with c4:
                vence = st.radio("Vigencia", ["Sin vencimiento", "Hasta una fecha"], key="perm_vig")
            fecha = None
            if vence == "Hasta una fecha":
                fecha = st.date_input("Vence el (hasta las 23:59, hora de Lima)", value=(datetime.now(LIMA) + timedelta(days=7)).date(),
                                      min_value=datetime.now(LIMA).date(), key="perm_fecha")
            nota = st.text_input("Nota (por qué se asigna)", key="perm_nota", max_chars=300)
            conf = st.checkbox("Confirmo que esta persona debe tener estos permisos", key="perm_conf")
            if st.button("Asignar permisos", type="primary", icon=":material/key:", key="perm_btn"):
                if not cuales:
                    st.info("Elija al menos un permiso.")
                elif not conf:
                    st.info("Marque la casilla de confirmación.")
                else:
                    vence_en = datetime.combine(fecha, time(23, 59, 59)) if fecha else None
                    errores, hechos = [], 0
                    for p in cuales:
                        ok, msg = permisos.otorgar(token, etiquetas[quien], p, redes_ok if p in ("DESCARGA_MASIVA", "RETIRO_REPOSITORIO") else None,
                                                   vence_en, nota)
                        if ok:
                            hechos += 1
                        else:
                            errores.append(f"{PERMISOS[p][0]}: {msg}")
                    st.session_state["perm_resultado"] = (
                        ("warn" if errores else "ok"),
                        f"Se asignaron {hechos} permiso(s)" + (f"; {len(errores)} con problema" if errores else ""),
                        esc(" · ".join(errores)) if errores else "Se avisó a la persona por correo.")
                    for k in ("perm_cuales", "perm_conf", "perm_nota"):
                        st.session_state.pop(k, None)
                    st.rerun()

    with st.container(key="panel_perm_lista"):
        panel_cab("Permisos asignados", "Vigentes, vencidos y revocados (historial completo)")
        if not filas:
            mostrar('<div class="sire-vacio">Todavía no se asignó ningún permiso.</div>')
        else:
            df = pd.DataFrame({
                "Persona": [f["usuario"] for f in filas],
                "Permiso": [PERMISOS.get(f["permiso"], (f["permiso"],))[0] for f in filas],
                "Redes": [", ".join(f.get("redes") or []) or "Todas" for f in filas],
                "Vence": [fecha_lima(f.get("vence_en")) if f.get("vence_en") else "Sin vencimiento" for f in filas],
                "Estado": [_estado_permiso(f) for f in filas],
                "Asignado": [f"{f.get('otorgado_por')} · {fecha_lima(f.get('fecha_creacion'))}" for f in filas],
                "Revocado": [(f"{f.get('revocado_por')} · {fecha_lima(f.get('fecha_revocacion'))}" if f.get("revocado_por") else "—") for f in filas]})
            mostrar(tabla_df(df, crudas=("Estado",), alto=420))

    activos = [f for f in filas if f.get("activo")]
    if activos:
        with st.container(key="peligro_perm_revocar"):
            mostrar(aviso("bad", "Revocar un permiso", "Deja de valer al instante y se avisa a la persona."))
            op = {f"{f['usuario']} · {PERMISOS.get(f['permiso'], (f['permiso'],))[0]} (N.º {f['id']})": f["id"] for f in activos}
            elegido = st.selectbox("Permiso a revocar", list(op), key="perm_rev_sel")
            motivo = st.text_input("Motivo", key="perm_rev_motivo", max_chars=300)
            if st.button("Revocar", type="primary", icon=":material/block:", key="perm_rev_btn"):
                ok, msg = permisos.revocar(token, op[elegido], motivo)
                st.session_state["perm_resultado"] = ("ok" if ok else "bad", msg)
                st.rerun()
