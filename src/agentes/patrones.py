# src/agentes/patrones.py
"""
Patrones de envío por red (SIREA 3.2) — se calculan con DATOS, sin IA.

La IA nunca calcula cifras: aquí el sistema cuenta, a partir de lo que de
verdad llegó, y la IA solo lo interpreta y lo redacta. Así «tarde en 6 de
las últimas 8 semanas» es siempre una cuenta verificable, igual para todos.

Qué se calcula
--------------
* Tipos que manda cada centro (c = Consulta Externa, h = Hospitalización,
  e = Emergencia). Se APRENDEN del historial: el nombre de cada archivo ya
  dice su tipo, semana y año (src/zip_processor.py). Un policlínico que nunca
  mandó Hospitalización no tiene «Hospitalización pendiente».
* Qué le falta a cada centro esta semana (por tipo), y qué ya llegó.
* Perfil de puntualidad de la red en las últimas semanas:
    - semanas tarde o sin envío (con la lista de semanas, como prueba),
    - tipo que suele faltar o llegar tarde,
    - tendencia (empeora / mejora / estable),
    - si suele enviar recién después de un recordatorio.
* Panorama de la semana: cuántas redes completaron, cuáles faltan.

Reglas de cuidado (OCDE: equidad y transparencia)
-------------------------------------------------
* Sin un mínimo de semanas con datos (PATRONES_MIN_SEMANAS, 4 por defecto)
  no se habla de «patrón».
* Las semanas que un administrador marcó como «atraso justificado» (feriado,
  caída del sistema…) no cuentan (tabla agente_atrasos_justificados).
* Las semanas anteriores al primer envío registrado en SIREA no cuentan
  (el sistema no estaba en uso: no es un atraso de la red).
* Esto es de uso INTERNO del administrador: nunca va en un correo a la red.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

TIPO_NOMBRE = {"c": "Consulta Externa", "h": "Hospitalización", "e": "Emergencia"}
ORDEN_TIPOS = ["c", "h", "e"]
T_JUSTIFICADOS = "agente_atrasos_justificados"


def _entero_env(nombre: str, por_defecto: int, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(int(os.getenv(nombre) or por_defecto), maximo))
    except ValueError:
        return por_defecto


MIN_SEMANAS = _entero_env("PATRONES_MIN_SEMANAS", 4, 2, 12)        # sin esto no hay «patrón»
SEMANAS_HISTORIAL = _entero_env("PATRONES_SEMANAS", 8, 4, 26)      # ventana que se mira hacia atrás
UMBRAL_TIPO_ESPERADO = 0.5     # un centro «manda» un tipo si lo mandó en la mitad o más de sus semanas
UMBRAL_PATRON = 0.5            # «suele atrasarse» si fue tarde en la mitad o más de las semanas analizadas


def nombre_tipo(letra: str) -> str:
    return TIPO_NOMBRE.get(str(letra or "").lower(), str(letra or ""))


def nombres_tipos(letras: Iterable[str]) -> List[str]:
    return [nombre_tipo(l) for l in ORDEN_TIPOS if l in set(letras)]


# ------------------------------------------------------------
# calendario: semanas hacia atrás (cruzando el cambio de año)
# ------------------------------------------------------------

def semanas_del_anio(anio: int) -> int:
    """Semanas del año según lo configurado en el panel (años epidemiológicos); si no está, el calendario estándar."""
    try:
        from src.db_manager import get_db_manager
        filas = (get_db_manager().supabase.table("anios_epidemiologicos").select("semanas").eq("anio", int(anio))
                 .limit(1).execute().data or [])
        if filas and filas[0].get("semanas"):
            return int(filas[0]["semanas"])
    except Exception:
        pass
    from src.calendario_epi import semanas_anio_epi
    return semanas_anio_epi(int(anio))


def semanas_atras(anio: int, semana: int, n: int) -> List[Tuple[int, int]]:
    """Las `n` semanas ANTERIORES a (anio, semana), de la más reciente a la más antigua."""
    out: List[Tuple[int, int]] = []
    a, s = int(anio), int(semana)
    while len(out) < n:
        s -= 1
        if s < 1:
            a -= 1
            s = semanas_del_anio(a)
        out.append((a, s))
    return out


# ------------------------------------------------------------
# lectura (una sola vez por cálculo)
# ------------------------------------------------------------

def _db():
    from src.db_manager import get_db_manager
    return get_db_manager()


def _parse(v) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _clave_centro(nombre) -> str:
    from app_pages.usuario_logica import _clave_centro as clave
    return clave(nombre)


def _pares(envio: Dict) -> Set[Tuple[str, str]]:
    """(centro, letra de tipo) que cubre un envío (detalle por archivo, o centros × tipos del formulario)."""
    from app_pages.usuario_logica import _pares_de_envio
    try:
        return set(_pares_de_envio(envio))
    except Exception:
        return set()


def justificados(red: Optional[str] = None) -> List[Dict]:
    """Semanas marcadas como «atraso justificado» por un administrador (activas)."""
    try:
        q = _db().supabase.table(T_JUSTIFICADOS).select("*").eq("activo", True)
        if red:
            q = q.eq("red", red)
        return q.order("creado_at", desc=True).limit(500).execute().data or []
    except Exception:
        return []


def marcar_justificado(red: str, anio: int, semana: int, motivo: str, usuario: str) -> Tuple[bool, str]:
    """Un administrador indica que el atraso de esa semana tuvo una causa válida: deja de contar en los patrones."""
    from src.agentes import guardrails
    if guardrails.detectar_pii(str(motivo or "")):
        return False, "El motivo no debe tener datos personales."
    motivo = guardrails.sanitizar_texto_usuario(str(motivo or "")).strip()[:300]
    if len(motivo) < 5:
        return False, "Indique brevemente el motivo (por ejemplo: «feriado regional», «caída del sistema»)."
    try:
        _db().supabase.table(T_JUSTIFICADOS).insert({"red": red, "anio": int(anio), "semana": int(semana),
                                                     "motivo": motivo, "creado_por": usuario}).execute()
    except Exception as e:  # noqa: BLE001
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return False, "Esa semana ya estaba marcada como justificada."
        return False, "No se pudo guardar: ejecute sql/54_sirea_3_2.sql en Supabase."
    try:
        _db().registrar_log(usuario=usuario, accion="ATRASO_JUSTIFICADO",
                            detalle=f"Red: {red} - Semana {semana}/{anio} - {motivo}"[:500])
    except Exception:
        pass
    return True, f"Semana {semana}/{anio} de {red} marcada como justificada: ya no cuenta en sus patrones."


def quitar_justificado(id_, usuario: str) -> bool:
    try:
        r = _db().supabase.table(T_JUSTIFICADOS).update({"activo": False}).eq("id", id_).execute()
        if r.data:
            _db().registrar_log(usuario=usuario, accion="ATRASO_JUSTIFICADO_QUITADO", detalle=f"id={id_}")
        return bool(r.data)
    except Exception:
        return False


def _recordatorios(dias: int) -> List[Dict]:
    """Recordatorios ya enviados (a mano desde Notificaciones o por el agente), con su red y semana."""
    from src.agentes import acciones
    out = list(acciones.recordatorios_manuales(None, dias))
    try:
        desde = datetime.now(timezone.utc).timestamp() - dias * 86400
        desde_iso = datetime.fromtimestamp(desde, timezone.utc).isoformat()
        filas = (_db().supabase.table("agente_acciones").select("red,semana,anio,ejecutada_at")
                 .eq("tipo", "RECORDATORIO_RED").eq("estado", "EJECUTADA").gte("ejecutada_at", desde_iso)
                 .order("ejecutada_at", desc=True).limit(1000).execute().data or [])
        for f in filas:
            d = _parse(f.get("ejecutada_at"))
            if d and d.timestamp() >= desde:
                out.append({"red": f.get("red"), "semana": f.get("semana"), "anio": f.get("anio"),
                            "ejecutada_at": f.get("ejecutada_at"), "origen": "agente"})
    except Exception:
        pass
    return out


@dataclass
class SemanaRed:
    anio: int
    semana: int
    envios: int = 0
    pares: Set[Tuple[str, str]] = field(default_factory=set)
    tarde: bool = False
    tipos_tarde: Set[str] = field(default_factory=set)
    ultimo_envio: Optional[datetime] = None


class Historial:
    """
    Todo lo necesario para calcular patrones de una semana, leído una sola vez:
    envíos vigentes (ni duplicados ni reemplazados) de la semana y de las
    `n` anteriores, centros de cada red, exclusiones, justificados y recordatorios.
    """

    def __init__(self, anio: int, semana: int, n: int = SEMANAS_HISTORIAL):
        self.anio, self.semana, self.n = int(anio), int(semana), int(n)
        self.previas = semanas_atras(self.anio, self.semana, self.n)
        self._semanas = [(self.anio, self.semana)] + self.previas
        self.por_red: Dict[str, Dict[Tuple[int, int], SemanaRed]] = defaultdict(dict)
        self.primera_semana_sistema: Optional[Tuple[int, int]] = None
        self._centros: Dict[str, Dict[str, str]] = {}
        self._excluidos: Dict[str, Set[str]] = {}
        self.justificadas: Dict[str, Set[Tuple[int, int]]] = defaultdict(set)
        self.recordatorios: Dict[Tuple[str, int, int], List[datetime]] = defaultdict(list)
        self._cargar()

    # --- carga ---
    def _envios(self, anio: int, semanas: List[int]) -> List[Dict]:
        """Envíos de un año entre la menor y la mayor semana pedidas, en páginas (Supabase devuelve hasta 1000 por vez)."""
        db, out, pagina = _db(), [], 1000
        cols = "red,anio,semana,centros,tipo_reporte,detalle_archivos,es_atrasado,dias_atraso_envio,fecha_envio,observacion"
        desde = 0
        while desde < 50000:
            try:
                q = (db.supabase.table("envios").select(cols).eq("anio", anio)
                     .gte("semana", min(semanas)).lte("semana", max(semanas)).order("id").range(desde, desde + pagina - 1))
                filas = q.execute().data or []
            except Exception:
                if "detalle_archivos" in cols:      # base sin sql/12: se reintenta sin el detalle por archivo
                    cols = cols.replace(",detalle_archivos", "")
                    continue
                break
            out.extend(filas)
            if len(filas) < pagina:
                break
            desde += pagina
        return out

    def _cargar(self):
        from utils.duplicados import solo_originales
        db = _db()
        validas = set(self._semanas)
        por_anio: Dict[int, List[int]] = defaultdict(list)
        for a, s in self._semanas:
            por_anio[a].append(s)
        for a, sems in sorted(por_anio.items()):
            envios = self._envios(a, sems)
            for e in solo_originales(envios):
                try:
                    clave = (int(e.get("anio") or a), int(e.get("semana")))
                except (TypeError, ValueError):
                    continue
                if self.primera_semana_sistema is None or clave < self.primera_semana_sistema:
                    self.primera_semana_sistema = clave
                if clave not in validas or not e.get("red"):
                    continue
                sem = self.por_red[e["red"]].setdefault(clave, SemanaRed(*clave))
                pares = _pares(e)
                sem.envios += 1
                sem.pares |= pares
                if e.get("es_atrasado") or (e.get("dias_atraso_envio") or 0) > 0:
                    sem.tarde = True
                    sem.tipos_tarde |= {l for _, l in pares}
                d = _parse(e.get("fecha_envio"))
                if d and (sem.ultimo_envio is None or d > sem.ultimo_envio):
                    sem.ultimo_envio = d
        try:   # la primera semana con envíos en todo el sistema (antes, SIREA no estaba en uso)
            primero = db.supabase.table("envios").select("anio,semana").order("anio").order("semana").limit(1).execute().data
            if primero:
                p = (int(primero[0]["anio"]), int(primero[0]["semana"]))
                self.primera_semana_sistema = min(p, self.primera_semana_sistema or p)
        except Exception:
            pass
        for j in justificados():
            try:
                self.justificadas[j["red"]].add((int(j["anio"]), int(j["semana"])))
            except (TypeError, ValueError, KeyError):
                continue
        todas = None
        for r in _recordatorios(dias=7 * (self.n + 2)):
            d = _parse(r.get("ejecutada_at"))
            try:
                if not d or not r.get("red"):
                    continue
                destino = [str(r["red"])]
                if str(r["red"]).strip().lower() in ("todas las redes", "todas"):   # un envío a todas cuenta para cada red
                    todas = todas if todas is not None else self.redes()
                    destino = todas
                for red in destino:
                    self.recordatorios[(red, int(r["anio"]), int(r["semana"]))].append(d)
            except (TypeError, ValueError):
                continue

    def centros(self, red: str) -> Dict[str, str]:
        """{clave del centro: nombre como se muestra en pantalla} sin los excluidos."""
        if red not in self._centros:
            from app_pages.admin_progreso import formatear_centro, obtener_centros_excluidos
            from src.data_loader import get_data_loader
            try:
                excl = set(obtener_centros_excluidos().get(red, []))
            except Exception:
                excl = set()
            mapa = {}
            for c in get_data_loader().obtener_centros(red) or []:
                disp = formatear_centro(c)
                nombre = c.get("nombre") if isinstance(c, dict) else str(c)
                if disp in excl or nombre in excl:
                    continue
                mapa[_clave_centro(disp)] = disp
            self._centros[red] = mapa
        return self._centros[red]

    def redes(self) -> List[str]:
        from src.data_loader import get_data_loader
        try:
            return list(get_data_loader().obtener_redes() or [])
        except Exception:
            return sorted(self.por_red)

    # --- semanas que cuentan ---
    def semanas_analizables(self, red: str) -> List[Tuple[int, int]]:
        """Semanas anteriores que cuentan para el perfil (sin justificadas ni previas al uso de SIREA)."""
        out = []
        for s in self.previas:
            if self.primera_semana_sistema and s < self.primera_semana_sistema:
                continue
            if s in self.justificadas.get(red, set()):
                continue
            out.append(s)
        return out

    # --- tipos esperados por centro ---
    def tipos_esperados(self, red: str) -> Dict[str, Set[str]]:
        """
        {clave del centro: letras que suele mandar}. Se aprende de las semanas
        anteriores; con pocas semanas, basta con haberlo mandado una vez.
        """
        semanas = self.semanas_analizables(red)
        cuenta: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for s in semanas:
            sem = self.por_red.get(red, {}).get(s)
            if not sem:
                continue
            for centro, letra in sem.pares:
                cuenta[centro][letra] += 1
        n = len(semanas)
        out: Dict[str, Set[str]] = {}
        for centro, letras in cuenta.items():
            if n >= MIN_SEMANAS:
                out[centro] = {l for l, k in letras.items() if k / n >= UMBRAL_TIPO_ESPERADO}
            else:
                out[centro] = set(letras)
        return out

    # --- esta semana ---
    def faltantes_por_tipo(self, red: str, anio: Optional[int] = None, semana: Optional[int] = None) -> List[Dict]:
        """
        Por centro: qué tipos ya llegaron y cuáles faltan esta semana.
        Un centro sin historial que no mandó nada figura con «todos sus reportes».
        """
        clave_sem = (int(anio or self.anio), int(semana or self.semana))
        sem = self.por_red.get(red, {}).get(clave_sem) or SemanaRed(*clave_sem)
        recibidos: Dict[str, Set[str]] = defaultdict(set)
        for centro, letra in sem.pares:
            recibidos[centro].add(letra)
        esperados = self.tipos_esperados(red)
        out = []
        for clave, nombre in sorted(self.centros(red).items(), key=lambda x: x[1]):
            esp = esperados.get(clave)
            rec = recibidos.get(clave, set())
            if esp:
                faltan = esp - rec
            elif not rec:
                faltan = None          # sin historial: no se sabe qué tipos manda
            else:
                faltan = set()
            if faltan is None or faltan:
                out.append({"centro": nombre, "recibidos": nombres_tipos(rec),
                            "faltan": nombres_tipos(faltan) if faltan else ["todos sus reportes"],
                            "sin_ningun_envio": not rec, "tipos_aprendidos": bool(esp)})
        return out

    # --- perfil ---
    def perfil(self, red: str) -> Dict:
        """
        Cómo viene la red en las semanas analizables. Una semana cuenta como
        «con problema» si llegó algo TARDE, si NO llegó nada, o si quedó
        INCOMPLETA (algún centro sin envío o sin un tipo que suele mandar).
        """
        semanas = self.semanas_analizables(red)
        datos = self.por_red.get(red, {})
        esperados = self.tipos_esperados(red)
        centros = set(self.centros(red))
        tarde, sin_envio, incompletas, puntuales = [], [], [], []
        por_tipo = defaultdict(int)
        tras_recordatorio = 0
        con_recordatorio = 0
        for s in semanas:
            sem = datos.get(s)
            etiqueta = f"{s[1]}/{s[0]}"
            if not sem or not sem.envios:
                sin_envio.append(etiqueta)
                continue
            recibidos = defaultdict(set)
            for c, l in sem.pares:
                recibidos[c].add(l)
            faltaron = {l for c, esp in esperados.items() for l in esp - recibidos.get(c, set())}
            centros_sin_envio = {c for c in centros if c not in recibidos}
            incompleta = bool(faltaron or centros_sin_envio)
            if sem.tarde:
                tarde.append(etiqueta)
            elif incompleta:
                incompletas.append(etiqueta)
            else:
                puntuales.append(etiqueta)
            for l in faltaron | sem.tipos_tarde:
                por_tipo[l] += 1
            recs = self.recordatorios.get((red, s[0], s[1])) or []
            if recs:
                con_recordatorio += 1
                if sem.ultimo_envio and sem.ultimo_envio > min(recs):
                    tras_recordatorio += 1
        n = len(semanas)
        problema = set(tarde) | set(sin_envio) | set(incompletas)
        malas = len(problema)
        hay_datos = n >= MIN_SEMANAS
        tendencia = "sin datos suficientes"
        if hay_datos:
            # semanas en orden: self.previas va de la más reciente a la más antigua
            marcas = [1 if f"{s[1]}/{s[0]}" in problema else 0 for s in semanas]
            recientes, anteriores = marcas[:3], marcas[3:]
            if len(anteriores) >= 3:
                tasa_r, tasa_a = sum(recientes) / 3, sum(anteriores) / len(anteriores)
                tendencia = ("empeora" if tasa_r - tasa_a >= 0.5 else "mejora" if tasa_a - tasa_r >= 0.5 else "estable")
            else:
                tendencia = "estable"
        # Si viene mejorando, no se la etiqueta por semanas antiguas: lo reciente pesa más (equidad).
        mejora = tendencia == "mejora"
        tipo_cronico = None
        if hay_datos and por_tipo and not mejora:
            letra, veces = max(por_tipo.items(), key=lambda x: x[1])
            if veces / n >= UMBRAL_PATRON and veces >= 3:
                tipo_cronico = {"tipo": nombre_tipo(letra), "semanas": veces, "de": n}
        patron = hay_datos and malas / n >= UMBRAL_PATRON and not mejora
        return {
            "red": red, "semanas_analizadas": n, "minimo_para_patron": MIN_SEMANAS, "hay_datos_suficientes": hay_datos,
            "semanas_tarde": len(tarde), "semanas_incompletas": len(incompletas), "semanas_sin_envio": len(sin_envio),
            "semanas_a_tiempo": len(puntuales), "semanas_con_problema": malas, "lista_semanas_tarde": tarde,
            "lista_semanas_incompletas": incompletas, "lista_semanas_sin_envio": sin_envio,
            "suele_atrasarse": bool(patron), "tipo_que_suele_faltar": tipo_cronico, "tendencia": tendencia,
            "semanas_con_recordatorio": con_recordatorio, "envio_despues_del_recordatorio": tras_recordatorio,
            "suele_esperar_recordatorio": bool(hay_datos and not mejora and con_recordatorio >= 3
                                               and tras_recordatorio / con_recordatorio >= UMBRAL_PATRON),
            "semanas_justificadas_excluidas": len(self.justificadas.get(red, set()) & set(self.previas)),
            "texto": describir_perfil_dict(red, n, malas, tarde, sin_envio, tipo_cronico, tendencia, hay_datos),
        }

    # --- panorama ---
    def panorama(self) -> Dict:
        """La semana en curso para todas las redes (para el admin y el informe; nunca para un correo a una red)."""
        filas = []
        for red in self.redes():
            if not self.centros(red):
                continue
            falt = self.faltantes_por_tipo(red)
            sem = self.por_red.get(red, {}).get((self.anio, self.semana))
            filas.append({"red": red, "completa": not falt, "envios": sem.envios if sem else 0,
                          "tarde": bool(sem and sem.tarde), "centros_con_pendientes": len(falt),
                          "centros_sin_ningun_envio": sum(1 for f in falt if f["sin_ningun_envio"])})
        pend = [f["red"] for f in filas if not f["completa"]]
        return {"anio": self.anio, "semana": self.semana, "redes_total": len(filas),
                "redes_completas": len(filas) - len(pend), "redes_pendientes": pend,
                "redes_con_envio_tardio": [f["red"] for f in filas if f["tarde"]], "detalle": filas}


def describir_perfil_dict(red, n, malas, tarde, sin_envio, tipo_cronico, tendencia, hay_datos) -> str:
    """Frase corta y neutra para el administrador (usa solo las cuentas de arriba)."""
    if not hay_datos:
        return (f"Aún no hay suficientes semanas con datos para hablar de un patrón ({n} de {MIN_SEMANAS} necesarias).")
    partes = [f"Envío tarde o incompleto en {malas} de las últimas {n} semanas" if malas
              else f"A tiempo en las últimas {n} semanas"]
    if tipo_cronico:
        partes.append(f"lo que más falta o llega tarde es {tipo_cronico['tipo']} ({tipo_cronico['semanas']} de {n})")
    if tendencia in ("empeora", "mejora"):
        partes.append("viene empeorando en las últimas 3 semanas" if tendencia == "empeora"
                      else "viene mejorando en las últimas 3 semanas")
    return "; ".join(partes) + "."


# ------------------------------------------------------------
# atajos
# ------------------------------------------------------------

def historial_semana_activa(n: int = SEMANAS_HISTORIAL) -> Historial:
    from src.agentes.herramientas import info_semana_actual
    info = info_semana_actual()
    return Historial(int(info["anio"]), int(info["semana_activa"]), n)


def redes_con_patron(h: Optional[Historial] = None) -> List[Dict]:
    """Redes que suelen atrasarse o que vienen empeorando (las que conviene recordar ANTES del corte)."""
    h = h or historial_semana_activa()
    out = []
    for red in h.redes():
        p = h.perfil(red)
        if p["suele_atrasarse"] or p["tendencia"] == "empeora" or p["tipo_que_suele_faltar"]:
            out.append(p)
    return sorted(out, key=lambda p: -p["semanas_con_problema"])


def redes_que_mejoran(h: Optional[Historial] = None) -> List[Dict]:
    h = h or historial_semana_activa()
    return [p for p in (h.perfil(r) for r in h.redes()) if p["tendencia"] == "mejora"]
