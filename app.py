# app.py
"""
Punto de entrada principal de SIREA (Sistema de Recepción de Reportes
Epidemiológicos) - EsSalud / OIIS.
Portada con acceso al envío de reportes, al progreso de cada red y al
panel de administración.
"""

import streamlit as st
from src.config import Config
from src.db_manager import get_db_manager
from src.data_loader import get_data_loader
from src.logging_config import configurar_logging, obtener_logger
from utils.avance import avance_nacional
from utils.helpers import sanitizar_html
from utils.tema import (
    aplicar_tema, encabezado_publico, pie_pagina, mostrar, icono, logo_uri,
    ruta_favicon, periodo_semana, fecha_corte_info, texto_dias_restantes,
    fecha_larga_es, correo_contacto,
)

# Configura el logging del proceso (archivo rotativo en storage/logs/ +
# consola) una sola vez, antes de que cualquier otro módulo escriba
# logs. Ver src/logging_config.py.
configurar_logging()
logger = obtener_logger(__name__)


# ============================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================

def configurar_pagina():
    """Configura la página (título de pestaña, ícono y ancho)."""
    st.set_page_config(
        page_title="SIREA · Recepción de Reportes Epidemiológicos - EsSalud",
        page_icon=ruta_favicon(),
        layout="wide",
        initial_sidebar_state="collapsed"
    )


# ============================================================
# NOTA: la semana activa y la fecha de corte se obtienen
# directamente de Config.get_semana_actual() / Config.get_fecha_corte(),
# que ya centralizan la lectura desde Supabase con fallback a .env.
# (antes había una copia local de estas funciones en cada página,
# con fallbacks distintos e inconsistentes entre sí)
# ============================================================


# ============================================================
# ESTILOS DE LA PORTADA (el tema general vive en utils/tema.py)
# ============================================================

def _css_portada() -> str:
    """Marca de agua de la OIIS en la cabecera del inicio (imagen incrustada)."""
    marca = logo_uri("oiis-blanco.svg")
    return f"""
<style>
.st-key-sire_hero::after{{
  content:""; position:absolute; right:-110px; bottom:-150px; width:520px; height:520px; opacity:.09; pointer-events:none;
  background:url("{marca}") no-repeat center / contain;
}}
</style>
"""


_PAGINAS = ('landing', 'usuario', 'admin', 'red_progreso')


def init_session_state():
    """Inicializa las variables de sesión."""
    if 'pagina' not in st.session_state:
        # SIREA 3.3: al refrescar (F5) se vuelve a la misma pantalla (se recuerda en la dirección: ?p=…)
        try:
            p = st.query_params.get("p")
        except Exception:
            p = None
        st.session_state.pagina = p if p in _PAGINAS else 'landing'
    if 'seccion_admin' not in st.session_state:
        st.session_state.seccion_admin = 'Dashboard'


# ============================================================
# MOSTRAR LANDING PAGE
# ============================================================

def _ir_a(pagina: str):
    st.session_state.pagina = pagina
    st.rerun()


def _mensaje_plazo(dt, dias: str) -> str:
    """Texto breve sobre el plazo de la semana (para el pie de la tarjeta de avance)."""
    if dt is None:
        return "La fecha de corte de esta semana aún no está definida"
    if dias == "plazo vencido":
        return "El plazo de envío venció: los envíos nuevos se registran como tardíos"
    if dias == "vence hoy":
        return "La fecha de corte vence hoy"
    return f"{dias.capitalize()} para la fecha de corte"


def mostrar_landing():
    """Inicio: semana activa, avance nacional y accesos a cada perfil."""

    aplicar_tema()
    st.markdown(_css_portada(), unsafe_allow_html=True)
    init_session_state()

    semana_actual = Config.get_semana_actual()
    anio_actual = Config.get_anio_actual()
    corte_txt, corte_dt = fecha_corte_info()
    dias = texto_dias_restantes(corte_dt)
    periodo = periodo_semana(anio_actual, semana_actual)
    av = avance_nacional(anio_actual, semana_actual)

    encabezado_publico("inicio")

    # ---------- Cabecera con el avance nacional ----------
    vencido = dias == "plazo vencido"
    if corte_dt is None:
        chip_txt, chip_cls = "Recepción abierta · fecha de corte por definir", ""
    elif vencido:
        chip_txt, chip_cls = f"Plazo vencido · corte: {fecha_larga_es(corte_dt)}", " cerrada"
    else:
        chip_txt, chip_cls = f"Recepción abierta · corte: {fecha_larga_es(corte_dt)}", ""

    with st.container(key="sire_hero"):
        col_txt, col_av = st.columns([1.05, 1], gap="large", vertical_alignment="center")
        with col_txt:
            mostrar(f"""
            <span class="sire-hero-chip{chip_cls}"><i></i>{chip_txt}</span>
            <div class="sire-hero-per">{periodo if periodo != '—' else f'Año {anio_actual}'}</div>
            <h1 class="sire-hero-h1">Semana epidemiológica {semana_actual}</h1>
            <p class="sire-hero-p">Envíe el reporte semanal de su red asistencial, reciba su acuse de recibo por correo
            al instante y siga el avance de sus centros.</p>
            """)
            b1, b2 = st.columns([1, 1.5])
            with b1:
                if st.button("Enviar reporte", key="hero_enviar", type="primary", use_container_width=True):
                    _ir_a('usuario')
            with b2:
                if st.button("Ver el progreso de mi red", key="hero_progreso", use_container_width=True):
                    _ir_a('red_progreso')

        with col_av:
            if av:
                pct = av["pct"]
                cifras = (av["redes_completas"], av["redes_proceso"], av["redes_sin_envio"])
                pie = f"{_mensaje_plazo(corte_dt, dias)} · {av['enviados']} de {av['total']} centros ya enviaron"
            else:
                pct, cifras = 0, ("—", "—", "—")
                pie = "El avance de la semana no está disponible por el momento."
            mostrar(f"""
            <div class="sire-glass" role="region" aria-label="Avance nacional de la semana">
              <div class="sire-glass-top">
                <div><span class="sire-glass-k">Avance nacional</span><span class="sire-glass-s">Centros con reporte recibido</span></div>
                <span class="sire-glass-pct">{pct if av else '—'}{' %' if av else ''}</span>
              </div>
              <div class="sire-glass-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:{pct}%"></i></div>
              <div class="sire-glass-3">
                <div><b>{cifras[0]}</b><span>redes al 100 %</span></div>
                <div><b>{cifras[1]}</b><span>en proceso</span></div>
                <div><b>{cifras[2]}</b><span>sin envíos aún</span></div>
              </div>
              <p class="sire-glass-pie">{pie}</p>
            </div>
            """)

    # ---------- Accesos ----------
    mostrar("""
    <h2 class="sire-seccion-t">¿Qué desea hacer?</h2>
    <p class="sire-seccion-s">Elija la opción que corresponda a su perfil.</p>
    """)

    col1, col2, col3 = st.columns(3, gap="medium")

    with col1, st.container(key="op_1"):
        mostrar(f"""
        <div class="sire-op">
          <div class="sire-op-ico" style="background:#E3F0FA">{icono('subir', 26, '#0077C8')}</div>
          <p class="sire-op-eye">Para redes asistenciales</p>
          <h3>Enviar reporte</h3>
          <p>Cargue el archivo ZIP de su red con los reportes de la semana. Al terminar recibe su código de seguimiento.</p>
        </div>
        """)
        if st.button("Ir a enviar  →", key="btn-usuario"):
            _ir_a('usuario')

    with col2, st.container(key="op_2"):
        mostrar(f"""
        <div class="sire-op">
          <div class="sire-op-ico" style="background:#E6F4EA">{icono('barras', 26, '#1E6B3A')}</div>
          <p class="sire-op-eye">Para redes asistenciales</p>
          <h3>Mi progreso</h3>
          <p>Vea qué centros de su red ya reportaron, cuáles faltan y su historial semana a semana. Acceso con la contraseña de su red.</p>
        </div>
        """)
        if st.button("Ver mi progreso  →", key="btn-red-progreso"):
            _ir_a('red_progreso')

    with col3, st.container(key="op_3"):
        mostrar(f"""
        <div class="sire-op">
          <div class="sire-op-ico" style="background:#E6ECF6">{icono('escudo', 26, '#1D3F76')}</div>
          <p class="sire-op-eye">Personal de la OIIS</p>
          <h3>Panel de administración</h3>
          <p>Seguimiento nacional, atrasos, duplicados y notificaciones a las redes. Solo para personal autorizado.</p>
        </div>
        """)
        if st.button("Ingresar al panel  →", key="btn-admin"):
            st.session_state.pagina = 'admin'
            st.session_state.seccion_admin = 'Dashboard'
            st.rerun()

    # ---------- Cómo funciona / plazos ----------
    st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
    c_a, c_b = st.columns(2, gap="medium")
    with c_a:
        mostrar("""
        <div class="sire-tarjeta2">
          <h2>Cómo funciona</h2>
          <p class="sub">Cuatro pasos, de la preparación al acuse.</p>
          <div class="sire-paso"><b>1</b><div><h3>Prepare un archivo ZIP</h3><p>Con los reportes de los centros de su red en formato xlsx, csv, xls o dbf.</p></div></div>
          <div class="sire-paso"><b>2</b><div><h3>Registre el envío</h3><p>Indique su red, los centros, el tipo de reporte, la semana y la persona responsable.</p></div></div>
          <div class="sire-paso"><b>3</b><div><h3>Reciba el acuse por correo</h3><p>Llega con el código de seguimiento y el detalle de lo enviado.</p></div></div>
          <div class="sire-paso" style="margin-bottom:0"><b>4</b><div><h3>Compruebe su avance</h3><p>En «Mi progreso» verá los centros enviados y pendientes de su red.</p></div></div>
        </div>
        """)
    with c_b:
        corte_frase = (
            f"Esta semana: {fecha_larga_es(corte_dt)} (hora de Lima)." if corte_dt is not None
            else "Esta semana aún no tiene una fecha definida."
        )
        contacto = correo_contacto()
        contacto_html = (
            f'<p class="sub" style="margin:auto 0 0;padding-top:16px;border-top:1px solid #EAF1F8">'
            f'Consultas: <a href="mailto:{sanitizar_html(contacto)}" style="font-weight:800">{sanitizar_html(contacto)}</a></p>'
            if contacto else ""
        )
        mostrar(f"""
        <div class="sire-tarjeta2" style="display:flex;flex-direction:column">
          <h2>Plazos y recordatorios</h2>
          <p class="sub">Qué esperar de la semana en curso.</p>
          <div class="sire-plazo"><span style="background:#E3F0FA">{icono('calendario', 20, '#0077C8', 2.2)}</span>
            <div><h3>Fecha de corte</h3><p>La define la OIIS cada semana. {corte_frase}</p></div></div>
          <div class="sire-plazo"><span style="background:#FFF4D6">{icono('campana', 20, '#7A5A00', 2.2)}</span>
            <div><h3>Recordatorio preventivo</h3><p>Las redes con centros pendientes reciben un correo antes de la fecha de corte.</p></div></div>
          <div class="sire-plazo"><span style="background:#FDE8E8">{icono('reloj', 20, '#9E2B2B', 2.2)}</span>
            <div><h3>Envíos tardíos</h3><p>Los envíos posteriores a la fecha de corte se registran como tardíos y el acuse lo indica con una cabecera roja.</p></div></div>
          {contacto_html}
        </div>
        """)

    # ---------- Franja de confianza + pie ----------
    mostrar(f"""
    <div class="sire-franja">
      <span>{icono('candado', 18, '#0077C8', 2.2)}Acceso con contraseña por red</span>
      <span>{icono('correo', 18, '#0077C8', 2.2)}Acuse de recibo por correo</span>
      <span>{icono('nube', 18, '#0077C8', 2.2)}Respaldo de archivos en Google Drive</span>
    </div>
    """)
    pie_pagina()


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    """Función principal de la aplicación."""

    configurar_pagina()

    # Si falta la configuración crítica (Supabase), detener aquí con un
    # mensaje claro en vez de dejar que cada página falle por separado
    # con errores confusos de la librería de Supabase.
    errores_criticos = Config.validar_critico()
    if errores_criticos:
        st.error("⚠️ El sistema no puede iniciar: falta configuración crítica")
        for error in errores_criticos:
            st.error(f"• {error}")
        st.info("Revise el archivo `.env` del proyecto y verifique esas variables.")
        st.stop()

    init_session_state()
    try:
        actual = st.query_params.get("p")
        if st.session_state.pagina == 'landing':
            if actual:
                st.query_params.clear()
        elif actual != st.session_state.pagina:
            st.query_params["p"] = st.session_state.pagina
    except Exception:
        pass

    if st.session_state.pagina == 'usuario':
        try:
            from app_pages.usuario import main as usuario_main
            usuario_main()
        except ImportError as e:
            logger.error("Fallo al importar app_pages/usuario.py: %s", e, exc_info=True)
            st.error("No se pudo cargar la página de usuario. Intenta nuevamente en unos minutos.")
            if st.button("Volver al inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()
        except Exception as e:
            # No se muestra el traceback al usuario final (puede revelar
            # rutas internas, nombres de variables, etc.) -- queda en el
            # log del servidor para diagnóstico.
            logger.exception("Error inesperado en la página de usuario")
            st.error("Ocurrió un error inesperado al procesar su solicitud. Por favor, intente nuevamente.")
            if st.button("Volver al inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()

    elif st.session_state.pagina == 'admin':
        try:
            from app_pages.admin import main as admin_main
            admin_main()
        except ImportError as e:
            logger.error("Fallo al importar app_pages/admin.py: %s", e, exc_info=True)
            st.error("No se pudo cargar el panel de administración. Intenta nuevamente en unos minutos.")
            if st.button("Volver al inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()
        except Exception as e:
            logger.exception("Error inesperado en el panel de administración")
            st.error("Ocurrió un error inesperado en el panel de administración. Por favor, intente nuevamente.")
            if st.button("Volver al inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()
    elif st.session_state.pagina == 'red_progreso':
        try:
            from app_pages.red_login import main as red_login_main
            red_login_main()
        except ImportError as e:
            logger.error("Fallo al importar app_pages/red_login.py: %s", e, exc_info=True)
            st.error("No se pudo cargar el acceso por red. Intenta nuevamente en unos minutos.")
            if st.button("Volver al inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()
        except Exception as e:
            logger.exception("Error inesperado en el login de red")
            st.error("Ocurrió un error inesperado. Por favor, intente nuevamente.")
            if st.button("Volver al inicio"):
                st.session_state.pagina = 'landing'
                st.rerun()
    else:
        mostrar_landing()


if __name__ == "__main__":
    main()