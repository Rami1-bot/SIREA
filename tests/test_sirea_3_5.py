# tests/test_sirea_3_5.py
"""
SIREA 3.5: secretos en .streamlit/secrets.toml, agente con responsables guardados,
herramientas y pendientes nuevos, Salud del sistema, clave de Supabase, avance nacional
con 3 consultas y su caché.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def bd(monkeypatch):
    from tests.fake_supabase import instalar
    import src.db_manager as dbm
    import src.data_loader as dl
    fake = instalar(monkeypatch)
    monkeypatch.setattr(dbm, "_db_manager", None)
    monkeypatch.setattr(dl, "_data_loader", None)
    import src.responsables_red as rr
    monkeypatch.setattr(rr, "_instancia", None, raising=False)
    return fake


# ---------------------------------------------------------------- secretos

def test_secrets_toml_carga_raiz_secciones_y_google(tmp_path, monkeypatch):
    from src import secretos
    (tmp_path / ".streamlit").mkdir()
    llave = "-----BEGIN PRIVATE KEY-----\\n" + "A" * 300 + "\\n-----END PRIVATE KEY-----\\n"
    (tmp_path / ".streamlit" / "secrets.toml").write_text(f'''
SIREA_PRUEBA_RAIZ = "uno"
SIREA_PRUEBA_NUM = 30
SIREA_PRUEBA_BOOL = true
SIREA_PRUEBA_VACIA = ""
[sireaprueba]
CLAVE = "dos"
[gcp_service_account]
type = "service_account"
client_email = "bot@proyecto.iam.gserviceaccount.com"
private_key = "{llave}"
''', encoding="utf-8")
    for k in ("SIREA_PRUEBA_RAIZ", "SIREA_PRUEBA_NUM", "SIREA_PRUEBA_BOOL", "SIREA_PRUEBA_VACIA", "SIREAPRUEBA_CLAVE",
              "GOOGLE_CREDENTIALS_JSON", "SIREA_SECRETS_PATH"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SIREA_PRUEBA_RAIZ", "del-sistema")            # el sistema gana
    ruta, n = secretos.cargar(tmp_path)
    assert ruta and n >= 4
    assert os.environ["SIREA_PRUEBA_RAIZ"] == "del-sistema"
    assert os.environ["SIREA_PRUEBA_NUM"] == "30" and os.environ["SIREA_PRUEBA_BOOL"] == "true"
    assert "SIREA_PRUEBA_VACIA" not in os.environ
    assert os.environ["SIREAPRUEBA_CLAVE"] == "dos"
    assert json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])["client_email"].endswith("gserviceaccount.com")
    for k in ("SIREA_PRUEBA_NUM", "SIREA_PRUEBA_BOOL", "SIREAPRUEBA_CLAVE", "GOOGLE_CREDENTIALS_JSON"):
        monkeypatch.delenv(k, raising=False)


def test_plantilla_secrets_es_toml_valido_y_no_activa_google_vacio():
    from src import secretos
    datos = secretos._leer_toml(RAIZ / ".streamlit" / "secrets.toml.example")
    plano = secretos.aplanar(datos)
    assert "SUPABASE_URL" in plano and "GEMINI_API_KEY" in plano
    assert "GOOGLE_CREDENTIALS_JSON" not in plano          # la sección de ejemplo no cuenta como credencial
    # cubre todas las variables del .env.example
    import re
    env = {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", (RAIZ / ".env.example").read_text(encoding="utf-8"), re.M)}
    assert env <= set(plano)


def test_secrets_toml_no_va_al_repositorio_ni_a_la_imagen():
    assert ".streamlit/secrets.toml" in (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert ".streamlit/secrets.toml" in (RAIZ / ".dockerignore").read_text(encoding="utf-8")


@pytest.mark.parametrize("clave,rol", [
    ("sb_secret_abc123", "secret"), ("sb_publishable_xyz", "publishable"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.firma", "service_role"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.firma", "anon"), ("cualquier-cosa", ""),
])
def test_rol_de_la_clave_de_supabase(clave, rol):
    import verificar_despliegue as vd
    assert vd.rol_clave_supabase(clave) == rol


# ---------------------------------------------------------------- agente y responsables guardados

def test_agente_suma_responsables_guardados_en_copia(bd):
    from src.agentes.acciones import responsables_de_red, _prep_recordatorio
    from tests.test_patrones import sembrar, _envio
    sembrar(bd)
    _envio(bd, "ALMENARA", 40, [("C.M. DEMO ALM 1", "c")], correo="envio@essalud.gob.pe")
    bd.tablas["responsables_red"] = [{"id": 1, "red": "ALMENARA", "nombre": "Rosa", "apellido": "Guardada",
                                      "correo": "rosa@essalud.gob.pe", "activo": True,
                                      "fecha_actualizacion": "2026-10-01T00:00:00+00:00"}]
    lista = responsables_de_red("ALMENARA")
    assert lista[0]["origen"] == "envio"
    assert any(r["correo"] == "rosa@essalud.gob.pe" and r["origen"] == "guardado" for r in lista)
    prep = _prep_recordatorio({"red": "ALMENARA"}, {})
    assert "rosa@essalud.gob.pe" in prep["copias"] and "guardado" in prep["destinatario_origen"]


def test_sin_envios_recientes_el_guardado_es_el_destinatario(bd):
    from src.agentes.acciones import _prep_recordatorio
    bd.tablas["envios"] = [e for e in bd.tablas.get("envios", []) if e.get("red") != "ICA"]
    bd.tablas["responsables_red"] = [{"id": 2, "red": "ICA", "nombre": "Luis", "apellido": "Pérez",
                                      "correo": "luis@essalud.gob.pe", "activo": True,
                                      "fecha_actualizacion": "2026-10-01T00:00:00+00:00"}]
    prep = _prep_recordatorio({"red": "ICA"}, {})
    assert prep["destinatario"] == "luis@essalud.gob.pe" and "guardado" in prep["destinatario_origen"]


# ---------------------------------------------------------------- herramientas y pendientes nuevos

def test_herramientas_nuevas_registradas_y_sin_datos_personales(bd):
    from src.agentes import herramientas as h
    nombres = {x.nombre for x in h.registro_herramientas()}
    assert {"zip_bloqueados_recientes", "cambios_de_configuracion_recientes", "solicitudes_de_permiso_pendientes",
            "cobertura_de_responsables", "estado_salud_sistema"} <= nombres
    bd.tablas["responsables_red"] = [{"id": 1, "red": "ANCASH", "nombre": "Ana", "apellido": "X",
                                      "correo": "ana@essalud.gob.pe", "activo": True, "fecha_actualizacion": "2026-10-01"}]
    cob = h.cobertura_de_responsables()
    assert cob["con_responsable_guardado"] == 1 and "ANCASH" not in cob["sin_responsable_guardado"]
    assert "@" not in json.dumps(cob)
    z = h.zip_bloqueados_recientes(7)
    assert "@" not in json.dumps(z)


def test_pendientes_incluye_lo_nuevo_y_respeta_el_rol(bd):
    from src.agentes import pendientes
    claves_super = {p.clave for p in pendientes.todos("SUPER_ADMIN")}
    claves_admin = {p.clave for p in pendientes.todos("ADMIN")}
    assert {"permisos", "seguridad", "configuracion", "salud"} <= claves_super
    assert "seguridad" in claves_admin and not ({"permisos", "configuracion", "salud"} & claves_admin)


def test_motivo_corto_de_zip_bloqueado():
    from src.agentes.herramientas import _motivo_corto
    assert _motivo_corto("programa ejecutable de Windows (.exe/.dll)") == "programa ejecutable"
    assert _motivo_corto("compresión desproporcionada (posible ZIP bomba)") == "posible ZIP bomba"


# ---------------------------------------------------------------- salud del sistema

def test_salud_del_sistema_sin_red_devuelve_registro_por_seccion(monkeypatch):
    import verificar_despliegue as vd
    res = vd.ejecutar(con_red=False)
    assert res["registro"] and set(res["resultados"]) == {"OK", "AVISO", "FALLA"}
    assert {i["seccion"] for i in res["registro"]} >= {"1. Variables de configuración", "2. Entorno y seguridad"}
    clave = os.environ.get("SUPABASE_KEY", "")
    assert all(clave not in (i["titulo"] + i["detalle"]) for i in res["registro"] if len(clave) >= 6)


def test_rls_se_informa_con_la_funcion_de_sql_55(bd):
    import verificar_despliegue as vd
    from src.db_manager import get_db_manager
    vd.registro.clear()
    vd.revisar_rls(get_db_manager())
    assert vd.registro[-1]["nivel"] == "OK" and "RLS" in vd.registro[-1]["titulo"]


# ---------------------------------------------------------------- portada

def test_avance_nacional_coincide_con_el_de_cada_red_y_usa_3_consultas(bd):
    from src.avance_nacional import calcular
    from app_pages.usuario_logica import calcular_avance_red
    from src.data_loader import get_data_loader
    calcular_avance_red.clear()
    esperado_env = esperado_tot = 0
    for red in get_data_loader().obtener_redes():
        av = calcular_avance_red(red, 2026, 40)
        esperado_env += len(av["enviados"])
        esperado_tot += av["total"]
    n = {"c": 0}
    original = bd.table

    def contar(nombre):
        n["c"] += 1
        return original(nombre)
    bd.table = contar
    d = calcular(2026, 40)
    bd.table = original
    assert d["enviados"] == esperado_env and d["total"] == esperado_tot
    assert n["c"] <= 4


def test_cache_de_la_portada_vence_y_es_por_semana(bd):
    from datetime import datetime, timedelta, timezone
    from src.avance_nacional import guardar_en_cache, leer_cache
    ahora = datetime.now(timezone.utc)
    datos = guardar_en_cache(2026, 40, ahora=ahora)
    assert leer_cache(2026, 40, ahora=ahora + timedelta(minutes=5)) == datos
    assert leer_cache(2026, 40, ahora=ahora + timedelta(minutes=11)) is None
    assert leer_cache(2026, 41, ahora=ahora) is None
