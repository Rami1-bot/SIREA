# tests/fake_supabase.py
"""
Supabase SIMULADO en memoria para abrir SIREA en un navegador sin red ni
claves (prueba de humo de pantallas) y para pruebas automatizadas.

    python -m streamlit run tests/smoke_app.py

Soporta lo que usa la aplicación: table().select/insert/upsert/update/
delete, eq/neq/gt/gte/lt/lte/like/ilike/in_/is_/or_, order/limit/range/
single, .execute().data y .count. Las tablas arrancan con datos mínimos de
demostración (un SUPER_ADMIN principal `oiis.winepi` / `Sirea-Demo-2026!`).
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


class _Resultado:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Query:
    def __init__(self, db: "FakeSupabase", tabla: str):
        self.db, self.tabla = db, tabla
        self._op, self._payload, self._on_conflict = "select", None, None
        self._filtros: List = []
        self._order: Optional[tuple] = None
        self._limit: Optional[int] = None
        self._range: Optional[tuple] = None
        self._single = False
        self._count = None

    # --- construcción ---
    def select(self, *a, count=None, **k):
        self._op, self._count = "select", count
        return self

    def insert(self, payload, **k):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None, **k):
        self._op, self._payload, self._on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload, **k):
        self._op, self._payload = "update", payload
        return self

    def delete(self, **k):
        self._op = "delete"
        return self

    def _f(self, tipo, col, val):
        self._filtros.append((tipo, col, val))
        return self

    def eq(self, c, v): return self._f("eq", c, v)
    def neq(self, c, v): return self._f("neq", c, v)
    def gt(self, c, v): return self._f("gt", c, v)
    def gte(self, c, v): return self._f("gte", c, v)
    def lt(self, c, v): return self._f("lt", c, v)
    def lte(self, c, v): return self._f("lte", c, v)
    def like(self, c, v): return self._f("like", c, v)
    def ilike(self, c, v): return self._f("ilike", c, v)
    def in_(self, c, v): return self._f("in", c, list(v))
    def is_(self, c, v): return self._f("is", c, v)
    def or_(self, *a, **k): return self
    def not_(self): return self

    def order(self, col, desc=False, **k):
        self._order = (col, desc)
        return self

    def limit(self, n, **k):
        self._limit = n
        return self

    def range(self, a, b, **k):
        self._range = (a, b)
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    # --- ejecución ---
    def _cumple(self, fila) -> bool:
        for tipo, col, val in self._filtros:
            x = fila.get(col)
            if tipo == "eq" and not (str(x) == str(val) if x is not None else val is None):
                return False
            if tipo == "neq" and str(x) == str(val):
                return False
            if tipo in ("gt", "gte", "lt", "lte"):
                try:
                    a, b = (float(x), float(val)) if not isinstance(x, str) or re.match(r"^-?\d+(\.\d+)?$", str(x)) else (str(x), str(val))
                except (TypeError, ValueError):
                    a, b = str(x), str(val)
                if tipo == "gt" and not a > b: return False
                if tipo == "gte" and not a >= b: return False
                if tipo == "lt" and not a < b: return False
                if tipo == "lte" and not a <= b: return False
            if tipo in ("like", "ilike"):
                pat = "^" + re.escape(str(val)).replace("%", ".*").replace("\\%", ".*") + "$"
                if not re.match(pat, str(x or ""), re.I if tipo == "ilike" else 0):
                    return False
            if tipo == "in" and str(x) not in [str(v) for v in val]:
                return False
            if tipo == "is" and not ((val is None and x is None) or (val == "null" and x is None) or (val is not None and x == val)):
                return False
        return True

    def execute(self):
        filas = self.db.tablas.setdefault(self.tabla, [])
        if self._op == "insert":
            nuevos = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for n in nuevos:
                n = {**copy.deepcopy(self.db.defaults.get(self.tabla, {})), **dict(n)}
                for cols, cond in self.db.unicos.get(self.tabla, ()):
                    if cond(n) and any(cond(f) and all(str(f.get(c)) == str(n.get(c)) for c in cols) for f in filas):
                        raise Exception(f"duplicate key value violates unique constraint (23505) on {self.tabla}{cols}")
                n.setdefault("id", self.db._next_id(self.tabla))
                for c in self.db.auto_fecha.get(self.tabla, ()):
                    if not n.get(c):
                        n[c] = datetime.now(timezone.utc).isoformat()
                filas.append(n)
                out.append(copy.deepcopy(n))
            return _Resultado(out)
        if self._op == "upsert":
            nuevos = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for n in nuevos:
                n = dict(n)
                clave = self._on_conflict or "id"
                ex = next((f for f in filas if clave in n and str(f.get(clave)) == str(n[clave])), None)
                if ex:
                    ex.update(n)
                    out.append(copy.deepcopy(ex))
                else:
                    n.setdefault("id", self.db._next_id(self.tabla))
                    filas.append(n)
                    out.append(copy.deepcopy(n))
            return _Resultado(out)
        if self._op == "update":
            out = []
            for f in filas:
                if self._cumple(f):
                    f.update(self._payload or {})
                    out.append(copy.deepcopy(f))
            return _Resultado(out)
        if self._op == "delete":
            keep, out = [], []
            for f in filas:
                (out if self._cumple(f) else keep).append(f)
            self.db.tablas[self.tabla] = keep
            return _Resultado(copy.deepcopy(out))
        # select
        sel = [copy.deepcopy(f) for f in filas if self._cumple(f)]
        if self._order:
            col, desc = self._order
            sel.sort(key=lambda r: (r.get(col) is None, str(r.get(col)) if not isinstance(r.get(col), (int, float)) else r.get(col)), reverse=desc)
        total = len(sel)
        if self._range:
            a, b = self._range
            sel = sel[a:b + 1]
        if self._limit is not None:
            sel = sel[: self._limit]
        if self._single:
            return _Resultado(sel[0] if sel else None, total)
        return _Resultado(sel, total if self._count else None)


class _RPC:
    def __init__(self, data=None):
        self.data = data

    def execute(self):
        return _Resultado(self.data)


class FakeSupabase:
    def __init__(self):
        self.tablas: Dict[str, List[Dict[str, Any]]] = {}
        self._ids: Dict[str, int] = {}
        self.auto_fecha = {"logs": ("fecha",), "envios": ("fecha_envio",), "auditoria_agentes_ia": ("fecha",),
                           "solicitudes_password": ("fecha_creacion",), "solicitudes_password_mensajes": ("fecha",),
                           "agente_corridas": ("inicio",), "agente_traza": ("fecha",), "agente_acciones": ("creada_at",),
                           "agente_memoria_red": ("creada_at",), "agente_evals": ("fecha",),
                           "agente_skill_versiones": ("creada_at",), "agente_atrasos_justificados": ("creado_at",),
                           "agente_informes": ("creado_at",),
                           "observaciones_envio": ("fecha_creacion",)}
        # valores por defecto de columnas (como en el SQL)
        self.defaults = {
            "agente_corridas": {"estado": "EN_CURSO", "fin": None, "n_casos": 0, "n_propuestas": 0, "n_descartadas": 0,
                                "n_sin_accion": 0, "proveedor": None, "resumen": None, "error": None},
            "agente_acciones": {"estado": "PROPUESTA", "decidida_por": None, "decidida_at": None, "motivo_decision": None,
                                "editada": False, "ejecutada_at": None, "resultado": None, "origen": "ia"},
            "agente_memoria_red": {"activa": True, "fuente": "humano", "vigente_hasta": None},
            "agente_skill_versiones": {"estado": "PROPUESTA", "decidida_por": None, "decidida_at": None, "motivo_decision": None},
            "agente_atrasos_justificados": {"activo": True},
            "agente_informes": {"estado": "BORRADOR", "texto_final": None, "aprobado_por": None, "aprobado_at": None,
                                "motivo_descarte": None},
        }
        # índices únicos: (columnas, condición de la fila) — p. ej. el índice parcial de la cola
        self.unicos = {"agente_acciones": [(("clave_unica",), lambda f: f.get("estado") == "PROPUESTA")],
                       "agente_skill_versiones": [(("skill",), lambda f: f.get("estado") == "APROBADA")],
                       "agente_atrasos_justificados": [(("red", "anio", "semana"), lambda f: f.get("activo"))]}
        self._sembrar()

    def _next_id(self, tabla):
        self._ids[tabla] = max(self._ids.get(tabla, 0), max([int(f.get("id") or 0) for f in self.tablas.get(tabla, [])] or [0])) + 1
        return self._ids[tabla]

    def table(self, nombre):
        return _Query(self, nombre)

    def from_(self, nombre):
        return _Query(self, nombre)

    def rpc(self, *a, **k):
        return _RPC([])

    # ---------------- datos de demostración ----------------
    def _sembrar(self):
        from src.security import hash_password
        ahora = datetime.now(timezone.utc)
        self.tablas["administradores"] = [
            {"id": 1, "usuario": "oiis.winepi", "nombre": "Responsable OIIS", "email": "oiis@essalud.gob.pe",
             "rol": "SUPER_ADMIN", "activo": True, "password_hash": hash_password("Sirea-Demo-2026!"),
             "fecha_creacion": ahora.isoformat(), "ultimo_login": None},
            {"id": 2, "usuario": "ana.admin", "nombre": "Ana Admin", "email": "ana@essalud.gob.pe",
             "rol": "ADMIN", "activo": True, "password_hash": hash_password("Clave-Admin-2026!"),
             "fecha_creacion": ahora.isoformat(), "ultimo_login": None},
        ]
        self.tablas["anios_epidemiologicos"] = [
            {"id": 1, "anio": 2026, "semanas": 52, "fecha_inicio": "2026-01-04", "fecha_fin": "2027-01-02", "activo": True},
        ]
        self.tablas["configuracion"] = [
            {"id": 1, "clave": "semana_activa", "valor": "40"},
            {"id": 2, "clave": "fecha_corte", "valor": "2026-10-21 23:59:59"},
            {"id": 3, "clave": "agentes_ia_estado", "valor": "ACTIVO_HITL"},
            {"id": 5, "clave": "agentes_ia_estado_investigador", "valor": "ACTIVO_HITL"},
        ]
        self.tablas["redes"] = [{"id": i + 1, "nombre": n} for i, n in enumerate(["ALMENARA", "ANCASH", "AREQUIPA"])]
        self.tablas["centros"] = []
        for r in self.tablas["redes"]:
            for j in range(4):
                self.tablas["centros"].append({"id": len(self.tablas["centros"]) + 1, "red_id": r["id"],
                                               "codigo": f"{r['id']}{j:02d}", "nombre": f"C.M. DEMO {r['nombre'][:3]} {j + 1}"})
        self.tablas["centros_excluidos"] = [{"id": 1, "red_id": 2, "centro_nombre": "C.M. DEMO ANC 4", "motivo": "Sin personal (caso excepcional)",
                                             "creado_por": "oiis.winepi", "fecha_exclusion": ahora.isoformat()}]
        self.tablas["credenciales_red"] = [{"id": 1, "red": "ANCASH", "password_hash": hash_password("Red-Ancash-2026!"), "activo": True,
                                            "fecha_creacion": ahora.isoformat(), "fecha_actualizacion": ahora.isoformat()}]
        self.tablas["carpetas_drive"] = [{"id": 1, "nombre": "Envíos 2026", "folder_id": "demo-folder", "activo": True, "capacidad_maxima_mb": 10000, "usado_mb": 120}]
        self.tablas["envios"] = []
        for i, (red, centros, dias) in enumerate([("ALMENARA", ["C.M. DEMO ALM 1", "C.M. DEMO ALM 2"], 3),
                                                   ("ANCASH", ["C.M. DEMO ANC 1"], 1),
                                                   ("AREQUIPA", ["C.M. DEMO ARE 1", "C.M. DEMO ARE 2", "C.M. DEMO ARE 3"], 0)]):
            self.tablas["envios"].append({
                "id": i + 1, "nombre_usuario": "Persona", "apellido_usuario": "Demo", "correo_usuario": "demo@essalud.gob.pe",
                "red": red, "centros": [{"nombre": c, "codigo": "000"} for c in centros], "semana": 40, "anio": 2026,
                "tipo_reporte": ["SEMANAL"], "fecha_envio": (ahora - timedelta(days=dias)).isoformat(), "ruta_zip": None,
                "drive_file_id": None, "cantidad_archivos": len(centros), "estado": "PROCESADO", "observacion": None,
                "es_atrasado": False, "version": 1, "codigo_seguimiento": f"ESS-DEMO-000{i + 1}", "semana_activa_envio": 40,
                "dias_atraso_envio": 0,
            })
        self.tablas["logs"] = [{"id": 1, "usuario": "oiis.winepi", "accion": "LOGIN", "detalle": "Inicio de sesión", "fecha": ahora.isoformat(), "ip": "127.0.0.1"}]
        self.tablas["auditoria_agentes_ia"] = [
            {"id": 1, "fecha": (ahora - timedelta(hours=2)).isoformat(), "usuario": "oiis.winepi", "rol": "SUPER_ADMIN",
             "agente": "investigador", "evento": "CONSULTA", "modelo": "gemini:gemini-3.6-flash",
             "entrada": "¿Por qué ANCASH no cierra?", "salida": "Situación: la red ANCASH va al 33 %…",
             "herramientas": ["progreso_de_una_red", "envios_tardios_de_red"], "observaciones": [], "duracion_ms": 1800},
            {"id": 2, "fecha": (ahora - timedelta(hours=1)).isoformat(), "usuario": "oiis.winepi", "rol": "SUPER_ADMIN",
             "agente": "solicitudes", "evento": "BORRADOR", "modelo": "groq:modelo-x", "referencia": "SOL-1",
             "entrada": "[SOL-1] red=ANCASH", "salida": "Sugerencia: APROBAR…", "herramientas": [],
             "observaciones": ["sugerencia:APROBAR"], "duracion_ms": 900},
            {"id": 3, "fecha": (ahora - timedelta(minutes=30)).isoformat(), "usuario": "ana.admin", "rol": "ADMIN",
             "agente": "sistema", "evento": "CAMBIO_ESTADO", "modelo": None, "entrada": "INACTIVO -> EN_REVISION",
             "salida": "prueba", "herramientas": [], "observaciones": []},
        ]
        self.tablas["solicitudes_password"] = [{"id": 1, "codigo": "SOL-0001", "red": "ANCASH", "nombre": "Juan Pérez", "correo": "jp@essalud.gob.pe",
                                                "estado": "PENDIENTE", "fecha_creacion": (ahora - timedelta(days=1)).isoformat()}]
        self.tablas["solicitudes_password_mensajes"] = [{"id": 1, "solicitud_id": 1, "autor_tipo": "RED", "autor": "Juan Pérez",
                                                         "mensaje": "Estimados señores de la OIIS:\n\nLa contraseña fue compartida con personal que ya no labora en la red; solicitamos cambiarla.\n\nAtentamente,\nJuan Pérez\nRed ANCASH",
                                                         "fecha": (ahora - timedelta(days=1)).isoformat()}]
        for t in ("cierres_corte", "respaldos", "destinatarios_externos", "permisos_operaciones", "descargas_masivas",
                  "retiros_archivos", "solicitudes_retiro", "sesiones_app", "intentos_login",
                  "agente_corridas", "agente_traza", "agente_acciones", "agente_memoria_red", "agente_evals",
                  "agente_skill_versiones", "agente_atrasos_justificados", "agente_informes"):
            self.tablas[t] = []
        # SIRE v7: bandeja de observaciones (para el Agente Operativo)
        self.tablas["observaciones_envio"] = [
            {"id": 1, "envio_id": 2, "codigo_seguimiento": "ESS-DEMO-0002", "red": "ANCASH", "semana": 40, "anio": 2026,
             "remitente": "Persona Demo", "correo": "demo@essalud.gob.pe", "motivo": "SUSTENTO", "estado_envio": "PROCESADO",
             "texto": "Enviamos tarde porque el lunes fue feriado regional; el resto llega mañana.", "detalle": None,
             "revisada": False, "fecha_creacion": (ahora - timedelta(hours=20)).isoformat()},
            {"id": 2, "envio_id": 3, "codigo_seguimiento": "ESS-DEMO-0003", "red": "AREQUIPA", "semana": 40, "anio": 2026,
             "remitente": "Persona Demo", "correo": "demo@essalud.gob.pe", "motivo": "OBSERVADO", "estado_envio": "OBSERVADO",
             "texto": None, "detalle": "El nombre del archivo indica el código de centro 'CAPX-12', que no existe en el catálogo.",
             "revisada": False, "fecha_creacion": (ahora - timedelta(hours=5)).isoformat()},
        ]
        self.tablas["auditoria_acciones"] = []


def instalar(monkeypatch=None):
    """Hace que `create_client` devuelva el Supabase simulado (para pruebas o para smoke_app)."""
    import src.db_manager as dbm
    fake = FakeSupabase()
    # SIRE v6.2+ crea el cliente con crear_cliente_supabase (src/conexion_supabase.py);
    # versiones anteriores usaban create_client. Se reemplazan ambos.
    for nombre in ("create_client", "crear_cliente_supabase"):
        if hasattr(dbm, nombre):
            if monkeypatch:
                monkeypatch.setattr(dbm, nombre, lambda *a, **k: fake)
            else:
                setattr(dbm, nombre, lambda *a, **k: fake)
    return fake
