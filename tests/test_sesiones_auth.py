# tests/test_sesiones_auth.py
"""
Parche de sesiones traído de SIGRE e integrado en el AuthManager de SIRE:
bloqueo por usuario y por IP (persistente; aquí en memoria porque la BD
está simulada) y expiración por inactividad. Sin Supabase real.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")


class _DB:
    """Doble mínimo del DatabaseManager para el login."""
    def __init__(self):
        from src.security import hash_password
        self.admins = {"ana": {"usuario": "ana", "nombre": "Ana", "rol": "ADMIN", "email": "a@x.pe", "activo": True,
                               "password_hash": hash_password("Clave-Segura-2026!")},
                       "beto": {"usuario": "beto", "nombre": "Beto", "rol": "ADMIN", "email": "b@x.pe", "activo": True,
                                "password_hash": hash_password("Otra-Clave-2026!")}}
        self.logs = []

    def obtener_administrador(self, usuario):
        return dict(self.admins.get(usuario)) if usuario in self.admins else None

    def registrar_log(self, **k):
        self.logs.append(k)

    def actualizar_ultimo_login(self, usuario):
        return True

    def actualizar_administrador(self, *a, **k):
        return True


@pytest.fixture
def auth(monkeypatch):
    from src import auth as auth_mod
    from src import session_store
    # la BD de sesiones "no existe": el almacén cae a memoria de inmediato
    monkeypatch.setattr(session_store.AlmacenSesiones, "_tabla", lambda self, n: (_ for _ in ()).throw(RuntimeError("sin tabla")))
    monkeypatch.setattr(auth_mod, "get_db_manager", lambda: _DB())
    return auth_mod.AuthManager()


def test_login_correcto(auth):
    r = auth.login("ana", "Clave-Segura-2026!", ip="10.0.0.1")
    assert r["exito"] and r["token"]
    assert auth.verificar_sesion(r["token"])


def test_bloqueo_por_usuario_tras_5_fallos(auth, monkeypatch):
    from src.config import Config
    monkeypatch.setattr(Config, "LOGIN_MAX_INTENTOS_USUARIO", 5)
    for _ in range(5):
        r = auth.login("ana", "mala", ip="10.0.0.1")
        assert not r["exito"]
    r = auth.login("ana", "Clave-Segura-2026!", ip="10.0.0.1")   # clave correcta, pero bloqueado
    assert not r["exito"] and "Intente nuevamente en" in r["mensaje"]


def test_bloqueo_por_ip_aunque_cambie_de_usuario(auth, monkeypatch):
    from src import session_store
    session_store.LIMITE_IP["max_intentos"] = 4
    for u in ("ana", "beto", "ana", "beto"):
        auth.login(u, "mala", ip="9.9.9.9")
    r = auth.login("beto", "Otra-Clave-2026!", ip="9.9.9.9")
    assert not r["exito"] and "Intente nuevamente" in r["mensaje"]
    # desde otra IP el usuario correcto sí entra (el bloqueo era por IP)
    r2 = auth.login("beto", "Otra-Clave-2026!", ip="1.1.1.1")
    assert r2["exito"]


def test_expira_por_inactividad(auth, monkeypatch):
    from src.config import Config
    monkeypatch.setattr(Config, "SESION_INACTIVIDAD_MINUTOS", 30)
    r = auth.login("ana", "Clave-Segura-2026!", ip="10.0.0.1")
    tok = r["token"]
    auth._sesiones_activas[tok]["ultima_actividad"] = datetime.now() - timedelta(minutes=31)
    assert not auth.verificar_sesion(tok)


def test_expira_por_duracion_absoluta(auth, monkeypatch):
    from src.config import Config
    monkeypatch.setattr(Config, "SESION_DURACION_HORAS", 8)
    r = auth.login("ana", "Clave-Segura-2026!", ip="10.0.0.1")
    tok = r["token"]
    auth._sesiones_activas[tok]["inicio"] = datetime.now() - timedelta(hours=9)
    auth._sesiones_activas[tok]["ultima_actividad"] = datetime.now()
    assert not auth.verificar_sesion(tok)
