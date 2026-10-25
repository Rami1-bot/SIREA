# pages/usuario.py
"""
Panel de usuario - Formulario para envio de reportes.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import re
from typing import List, Optional, Dict, Any

from src.config import Config
from src.data_loader import get_data_loader
from src.zip_processor import get_zip_processor
from src.db_manager import get_db_manager
from utils.helpers import sanitizar_html
from utils import frecuentes
from utils.cuentas_ui import campos_correo_verificado
from utils.tema import (
    aplicar_tema, encabezado_publico, pie_pagina, titulo_pagina, mostrar,
    mostrar_aviso, aviso, chip, icono, tarjeta, filas, detalle, hero_acuse,
    seccion, lista_estado, periodo_semana, fecha_corte_info, TONOS, AZUL,
)


# ============================================================
# NOTA: semana activa, año activo y fecha de corte se obtienen
# directamente de Config.get_semana_actual() / get_anio_actual() /
# get_fecha_corte(), que centralizan la lectura desde Supabase con
# fallback a .env (antes había una copia local de estas 3 funciones
# aquí, con un fallback a atributos de Config que no existían).
# ============================================================


# ============================================================
# LÓGICA DE NEGOCIO: movida a pages/usuario_logica.py
# (verificación de estado de envío, formateo de centros, procesar_envio,
# etc. — separada de este archivo para que quede reutilizable/testeable
# sin depender del renderizado de pantalla, y lista para exponerse como
# tools del agente en la siguiente fase)
# ============================================================

from app_pages.usuario_logica import (
    obtener_anios_permitidos,
    obtener_semanas_por_anio,
    obtener_semanas_disponibles_por_anio,
    obtener_fecha_corte_semana,
    obtener_centros_excluidos,
    obtener_centros_con_red_por_red,
    formatear_centro_desde_dict,
    obtener_nombre_limpio_desde_dict,
    extraer_nombre_limpio,
    extraer_codigo,
    obtener_hora_local,
    estandarizar_nombre,
    verificar_estado_envio,
    permitir_adelantados,
    procesar_envio,
    verificar_envio_duplicado,
    clasificar_envio,
    validar_red_zip,
    calcular_avance_red,
)


def init_session_state():
    """Inicializa las variables de sesion."""
    if 'usuario_envio_exitoso' not in st.session_state:
        st.session_state.usuario_envio_exitoso = False
    if 'usuario_datos_envio' not in st.session_state:
        st.session_state.usuario_datos_envio = {}
    if 'usuario_red_seleccionada' not in st.session_state:
        st.session_state.usuario_red_seleccionada = None
    if 'usuario_centros_disponibles' not in st.session_state:
        st.session_state.usuario_centros_disponibles = []
    if 'usuarios_frecuentes' not in st.session_state:
        st.session_state.usuarios_frecuentes = []
    if 'usuario_autocompletado' not in st.session_state:
        st.session_state.usuario_autocompletado = None
    if 'pagina' not in st.session_state:
        st.session_state.pagina = 'landing'
    if 'campos_validados' not in st.session_state:
        st.session_state.campos_validados = {}
    # Cache de centros excluidos (se actualiza desde la DB)
    if 'centros_excluidos' not in st.session_state:
        st.session_state.centros_excluidos = {}
    # Cache de centros por red
    if 'centros_por_red' not in st.session_state:
        st.session_state.centros_por_red = {}


def actualizar_centros_excluidos():
    """
    Actualiza el cache de centros excluidos desde la base de datos.
    """
    st.session_state.centros_excluidos = obtener_centros_excluidos()


def actualizar_centros():
    """
    Actualiza los centros disponibles segun la red seleccionada.
    Usa la vista centros_con_red para obtener datos completos.
    Excluye los centros que el administrador ha marcado como excluidos.
    """
    # Actualizar cache de centros excluidos desde la DB
    actualizar_centros_excluidos()
    
    if not st.session_state.usuario_red_seleccionada:
        st.session_state.usuario_centros_disponibles = []
        return
    
    red_nombre = st.session_state.usuario_red_seleccionada
    
    # Obtener centros de la red usando la vista centros_con_red
    centros_db = obtener_centros_con_red_por_red(red_nombre)
    
    if not centros_db:
        st.session_state.usuario_centros_disponibles = []
        return
    
    # Obtener centros excluidos para esta red
    centros_excluidos = st.session_state.centros_excluidos
    excluidos_red = centros_excluidos.get(red_nombre, [])
    
    # Filtrar centros excluidos
    centros_filtrados = []
    nombres_excluidos = []
    
    for centro in centros_db:
        # Obtener el nombre del centro desde el diccionario
        nombre_centro = centro.get('centro_nombre', '')
        codigo_centro = centro.get('codigo', '')
        
        # Formatear el centro para mostrarlo
        centro_formateado = formatear_centro_desde_dict(centro)
        
        # Verificar si el centro está excluido
        esta_excluido = False
        
        for excluido in excluidos_red:
            # Extraer nombre del excluido
            excluido_nombre = extraer_nombre_limpio(excluido)
            
            # Comparar por nombre completo (ignorando mayúsculas)
            if nombre_centro and excluido_nombre and nombre_centro.lower() == excluido_nombre.lower():
                esta_excluido = True
                break
            
            # Comparar por nombre formateado
            if centro_formateado.lower() == excluido.lower():
                esta_excluido = True
                break
            
            # Comparar por código
            if codigo_centro and excluido_nombre and codigo_centro == excluido_nombre:
                esta_excluido = True
                break
        
        if not esta_excluido:
            centros_filtrados.append(centro_formateado)
        else:
            nombres_excluidos.append(centro_formateado)
    
    st.session_state.usuario_centros_disponibles = centros_filtrados
    
    # Guardar los centros excluidos filtrados para mostrarlos en la UI
    st.session_state.nombres_excluidos_actuales = nombres_excluidos


def mostrar_encabezado(subtitulo: str = None, migas: str = "Inicio / Enviar reporte"):
    """Barra superior, titulo de la pagina y datos de la semana en curso."""

    encabezado_publico("enviar")
    titulo_pagina(
        "Envío de reporte semanal",
        subtitulo or "Complete los datos y adjunte el archivo ZIP de su red. "
                     "Los campos marcados con * son obligatorios.",
        migas=migas,
    )


def _panel_semana():
    """Tarjeta 'Semana en curso' del panel lateral."""
    semana = Config.get_semana_actual()
    anio = Config.get_anio_actual()
    corte, _ = fecha_corte_info()
    mostrar(tarjeta("Semana en curso", filas([
        ("Semana activa", f"{semana} · {anio}"),
        ("Periodo", periodo_semana(anio, semana)),
        ("Fecha límite", corte),
    ])))


def _panelcalcular_avance_red(red: str):
    """
    Tarjeta 'Avance de la red': cuantos centros de la red ya enviaron en
    la semana activa, con barra y lista Enviado/Pendiente. Es solo
    informativa: no afecta al formulario.
    """
    semana = Config.get_semana_actual()
    anio = Config.get_anio_actual()
    titulo = f"Avance de la red {sanitizar_html(str(red))} · Semana {semana}"

    av = calcular_avance_red(red, anio, semana) if red else None
    if av is None:
        mostrar(tarjeta(titulo, '<p class="sire-nota" style="margin:12px 0">No se pudo consultar el avance en este momento.</p>'))
        return
    if av['total'] == 0:
        mostrar(tarjeta(titulo, '<p class="sire-nota" style="margin:12px 0">La red no tiene centros activos registrados.</p>'))
        return

    total = av['total']
    n_env = len(av['enviados'])
    pct = int(round(n_env * 100 / total))
    color = TONOS["ok"][0] if pct >= 100 else AZUL
    items = (
        [(sanitizar_html(c), "ok", "Enviado") for c in av['enviados']]
        + [(sanitizar_html(c), "warn", "Pendiente") for c in av['pendientes']]
    )
    nota = f"Se actualiza con cada envío recibido. {av['excluidos']} centro(s) excluido(s) por la OIIS no se cuentan." if av['excluidos'] else "Se actualiza con cada envío recibido."
    cuerpo = (
        f'<div class="sire-avance-n"><b>{n_env} de {total}</b>'
        f'<span>centros enviaron · <strong>{pct} %</strong></span></div>'
        f'<div class="sire-avance-pista" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" '
        f'aria-valuemax="100" aria-label="Avance de la red"><div style="width:{pct}%;background:{color}"></div></div>'
        f'<div class="sire-scroll" style="margin-top:12px;border-top:1px solid #E4EAEF">{lista_estado(items)}</div>'
        f'<p class="sire-nota">{nota}</p>'
    )
    mostrar(tarjeta(titulo, cuerpo))


def _panel_antes_de_enviar():
    mostrar("""
    <div class="sire-panel">
      <h3>Antes de enviar</h3>
      <ul style="margin:0;padding-left:20px;font-size:15px;color:#33424F;display:flex;flex-direction:column;gap:8px">
        <li>Empaquete todos los archivos del reporte en un solo ZIP.</li>
        <li>Verifique que el ZIP corresponda a la red y la semana elegidas.</li>
        <li>Recibirá un acuse con su código de seguimiento en el correo indicado.</li>
      </ul>
    </div>
    """)



@st.dialog("Posible envío duplicado")
def _dialogo_confirmar_envio_duplicado():
    """
    Modal de confirmación mostrado cuando ya existe un envío registrado
    para la misma red/semana/año que incluye alguno de los mismos
    centros que el usuario está a punto de enviar.

    No bloquea el envío -- solo advierte y pide confirmar. Si el
    usuario confirma ("Sí"), el envío se procesa aquí mismo con los
    datos guardados en session_state al detectar la coincidencia. Si
    cancela ("No"), se descarta el intento y no se envía nada.

    IMPORTANTE: esta función se llama desde mostrar_formulario(), FUERA
    del fragmento _renderizar_seccion_formulario() -- llamar a
    st.dialog dentro de un st.fragment es una combinación no soportada
    por Streamlit (el modal queda "colgado" y no cierra bien).
    """
    pendiente = st.session_state.get('_dup_envio_pendiente')
    if not pendiente:
        return

    info = pendiente['duplicado_info']
    plan = pendiente.get('plan') or {}
    dividir = plan.get('modo') == 'dividir'

    if dividir:
        st.warning(
            f"Parte de su ZIP ya fue recibida esta semana ({pendiente['semana']}/{pendiente['ano']}, "
            f"red **{pendiente['red']}**): **{len(plan['repetidos'])} archivo(s)** de "
            f"{'; '.join(info.get('pares_repetidos') or info['centros_coincidentes'])}."
        )
        st.success(
            f"Los otros **{len(plan['nuevos'])} archivo(s)** son nuevos y se registrarán como un envío normal."
        )
    else:
        st.warning(
            f"Ya existe un envío registrado para la red **{pendiente['red']}** "
            f"en la semana {pendiente['semana']}/{pendiente['ano']}, para "
            f"el/los centro(s): **{', '.join(info['centros_coincidentes'])}**."
        )

    st.markdown("**Envío(s) previo(s) encontrado(s):**")
    for e in info['envios']:
        fecha = str(e.get('fecha_envio') or '')[:19].replace('T', ' ')
        st.caption(
            f"- Código `{e.get('codigo_seguimiento', 'N/A')}` · "
            f"{e.get('nombre_usuario') or 'N/D'} · {fecha or 'fecha N/D'} · "
            f"estado {e.get('estado', 'N/D')}"
        )

    if dividir:
        mostrar_aviso(
            "warn", "Qué ocurrirá si continúa",
            "Su ZIP se <strong>dividirá automáticamente</strong>: los archivos nuevos se registran como envío "
            "normal y los ya recibidos se guardan en la <strong>carpeta de duplicados</strong> sin reemplazar "
            "al envío anterior (la OIIS será notificada). Recibirá un solo acuse que explica ambas partes."
        )
        st.markdown("¿Desea continuar?")
    else:
        mostrar_aviso(
            "warn", "Qué ocurrirá si continúa",
            "Su archivo se guardará en una <strong>carpeta aparte de duplicados</strong>: "
            "<strong>no reemplazará</strong> al envío anterior y la OIIS será notificada para revisarlo. "
            "Recibirá un acuse de color naranja."
        )
        st.markdown("¿Desea enviar los archivos de todos modos?")

    puede_reemplazar = bool(plan.get('reemplazo_posible'))
    if puede_reemplazar:
        mostrar_aviso(
            "info", "Opción: reemplazar lo ya enviado",
            "Si este ZIP corrige o completa lo enviado antes, puede <strong>reemplazarlo</strong>: se registra "
            "<strong>todo este ZIP</strong> como envío normal y los archivos anteriores de esos centros pasan a la "
            "carpeta <strong>REEMPLAZADOS</strong> (no se borra nada). Si otra persona hizo el envío anterior, se le avisará."
        )
    elif plan.get('reemplazo_motivo'):
        st.caption("Reemplazo no disponible: " + plan['reemplazo_motivo'])

    def _enviar(**extra):
        with st.spinner("Procesando envío..."):
            procesar_envio(
                nombres=pendiente['nombres'],
                apellidos=pendiente['apellidos'],
                correo=pendiente['correo'],
                red=pendiente['red'],
                centros=pendiente['centros'],
                ano=pendiente['ano'],
                semana=pendiente['semana'],
                tipos=pendiente['tipos'],
                archivo=pendiente['archivo'],
                info_zip=pendiente['info_zip'],
                estado_envio=pendiente['estado_envio'],
                duplicado_info=pendiente['duplicado_info'],
                plan=pendiente.get('plan'),
                sustento=pendiente.get('sustento', ''),
                **extra
            )
        # Si el código llega hasta aquí, procesar_envio no completó con éxito (el caso exitoso termina
        # en su propio st.rerun()): se limpia el estado pendiente para no dejar el diálogo con datos viejos.
        st.session_state.pop('_dup_envio_pendiente', None)

    columnas = st.columns(3 if puede_reemplazar else 2)

    with columnas[0]:
        if st.button(
            "Sí, dividir y enviar" if dividir else "Sí, enviar como duplicado",
            key="btn_dup_confirmar_si",
            use_container_width=True,
            type="primary"
        ):
            _enviar(es_duplicado=not dividir)

    if puede_reemplazar:
        with columnas[1]:
            if st.button(
                "Reemplazar los ya enviados",
                key="btn_dup_reemplazar",
                use_container_width=True
            ):
                _enviar(es_duplicado=False, reemplazar=True)

    with columnas[-1]:
        if st.button(
            "No, cancelar",
            key="btn_dup_confirmar_no",
            use_container_width=True
        ):
            st.session_state.pop('_dup_envio_pendiente', None)
            st.info("Envío cancelado. No se enviaron archivos.")
            st.rerun()


def mostrar_formulario():
    """Muestra el formulario de envío con validación en tiempo real."""

    aplicar_tema()

    # Actualizar cache de centros excluidos desde la DB al cargar
    actualizar_centros_excluidos()

    mostrar_encabezado()

    # Si el envío anterior detectó una posible duplicidad, se muestra el
    # modal de confirmación AQUÍ (fuera del fragmento de abajo) -- llamar
    # a st.dialog dentro de un st.fragment no funciona bien en Streamlit.
    if st.session_state.get('_dup_envio_pendiente'):
        _dialogo_confirmar_envio_duplicado()

    with st.container(key="sire_enviar"):
        _renderizar_seccion_formulario()

    pie_pagina()


@st.fragment
def _renderizar_seccion_formulario():
    """Formulario (izquierda) y panel lateral con el avance de la red (derecha)."""
    col_form, col_aside = st.columns([2.1, 1], gap="large")
    with col_form:
        red = _formulario_cuerpo()
    with col_aside:
        _panel_semana()
        _panelcalcular_avance_red(red)
        _panel_antes_de_enviar()


def _usar_periodo_del_zip(semana: int, anio: int):
    """Corrige el formulario con la semana/año que traen los archivos del ZIP."""
    st.session_state['sel_anio'] = anio
    st.session_state['sel_semana'] = semana


def _tipo_visible(tipo: str) -> str:
    """Texto del tipo de reporte para mostrar (el valor guardado no lleva tilde)."""
    return {"Hospitalizacion": "Hospitalización"}.get(tipo, tipo)


def _mostrar_estado_envio(estado_envio: dict):
    """Aviso de si el envío quedará a tiempo, tardío o no permitido para la semana elegida."""
    msg = sanitizar_html(str(estado_envio.get('mensaje', '')))
    no_permitido = estado_envio.get('es_atrasado') and any(
        t in msg for t in ("NO PERMITIDO", "NO PERMITIDA")
    )
    detalle_txt = (
        f"Semana actual: {estado_envio['semana_actual']}/{estado_envio['anio_actual']} · "
        f"Semana seleccionada: {estado_envio['semana_seleccionada']}/{estado_envio['anio_seleccionado']}"
    )
    if estado_envio.get('fecha_limite'):
        detalle_txt += f" · Fecha de corte: {estado_envio['fecha_limite'].strftime('%d/%m/%Y %H:%M')}"
    if estado_envio.get('semanas_atraso', 0) and estado_envio.get('es_atrasado'):
        detalle_txt += f" · Semanas de atraso: {estado_envio['semanas_atraso']}"

    if no_permitido:
        mostrar_aviso("warn", msg)
    elif estado_envio.get('es_atrasado'):
        mostrar_aviso("bad", msg, detalle_txt)
    else:
        mostrar_aviso("ok", msg, detalle_txt)


def _formulario_cuerpo():
    """
    Sección interactiva del formulario (usuario frecuente, red, datos
    del remitente, centros, semana/año con vista previa de atraso en
    vivo, tipo de reporte, archivo y envío).

    Aislada en un fragmento para que escribir en un campo o cambiar un
    selector no recargue la página completa (CSS, encabezado, progreso
    de la red) -- solo esta sección se vuelve a dibujar. El envío en sí
    sigue afectando toda la app porque procesar_envio() llama a
    st.rerun() sin scope='fragment', lo que fuerza una recarga completa.
    """
    
    # Si en la vuelta anterior se detectó que el ZIP no coincide con los
    # centros seleccionados, aquí se aplica la corrección -- tiene que
    # pasar ANTES de que el multiselect se dibuje más abajo, porque
    # Streamlit no permite cambiar el valor de un widget después de
    # instanciado en la misma ejecución.
    if '_centros_auto_sync' in st.session_state:
        st.session_state['multiselect_centros'] = st.session_state.pop('_centros_auto_sync')
    # Igual con el tipo de reporte: se completa con lo que traen los nombres del ZIP.
    if '_tipos_auto_sync' in st.session_state:
        st.session_state['multiselect_tipos'] = st.session_state.pop('_tipos_auto_sync')
    
    # ============================================================
    # TARJETAS DEL FORMULARIO (se crean primero para poder rellenarlas
    # en el orden que necesita la logica, sin cambiar su orden en pantalla)
    # ============================================================
    c1 = st.container(key="sec_1")
    c2 = st.container(key="sec_2")
    c3 = st.container(key="sec_3")
    c4 = st.container(key="sec_4")

    # Usuarios frecuentes: se guardan en el navegador (ver utils/frecuentes.py)
    # y un clic completa nombres, apellidos y correo. El componente debe
    # dibujarse en cada ejecución, antes de crear los campos de texto.
    usuarios_frecuentes = frecuentes.almacen()
    with c2:
        seccion(2, "Responsable del envío")
        frecuentes.panel(usuarios_frecuentes)

    data_loader = get_data_loader()
    redes = data_loader.obtener_redes()

    default_red = None
    default_centros = []

    if st.session_state.usuario_red_seleccionada is None:
        if default_red and default_red in redes:
            st.session_state.usuario_red_seleccionada = default_red
        elif redes:
            st.session_state.usuario_red_seleccionada = redes[0]
        actualizar_centros()

    # ============================================================
    # 1. RED Y PERIODO
    # ============================================================
    index_red = 0
    if st.session_state.usuario_red_seleccionada in redes:
        index_red = redes.index(st.session_state.usuario_red_seleccionada)

    # Años y semanas disponibles (dinámicos desde la BD)
    anios_permitidos = obtener_anios_permitidos()
    if not anios_permitidos:
        anios_permitidos = [datetime.now().year]
    anos = anios_permitidos
    anio_actual = Config.get_anio_actual()
    idx_anio = anos.index(anio_actual) if anio_actual in anos else 0

    with c1:
        seccion(1, "Red y periodo")
        col_red, col_anio, col_sem = st.columns([2, 1, 1])

        with col_red:
            red_seleccionada = st.selectbox(
                "Red asistencial *",
                options=redes,
                index=index_red,
                key="red_select"
            )

        with col_anio:
            ano_seleccionado = st.selectbox(
                "Año *",
                options=anos,
                index=idx_anio,
                key="sel_anio"
            )

        semanas_disponibles = obtener_semanas_disponibles_por_anio(ano_seleccionado)
        if not semanas_disponibles:
            semanas_disponibles = list(range(1, 54))

        semana_actual_sistema = Config.get_semana_actual()
        idx_semana = 0
        if semana_actual_sistema in semanas_disponibles:
            idx_semana = semanas_disponibles.index(semana_actual_sistema)

        with col_sem:
            semana_seleccionada = st.selectbox(
                "Semana *",
                options=semanas_disponibles,
                index=idx_semana,
                key="sel_semana"
            )

        if red_seleccionada != st.session_state.usuario_red_seleccionada:
            st.session_state.usuario_red_seleccionada = red_seleccionada
            # Actualizar centros disponibles (excluye los excluidos)
            actualizar_centros()

        # ---- Estado del envío (a tiempo / atrasado) según la semana elegida ----
        estado_envio = verificar_estado_envio(semana_seleccionada, ano_seleccionado)
        _mostrar_estado_envio(estado_envio)
        st.caption(f"Años permitidos: {', '.join(map(str, anios_permitidos))} · Semanas disponibles: {len(semanas_disponibles)}")

        # ---- Centros excluidos por el administrador para esta red ----
        excluidos_red = st.session_state.centros_excluidos.get(red_seleccionada, [])
        if excluidos_red:
            nombres_excluidos = [extraer_nombre_limpio(e) or e for e in excluidos_red]
            mostrar_aviso(
                "info",
                f"{len(excluidos_red)} centro(s) excluido(s) por la OIIS",
                "No aparecerán en la lista de selección: "
                f"<strong>{sanitizar_html(', '.join(nombres_excluidos))}</strong>"
            )

    # ============================================================
    # 2. RESPONSABLE DEL ENVIO
    # ============================================================
    with c2:
        col1, col2 = st.columns(2)

        with col1:
            apellidos = st.text_input(
                "Apellidos *",
                placeholder="Ej. Quispe Rojas",
                key="input_apellidos"
            )

        with col2:
            nombres = st.text_input(
                "Nombres *",
                placeholder="Ej. María Elena",
                key="input_nombres"
            )

        correo, eval_correo = campos_correo_verificado(
            "input_correo", "input_correo_repetido", "chk_correo_noinst", "sire_sugerencias_correo",
            ayuda="A este correo se enviará el acuse de recibo con el código de seguimiento.",
        )

    # ============================================================
    # 3. CENTROS Y TIPO DE REPORTE
    # ============================================================
    with c3:
        seccion(3, "Centros y tipo de reporte")

        if red_seleccionada and st.session_state.usuario_centros_disponibles:
            # Filtrar default_centros_validos solo con centros disponibles
            default_centros_validos = [
                c for c in default_centros
                if c in st.session_state.usuario_centros_disponibles
            ]

            centros_seleccionados = st.multiselect(
                "Centros asistenciales *",
                options=st.session_state.usuario_centros_disponibles,
                default=default_centros_validos if default_centros_validos else None,
                key="multiselect_centros",
                placeholder="Seleccione uno o más centros",
                help="Solo se muestran los centros de la red seleccionada."
            )
        else:
            centros_seleccionados = st.multiselect(
                "Centros asistenciales *",
                options=[],
                disabled=True,
                key="multiselect_centros",
                placeholder="No hay centros disponibles para esta red"
            )

        tipos_reporte = ["Consulta Externa", "Hospitalizacion", "Emergencia"]
        tipos_seleccionados = st.multiselect(
            "Tipo de reporte *",
            options=tipos_reporte,
            format_func=_tipo_visible,
            key="multiselect_tipos",
            placeholder="Seleccione uno o más tipos"
        )

    # ============================================================
    # 4. ARCHIVO ZIP
    # ============================================================
    with c4:
        seccion(4, "Archivo ZIP")
        mostrar_aviso(
            "warn",
            "Requisito del sistema",
            "Solo se aceptan archivos en formato <strong>.ZIP</strong>. El botón de envío se "
            "habilitará únicamente cuando adjunte un archivo ZIP válido."
        )

    with c4:
        archivo = st.file_uploader(
            "Seleccione su archivo ZIP *",
            type=['zip'],
            key="file_uploader_zip",
            help="Solo se permiten archivos con extensión .zip. Empaquete sus archivos en formato ZIP."
        )
    
        # ============================================================
        # VALIDACION EN TIEMPO REAL
        # ============================================================
    
        validaciones = {}
    
        # Apellidos - Validar
        if not apellidos:
            validaciones['Apellidos'] = {'estado': 'pendiente', 'mensaje': 'Campo obligatorio'}
        elif re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ ]+\Z', apellidos) and len(apellidos) >= 2:
            validaciones['Apellidos'] = {'estado': 'ok', 'mensaje': 'Válido'}
        else:
            validaciones['Apellidos'] = {'estado': 'error', 'mensaje': 'Solo letras, mínimo 2 caracteres'}

        # Nombres - Validar (se estandarizan al enviar)
        if not nombres:
            validaciones['Nombres'] = {'estado': 'pendiente', 'mensaje': 'Campo obligatorio'}
        elif re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ ]+\Z', nombres) and len(nombres) >= 2:
            validaciones['Nombres'] = {'estado': 'ok', 'mensaje': 'Válido'}
        else:
            validaciones['Nombres'] = {'estado': 'error', 'mensaje': 'Solo letras, mínimo 2 caracteres'}

        # Correo
        validaciones['Correo Electrónico'] = {'estado': eval_correo['estado'], 'mensaje': eval_correo['mensaje']}
    
        # Centros
        if not centros_seleccionados or len(centros_seleccionados) == 0:
            validaciones['Centros Asistenciales'] = {'estado': 'pendiente', 'mensaje': 'Seleccione al menos un centro'}
        else:
            validaciones['Centros Asistenciales'] = {'estado': 'ok', 'mensaje': f'{len(centros_seleccionados)} seleccionados'}
    
        # Tipo de Reporte
        if not tipos_seleccionados or len(tipos_seleccionados) == 0:
            validaciones['Tipo de Reporte'] = {'estado': 'pendiente', 'mensaje': 'Seleccione al menos un tipo'}
        else:
            validaciones['Tipo de Reporte'] = {'estado': 'ok', 'mensaje': f'{len(tipos_seleccionados)} seleccionados'}
    
        # Archivo ZIP
        zip_valido = False
        info_zip = None
        zip_extension_valida = False
    
        if archivo is None:
            validaciones['Archivo ZIP'] = {'estado': 'pendiente', 'mensaje': 'Cargue un archivo ZIP'}
        else:
            # Verificar extension
            nombre_archivo = archivo.name
            if nombre_archivo.lower().endswith('.zip'):
                zip_extension_valida = True
                archivo_bytes = archivo.read()
                archivo.seek(0)
            
                zip_processor = get_zip_processor()
                centros_red_completa = obtener_centros_con_red_por_red(red_seleccionada)
                codigos_red = [c.get('codigo') for c in centros_red_completa if c.get('codigo')]
                resultado = zip_processor.validar_zip(archivo_bytes, nombre_archivo, codigos_centros=codigos_red)
            
                # Semana/año que traen los NOMBRES de los archivos vs. los que
                # eligió el remitente (nunca se mira el contenido).
                chequeo_periodo = (
                    zip_processor.validar_periodo(resultado, semana_seleccionada, ano_seleccionado, semanas_disponibles)
                    if resultado['estado'] in ('ok', 'observacion') else None
                )

                # Códigos de centro de los nombres vs. la red elegida: un ZIP de otra
                # red (o mezclado) no se acepta, y se explica qué corregir.
                chequeo_red = (
                    validar_red_zip(resultado, red_seleccionada)
                    if resultado['estado'] in ('ok', 'observacion') else None
                )
                bloqueos = []
                if chequeo_red is not None and not chequeo_red['ok']:
                    bloqueos.append(('red', chequeo_red['mensaje'], 'El ZIP no corresponde a la red elegida'))
                if chequeo_periodo is not None and not chequeo_periodo['ok']:
                    bloqueos.append(('periodo', chequeo_periodo['mensaje'], 'Semana/año del ZIP no coinciden'))

                if bloqueos:
                    zip_valido = False
                    validaciones['Archivo ZIP'] = {'estado': 'error', 'mensaje': '; '.join(b[2] for b in bloqueos)}
                    for _, texto, _ in bloqueos:
                        st.error(texto)
                    # Si todos los archivos son de UNA misma semana, un clic corrige el formulario.
                    pu = chequeo_periodo.get('periodo_unico') if chequeo_periodo else None
                    if pu and pu[1] in anos and pu[0] in (obtener_semanas_disponibles_por_anio(pu[1]) or []):
                        st.button(
                            f"Usar semana {pu[0]}/{pu[1]}",
                            key="btn_usar_periodo_zip",
                            on_click=_usar_periodo_del_zip, args=(pu[0], pu[1]),
                        )
                elif resultado['estado'] == 'ok' or resultado['estado'] == 'observacion':
                    zip_valido = True
                    info_zip = resultado
                    validaciones['Archivo ZIP'] = {'estado': 'ok', 'mensaje': 'Archivo ZIP válido'}
                    if resultado['estado'] == 'observacion':
                        st.warning(f"Advertencia: {resultado['mensaje']}")
                    else:
                        st.success(f"Archivo ZIP válido: {resultado['mensaje']}")
                
                    # Si los centros que el ZIP realmente trae no coinciden
                    # con los que el usuario seleccionó arriba en "Centro(s)
                    # Asistencial(es)", se ajusta automáticamente la
                    # selección para que coincida -- así, si alguien
                    # seleccionó todos los centros "por si acaso" pero el
                    # ZIP solo trae algunos, no hace falta corregirlo a mano.
                    # Aviso simple (sin bloquear) si el ZIP trae algún
                    # código numérico que no pertenece a ningún centro de
                    # la red seleccionada -- señal de que puede ser el ZIP
                    # de otra red.
                    codigos_fuera_de_red = resultado.get('codigos_fuera_de_red', [])
                    if codigos_fuera_de_red:
                        st.warning(
                            f"Revisa el archivo: trae código(s) ({', '.join(codigos_fuera_de_red)}) "
                            f"que no pertenecen a ningún centro de la red **{red_seleccionada}**. "
                            f"Verifica que sea el archivo correcto para esta red."
                        )

                    # Aviso informativo (no bloquea el envío): archivos con
                    # extensión real (xlsx/csv/dbf) cuyo nombre no trae el
                    # código del centro embebido -- no se puede confirmar
                    # automáticamente a qué centro pertenecen, así que se
                    # avisa para que el usuario verifique manualmente que
                    # seleccionó el/los centro(s) correcto(s) arriba. El
                    # administrador también verá esta observación al
                    # revisar el envío.
                    archivos_sin_centro = resultado.get('archivos_sin_centro_identificado', [])
                    if archivos_sin_centro:
                        st.info(
                            f"No se pudo identificar automáticamente el centro de "
                            f"{len(archivos_sin_centro)} archivo(s) ({', '.join(archivos_sin_centro[:3])}"
                            f"{'…' if len(archivos_sin_centro) > 3 else ''}). "
                            f"Verifica que hayas seleccionado el/los centro(s) correcto(s) arriba; "
                            f"quedará anotado para que el administrador lo revise."
                        )

                    # Semana/año leídos de los nombres (ya coinciden con lo elegido).
                    if chequeo_periodo and chequeo_periodo['periodos']:
                        st.caption(
                            f"Semana y año leídos de los nombres de los archivos: "
                            f"{semana_seleccionada}/{ano_seleccionado} (coinciden con lo elegido)."
                        )
                    archivos_sin_tipo = resultado.get('archivos_sin_tipo', [])
                    if archivos_sin_tipo:
                        st.info(
                            f"{len(archivos_sin_tipo)} archivo(s) tienen un nombre libre "
                            f"({', '.join(archivos_sin_tipo[:3])}{'…' if len(archivos_sin_tipo) > 3 else ''}): "
                            f"no se puede comprobar su tipo ni su semana. Se aceptan y quedan anotados para la OIIS."
                        )

                    # Tipo de reporte: se completa solo con lo que traen los nombres
                    # (2ª letra: c = consulta externa, e = emergencia, h = hospitalización),
                    # igual que los centros. Si hay archivos de nombre libre se respeta
                    # además lo que el remitente ya había marcado.
                    tipos_zip = resultado.get('tipos_detectados', [])
                    if tipos_zip:
                        if archivos_sin_tipo:
                            objetivo_tipos = [t for t in tipos_reporte if t in (set(tipos_zip) | set(tipos_seleccionados))]
                        else:
                            objetivo_tipos = list(tipos_zip)
                        if set(objetivo_tipos) != set(tipos_seleccionados):
                            st.session_state['_tipos_auto_sync'] = objetivo_tipos
                            st.rerun(scope="fragment")

                    centros_detectados = resultado.get('centros_detectados', [])
                    if centros_detectados:
                        mapa_codigo_a_nombre = {
                            c.get('codigo'): formatear_centro_desde_dict(c)
                            for c in centros_red_completa if c.get('codigo')
                        }
                        # Códigos que SÍ se pueden seleccionar en el menú de
                        # arriba (ya excluye lo que el admin dio de baja).
                        codigos_disponibles_menu = {
                            extraer_codigo(c) for c in st.session_state.usuario_centros_disponibles
                            if extraer_codigo(c)
                        }
                        codigos_seleccionados = {
                            extraer_codigo(c) for c in centros_seleccionados if extraer_codigo(c)
                        }
                        codigos_zip = set(centros_detectados)

                        # De lo que trae el ZIP, separar lo que sí se puede
                        # auto-seleccionar de lo que está excluido -- intentar
                        # auto-seleccionar un centro excluido rompe el menú,
                        # porque no está entre sus opciones.
                        codigos_zip_disponibles = codigos_zip & codigos_disponibles_menu
                        codigos_zip_excluidos = codigos_zip - codigos_disponibles_menu

                        if codigos_zip_excluidos:
                            etiquetas_excluidos = [
                                mapa_codigo_a_nombre.get(cod, cod) for cod in sorted(codigos_zip_excluidos)
                            ]
                            st.warning(
                                f"El ZIP incluye archivos de {len(etiquetas_excluidos)} "
                                f"centro(s) marcado(s) como **excluido(s)** en el sistema: "
                                f"{', '.join(etiquetas_excluidos)}. Si ese centro ya volvió a "
                                f"estar activo, pide al administrador que lo reincorpore en "
                                f"\"Gestión de Exclusiones\" antes de que puedas seleccionarlo aquí."
                            )

                        if codigos_seleccionados != codigos_zip_disponibles and codigos_zip_disponibles:
                            nuevos_seleccionados = [
                                mapa_codigo_a_nombre[cod] for cod in sorted(codigos_zip_disponibles)
                                if cod in mapa_codigo_a_nombre
                            ]
                            if nuevos_seleccionados:
                                st.session_state['_centros_auto_sync'] = nuevos_seleccionados
                                st.info(
                                    f"El ZIP trae archivos de {len(nuevos_seleccionados)} "
                                    f"centro(s) distinto(s) a los que tenías seleccionados -- "
                                    f"se actualizó \"Centro(s) Asistencial(es)\" arriba para "
                                    f"que coincida con lo que realmente estás enviando."
                                )
                                st.rerun(scope="fragment")
                    
                        # Mostrar qué otros centros de la red siguen sin
                        # enviar nada esta semana (considerando también los
                        # envíos de otras personas, no solo este ZIP), para
                        # que quede claro de un vistazo qué falta.
                        try:
                            db_manager_check = get_db_manager()
                            semana_activa_check = Config.get_semana_actual()
                            anio_activo_check = Config.get_anio_actual()
                            envios_semana_red = db_manager_check.obtener_envios(
                                anio=anio_activo_check,
                                semana=semana_activa_check,
                                red=red_seleccionada,
                                limit=1000
                            )
                        except Exception:
                            envios_semana_red = []
                    
                        codigos_ya_enviados = set()
                        for envio in envios_semana_red or []:
                            for c in envio.get('centros', []) or []:
                                cod = c.get('codigo', '') if isinstance(c, dict) else extraer_codigo(str(c))
                                if cod:
                                    codigos_ya_enviados.add(cod.upper())
                    
                        codigos_disponibles = {
                            extraer_codigo(c) for c in st.session_state.usuario_centros_disponibles
                            if extraer_codigo(c)
                        }
                        codigos_cubiertos = {c.upper() for c in codigos_zip | codigos_ya_enviados}
                        codigos_pendientes = sorted(codigos_disponibles - codigos_cubiertos)
                    
                        if codigos_pendientes:
                            etiquetas_pendientes = [
                                mapa_codigo_a_nombre.get(cod, cod) for cod in codigos_pendientes
                            ]
                            st.info(
                                f"De la red **{red_seleccionada}**, con este envío aún "
                                f"quedarían **{len(etiquetas_pendientes)}** centro(s) sin "
                                f"reportar esta semana: {', '.join(etiquetas_pendientes)}."
                            )
                        else:
                            st.success(
                                f"Con este envío, la red **{red_seleccionada}** queda "
                                f"completa esta semana."
                            )
                else:
                    zip_valido = False
                    validaciones['Archivo ZIP'] = {'estado': 'error', 'mensaje': resultado['mensaje']}
                    st.error(f"Error: {resultado['mensaje']}")
            else:
                zip_extension_valida = False
                validaciones['Archivo ZIP'] = {'estado': 'error', 'mensaje': 'El archivo debe tener extensión .zip'}
                st.error("Error: El archivo seleccionado no tiene extensión .zip. Solo se permiten archivos ZIP.")
    
    # ============================================================
    # MOSTRAR RESUMEN DE VALIDACION
    # ============================================================
    
    campos_pendientes = []
    campos_con_error = []
    
    for campo, estado in validaciones.items():
        if estado['estado'] == 'pendiente':
            campos_pendientes.append(campo)
        elif estado['estado'] == 'error':
            campos_con_error.append(campo)
    
    if not campos_pendientes and not campos_con_error:
        mostrar_aviso("ok", "Todos los campos están completos.", "Puede enviar su reporte.")
    else:
        if campos_con_error:
            mostrar_aviso("bad", "Corrija los campos con error", ", ".join(campos_con_error))
        if campos_pendientes:
            mostrar_aviso("warn", "Campos pendientes", ", ".join(campos_pendientes))

    # ============================================================
    # FORMULARIO CON EL BOTON DE ENVIO
    # ============================================================
    
    todos_validos = all(v['estado'] == 'ok' for v in validaciones.values())
    
    # Verificar adicionalmente que el año este permitido
    if estado_envio.get('es_atrasado', False) and ("NO PERMITIDO" in estado_envio.get('mensaje', '') or "FUTURA NO PERMITIDA" in estado_envio.get('mensaje', '')):
        todos_validos = False
    
    with st.form("formulario_envio", clear_on_submit=False):
        
        # Mensajes informativos
        if not todos_validos and archivo is not None and not zip_extension_valida:
            mostrar_aviso(
                "bad", "Formato no válido",
                "El archivo seleccionado no es un ZIP. Empaquete sus archivos en formato ZIP y vuelva a intentarlo."
            )
        elif not todos_validos and archivo is None:
            mostrar_aviso(
                "info", "Requisito para el envío",
                "Cargue un archivo en formato ZIP para habilitar el botón de envío. "
                "Empaquete todos sus archivos en un único archivo ZIP antes de continuar."
            )

        with st.container(key="sec_5"):
            seccion(5, "Observación (opcional)")
            sugerir = bool(estado_envio.get('es_atrasado')) or bool(info_zip and info_zip.get('archivos_sin_tipo'))
            st.caption(
                ("Su envío tiene algo que conviene explicar (por ejemplo, el motivo de un retraso o de nombres de archivo "
                 "distintos). " if sugerir else
                 "Si desea dejar un comentario a la OIIS sobre este envío, escríbalo aquí. ")
                + "Es opcional y no impide el envío. **No incluya datos de pacientes ni datos personales.**"
            )
            sustento = st.text_area(
                "Observación",
                key="input_sustento",
                max_chars=1000,
                height=96,
                label_visibility="collapsed",
                placeholder="Escriba aquí su observación (máximo 1000 caracteres)…"
            )

        enviar = st.form_submit_button(
            "Enviar reporte",
            disabled=not todos_validos,
            use_container_width=True,
            type="primary"
        )
        
        if enviar:
            if todos_validos:
                # Estandarizar nombres antes de guardar
                nombres_estandarizado = estandarizar_nombre(nombres)
                apellidos_estandarizado = estandarizar_nombre(apellidos)

                if info_zip is None:
                    archivo_bytes = archivo.read()
                    archivo.seek(0)
                    zip_processor = get_zip_processor()
                    codigos_red = [c.get('codigo') for c in obtener_centros_con_red_por_red(red_seleccionada) if c.get('codigo')]
                    info_zip = zip_processor.validar_zip(archivo_bytes, archivo.name, codigos_centros=codigos_red)

                # ============================================================
                # VERIFICACION DE POSIBLE ENVIO DUPLICADO
                # ============================================================
                # Si ya existe un envío registrado esta semana para la misma
                # red que incluya alguno de estos mismos centros, se avisa
                # antes de continuar -- para evitar reenvíos accidentales
                # (doble clic, recarga de página, otra persona de la red que
                # ya lo mandó, etc.). No es un bloqueo: el usuario decide.
                # Primero se clasifica archivo por archivo (centro + tipo c/e/h): lo ya
                # recibido va a duplicados y lo nuevo al envío normal. Si los nombres no
                # permiten verificarlo, rige la regla anterior (centros del formulario).
                plan = clasificar_envio(red_seleccionada, ano_seleccionado, semana_seleccionada, info_zip)
                if plan['modo'] == 'legacy':
                    duplicado = verificar_envio_duplicado(
                        red_seleccionada, centros_seleccionados, ano_seleccionado, semana_seleccionada
                    )
                elif plan['modo'] in ('todo_duplicado', 'dividir'):
                    duplicado = plan['duplicado_info']
                else:
                    duplicado = None

                if duplicado:
                    st.session_state['_dup_envio_pendiente'] = {
                        'duplicado_info': duplicado,
                        'nombres': nombres_estandarizado,
                        'apellidos': apellidos_estandarizado,
                        'correo': correo,
                        'red': red_seleccionada,
                        'centros': centros_seleccionados,
                        'ano': ano_seleccionado,
                        'semana': semana_seleccionada,
                        'tipos': tipos_seleccionados,
                        'archivo': archivo,
                        'info_zip': info_zip,
                        'estado_envio': estado_envio,
                        'plan': plan,
                        'sustento': (sustento or '').strip()
                    }
                    # Rerun COMPLETO (sin scope="fragment"): el modal de
                    # confirmación se muestra en mostrar_formulario(), fuera
                    # de este fragmento, así que hace falta que se vuelva a
                    # ejecutar todo el script para que aparezca.
                    st.rerun()
                else:
                    with st.spinner("Procesando envío..."):
                        procesar_envio(
                            nombres=nombres_estandarizado,
                            apellidos=apellidos_estandarizado,
                            correo=correo,
                            red=red_seleccionada,
                            centros=centros_seleccionados,
                            ano=ano_seleccionado,
                            semana=semana_seleccionada,
                            tipos=tipos_seleccionados,
                            archivo=archivo,
                            info_zip=info_zip,
                            estado_envio=estado_envio,
                            plan=plan,
                            sustento=(sustento or '').strip()
                        )
            else:
                st.error("No se puede enviar. Corrija los errores antes de continuar.")

    return red_seleccionada


def _reiniciar_envio():
    st.session_state.usuario_envio_exitoso = False
    st.session_state.usuario_datos_envio = {}
    st.session_state.usuario_red_seleccionada = None
    st.session_state.usuario_centros_disponibles = []
    st.session_state.usuario_autocompletado = None
    st.session_state.pop('_dup_envio_pendiente', None)
    st.session_state.pop('input_sustento', None)


def mostrar_confirmacion():
    """Muestra la confirmación del envío exitoso."""

    aplicar_tema()

    datos = st.session_state.usuario_datos_envio

    # El envío salió bien: el navegador recuerda a esta persona para la próxima vez.
    if datos.get('correo') and datos.get('codigo'):
        frecuentes.guardar_tras_envio(
            datos.get('nombres', ''), datos.get('apellidos', ''), datos.get('correo', ''), str(datos.get('codigo')))

    semana_actual_sistema = Config.get_semana_actual()
    anio_actual_sistema = Config.get_anio_actual()

    encabezado_publico("enviar")

    # El reporte ya quedó registrado (eso no depende del correo), pero si el
    # acuse de recibo falló al enviarse se avisa para que no sea una sorpresa.
    hora_envio = datos.get('hora_envio') or datetime.now()
    hora_envio_str = hora_envio.strftime('%d/%m/%Y %H:%M:%S')
    fecha_limite = datos.get('fecha_limite')
    fecha_corte_str = fecha_limite.strftime('%d/%m/%Y %H:%M') if fecha_limite else 'No configurada'
    sem = datos.get('semana', 'N/A')
    anio = datos.get('ano', 'N/A')

    estado = datos.get('estado')
    atrasado = bool(datos.get('es_atrasado', False)) or estado == 'ATRASADO'
    codigo_txt = sanitizar_html(str(datos.get('codigo', '')))
    migas = "Inicio / Enviar reporte / Confirmación"

    es_duplicado = bool(datos.get('es_duplicado', False))

    # ---- Resultado: duplicado (naranja), a tiempo (azul), tardío (rojo) u observado (ámbar) ----
    if es_duplicado:
        previos = ", ".join(sanitizar_html(str(x)) for x in datos.get('codigos_previos', []) if x)
        hero_acuse("naranja", "Reporte recibido como duplicado",
                   "Este centro ya había sido enviado en la semana indicada"
                   + (f" (envío previo: {previos})" if previos else "")
                   + ". Su archivo se guardó en una carpeta aparte, no reemplaza al anterior y la OIIS lo revisará.",
                   codigo_txt, migas)
        chip_estado = chip("Envío duplicado", "dup", "alerta")
    elif atrasado:
        extra = [f"Semana {sem}/{anio}, ya vencida.", f"Fecha de corte: {fecha_corte_str}."]
        if datos.get('semanas_atraso', 0) > 0:
            extra.append(f"Semanas de atraso: {datos['semanas_atraso']}.")
        if datos.get('dias_atraso', 0) > 0:
            extra.append(f"Días de atraso: {datos['dias_atraso']}.")
        hero_acuse("rojo", "Reporte recibido fuera de plazo",
                   "Su envío quedó registrado como tardío. " + " ".join(extra), codigo_txt, migas)
        chip_estado = chip("Envío tardío", "bad", "reloj")
    elif estado == 'OBSERVADO':
        hero_acuse("ambar", "Reporte recibido con observaciones",
                   "Su envío quedó registrado, pero requiere revisión. Conserve el código de seguimiento como constancia.",
                   codigo_txt, migas)
        mostrar_aviso("warn", "Observación", sanitizar_html(str(datos.get('observacion') or '')))
        chip_estado = chip("Recibido con observaciones", "warn", "alerta")
    else:
        hero_acuse("azul", "Reporte recibido correctamente",
                   "Su envío quedó registrado dentro del plazo establecido. Conserve el código de seguimiento como constancia.",
                   codigo_txt, migas)
        chip_estado = chip("Recibido a tiempo", "ok", "check")

    parte_dup = datos.get('parte_duplicada')
    if parte_dup:
        mostrar_aviso(
            "warn", "Una parte de su ZIP ya estaba recibida",
            f"{parte_dup['archivos']} archivo(s) de {sanitizar_html('; '.join(parte_dup['detalle']))} se guardaron "
            f"como <strong>duplicado</strong> (código <strong>{sanitizar_html(str(parte_dup['codigo']))}</strong>); "
            f"no reemplazan al envío anterior y la OIIS los revisará. Lo demás quedó registrado en este envío."
        )

    rep = datos.get('reemplazo')
    if rep:
        if rep['reemplazados']:
            cods = ', '.join(sanitizar_html(str(r['codigo'])) for r in rep['reemplazados'])
            mostrar_aviso(
                "info", "Envío anterior reemplazado",
                f"Este envío reemplazó a: <strong>{cods}</strong>. Los archivos anteriores no se borraron: "
                f"quedaron guardados en la carpeta REEMPLAZADOS."
            )
        if rep['fallos']:
            mostrar_aviso(
                "info", "Reemplazo en proceso",
                "Su envío nuevo quedó registrado correctamente. La OIIS completará el reemplazo del envío anterior; "
                "usted no necesita hacer nada más."
            )

    if datos.get('sustento'):
        mostrar_aviso("info", "Su observación quedó registrada", sanitizar_html(str(datos['sustento'])))

    if datos.get('correo_enviado') is False:
        mostrar_aviso(
            "warn",
            "No se pudo enviar el correo del acuse",
            "Su reporte quedó registrado correctamente. Guarde el código de seguimiento "
            "como comprobante y avise a la OIIS si esto se repite."
        )

    if atrasado and not es_duplicado and datos.get('observacion'):
        mostrar_aviso("warn", "Detalle", sanitizar_html(str(datos['observacion'])))

    esc = lambda v: sanitizar_html(str(v))
    col_res, col_lat = st.columns([2.1, 1], gap="large")

    with col_res:
        filas_det = [
            ("Red asistencial", esc(datos.get('red', ''))),
            ("Centros", esc(', '.join(datos.get('centros', [])))),
            ("Año y semana", f"{esc(anio)} · Semana epidemiológica {esc(sem)}"),
            ("Tipos de reporte", esc(', '.join(_tipo_visible(t) for t in datos.get('tipos', [])))),
            ("Archivos incluidos", esc(datos.get('cantidad_archivos', ''))),
            ("Fecha de envío", hora_envio_str),
            ("Fecha de corte", fecha_corte_str),
            ("Estado", chip_estado),
        ]
        mostrar(
            '<div class="sire-panel">'
            + detalle(filas_det)
            + '</div>'
        )
        mostrar(tarjeta("Remitente", filas([
            ("Apellidos y nombres", f"{esc(datos.get('apellidos', ''))} {esc(datos.get('nombres', ''))}"),
            ("Correo", esc(datos.get('correo', ''))),
        ])))

    with col_lat:
        if datos.get('correo_enviado') is not False:
            mostrar_aviso("info", "Acuse de recibo enviado", f"Se envió a <strong>{esc(datos.get('correo', ''))}</strong>.")
        mostrar(tarjeta("Semana en curso", filas([
            ("Semana activa", f"{semana_actual_sistema} · {anio_actual_sistema}"),
            ("Fecha límite", fecha_corte_info()[0]),
        ])))
        if st.button("Realizar nuevo envío", key="btn_nuevo_envio", type="primary", use_container_width=True):
            _reiniciar_envio()
            st.rerun()
        if st.button("Ver el progreso de mi red", key="btn_ver_progreso_red", use_container_width=True):
            _reiniciar_envio()
            st.session_state.pagina = 'red_progreso'
            st.rerun()

    pie_pagina()


def main():
    """Función principal de la página."""

    # La configuración de página (título, ícono, ancho) la fija app.py.
    init_session_state()

    if st.session_state.usuario_envio_exitoso:
        mostrar_confirmacion()
    else:
        mostrar_formulario()


if __name__ == "__main__":
    main()
