# tests/test_sirea_3_2.py
"""
SIREA 3.2 con Supabase SIMULADO: recordatorio formal por tipo de reporte
(responsables en copia, borrador, control de tono, vista previa), expedientes
con patrones, informe semanal, asistente y su registro.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from tests.test_patrones import sembrar, _envio  # noqa: E402

SUPER = {"usuario": "oiis.winepi", "rol": "SUPER_ADMIN"}


@pytest.fixture
def bd(monkeypatch):
    from tests.fake_supabase import instalar
    import src.db_manager as dbm
    import src.data_loader as dl
    import src.observaciones as obs
    fake = instalar(monkeypatch)
    monkeypatch.setattr(dbm, "_db_manager", None)
    monkeypatch.setattr(dl, "_data_loader", None)
    monkeypatch.setattr(obs, "_instancia", None)
    fake.tablas["observaciones_envio"] = []
    for clave, valor in (("agentes_ia_estado", "ACTIVO_HITL"), ("agentes_ia_estado_operativo", "ACTIVO_HITL"),
                         ("agentes_ia_estado_investigador", "ACTIVO_HITL")):
        filas = fake.tablas["configuracion"]
        ex = next((f for f in filas if f["clave"] == clave), None)
        if ex:
            ex["valor"] = valor
        else:
            filas.append({"id": 900 + len(filas), "clave": clave, "valor": valor})
    sembrar(fake)
    # dos responsables que enviaron por ALMENARA
    _envio(fake, "ALMENARA", 39, [("C.M. DEMO ALM 2", "c")], correo="otra.resp@essalud.gob.pe")
    return fake


@pytest.fixture
def correo(monkeypatch):
    enviados = []
    import src.email_sender as es
    real = es.get_email_sender()

    class _Sender:
        def componer_recordatorio(self, *a, **k):
            return real.componer_recordatorio(*a, **k)

        def enviar_recordatorio(self, *a, **k):
            enviados.append(k)
            return True, "enviado"

    monkeypatch.setattr(es, "get_email_sender", lambda: _Sender())
    return enviados


# ------------------------------------------------------------
# borrador formal y tono
# ------------------------------------------------------------

def test_borrador_formal_dice_que_falta_por_tipo():
    from src.agentes.acciones import borrador_formal
    t = borrador_formal([{"centro": "Hospital X", "recibidos": ["Consulta Externa", "Hospitalización"], "faltan": ["Emergencia"],
                          "sin_ningun_envio": False}], vencido=False, preventivo_por_historial=True)
    assert "Consulta Externa y Hospitalización del Hospital X" in t
    assert "pendiente: Emergencia del Hospital X" in t
    assert "antes de la fecha límite" in t and "apoyo" in t


@pytest.mark.parametrize("texto", [
    "Su red es la única red que no envió.",
    "Las demás redes ya cumplieron con el envío.",
    "Nuevamente le recordamos que falta el reporte.",
    "Su red se atrasó 6 de las últimas 8 semanas.",
    "Como ya hizo ANCASH, le pedimos enviar.",
    "De lo contrario habrá consecuencias.",
])
def test_problema_de_tono_detecta_comparaciones_y_reproches(texto):
    from src.agentes.acciones import problema_de_tono
    assert problema_de_tono(texto, "ALMENARA", ["ALMENARA", "ANCASH", "AREQUIPA"])


def test_texto_formal_pasa_el_control_de_tono():
    from src.agentes.acciones import problema_de_tono
    assert problema_de_tono("Le agradeceremos compartir el reporte de Emergencia del Hospital X a través de SIREA "
                            "antes de la fecha límite. Quedamos atentos por si requiere apoyo.", "ALMENARA", ["ANCASH"]) is None


def _exp_red(**extra):
    exp = {"tipo_caso": "red", "red": "ALMENARA", "anio": 2026, "semana": 40, "horas_al_corte": 30,
           "faltantes": ["300 C.M. DEMO ALM 3"],
           "pendientes_por_tipo": [{"centro": "100 C.M. DEMO ALM 1", "recibidos": ["Consulta Externa"], "faltan": ["Emergencia"],
                                    "sin_ningun_envio": False},
                                   {"centro": "300 C.M. DEMO ALM 3", "recibidos": [], "faltan": ["todos sus reportes"],
                                    "sin_ningun_envio": True}],
           "acciones_previas": [], "_otras_redes": ["ANCASH", "AREQUIPA"]}
    exp.update(extra)
    return exp


def test_mensaje_comparativo_de_la_ia_se_reemplaza_por_el_borrador():
    from src.agentes.acciones import procesar_propuesta
    acc, motivo = procesar_propuesta({"tipo": "RECORDATORIO_RED", "centros_pendientes": ["100 C.M. DEMO ALM 1", "300 C.M. DEMO ALM 3"],
                                      "mensaje_personalizado": "Su red es la única que falta; las demás redes ya enviaron."},
                                     _exp_red(), ("RECORDATORIO_RED",), preparar=False)
    assert motivo is None
    p = acc["payload"]
    assert p["aviso_mensaje"] and p["mensaje_origen"] == "plantilla"
    assert "única" not in p["mensaje_personalizado"] and "Emergencia del 100 C.M. DEMO ALM 1" in p["mensaje_personalizado"]
    assert [x["centro"] for x in p["pendientes_por_tipo"]] == ["100 C.M. DEMO ALM 1", "300 C.M. DEMO ALM 3"]


def test_centro_parcial_es_un_pendiente_valido_y_uno_inventado_no():
    from src.agentes.acciones import procesar_propuesta
    acc, motivo = procesar_propuesta({"tipo": "RECORDATORIO_RED", "centros_pendientes": ["100 C.M. DEMO ALM 1"]},
                                     _exp_red(), ("RECORDATORIO_RED",), preparar=False)
    assert motivo is None and acc["payload"]["mensaje_origen"] == "plantilla"
    _, motivo = procesar_propuesta({"tipo": "RECORDATORIO_RED", "centros_pendientes": ["CENTRO INVENTADO"]},
                                   _exp_red(), ("RECORDATORIO_RED",), preparar=False)
    assert motivo and "no están pendientes" in motivo


# ------------------------------------------------------------
# responsables, copia, vista previa y ejecución
# ------------------------------------------------------------

def test_responsables_de_la_red_y_copias(bd):
    from src.agentes.acciones import _prep_recordatorio, responsables_de_red
    resp = responsables_de_red("ALMENARA")
    assert [r["correo"] for r in resp] == ["resp@essalud.gob.pe", "otra.resp@essalud.gob.pe"]   # el más reciente primero
    prep = _prep_recordatorio({"red": "ALMENARA"}, {})
    assert prep["destinatario"] == "resp@essalud.gob.pe" and prep["copias"] == "otra.resp@essalud.gob.pe"


def test_copia_invalida_se_rechaza_antes_de_enviar():
    from src.agentes.acciones import revalidar_para_ejecutar
    base = {"destinatario": "a@essalud.gob.pe", "mensaje_personalizado": "Texto formal."}
    assert revalidar_para_ejecutar("RECORDATORIO_RED", {**base, "copias": "b@essalud.gob.pe, c@essalud.gob.pe"}) is None
    assert "copia" in revalidar_para_ejecutar("RECORDATORIO_RED", {**base, "copias": "no-es-correo"})


def test_correo_lleva_el_detalle_por_tipo(bd):
    from src.email_sender import get_email_sender
    asunto, html, plano = get_email_sender().componer_recordatorio(
        "Persona Responsable", "ALMENARA", 40, "2026-10-30 23:59:59", centros_pendientes=["100 C.M. DEMO ALM 1"], anio=2026,
        tipo="PREVENTIVO", mensaje_adicional="Quedaría pendiente el reporte de Emergencia.",
        pendientes_por_tipo=[{"centro": "100 C.M. DEMO ALM 1", "faltan": ["Emergencia"], "recibidos": ["Consulta Externa"]}])
    assert "Semana 40/2026" in asunto
    assert "Reportes pendientes por centro" in plano and "100 C.M. DEMO ALM 1: Emergencia" in plano
    assert "Reportes pendientes por centro" in html and "Emergencia" in html


def test_vista_previa_y_aprobacion_envian_con_copia(bd, correo):
    from src.agentes import acciones
    p = {"red": "ALMENARA", "semana": 40, "anio": 2026, "tono": "PREVENTIVO", "centros_pendientes": ["100 C.M. DEMO ALM 1"],
         "pendientes_por_tipo": [{"centro": "100 C.M. DEMO ALM 1", "faltan": ["Emergencia"], "recibidos": []}],
         "mensaje_personalizado": "Le agradeceremos el envío del reporte de Emergencia.",
         "destinatario": "otra.resp@essalud.gob.pe", "nombre_destinatario": "Resp Envio", "copias": "resp@essalud.gob.pe"}
    asunto, texto = acciones.vista_previa_recordatorio(p)
    assert "Con copia a: resp@essalud.gob.pe" in texto and "Emergencia" in texto
    ok, _ = acciones._ejec_recordatorio({**p, "_accion_id": 7}, SUPER)
    assert ok and correo[0]["cc"] == ["resp@essalud.gob.pe"] and correo[0]["pendientes_por_tipo"]
    assert any("ACC-7" in l["detalle"] for l in bd.tablas["logs"] if l["accion"] == "ENVIO_RECORDATORIO")


# ------------------------------------------------------------
# expedientes con patrones y reglas
# ------------------------------------------------------------

def test_expedientes_traen_pendientes_por_tipo_y_perfil(bd):
    from src.agentes.agente_operativo import expedientes_seguimiento, _publico
    exps = {e["red"]: e for e in expedientes_seguimiento()}
    assert "AREQUIPA" not in exps                      # completó la semana
    alm = exps["ALMENARA"]
    assert alm is next(iter(exps.values()))            # primero la que suele atrasarse
    assert alm["perfil_red"]["suele_atrasarse"] is True
    alm1 = next(x for x in alm["pendientes_por_tipo"] if x["centro"].endswith("ALM 1"))
    assert alm1["faltan"] == ["Emergencia"]
    assert alm["contexto_interno_no_va_en_el_correo"]["redes_completas"] == 1
    assert "_otras_redes" not in _publico(alm)          # no viaja al modelo


def test_reglas_preventivo_solo_para_redes_con_patron():
    from src.agentes.agente_operativo import decidir_por_reglas
    from src.agentes.skills import obtener
    sk = obtener("seguimiento_red")
    con = _exp_red(horas_al_corte=50, perfil_red={"suele_atrasarse": True})
    sin = _exp_red(horas_al_corte=50, perfil_red={"suele_atrasarse": False})
    assert decidir_por_reglas(sk, con)["decision"]["acciones"][0]["tipo"] == "RECORDATORIO_RED"
    assert decidir_por_reglas(sk, sin)["decision"]["acciones"][0]["tipo"] == "SIN_ACCION"
    assert decidir_por_reglas(sk, _exp_red(horas_al_corte=100, perfil_red={"suele_atrasarse": True}))["decision"]["acciones"][0]["tipo"] == "SIN_ACCION"


# ------------------------------------------------------------
# informe semanal
# ------------------------------------------------------------

def _respuesta(texto):
    from src.agentes.proveedores import Respuesta
    return Respuesta(texto, [], "gemini", "modelo-falso")


def test_datos_y_texto_del_sistema(bd):
    from src.agentes import informe_semanal as inf
    d = inf.datos_semana(2026, 40)
    assert d["redes_total"] == 3 and d["redes_completas"] == 1 and set(d["lista_redes_con_pendientes"]) == {"ALMENARA", "ANCASH"}
    assert d["redes_a_vigilar"][0]["red"] == "ALMENARA" and "ANCASH" in d["redes_que_mejoran"]
    t = inf.texto_sistema(d)
    for titulo in ("Situación de la semana", "Lo destacado", "Patrones a vigilar", "Recomendaciones"):
        assert titulo in t
    assert "1 de 3 redes completaron" in t and "Vienen mejorando: ANCASH" in t


def test_la_ia_que_inventa_cifras_se_descarta(bd, monkeypatch):
    from src.agentes import informe_semanal as inf, proveedores
    d = inf.datos_semana(2026, 40)
    monkeypatch.setattr(proveedores, "generar", lambda *a, **k: _respuesta(
        "Situación de la semana\n- 47 redes completaron.\nLo destacado\n- x\nPatrones a vigilar\n- x\nRecomendaciones\n- x"))
    texto, info = inf.redactar_con_ia(d)
    assert texto is None and "47" in info["motivo"]


def test_preparar_aprobar_y_salidas(bd, monkeypatch):
    from src.agentes import informe_semanal as inf, proveedores
    buena = ("Situación de la semana\n- 1 de 3 redes completaron la semana 40.\nLo destacado\n- ALMENARA y ANCASH tienen pendientes.\n"
             "Patrones a vigilar\n- ALMENARA tiende a enviar la Emergencia después del corte.\nRecomendaciones\n"
             "- Recordar antes del corte a ALMENARA y reconocer a ANCASH, que viene mejorando.")
    monkeypatch.setattr(proveedores, "generar", lambda *a, **k: _respuesta(buena))
    f = inf.preparar(2026, 40, "oiis.winepi")
    assert f["estado"] == "BORRADOR" and f["texto_ia"] == buena and f["origen_sugerido"] == "ia"
    assert any(r.get("referencia") == f"INF-{f['id']}" and r["evento"] == "BORRADOR" for r in bd.tablas["auditoria_agentes_ia"])
    ok, msg = inf.enviar(f, "jefatura@essalud.gob.pe", SUPER)
    assert not ok and "aprobado" in msg
    ok, _ = inf.aprobar(f["id"], buena, "ia", SUPER)
    assert ok
    fila = inf.listar()[0]
    assert fila["estado"] == "APROBADO" and fila["editado"] is False and "Validado por oiis.winepi" in inf.leyenda(fila)
    assert inf.a_word(fila)[:2] == b"PK"
    assert inf.metricas() == {"aprobados": 1, "con_texto_ia": 1, "con_texto_sistema": 0, "ia_sin_editar": 1}
    enviados = []
    import src.email_sender as es
    monkeypatch.setattr(es, "get_email_sender", lambda: type("S", (), {"enviar_informe_semanal": lambda self, *a: (enviados.append(a), (True, "ok"))[1]})())
    ok, _ = inf.enviar(fila, "jefatura@essalud.gob.pe", SUPER)
    assert ok and enviados[0][0] == "jefatura@essalud.gob.pe"


def test_informe_sin_ia_usa_el_texto_del_sistema(bd):
    from src.agentes import informe_semanal as inf
    f = inf.preparar(2026, 40, "oiis.winepi", usar_ia=False)
    assert f["texto_ia"] is None and f["origen_sugerido"] == "sistema" and "Recomendaciones" in f["texto_sistema"]
    ok, msg = inf.aprobar(f["id"], "corto", "sistema", SUPER)
    assert not ok


def test_correo_del_informe_se_arma(bd):
    from src.email_sender import get_email_sender
    import src.email_sender as es
    s = get_email_sender()
    capturado = {}
    s._enviar_correo = lambda dest, asunto, html, plano, **k: (capturado.update(dest=dest, asunto=asunto, html=html), (True, "ok"))[1]
    ok, _ = s.enviar_informe_semanal("j@essalud.gob.pe", 40, 2026, "Situación de la semana\n- 1 de 3 <b>redes</b>.", "Validado")
    assert ok and "Semana 40/2026" in capturado["asunto"] and "&lt;b&gt;" in capturado["html"]


# ------------------------------------------------------------
# asistente en todas las pantallas
# ------------------------------------------------------------

def test_herramientas_nuevas_de_solo_lectura(bd):
    from src.agentes import herramientas as h
    h._CACHE_HIST["h"] = None
    nombres = {x.nombre for x in h.registro_herramientas()}
    assert {"faltantes_por_tipo_de_red", "perfil_de_red", "panorama_semana", "redes_con_patron_de_atraso",
            "observaciones_pendientes_resumen", "propuestas_pendientes_del_agente", "actividad_ia_reciente"} <= nombres
    assert h.perfil_de_red("ALMENARA")["suele_atrasarse"] is True
    falt = h.faltantes_por_tipo_de_red("ALMENARA")["centros_con_pendientes"]
    assert any(x["faltan"] == ["Emergencia"] for x in falt)
    assert h.panorama_semana()["redes_completas"] == 1
    import json
    assert "@" not in json.dumps(h.propuestas_pendientes_del_agente()) + json.dumps(h.actividad_ia_reciente(7))


def test_el_asistente_recibe_la_pantalla_y_queda_registrado(bd, monkeypatch):
    from src.agentes import agente_investigador as inv
    vistos = {}

    def falso(sistema, mensajes, herramientas, **k):
        vistos["ultimo"] = mensajes[-1].contenido
        return _respuesta("A ALMENARA le falta Emergencia del C.M. DEMO ALM 1."), ["faltantes_por_tipo_de_red"]

    monkeypatch.setattr(inv, "ejecutar_con_herramientas", falso)
    r = inv.responder_pregunta("¿Qué le falta a la red ALMENARA?", [], pantalla="Notificaciones")
    assert not r["bloqueado"] and "[Pantalla actual: Notificaciones]" in vistos["ultimo"]
    reg = bd.tablas["auditoria_agentes_ia"][-1]
    assert reg["agente"] == "investigador" and reg["entrada"].startswith("[Notificaciones]")


@pytest.mark.parametrize("pregunta,ok", [
    ("¿Qué redes no mandaron emergencia?", True),
    ("¿Qué patrones tiene Almenara?", True),
    ("¿Cuántas observaciones hay sin revisar?", True),
    ("Dame el diagnóstico del paciente hospitalizado", False),
    ("¿Quién ganó el partido de ayer?", False),
])
def test_dominio_del_asistente(pregunta, ok):
    from src.agentes import guardrails
    assert guardrails.evaluar_entrada(pregunta).permitido is ok


def test_historial_de_ia_en_palabras_simples():
    from src.agentes import auditoria
    assert auditoria.funcion_de({"agente": "investigador"}) == "Quipu (asistente de consulta)"
    assert auditoria.funcion_de({"agente": "operativo", "referencia": "INF-3"}) == "Informe semanal"
    assert auditoria.funcion_de({"agente": "operativo", "referencia": "ACC-9"}) == "Agente Operativo"
    assert auditoria.EVENTO_SIMPLE["APROBACION"] == "Aprobado por una persona"


def test_historial_simulado_para_la_demo(bd):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sembrar", Path(__file__).resolve().parents[1] / "scripts" / "sembrar_historial_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bd.tablas["envios"] = []
    n = mod.sembrar(8)
    assert n > 0 and all(e["codigo_seguimiento"].startswith("DEMO-SIM-") and e["correo_usuario"].endswith("@example.org")
                         for e in bd.tablas["envios"])
    from src.agentes.patrones import Historial
    h = Historial(2026, 40, 8)
    perfiles = [h.perfil(r) for r in h.redes()]
    assert all(p["hay_datos_suficientes"] for p in perfiles)
    assert any(p["suele_atrasarse"] or p["tendencia"] in ("mejora", "empeora") for p in perfiles)
    assert mod.borrar() == n and not bd.tablas["envios"]


# ------------------------------------------------------------
# hallazgos de la revisión independiente
# ------------------------------------------------------------

def test_recordatorio_con_muchos_centros_no_pierde_ninguno():
    from src.agentes.acciones import procesar_propuesta
    centros = [f"CAP DEMO {i}" for i in range(35)]
    exp = _exp_red(faltantes=centros[30:],
                   pendientes_por_tipo=[{"centro": c, "recibidos": [], "faltan": ["Consulta Externa"], "sin_ningun_envio": True}
                                        for c in centros[:30]])
    acc, motivo = procesar_propuesta({"tipo": "RECORDATORIO_RED", "centros_pendientes": centros}, exp, ("RECORDATORIO_RED",),
                                     preparar=False)
    assert motivo is None
    assert [x["centro"] for x in acc["payload"]["pendientes_por_tipo"]] == centros


@pytest.mark.parametrize("texto", ["Su red es la única que aún no completa el envío.", "Todas las redes ya enviaron su reporte.",
                                   "Ya son varias semanas en que el envío llega después del corte."])
def test_tono_detecta_mas_comparaciones(texto):
    from src.agentes.acciones import problema_de_tono
    assert problema_de_tono(texto, "ALMENARA", [])


def test_informe_no_cuenta_todos_sus_reportes_como_tipo(bd):
    from src.agentes import informe_semanal as inf
    d = inf.datos_semana(2026, 40)
    assert "todos sus reportes" not in d["centros_con_pendientes_por_tipo"]


def test_informe_con_datos_personales_no_se_aprueba(bd):
    from src.agentes import informe_semanal as inf
    f = inf.preparar(2026, 40, "oiis.winepi", usar_ia=False)
    ok, msg = inf.aprobar(f["id"], f["texto_sistema"] + "\n- Contacto: jefe.red@essalud.gob.pe", "sistema", SUPER)
    assert not ok and "datos personales" in msg
    ok, _ = inf.aprobar(f["id"], f["texto_sistema"].replace("\n", "\n  "), "sistema", SUPER)
    assert ok and inf.listar()[0]["editado"] is False        # espacios distintos no cuentan como edición


def test_informe_del_viernes_una_sola_vez(bd):
    from datetime import datetime
    from src.agentes import informe_semanal as inf
    viernes = datetime(2026, 10, 23, 10)
    assert inf.procesar_programado(viernes, 2026, 40)
    assert inf.procesar_programado(viernes, 2026, 40) is None
    assert len(inf.listar()) == 1
    assert inf.procesar_programado(datetime(2026, 10, 22, 10), 2026, 41) is None     # jueves: nada


def test_recordatorio_a_todas_las_redes_cuenta_para_cada_una(bd):
    from src.agentes.acciones import detalle_log_recordatorio
    from src.agentes.patrones import Historial
    from datetime import datetime, timezone
    bd.tablas["logs"].append({"id": 99, "usuario": "oiis.winepi", "accion": "ENVIO_RECORDATORIO",
                              "detalle": detalle_log_recordatorio("x@essalud.gob.pe", "Todas las redes", 39, 2026, "PREVENTIVO"),
                              "fecha": datetime.now(timezone.utc).isoformat()})
    h = Historial(2026, 40, 8)
    assert h.recordatorios.get(("ALMENARA", 2026, 39)) and h.recordatorios.get(("ANCASH", 2026, 39))


# ---------------- SIREA 3.3: informe en PDF ----------------

def test_informe_pdf_borrador_y_aprobado():
    from src.agentes import informe_semanal as inf
    fila = {"id": 9, "anio": 2026, "semana": 40, "estado": "BORRADOR", "creado_por": "oiis.winepi",
            "creado_at": "2026-10-24T19:00:00+00:00",
            "datos": {"redes_completas": 2, "redes_total": 3, "redes_con_pendientes": 1, "redes_a_vigilar": [],
                      "recordatorios_enviados_en_la_semana": 0},
            "texto_sistema": "Situación de la semana\n- 2 de 3 redes completaron <script>x</script>.\n\nRecomendaciones\n- Nada."}
    pdf = inf.a_pdf(fila)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 5000
    PdfReader = pytest.importorskip("pypdf").PdfReader
    import io
    txt = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "Semana 40/2026" in txt and "BORRADOR" in txt and "<script>x</script>" in txt
    ok = dict(fila, estado="APROBADO", texto_final="Situación de la semana\n- Todo bien.", origen_final="sistema",
              aprobado_por="oiis.winepi", aprobado_at="2026-10-24T20:00:00+00:00")
    txt2 = PdfReader(io.BytesIO(inf.a_pdf(ok))).pages[0].extract_text()
    assert "Todo bien" in txt2 and "pendiente de validación" not in txt2 and "Aprobado" in txt2


# ---------------- SIREA 3.3: copias en Notificaciones y estadísticas por año ----------------

def test_copias_de_notificaciones_validan_y_no_repiten():
    from app_pages.admin_notificaciones import _copias, _copias_invalidas
    assert _copias("a@x.pe, B@x.pe; a@x.pe  c@x.pe", principal="c@x.pe") == ["a@x.pe", "b@x.pe"]
    assert _copias_invalidas("a@x.pe, no-es-correo") == ["no-es-correo"]


def test_estadisticas_de_la_semana_no_mezclan_anios(bd):
    from src.db_manager import get_db_manager
    for anio, red in ((2025, "ANCASH"), (2026, "ANCASH"), (2026, "AREQUIPA")):
        bd.tablas["envios"].append({"id": 9000 + len(bd.tablas["envios"]), "red": red, "semana": 33, "anio": anio, "estado": "APROBADO",
                                    "es_atrasado": False, "centros": [], "fecha_envio": "2026-08-10T10:00:00+00:00"})
    st = get_db_manager().obtener_estadisticas_semana(33, incluir_atrasados=False, anio=2025)
    assert st["anio"] == 2025 and st["envios_por_red"].get("ANCASH", 0) >= 1 and "AREQUIPA" not in st["envios_por_red"]


def test_responsables_traen_nombre_y_apellido_por_separado(bd):
    from src.agentes.acciones import responsables_de_red
    from datetime import datetime, timezone
    bd.tablas["envios"].append({"id": 9999, "red": "ICA", "semana": 40, "anio": 2026, "nombre_usuario": "Ana María",
                                "apellido_usuario": "Quispe Huamán", "correo_usuario": "ana@essalud.gob.pe",
                                "fecha_envio": datetime.now(timezone.utc).isoformat(), "centros": []})
    r = responsables_de_red("ICA")
    assert r and r[0]["nombres"] == "Ana María" and r[0]["apellidos"] == "Quispe Huamán"
