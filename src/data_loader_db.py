# src/data_loader_db.py
"""
DataLoader que obtiene redes y centros desde Supabase.
Mantiene la misma interfaz que DataLoader (REDES2.txt) para migracion gradual.
"""

from typing import Dict, List, Optional, Any
from src.db_manager import get_db_manager


class DataLoaderDB:
    """Cargador de datos maestros desde Supabase."""

    def __init__(self):
        """Inicializa el cargador y carga los datos desde Supabase."""
        self.db = get_db_manager()
        self._redes_cache = None
        self._centros_cache = None
        self._cargar_datos()

    def _cargar_datos(self):
        """
        Carga redes y centros desde Supabase y los almacena en cache.
        """
        try:
            # Cargar redes
            resultado = self.db.supabase.table('redes')\
                .select('*')\
                .order('nombre')\
                .execute()
            self._redes_cache = resultado.data

            # Cargar centros con informacion de la red
            resultado = self.db.supabase.table('centros')\
                .select('*, redes(nombre)')\
                .order('nombre')\
                .execute()
            self._centros_cache = resultado.data

        except Exception as e:
            print(f"Error al cargar datos desde Supabase: {e}")
            self._redes_cache = []
            self._centros_cache = []

    # ============================================================
    # METODOS PUBLICOS - OBTENCION DE DATOS
    # ============================================================

    def obtener_redes(self) -> List[str]:
        """
        Obtiene la lista de nombres de todas las redes disponibles.
        """
        if self._redes_cache is None:
            self._cargar_datos()
        return [r['nombre'] for r in self._redes_cache]

    def obtener_centros(self, red: str) -> List[Dict[str, str]]:
        """
        Obtiene los centros de una red especifica.
        Retorna una lista de diccionarios con codigo y nombre.
        """
        if self._centros_cache is None:
            self._cargar_datos()

        # Buscar el ID de la red
        red_id = None
        for r in self._redes_cache or []:
            if r['nombre'] == red:
                red_id = r['id']
                break

        if not red_id:
            return []

        return [
            {
                'codigo': c['codigo'],
                'nombre': c['nombre'],
                'codigo_nombre': f"{c['codigo']}:{c['nombre']}"
            }
            for c in self._centros_cache or []
            if c.get('red_id') == red_id
        ]

    def obtener_centros_codigo_nombre(self, red: str) -> List[str]:
        """
        Obtiene los centros de una red en formato codigo:nombre.
        Util para desplegables.
        """
        return [c['codigo_nombre'] for c in self.obtener_centros(red)]

    def obtener_centros_nombres(self, red: str) -> List[str]:
        """
        Obtiene solo los nombres de los centros de una red.
        """
        return [c['nombre'] for c in self.obtener_centros(red)]

    def obtener_centros_codigos(self, red: str) -> List[str]:
        """
        Obtiene solo los codigos de los centros de una red.
        """
        return [c['codigo'] for c in self.obtener_centros(red)]

    def contar_centros(self, red: str) -> int:
        """
        Cuenta cuantos centros tiene una red.
        """
        return len(self.obtener_centros(red))

    def red_tiene_centros(self, red: str) -> bool:
        """
        Verifica si una red tiene centros registrados.
        """
        return self.contar_centros(red) > 0

    # ============================================================
    # METODOS PUBLICOS - ESTADISTICAS Y RECARGA
    # ============================================================

    def recargar(self) -> Dict:
        """
        Recarga los datos desde Supabase.
        Util cuando el administrador agrega o elimina redes/centros.
        """
        self._cargar_datos()
        return self.obtener_estadisticas()

    def obtener_estadisticas(self) -> Dict:
        """
        Obtiene estadisticas de la estructura de datos.
        """
        if self._redes_cache is None:
            self._cargar_datos()

        redes = self._redes_cache or []
        centros = self._centros_cache or []

        # Calcular centros por red
        centros_por_red = {}
        for red in redes:
            count = sum(1 for c in centros if c.get('red_id') == red['id'])
            centros_por_red[red['nombre']] = count

        return {
            'total_redes': len(redes),
            'total_centros': len(centros),
            'centros_por_red': centros_por_red,
            'fuente': 'Supabase',
            'redes': [r['nombre'] for r in redes]
        }

    def to_dict(self) -> Dict:
        """
        Retorna toda la estructura de datos como diccionario.
        """
        if self._redes_cache is None:
            self._cargar_datos()

        resultado = {}
        for red in self._redes_cache or []:
            nombre = red['nombre']
            resultado[nombre] = [
                {'codigo': c['codigo'], 'nombre': c['nombre']}
                for c in self._centros_cache or []
                if c.get('red_id') == red['id']
            ]
        return resultado

    # ============================================================
    # METODOS PARA ADMINISTRACION (CRUD)
    # ============================================================

    def agregar_red(self, nombre: str) -> bool:
        """
        Agrega una nueva red a Supabase.
        """
        try:
            self.db.supabase.table('redes').insert({'nombre': nombre}).execute()
            self.recargar()
            return True
        except Exception as e:
            print(f"Error al agregar red: {e}")
            return False

    def eliminar_red(self, red_nombre: str) -> bool:
        """
        Elimina una red y sus centros por cascada.
        """
        try:
            for r in self._redes_cache or []:
                if r['nombre'] == red_nombre:
                    self.db.supabase.table('redes').delete().eq('id', r['id']).execute()
                    self.recargar()
                    return True
            return False
        except Exception as e:
            print(f"Error al eliminar red: {e}")
            return False

    def agregar_centro(self, red_nombre: str, codigo: str, nombre: str) -> bool:
        """
        Agrega un centro a una red existente.
        """
        try:
            # Buscar red_id
            red_id = None
            for r in self._redes_cache or []:
                if r['nombre'] == red_nombre:
                    red_id = r['id']
                    break

            if not red_id:
                return False

            self.db.supabase.table('centros').insert({
                'red_id': red_id,
                'codigo': codigo,
                'nombre': nombre
            }).execute()
            self.recargar()
            return True
        except Exception as e:
            print(f"Error al agregar centro: {e}")
            return False

    def eliminar_centro(self, centro_codigo: str) -> bool:
        """
        Elimina un centro por su codigo.
        """
        try:
            self.db.supabase.table('centros').delete().eq('codigo', centro_codigo).execute()
            self.recargar()
            return True
        except Exception as e:
            print(f"Error al eliminar centro: {e}")
            return False


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

_data_loader_db = None


def get_data_loader_db() -> DataLoaderDB:
    """
    Retorna la instancia unica del DataLoaderDB.
    """
    global _data_loader_db
    if _data_loader_db is None:
        _data_loader_db = DataLoaderDB()
    return _data_loader_db


def limpiar_cache():
    """
    Limpia la instancia cacheada del DataLoaderDB.
    """
    global _data_loader_db
    _data_loader_db = None