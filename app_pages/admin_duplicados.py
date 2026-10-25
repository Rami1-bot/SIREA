# pages/admin_duplicados.py
"""
Control de Duplicados.

Hay dos casos:
  1. Envíos que las redes repitieron a propósito (el sistema los avisó y ellas
     confirmaron): su archivo está en la carpeta de duplicados de Drive y el
     registro quedó marcado como «ENVÍO DUPLICADO». Aquí se revisan y, si no
     hacen falta, se eliminan junto con su archivo.
  2. Centros con más de un envío normal en la misma semana (registros
     anteriores a esta función): se conserva el más reciente.
"""

import pandas as pd
import streamlit as st

from src.config import Config
from src.db_manager import get_db_manager
from utils.duplicados import es_duplicado, solo_originales
from utils.helpers import sanitizar_html
from utils.tema import kpi, mostrar, aviso, chip
from utils.tema_admin import esc, tabla_df, panel_cab
from app_pages.admin_helpers import (
    actor_actual,
    formatear_centro,
    formatear_fecha_columna,
    obtener_centros_excluidos,
    requerir_admin,
)
from src.repositorio import get_repositorio


def _eliminar_archivo_drive(drive_file_id):
    """
    Quita el archivo del duplicado de Drive (o del almacenamiento local).
    Devuelve (ok, detalle) con el resultado REAL de la operación.
    """
    valor = str(drive_file_id or "").strip()
    if not valor or valor == "LOCAL":
        return False, "El registro no tiene un archivo asociado."
    try:
        from src.drive_manager import get_drive_manager
        gestor = get_drive_manager()
        if hasattr(gestor, "eliminar_archivo_detallado"):
            return gestor.eliminar_archivo_detallado(valor)
        return bool(gestor.eliminar_archivo(valor)), ""
    except Exception as e:
        print(f"No se pudo eliminar el archivo de Drive: {e}")
        return False, f"Error inesperado: {e}"


def _centros_texto(envio) -> str:
    centros = envio.get('centros', []) or []
    if isinstance(centros, list):
        return ", ".join(formatear_centro(c) for c in centros)
    return str(centros)


def _seccion_duplicados_marcados(db_manager, envios_semana, semana):
    """Envíos registrados como duplicados (archivo en la carpeta de duplicados)."""
    marcados = [e for e in envios_semana if es_duplicado(e)]
    if not marcados:
        mostrar(aviso(
            "ok", "No hay envíos duplicados pendientes de revisión",
            f"Ninguna red repitió un centro en la semana {semana}."))
        return

    c1, c2 = st.columns(2)
    with c1:
        mostrar(kpi("Duplicados por revisar", len(marcados), f"Semana {semana}", "dup", "copia"))
    with c2:
        redes = len({e.get('red') for e in marcados})
        mostrar(kpi("Redes involucradas", redes, "Con al menos un duplicado"))

    carpeta = "la carpeta de duplicados de Drive" if Config.GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID \
        else "la subcarpeta DUPLICADOS de la carpeta principal de Drive"
    with st.container(key="panel_dup_marcados"):
        panel_cab("Envíos duplicados recibidos", f"Sus archivos están en {carpeta}; no reemplazan al envío original")
        vista = pd.DataFrame({
            'Red': [sanitizar_html(str(e.get('red', ''))) for e in marcados],
            'Centros': [sanitizar_html(_centros_texto(e)) for e in marcados],
            'Responsable': [sanitizar_html(f"{e.get('nombre_usuario', '')} {e.get('apellido_usuario', '')}".strip()) for e in marcados],
            'Código': [sanitizar_html(str(e.get('codigo_seguimiento', ''))) for e in marcados],
            'Fecha de envío': [formatear_fecha_columna(e.get('fecha_envio', '')) for e in marcados],
            'Estado': [chip("Duplicado", "dup", "copia") for _ in marcados],
        })
        mostrar(tabla_df(vista, crudas=('Estado',)))

    actor = actor_actual()
    rep = get_repositorio()
    permitido, motivo_bloqueo = rep.puede_gestionar_duplicados(actor)
    if not permitido:
        mostrar(aviso("warn", "No puede eliminar duplicados", esc(motivo_bloqueo)))
        return
    with st.container(key="peligro_dup_marcados"):
        mostrar(aviso(
            "bad", "Eliminar duplicados recibidos",
            "Se elimina el registro del duplicado y, si lo marca, también su archivo en Drive. "
            "El envío original no se toca. Esta acción no se puede deshacer. Queda registrado quién lo hizo y se avisa a oiis.winepi."))
        opciones = {f"{e.get('codigo_seguimiento', e.get('id'))} · {e.get('red', '')} · {_centros_texto(e)}": e for e in marcados}
        elegidos = st.multiselect("Duplicados a eliminar", list(opciones), key="dup_marcados_elegidos",
                                  placeholder="Seleccione uno o más duplicados")
        borrar_drive = st.checkbox("Eliminar también el archivo en Drive", value=True, key="dup_marcados_drive")
        confirmar = st.checkbox("Confirmo que deseo eliminar los duplicados seleccionados", key="dup_marcados_confirma")
        if st.button("Eliminar duplicados seleccionados", type="primary", icon=":material/delete:", key="dup_marcados_btn"):
            if not elegidos:
                st.info("Seleccione al menos un duplicado.")
            elif not confirmar:
                st.info("Marque la casilla de confirmación para eliminar.")
            else:
                eliminados = archivos = 0
                fallos = []   # (código, motivo): el registro se CONSERVA para poder reintentar
                detalle_aud = []   # (código, red, resultado) para la auditoría y el acuse
                for etiqueta in elegidos:
                    envio = opciones[etiqueta]
                    codigo = envio.get('codigo_seguimiento', envio.get('id'))
                    if borrar_drive:
                        ok_arch, motivo = _eliminar_archivo_drive(envio.get('drive_file_id'))
                        if ok_arch:
                            archivos += 1
                        else:
                            fallos.append((codigo, motivo))
                            detalle_aud.append((str(codigo), str(envio.get('red')), f"no eliminado: {motivo}"))
                            continue
                    if db_manager.eliminar_envio(envio.get('id')):
                        eliminados += 1
                        detalle_aud.append((str(codigo), str(envio.get('red')), "eliminado (registro y archivo)" if borrar_drive else "eliminado (registro)"))
                    else:
                        fallos.append((codigo, "No se pudo borrar el registro de la base de datos."))
                        detalle_aud.append((str(codigo), str(envio.get('red')), "no eliminado: error de base de datos"))
                rep.registrar_duplicados_eliminados(actor, detalle_aud, eliminados, len(fallos), borrar_drive)
                if fallos:
                    lista = "".join(f"<li><strong>{sanitizar_html(str(c))}</strong>: {sanitizar_html(str(m))}</li>"
                                    for c, m in fallos)
                    st.session_state["dup_resultado"] = (
                        "warn" if eliminados else "bad",
                        f"Se eliminaron {eliminados} duplicado(s); {len(fallos)} no se pudieron eliminar",
                        f"<ul style='margin:6px 0 0 18px'>{lista}</ul>"
                        "Esos registros se conservaron para que pueda reintentar.")
                else:
                    msg = f"Se eliminaron {eliminados} duplicado(s)"
                    msg += f" y {archivos} archivo(s) de Drive." if borrar_drive else " (los archivos de Drive se conservaron)."
                    st.toast(msg, icon=":material/check_circle:")
                st.rerun()


def _seccion_repetidos_normales(db_manager, envios_semana, semana_activa):
    """Centros con más de un envío normal en la semana (conserva el más reciente)."""
    centros_excluidos = obtener_centros_excluidos()
    datos = []
    for envio in solo_originales(envios_semana):
        red = envio.get('red', '')
        centros = envio.get('centros', [])
        if isinstance(centros, list):
            for centro in centros:
                centro_str = formatear_centro(centro)
                if red in centros_excluidos and centro_str in centros_excluidos[red]:
                    continue
                datos.append({
                    'id': envio.get('id'),
                    'red': sanitizar_html(str(red)),
                    'centro': sanitizar_html(str(centro_str)),
                    'nombre_usuario': sanitizar_html(str(envio.get('nombre_usuario', ''))),
                    'apellido_usuario': sanitizar_html(str(envio.get('apellido_usuario', ''))),
                    'fecha_envio': envio.get('fecha_envio', '')
                })
    if not datos:
        return

    df = pd.DataFrame(datos)
    duplicados = df[df.duplicated(subset=['red', 'centro'], keep=False)]
    if duplicados.empty:
        return

    resumen = duplicados.groupby(['red', 'centro']).size().reset_index(name='veces_enviado')
    resumen = resumen[resumen['veces_enviado'] > 1]

    mostrar('<h2 class="sire-h2">Centros con más de un envío</h2>')
    c1, c2, c3 = st.columns(3)
    with c1:
        mostrar(kpi("Centros repetidos", len(resumen), f"Semana {semana_activa}", "warn", "alerta"))
    with c2:
        mostrar(kpi("Registros repetidos", len(duplicados), "Envíos involucrados"))
    with c3:
        mostrar(kpi("A eliminar", len(duplicados) - len(resumen), "Se conserva el más reciente"))

    with st.container(key="panel_resumen_dup"):
        panel_cab("Centros con más de un envío", "Cantidad de veces que se envió cada centro")
        res = resumen.rename(columns={'red': 'Red', 'centro': 'Centro', 'veces_enviado': 'Veces enviado'})
        mostrar(tabla_df(res, derecha=('Veces enviado',)))

    with st.container(key="panel_registros_dup"):
        panel_cab("Registros repetidos", "Detalle de cada envío repetido")
        det = duplicados.sort_values(['red', 'centro', 'fecha_envio'], ascending=[True, True, False])
        vista = pd.DataFrame({
            'Red': det['red'],
            'Centro': det['centro'],
            'Responsable': (det['nombre_usuario'] + ' ' + det['apellido_usuario']).str.strip(),
            'Fecha de envío': det['fecha_envio'].apply(formatear_fecha_columna),
        })
        mostrar(tabla_df(vista))

    actor = actor_actual()
    rep = get_repositorio()
    permitido, motivo_bloqueo = rep.puede_gestionar_duplicados(actor)
    if not permitido:
        mostrar(aviso("warn", "No puede eliminar registros repetidos", esc(motivo_bloqueo)))
        return
    with st.container(key="peligro_duplicados"):
        mostrar(aviso(
            "bad", "Eliminar registros repetidos",
            "Se eliminarán los registros repetidos y se conservará el más reciente de cada centro. "
            "Esta acción no se puede deshacer."))
        with st.form("form_eliminar_duplicados", border=False):
            confirmar = st.checkbox("Confirmo que deseo eliminar los registros repetidos")
            submit = st.form_submit_button("Eliminar registros repetidos", type="primary", icon=":material/delete:")

            if submit:
                if confirmar:
                    with st.spinner("Eliminando registros repetidos..."):
                        eliminados = 0
                        detalle_aud = []
                        for (red, centro), grupo in duplicados.groupby(['red', 'centro']):
                            if len(grupo) > 1:
                                grupo_ordenado = grupo.sort_values('fecha_envio', ascending=False)
                                ids_a_eliminar = grupo_ordenado.iloc[1:]['id'].tolist()
                                for envio_id in ids_a_eliminar:
                                    if db_manager.eliminar_envio(envio_id):
                                        eliminados += 1
                                        detalle_aud.append((f"envío {envio_id}", str(red), f"registro repetido del centro {centro} eliminado"))
                        rep.registrar_duplicados_eliminados(actor, detalle_aud, eliminados, 0, False)

                        st.success(f"Se eliminaron {eliminados} registros repetidos.")
                        st.rerun()
                else:
                    st.info("Marque la casilla de confirmación para eliminar.")


def _selector_semana(db_manager):
    """
    Elige qué semana revisar: la actual (por defecto) u otra de cualquier año registrado.
    Devuelve (semana, anio, es_actual).
    """
    semana_actual = Config.get_semana_actual()
    anios = sorted({a['anio'] for a in (db_manager.obtener_anios_epidemiologicos() or []) if a.get('anio')}, reverse=True)
    anio_actual = Config.get_anio_actual()
    with st.container(key="panel_dup_semana"):
        panel_cab("Semana a revisar", "La semana actual o cualquier semana anterior")
        modo = st.radio("Semana", ["Semana actual", "Otra semana"], horizontal=True, key="dup_modo_semana",
                        label_visibility="collapsed")
        if modo == "Semana actual":
            st.caption(f"Semana {semana_actual} del {anio_actual}, la que reciben las redes ahora.")
            return semana_actual, None, True
        c1, c2, _ = st.columns([1, 1, 2])
        with c1:
            opciones = anios or [anio_actual]
            anio = st.selectbox("Año", opciones, index=opciones.index(anio_actual) if anio_actual in opciones else 0,
                                key="dup_anio_sel")
        with c2:
            semana = st.number_input("Semana", min_value=1, max_value=53, step=1,
                                     value=max(1, semana_actual - 1) if anio == anio_actual else 52,
                                     key=f"dup_semana_sel_{anio}")
        return int(semana), int(anio), False


def mostrar_control_duplicados():
    """Muestra el control de envíos duplicados."""

    requerir_admin()

    db_manager = get_db_manager()

    resultado = st.session_state.pop("dup_resultado", None)
    if resultado:
        mostrar(aviso(resultado[0], resultado[1], resultado[2]))

    semana_sel, anio_sel, es_actual = _selector_semana(db_manager)
    envios = db_manager.obtener_envios(semana=semana_sel, anio=anio_sel, limit=500)

    if not envios:
        mostrar(aviso("info", "No hay envíos registrados para la semana actual" if es_actual
                      else f"No hay envíos registrados para la semana {semana_sel} de {anio_sel}"))
        return

    _seccion_duplicados_marcados(db_manager, envios, semana_sel)
    _seccion_repetidos_normales(db_manager, envios, semana_sel)
