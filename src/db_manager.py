# src/db_manager.py
"""
Gestión de la base de datos Supabase para el sistema de reportes.
Maneja las operaciones CRUD para envíos, administradores, configuración
y centros excluidos.
"""

import os
import time
from supabase import create_client  # noqa: F401  (se conserva por compatibilidad)
from src.conexion_supabase import crear_cliente_supabase
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import json
import hashlib
import secrets
import string

from src.config import Config


class DatabaseManager:
    """
    Gestor de la base de datos Supabase.
    """
    
    def __init__(self):
        """Inicializa la conexión a Supabase."""
        # Conexión HTTP/1.1 con reintento de lecturas: evita los cortes de la conexión HTTP/2 compartida
        # (WinError 10035, ConnectionTerminated) que aparecen en Windows. Ver src/conexion_supabase.py.
        self.supabase = crear_cliente_supabase(
            os.environ.get('SUPABASE_URL', ''),
            os.environ.get('SUPABASE_KEY', '')
        )
    
    # ============================================================
    # METODOS AUXILIARES
    # ============================================================
    
    def _generar_codigo_seguimiento(self) -> str:
        """Genera un codigo de seguimiento unico."""
        caracteres = string.ascii_uppercase + string.digits
        codigo = 'ESS-' + ''.join(secrets.choice(caracteres) for _ in range(4)) + '-' + ''.join(secrets.choice(caracteres) for _ in range(4))
        
        while self.obtener_envio_por_codigo(codigo):
            codigo = 'ESS-' + ''.join(secrets.choice(caracteres) for _ in range(4)) + '-' + ''.join(secrets.choice(caracteres) for _ in range(4))
        
        return codigo
    
    def _obtener_fecha_actual_iso(self) -> str:
        """Obtiene la fecha y hora actual en formato ISO."""
        return datetime.now().isoformat()
    
    def _obtener_fecha_actual(self) -> datetime:
        """Obtiene la fecha y hora actual."""
        return datetime.now()
    
    # ============================================================
    # METODOS PARA ENVIOS
    # ============================================================
    
    def registrar_envio(
        self,
        nombre_usuario: str,
        apellido_usuario: str,
        correo_usuario: str,
        red: str,
        centros: List[str],
        semana: int,
        tipo_reporte: List[str],
        ruta_zip: str,
        drive_file_id: str,
        cantidad_archivos: int = 0,
        estado: str = 'PENDIENTE',
        observacion: Optional[str] = None,
        anio: Optional[int] = None,
        codigo_seguimiento: Optional[str] = None,
        es_atrasado: bool = False,
        semana_activa_envio: Optional[int] = None,
        dias_atraso_envio: int = 0,
        detalle_archivos: Optional[List[Dict]] = None
    ) -> int:
        """
        Registra un nuevo envio en la base de datos.

        detalle_archivos (opcional): un dict por archivo del ZIP con
        centro, código, tipo (c/e/h), semana, año y huella SHA-256 -- sirve
        para detectar duplicados por centro+tipo y archivos repetidos de
        otras semanas. Requiere la columna envios.detalle_archivos
        (sql/12_envios_detalle_archivos.sql); si la columna aún no existe
        el envío se registra igual, sin ese detalle.
        Retorna el ID del envio creado.

        semana_activa_envio y dias_atraso_envio quedan FIJOS con el
        contexto real del momento del envio (que semana estaba activa,
        cuantos dias de atraso tenia en ESE momento) -- a diferencia de
        `semana` (de que semana es el reporte) y `es_atrasado`, estos no
        deben recalcularse despues con la configuracion actual, porque
        el admin puede cambiar la semana activa o la fecha de corte en
        cualquier momento y eso no debe reescribir la historia.
        """
        if anio is None:
            anio_activo = self.obtener_anio_activo_epidemiologico()
            anio = anio_activo['anio'] if anio_activo else datetime.now().year

        if semana_activa_envio is None:
            semana_activa_envio = semana

        if codigo_seguimiento is None:
            codigo_seguimiento = self._generar_codigo_seguimiento()
        
        data = {
            'nombre_usuario': nombre_usuario,
            'apellido_usuario': apellido_usuario,
            'correo_usuario': correo_usuario,
            'red': red,
            'centros': centros,
            'semana': semana,
            'anio': anio,
            'tipo_reporte': tipo_reporte,
            'ruta_zip': ruta_zip,
            'drive_file_id': drive_file_id,
            'cantidad_archivos': cantidad_archivos,
            'estado': estado,
            'observacion': observacion,
            'es_atrasado': es_atrasado,
            'semana_activa_envio': semana_activa_envio,
            'dias_atraso_envio': max(0, dias_atraso_envio),
            'codigo_seguimiento': codigo_seguimiento,
            'fecha_actualizacion': self._obtener_fecha_actual_iso()
        }
        
        if detalle_archivos:
            data['detalle_archivos'] = detalle_archivos

        try:
            resultado = self.supabase.table('envios').insert(data).execute()
            return resultado.data[0]['id'] if resultado.data else None
        except Exception as e:
            if detalle_archivos and 'detalle_archivos' in str(e):
                # La columna aún no existe: el envío NO se pierde, se registra sin el detalle.
                print("Aviso: falta la columna envios.detalle_archivos "
                      "(ejecute sql/12_envios_detalle_archivos.sql). Se registra sin detalle.")
                data.pop('detalle_archivos', None)
                try:
                    resultado = self.supabase.table('envios').insert(data).execute()
                    return resultado.data[0]['id'] if resultado.data else None
                except Exception as e2:
                    print(f"Error al registrar envío: {e2}")
                    return None
            print(f"Error al registrar envío: {e}")
            return None
    
    def obtener_envio(self, envio_id: int) -> Optional[Dict]:
        """Obtiene un envio por su ID."""
        try:
            resultado = self.supabase.table('envios')\
                .select('*')\
                .eq('id', envio_id)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener envío: {e}")
            return None
    
    def obtener_envio_por_codigo(self, codigo: str) -> Optional[Dict]:
        """Obtiene un envio por su codigo de seguimiento."""
        try:
            resultado = self.supabase.table('envios')\
                .select('*')\
                .eq('codigo_seguimiento', codigo)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener envío por código: {e}")
            return None
    
    def obtener_envios(
        self,
        semana: Optional[int] = None,
        red: Optional[str] = None,
        estado: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        anio: Optional[int] = None,
        incluir_atrasados: bool = True,
        solo_atrasados: bool = False,
        semana_activa_envio: Optional[int] = None
    ) -> List[Dict]:
        """
        Obtiene una lista de envios con filtros opcionales.

        `semana` filtra por de-que-semana-es-el-reporte (uso normal, para
        ver el progreso/seguimiento de una semana). `semana_activa_envio`
        filtra en cambio por cuando se REGISTRO el envio -- usalo para
        vistas tipo "que atrasos ocurrieron durante la semana activa X",
        que es una pregunta distinta (ver obtener_envios_atrasados).
        """
        try:
            query = self.supabase.table('envios').select('*')
            
            if semana is not None:
                query = query.eq('semana', semana)
            if semana_activa_envio is not None:
                query = query.eq('semana_activa_envio', semana_activa_envio)
            if red:
                query = query.eq('red', red)
            if estado:
                query = query.eq('estado', estado)
            if anio is not None:
                query = query.eq('anio', anio)
            
            if not incluir_atrasados:
                query = query.eq('es_atrasado', False)
            
            if solo_atrasados:
                query = query.eq('es_atrasado', True)
            
            query = query.range(offset, offset + limit - 1).order('fecha_envio', desc=True)
            resultado = query.execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener envíos: {e}")
            return []
    
    def obtener_envios_atrasados(
        self, 
        semana_actual: int, 
        limit: int = 500,
        anio: Optional[int] = None
    ) -> List[Dict]:
        """
        Obtiene los envíos atrasados que fueron REGISTRADOS mientras
        `semana_actual` estaba activa (columna semana_activa_envio) --
        no los que son SOBRE esa semana (columna semana).

        Ejemplo: si en la semana activa 37 alguien envia tardiamente un
        reporte de la semana 36, ese envio debe aparecer como atraso de
        la semana 37 (que es cuando ocurrio el atraso), no de la 36.

        Requiere la columna semana_activa_envio (ver migracion SQL). Los
        envios registrados ANTES de esa migracion no tienen este dato y
        no apareceran aqui -- quedan como historial visible solo al
        consultar directamente la tabla de envios.
        """
        try:
            if anio is None:
                anio = Config.get_anio_actual()

            query = self.supabase.table('envios').select('*')
            query = query.eq('es_atrasado', True)
            query = query.eq('anio', anio)
            query = query.eq('semana_activa_envio', semana_actual)
            query = query.limit(limit).order('semana', desc=True)
            
            resultado = query.execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener envíos atrasados: {e}")
            return []
    
    def obtener_semanas_disponibles(self, anio: Optional[int] = None) -> List[int]:
        """Obtiene todas las semanas disponibles en los envios."""
        try:
            query = self.supabase.table('envios').select('semana', distinct=True)
            if anio is not None:
                query = query.eq('anio', anio)
            query = query.order('semana', desc=True)
            resultado = query.execute()
            return [item['semana'] for item in resultado.data]
        except Exception as e:
            print(f"Error al obtener semanas disponibles: {e}")
            return []
    
    def actualizar_envio(
        self,
        envio_id: int,
        estado: Optional[str] = None,
        observacion: Optional[str] = None,
        es_atrasado: Optional[bool] = None,
        version: Optional[int] = None
    ) -> bool:
        """Actualiza un envio existente."""
        try:
            updates = {}
            if estado:
                updates['estado'] = estado
            if observacion is not None:
                updates['observacion'] = observacion
            if es_atrasado is not None:
                updates['es_atrasado'] = es_atrasado
            if version is not None:
                updates['version'] = version
            
            if not updates:
                return True
            
            updates['fecha_actualizacion'] = self._obtener_fecha_actual_iso()
            
            resultado = self.supabase.table('envios')\
                .update(updates)\
                .eq('id', envio_id)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar envío: {e}")
            return False
    
    def actualizar_campos_envio(self, envio_id: int, campos: Dict) -> bool:
        """Actualiza columnas concretas de un envío (p. ej. al reemplazar su archivo). True si se actualizó."""
        try:
            data = dict(campos)
            data['fecha_actualizacion'] = self._obtener_fecha_actual_iso()
            resultado = self.supabase.table('envios').update(data).eq('id', envio_id).execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar envío {envio_id}: {e}")
            return False

    def eliminar_envio(self, envio_id: int) -> bool:
        """Elimina un envio de la base de datos."""
        try:
            resultado = self.supabase.table('envios')\
                .delete()\
                .eq('id', envio_id)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al eliminar envío: {e}")
            return False
    
    def eliminar_envios_por_red_y_centro(
        self,
        red: str,
        centro: str,
        semana: int,
        mantener_id: Optional[int] = None
    ) -> int:
        """Elimina envíos duplicados de un centro especifico."""
        try:
            envios = self.obtener_envios(red=red, semana=semana, limit=10000)
            ids_a_eliminar = []
            
            for envio in envios:
                centros = envio.get('centros', [])
                if isinstance(centros, list) and centro in centros:
                    if mantener_id is None or envio['id'] != mantener_id:
                        ids_a_eliminar.append(envio['id'])
            
            eliminados = 0
            for envio_id in ids_a_eliminar:
                if self.eliminar_envio(envio_id):
                    eliminados += 1
            
            return eliminados
        except Exception as e:
            print(f"Error al eliminar envíos duplicados: {e}")
            return 0
    
    def contar_envios(
        self, 
        semana: Optional[int] = None, 
        anio: Optional[int] = None,
        incluir_atrasados: bool = True
    ) -> int:
        """Cuenta el numero total de envios."""
        try:
            query = self.supabase.table('envios').select('*', count='exact')
            if semana is not None:
                query = query.eq('semana', semana)
            if anio is not None:
                query = query.eq('anio', anio)
            if not incluir_atrasados:
                query = query.eq('es_atrasado', False)
            
            resultado = query.execute()
            return resultado.count
        except Exception as e:
            print(f"Error al contar envíos: {e}")
            return 0
    
    def _envios_de_semana(self, semana: int, anio: Optional[int], incluir_atrasados: bool, columnas: str) -> List[Dict]:
        """SIREA 3.3: todos los envíos de la semana, de 1000 en 1000 (PostgREST no devuelve más por consulta)."""
        filas: List[Dict] = []
        offset = 0
        while True:
            q = self.supabase.table('envios').select(columnas).eq('semana', semana)
            if anio is not None:
                q = q.eq('anio', anio)
            if not incluir_atrasados:
                q = q.eq('es_atrasado', False)
            lote = q.order('id').range(offset, offset + 999).execute().data or []
            filas.extend(lote)
            if len(lote) < 1000:
                return filas
            offset += 1000

    def contar_envios_por_red(
        self, 
        semana: int, 
        anio: Optional[int] = None,
        incluir_atrasados: bool = True
    ) -> Dict[str, int]:
        """Cuenta los envíos por red para una semana especifica."""
        try:
            envios = self._envios_de_semana(semana, anio, incluir_atrasados, 'id,red')
            
            resultado = {}
            for envio in envios:
                red = envio.get('red', 'Sin Red')
                resultado[red] = resultado.get(red, 0) + 1
            
            return resultado
        except Exception as e:
            print(f"Error al contar envíos por red: {e}")
            return {}
    
    def contar_envios_por_estado(
        self, 
        semana: int,
        incluir_atrasados: bool = True,
        anio: Optional[int] = None,
    ) -> Dict[str, int]:
        """Cuenta los envíos por estado para una semana especifica."""
        try:
            envios = self._envios_de_semana(semana, anio, incluir_atrasados, 'id,estado')
            
            resultado = {}
            for envio in envios:
                estado = envio.get('estado', 'PENDIENTE')
                resultado[estado] = resultado.get(estado, 0) + 1
            
            return resultado
        except Exception as e:
            print(f"Error al contar envíos por estado: {e}")
            return {}
    
    def obtener_centros_por_red(
        self, 
        semana: int,
        incluir_atrasados: bool = False
    ) -> Dict[str, List[str]]:
        """Obtiene todos los centros enviados por red en una semana especifica."""
        try:
            envios = self.obtener_envios(
                semana=semana,
                incluir_atrasados=incluir_atrasados,
                limit=10000
            )
            
            resultado = {}
            for envio in envios:
                red = envio.get('red', '')
                centros = envio.get('centros', [])
                if red not in resultado:
                    resultado[red] = []
                for centro in centros:
                    if centro not in resultado[red]:
                        resultado[red].append(centro)
            
            return resultado
        except Exception as e:
            print(f"Error al obtener centros por red: {e}")
            return {}
    
    def obtener_estadisticas_semana(
        self, 
        semana: int,
        incluir_atrasados: bool = True,
        anio: Optional[int] = None,
    ) -> Dict:
        """Obtiene estadisticas completas para una semana (SIREA 3.3: del año indicado; por defecto, el activo)."""
        if anio is None:
            anio = Config.get_anio_actual()
        total_envios = self.contar_envios(semana, anio=anio, incluir_atrasados=incluir_atrasados)
        envios_por_red = self.contar_envios_por_red(semana, anio=anio, incluir_atrasados=incluir_atrasados)
        envios_por_estado = self.contar_envios_por_estado(semana, incluir_atrasados=incluir_atrasados, anio=anio)
        atrasados = len(self.obtener_envios_atrasados(semana, limit=1000, anio=anio))
        
        return {
            'semana': semana,
            'anio': anio,
            'total_envios': total_envios,
            'envios_por_red': envios_por_red,
            'envios_por_estado': envios_por_estado,
            'atrasados': atrasados,
            'aprobados': envios_por_estado.get('APROBADO', 0),
            'observados': envios_por_estado.get('OBSERVADO', 0),
            'pendientes': envios_por_estado.get('PENDIENTE', 0),
        }
    
    # ============================================================
    # METODOS PARA ADMINISTRADORES
    # ============================================================
    
    def obtener_administrador(self, usuario: str) -> Optional[Dict]:
        """Obtiene un administrador por su nombre de usuario."""
        try:
            resultado = self.supabase.table('administradores')\
                .select('*')\
                .eq('usuario', usuario)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener administrador: {e}")
            return None
    
    def obtener_administradores(self, solo_activos: bool = False) -> List[Dict]:
        """Obtiene todos los administradores."""
        try:
            query = self.supabase.table('administradores').select('*')
            if solo_activos:
                query = query.eq('activo', True)
            query = query.order('id')
            resultado = query.execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener administradores: {e}")
            return []
    
    def crear_administrador(
        self,
        usuario: str,
        password_hash: str,
        nombre: str,
        email: str,
        rol: str = 'ADMIN'
    ) -> bool:
        """Crea un nuevo administrador."""
        try:
            data = {
                'usuario': usuario,
                'password_hash': password_hash,
                'nombre': nombre,
                'email': email,
                'rol': rol
            }
            resultado = self.supabase.table('administradores').insert(data).execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al crear administrador: {e}")
            return False
    
    def actualizar_administrador(
        self,
        usuario: str,
        nombre: Optional[str] = None,
        email: Optional[str] = None,
        rol: Optional[str] = None,
        password_hash: Optional[str] = None,
        activo: Optional[bool] = None
    ) -> bool:
        """Actualiza un administrador existente."""
        try:
            updates = {}
            if nombre is not None:
                updates['nombre'] = nombre
            if email is not None:
                updates['email'] = email
            if rol is not None:
                updates['rol'] = rol
            if password_hash is not None:
                updates['password_hash'] = password_hash
            if activo is not None:
                updates['activo'] = activo
            
            if not updates:
                return True
            
            resultado = self.supabase.table('administradores')\
                .update(updates)\
                .eq('usuario', usuario)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar administrador: {e}")
            return False
    
    def renombrar_administrador(self, usuario_actual: str, usuario_nuevo: str) -> bool:
        """Cambia el nombre de usuario (columna usuario) de un administrador."""
        try:
            resultado = self.supabase.table('administradores')\
                .update({'usuario': usuario_nuevo})\
                .eq('usuario', usuario_actual)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al renombrar administrador: {e}")
            return False

    def actualizar_ultimo_login(self, usuario: str) -> bool:
        """Actualiza la fecha de último login."""
        try:
            resultado = self.supabase.table('administradores')\
                .update({'ultimo_login': self._obtener_fecha_actual_iso()})\
                .eq('usuario', usuario)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar último login: {e}")
            return False
    
    def eliminar_administrador(self, usuario: str) -> bool:
        """Elimina un administrador (no permite eliminar SUPER_ADMIN)."""
        try:
            admin = self.obtener_administrador(usuario)
            if admin and admin.get('rol') == 'SUPER_ADMIN':
                return False
            
            resultado = self.supabase.table('administradores')\
                .delete()\
                .eq('usuario', usuario)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al eliminar administrador: {e}")
            return False
    
    # ============================================================
    # METODOS PARA CREDENCIALES DE RED (login por red)
    # ============================================================
    # Tabla separada de "administradores": cada red asistencial tiene
    # su propia contraseña (bcrypt), generada y distribuida por el
    # administrador -- no hay autoregistro. Se usa para que cada red
    # pueda ver SOLO su propio progreso semana a semana (ver
    # pages/red_progreso.py), sin acceso al formulario de envio ni a
    # los datos de otras redes.

    def obtener_credencial_red(self, red: str) -> Optional[Dict]:
        """Obtiene la credencial de una red por su nombre."""
        try:
            resultado = self.supabase.table('credenciales_red')\
                .select('*')\
                .eq('red', red)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener credencial de red: {e}")
            return None

    def listar_credenciales_red(self) -> List[Dict]:
        """Lista las credenciales de todas las redes que ya tienen una configurada."""
        try:
            resultado = self.supabase.table('credenciales_red')\
                .select('*')\
                .order('red')\
                .execute()
            return resultado.data
        except Exception as e:
            print(f"Error al listar credenciales de red: {e}")
            return []

    def crear_credencial_red(
        self,
        red: str,
        password_hash: str,
        creado_por: Optional[str] = None,
        debe_cambiar_password: bool = True
    ) -> bool:
        """Crea la credencial de acceso de una red.

        debe_cambiar_password=True por defecto: toda contraseña creada
        por el administrador se considera temporal y la red debe
        cambiarla la primera vez que entra a "Ver mi progreso".
        """
        try:
            data = {
                'red': red,
                'password_hash': password_hash,
                'activo': True,
                'creado_por': creado_por,
                'debe_cambiar_password': debe_cambiar_password
            }
            resultado = self.supabase.table('credenciales_red').insert(data).execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al crear credencial de red: {e}")
            return False

    def actualizar_credencial_red(
        self,
        red: str,
        password_hash: Optional[str] = None,
        activo: Optional[bool] = None,
        debe_cambiar_password: Optional[bool] = None
    ) -> bool:
        """Actualiza la contraseña, el estado activo y/o la bandera de
        cambio obligatorio de contraseña de la credencial de una red."""
        try:
            updates = {}
            if password_hash is not None:
                updates['password_hash'] = password_hash
            if activo is not None:
                updates['activo'] = activo
            if debe_cambiar_password is not None:
                updates['debe_cambiar_password'] = debe_cambiar_password

            if not updates:
                return True

            updates['fecha_actualizacion'] = self._obtener_fecha_actual_iso()

            resultado = self.supabase.table('credenciales_red')\
                .update(updates)\
                .eq('red', red)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar credencial de red: {e}")
            return False

    def actualizar_ultimo_login_red(self, red: str) -> bool:
        """Actualiza la fecha de último login de una red."""
        try:
            resultado = self.supabase.table('credenciales_red')\
                .update({'ultimo_login': self._obtener_fecha_actual_iso()})\
                .eq('red', red)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar último login de red: {e}")
            return False

    def eliminar_credencial_red(self, red: str) -> bool:
        """Elimina la credencial de acceso de una red."""
        try:
            resultado = self.supabase.table('credenciales_red')\
                .delete()\
                .eq('red', red)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al eliminar credencial de red: {e}")
            return False

    # ============================================================
    # METODOS PARA CONFIGURACION
    # ============================================================

    # Cada pantalla pregunta varias veces por la semana activa, el corte y el año activo.
    # Se recuerdan unos segundos para no repetir las mismas consultas; cualquier cambio
    # (guardar/actualizar configuración, crear/activar/editar/eliminar año) limpia el recuerdo.
    _CACHE_SEGUNDOS = 10

    def _cache_leer(self, clave):
        c = self.__dict__.setdefault('_cache_consultas', {})
        v = c.get(clave)
        if v and (time.monotonic() - v[0]) < self._CACHE_SEGUNDOS:
            return True, v[1]
        return False, None

    def _cache_guardar(self, clave, valor):
        self.__dict__.setdefault('_cache_consultas', {})[clave] = (time.monotonic(), valor)

    def invalidar_cache(self):
        """Olvida lo recordado (se llama tras cualquier escritura de configuración o años)."""
        self.__dict__.setdefault('_cache_consultas', {}).clear()

    def obtener_configuracion(self, clave: str) -> Optional[str]:
        """Obtiene el valor de una clave de configuracion."""
        hit, valor = self._cache_leer(('cfg', clave))
        if hit:
            return valor
        try:
            resultado = self.supabase.table('configuracion')\
                .select('valor')\
                .eq('clave', clave)\
                .execute()
            valor = resultado.data[0]['valor'] if resultado.data else None
            self._cache_guardar(('cfg', clave), valor)
            return valor
        except Exception as e:
            print(f"Error al obtener configuración: {e}")
            return None
    
    def actualizar_configuracion(self, clave: str, valor: str) -> bool:
        """Actualiza el valor de una clave de configuracion."""
        try:
            resultado = self.supabase.table('configuracion')\
                .update({
                    'valor': valor,
                    'fecha_actualizacion': self._obtener_fecha_actual_iso()
                })\
                .eq('clave', clave)\
                .execute()
            self.invalidar_cache()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar configuración: {e}")
            return False
    
    def guardar_configuracion(self, clave: str, valor: str):
        """
        Guarda un valor de configuración y COMPRUEBA que quedó guardado.

        Actualiza la fila si existe; si no existe (o la actualización no
        alcanzó ninguna fila) la crea. Después vuelve a leerla: así nunca se
        informa «guardado» cuando la base de datos no lo aceptó.
        Devuelve (ok, detalle).
        """
        valor = str(valor)
        try:
            ahora = self._obtener_fecha_actual_iso()
            res = self.supabase.table('configuracion')                .update({'valor': valor, 'fecha_actualizacion': ahora})                .eq('clave', clave)                .execute()
            if not res.data:
                self.supabase.table('configuracion')                    .insert({'clave': clave, 'valor': valor, 'fecha_actualizacion': ahora})                    .execute()
            self.invalidar_cache()
            leido = self.obtener_configuracion(clave)
            if leido is None or str(leido) != valor:
                return False, (f"La base de datos no confirmó el valor de «{clave}». "
                               "Revise los permisos de la tabla configuracion (clave de servicio de Supabase).")
            return True, "Guardado."
        except Exception as e:
            print(f"Error al guardar configuración '{clave}': {e}")
            return False, f"No se pudo guardar «{clave}»: {e}"

    def obtener_todas_configuraciones(self) -> Dict[str, str]:
        """Obtiene todas las configuraciones."""
        try:
            resultado = self.supabase.table('configuracion')\
                .select('clave, valor')\
                .execute()
            return {item['clave']: item['valor'] for item in resultado.data}
        except Exception as e:
            print(f"Error al obtener configuraciones: {e}")
            return {}
    
    # ============================================================
    # METODOS PARA CARPETAS DRIVE
    # ============================================================
    
    def obtener_carpeta_activa(self) -> Optional[Dict]:
        """Obtiene la carpeta de Drive activa."""
        try:
            resultado = self.supabase.table('carpetas_drive')\
                .select('*')\
                .eq('activo', True)\
                .limit(1)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener carpeta activa: {e}")
            return None
    
    def obtener_carpetas_drive(self) -> List[Dict]:
        """Obtiene todas las carpetas de Drive."""
        try:
            resultado = self.supabase.table('carpetas_drive')\
                .select('*')\
                .order('activo', desc=True)\
                .order('fecha_creacion', desc=True)\
                .execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener carpetas Drive: {e}")
            return []
    
    def crear_carpeta_drive(
        self,
        nombre: str,
        folder_id: str,
        capacidad_maxima_mb: Optional[int] = None
    ) -> bool:
        """Registra una nueva carpeta de Drive."""
        try:
            data = {
                'nombre': nombre,
                'folder_id': folder_id,
                'capacidad_maxima_mb': capacidad_maxima_mb
            }
            resultado = self.supabase.table('carpetas_drive').insert(data).execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al crear carpeta Drive: {e}")
            return False
    
    def cambiar_carpeta_activa_detallado(self, carpeta_id: int) -> Tuple[bool, str]:
        """
        Marca una carpeta como activa y comprueba que quedó así.

        Importante: Supabase (PostgREST) rechaza un UPDATE sin condición, así que
        la versión anterior (que desactivaba «todas» sin filtro) siempre fallaba.
        Aquí se desactivan solo las que están activas.
        Devuelve (ok, detalle).
        """
        previa = None
        try:
            previa = self.obtener_carpeta_activa()
            self.supabase.table('carpetas_drive')\
                .update({'activo': False})\
                .eq('activo', True)\
                .execute()
            resultado = self.supabase.table('carpetas_drive')\
                .update({'activo': True})\
                .eq('id', carpeta_id)\
                .execute()
            if not resultado.data:
                raise RuntimeError("la carpeta no existe o la base de datos no aceptó el cambio")
            activa = self.obtener_carpeta_activa()
            if not activa or activa.get('id') != carpeta_id:
                raise RuntimeError("la base de datos no confirmó el cambio")
            return True, "Carpeta activada."
        except Exception as e:
            print(f"Error al cambiar carpeta activa: {e}")
            try:   # no dejar sin carpeta activa
                if previa and previa.get('id') != carpeta_id:
                    self.supabase.table('carpetas_drive').update({'activo': True}).eq('id', previa['id']).execute()
            except Exception:
                pass
            return False, f"No se pudo activar la carpeta: {e}"

    def cambiar_carpeta_activa(self, carpeta_id: int) -> bool:
        """Cambia la carpeta activa (ver cambiar_carpeta_activa_detallado)."""
        return self.cambiar_carpeta_activa_detallado(carpeta_id)[0]
    
    def eliminar_carpeta_drive(self, carpeta_id: int) -> bool:
        """Elimina una carpeta de Drive (solo si esta inactiva)."""
        try:
            # Verificar que este inactiva
            carpeta = self.supabase.table('carpetas_drive')\
                .select('activo')\
                .eq('id', carpeta_id)\
                .execute()
            
            if carpeta.data and carpeta.data[0].get('activo') == True:
                return False
            
            resultado = self.supabase.table('carpetas_drive')\
                .delete()\
                .eq('id', carpeta_id)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al eliminar carpeta Drive: {e}")
            return False
    
    # ============================================================
    # METODOS PARA LOGS
    # ============================================================
    
    def registrar_log(
        self,
        usuario: str,
        accion: str,
        detalle: Optional[str] = None,
        ip: Optional[str] = None
    ) -> bool:
        """Registra una accion en el log del sistema."""
        try:
            data = {
                'usuario': usuario,
                'accion': accion,
                'detalle': detalle,
                'ip': ip
            }
            resultado = self.supabase.table('logs').insert(data).execute()
            ok = len(resultado.data) > 0
        except Exception as e:
            print(f"Error al registrar log: {e}")
            ok = False
        # Lo mismo queda en la auditoría (solo escritura, con cadena de huellas).
        try:
            from src.auditoria import get_auditoria
            aud = get_auditoria()
            if aud.db is self:
                aud.espejo(usuario, accion, detalle, ip)
        except Exception:
            pass
        return ok
    
    def obtener_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        usuario: Optional[str] = None,
        accion: Optional[str] = None
    ) -> List[Dict]:
        """Obtiene los logs del sistema."""
        try:
            query = self.supabase.table('logs').select('*')
            
            if usuario:
                query = query.eq('usuario', usuario)
            if accion:
                query = query.eq('accion', accion)
            
            query = query.range(offset, offset + limit - 1).order('fecha', desc=True)
            resultado = query.execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener logs: {e}")
            return []
    
    def limpiar_logs_antiguos(self, dias: int = 90) -> int:
        """Elimina logs mas antiguos de X dias."""
        try:
            fecha_limite = datetime.now() - timedelta(days=dias)
            resultado = self.supabase.table('logs')\
                .delete()\
                .lt('fecha', fecha_limite.isoformat())\
                .execute()
            return len(resultado.data)
        except Exception as e:
            print(f"Error al limpiar logs: {e}")
            return 0
    
    # ============================================================
    # METODOS PARA AÑOS EPIDEMIOLOGICOS
    # ============================================================
    
    def obtener_anios_epidemiologicos(self) -> List[Dict]:
        """Obtiene todos los años epidemiologicos."""
        try:
            resultado = self.supabase.table('anios_epidemiologicos')\
                .select('*')\
                .order('anio', desc=True)\
                .execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener años epidemiológicos: {e}")
            return []
    
    def obtener_anio_epidemiologico(self, anio: int) -> Optional[Dict]:
        """Obtiene un año epidemiologico especifico."""
        try:
            resultado = self.supabase.table('anios_epidemiologicos')\
                .select('*')\
                .eq('anio', anio)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener año epidemiológico: {e}")
            return None
    
    def obtener_anio_activo_epidemiologico(self) -> Optional[Dict]:
        """Obtiene el año epidemiologico activo."""
        hit, valor = self._cache_leer(('anio_activo',))
        if hit:
            return dict(valor) if valor else None
        try:
            resultado = self.supabase.table('anios_epidemiologicos')\
                .select('*')\
                .eq('activo', True)\
                .limit(1)\
                .execute()
            valor = resultado.data[0] if resultado.data else None
            self._cache_guardar(('anio_activo',), valor)
            return dict(valor) if valor else None
        except Exception as e:
            print(f"Error al obtener año activo: {e}")
            return None
    
    def crear_anio_epidemiologico(
        self,
        anio: int,
        semanas: int,
        fecha_inicio: str,
        fecha_fin: str,
        activo: bool = False
    ) -> bool:
        """Crea un nuevo año epidemiologico."""
        try:
            # Verificar que el año no exista
            existe = self.obtener_anio_epidemiologico(anio)
            if existe:
                return False
            
            data = {
                'anio': anio,
                'semanas': semanas,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'activo': activo
            }
            resultado = self.supabase.table('anios_epidemiologicos').insert(data).execute()
            self.invalidar_cache()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al crear año epidemiológico: {e}")
            return False
    
    def actualizar_anio_epidemiologico(
        self,
        anio: int,
        semanas: Optional[int] = None,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        activo: Optional[bool] = None
    ) -> bool:
        """Actualiza un año epidemiologico existente."""
        try:
            updates = {}
            if semanas is not None:
                updates['semanas'] = semanas
            if fecha_inicio is not None:
                updates['fecha_inicio'] = fecha_inicio
            if fecha_fin is not None:
                updates['fecha_fin'] = fecha_fin
            if activo is not None:
                updates['activo'] = activo
            
            if not updates:
                return True
            
            resultado = self.supabase.table('anios_epidemiologicos')\
                .update(updates)\
                .eq('anio', anio)\
                .execute()
            self.invalidar_cache()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al actualizar año epidemiológico: {e}")
            return False
    
    def activar_anio_epidemiologico(self, anio: int) -> bool:
        """Activa un año epidemiologico y desactiva los demas."""
        previos = []
        try:
            # Supabase rechaza un UPDATE sin condición (WHERE): se desactivan los DEMÁS años con una condición.
            previos = [a['anio'] for a in (self.supabase.table('anios_epidemiologicos')
                                           .select('anio').eq('activo', True).execute().data or [])
                       if a.get('anio') != anio]
            if previos:
                self.supabase.table('anios_epidemiologicos')\
                    .update({'activo': False})\
                    .neq('anio', anio)\
                    .execute()

            # Activar el seleccionado
            resultado = self.supabase.table('anios_epidemiologicos')\
                .update({'activo': True})\
                .eq('anio', anio)\
                .execute()
            self.invalidar_cache()
            if not resultado.data:
                # El año no existe: se deja activo el que estaba, para no quedar sin año activo.
                for previo in previos:
                    self.supabase.table('anios_epidemiologicos').update({'activo': True}).eq('anio', previo).execute()
                self.invalidar_cache()
                return False
            return True
        except Exception as e:
            print(f"Error al activar año: {e}")
            return False
    
    def eliminar_anio_epidemiologico(self, anio: int) -> bool:
        """Elimina un año epidemiologico (solo si no esta activo)."""
        try:
            anio_data = self.obtener_anio_epidemiologico(anio)
            if anio_data and anio_data.get('activo') == True:
                return False
            
            resultado = self.supabase.table('anios_epidemiologicos')\
                .delete()\
                .eq('anio', anio)\
                .execute()
            self.invalidar_cache()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al eliminar año: {e}")
            return False
    
    def obtener_anios_permitidos(self) -> List[int]:
        """Obtiene la lista de años permitidos para envios."""
        try:
            anio_activo = self.obtener_anio_activo_epidemiologico()
            if not anio_activo:
                return []
            
            permitir_anteriores = self.obtener_configuracion('permitir_anios_anteriores')
            permitir_anteriores = permitir_anteriores.lower() == 'true' if permitir_anteriores else True
            
            if not permitir_anteriores:
                return [anio_activo['anio']]
            
            años_anteriores = self.obtener_configuracion('años_anteriores_permitidos')
            try:
                max_anteriores = int(años_anteriores) if años_anteriores else 2
            except:
                max_anteriores = 2
            
            anios = [anio_activo['anio']]
            for i in range(1, max_anteriores + 1):
                anio_anterior = anio_activo['anio'] - i
                if self.obtener_anio_epidemiologico(anio_anterior):
                    anios.append(anio_anterior)
            
            return sorted(anios)
        except Exception as e:
            print(f"Error al obtener años permitidos: {e}")
            return []
    
    def obtener_semanas_por_anio(self, anio: int) -> int:
        """Obtiene el numero de semanas para un año."""
        try:
            anio_data = self.obtener_anio_epidemiologico(anio)
            if anio_data:
                return anio_data.get('semanas', 52)
            return 52
        except Exception as e:
            print(f"Error al obtener semanas por año: {e}")
            return 52
    
    def obtener_semanas_disponibles_por_anio(self, anio: int) -> List[int]:
        """Obtiene la lista de semanas disponibles para un año."""
        semanas = self.obtener_semanas_por_anio(anio)
        return list(range(1, semanas + 1))
    
    # ============================================================
    # METODOS PARA PROGRESO Y SEGUIMIENTO
    # ============================================================
    
    def obtener_envios_con_centros(
        self,
        anio: int,
        semana: Optional[int] = None,
        red: Optional[str] = None,
        limit: int = 2000
    ) -> List[Dict]:
        """Obtiene envios con los centros ya parseados."""
        return self.obtener_envios(
            semana=semana,
            red=red,
            anio=anio,
            limit=limit,
            incluir_atrasados=True
        )
    
    def obtener_centros_unicos_por_red(
        self,
        anio: int,
        semana: int,
        red: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """Obtiene los centros unicos que enviaron por red."""
        envios = self.obtener_envios(
            anio=anio,
            semana=semana,
            red=red,
            limit=2000
        )
        
        centros_por_red = {}
        for envio in envios:
            red_envio = envio.get('red', '')
            centros = envio.get('centros', [])
            
            if red_envio not in centros_por_red:
                centros_por_red[red_envio] = []
            
            for centro in centros:
                if isinstance(centro, dict):
                    nombre = centro.get('nombre', str(centro))
                else:
                    nombre = str(centro)
                
                if nombre not in centros_por_red[red_envio]:
                    centros_por_red[red_envio].append(nombre)
        
        return centros_por_red
    
    def obtener_resumen_general(self) -> Dict:
        """Obtiene un resumen general de la base de datos."""
        try:
            envios = self.supabase.table('envios').select('*', count='exact').execute()
            admins = self.supabase.table('administradores').select('*', count='exact').eq('activo', True).execute()
            carpetas = self.supabase.table('carpetas_drive').select('*', count='exact').execute()
            logs = self.supabase.table('logs').select('*', count='exact').execute()
            
            return {
                'total_envios': envios.count,
                'total_admins': admins.count,
                'total_carpetas': carpetas.count,
                'total_logs': logs.count,
                'tamano_db_mb': 0  # No aplica en Supabase
            }
        except Exception as e:
            print(f"Error al obtener resumen: {e}")
            return {
                'total_envios': 0,
                'total_admins': 0,
                'total_carpetas': 0,
                'total_logs': 0,
                'tamano_db_mb': 0
            }
    
    # ============================================================
    # METODOS PARA CENTROS EXCLUIDOS (NUEVO)
    # ============================================================
    
    def obtener_red_por_nombre(self, nombre: str) -> Optional[Dict]:
        """
        Obtiene una red por su nombre.
        """
        try:
            resultado = self.supabase.table('redes')\
                .select('*')\
                .eq('nombre', nombre)\
                .execute()
            return resultado.data[0] if resultado.data else None
        except Exception as e:
            print(f"Error al obtener red por nombre: {e}")
            return None
    
    def obtener_centros_excluidos(self, red_id: Optional[int] = None) -> List[Dict]:
        """
        Obtiene todos los centros excluidos.
        Si se especifica red_id, solo los de esa red.
        """
        try:
            query = self.supabase.table('centros_excluidos').select('*')
            if red_id:
                query = query.eq('red_id', red_id)
            query = query.order('red_id').order('centro_nombre')
            resultado = query.execute()
            return resultado.data
        except Exception as e:
            print(f"Error al obtener centros excluidos: {e}")
            return []
    
    def obtener_centros_excluidos_por_red(self, red_nombre: str) -> List[str]:
        """
        Obtiene los nombres de centros excluidos para una red especifica.
        """
        try:
            # Obtener red_id
            red = self.obtener_red_por_nombre(red_nombre)
            if not red:
                return []
            
            resultado = self.supabase.table('centros_excluidos')\
                .select('centro_nombre')\
                .eq('red_id', red['id'])\
                .execute()
            
            return [item['centro_nombre'] for item in resultado.data]
        except Exception as e:
            print(f"Error al obtener centros excluidos por red: {e}")
            return []
    
    def obtener_todas_las_exclusiones_agrupadas(self) -> Dict[str, List[str]]:
        """
        Obtiene todas las exclusiones agrupadas por red.
        Retorna: {"RED": ["centro1", "centro2", ...]}
        """
        try:
            # Obtener todas las exclusiones con nombre de red
            resultado = self.supabase.table('centros_excluidos')\
                .select('*, redes(nombre)')\
                .execute()
            
            exclusiones = {}
            for item in resultado.data:
                red_nombre = item.get('redes', {}).get('nombre', '')
                centro_nombre = item.get('centro_nombre', '')
                
                if red_nombre and centro_nombre:
                    if red_nombre not in exclusiones:
                        exclusiones[red_nombre] = []
                    if centro_nombre not in exclusiones[red_nombre]:
                        exclusiones[red_nombre].append(centro_nombre)
            
            return exclusiones
        except Exception as e:
            print(f"Error al obtener exclusiones agrupadas: {e}")
            return {}
    
    def agregar_centro_excluido(
        self, 
        red_nombre: str, 
        centro_nombre: str, 
        motivo: Optional[str] = None,
        creado_por: Optional[str] = None
    ) -> bool:
        """
        Agrega un centro a la lista de excluidos.
        """
        try:
            # Obtener red_id
            red = self.obtener_red_por_nombre(red_nombre)
            if not red:
                return False
            
            # Verificar si ya existe
            existente = self.supabase.table('centros_excluidos')\
                .select('id')\
                .eq('red_id', red['id'])\
                .eq('centro_nombre', centro_nombre)\
                .execute()
            
            if existente.data:
                return True  # Ya existe
            
            data = {
                'red_id': red['id'],
                'centro_nombre': centro_nombre,
                'motivo': motivo,
                'creado_por': creado_por,
                'fecha_exclusion': self._obtener_fecha_actual_iso()
            }
            resultado = self.supabase.table('centros_excluidos').insert(data).execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al agregar centro excluido: {e}")
            return False
    
    def eliminar_centro_excluido(self, red_nombre: str, centro_nombre: str) -> bool:
        """
        Elimina un centro de la lista de excluidos (reincorporacion).
        """
        try:
            # Obtener red_id
            red = self.obtener_red_por_nombre(red_nombre)
            if not red:
                return False
            
            resultado = self.supabase.table('centros_excluidos')\
                .delete()\
                .eq('red_id', red['id'])\
                .eq('centro_nombre', centro_nombre)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al eliminar centro excluido: {e}")
            return False
    
    def limpiar_centros_excluidos(self, red_nombre: str) -> bool:
        """
        Elimina todos los centros excluidos de una red.
        """
        try:
            red = self.obtener_red_por_nombre(red_nombre)
            if not red:
                return False
            
            resultado = self.supabase.table('centros_excluidos')\
                .delete()\
                .eq('red_id', red['id'])\
                .execute()
            return True
        except Exception as e:
            print(f"Error al limpiar centros excluidos: {e}")
            return False
    
    def verificar_centro_excluido(self, red_nombre: str, centro_nombre: str) -> bool:
        """
        Verifica si un centro especifico esta excluido.
        """
        try:
            red = self.obtener_red_por_nombre(red_nombre)
            if not red:
                return False
            
            resultado = self.supabase.table('centros_excluidos')\
                .select('id')\
                .eq('red_id', red['id'])\
                .eq('centro_nombre', centro_nombre)\
                .execute()
            return len(resultado.data) > 0
        except Exception as e:
            print(f"Error al verificar centro excluido: {e}")
            return False
    
    def contar_centros_excluidos(self, red_nombre: str) -> int:
        """
        Cuenta cuantos centros estan excluidos en una red.
        """
        try:
            red = self.obtener_red_por_nombre(red_nombre)
            if not red:
                return 0
            
            resultado = self.supabase.table('centros_excluidos')\
                .select('id', count='exact')\
                .eq('red_id', red['id'])\
                .execute()
            return resultado.count
        except Exception as e:
            print(f"Error al contar centros excluidos: {e}")
            return 0

    # ============================================================
    # SOLICITUDES DE CAMBIO DE CONTRASEÑA (red <-> administrador)
    # Tablas: solicitudes_password y solicitudes_password_mensajes
    # (ver sql/09_solicitudes_cambio_password.sql)
    # ============================================================

    def solicitudes_password_disponibles(self) -> bool:
        """True si las tablas de solicitudes existen (migración 09 ejecutada)."""
        ahora = datetime.now().timestamp()
        cache = getattr(self, '_sol_disp_cache', None)
        if cache and (cache[0] or ahora - cache[1] < 30):
            return cache[0]
        try:
            self.supabase.table('solicitudes_password').select('id').limit(1).execute()
            self.supabase.table('solicitudes_password_mensajes').select('id').limit(1).execute()
            disponible = True
        except Exception as e:
            print(f"Solicitudes de contraseña no disponibles: {e}")
            disponible = False
        self._sol_disp_cache = (disponible, ahora)
        return disponible

    def crear_solicitud_password(self, codigo: str, red: str, nombre: str, correo: str) -> Optional[Dict]:
        try:
            r = self.supabase.table('solicitudes_password').insert({
                'codigo': codigo, 'red': red, 'nombre': nombre, 'correo': correo, 'estado': 'PENDIENTE'
            }).execute()
            return r.data[0] if r.data else None
        except Exception as e:
            print(f"Error al crear solicitud de contraseña: {e}")
            return None

    def obtener_solicitud_password(self, solicitud_id) -> Optional[Dict]:
        try:
            r = self.supabase.table('solicitudes_password').select('*').eq('id', solicitud_id).execute()
            return r.data[0] if r.data else None
        except Exception as e:
            print(f"Error al obtener solicitud de contraseña: {e}")
            return None

    def listar_solicitudes_password(
        self, red: Optional[str] = None, estados: Optional[List[str]] = None, limit: int = 100
    ) -> List[Dict]:
        """Solicitudes, las más recientes primero."""
        try:
            q = self.supabase.table('solicitudes_password').select('*')
            if red:
                q = q.eq('red', red)
            if estados:
                q = q.in_('estado', estados)
            r = q.order('fecha_creacion', desc=True).limit(limit).execute()
            return r.data or []
        except Exception as e:
            print(f"Error al listar solicitudes de contraseña: {e}")
            return []

    def contar_solicitudes_password(self, estado: str = 'PENDIENTE') -> int:
        try:
            r = self.supabase.table('solicitudes_password').select('id', count='exact').eq('estado', estado).execute()
            return int(r.count or 0)
        except Exception:
            return 0

    def actualizar_solicitud_password(self, solicitud_id, **campos) -> bool:
        """Actualiza estado, fechas y responsable de una solicitud."""
        permitidos = {'estado', 'fecha_resolucion', 'resuelto_por', 'fecha_vencimiento', 'fecha_uso'}
        datos = {k: v for k, v in campos.items() if k in permitidos}
        if not datos:
            return True
        try:
            r = self.supabase.table('solicitudes_password').update(datos).eq('id', solicitud_id).execute()
            return len(r.data) > 0
        except Exception as e:
            print(f"Error al actualizar solicitud de contraseña: {e}")
            return False

    def agregar_mensaje_solicitud(self, solicitud_id, autor_tipo: str, autor: str, mensaje: str) -> bool:
        try:
            r = self.supabase.table('solicitudes_password_mensajes').insert({
                'solicitud_id': solicitud_id, 'autor_tipo': autor_tipo, 'autor': autor, 'mensaje': mensaje
            }).execute()
            return len(r.data) > 0
        except Exception as e:
            print(f"Error al guardar mensaje de solicitud: {e}")
            return False

    def obtener_mensajes_solicitud(self, solicitud_id) -> List[Dict]:
        try:
            r = self.supabase.table('solicitudes_password_mensajes').select('*')\
                .eq('solicitud_id', solicitud_id).order('fecha').order('id').execute()
            return r.data or []
        except Exception as e:
            print(f"Error al obtener mensajes de solicitud: {e}")
            return []


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

_db_manager = None


def get_db_manager() -> DatabaseManager:
    """
    Retorna la instancia unica del DatabaseManager.
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def limpiar_cache():
    """
    Limpia la instancia cacheada del DatabaseManager.
    """
    global _db_manager
    _db_manager = None