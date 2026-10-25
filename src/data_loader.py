# src/data_loader.py
"""
Carga y gestión de datos maestros desde REDES2.txt.
Permite leer la estructura de Redes Asistenciales y sus Centros.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from src.config import Config
from utils.helpers import sanitizar_nombre


class DataLoader:
    """
    Cargador de datos maestros desde REDES2.txt.
    """
    
    def __init__(self):
        """Inicializa el cargador de datos."""
        self.ruta_archivo = Config.DATA_DIR / "REDES2.txt"
        self._redes: Dict[str, List[Dict[str, str]]] = {}
        self._ultima_actualizacion = None
        self._fecha_carga = None
        self._errores_carga = []
        self._cargar_datos()
    
    def _cargar_datos(self):
        """
        Carga el archivo REDES2.txt y construye la estructura de datos.
        Formato esperado:
            [NOMBRE_RED]
            CODIGO:NOMBRE_CENTRO
            CODIGO:NOMBRE_CENTRO
            [OTRA_RED]
            ...
        """
        if not self.ruta_archivo.exists():
            raise FileNotFoundError(
                f"Archivo REDES2.txt no encontrado en: {self.ruta_archivo}"
            )
        
        try:
            with open(self.ruta_archivo, 'r', encoding='utf-8') as f:
                lineas = f.readlines()
        except UnicodeDecodeError:
            # Intentar con otra codificación
            with open(self.ruta_archivo, 'r', encoding='latin-1') as f:
                lineas = f.readlines()
        
        red_actual = None
        datos = {}
        errores = []
        linea_numero = 0
        total_centros = 0
        
        # Expresión regular para validar códigos alfanuméricos
        # Permite letras mayúsculas, minúsculas y números
        patron_codigo = re.compile(r'^[a-zA-Z0-9]+$')
        
        for linea in lineas:
            linea_numero += 1
            linea = linea.strip()
            
            # Saltar líneas vacías
            if not linea:
                continue
            
            # Saltar comentarios (líneas que empiezan con #)
            if linea.startswith('#'):
                continue
            
            # Detectar nueva red (formato: [NOMBRE_RED])
            if linea.startswith('[') and linea.endswith(']'):
                red_actual = linea[1:-1].strip()
                if not red_actual:
                    errores.append(f"Línea {linea_numero}: Red sin nombre")
                    red_actual = None
                    continue
                
                if red_actual in datos:
                    errores.append(f"Línea {linea_numero}: Red duplicada '{red_actual}'")
                
                datos[red_actual] = []
                continue
            
            # Procesar centro (formato: CODIGO:NOMBRE)
            if red_actual and ':' in linea:
                partes = linea.split(':', 1)
                if len(partes) == 2:
                    codigo = partes[0].strip()
                    nombre = partes[1].strip()
                    
                    if not codigo:
                        errores.append(f"Línea {linea_numero}: Centro sin código en red '{red_actual}'")
                        continue
                    if not nombre:
                        errores.append(f"Línea {linea_numero}: Centro sin nombre en red '{red_actual}'")
                        continue
                    
                    # Validar que el código sea alfanumérico (permite letras y números)
                    if not patron_codigo.match(codigo):
                        errores.append(f"Línea {linea_numero}: Código inválido '{codigo}' en red '{red_actual}' (solo letras y números permitidos)")
                    else:
                        # Verificar código duplicado dentro de la misma red
                        codigos_existentes = [c['codigo'] for c in datos[red_actual]]
                        if codigo in codigos_existentes:
                            errores.append(f"Línea {linea_numero}: Código duplicado '{codigo}' en red '{red_actual}'")
                        
                        datos[red_actual].append({
                            'codigo': codigo,
                            'nombre': nombre,
                            'codigo_nombre': f"{codigo}:{nombre}"
                        })
                        total_centros += 1
                else:
                    errores.append(f"Línea {linea_numero}: Formato inválido en red '{red_actual}'")
            elif red_actual:
                errores.append(f"Línea {linea_numero}: Formato inválido en red '{red_actual}': '{linea}'")
        
        # Guardar errores
        self._errores_carga = errores
        
        # Mostrar errores si existen (ahora solo advertencias, no bloquean)
        if errores:
            print(f"Advertencias al cargar REDES2.txt: {len(errores)}")
            for error in errores[:10]:
                print(f"  - {error}")
            if len(errores) > 10:
                print(f"  ... y {len(errores) - 10} advertencias más")
        
        self._redes = datos
        self._ultima_actualizacion = self.ruta_archivo.stat().st_mtime if self.ruta_archivo.exists() else None
        self._fecha_carga = datetime.now()
    
    # ============================================================
    # MÉTODOS PÚBLICOS - OBTENCIÓN DE DATOS
    # ============================================================
    
    def obtener_redes(self) -> List[str]:
        """
        Obtiene la lista de todas las redes disponibles.
        """
        return sorted(self._redes.keys())
    
    def obtener_centros(self, red: str) -> List[Dict[str, str]]:
        """
        Obtiene los centros de una red específica.
        Retorna una lista de diccionarios con código y nombre.
        """
        return self._redes.get(red, [])
    
    def obtener_centros_nombres(self, red: str) -> List[str]:
        """
        Obtiene solo los nombres de los centros de una red.
        """
        return [c['nombre'] for c in self._redes.get(red, [])]
    
    def obtener_centros_codigos(self, red: str) -> List[str]:
        """
        Obtiene solo los códigos de los centros de una red.
        """
        return [c['codigo'] for c in self._redes.get(red, [])]
    
    def obtener_centros_codigo_nombre(self, red: str) -> List[str]:
        """
        Obtiene la lista de código:nombre de los centros.
        Útil para desplegables.
        """
        return [c['codigo_nombre'] for c in self._redes.get(red, [])]
    
    def obtener_centros_con_formato(self, red: str, formato: str = "codigo_nombre") -> List[str]:
        """
        Obtiene los centros de una red en el formato especificado.
        Formatos disponibles: codigo_nombre, nombre, codigo
        """
        formatos = {
            'codigo_nombre': lambda c: c['codigo_nombre'],
            'nombre': lambda c: c['nombre'],
            'codigo': lambda c: c['codigo']
        }
        if formato not in formatos:
            return []
        return [formatos[formato](c) for c in self._redes.get(red, [])]
    
    def contar_centros(self, red: str) -> int:
        """
        Cuenta cuántos centros tiene una red.
        """
        return len(self._redes.get(red, []))
    
    def red_tiene_centros(self, red: str) -> bool:
        """
        Verifica si una red tiene centros registrados.
        """
        return len(self._redes.get(red, [])) > 0
    
    def obtener_errores_carga(self) -> List[str]:
        """
        Obtiene los errores encontrados durante la última carga.
        """
        return self._errores_carga.copy()
    
    def obtener_fecha_carga(self) -> Optional[datetime]:
        """
        Obtiene la fecha de la última carga de datos.
        """
        return self._fecha_carga
    
    # ============================================================
    # MÉTODOS PÚBLICOS - BÚSQUEDA
    # ============================================================
    
    def buscar_centro_por_codigo(self, codigo: str) -> Optional[Dict[str, str]]:
        """
        Busca un centro por su código en todas las redes.
        """
        codigo = str(codigo).strip()
        for red, centros in self._redes.items():
            for centro in centros:
                if centro['codigo'] == codigo:
                    return {**centro, 'red': red}
        return None
    
    def buscar_centro_por_nombre(self, nombre: str) -> Optional[Dict[str, str]]:
        """
        Busca un centro por su nombre en todas las redes.
        """
        nombre_lower = nombre.lower().strip()
        for red, centros in self._redes.items():
            for centro in centros:
                if centro['nombre'].lower() == nombre_lower:
                    return {**centro, 'red': red}
        return None
    
    def buscar_centros_por_red_y_codigos(
        self,
        red: str,
        codigos: List[str]
    ) -> List[Dict[str, str]]:
        """
        Busca centros específicos por su código dentro de una red.
        """
        codigos_set = {str(c).strip() for c in codigos}
        centros_red = self._redes.get(red, [])
        return [
            c for c in centros_red
            if c['codigo'] in codigos_set
        ]
    
    def buscar_centros_por_red_y_nombres(
        self,
        red: str,
        nombres: List[str]
    ) -> List[Dict[str, str]]:
        """
        Busca centros específicos por su nombre dentro de una red.
        """
        nombres_set = {n.strip() for n in nombres}
        centros_red = self._redes.get(red, [])
        return [
            c for c in centros_red
            if c['nombre'] in nombres_set
        ]
    
    def buscar_por_termino(self, termino: str, limite: int = 20) -> List[Dict]:
        """
        Busca redes o centros que coincidan con un término.
        """
        resultados = []
        termino_lower = termino.lower().strip()
        
        if not termino_lower:
            return []
        
        for red, centros in self._redes.items():
            if termino_lower in red.lower():
                resultados.append({
                    'tipo': 'red',
                    'nombre': red,
                    'centros': len(centros)
                })
            
            for centro in centros:
                if (termino_lower in centro['nombre'].lower() or
                    termino_lower in centro['codigo'].lower()):
                    resultados.append({
                        'tipo': 'centro',
                        'red': red,
                        'codigo': centro['codigo'],
                        'nombre': centro['nombre']
                    })
        
        return resultados[:limite]
    
    def obtener_red_de_centro(self, codigo: str) -> Optional[str]:
        """
        Obtiene la red a la que pertenece un centro por su código.
        """
        codigo = str(codigo).strip()
        for red, centros in self._redes.items():
            for centro in centros:
                if centro['codigo'] == codigo:
                    return red
        return None
    
    # ============================================================
    # MÉTODOS PÚBLICOS - ESTADÍSTICAS Y VALIDACIÓN
    # ============================================================
    
    def obtener_estadisticas(self) -> Dict:
        """
        Obtiene estadísticas de la estructura de datos.
        """
        total_redes = len(self._redes)
        total_centros = sum(len(centros) for centros in self._redes.values())
        
        redes_con_mas_centros = sorted(
            [(red, len(centros)) for red, centros in self._redes.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        redes_con_menos_centros = sorted(
            [(red, len(centros)) for red, centros in self._redes.items()],
            key=lambda x: x[1]
        )[:5]
        
        return {
            'total_redes': total_redes,
            'total_centros': total_centros,
            'promedio_centros_por_red': round(total_centros / total_redes, 2) if total_redes > 0 else 0,
            'redes_con_mas_centros': redes_con_mas_centros,
            'redes_con_menos_centros': redes_con_menos_centros,
            'archivo': str(self.ruta_archivo),
            'ultima_actualizacion': self._ultima_actualizacion,
            'fecha_carga': self._fecha_carga.strftime('%Y-%m-%d %H:%M:%S') if self._fecha_carga else None,
            'errores_carga': len(self._errores_carga),
            'errores_detalle': self._errores_carga[:10]
        }
    
    def recargar(self) -> Dict:
        """
        Recarga los datos desde el archivo.
        Útil para cuando el admin actualiza el archivo.
        Retorna un resumen de la recarga.
        """
        self._cargar_datos()
        return self.obtener_estadisticas()
    
    def validar_estructura(self) -> Tuple[bool, List[str]]:
        """
        Valida que la estructura de datos sea correcta.
        Retorna (es_valido, lista_errores).
        """
        errores = []
        
        if not self._redes:
            errores.append("No se encontraron redes en el archivo")
            return False, errores
        
        for red, centros in self._redes.items():
            if not red:
                errores.append("Se encontró una red sin nombre")
                continue
            
            if not centros:
                errores.append(f"La red '{red}' no tiene centros")
                continue
            
            # Verificar códigos duplicados dentro de la misma red
            codigos = [c['codigo'] for c in centros]
            codigos_duplicados = set([c for c in codigos if codigos.count(c) > 1])
            if codigos_duplicados:
                errores.append(
                    f"La red '{red}' tiene códigos duplicados: {', '.join(codigos_duplicados)}"
                )
            
            # Verificar nombres duplicados
            nombres = [c['nombre'] for c in centros]
            nombres_duplicados = set([n for n in nombres if nombres.count(n) > 1])
            if nombres_duplicados:
                errores.append(
                    f"La red '{red}' tiene nombres duplicados: {', '.join(nombres_duplicados)}"
                )
            
            for centro in centros:
                if not centro.get('codigo'):
                    errores.append(f"Centro sin código en red '{red}'")
                if not centro.get('nombre'):
                    errores.append(f"Centro sin nombre en red '{red}'")
        
        return len(errores) == 0, errores
    
    def comparar_con_archivo(self) -> bool:
        """
        Verifica si los datos en memoria coinciden con el archivo.
        """
        if not self.ruta_archivo.exists():
            return False
        
        mtime_actual = self.ruta_archivo.stat().st_mtime
        return self._ultima_actualizacion == mtime_actual
    
    # ============================================================
    # MÉTODOS PÚBLICOS - EXPORTACIÓN
    # ============================================================
    
    def to_dict(self) -> Dict:
        """
        Retorna toda la estructura de datos como diccionario.
        """
        return self._redes.copy()
    
    def to_json(self, indent: int = 2) -> str:
        """
        Retorna toda la estructura de datos como JSON.
        """
        return json.dumps(self._redes, ensure_ascii=False, indent=indent)
    
    def generar_opciones_desplegable(self) -> Dict[str, List[str]]:
        """
        Genera las opciones para desplegables en el formulario.
        Formato: { "red": ["codigo:nombre", ...] }
        """
        opciones = {}
        for red, centros in self._redes.items():
            opciones[red] = [c['codigo_nombre'] for c in centros]
        return opciones
    
    def generar_dict_para_filtros(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Genera estructura para filtros en el panel admin.
        Formato: { "red": { "codigos": [...], "nombres": [...] } }
        """
        resultado = {}
        for red, centros in self._redes.items():
            resultado[red] = {
                'codigos': [c['codigo'] for c in centros],
                'nombres': [c['nombre'] for c in centros],
                'total': len(centros)
            }
        return resultado
    
    # ============================================================
    # MÉTODOS PÚBLICOS - UTILIDADES ADICIONALES
    # ============================================================
    
    def obtener_resumen_por_red(self) -> List[Dict]:
        """
        Obtiene un resumen de cada red con sus estadísticas.
        """
        resumen = []
        for red in sorted(self._redes.keys()):
            centros = self._redes[red]
            resumen.append({
                'red': red,
                'total_centros': len(centros),
                'centros': centros
            })
        return resumen
    
    def obtener_todas_redes_con_centros(self) -> Dict[str, List[str]]:
        """
        Obtiene todas las redes con sus centros en formato simple.
        """
        return {
            red: [c['nombre'] for c in centros]
            for red, centros in self._redes.items()
        }
    
    def obtener_todos_centros(self) -> List[Dict[str, str]]:
        """
        Obtiene todos los centros de todas las redes.
        Útil para el control de atrasos.
        
        Returns:
            Lista de dicts con 'red', 'codigo', 'nombre'
        """
        todos = []
        for red in self._redes:
            for centro in self._redes[red]:
                todos.append({
                    'red': red,
                    'codigo': centro['codigo'],
                    'nombre': centro['nombre']
                })
        return todos
    
    def obtener_centros_para_atrasos(self) -> List[Dict[str, str]]:
        """
        Obtiene todos los centros en formato simplificado para control de atrasos.
        
        Returns:
            Lista de dicts con 'red' y 'centro' (nombre)
        """
        todos = []
        for red in self._redes:
            for centro in self._redes[red]:
                todos.append({
                    'red': red,
                    'centro': centro['nombre']
                })
        return todos
    
    def exportar_a_csv(self, ruta_salida: Optional[Path] = None) -> Tuple[bool, str]:
        """
        Exporta los datos a un archivo CSV.
        Retorna (éxito, mensaje).
        """
        import csv
        
        if ruta_salida is None:
            ruta_salida = Config.DATA_DIR / "redes_centros.csv"
        
        try:
            with open(ruta_salida, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Red', 'Código', 'Nombre'])
                
                for red, centros in sorted(self._redes.items()):
                    for centro in centros:
                        writer.writerow([red, centro['codigo'], centro['nombre']])
            
            return True, f"Datos exportados a: {ruta_salida}"
        except Exception as e:
            return False, f"Error al exportar: {str(e)}"


# ============================================================
# FUNCIONES DE CARGA RAPIDA CON SOPORTE PARA SUPABASE
# ============================================================

_data_loader = None


def get_data_loader() -> object:
    """
    Retorna el DataLoader segun configuracion.
    Prioridad: Supabase -> REDES2.txt
    
    Returns:
        Instancia de DataLoaderDB si Supabase tiene datos,
        o DataLoader (REDES2.txt) como fallback.
    """
    global _data_loader
    
    if _data_loader is None:
        # Intentar usar Supabase primero
        try:
            from src.data_loader_db import DataLoaderDB
            loader = DataLoaderDB()
            # Verificar que hay datos
            if loader.obtener_redes():
                print("[INFO] Usando DataLoader desde Supabase")
                _data_loader = loader
                return _data_loader
            else:
                print("[WARN] Supabase sin datos, usando REDES2.txt como fallback")
        except ImportError as e:
            print(f"[WARN] No se pudo importar DataLoaderDB: {e}")
        except Exception as e:
            print(f"[WARN] Error cargando desde Supabase: {e}")
        
        # Fallback a REDES2.txt
        print("[INFO] Usando DataLoader desde REDES2.txt")
        _data_loader = DataLoader()
    
    return _data_loader


def cargar_redes_y_centros() -> Dict[str, List[Dict]]:
    """
    Funcion de carga rapida para usar con st.cache_data.
    """
    loader = get_data_loader()
    return loader.to_dict()


def obtener_redes() -> List[str]:
    """
    Funcion rapida para obtener lista de redes.
    """
    loader = get_data_loader()
    return loader.obtener_redes()


def obtener_centros(red: str) -> List[Dict[str, str]]:
    """
    Funcion rapida para obtener centros de una red.
    """
    loader = get_data_loader()
    return loader.obtener_centros(red)


def obtener_centros_codigo_nombre(red: str) -> List[str]:
    """
    Funcion rapida para obtener centros en formato codigo:nombre.
    """
    loader = get_data_loader()
    return loader.obtener_centros_codigo_nombre(red)


def obtener_opciones_desplegable() -> Dict[str, List[str]]:
    """
    Funcion rapida para obtener opciones de desplegables.
    """
    loader = get_data_loader()
    return loader.generar_opciones_desplegable()


def obtener_todos_centros() -> List[Dict[str, str]]:
    """
    Funcion rapida para obtener todos los centros.
    Util para control de atrasos.
    """
    loader = get_data_loader()
    return loader.obtener_todos_centros()


def obtener_centros_para_atrasos() -> List[Dict[str, str]]:
    """
    Funcion rapida para obtener centros en formato para control de atrasos.
    """
    loader = get_data_loader()
    return loader.obtener_centros_para_atrasos()


def recargar_datos() -> Dict:
    """
    Funcion rapida para recargar los datos.
    """
    loader = get_data_loader()
    return loader.recargar()


def validar_datos() -> Tuple[bool, List[str]]:
    """
    Funcion rapida para validar la estructura de datos.
    """
    loader = get_data_loader()
    return loader.validar_estructura()


def limpiar_cache():
    """
    Limpia la instancia cacheada del DataLoader.
    Util para forzar una recarga completa de datos.
    """
    global _data_loader
    _data_loader = None


def obtener_datos_para_formulario() -> Dict:
    """
    Obtiene datos formateados para el formulario de usuario.
    Retorna un diccionario con redes y centros.
    """
    loader = get_data_loader()
    return {
        'redes': loader.obtener_redes(),
        'opciones_centros': loader.generar_opciones_desplegable(),
        'estadisticas': loader.obtener_estadisticas()
    }


# ============================================================
# FUNCIONES DE VALIDACION Y TEST
# ============================================================

def validar_formato_archivo(ruta_archivo: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """
    Valida el formato del archivo REDES2.txt.
    Retorna (es_valido, lista_errores).
    """
    if ruta_archivo is None:
        ruta_archivo = Config.DATA_DIR / "REDES2.txt"
    
    errores = []
    
    if not ruta_archivo.exists():
        return False, [f"Archivo no encontrado: {ruta_archivo}"]
    
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            lineas = f.readlines()
    except UnicodeDecodeError:
        with open(ruta_archivo, 'r', encoding='latin-1') as f:
            lineas = f.readlines()
    
    red_actual = None
    linea_numero = 0
    redes_encontradas = set()
    
    # Expresion regular para validar codigos alfanumericos
    patron_codigo = re.compile(r'^[a-zA-Z0-9]+$')
    
    for linea in lineas:
        linea_numero += 1
        linea = linea.strip()
        
        if not linea:
            continue
        
        # Saltar comentarios
        if linea.startswith('#'):
            continue
        
        # Validar formato de red
        if linea.startswith('[') or linea.endswith(']'):
            if not (linea.startswith('[') and linea.endswith(']')):
                errores.append(f"Linea {linea_numero}: Formato de red inválido: '{linea}'")
                continue
            
            red_actual = linea[1:-1].strip()
            if not red_actual:
                errores.append(f"Linea {linea_numero}: Red sin nombre")
                continue
            
            if red_actual in redes_encontradas:
                errores.append(f"Linea {linea_numero}: Red duplicada '{red_actual}'")
            
            redes_encontradas.add(red_actual)
            continue
        
        # Validar formato de centro
        if red_actual:
            if ':' not in linea:
                errores.append(f"Linea {linea_numero}: Centro sin formato CÓDIGO:NOMBRE: '{linea}'")
            else:
                partes = linea.split(':', 1)
                codigo = partes[0].strip()
                nombre = partes[1].strip() if len(partes) > 1 else ""
                
                if not codigo:
                    errores.append(f"Linea {linea_numero}: Centro sin código en red '{red_actual}'")
                elif not patron_codigo.match(codigo):
                    errores.append(f"Linea {linea_numero}: Código inválido '{codigo}' en red '{red_actual}' (solo letras y numeros permitidos)")
                
                if not nombre:
                    errores.append(f"Linea {linea_numero}: Centro sin nombre en red '{red_actual}'")
    
    if not redes_encontradas:
        errores.append("No se encontraron redes en el archivo")
    
    return len(errores) == 0, errores


def test_carga_datos() -> Dict:
    """
    Funcion de prueba para verificar la carga de datos.
    Retorna un resumen del test.
    """
    loader = get_data_loader()
    estadisticas = loader.obtener_estadisticas()
    valido, errores = loader.validar_estructura()
    
    return {
        'estadisticas': estadisticas,
        'valido': valido,
        'errores': errores,
        'redes': loader.obtener_redes(),
        'total_redes': len(loader.obtener_redes()),
        'primeras_redes': {
            red: loader.obtener_centros(red)[:3]
            for red in loader.obtener_redes()[:3]
        }
    }