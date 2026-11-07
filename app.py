# app.py
"""
Punto de entrada principal de SIREA (Sistema de Recepción de Reportes
Epidemiológicos) - EsSalud / OIIS.
Portada con acceso al envío de reportes, al progreso de cada red y al
panel de administración.
"""

import re

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
    fecha_larga_es, correo_contacto, quipu_semanas, _CSS_SIREA_BANDA,
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
    """Estilos de la portada: banda azul corporativa con el búho de la OIIS de marca de agua y fichas de cristal."""
    marca = logo_uri("oiis-blanco.svg")
    return f"""
<style>
/* banda a todo el ancho: encabezado + cabecera */
.st-key-sire_banda{{
  position:relative; isolation:isolate; overflow:hidden; color:#FFFFFF;
  width:100vw !important; max-width:100vw !important; margin-left:calc(50% - 50vw) !important; margin-bottom:0;
  padding:0 clamp(20px, 4vw, 72px) 0 !important;
  background:
    radial-gradient(900px 480px at 82% 18%, rgba(65,182,230,.50) 0%, rgba(65,182,230,0) 60%),
    radial-gradient(760px 480px at 0% 100%, rgba(10,60,120,.50) 0%, rgba(10,60,120,0) 65%),
    linear-gradient(135deg, #005C9C 0%, #0077C8 45%, #13213A 100%);
}}
.st-key-sire_banda::before{{
  content:""; position:absolute; z-index:-1; right:-90px; top:70px; width:min(780px,62vw); aspect-ratio:1296/1176; opacity:.13; pointer-events:none;
  background:url("{marca}") no-repeat center / contain;
}}
.st-key-sire_banda::after{{
  content:""; position:absolute; z-index:-1; inset:0; pointer-events:none;
  background:linear-gradient(112deg, rgba(255,255,255,.16) 0%, rgba(255,255,255,.05) 30%, rgba(255,255,255,0) 31%);
}}
/* encabezado sobre el azul */
.st-key-sire_banda .st-key-sire_hdr::before{{ background:transparent; border:0; }}
.st-key-sire_banda .sire-brand-essalud{{ filter:brightness(0) invert(1); }}
.st-key-sire_banda .sire-brand-sep{{ background:rgba(255,255,255,.45); }}
.st-key-sire_banda .sire-brand-txt b{{ color:#FFFFFF; }}
.st-key-sire_banda .sire-brand-txt b .sire-a{{ color:#D9C7F2; }}
.st-key-sire_banda .sire-brand-txt small{{ color:#E3F0FA; }}
.st-key-sire_banda .sire-brand svg rect:first-child{{ fill:#FFFFFF; }}
.st-key-sire_banda .sire-brand svg rect:nth-child(n+2){{ fill:#0077C8; }}
.st-key-sire_banda .sire-semana-chip{{ display:none; }}
.st-key-sire_banda .st-key-sire_hdr .stButton > button{{
  min-height:44px; padding:0 12px !important; white-space:nowrap; border-radius:999px !important; border:1px solid rgba(255,255,255,.55) !important; color:#FFFFFF !important;
  background:linear-gradient(135deg, rgba(255,255,255,.30), rgba(255,255,255,.10)) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.55), 0 6px 16px rgba(10,60,120,.18) !important; backdrop-filter:blur(10px); font-weight:700 !important;
}}
.st-key-sire_banda .st-key-sire_hdr .stButton > button *{{ color:#FFFFFF !important; }}
.st-key-sire_banda .st-key-sire_hdr .stButton > button:hover{{ background:linear-gradient(135deg, rgba(255,255,255,.42), rgba(255,255,255,.18)) !important; color:#FFFFFF !important; }}
.st-key-sire_banda .st-key-sire_hdr .stButton > button[kind="primary"]{{
  background:#FFFFFF !important; border-color:#FFFFFF !important; box-shadow:0 6px 16px rgba(10,60,120,.25) !important; }}
.st-key-sire_banda .st-key-sire_hdr .stButton > button[kind="primary"] *{{ color:#0077C8 !important; }}
.st-key-sire_banda .st-key-sire_hdr [class*="st-key-nav_pub_admin"] .stButton > button{{
  background:linear-gradient(135deg, #1D3F76, #13213A) !important; border-color:rgba(255,255,255,.45) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(10,60,120,.35) !important; }}
/* cabecera */
.st-key-sire_banda .st-key-sire_hero{{ background:transparent; box-shadow:none; border-radius:0; margin-top:0; padding:36px 0 132px !important; overflow:visible; }}
.st-key-sire_banda .sire-hero-chip{{ background:rgba(255,255,255,.20); border:1px solid rgba(255,255,255,.55); backdrop-filter:blur(10px); }}
.st-key-sire_banda .sire-hero-chip i{{ background:#8CF0B4; box-shadow:0 0 0 4px rgba(140,240,180,.3); }}
.st-key-sire_banda .sire-hero-chip.cerrada i{{ background:#FFB4B4; box-shadow:0 0 0 4px rgba(255,180,180,.3); }}
.sire-hero-semana{{ display:flex; flex-wrap:wrap; align-items:flex-end; gap:6px 20px; margin:8px 0 6px; }}
.sire-hero-num{{ font-size:clamp(110px,15vw,190px); font-weight:800; line-height:.8; letter-spacing:-.04em; text-shadow:0 12px 40px rgba(10,60,120,.35); }}
.sire-hero-semana > div{{ padding-bottom:6px; }}
.sire-hero-semana small{{ display:block; font-size:14px; font-weight:800; letter-spacing:0; text-transform:none; color:#DCE6FD; }}
.sire-hero-semana > div span{{ display:block; font-size:20px; font-weight:600; margin-top:4px; }}
.st-key-sire_banda .sire-hero-p{{ color:#EAF4FC; }}
.st-key-sire_banda .st-key-sire_hero .stButton > button[kind="secondary"]{{
  background:linear-gradient(135deg, rgba(255,255,255,.30), rgba(255,255,255,.10)) !important; border:1px solid rgba(255,255,255,.6) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.55) !important; backdrop-filter:blur(10px); }}
.st-key-sire_banda .st-key-sire_hero .stButton > button[kind="primary"]{{ color:#0077C8 !important; }}
/* mosaico de cristal */
.sire-mosaico{{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }}
.sire-cristal{{
  background:linear-gradient(112deg, rgba(255,255,255,.30) 0%, rgba(255,255,255,.08) 42%, rgba(255,255,255,.04) 43%, rgba(255,255,255,.14) 100%), rgba(10,60,120,.22);
  border:1px solid rgba(255,255,255,.5); box-shadow:inset 0 1px 0 rgba(255,255,255,.6), 0 20px 40px rgba(10,60,120,.28);
  backdrop-filter:blur(16px); border-radius:24px; padding:22px; color:#FFFFFF;
}}
.sire-cristal.ancho{{ grid-column:span 2; padding:26px; }}
.sire-cristal .k{{ font-size:13px; font-weight:800; letter-spacing:0; text-transform:none; color:#EAF4FC; display:block; }}
.sire-cristal .s{{ font-size:14px; color:#EAF4FC; }}
.sire-cristal .v{{ margin-top:8px; font-size:44px; font-weight:800; line-height:1; }}
.sire-cristal .v small{{ font-size:20px; font-weight:700; color:#EAF4FC; }}
.sire-cristal .top{{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; flex-wrap:wrap; }}
.sire-cristal .pct{{ margin-top:10px; font-size:64px; font-weight:800; line-height:1; }}
.sire-cristal .barra{{ margin-top:16px; height:12px; background:rgba(255,255,255,.28); border-radius:999px; overflow:hidden; }}
.sire-cristal .barra i{{ display:block; height:100%; background:linear-gradient(90deg,#FFC9B8,#FFFFFF); border-radius:999px; }}
.sire-cristal .pie{{ margin:12px 0 0; font-size:13.5px; color:#EAF4FC; }}
.sire-cristal .ok{{ color:#9AF5C0; }} .sire-cristal .ambar{{ color:#FFFFFF; }} .sire-cristal .rojo{{ color:#FFC2BB; }}
/* accesos: suben sobre la banda */
.st-key-sire_accesos{{ position:relative; z-index:2; margin-top:-84px; }}
[class*="st-key-op_"]{{ border-radius:24px !important; box-shadow:inset 0 6px 0 #0077C8, 0 24px 48px rgba(10,60,120,.20) !important; padding-top:30px !important; }}
.st-key-op_2{{ box-shadow:inset 0 6px 0 #1E6B3A, 0 24px 48px rgba(10,60,120,.20) !important; }}
.st-key-op_3{{ box-shadow:inset 0 6px 0 #1D3F76, 0 24px 48px rgba(10,60,120,.20) !important; }}
/* ---------- SIREA 3.5: portada con la cuerda de semanas ---------- */
.st-key-sire_banda .st-key-sire_hero{{ padding:44px 0 128px !important; }}
.sirea-hero h1{{ margin:22px 0 0 !important; padding:0 !important; color:#FFFFFF !important; font-size:clamp(38px,4.4vw,58px) !important;
  line-height:1.04 !important; font-weight:700 !important; letter-spacing:-.025em !important; max-width:15ch; }}
.sirea-hero-per{{ margin:16px 0 0 !important; color:#FFFFFF; font-weight:600; font-size:16px; }}
.sirea-hero-p{{ margin:14px 0 22px !important; color:#FFFFFF; font-size:17px; line-height:1.55; max-width:none; }}
.sirea-mosaico{{ display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; margin-top:10px; }}
.sirea-t{{ border-radius:14px; padding:20px 22px; display:flex; flex-direction:column; gap:6px; min-height:132px;
  background:#FFFFFF; color:#1D3F76; border-top:4px solid #0077C8; box-shadow:0 14px 34px rgba(0,30,70,.22); }}
.sirea-t p{{ color:#4B5875; }}
.sirea-t h2{{ margin:0 !important; padding:0 !important; font-family:'IBM Plex Sans', sans-serif !important; font-size:15px !important;
  font-weight:600 !important; letter-spacing:0 !important; color:inherit !important; }}
.sirea-t b{{ font-family:'Bricolage Grotesque', sans-serif; font-size:30px; font-weight:800; line-height:1.1; font-variant-numeric:tabular-nums; }}
.sirea-t p{{ margin:0 !important; font-size:14px; line-height:1.4; }}
.sirea-t-blanco{{ grid-column:1 / -1; flex-direction:row; align-items:center; gap:20px; min-height:0; }}
.sirea-t-blanco p{{ color:#3D5A80; }}
.sirea-t-verde{{ border-top-color:#41B6E6; }}
.sirea-t-celeste{{ border-top-color:#1D3F76; }}
.sirea-t-lila{{ grid-column:1 / -1; }}
.sirea-t-lila p{{ font-weight:600; }}
.sirea-t-lila.vencido{{ border-top-color:#B42318; }} .sirea-t-lila.vencido p{{ color:#9E2B2B; }}
.sirea-barra{{ height:12px; border-radius:99px; background:#E3F0FA; margin-top:14px; overflow:hidden; }}
.sirea-barra i{{ display:block; height:100%; border-radius:99px; background:linear-gradient(90deg, #0077C8, #41B6E6); }}
.sirea-barra-ley{{ display:flex; gap:22px; margin-top:10px; font-size:13.5px; font-weight:600; color:#3D5A80; }}
.sirea-barra-ley span{{ display:inline-flex; align-items:center; gap:8px; }}
.sirea-barra-ley i{{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
.sirea-anillo{{ flex:none; width:112px; height:112px; border-radius:50%; display:grid; place-items:center; }}
.sirea-anillo span{{ width:84px; height:84px; border-radius:50%; background:#FFFFFF; display:flex; align-items:baseline; justify-content:center; padding-top:22px; box-sizing:border-box; gap:1px;
  font-family:'Bricolage Grotesque', sans-serif; color:#1D3F76; font-size:18px; font-weight:700; }}
.sirea-anillo span b{{ font-size:32px; font-weight:800; line-height:1; }}
.sirea-quipu-banda{{ margin-top:34px; }}
.st-key-sire_accesos{{ margin-top:-72px !important; }}
[class*="st-key-op_"]{{ border-radius:14px !important; border:1px solid #D6E2EE !important; border-top:4px solid #0077C8 !important;
  box-shadow:0 10px 26px rgba(0,50,100,.10) !important; background:#FFFFFF !important; }}
.st-key-op_2{{ border-top-color:#41B6E6 !important; }}
.st-key-op_3{{ border-top-color:#1D3F76 !important; }}
.sire-dos{{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:16px; align-items:stretch; }}
.sire-dos > .sire-tarjeta2{{ height:100%; box-sizing:border-box; margin:0 !important; }}
@media (max-width: 900px){{ .sire-dos{{ grid-template-columns:minmax(0,1fr); }} }}
[class*="st-key-op_"] h3{{ color:#1D3F76 !important; }}
.stApp .st-key-op_1 div.stButton > button{{ background:#0077C8 !important; border-color:#0077C8 !important; color:#FFFFFF !important; }}
.stApp .st-key-op_2 div.stButton > button{{ background:#0077C8 !important; border-color:#0077C8 !important; color:#FFFFFF !important; }}
.stApp .st-key-op_3 div.stButton > button{{ background:#FFFFFF !important; border:1.5px solid #0077C8 !important; color:#005C9C !important; }}
.stApp [class*="st-key-op_"] div.stButton > button *{{ color:inherit !important; }}
.stApp .st-key-sire_banda .st-key-sire_hero div.stButton > button[kind="primary"]{{ background:#FFFFFF !important; border-color:#FFFFFF !important; }}
.stApp .st-key-sire_banda .st-key-sire_hero div.stButton > button[kind="primary"] *{{ color:#004F85 !important; font-weight:700 !important; }}
.stApp .st-key-sire_banda .st-key-sire_hero div.stButton > button[kind="primary"]:hover{{ background:#EAF3FB !important; border-color:#EAF3FB !important; }}
.stApp [class*="st-key-op_"] div.stButton{{ width:100% !important; }}
.stApp [class*="st-key-op_"] div.stButton > button{{ width:100% !important; min-height:46px; font-weight:700 !important; }}
@media (max-width: 900px){{
  .st-key-sire_banda .st-key-sire_hero{{ padding-bottom:110px !important; }}
  .sire-cristal.ancho{{ grid-column:span 2; }}
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
    st.markdown(_css_portada() + _CSS_SIREA_BANDA, unsafe_allow_html=True)
    init_session_state()

    semana_actual = Config.get_semana_actual()
    anio_actual = Config.get_anio_actual()
    corte_txt, corte_dt = fecha_corte_info()
    dias = texto_dias_restantes(corte_dt)
    periodo = periodo_semana(anio_actual, semana_actual)
    av = avance_nacional(anio_actual, semana_actual)

    # ---------- Banda azul: encabezado + cabecera con el avance nacional ----------
    vencido = dias == "plazo vencido"
    if corte_dt is None:
        chip_txt, chip_cls = "Recepción abierta · fecha de corte por definir", ""
    elif vencido:
        chip_txt, chip_cls = f"Plazo vencido · corte: {fecha_larga_es(corte_dt)}", " cerrada"
    else:
        chip_txt, chip_cls = f"Recepción abierta · corte: {fecha_larga_es(corte_dt)}", ""

    # «Para el corte»: número grande + unidad (o texto si ya venció / vence hoy)
    m_dias = re.search(r"(\d+)\s+(días?|día)", dias or "")
    if m_dias:
        corte_val = f'{m_dias.group(1)}<small> {m_dias.group(2)}</small>'
    elif dias == "vence hoy":
        corte_val = "Hoy"
    elif vencido:
        corte_val = '<small>Vencido</small>'
    else:
        corte_val = "—"
    corte_cls = "rojo" if vencido else "ambar"

    try:
        from src.db_manager import get_db_manager
        total_semanas = int(get_db_manager().obtener_semanas_por_anio(anio_actual) or 52)
    except Exception:
        total_semanas = 52
    corte_corto = corte_dt.strftime("%d/%m/%Y %H:%M") if corte_dt else "por definir"

    with st.container(key="sire_banda"):
        encabezado_publico("inicio")
        with st.container(key="sire_hero"):
            col_txt, col_av = st.columns([1.15, 1], gap="large", vertical_alignment="top")
            with col_txt:
                mostrar(f"""
                <div class="sirea-hero">
                  <span class="sire-hero-chip{chip_cls}"><i></i>{chip_txt}</span>
                  <h1>Semana epidemiológica {semana_actual}</h1>
                  <p class="sirea-hero-per">{periodo if periodo != '—' else f'Año {anio_actual}'} · {_mensaje_plazo(corte_dt, dias)}</p>
                  <p class="sirea-hero-p">Envíe el reporte de su red y siga el avance de sus centros. El acuse de recibo, con su
                  código de seguimiento, le llega por correo al instante.</p>
                </div>
                """)
                b1, b2 = st.columns([1, 1.2])
                with b1:
                    if st.button("Enviar reporte", key="hero_enviar", type="primary", use_container_width=True):
                        _ir_a('usuario')
                with b2:
                    if st.button("Ver el progreso de mi red", key="hero_progreso", use_container_width=True):
                        _ir_a('red_progreso')

            with col_av:
                # SIREA 3.5: mosaico de colores. Cada bloque tiene su color y un texto que contrasta con él.
                dias_txt = str(dias).capitalize() if dias else "Por definir"
                if av:
                    pct = av["pct"]
                    anillo = (f'<div class="sirea-anillo" role="img" aria-label="Avance nacional {pct} %" '
                              f'style="background:conic-gradient(#0077C8 0 {pct}%, #E3F0FA {pct}% 100%)">'
                              f'<span><b>{pct}</b>%</span></div>')
                    centros = f"{av['enviados']} de {av['total']}"
                    barra = (f'<div class="sirea-barra" aria-hidden="true"><i style="width:{pct}%"></i></div>'
                             f'<div class="sirea-barra-ley"><span><i style="background:#0077C8"></i>{av["enviados"]} con reporte</span>'
                             f'<span><i style="background:#C9DDF0"></i>{max(0, av["total"] - av["enviados"])} pendientes</span></div>')
                    redes = f"{av['redes_completas']} completas"
                    redes_sub = f"{av['redes_proceso']} en proceso · {av['redes_sin_envio']} sin envíos"
                else:
                    anillo = '<div class="sirea-anillo" style="background:#E3F0FA"><span><b>—</b></span></div>'
                    centros, redes, redes_sub = "—", "—", "Aún sin datos de la semana"
                    barra = ""
                mostrar(f"""
                <section class="sirea-mosaico" aria-label="Avance nacional de la semana">
                  <div class="sirea-t sirea-t-blanco">
                    {anillo}
                    <div style="flex:1;min-width:0"><h2>Avance nacional</h2><p>centros con reporte sobre el total esperado</p>{barra}</div>
                  </div>
                  <div class="sirea-t sirea-t-verde"><h2>Centros con reporte</h2><b>{centros}</b><p>en todo el país</p></div>
                  <div class="sirea-t sirea-t-celeste"><h2>Redes</h2><b>{redes}</b><p>{redes_sub}</p></div>
                  <div class="sirea-t sirea-t-lila{' vencido' if dias == 'plazo vencido' else ''}"><h2>Fecha de corte</h2><b>{corte_corto}</b><p>{dias_txt}</p></div>
                </section>
                """)
            mostrar(f'<div class="sirea-quipu-banda">{quipu_semanas(semana_actual, total_semanas, anio_actual)}</div>')

    # ---------- Accesos ----------
    with st.container(key="sire_accesos"):
        col1, col2, col3 = st.columns(3, gap="medium")

        with col1, st.container(key="op_1"):
            mostrar(f"""
            <div class="sire-op">
              <div class="sire-op-ico" style="background:#EAF3FB">{icono('subir', 26, '#0077C8')}</div>
              <p class="sire-op-eye">Para redes asistenciales</p>
              <h3>Enviar reporte</h3>
              <p>Cargue el archivo ZIP de su red con los reportes de la semana. Al terminar recibe su código de seguimiento.</p>
            </div>
            """)
            if st.button("Ir a enviar  →", key="btn-usuario", use_container_width=True):
                _ir_a('usuario')

        with col2, st.container(key="op_2"):
            mostrar(f"""
            <div class="sire-op">
              <div class="sire-op-ico" style="background:#EAF3FB">{icono('barras', 26, '#0077C8')}</div>
              <p class="sire-op-eye">Para redes asistenciales</p>
              <h3>Mi progreso</h3>
              <p>Vea qué centros de su red ya reportaron, cuáles faltan y su historial semana a semana. Acceso con la contraseña de su red.</p>
            </div>
            """)
            if st.button("Ver mi progreso  →", key="btn-red-progreso", use_container_width=True):
                _ir_a('red_progreso')

        with col3, st.container(key="op_3"):
            mostrar(f"""
            <div class="sire-op">
              <div class="sire-op-ico" style="background:#EAF3FB">{icono('escudo', 26, '#1D3F76')}</div>
              <p class="sire-op-eye">Personal de la OIIS</p>
              <h3>Panel de administración</h3>
              <p>Seguimiento nacional, atrasos, duplicados y notificaciones a las redes. Solo para personal autorizado.</p>
            </div>
            """)
            if st.button("Ingresar al panel  →", key="btn-admin", use_container_width=True):
                st.session_state.pagina = 'admin'
                st.session_state.seccion_admin = 'Dashboard'
                st.rerun()

    # ---------- Cómo funciona / plazos ----------
    st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
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
    # Las dos tarjetas en una misma rejilla: misma altura, de extremo a extremo.
    mostrar(f"""
    <div class="sire-dos">
      <div class="sire-tarjeta2">
        <h2>Cómo funciona</h2>
        <p class="sub">Cuatro pasos, de la preparación al acuse.</p>
        <div class="sire-paso"><b>1</b><div><h3>Prepare un archivo ZIP</h3><p>Con los reportes de los centros de su red en formato xlsx, csv, xls o dbf.</p></div></div>
        <div class="sire-paso"><b>2</b><div><h3>Registre el envío</h3><p>Indique su red, los centros, el tipo de reporte, la semana y la persona responsable.</p></div></div>
        <div class="sire-paso"><b>3</b><div><h3>Reciba el acuse por correo</h3><p>Llega con el código de seguimiento y el detalle de lo enviado.</p></div></div>
        <div class="sire-paso" style="margin-bottom:0"><b>4</b><div><h3>Compruebe su avance</h3><p>En «Mi progreso» verá los centros enviados y pendientes de su red.</p></div></div>
      </div>
      <div class="sire-tarjeta2" style="display:flex;flex-direction:column">
        <h2>Plazos y recordatorios</h2>
        <p class="sub">Qué esperar de la semana en curso.</p>
        <div class="sire-plazo"><span style="background:#E3F0FA">{icono('calendario', 20, '#0077C8', 2.2)}</span>
          <div><h3>Fecha de corte</h3><p>La define la OIIS cada semana. {corte_frase}</p></div></div>
        <div class="sire-plazo"><span style="background:#EAF3FB">{icono('campana', 20, '#0077C8', 2.2)}</span>
          <div><h3>Recordatorio preventivo</h3><p>Las redes con centros pendientes reciben un correo antes de la fecha de corte.</p></div></div>
        <div class="sire-plazo"><span style="background:#FDE8E8">{icono('reloj', 20, '#9E2B2B', 2.2)}</span>
          <div><h3>Envíos tardíos</h3><p>Los envíos posteriores a la fecha de corte se registran como tardíos y el acuse lo indica con una cabecera roja.</p></div></div>
        <div class="sire-plazo"><span style="background:#EAF3FB">{icono('correo', 20, '#0077C8', 2.2)}</span>
          <div><h3>Acuse con código</h3><p>Cada envío recibe un código de seguimiento; con él la OIIS ubica su reporte en segundos.</p></div></div>
        {contacto_html}
      </div>
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

def _aviso_sin_conexion(contenedor=None) -> bool:
    """
    Franja de aviso si el servidor de la base de datos no responde (proyecto pausado, sin internet, proxy).
    - Redes y público: un mensaje corto y amable, sin datos técnicos.
    - Administradores con sesión: además, la causa y qué hacer.
    Se vuelve a comprobar sola cada 30 s; cuando la conexión vuelve, la pantalla se recarga.
    """
    try:
        from src.conexion_supabase import diagnostico_conexion
    except Exception:
        return False
    if not diagnostico_conexion():
        return False

    @st.fragment(run_every="30s")
    def _franja():
        motivo = diagnostico_conexion(cada_segundos=25)
        if not motivo:
            st.rerun(scope="app")      # volvió la conexión: se recarga todo con datos
            return
        admin = bool(st.session_state.get('admin_logueado'))
        detalle = ""
        if admin:
            detalle = (
                '<details><summary>Detalle técnico (solo administradores)</summary>'
                f'<p>{sanitizar_html(motivo)}</p>'
                '<p>Si el proyecto de Supabase está <b>pausado</b> por inactividad (plan gratuito), reactívelo en '
                'supabase.com → su proyecto → <b>Resume project</b>; la dirección puede tardar unos minutos en '
                'volver a responder. Para que no se vuelva a pausar, active el robot de actividad '
                '(<code>docs/MANTENER_ACTIVO.md</code>). Revisión paso a paso: <code>python verificar_despliegue.py</code>.</p>'
                '</details>'
            )
        mostrar(
            '<div class="sire-sin-red" role="status" aria-live="polite">'
            f'<div class="sire-sin-red-in">{icono("info", 20, "#FFFFFF", 2.2)}'
            '<div><b>El sistema no está disponible en este momento.</b> '
            'Estamos restableciendo la conexión; esta pantalla se actualiza sola. '
            'Si estaba llenando un envío, no cierre la página: lo que ya escribió se conserva.'
            f'{detalle}</div></div></div>'
        )

    if contenedor is not None:
        with contenedor:
            _franja()
    else:
        _franja()
    return True


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
        st.info("Revise `.streamlit/secrets.toml` (o el `.env`, si aún lo usa) y verifique esas variables.")
        st.stop()

    init_session_state()
    # Lugar reservado arriba de todo para el aviso de conexión (oculto si está vacío). Se llena al inicio si ya se
    # sabe que no hay conexión, o al final si las consultas de esta pantalla fallaron (p. ej. detrás de un proxy).
    _caja_aviso = st.container(key="sire_aviso_red")
    _aviso_mostrado = _aviso_sin_conexion(_caja_aviso)
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

    if not _aviso_mostrado:
        _aviso_sin_conexion(_caja_aviso)   # las consultas de esta pantalla fallaron por conexión


if __name__ == "__main__":
    main()