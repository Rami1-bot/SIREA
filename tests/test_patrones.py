# tests/test_patrones.py
"""
SIREA 3.2 · Patrones de envío (sin IA) con Supabase SIMULADO.

Historial sembrado (semana activa 40/2026, ventana 32-39):
  ALMENARA  centro 1 manda C+H+E, centros 2 y 3 solo C (el 4 está excluido);
            tarde en 5 de 8 semanas, casi siempre con Emergencia; esta semana al
            centro 1 le falta E y el centro 3 no mandó nada.
  AREQUIPA  siempre a tiempo.
  ANCASH    tarde las semanas 32-35 y a tiempo desde la 36 (mejora).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")


def _envio(fake, red, semana, archivos, tarde=False, anio=2026, horas_despues=0, correo="resp@essalud.gob.pe"):
    """archivos: [(centro, letra)]"""
    fecha = datetime(2026, 1, 4, 12, tzinfo=timezone.utc) + timedelta(weeks=semana - 1, days=4, hours=horas_despues)
    fake.tablas["envios"].append({
        "id": len(fake.tablas["envios"]) + 1, "nombre_usuario": "Resp", "apellido_usuario": "Envio", "correo_usuario": correo,
        "red": red, "centros": sorted({c for c, _ in archivos}), "semana": semana, "anio": anio,
        "tipo_reporte": [], "fecha_envio": fecha.isoformat(), "estado": "PROCESADO", "observacion": None,
        "es_atrasado": tarde, "dias_atraso_envio": 2 if tarde else 0, "cantidad_archivos": len(archivos),
        "codigo_seguimiento": f"T-{len(fake.tablas['envios']) + 1}", "semana_activa_envio": semana,
        "detalle_archivos": [{"archivo": f"p{l}{semana}26.x", "centro": c, "tipo": l, "semana": semana, "anio": anio}
                             for c, l in archivos],
    })


ALM1, ALM2 = "C.M. DEMO ALM 1", "C.M. DEMO ALM 2"


def sembrar(fake):
    fake.tablas["envios"] = []
    fake.tablas["centros_excluidos"] = [{"id": 1, "red_id": 1, "redes": {"nombre": "ALMENARA"}, "centro_nombre": "C.M. DEMO ALM 4", "motivo": "Cerrado (prueba)",
                                         "creado_por": "oiis.winepi", "fecha_exclusion": "2026-01-01T00:00:00+00:00"}]
    tarde_alm = {39, 38, 37, 35, 33}
    for s in range(32, 40):
        # ALMENARA: lo normal llega a tiempo; la Emergencia llega tarde en las semanas marcadas
        _envio(fake, "ALMENARA", s, [(ALM1, "c"), (ALM1, "h"), (ALM2, "c"), ("C.M. DEMO ALM 3", "c")])
        _envio(fake, "ALMENARA", s, [(ALM1, "e")], tarde=s in tarde_alm)
        _envio(fake, "AREQUIPA", s, [(f"C.M. DEMO ARE {i}", "c") for i in range(1, 5)])
        _envio(fake, "ANCASH", s, [(f"C.M. DEMO ANC {i}", "c") for i in range(1, 5)], tarde=s <= 35)
    _envio(fake, "ALMENARA", 40, [(ALM1, "c"), (ALM1, "h"), (ALM2, "c")])
    _envio(fake, "AREQUIPA", 40, [(f"C.M. DEMO ARE {i}", "c") for i in range(1, 5)])


@pytest.fixture
def bd(monkeypatch):
    from tests.fake_supabase import instalar
    import src.db_manager as dbm
    import src.data_loader as dl
    fake = instalar(monkeypatch)
    monkeypatch.setattr(dbm, "_db_manager", None)
    monkeypatch.setattr(dl, "_data_loader", None)
    fake.tablas.setdefault("agente_atrasos_justificados", [])
    sembrar(fake)
    return fake


def _h():
    from src.agentes.patrones import Historial
    return Historial(2026, 40, 8)


def test_semanas_atras_cruza_el_cambio_de_anio():
    from src.agentes.patrones import semanas_atras
    # 2025 tiene 53 semanas epidemiológicas en el calendario estándar (si el panel no dice otra cosa)
    assert semanas_atras(2026, 2, 3) == [(2026, 1), (2025, 53), (2025, 52)]


def test_tipos_esperados_se_aprenden_del_historial(bd):
    h = _h()
    esp = h.tipos_esperados("ALMENARA")
    assert esp["c.m. demo alm 1"] == {"c", "h", "e"}
    assert esp["c.m. demo alm 2"] == {"c"}          # nunca mandó H ni E: no se le pide


def test_faltantes_por_tipo_de_la_semana(bd):
    falt = {f["centro"]: f for f in _h().faltantes_por_tipo("ALMENARA")}
    alm1 = next(v for k, v in falt.items() if k.endswith("ALM 1"))
    assert alm1["faltan"] == ["Emergencia"] and alm1["recibidos"] == ["Consulta Externa", "Hospitalización"]
    assert not any(k.endswith(("ALM 2", "ALM 4")) for k in falt)          # completo / excluido
    alm3 = next(v for k, v in falt.items() if k.endswith("ALM 3"))
    assert alm3["sin_ningun_envio"] and alm3["faltan"] == ["Consulta Externa"] and alm3["tipos_aprendidos"]


def test_centro_sin_historial_figura_con_todos_sus_reportes(bd):
    bd.tablas["envios"] = [e for e in bd.tablas["envios"]
                           if not (e["red"] == "ALMENARA" and "C.M. DEMO ALM 3" in e["centros"] and e["semana"] < 40)
                           or e["centros"] != ["C.M. DEMO ALM 3"]]
    for e in bd.tablas["envios"]:
        if e["red"] == "ALMENARA":
            e["detalle_archivos"] = [d for d in e["detalle_archivos"] if d["centro"] != "C.M. DEMO ALM 3"]
    alm3 = next(v for v in _h().faltantes_por_tipo("ALMENARA") if v["centro"].endswith("ALM 3"))
    assert alm3["faltan"] == ["todos sus reportes"] and not alm3["tipos_aprendidos"]


def test_semana_a_tiempo_pero_incompleta_cuenta_como_problema(bd):
    # AREQUIPA: solo el centro 1 envía (a tiempo) durante las 8 semanas
    for e in bd.tablas["envios"]:
        if e["red"] == "AREQUIPA":
            e["detalle_archivos"] = [d for d in e["detalle_archivos"] if d["centro"] == "C.M. DEMO ARE 1"]
            e["centros"] = ["C.M. DEMO ARE 1"]
    p = _h().perfil("AREQUIPA")
    assert p["semanas_incompletas"] == 8 and p["semanas_tarde"] == 0 and p["suele_atrasarse"] is True
    assert "8 de las últimas 8" in p["texto"]


def test_perfil_red_que_suele_atrasarse(bd):
    p = _h().perfil("ALMENARA")
    assert p["semanas_analizadas"] == 8 and p["semanas_tarde"] == 5
    assert p["suele_atrasarse"] is True
    assert p["tipo_que_suele_faltar"]["tipo"] == "Emergencia"
    assert "5 de las últimas 8" in p["texto"]
    assert "39/2026" in p["lista_semanas_tarde"]          # la prueba: qué semanas


def test_perfil_red_puntual_y_red_que_mejora(bd):
    h = _h()
    assert h.perfil("AREQUIPA")["suele_atrasarse"] is False and h.perfil("AREQUIPA")["semanas_con_problema"] == 0
    anc = h.perfil("ANCASH")
    assert anc["tendencia"] == "mejora" and anc["semanas_tarde"] == 4
    assert anc["suele_atrasarse"] is False          # mejoró: no se le etiqueta por semanas antiguas
    assert anc["tipo_que_suele_faltar"] is None and anc["suele_esperar_recordatorio"] is False


def test_atraso_justificado_no_cuenta(bd):
    from src.agentes import patrones
    for s in (39, 38):
        ok, _ = patrones.marcar_justificado("ALMENARA", 2026, s, "Feriado regional y caída del sistema", "oiis.winepi")
        assert ok
    p = _h().perfil("ALMENARA")
    assert p["semanas_analizadas"] == 6 and p["semanas_tarde"] == 3 and p["semanas_justificadas_excluidas"] == 2
    ok, msg = patrones.marcar_justificado("ALMENARA", 2026, 37, "x", "oiis.winepi")
    assert not ok and "motivo" in msg


def test_sin_semanas_suficientes_no_hay_patron(bd):
    bd.tablas["envios"] = [e for e in bd.tablas["envios"] if e["semana"] >= 38]   # SIREA se empezó a usar en la 38
    p = _h().perfil("ALMENARA")
    assert p["semanas_analizadas"] == 2 and p["hay_datos_suficientes"] is False
    assert p["suele_atrasarse"] is False and "Aún no hay suficientes semanas" in p["texto"]


def test_panorama_de_la_semana(bd):
    pan = _h().panorama()
    assert pan["redes_total"] == 3
    assert set(pan["redes_pendientes"]) == {"ALMENARA", "ANCASH"}
    assert pan["redes_completas"] == 1


def test_redes_con_patron(bd):
    from src.agentes import patrones
    nombres = [p["red"] for p in patrones.redes_con_patron(_h())]
    assert "ALMENARA" in nombres and "AREQUIPA" not in nombres
