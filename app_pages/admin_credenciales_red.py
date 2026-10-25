# pages/admin_credenciales_red.py
"""
Gestión de credenciales de login por red ("Progreso por Red" para redes).

El administrador genera y distribuye manualmente una contraseña por
cada una de las ~30 redes asistenciales -- no hay autoregistro. Con
esa contraseña, cada red puede entrar a una vista de solo lectura de
su propio progreso semana a semana (ver pages/red_login.py y
pages/red_progreso.py), sin acceso al formulario de envío ni a los
datos de otras redes.
"""

import streamlit as st
import pandas as pd

from src.auth import get_auth_manager
from src.auth_red import get_red_auth_manager
from src.data_loader import get_data_loader
from src.password_policy import generar as generar_password_segura, validar as validar_password
from utils.cuentas_ui import requisitos_html, explicacion_requisitos
from utils.tema import mostrar, aviso, chip
from utils.tema_admin import tabla_df, panel_cab, esc
from app_pages.admin_helpers import formatear_fecha_columna


# Nombres de columna aceptados (case-insensitive) para detectar
# automaticamente cual es la columna de red y cual la de contraseña,
# sin importar como las haya llamado el usuario en su archivo.
_COLUMNAS_RED = ['red', 'nombre_red', 'nombre red', 'network', 'red asistencial']
_COLUMNAS_PASSWORD = ['password', 'contraseña', 'contrasena', 'clave', 'pass', 'contraseña de red']


def _detectar_columna(columnas_df, candidatos) -> str:
    """Busca, sin distinguir mayúsculas/tildes básicas, cuál columna del
    archivo corresponde a la red o a la contraseña."""
    mapa = {str(c).strip().lower(): c for c in columnas_df}
    for candidato in candidatos:
        if candidato in mapa:
            return mapa[candidato]
    return None


def _leer_tabla_credenciales(archivo) -> pd.DataFrame:
    """Lee el archivo subido (CSV o Excel) como DataFrame."""
    nombre = archivo.name.lower()
    if nombre.endswith('.csv'):
        return pd.read_csv(archivo, dtype=str)
    return pd.read_excel(archivo, dtype=str)


def _mostrar_carga_masiva(red_auth, redes_validas: list):
    """
    Carga masiva de credenciales desde un archivo CSV o Excel con dos
    columnas: red y contraseña. Pensado para cuando el administrador ya
    preparó las ~30 contraseñas en una tabla propia y no quiere
    escribirlas una por una en el formulario de arriba.

    El archivo se procesa DENTRO de la sesión de Streamlit -- las
    contraseñas nunca se muestran completas en pantalla ni se envían a
    ningún otro lado; solo se usan para generar el hash bcrypt de cada
    credencial.
    """
    st.markdown("""
    Suba un archivo **.csv** o **.xlsx** con dos columnas: una con el
    nombre de la red y otra con su contraseña temporal (por ejemplo `red` y
    `password`, o `Red` y `Contraseña`; el sistema detecta varios nombres
    comunes). Una fila por red. Cada contraseña debe cumplir la política de
    seguridad (mínimo 10 caracteres, mayúsculas, minúsculas, número y símbolo,
    sin palabras muy usadas); las que no la cumplan se rechazan y se indica el motivo.
    """)

    archivo = st.file_uploader(
        "Archivo con red y contraseña",
        type=['csv', 'xlsx'],
        key="file_uploader_carga_masiva_red"
    )

    if archivo is None:
        return

    try:
        df = _leer_tabla_credenciales(archivo)
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return

    if df.empty:
        st.warning("El archivo no tiene filas.")
        return

    col_red = _detectar_columna(df.columns, _COLUMNAS_RED)
    col_password = _detectar_columna(df.columns, _COLUMNAS_PASSWORD)

    if not col_red or not col_password:
        st.error(
            f"No se pudieron identificar las columnas de red y/o contraseña. "
            f"Columnas encontradas en el archivo: {', '.join(str(c) for c in df.columns)}. "
            f"Renombre las columnas a algo como 'red' y 'password' e intente de nuevo."
        )
        return

    # Limpiar filas vacías o incompletas antes de mostrar cualquier cosa.
    df_limpio = df[[col_red, col_password]].copy()
    df_limpio.columns = ['red', 'password']
    df_limpio['red'] = df_limpio['red'].astype(str).str.strip()
    df_limpio['password'] = df_limpio['password'].astype(str).str.strip()

    filas_incompletas = df_limpio[(df_limpio['red'] == '') | (df_limpio['password'] == '') | (df_limpio['red'] == 'nan') | (df_limpio['password'] == 'nan')]
    df_validas = df_limpio.drop(index=filas_incompletas.index)

    if not filas_incompletas.empty:
        st.warning(f"{len(filas_incompletas)} fila(s) sin red o sin contraseña serán ignoradas.")

    if df_validas.empty:
        st.error("No quedaron filas válidas (con red y contraseña) para procesar.")
        return

    # Aviso (no bloqueante) si algún nombre de red del archivo no
    # coincide exactamente con una red ya registrada en el sistema --
    # suele ser un typo o una red con nombre distinto.
    redes_no_reconocidas = sorted(set(df_validas['red']) - set(redes_validas))
    if redes_no_reconocidas:
        st.warning(
            f"Estas redes del archivo no coinciden con ninguna red registrada en el "
            f"sistema: {', '.join(redes_no_reconocidas)}. Revise que el nombre esté escrito "
            f"igual (mayúsculas y todo) antes de continuar, o proceda si sabe que es correcto."
        )

    # Vista previa SIN mostrar la contraseña completa -- solo para
    # confirmar que se detectaron las redes correctas y cuántos
    # caracteres tiene cada contraseña.
    st.markdown("**Vista previa (las contraseñas no se muestran completas):**")
    df_preview = df_validas.copy()
    df_preview['Seguridad'] = [
        'Cumple' if validar_password(p, contexto=[r])[0] else 'No cumple la política'
        for r, p in zip(df_preview['red'], df_preview['password'])
    ]
    df_preview['password'] = df_preview['password'].apply(lambda p: (p[:2] + '•' * max(0, len(p) - 2)) if p else '')
    df_preview = df_preview.rename(columns={'red': 'Red', 'password': 'Contraseña (oculta)'})
    st.dataframe(df_preview, width='stretch', hide_index=True)

    st.caption(f"{len(df_validas)} credencial(es) lista(s) para procesar.")

    confirmar_no_reconocidas = True
    if redes_no_reconocidas:
        confirmar_no_reconocidas = st.checkbox(
            "Crear de todas formas las credenciales de redes no reconocidas",
            value=False,
            key="chk_confirmar_redes_no_reconocidas"
        )

    if st.button("Procesar carga masiva", type="primary", key="btn_procesar_carga_masiva", use_container_width=True):
        creado_por = (
            st.session_state.get('admin_usuario', {}).get('usuario', 'SYSTEM')
            if isinstance(st.session_state.get('admin_usuario'), dict) else 'SYSTEM'
        )

        resultados = []
        for _, fila in df_validas.iterrows():
            red_fila = fila['red']
            password_fila = fila['password']

            if red_fila in redes_no_reconocidas and not confirmar_no_reconocidas:
                resultados.append({'Red': red_fila, 'Resultado': 'Omitida (red no reconocida, sin confirmar)'})
                continue

            valida, motivo = validar_password(password_fila, contexto=[red_fila])
            if not valida:
                resultados.append({'Red': red_fila, 'Resultado': f'Rechazada: {motivo}'})
                continue

            exito, mensaje = red_auth.crear_o_actualizar_credencial(
                red=red_fila, password=password_fila, creado_por=creado_por
            )
            resultados.append({'Red': red_fila, 'Resultado': 'OK' if exito else f'Error: {mensaje}'})

        st.markdown("**Resultado de la carga masiva:**")
        st.dataframe(pd.DataFrame(resultados), width='stretch', hide_index=True)

        exitosas = sum(1 for r in resultados if r['Resultado'] == 'OK')
        st.success(f"{exitosas} de {len(resultados)} credenciales se crearon o actualizaron correctamente.")
        st.info("Recuerde entregar cada contraseña solo a su red correspondiente por un canal seguro.")


def _chip_activo(valor):
    return chip("Activo", "ok", "check") if valor in (True, 1, "1", "true", "True") else chip("Desactivado", "mute")


def _chip_temporal(valor):
    return chip("Pendiente de cambio", "warn", "reloj") if valor in (True, 1, "1", "true", "True") else chip("Propia", "ok", "check")


def mostrar_gestion_credenciales_red():
    """Muestra la gestión de credenciales de login por red."""

    auth_manager = get_auth_manager()
    red_auth = get_red_auth_manager()
    data_loader = get_data_loader()

    if not auth_manager.es_super_admin(st.session_state.get('admin_token')):
        mostrar(aviso("warn", "Acceso restringido", "Solo SUPER_ADMIN puede gestionar las credenciales de red."))
        return

    mostrar(aviso(
        "info", "Cómo funciona",
        "Cada red tiene su propia contraseña para entrar a una vista de solo lectura de su progreso semana a "
        "semana. Usted genera la contraseña aquí y se la entrega manualmente a la red; no hay autoregistro."))

    redes = data_loader.obtener_redes()
    if not redes:
        mostrar(aviso("info", "No hay redes registradas en el sistema"))
        return

    credenciales = red_auth.listar_credenciales()
    redes_con_credencial = {c['red']: c for c in credenciales}

    # ============================================================
    # LISTADO DE CREDENCIALES CONFIGURADAS
    # ============================================================
    with st.container(key="panel_cred_lista"):
        panel_cab("Redes con acceso configurado",
                  f"{len(credenciales)} de {len(redes)} redes tienen contraseña")
        if not credenciales:
            mostrar(aviso("info", "Todavía no se configuró ninguna contraseña de red"))
        else:
            df = pd.DataFrame(credenciales)
            vista = pd.DataFrame({
                'Red': df['red'],
                'Acceso': df.get('activo', True),
                'Contraseña': df.get('debe_cambiar_password', False),
                'Último ingreso': df['ultimo_login'].apply(formatear_fecha_columna) if 'ultimo_login' in df.columns else '—',
                'Actualizada': df['fecha_actualizacion'].apply(formatear_fecha_columna) if 'fecha_actualizacion' in df.columns else '—',
            })
            mostrar(tabla_df(vista, chips={'Acceso': _chip_activo, 'Contraseña': _chip_temporal}, alto=480))

    # ============================================================
    # CREAR / REGENERAR CONTRASEÑA DE UNA RED
    # ============================================================
    with st.container(key="panel_cred_crear"):
        panel_cab("Crear o regenerar contraseña de una red",
                  "Si la red ya tiene contraseña, se reemplaza por la nueva")

        red_seleccionada = st.selectbox(
            "Red", options=redes, key="select_red_credencial",
            help="Si la red ya tiene una contraseña, se le asignará una nueva (regenerar)."
        )

        ya_existe = red_seleccionada in redes_con_credencial
        if ya_existe:
            mostrar(aviso("warn", f"La red {esc(red_seleccionada)} ya tiene una contraseña",
                          "Guardar una nueva la reemplaza."))

        col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
        with col1:
            password_manual = st.text_input(
                "Contraseña temporal", type="password", key="input_password_red",
                help="Puede escribir una o generar una segura con el botón de al lado. "
                     "La red deberá cambiarla en su primer ingreso."
            )
        with col2:
            if st.button("Generar segura", key="btn_generar_password_red", use_container_width=True,
                         icon=":material/autorenew:"):
                st.session_state['_password_red_generada'] = generar_password_segura()

        if password_manual:
            mostrar(requisitos_html(password_manual, [red_seleccionada]))
            explicacion_requisitos()

        password_generada = st.session_state.get('_password_red_generada')
        if password_generada:
            mostrar(aviso("warn", "Contraseña generada",
                          f"<code>{esc(password_generada)}</code> · Cópiela antes de continuar: no se volverá a mostrar."))

        password_a_usar = password_manual or password_generada

        if st.button(
            "Guardar contraseña" if not ya_existe else "Regenerar contraseña",
            key="btn_guardar_credencial_red", type="primary", icon=":material/key:",
        ):
            if not password_a_usar:
                mostrar(aviso("bad", "Falta la contraseña", "Escriba una contraseña o genere una segura."))
            else:
                exito, mensaje = red_auth.crear_o_actualizar_credencial(
                    red=red_seleccionada,
                    password=password_a_usar,
                    creado_por=st.session_state.get('admin_usuario', {}).get('usuario', 'SYSTEM')
                    if isinstance(st.session_state.get('admin_usuario'), dict) else 'SYSTEM'
                )
                if exito:
                    mostrar(aviso("ok", esc(mensaje)))
                    if password_generada:
                        mostrar(aviso(
                            "warn", f"Contraseña de la red {esc(red_seleccionada)}",
                            f"<code>{esc(password_a_usar)}</code> · Guárdela ahora: no se volverá a mostrar."))
                    st.session_state.pop('_password_red_generada', None)
                else:
                    mostrar(aviso("bad", "No se pudo guardar", esc(mensaje)))

    # ============================================================
    # CARGA MASIVA DESDE ARCHIVO (CSV / EXCEL)
    # ============================================================
    with st.container(key="panel_cred_masiva"):
        panel_cab("Carga masiva desde archivo", "CSV o Excel con una fila por red")
        _mostrar_carga_masiva(red_auth, redes)

    # ============================================================
    # ACTIVAR / DESACTIVAR / ELIMINAR
    # ============================================================
    if credenciales:
        with st.container(key="panel_cred_gestion"):
            panel_cab("Activar o desactivar acceso", "Una red desactivada no puede ingresar a ver su progreso")
            col0, col1, _ = st.columns([1.4, 1, 1.6], vertical_alignment="bottom")
            with col0:
                red_gestion = st.selectbox(
                    "Red", options=[c['red'] for c in credenciales], key="select_red_gestion_credencial"
                )
            info_red = redes_con_credencial.get(red_gestion, {})
            esta_activo = info_red.get('activo', True)
            with col1:
                if esta_activo:
                    if st.button("Desactivar acceso", key="btn_desactivar_red", use_container_width=True):
                        exito, mensaje = red_auth.desactivar_credencial(red_gestion)
                        if exito:
                            st.toast(mensaje, icon=":material/check_circle:")
                            st.rerun()
                        st.error(mensaje)
                else:
                    if st.button("Activar acceso", key="btn_activar_red", type="primary", use_container_width=True):
                        exito, mensaje = red_auth.activar_credencial(red_gestion)
                        if exito:
                            st.toast(mensaje, icon=":material/check_circle:")
                            st.rerun()
                        st.error(mensaje)

        with st.container(key="peligro_credencial"):
            mostrar(aviso("bad", "Eliminar la credencial de una red",
                          "La red deja de poder ingresar hasta que se le cree una contraseña nueva."))
            col1, col2, col3 = st.columns([1.2, 1.6, 1], vertical_alignment="bottom")
            with col1:
                red_eliminar = st.selectbox("Red", options=[c['red'] for c in credenciales], key="select_red_eliminar_cred")
            with col2:
                confirmar = st.checkbox(f"Confirmo que deseo eliminar la credencial de {red_eliminar}", key="cred_confirma")
            with col3:
                if st.button("Eliminar credencial", type="primary", use_container_width=True,
                             icon=":material/delete:", key="btn_eliminar_cred"):
                    if not confirmar:
                        st.warning("Marque la casilla de confirmación para eliminar.")
                    else:
                        exito, mensaje = red_auth.eliminar_credencial(red_eliminar)
                        if exito:
                            st.toast(mensaje, icon=":material/check_circle:")
                            st.rerun()
                        st.error(mensaje)
