# pages/admin_helpers.py
"""
Funciones chicas compartidas entre las páginas del panel de administrador
(formateo de fechas/centros, colores/estilos de estado para tablas,
saneo de DataFrames, exclusiones). Separadas de admin.py para que las
páginas divididas (admin_dashboard.py, admin_atrasos.py, etc.) puedan
importarlas sin duplicar código.
"""

import pandas as pd
import streamlit as st
from src.db_manager import get_db_manager
from src.auth import get_auth_manager
from utils.helpers import sanitizar_html


def requerir_admin(permiso_super_admin: bool = False) -> bool:
    """
    Verifica que exista una sesión de administrador VÁLIDA -- revalida el
    token contra AuthManager (no confía solo en el flag booleano de
    session_state, que puede quedar "encendido" en una pestaña abierta
    aunque el token ya haya expirado u otro flujo lo haya invalidado).

    Pensada como primera línea de cada mostrar_*() del panel de admin:
    es una defensa en profundidad además del control que ya hace
    admin.py al enrutar las secciones, para que cada sección quede
    protegida por sí misma sin importar cómo se llegue a invocarla.

    Si la sesión no es válida, muestra un aviso y corta la ejecución del
    script con st.stop() (no retorna). Si permiso_super_admin=True,
    exige además rol SUPER_ADMIN (no solo ADMIN).
    """
    token = st.session_state.get('admin_token')
    auth_manager = get_auth_manager()

    if not token or not auth_manager.verificar_sesion(token):
        st.session_state.admin_logueado = False
        st.session_state.admin_token = None
        st.session_state.admin_usuario = None
        from utils.tema import mostrar_aviso
        mostrar_aviso("bad", "Tu sesión expiró o no es válida", "Vuelve a iniciar sesión.")
        st.stop()

    if permiso_super_admin and not auth_manager.es_super_admin(token):
        from utils.tema import mostrar_aviso
        mostrar_aviso("bad", "Acceso restringido", "Esta sección solo está disponible para SUPER_ADMIN.")
        st.stop()

    return True


def actor_actual() -> dict:
    """
    Persona con sesión válida, tomada del servidor (no de lo que haya en la pantalla):
    {usuario, nombre, rol, email}. Corta la ejecución si la sesión no es válida.
    """
    requerir_admin()
    return get_auth_manager().obtener_usuario_actual(st.session_state.get('admin_token')) or {}


def formatear_fecha_columna(valor):
    """Formatea fechas convirtiendo UTC a hora Peru."""
    from datetime import timedelta
    
    if valor is None or valor == 'N/A' or valor == '':
        return '—'
    try:
        dt = pd.to_datetime(valor)
        if pd.isna(dt):
            return '—'
        # Restar 5 horas (UTC a Peru)
        dt_peru = dt - timedelta(hours=5)
        return dt_peru.strftime('%d/%m/%Y %H:%M')
    except:
        return '—'


def color_estado(estado):
    """Retorna la clase CSS para el estado."""
    if not estado:
        return 'badge-secondary'
    estado_str = str(estado).upper()
    if estado_str == 'APROBADO':
        return 'badge-success'
    elif estado_str == 'OBSERVADO':
        return 'badge-warning'
    elif estado_str == 'ATRASADO':
        return 'badge-danger'
    else:
        return 'badge-secondary'


def color_porcentaje(porcentaje):
    """Retorna la clase CSS para el porcentaje."""
    try:
        valor = float(str(porcentaje).replace('%', '').strip())
        if valor >= 80:
            return 'badge-success'
        elif valor >= 50:
            return 'badge-warning'
        else:
            return 'badge-danger'
    except:
        return 'badge-secondary'


def formatear_centro(centro):
    """Formatea un centro para mostrarlo como 'codigo nombre'."""
    if isinstance(centro, dict):
        codigo = centro.get('codigo', '')
        nombre = centro.get('nombre', '')
        if codigo and nombre:
            return f"{codigo} {nombre}"
        elif nombre:
            return nombre
        else:
            return str(centro)
    return str(centro)


def obtener_nombre_centro(centro):
    """Obtiene el nombre del centro desde un dict o string."""
    if isinstance(centro, dict):
        return centro.get('nombre', str(centro))
    return str(centro)


def estilo_estado(val):
    """Funcion para aplicar estilo a la columna Estado."""
    if pd.isna(val) or val == '':
        return 'background-color: #E2E3E5; color: #383D41; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
    val_str = str(val).upper()
    if val_str == 'APROBADO':
        return 'background-color: #D4EDDA; color: #155724; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
    elif val_str == 'OBSERVADO':
        return 'background-color: #FFF3CD; color: #856404; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
    elif val_str == 'ATRASADO':
        return 'background-color: #F8D7DA; color: #721C24; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
    else:
        return 'background-color: #E2E3E5; color: #383D41; font-weight: 700; border-radius: 20px; padding: 4px 12px;'


def estilo_porcentaje(val):
    """Funcion para aplicar estilo a la columna % Recibido."""
    try:
        valor = float(str(val).replace('%', '').strip())
        if valor >= 80:
            return 'background-color: #D4EDDA; color: #155724; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
        elif valor >= 50:
            return 'background-color: #FFF3CD; color: #856404; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
        else:
            return 'background-color: #F8D7DA; color: #721C24; font-weight: 700; border-radius: 20px; padding: 4px 12px;'
    except:
        return 'background-color: #E2E3E5; color: #383D41; font-weight: 700; border-radius: 20px; padding: 4px 12px;'


def sanitizar_dataframe(df: pd.DataFrame, columnas: list) -> pd.DataFrame:
    """
    Sanitiza las columnas especificadas de un DataFrame.
    """
    df_copy = df.copy()
    for col in columnas:
        if col in df_copy.columns:
            df_copy[col] = df_copy[col].apply(lambda x: sanitizar_html(str(x)) if x and pd.notna(x) else "")
    return df_copy


def obtener_centros_excluidos():
    """
    Obtiene el diccionario de centros excluidos desde la base de datos.
    Esta funcion se mantiene para compatibilidad con el resto del codigo.
    """
    db_manager = get_db_manager()
    return db_manager.obtener_todas_las_exclusiones_agrupadas()