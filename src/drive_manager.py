# src/drive_manager.py
"""
Gestión de Google Drive para el sistema de reportes.
Versión con CUENTA DE SERVICIO (¡NO EXPIERA!).
"""

import os
import io
import pickle
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime

# ✅ NUEVO: Importación para Service Account
from google.oauth2 import service_account

# Importaciones para OAuth (se mantienen por compatibilidad)
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

from src.config import Config
from utils.helpers import sanitizar_nombre


def _escapar_query_drive(valor: str) -> str:
    """
    Escapa un valor para insertarlo dentro de una cadena `q=` de la API
    de Google Drive (que usa comillas simples como delimitador). Sin
    esto, un nombre o término de búsqueda con una comilla simple podría
    alterar la consulta armada por f-string (p. ej. cerrar el valor
    antes de tiempo y agregar condiciones `or ...` propias). La mayoría
    de los llamadores ya pasan el nombre por sanitizar_nombre() antes
    de llegar aquí, pero esta función no debería depender de eso.
    Ver: https://developers.google.com/drive/api/guides/ref-search-terms
    """
    if valor is None:
        return ""
    return str(valor).replace("\\", "\\\\").replace("'", "\\'")


class DriveManager:
    """
    Gestor de operaciones en Google Drive con autenticación SERVICE ACCOUNT.
    ¡NUNCA EXPIERA!
    """
    
    # Scope 'drive' (no 'drive.file'): con 'drive.file' la cuenta de servicio
    # solo ve lo que ELLA misma creo, y no puede ni consultar la carpeta raiz
    # compartida (da 404). El alcance real sigue limitado a lo que se haya
    # compartido con la cuenta de servicio (la Unidad compartida).
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    def __init__(self):
        """Inicializa el cliente de Google Drive con Service Account."""
        self.folder_id_root = Config.GOOGLE_DRIVE_FOLDER_ID
        self.service = self._autenticar()
        self._cache_carpetas = {}
    
    def _autenticar(self):
        """
        Autentica con CUENTA DE SERVICIO.
        ¡NUNCA EXPIERA! ✅
        """
        # Ruta al archivo JSON de la cuenta de servicio
        creds_path = Config.BASE_DIR / Config.GOOGLE_CREDENTIALS_PATH
        
        if not creds_path.exists():
            raise FileNotFoundError(
                f"Archivo service_account.json no encontrado en: {creds_path}\n"
                "Descárgalo desde Google Cloud Console -> Credenciales -> Cuenta de servicio"
            )
        
        # ✅ Con Service Account, ¡NO EXPIERA!
        creds = service_account.Credentials.from_service_account_file(
            str(creds_path),
            scopes=self.SCOPES
        )
        
        return build('drive', 'v3', credentials=creds)
    
    # ============================================================
    # MÉTODOS PARA CARPETAS
    # ============================================================
    
    def crear_carpeta(self, nombre: str, padre_id: Optional[str] = None) -> str:
        """
        Crea una carpeta en Drive.
        Si ya existe, retorna su ID.
        """
        nombre_limpio = sanitizar_nombre(nombre)
        
        # Verificar en caché primero
        cache_key = f"{padre_id}_{nombre_limpio}"
        if cache_key in self._cache_carpetas:
            return self._cache_carpetas[cache_key]
        
        # Buscar si ya existe
        existente = self._buscar_carpeta(nombre_limpio, padre_id)
        if existente:
            self._cache_carpetas[cache_key] = existente
            return existente
        
        # Crear nueva carpeta
        metadata = {
            'name': nombre_limpio,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if padre_id:
            metadata['parents'] = [padre_id]
        
        try:
            carpeta = self.service.files().create(
                supportsAllDrives=True,
                body=metadata,
                fields='id'
            ).execute()
            
            carpeta_id = carpeta.get('id')
            self._cache_carpetas[cache_key] = carpeta_id
            return carpeta_id
        except HttpError as e:
            print(f"Error al crear carpeta '{nombre_limpio}': {e}")
            raise
    
    def _buscar_carpeta(self, nombre: str, padre_id: Optional[str] = None) -> Optional[str]:
        """Busca una carpeta por nombre en un directorio padre."""
        query = f"name='{_escapar_query_drive(nombre)}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if padre_id:
            query += f" and '{_escapar_query_drive(padre_id)}' in parents"
        
        try:
            results = self.service.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            return files[0]['id'] if files else None
        except HttpError as e:
            print(f"Error al buscar carpeta '{nombre}': {e}")
            return None
    
    def obtener_o_crear_ruta(self, ruta: str, raiz_id: Optional[str] = None) -> str:
        """
        Crea la estructura de carpetas anidadas.
        Ejemplo: "ALMENARA/SEMANA_25/ANCIJE"
        Retorna el ID de la carpeta final.

        `raiz_id`: carpeta de Drive desde la que se cuelga la ruta (por
        ejemplo, la carpeta de duplicados). Si no se indica, se usa la
        carpeta principal configurada en GOOGLE_DRIVE_FOLDER_ID.
        """
        partes = [p for p in ruta.split('/') if p.strip()]
        padre_id = raiz_id or self.folder_id_root
        
        for parte in partes:
            parte_limpia = sanitizar_nombre(parte)
            padre_id = self.crear_carpeta(parte_limpia, padre_id)
        
        return padre_id
    
    def listar_subcarpetas(self, carpeta_id: str) -> List[Dict]:
        """
        Lista todas las subcarpetas de una carpeta.
        """
        query = f"'{_escapar_query_drive(carpeta_id)}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        try:
            results = self.service.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives',
                fields='files(id, name, createdTime)',
                pageSize=100
            ).execute()
            
            return results.get('files', [])
        except HttpError as e:
            print(f"Error al listar subcarpetas: {e}")
            return []
    
    def obtener_carpeta_por_nombre(self, nombre: str, padre_id: Optional[str] = None) -> Optional[str]:
        """
        Obtiene el ID de una carpeta por su nombre.
        """
        return self._buscar_carpeta(sanitizar_nombre(nombre), padre_id)
    
    # ============================================================
    # MÉTODOS PARA ARCHIVOS
    # ============================================================
    
    def subir_archivo(
        self,
        ruta_local: str,
        nombre_archivo: str,
        carpeta_destino: str,
        mimetype: Optional[str] = None,
        raiz_id: Optional[str] = None
    ) -> Dict:
        """
        Sube un archivo a Google Drive.
        `raiz_id` permite subirlo bajo otra carpeta raíz (p. ej. duplicados).
        """
        # Verificar que el archivo existe
        if not os.path.exists(ruta_local):
            raise FileNotFoundError(f"Archivo local no encontrado: {ruta_local}")
        
        # Obtener o crear la carpeta destino
        carpeta_id = self.obtener_o_crear_ruta(carpeta_destino, raiz_id)
        
        # Preparar metadata
        metadata = {
            'name': nombre_archivo,
            'parents': [carpeta_id]
        }
        
        # Subir archivo
        media = MediaFileUpload(
            ruta_local,
            mimetype=mimetype,
            resumable=True
        )
        
        try:
            archivo = self.service.files().create(
                supportsAllDrives=True,
                body=metadata,
                media_body=media,
                fields='id, name, webViewLink, size, createdTime'
            ).execute()
            
            return {
                'id': archivo.get('id'),
                'nombre': archivo.get('name'),
                'link': archivo.get('webViewLink'),
                'tamaño': archivo.get('size', 0),
                'fecha_creacion': archivo.get('createdTime')
            }
        except HttpError as e:
            print(f"Error al subir archivo '{nombre_archivo}': {e}")
            raise
    
    def subir_desde_bytes(
        self,
        contenido: bytes,
        nombre_archivo: str,
        carpeta_destino: str,
        mimetype: str = 'application/zip',
        raiz_id: Optional[str] = None
    ) -> Dict:
        """
        Sube un archivo desde bytes a Google Drive.
        """
        carpeta_id = self.obtener_o_crear_ruta(carpeta_destino, raiz_id)
        
        metadata = {
            'name': nombre_archivo,
            'parents': [carpeta_id]
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(contenido),
            mimetype=mimetype,
            resumable=True
        )
        
        try:
            archivo = self.service.files().create(
                supportsAllDrives=True,
                body=metadata,
                media_body=media,
                fields='id, name, webViewLink, size, createdTime'
            ).execute()
            
            return {
                'id': archivo.get('id'),
                'nombre': archivo.get('name'),
                'link': archivo.get('webViewLink'),
                'tamaño': archivo.get('size', 0),
                'fecha_creacion': archivo.get('createdTime')
            }
        except HttpError as e:
            print(f"Error al subir archivo desde bytes '{nombre_archivo}': {e}")
            raise
    
    # ============================================================
    # MÉTODOS PARA LISTAR Y CONSULTAR
    # ============================================================
    
    def listar_archivos_en_carpeta(self, carpeta_id: str) -> List[Dict]:
        """
        Lista todos los archivos en una carpeta de Drive.
        """
        query = f"'{_escapar_query_drive(carpeta_id)}' in parents and trashed=false"
        
        try:
            results = self.service.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives',
                fields='files(id, name, size, createdTime, webViewLink, mimeType)',
                pageSize=100
            ).execute()
            
            return results.get('files', [])
        except HttpError as e:
            print(f"Error al listar archivos: {e}")
            return []
    
    def obtener_info_archivo(self, archivo_id: str) -> Dict:
        """
        Obtiene información detallada de un archivo.
        """
        try:
            archivo = self.service.files().get(
                supportsAllDrives=True,
                fileId=archivo_id,
                fields='id, name, size, createdTime, webViewLink, parents, mimeType'
            ).execute()
            
            return archivo
        except HttpError as e:
            print(f"Error al obtener información del archivo: {e}")
            return {}
    
    @staticmethod
    def _motivo_http(e: HttpError) -> str:
        """Texto corto y legible del motivo de un error de la API de Drive."""
        estado = getattr(getattr(e, 'resp', None), 'status', None)
        try:
            import json as _json
            detalle = _json.loads(e.content.decode('utf-8')).get('error', {})
            texto = detalle.get('message') or ''
        except Exception:
            texto = ''
        if estado in (401, 403):
            return (f"Drive rechazó la operación por permisos ({estado}). La cuenta de servicio necesita "
                    f"poder mover a la papelera los archivos de esa carpeta. {texto}").strip()
        return f"Error de Drive ({estado}). {texto}".strip()

    def eliminar_archivo_detallado(self, archivo_id: str, definitivo: bool = False) -> Tuple[bool, str]:
        """
        Quita un archivo de Drive y dice qué pasó realmente.

        Con definitivo=True se borra sin pasar por la papelera (libera espacio,
        pero NO se puede recuperar); exige que la cuenta de servicio tenga rol
        de Administrador del archivo.

        Primero lo envía a la PAPELERA (lo permite el rol «Gestor de contenido»
        y se puede recuperar durante 30 días). Solo si Drive no lo permite
        intenta el borrado definitivo (exige rol de administrador).
        Un archivo que ya no existe (404) cuenta como eliminado.

        Devuelve (ok, detalle).
        """
        archivo_id = (archivo_id or '').strip()
        if not archivo_id:
            return False, "El registro no tiene un archivo asociado en Drive."
        if definitivo:
            try:
                self.service.files().delete(fileId=archivo_id, supportsAllDrives=True).execute()
                return True, "Archivo eliminado definitivamente de Drive."
            except HttpError as e_borrar:
                if getattr(e_borrar.resp, 'status', None) == 404:
                    return True, "El archivo ya no estaba en Drive."
                print(f"Error al eliminar definitivamente {archivo_id}: {e_borrar}")
                return False, self._motivo_http(e_borrar)
            except Exception as e:
                return False, f"Error inesperado: {e}"
        try:
            self.service.files().update(
                fileId=archivo_id, body={'trashed': True},
                supportsAllDrives=True, fields='id, trashed'
            ).execute()
            return True, "Archivo enviado a la papelera de Drive."
        except HttpError as e_papelera:
            if getattr(e_papelera.resp, 'status', None) == 404:
                return True, "El archivo ya no estaba en Drive."
            try:
                self.service.files().delete(fileId=archivo_id, supportsAllDrives=True).execute()
                return True, "Archivo eliminado de Drive."
            except HttpError as e_borrar:
                if getattr(e_borrar.resp, 'status', None) == 404:
                    return True, "El archivo ya no estaba en Drive."
                motivo = self._motivo_http(e_papelera)
                print(f"Error al eliminar archivo {archivo_id}: papelera={e_papelera} borrar={e_borrar}")
                return False, motivo
        except Exception as e:
            print(f"Error inesperado al eliminar archivo {archivo_id}: {e}")
            return False, f"Error inesperado: {e}"

    def eliminar_archivo(self, archivo_id: str) -> bool:
        """Elimina (papelera) un archivo de Drive. Ver eliminar_archivo_detallado."""
        return self.eliminar_archivo_detallado(archivo_id)[0]
    
    def mover_archivo(self, archivo_id: str, nueva_carpeta_id: str) -> bool:
        """
        Mueve un archivo a una nueva carpeta.
        """
        try:
            archivo = self.obtener_info_archivo(archivo_id)
            padres_actuales = archivo.get('parents', [])
            
            self.service.files().update(
                supportsAllDrives=True,
                fileId=archivo_id,
                addParents=nueva_carpeta_id,
                removeParents=','.join(padres_actuales),
                fields='id, parents'
            ).execute()
            return True
        except HttpError as e:
            print(f"Error al mover archivo: {e}")
            return False
    
    def mover_a_ruta(self, archivo_id: str, carpeta_destino: str, raiz_id: Optional[str] = None) -> Dict:
        """
        Mueve un archivo (sin borrarlo) a la ruta indicada bajo `raiz_id` (o la carpeta principal).
        Devuelve {'id', 'ruta'}: en Drive el id no cambia al mover.
        """
        carpeta_id = self.obtener_o_crear_ruta(carpeta_destino, raiz_id)
        if not self.mover_archivo(archivo_id, carpeta_id):
            raise RuntimeError("Drive no permitió mover el archivo (¿falta permiso de editor sobre la carpeta?).")
        return {'id': archivo_id, 'ruta': carpeta_destino}

    def copiar_archivo(self, archivo_id: str, nuevo_nombre: str) -> Optional[Dict]:
        """
        Crea una copia de un archivo.
        """
        try:
            archivo = self.service.files().copy(
                supportsAllDrives=True,
                fileId=archivo_id,
                body={'name': nuevo_nombre},
                fields='id, name, webViewLink'
            ).execute()
            
            return archivo
        except HttpError as e:
            print(f"Error al copiar archivo: {e}")
            return None
    
    def descargar_archivo(self, archivo_id: str) -> Optional[bytes]:
        """
        Descarga el contenido de un archivo de Drive.
        """
        return self.descargar_archivo_detallado(archivo_id)[0]

    def descargar_archivo_detallado(self, archivo_id: str) -> Tuple[Optional[bytes], str]:
        """
        Descarga un archivo de Drive y, si no puede, dice POR QUÉ (permisos, no existe, sin conexión…).
        Devuelve (contenido, "") o (None, motivo).
        """
        archivo_id = (archivo_id or '').strip()
        if not archivo_id:
            return None, "El registro no tiene un archivo asociado en Drive."
        try:
            request = self.service.files().get_media(fileId=archivo_id, supportsAllDrives=True)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            return file_content.getvalue(), ""
        except HttpError as e:
            print(f"Error al descargar archivo {archivo_id}: {e}")
            estado = getattr(getattr(e, 'resp', None), 'status', None)
            if estado == 404:
                return None, ("Drive no encontró el archivo (404): fue movido o eliminado, o la cuenta de servicio "
                              "no tiene acceso a su carpeta.")
            if estado in (401, 403):
                try:
                    import json as _json
                    texto = _json.loads(e.content.decode('utf-8')).get('error', {}).get('message', '')
                except Exception:
                    texto = ''
                return None, (f"Drive negó la lectura ({estado}). Comparta la carpeta con la cuenta de servicio "
                              f"(rol Lector o superior) o revise sus credenciales. {texto}").strip()
            return None, self._motivo_http(e)
        except Exception as e:
            print(f"Error al descargar archivo {archivo_id}: {e}")
            return None, f"No se pudo conectar con Drive: {type(e).__name__}: {e}"
    
    # ============================================================
    # MÉTODOS UTILITARIOS
    # ============================================================
    
    def construir_ruta_drive(
        self,
        red: str,
        semana: int,
        centros: List[str],
        nombre_archivo: str
    ) -> Tuple[str, str]:
        """
        Construye la ruta completa en Drive para un archivo.
        """
        red_limpia = sanitizar_nombre(red)
        semana_str = f"SEMANA_{str(semana).zfill(2)}"
        
        if len(centros) > 1:
            carpeta_destino = f"{red_limpia}/{semana_str}"
        else:
            centro_limpio = sanitizar_nombre(centros[0]) if centros else "general"
            carpeta_destino = f"{red_limpia}/{semana_str}/{centro_limpio}"
        
        return carpeta_destino, nombre_archivo
    
    def obtener_estructura_completa(self) -> Dict:
        """
        Obtiene la estructura completa de carpetas y archivos.
        """
        estructura = {
            'carpeta_raiz': self.folder_id_root,
            'redes': []
        }
        
        redes = self.listar_subcarpetas(self.folder_id_root)
        
        for red in redes:
            red_info = {
                'id': red['id'],
                'nombre': red['name'],
                'semanas': []
            }
            
            semanas = self.listar_subcarpetas(red['id'])
            for semana in semanas:
                semana_info = {
                    'id': semana['id'],
                    'nombre': semana['name'],
                    'centros': [],
                    'archivos': []
                }
                
                contenidos = self.listar_archivos_en_carpeta(semana['id'])
                subcarpetas = self.listar_subcarpetas(semana['id'])
                
                semana_info['centros'] = subcarpetas
                semana_info['archivos'] = contenidos
                
                red_info['semanas'].append(semana_info)
            
            estructura['redes'].append(red_info)
        
        return estructura
    
    def obtener_archivos_por_red_semana(self, red: str, semana: int) -> List[Dict]:
        """
        Obtiene todos los archivos de una red y semana específica.
        """
        red_limpia = sanitizar_nombre(red)
        semana_str = f"SEMANA_{str(semana).zfill(2)}"
        
        # Buscar carpeta de la red
        red_id = self.obtener_carpeta_por_nombre(red_limpia, self.folder_id_root)
        if not red_id:
            return []
        
        # Buscar carpeta de la semana
        semana_id = self.obtener_carpeta_por_nombre(semana_str, red_id)
        if not semana_id:
            return []
        
        # Listar archivos en la carpeta de la semana
        archivos = self.listar_archivos_en_carpeta(semana_id)
        
        # Listar archivos en subcarpetas (centros)
        subcarpetas = self.listar_subcarpetas(semana_id)
        for subcarpeta in subcarpetas:
            archivos_subcarpeta = self.listar_archivos_en_carpeta(subcarpeta['id'])
            archivos.extend(archivos_subcarpeta)
        
        return archivos
    
    # ============================================================
    # MÉTODOS DE RESPALDO Y MANTENIMIENTO
    # ============================================================
    
    def crear_backup(self, nombre_backup: str) -> str:
        """
        Crea una copia de respaldo de la estructura actual.
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_completo = f"BACKUP_{sanitizar_nombre(nombre_backup)}_{timestamp}"
        carpeta_backup = self.crear_carpeta(
            nombre_completo,
            self.folder_id_root
        )
        return carpeta_backup
    
    def mover_a_cuarentena(
        self,
        archivo_id: str,
        motivo: str = "observacion"
    ) -> bool:
        """
        Mueve un archivo a la carpeta de cuarentena.
        """
        carpeta_cuarentena = self.crear_carpeta(
            "CUARENTENA",
            self.folder_id_root
        )
        
        carpeta_motivo = self.crear_carpeta(
            sanitizar_nombre(motivo),
            carpeta_cuarentena
        )
        
        return self.mover_archivo(archivo_id, carpeta_motivo)
    
    def limpiar_cache(self):
        """Limpia la caché de carpetas."""
        self._cache_carpetas.clear()
    
    def verificar_conexion(self) -> Tuple[bool, str]:
        """
        Verifica que la conexión con Google Drive funcione.
        """
        try:
            self.service.files().get(
                supportsAllDrives=True,
                fileId=self.folder_id_root,
                fields='id, name'
            ).execute()
            return True, "Conexión exitosa con Google Drive"
        except HttpError as e:
            return False, f"Error de conexión: {e}"
        except Exception as e:
            return False, f"Error inesperado: {e}"
    
    def probar_carpeta(self, folder_id: str) -> Dict:
        """
        Comprueba el acceso de la cuenta de servicio a una carpeta de Drive.
        Devuelve {ok, nombre, escribir, papelera, detalle}.
        """
        folder_id = (folder_id or '').strip()
        if not folder_id:
            return {'ok': False, 'nombre': '', 'escribir': False, 'papelera': False,
                    'detalle': 'No hay un ID configurado (revise el archivo .env).'}
        try:
            info = self.service.files().get(
                fileId=folder_id, supportsAllDrives=True,
                fields='id, name, mimeType, capabilities(canAddChildren, canTrash, canDelete)'
            ).execute()
        except HttpError as e:
            estado = getattr(getattr(e, 'resp', None), 'status', None)
            if estado == 404:
                return {'ok': False, 'nombre': '', 'escribir': False, 'papelera': False,
                        'detalle': 'Drive no encuentra la carpeta: revise el ID o comparta la carpeta con la cuenta de servicio.'}
            return {'ok': False, 'nombre': '', 'escribir': False, 'papelera': False,
                    'detalle': self._motivo_http(e)}
        except Exception as e:
            return {'ok': False, 'nombre': '', 'escribir': False, 'papelera': False, 'detalle': f'Error inesperado: {e}'}
        if info.get('mimeType') != 'application/vnd.google-apps.folder':
            return {'ok': False, 'nombre': info.get('name', ''), 'escribir': False, 'papelera': False,
                    'detalle': 'El ID corresponde a un archivo, no a una carpeta.'}
        cap = info.get('capabilities') or {}
        escribir, papelera = bool(cap.get('canAddChildren')), bool(cap.get('canTrash') or cap.get('canDelete'))
        if not escribir:
            detalle = 'Solo lectura: la cuenta de servicio debe ser «Gestor de contenido» o «Editor».'
        elif not papelera:
            detalle = 'Puede escribir, pero no quitar archivos (necesita «Gestor de contenido» o «Editor»).'
        else:
            detalle = 'Acceso correcto (escribir y quitar archivos).'
        return {'ok': escribir, 'nombre': info.get('name', ''), 'escribir': escribir, 'papelera': papelera, 'detalle': detalle}

    def obtener_espacio_usado(self) -> Dict:
        """
        Obtiene información sobre el espacio usado en Drive.
        """
        try:
            about = self.service.about().get(
                fields='storageQuota'
            ).execute()
            
            quota = about.get('storageQuota', {})
            
            return {
                'limite_bytes': quota.get('limit', 0),
                'usado_bytes': quota.get('usage', 0),
                'usado_drive_bytes': quota.get('usageInDrive', 0),
                'usado_trash_bytes': quota.get('usageInDriveTrash', 0)
            }
        except HttpError as e:
            print(f"Error al obtener espacio usado: {e}")
            return {}
    
    def buscar_archivos(self, termino: str, carpeta_id: Optional[str] = None) -> List[Dict]:
        """
        Busca archivos por nombre en Drive.
        """
        query = f"name contains '{_escapar_query_drive(termino)}' and trashed=false"
        if carpeta_id:
            query += f" and '{_escapar_query_drive(carpeta_id)}' in parents"
        
        try:
            results = self.service.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives',
                fields='files(id, name, size, createdTime, webViewLink, parents)',
                pageSize=50
            ).execute()
            
            return results.get('files', [])
        except HttpError as e:
            print(f"Error al buscar archivos: {e}")
            return []


# ============================================================
# LOCAL DRIVE MANAGER (FALLBACK)
# ============================================================

class LocalDriveManager:
    """Gestor de almacenamiento LOCAL (sin Google Drive)."""
    
    def __init__(self):
        self.folder_id_root = "LOCAL"
        self._cache_carpetas = {}
    
    def subir_archivo(self, ruta_local, nombre_archivo, carpeta_destino, mimetype=None, raiz_id=None):
        """Guarda el archivo LOCALMENTE (si se pide otra raíz, va a una carpeta DUPLICADOS)."""
        from src.config import Config
        import shutil
        
        # Crear carpeta destino
        if raiz_id:
            carpeta_destino = f"DUPLICADOS/{carpeta_destino}"
        destino = Config.STORAGE_DIR / "envios" / carpeta_destino
        destino.mkdir(parents=True, exist_ok=True)
        
        # Copiar archivo
        ruta_destino = destino / nombre_archivo
        shutil.copy2(ruta_local, ruta_destino)
        
        return {
            'id': str(ruta_destino),
            'nombre': nombre_archivo,
            'link': f'file://{ruta_destino}',
            'tamaño': ruta_destino.stat().st_size,
            'fecha_creacion': datetime.now().isoformat()
        }
    
    def verificar_conexion(self):
        return True, "Modo LOCAL (sin Google Drive)"
    
    def crear_carpeta(self, nombre, padre_id=None):
        return f"LOCAL_{nombre}"
    
    def obtener_carpeta_por_nombre(self, nombre, padre_id=None):
        return f"LOCAL_{nombre}"
    
    def listar_subcarpetas(self, carpeta_id):
        return []
    
    def listar_archivos_en_carpeta(self, carpeta_id):
        return []
    
    def obtener_info_archivo(self, archivo_id):
        return {}
    
    def probar_carpeta(self, folder_id):
        return {'ok': True, 'nombre': 'almacenamiento local', 'escribir': True, 'papelera': True,
                'detalle': 'Modo local: los archivos se guardan en el servidor.'}

    def descargar_archivo_detallado(self, archivo_id):
        datos = self.descargar_archivo(archivo_id)
        return (datos, "") if datos is not None else (None, "El archivo no está en el almacenamiento local.")

    def descargar_archivo(self, archivo_id):
        """Lee un archivo del almacenamiento local (solo dentro de storage/)."""
        try:
            ruta = Path(str(archivo_id)).resolve()
            if Config.STORAGE_DIR.resolve() not in ruta.parents or not ruta.is_file():
                return None
            return ruta.read_bytes()
        except Exception as e:
            print(f"No se pudo leer el archivo local: {e}")
            return None

    def eliminar_archivo_detallado(self, archivo_id, definitivo=False):
        """Borra un archivo del almacenamiento local (solo dentro de storage/)."""
        try:
            ruta = Path(str(archivo_id)).resolve()
            base = Config.STORAGE_DIR.resolve()
            if base not in ruta.parents:
                return False, "La ruta del archivo está fuera de la carpeta de almacenamiento."
            if not ruta.exists():
                return True, "El archivo ya no existía."
            ruta.unlink()
            return True, "Archivo eliminado del almacenamiento local."
        except Exception as e:
            return False, f"No se pudo eliminar el archivo local: {e}"

    def eliminar_archivo(self, archivo_id):
        return self.eliminar_archivo_detallado(archivo_id)[0]
    
    def mover_archivo(self, archivo_id, nueva_carpeta_id):
        return True

    def mover_a_ruta(self, archivo_id, carpeta_destino, raiz_id=None):
        """Mueve un archivo de storage/ a otra carpeta de storage/ (sin borrarlo). El id es la ruta, así que cambia."""
        import shutil
        origen = Path(str(archivo_id)).resolve()
        base = Config.STORAGE_DIR.resolve()
        if base not in origen.parents or not origen.is_file():
            raise RuntimeError("El archivo no está en el almacenamiento local.")
        if raiz_id:
            carpeta_destino = f"REEMPLAZADOS/{carpeta_destino}" if not str(carpeta_destino).startswith("REEMPLAZADOS") else carpeta_destino
        destino_dir = (Config.STORAGE_DIR / "envios" / carpeta_destino)
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / origen.name
        shutil.move(str(origen), str(destino))
        return {'id': str(destino), 'ruta': carpeta_destino}
    
    def construir_ruta_drive(self, red, semana, centros, nombre_archivo):
        from utils.helpers import sanitizar_nombre
        red_limpia = sanitizar_nombre(red)
        semana_str = f"SEMANA_{str(semana).zfill(2)}"
        if len(centros) > 1:
            carpeta_destino = f"{red_limpia}/{semana_str}"
        else:
            centro_limpio = sanitizar_nombre(centros[0]) if centros else "general"
            carpeta_destino = f"{red_limpia}/{semana_str}/{centro_limpio}"
        return carpeta_destino, nombre_archivo
    
    def limpiar_cache(self):
        self._cache_carpetas.clear()
    
    def obtener_espacio_usado(self):
        return {'limite_bytes': 0, 'usado_bytes': 0}
    
    def buscar_archivos(self, termino, carpeta_id=None):
        return []


# ============================================================
# INSTANCIA GLOBAL (SINGLETON)
# ============================================================

_drive_manager = None

def get_drive_manager():
    """
    Retorna la instancia del gestor de almacenamiento.
    Si STORAGE_MODE=local, usa LocalDriveManager.
    Si STORAGE_MODE=drive, usa DriveManager con Service Account.
    """
    global _drive_manager
    
    # Si está en modo local, usar LocalDriveManager
    if os.getenv("STORAGE_MODE", "").lower() == "local":
        if _drive_manager is None or not isinstance(_drive_manager, LocalDriveManager):
            _drive_manager = LocalDriveManager()
        return _drive_manager
    
    # Si no, intentar con Drive (Service Account)
    try:
        if _drive_manager is None:
            _drive_manager = DriveManager()
    except Exception as e:
        print(f"⚠️ Error con Drive: {e}")
        # Pasar a modo local EN SILENCIO guardaría los envíos fuera de Drive sin que nadie lo note.
        # Por seguridad ya no se hace salvo que se pida expresamente (STORAGE_FALLBACK_LOCAL=true).
        if os.getenv("STORAGE_FALLBACK_LOCAL", "").strip().lower() in ("1", "true", "si", "sí", "yes"):
            print("🔄 Usando modo LOCAL como fallback (STORAGE_FALLBACK_LOCAL=true)")
            _drive_manager = LocalDriveManager()
        else:
            _drive_manager = None
            raise RuntimeError(f"No se pudo conectar con Google Drive: {type(e).__name__}: {e}") from e
    
    return _drive_manager


def limpiar_cache():
    """Limpia la instancia cacheada del DriveManager."""
    global _drive_manager
    _drive_manager = None