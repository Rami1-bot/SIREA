"""SIREA 3.5: robot de actividad (scripts/mantener_activo.py)."""
import importlib.util
import io
import socket
import urllib.error
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "mantener_activo.py"
spec = importlib.util.spec_from_file_location("mantener_activo", RUTA)
ma = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ma)


@pytest.fixture(autouse=True)
def _sin_proxy(monkeypatch):
    for v in ("HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("ok",)])


def test_pausado_o_sin_dns(monkeypatch):
    def falla(*a, **k):
        raise socket.gaierror(11001, "getaddrinfo failed")
    monkeypatch.setattr(socket, "getaddrinfo", falla)
    codigo, msg = ma.latir_supabase("https://abc.supabase.co", "k")
    assert codigo == 2 and "PAUSADO" in msg and "Resume project" in msg


def test_latido_ok(monkeypatch):
    llamadas = []
    def pedir(url, metodo="GET", cab=None, cuerpo=None):
        llamadas.append((url, metodo, cab))
        return 200, '"2026-11-06T18:00:00+00:00"'
    monkeypatch.setattr(ma, "_pedir", pedir)
    codigo, msg = ma.latir_supabase("https://abc.supabase.co/", "clave-publica")
    assert codigo == 0 and "despierto" in msg
    url, metodo, cab = llamadas[0]
    assert url == "https://abc.supabase.co/rest/v1/rpc/sirea_latido" and metodo == "POST"
    assert cab["apikey"] == "clave-publica"


def test_sin_funcion_usa_lectura_minima(monkeypatch):
    respuestas = iter([(404, "no existe"), (401, "permiso")])
    monkeypatch.setattr(ma, "_pedir", lambda *a, **k: next(respuestas))
    codigo, msg = ma.latir_supabase("https://abc.supabase.co", "k")
    assert codigo == 0 and "56_latido_robot" in msg


def test_error_del_servidor(monkeypatch):
    monkeypatch.setattr(ma, "_pedir", lambda *a, **k: (503, "x"))
    codigo, msg = ma.latir_supabase("https://abc.supabase.co", "k")
    assert codigo == 1 and "reactivándose" in msg


def test_clave_rechazada(monkeypatch):
    monkeypatch.setattr(ma, "_pedir", lambda *a, **k: (401, "x"))
    assert ma.latir_supabase("https://abc.supabase.co", "k")[0] == 1


def test_config_desde_secrets_y_prioridad(tmp_path, monkeypatch):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text(
        'SUPABASE_URL = "https://desde-secrets.supabase.co"\nSUPABASE_KEY = "secreta"\nHTTPS_PROXY = "http://p:8080"\n',
        encoding="utf-8")
    (tmp_path / ".env").write_text("SIREA_LATIDO_KEY=publica-env\n", encoding="utf-8")
    for k in ma.CLAVES:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("SIREA_SECRETS_PATH", raising=False)
    cfg, origen = ma.cargar_config(tmp_path)
    assert cfg["SUPABASE_URL"] == "https://desde-secrets.supabase.co" and origen["SUPABASE_URL"] == "secrets.toml"
    assert cfg["SIREA_LATIDO_KEY"] == "publica-env" and origen["SIREA_LATIDO_KEY"] == ".env"
    import os
    assert os.environ.get("HTTPS_PROXY") == "http://p:8080"
    monkeypatch.delenv("HTTPS_PROXY", raising=False)


def test_main_sin_configuracion(monkeypatch, capsys):
    monkeypatch.setattr(ma, "cargar_config", lambda *a, **k: ({}, {}))
    assert ma.main([]) == 1
    assert "Falta SUPABASE_URL" in capsys.readouterr().out
