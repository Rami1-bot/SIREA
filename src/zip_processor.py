# src/zip_processor.py
"""
Procesamiento y validación de archivos ZIP para el sistema de reportes.
Verifica integridad, estructura y contenido de los archivos subidos.
"""

import os
import io
import hashlib
import re
import zipfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from src.config import Config
from utils.helpers import sanitizar_nombre, tamaño_legible


# Tipo de reporte que lleva la SEGUNDA letra del nombre del archivo
# (ej. "pc4026jj.204": c = consulta externa). La primera letra y lo que
# sigue a la semana/año ("jj", "ij"...) no se usan.
TIPO_POR_LETRA = {'c': 'Consulta Externa', 'e': 'Emergencia', 'h': 'Hospitalizacion'}
LETRA_POR_TIPO = {
    'consulta externa': 'c', 'emergencia': 'e',
    'hospitalizacion': 'h', 'hospitalización': 'h',
}
ORDEN_TIPOS = ['Consulta Externa', 'Hospitalizacion', 'Emergencia']  # el del formulario

# <1ª letra><tipo c/e/h><semana 2 dígitos><año 2 dígitos>...  (ej. pe4026jj, SC3526HI)
_PATRON_NOMBRE_REPORTE = re.compile(r'^[A-Za-z]([ceh])(\d{2})(\d{2})', re.IGNORECASE)


class ZipProcessor:
    """
    Procesador de archivos ZIP.
    """

    def __init__(self):
        """Inicializa el procesador de ZIPs."""
        self.extensiones_permitidas = Config.EXTENSIONES_PERMITIDAS
        self.extensiones_bloqueadas = Config.EXTENSIONES_BLOQUEADAS
        self.permitir_extensiones_numericas = Config.PERMITIR_EXTENSIONES_NUMERICAS
        self._patron_extension_numerica = re.compile(r'^\.\d+$')
        # Extensión alfanumérica "de código de centro" (ej. ".B56", ".A72",
        # ".r01"): de 1 a 4 caracteres y con AL MENOS UN DÍGITO. Antes el
        # patrón era "cualquier letra/número", lo que dejaba pasar
        # extensiones comunes como .pdf, .docx, .html, .php, .jar, .dll o
        # .lnk (solo se rechazaba la lista corta de EXTENSIONES_BLOQUEADAS).
        # Los códigos reales de data/REDES2.txt son de <= 3 caracteres y
        # todos llevan un dígito (491 numéricos y 11 tipo A72/B56).
        self._patron_extension_alfanumerica = re.compile(
            r'^\.(?=[A-Za-z0-9]{1,4}$)[A-Za-z0-9]*\d[A-Za-z0-9]*$'
        )
        # Obtener tamaño máximo dinámicamente desde la configuración
        tamano_maximo_mb = Config.get_tamano_maximo_zip_mb()
        self.tamano_maximo_bytes = tamano_maximo_mb * 1024 * 1024
        self.max_archivos_permitidos = 100
        self.max_tamano_descomprimido_mb = 500

    def _es_extension_permitida(self, ext: str, codigos_centros_validos: Optional[set] = None) -> bool:
        """
        Indica si una extensión debe aceptarse:
        - está en la lista configurada (.xlsx, .csv, etc.), o
        - coincide con el CÓDIGO REAL de un centro de la red que se
          está enviando (ej. ".127", ".B56") -- así nombra estos
          archivos el sistema legacy. Cubre en particular los códigos
          alfanuméricos (ej. "B56"), que el patrón numérico no detecta.
        - es puramente numérica (ej. ".127", ".999") y el sistema
          legacy que las genera está habilitado -- esta regla aplica
          SIEMPRE como respaldo, no solo cuando no se conoce la red,
          porque el número de un archivo puede no coincidir con
          ningún centro de la red seleccionada y aun así ser legítimo
          (ej. un centro dado de baja, o un desfase entre el sistema
          legacy y la tabla de centros).
        - es alfanumérica (letras y números mezclados, ej. ".r01") --
          se deja pasar sin más preguntas, porque no hay forma
          confiable de validarla contra una lista conocida. La
          verificación de "¿esto es de la red correcta?" solo se hace
          para las puramente numéricas, que sí podemos comparar contra
          códigos reales (ver validar_zip).
        """
        if ext in self.extensiones_permitidas:
            return True

        sufijo = ext[1:].upper() if ext.startswith('.') else ext.upper()

        if codigos_centros_validos and sufijo in codigos_centros_validos:
            return True

        if self.permitir_extensiones_numericas and self._patron_extension_numerica.match(ext):
            return True

        if self.permitir_extensiones_numericas and self._patron_extension_alfanumerica.match(ext):
            return True

        return False

    def _extraer_codigo_embebido(self, nombre_archivo: str) -> Optional[str]:
        """
        Para archivos con extensión REAL ya permitida (.xlsx, .csv,
        .dbf, etc.), el sistema legacy a veces nombra el archivo con
        el código del centro como una segunda "extensión" antes de la
        extensión real -- ej. "pc3726ii.062.csv" (centro 062) o
        "pe3726ii.440.xlsx" (centro 440). Es el mismo código que en un
        ZIP viejo hubiera venido como extensión única (ej.
        "pc3726ii.062" a secas), solo que aquí el archivo sí trae su
        extensión real al final.

        Devuelve el código en mayúsculas (ej. "062", "B56") si el
        nombre sigue ese patrón, o None si no lo sigue -- un nombre
        sin ese patrón (ej. "reporte_semanal.xlsx") no es un error, es
        simplemente un archivo cuyo centro no se puede identificar
        automáticamente por el nombre.
        """
        nombre_base = os.path.basename(nombre_archivo)
        nombre_sin_ext_real = os.path.splitext(nombre_base)[0]
        posible_codigo_ext = os.path.splitext(nombre_sin_ext_real)[1]

        if not posible_codigo_ext:
            return None

        if (self._patron_extension_numerica.match(posible_codigo_ext) or
                self._patron_extension_alfanumerica.match(posible_codigo_ext)):
            return posible_codigo_ext[1:].upper()

        return None

    def analizar_nombre_reporte(self, nombre_archivo: str) -> Dict[str, Any]:
        """
        Lee del NOMBRE del archivo el tipo de reporte, la semana y el año.

        Formato: <1ª letra><c|e|h><semana 2 díg.><año 2 díg.><...>.<código>
        Ej.: "pe4026jj.204" -> emergencia, semana 40, año 2026.
        Solo se mira el nombre (nunca el contenido). Si no sigue ese
        formato devuelve tipo/semana/anio = None (nombre libre: no se
        puede validar, no es un error).
        """
        base = os.path.basename(str(nombre_archivo).replace('\\', '/'))
        raiz = base.split('.', 1)[0]
        m = _PATRON_NOMBRE_REPORTE.match(raiz)
        if not m:
            return {"tipo": None, "semana": None, "anio": None}
        return {
            "tipo": TIPO_POR_LETRA[m.group(1).lower()],
            "semana": int(m.group(2)),
            "anio": 2000 + int(m.group(3)),
        }

    def _codigo_de_archivo(self, nombre_archivo: str, codigos_validos: Optional[set]) -> Optional[str]:
        """Código de centro que trae el nombre (extensión o segunda extensión), en mayúsculas."""
        ext = os.path.splitext(nombre_archivo)[1].lower()
        if ext in self.extensiones_permitidas:
            return self._extraer_codigo_embebido(nombre_archivo)
        sufijo = ext[1:].upper() if ext.startswith('.') else ext.upper()
        return sufijo or None

    def validar_periodo(
        self,
        info_zip: Dict,
        semana: int,
        anio: int,
        semanas_validas: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Compara la semana/año que traen los nombres de los archivos con la
        semana/año que el remitente declaró en el formulario.

        Devuelve {"ok", "mensaje", "archivos_otro_periodo", "periodos"}.
        Los archivos de nombre libre no se pueden comparar y no cuentan.
        Un ZIP con archivos de varias semanas no pasa: debe haber un ZIP por semana.
        """
        detalle = (info_zip or {}).get("archivos_detalle") or []
        fuera, inexistentes, periodos = [], [], set()
        for d in detalle:
            s, a = d.get("semana"), d.get("anio")
            if s is None or a is None:
                continue
            periodos.add((s, a))
            if (s, a) != (int(semana), int(anio)):
                fuera.append(d)
                if semanas_validas and a == int(anio) and s not in semanas_validas:
                    inexistentes.append(d)

        res = {"ok": not fuera, "mensaje": "", "archivos_otro_periodo": [d["archivo"] for d in fuera],
               "periodos": sorted(periodos), "periodo_unico": None}
        if not fuera:
            return res

        def _lista(nombres, limite=6):
            nombres = [os.path.basename(n) for n in nombres]
            txt = ", ".join(f"`{n}`" for n in nombres[:limite])
            return txt + (f" y {len(nombres) - limite} más" if len(nombres) > limite else "")

        grupos: Dict[Tuple[int, int], List[str]] = {}
        for d in detalle:
            if d.get("semana") is not None and d.get("anio") is not None:
                grupos.setdefault((d["semana"], d["anio"]), []).append(d["archivo"])
        elegido = (int(semana), int(anio))

        if len(grupos) == 1:
            (s_, a_), nombres = next(iter(grupos.items()))
            res["periodo_unico"] = (s_, a_)
            res["mensaje"] = (
                f"**Los archivos son de la semana {s_}/{a_}, pero usted eligió la semana {elegido[0]}/{elegido[1]}.**\n\n"
                f"Archivos: {_lista(nombres)}.\n\n"
                f"Si realmente desea enviar la semana {s_}, cambie «Semana»"
                + (" y «Año»" if a_ != elegido[1] else "")
                + f" a {s_}/{a_}. Si no, adjunte el ZIP de la semana {elegido[0]}/{elegido[1]}."
            )
        else:
            lineas = "\n".join(
                f"- semana {s_}/{a_}: {len(n)} archivo(s) ({_lista(n, 3)})" for (s_, a_), n in sorted(grupos.items())
            )
            res["mensaje"] = (
                f"**El ZIP mezcla archivos de semanas distintas** (usted eligió la semana {elegido[0]}/{elegido[1]}):\n\n"
                f"{lineas}\n\n"
                "Cada ZIP debe traer una sola semana: separe los archivos y envíe un ZIP por semana."
            )
        if inexistentes:
            sems = sorted({d["semana"] for d in inexistentes})
            res["mensaje"] += (
                f"\n\nLa semana {', '.join(map(str, sems))} no existe en el año epidemiológico {anio}"
                + (f" (tiene {max(semanas_validas)} semanas)." if semanas_validas else ".")
            )
        return res

    def dividir_zip(self, archivo_bytes: bytes, nombres_a_incluir) -> bytes:
        """
        Devuelve un ZIP nuevo con SOLO los archivos indicados (mismo nombre,
        mismo contenido, mismas fechas). El ZIP original no se modifica.
        """
        incluir = set(nombres_a_incluir)
        salida = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zin, \
                zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename in incluir and not info.filename.endswith('/'):
                    nuevo = zipfile.ZipInfo(info.filename, info.date_time)
                    nuevo.compress_type = zipfile.ZIP_DEFLATED
                    nuevo.external_attr = info.external_attr
                    zout.writestr(nuevo, zin.read(info.filename))
        return salida.getvalue()

    # ============================================================
    # VALIDACIONES PRINCIPALES
    # ============================================================

    def validar_zip(
        self,
        archivo_bytes: bytes,
        nombre_archivo: str,
        codigos_centros: Optional[List[str]] = None
    ) -> Dict:
        """
        Valida un archivo ZIP completo.

        Args:
            codigos_centros: códigos reales de los centros de la red que
                se está enviando (ej. ["127", "129", "132"] o ["B56",
                "B58"]). Si se pasa, un archivo interno con extensión
                igual a uno de estos códigos (ej. "SC3526HI.127") se
                acepta como válido -- así nombra sus archivos el
                sistema legacy que exporta estos reportes.

        Retorna:
        {
            "valido": bool,
            "estado": "ok" | "corrupto" | "observacion",
            "mensaje": str,
            "cantidad": int,
            "archivos": List[str],
            "tamaño_bytes": int,
            "tamaño_legible": str,
            "extensiones": List[str],
            "extensiones_invalidas": List[str],
            "archivos_invalidos": List[str],
            "centros_detectados": List[str],
            "codigos_fuera_de_red": List[str],
            "archivos_sin_centro_identificado": List[str],
            "hash_md5": str,
            "hash_sha256": str
        }
        """
        resultado = {
            "valido": False,
            "estado": "error",
            "mensaje": "",
            "cantidad": 0,
            "archivos": [],
            "tamaño_bytes": len(archivo_bytes),
            "tamaño_legible": tamaño_legible(len(archivo_bytes)),
            "extensiones": [],
            "extensiones_invalidas": [],
            "archivos_invalidos": [],
            "centros_detectados": [],
            "codigos_fuera_de_red": [],
            "archivos_sin_centro_identificado": [],
            "archivos_detalle": [],
            "tipos_detectados": [],
            "archivos_sin_tipo": [],
            "hash_md5": "",
            "hash_sha256": ""
        }

        codigos_centros_validos = (
            {str(c).strip().upper() for c in codigos_centros if str(c).strip()}
            if codigos_centros else None
        )

        # Calcular hashes
        resultado["hash_md5"] = hashlib.md5(archivo_bytes).hexdigest()
        resultado["hash_sha256"] = hashlib.sha256(archivo_bytes).hexdigest()

        # Validación 1: Extensión del archivo
        if not self._validar_extension_zip(nombre_archivo):
            resultado["mensaje"] = f"El archivo no tiene extensión .zip: {nombre_archivo}"
            resultado["estado"] = "corrupto"
            return resultado

        # Validación 2: Tamaño del archivo
        if len(archivo_bytes) > self.tamano_maximo_bytes:
            tamano_maximo_mb = Config.get_tamano_maximo_zip_mb()
            resultado["mensaje"] = (
                f"El archivo excede el tamaño máximo de {tamano_maximo_mb} MB. "
                f"Tamaño actual: {resultado['tamaño_legible']}"
            )
            resultado["estado"] = "corrupto"
            return resultado

        # Validación 3: Archivo vacío
        if len(archivo_bytes) == 0:
            resultado["mensaje"] = "El archivo está vacío"
            resultado["estado"] = "corrupto"
            return resultado

        # Validación 4: Integridad del ZIP
        try:
            with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zf:
                # Verificar si el ZIP es válido
                archivo_corrupto = zf.testzip()
                if archivo_corrupto is not None:
                    resultado["mensaje"] = f"El archivo ZIP contiene un archivo dañado: {archivo_corrupto}"
                    resultado["estado"] = "corrupto"
                    return resultado

                # Obtener lista de archivos
                archivos = [f for f in zf.namelist() if not f.endswith('/')]
                resultado["cantidad"] = len(archivos)
                resultado["archivos"] = archivos

                if not archivos:
                    resultado["mensaje"] = "El archivo ZIP está vacío"
                    resultado["estado"] = "corrupto"
                    return resultado

                # Validar cantidad máxima de archivos
                if len(archivos) > self.max_archivos_permitidos:
                    resultado["mensaje"] = (
                        f"El ZIP contiene demasiados archivos ({len(archivos)}). "
                        f"Máximo permitido: {self.max_archivos_permitidos}"
                    )
                    resultado["estado"] = "corrupto"
                    return resultado

                # Validar tamaño descomprimido
                tamano_total = sum(info.file_size for info in zf.infolist())
                if tamano_total > self.max_tamano_descomprimido_mb * 1024 * 1024:
                    resultado["mensaje"] = (
                        f"El tamaño total descomprimido excede el límite de "
                        f"{self.max_tamano_descomprimido_mb} MB"
                    )
                    resultado["estado"] = "corrupto"
                    return resultado

                # Validar extensiones de los archivos internos
                extensiones_validas = []
                extensiones_invalidas = []
                extensiones_bloqueadas = []
                archivos_invalidos = []
                codigos_detectados = set()
                codigos_fuera_de_red = set()
                archivos_sin_centro_identificado = []

                for archivo in archivos:
                    ext = os.path.splitext(archivo)[1].lower()

                    if ext in self.extensiones_bloqueadas:
                        extensiones_bloqueadas.append(ext)
                        archivos_invalidos.append(archivo)
                    elif self._es_extension_permitida(ext, codigos_centros_validos):
                        extensiones_validas.append(ext)
                        # Si la extensión coincide con el código real de un
                        # centro de la red (no solo con el respaldo
                        # numérico genérico), lo guardamos para poder
                        # comparar después contra los centros que el
                        # usuario seleccionó en el formulario.
                        sufijo = ext[1:].upper() if ext.startswith('.') else ext.upper()
                        if codigos_centros_validos and sufijo in codigos_centros_validos:
                            codigos_detectados.add(sufijo)
                        elif codigos_centros_validos and self._patron_extension_numerica.match(ext):
                            # Es un código numérico válido en general
                            # (por eso pasó la validación), pero no
                            # pertenece a NINGÚN centro de la red
                            # seleccionada -- posible señal de que el
                            # ZIP es de otra red. Solo se marca para
                            # números, porque los alfanuméricos no se
                            # pueden comparar con la misma confianza.
                            codigos_fuera_de_red.add(sufijo)
                        elif ext in self.extensiones_permitidas:
                            # Archivo con extensión REAL (.xlsx, .csv,
                            # .dbf, etc.), no con el respaldo numérico
                            # genérico -- intentar la misma
                            # identificación de centro que se hace
                            # arriba, pero buscando el código como una
                            # segunda extensión en el nombre (ver
                            # _extraer_codigo_embebido), ej.
                            # "pc3726ii.062.csv".
                            codigo_embebido = self._extraer_codigo_embebido(archivo)
                            if codigo_embebido and codigos_centros_validos and codigo_embebido in codigos_centros_validos:
                                codigos_detectados.add(codigo_embebido)
                            elif (codigo_embebido and codigos_centros_validos and
                                    self._patron_extension_numerica.match(f".{codigo_embebido}")):
                                # Mismo criterio que arriba: solo se
                                # marca "fuera de red" cuando el código
                                # embebido es puramente numérico, por
                                # la misma razón (los alfanuméricos no
                                # se pueden comparar con la misma
                                # confianza).
                                codigos_fuera_de_red.add(codigo_embebido)
                            elif not codigo_embebido:
                                # No se pudo identificar el centro por
                                # el nombre -- no es un error (la
                                # extensión ya es válida), pero se deja
                                # constancia para que el admin lo
                                # identifique o lo valide manualmente.
                                archivos_sin_centro_identificado.append(archivo)
                    else:
                        extensiones_invalidas.append(ext)
                        archivos_invalidos.append(archivo)

                resultado["extensiones"] = list(set(extensiones_validas))
                resultado["extensiones_invalidas"] = list(set(extensiones_invalidas + extensiones_bloqueadas))
                resultado["archivos_invalidos"] = archivos_invalidos
                resultado["centros_detectados"] = sorted(codigos_detectados)
                resultado["codigos_fuera_de_red"] = sorted(codigos_fuera_de_red)
                resultado["archivos_sin_centro_identificado"] = archivos_sin_centro_identificado

                # Detalle por archivo (solo de los de extensión aceptada):
                # tipo/semana/año leídos del NOMBRE, código de centro y huella
                # SHA-256. No se abre ni interpreta el contenido.
                invalidos = set(archivos_invalidos)
                detalle = []
                sin_tipo = []
                for archivo in archivos:
                    if archivo in invalidos:
                        continue
                    nom = self.analizar_nombre_reporte(archivo)
                    detalle.append({
                        "archivo": archivo,
                        "codigo": self._codigo_de_archivo(archivo, codigos_centros_validos),
                        "tipo": nom["tipo"],
                        "semana": nom["semana"],
                        "anio": nom["anio"],
                        "sha256": hashlib.sha256(zf.read(archivo)).hexdigest(),
                        "bytes": zf.getinfo(archivo).file_size,
                    })
                    if nom["tipo"] is None:
                        sin_tipo.append(archivo)
                resultado["archivos_detalle"] = detalle
                resultado["archivos_sin_tipo"] = sin_tipo
                tipos = {d["tipo"] for d in detalle if d["tipo"]}
                resultado["tipos_detectados"] = [t for t in ORDEN_TIPOS if t in tipos]

                # Determinar estado final
                if extensiones_bloqueadas:
                    resultado["estado"] = "corrupto"
                    resultado["mensaje"] = (
                        f"El ZIP contiene archivos con extensiones bloqueadas: "
                        f"{', '.join(set(extensiones_bloqueadas))}"
                    )
                    resultado["valido"] = False
                elif extensiones_invalidas:
                    resultado["estado"] = "observacion"
                    resultado["mensaje"] = (
                        f"El ZIP contiene {len(archivos_invalidos)} archivo(s) con extensión no permitida "
                        f"({', '.join(set(extensiones_invalidas))}). "
                        f"Si su archivo viene del sistema de exportación por centro, verifique que el número o "
                        f"código después del punto coincida con uno de los centros de esta red."
                    )
                    resultado["valido"] = False
                else:
                    resultado["estado"] = "ok"
                    resultado["mensaje"] = (
                        f"Archivo ZIP válido con {len(archivos)} archivo(s)"
                    )
                    resultado["valido"] = True

                # Nota informativa, nunca bloqueante: no cambia "estado"
                # ni "valido" -- el archivo ya pasó la validación
                # principal (extensión permitida). Solo queda registrado
                # para que el admin identifique el centro a mano.
                if archivos_sin_centro_identificado:
                    resultado["mensaje"] += (
                        f" (revisar manualmente el centro de "
                        f"{len(archivos_sin_centro_identificado)} archivo(s) "
                        f"sin código identificable en el nombre)"
                    )

                return resultado

        except zipfile.BadZipFile:
            resultado["mensaje"] = "El archivo no es un ZIP válido o está corrupto"
            resultado["estado"] = "corrupto"
            return resultado
        except Exception as e:
            resultado["mensaje"] = f"Error al procesar el ZIP: {str(e)}"
            resultado["estado"] = "error"
            return resultado

    def validar_zip_desde_archivo(self, ruta_archivo: str) -> Dict:
        """
        Valida un archivo ZIP desde una ruta en el sistema.
        """
        try:
            with open(ruta_archivo, 'rb') as f:
                contenido = f.read()
            return self.validar_zip(contenido, os.path.basename(ruta_archivo))
        except FileNotFoundError:
            return {
                "valido": False,
                "estado": "error",
                "mensaje": f"Archivo no encontrado: {ruta_archivo}",
                "cantidad": 0,
                "archivos": [],
                "tamaño_bytes": 0,
                "tamaño_legible": "0 B",
                "extensiones": [],
                "extensiones_invalidas": [],
                "archivos_invalidos": [],
                "hash_md5": "",
                "hash_sha256": ""
            }
        except Exception as e:
            return {
                "valido": False,
                "estado": "error",
                "mensaje": f"Error al leer el archivo: {str(e)}",
                "cantidad": 0,
                "archivos": [],
                "tamaño_bytes": 0,
                "tamaño_legible": "0 B",
                "extensiones": [],
                "extensiones_invalidas": [],
                "archivos_invalidos": [],
                "hash_md5": "",
                "hash_sha256": ""
            }

    # ============================================================
    # MÉTODOS AUXILIARES DE VALIDACIÓN
    # ============================================================

    def _validar_extension_zip(self, nombre_archivo: str) -> bool:
        """Verifica que el archivo tenga extensión .zip."""
        return nombre_archivo.lower().endswith('.zip')

    def _validar_tamaño(self, bytes: int) -> bool:
        """Verifica que el tamaño no exceda el máximo."""
        return bytes <= self.tamano_maximo_bytes

    # ============================================================
    # MÉTODOS PARA PROCESAMIENTO
    # ============================================================

    def extraer_zip(self, archivo_bytes: bytes, ruta_destino: str) -> Dict:
        """
        Extrae un archivo ZIP en una carpeta destino.

        Retorna:
        {
            "exito": bool,
            "mensaje": str,
            "archivos_extraidos": List[str],
            "ruta_destino": str
        }
        """
        try:
            ruta_destino_path = Path(ruta_destino)
            ruta_destino_path.mkdir(parents=True, exist_ok=True)

            archivos_extraidos = []

            with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zf:
                for archivo in zf.namelist():
                    # Evitar path traversal
                    nombre_seguro = self._sanitizar_ruta_zip(archivo)
                    ruta_completa = ruta_destino_path / nombre_seguro

                    # Si es directorio, crearlo
                    if archivo.endswith('/'):
                        ruta_completa.mkdir(parents=True, exist_ok=True)
                    else:
                        # Crear directorios padre
                        ruta_completa.parent.mkdir(parents=True, exist_ok=True)

                        # Extraer archivo
                        with zf.open(archivo) as fuente:
                            with open(ruta_completa, 'wb') as destino:
                                destino.write(fuente.read())
                        archivos_extraidos.append(str(ruta_completa))

            return {
                "exito": True,
                "mensaje": f"Archivo extraído correctamente. {len(archivos_extraidos)} archivos",
                "archivos_extraidos": archivos_extraidos,
                "ruta_destino": str(ruta_destino_path)
            }

        except zipfile.BadZipFile:
            return {
                "exito": False,
                "mensaje": "El archivo ZIP está corrupto",
                "archivos_extraidos": [],
                "ruta_destino": ruta_destino
            }
        except Exception as e:
            return {
                "exito": False,
                "mensaje": f"Error al extraer el ZIP: {str(e)}",
                "archivos_extraidos": [],
                "ruta_destino": ruta_destino
            }

    def extraer_zip_desde_archivo(self, ruta_origen: str, ruta_destino: str) -> Dict:
        """
        Extrae un archivo ZIP desde una ruta del sistema.
        """
        try:
            with open(ruta_origen, 'rb') as f:
                contenido = f.read()
            return self.extraer_zip(contenido, ruta_destino)
        except FileNotFoundError:
            return {
                "exito": False,
                "mensaje": f"Archivo no encontrado: {ruta_origen}",
                "archivos_extraidos": [],
                "ruta_destino": ruta_destino
            }
        except Exception as e:
            return {
                "exito": False,
                "mensaje": f"Error al leer el archivo: {str(e)}",
                "archivos_extraidos": [],
                "ruta_destino": ruta_destino
            }

    def _sanitizar_ruta_zip(self, ruta: str) -> str:
        """
        Sanitiza una ruta dentro del ZIP para evitar path traversal.
        """
        # Reemplazar separadores de ruta
        ruta_limpia = ruta.replace('\\', '/')

        # Eliminar rutas absolutas
        while ruta_limpia.startswith('/'):
            ruta_limpia = ruta_limpia[1:]

        # Eliminar referencias a directorios padre
        partes = []
        for parte in ruta_limpia.split('/'):
            if parte == '..':
                continue
            if parte in ['.', '']:
                continue
            partes.append(parte)

        return '/'.join(partes)

    # ============================================================
    # MÉTODOS DE INFORMACIÓN
    # ============================================================

    def obtener_info_zip(self, archivo_bytes: bytes) -> Dict:
        """
        Obtiene información detallada de un ZIP sin validar extensiones.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zf:
                archivos = zf.namelist()
                archivos_no_directorios = [f for f in archivos if not f.endswith('/')]

                # Obtener estadísticas de archivos
                extensiones = {}
                for archivo in archivos_no_directorios:
                    ext = os.path.splitext(archivo)[1].lower()
                    extensiones[ext] = extensiones.get(ext, 0) + 1

                # Calcular tamaños
                tamano_comprimido = sum(info.compress_size for info in zf.infolist())
                tamano_descomprimido = sum(info.file_size for info in zf.infolist())

                return {
                    "exito": True,
                    "total_archivos": len(archivos_no_directorios),
                    "total_elementos": len(archivos),
                    "archivos": archivos,
                    "extensiones": extensiones,
                    "extensiones_permitidas": self.extensiones_permitidas,
                    "tiene_carpetas": any(f.endswith('/') for f in archivos),
                    "tamano_comprimido": tamano_comprimido,
                    "tamano_descomprimido": tamano_descomprimido,
                    "tamano_comprimido_legible": tamaño_legible(tamano_comprimido),
                    "tamano_descomprimido_legible": tamaño_legible(tamano_descomprimido)
                }

        except Exception as e:
            return {
                "exito": False,
                "mensaje": f"Error al obtener información: {str(e)}",
                "total_archivos": 0,
                "total_elementos": 0,
                "archivos": [],
                "extensiones": {},
                "extensiones_permitidas": self.extensiones_permitidas,
                "tiene_carpetas": False,
                "tamano_comprimido": 0,
                "tamano_descomprimido": 0
            }

    def obtener_tamaño_estimado_descomprimido(self, archivo_bytes: bytes) -> int:
        """
        Estima el tamaño total descomprimido de un ZIP.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zf:
                total = 0
                for info in zf.infolist():
                    total += info.file_size
                return total
        except:
            return 0

    # ============================================================
    # MÉTODOS DE LIMPIEZA
    # ============================================================

    def limpiar_archivos_temporales(self, ruta: str, eliminar_carpeta: bool = False) -> bool:
        """
        Limpia archivos temporales extraídos.
        """
        try:
            ruta_path = Path(ruta)
            if ruta_path.exists():
                if ruta_path.is_dir():
                    for archivo in ruta_path.iterdir():
                        if archivo.is_file():
                            archivo.unlink()
                        elif archivo.is_dir():
                            shutil.rmtree(archivo)

                    if eliminar_carpeta:
                        ruta_path.rmdir()
                    return True
                else:
                    ruta_path.unlink()
                    return True
            return False
        except Exception as e:
            print(f"Error al limpiar archivos temporales: {e}")
            return False

    def verificar_archivo_corrupto(self, archivo_bytes: bytes) -> Optional[str]:
        """
        Verifica si hay archivos corruptos en el ZIP.
        Retorna el nombre del archivo corrupto o None.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(archivo_bytes)) as zf:
                return zf.testzip()
        except:
            return "ZIP inválido"


# ============================================================
# FUNCIONES DE CARGA RÁPIDA (para uso en Streamlit)
# ============================================================

_zip_processor = None


def get_zip_processor() -> ZipProcessor:
    """
    Retorna la instancia única del ZipProcessor.
    """
    global _zip_processor
    if _zip_processor is None:
        _zip_processor = ZipProcessor()
    return _zip_processor


def validar_zip_subido(archivo_bytes: bytes, nombre_archivo: str) -> Dict:
    """
    Valida un archivo ZIP subido por el usuario.
    Función de acceso rápido.
    """
    processor = get_zip_processor()
    return processor.validar_zip(archivo_bytes, nombre_archivo)


def validar_zip_subido_desde_archivo(ruta_archivo: str) -> Dict:
    """
    Valida un archivo ZIP desde una ruta.
    """
    processor = get_zip_processor()
    return processor.validar_zip_desde_archivo(ruta_archivo)


def extraer_zip(archivo_bytes: bytes, ruta_destino: str) -> Dict:
    """
    Extrae un archivo ZIP.
    """
    processor = get_zip_processor()
    return processor.extraer_zip(archivo_bytes, ruta_destino)


def obtener_info_zip(archivo_bytes: bytes) -> Dict:
    """
    Obtiene información de un archivo ZIP.
    """
    processor = get_zip_processor()
    return processor.obtener_info_zip(archivo_bytes)


def limpiar_cache():
    """
    Limpia la instancia cacheada del ZipProcessor.
    """
    global _zip_processor
    _zip_processor = None