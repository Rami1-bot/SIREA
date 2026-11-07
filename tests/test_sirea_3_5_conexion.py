"""SIREA 3.5: diagnóstico de conexión con Supabase y mensaje claro cuando no se puede leer la configuración."""
import socket

import pytest

from src import conexion_supabase as cs


@pytest.fixture(autouse=True)
def _limpiar(monkeypatch):
    cs._CACHE_DIAG.clear()
    cs._ULTIMO_LOG.clear()
    for v in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(v, raising=False)


def test_es_error_de_conexion():
    assert cs.es_error_de_conexion(OSError("[Errno 11001] getaddrinfo failed"))
    assert cs.es_error_de_conexion(Exception("ConnectError: [Errno -2] Name or service not known"))
    assert not cs.es_error_de_conexion(ValueError("columna inexistente"))


def test_diagnostico_url_vacia_invalida_y_ejemplo():
    assert "vacío" in cs.diagnostico_conexion("")
    assert "no es una dirección válida" in cs.diagnostico_conexion("supabase sin esquema")
    assert "valor de ejemplo" in cs.diagnostico_conexion("https://xxxx.supabase.co")
    assert cs.diagnostico_conexion("http://localhost") is None


def test_diagnostico_host_que_no_resuelve(monkeypatch):
    def falla(*a, **k):
        raise socket.gaierror(11001, "getaddrinfo failed")
    monkeypatch.setattr(socket, "getaddrinfo", falla)
    msg = cs.diagnostico_conexion("https://abcdefgh.supabase.co")
    assert "abcdefgh.supabase.co" in msg and "secrets.toml" in msg


def test_diagnostico_host_que_resuelve(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("ok",)])
    assert cs.diagnostico_conexion("https://abcdefgh.supabase.co") is None


def test_con_proxy_no_se_comprueba_dns(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.essalud:8080")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("x")))
    assert cs.diagnostico_conexion("https://abcdefgh.supabase.co") is None


def test_con_proxy_avisa_si_fallaron_consultas(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.essalud:8080")
    monkeypatch.setattr(cs, "diagnostico_conexion", cs.diagnostico_conexion)
    assert cs.diagnostico_conexion("https://abcdefgh.supabase.co") is None
    cs.registrar_error("Error al obtener configuración", OSError("[Errno 11001] getaddrinfo failed"))
    msg = cs.diagnostico_conexion("https://abcdefgh.supabase.co", cada_segundos=0)
    assert msg and "proxy" in msg and "pausado" in msg


def test_registrar_error_resume_los_de_conexion(monkeypatch, capsys):
    monkeypatch.setattr(cs, "diagnostico_conexion", lambda *a, **k: "Revise X.")
    err = OSError("[Errno 11001] getaddrinfo failed")
    for _ in range(50):
        cs.registrar_error(f"Error al obtener configuración: {err}", err)
    salida = capsys.readouterr().out.strip().splitlines()
    assert len(salida) == 1 and "Sin conexión" in salida[0]
    cs.registrar_error("Error al obtener algo: dato raro", ValueError("dato raro"))
    assert "dato raro" in capsys.readouterr().out


def test_sin_conexion_no_dice_anio_no_permitido(monkeypatch):
    from app_pages import usuario_logica as ul
    monkeypatch.setattr(ul, "obtener_anios_permitidos", lambda: [])
    monkeypatch.setattr(cs, "diagnostico_conexion", lambda *a, **k: "No se encuentra el servidor «x.supabase.co».")
    r = ul.verificar_estado_envio(40, 2026)
    assert "AÑO NO PERMITIDO" not in r["mensaje"]
    assert r["sin_conexion"] is True
    # mensaje amable y sin datos técnicos (esos solo los ve el administrador)
    assert "no está disponible" in r["mensaje"]
    assert "supabase" not in r["mensaje"].lower() and "secrets" not in r["mensaje"].lower()


def test_anio_fuera_de_lista_sigue_avisando(monkeypatch):
    from app_pages import usuario_logica as ul
    monkeypatch.setattr(ul, "obtener_anios_permitidos", lambda: [2025])
    r = ul.verificar_estado_envio(40, 2026)
    assert r["mensaje"].startswith("AÑO NO PERMITIDO: 2026. Años permitidos: 2025")
