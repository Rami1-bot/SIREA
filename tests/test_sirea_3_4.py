# tests/test_sirea_3_4.py
"""
SIREA 3.4: lo que se incorporó de SIRE v7.3 – v8.1.

Revisión del ZIP por dentro (v7.5), contraseña amable para las redes (v7.3), cambios de
configuración con permiso y motivo (v7.5), Excel corporativo (v7.7) y la unión de las
variables de sesión de SIRE y SIREA.
"""
import io
import re
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _zip(archivos):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, datos in archivos:
            zf.writestr(nombre, datos)
    return b.getvalue()


def _exe_windows() -> bytes:
    cab = bytearray(b"MZ" + b"\x00" * 0x7E)
    cab[0x3C:0x40] = (0x80).to_bytes(4, "little")       # e_lfanew -> encabezado PE en 0x80
    return bytes(cab) + b"PE\x00\x00" + b"\x00" * 700


@pytest.fixture
def zp():
    from src.zip_processor import ZipProcessor
    return ZipProcessor()


# ---------------------------------------------------------------- ZIP revisado por dentro

def test_zip_normal_con_extension_de_centro_se_acepta(zp):
    r = zp.validar_zip(_zip([("pe4026jj.204", b"DATOS,1,2,3\n" * 100)]), "envio.zip")
    assert r["valido"] and not r["archivos_peligrosos"]
    assert len(r["archivos_detalle"]) == 1 and len(r["archivos_detalle"][0]["sha256"]) == 64


@pytest.mark.parametrize("nombre,datos,frase", [
    ("pe4026jj.204", _exe_windows(), "ejecutable"),
    ("pe4026jj.204", _zip([("a.txt", b"x" * 600)]), "comprimido"),
    ("reporte.exe.062", b"hola" * 200, "doble extensión"),
    ("pc4026jj.204", b"=cmd|' /C calc'!A0\n" + b"1,2\n" * 200, "fórmulas"),
    ("pe4026jj.204", b"\x00" * (60 * 1024 * 1024), "ZIP bomba"),
])
def test_zip_peligroso_se_bloquea_con_motivo(zp, nombre, datos, frase):
    r = zp.validar_zip(_zip([(nombre, datos)]), "envio.zip")
    assert not r["valido"] and r["archivos_peligrosos"]
    assert frase.lower() in r["mensaje"].lower()
    assert "OIIS" in r["mensaje"]                      # dice a quién acudir


def test_zip_con_ruta_que_sale_de_la_carpeta_se_bloquea(zp):
    r = zp.validar_zip(_zip([("../../windows/pe4026jj.204", b"1,2\n" * 200)]), "envio.zip")
    assert not r["valido"]


# ---------------------------------------------------------------- contraseñas

def test_perfil_red_es_mas_amable_pero_mantiene_lo_que_protege():
    from src.password_policy import PERFIL_RED, validar
    assert validar("tumbes2026x", contexto=["LAMBAYEQUE"], perfil=PERFIL_RED)[0]
    assert validar("costa-rosa-globo-cueva", contexto=["ICA"], perfil=PERFIL_RED)[0]     # frase sin número
    assert not validar("abc12", perfil=PERFIL_RED)[0]                                     # corta
    assert not validar("Essalud2026", perfil=PERFIL_RED)[0]                               # institución
    assert not validar("arequipa2026", contexto=["AREQUIPA"], perfil=PERFIL_RED)[0]       # nombre de la red
    assert not validar("tumbes2026x")[0]                                                  # el panel sigue estricto


def test_sugerencia_legible_siempre_cumple_el_perfil_red():
    from src.password_policy import PERFIL_RED, generar_legible, validar
    for _ in range(200):
        p = generar_legible(["PIURA"])
        assert validar(p, contexto=["PIURA"], perfil=PERFIL_RED)[0], p


def test_js_de_requisitos_en_vivo_no_tiene_texto_con_forma_de_etiqueta():
    js = (RAIZ / "components" / "password_vivo.js").read_text(encoding="utf-8")
    assert not re.search(r"<[A-Za-z/!]", js), "st.html descartaría el script"


# ---------------------------------------------------------------- configuración protegida

def test_cambio_de_configuracion_exige_permiso_y_motivo(monkeypatch):
    from src import cambios_configuracion as cc
    obj = cc.CambiosConfiguracion.__new__(cc.CambiosConfiguracion)
    monkeypatch.setattr(cc.CambiosConfiguracion, "puede", lambda self, actor: actor.get("usuario") == "oiis.winepi")

    class _Aud:
        def registrar(self, *a, **k):
            pass
    monkeypatch.setattr(cc.CambiosConfiguracion, "aud", property(lambda self: _Aud()))
    err, _ = obj._autorizar({"usuario": "otra.cuenta", "rol": "ADMIN"}, "X", "obj", "un motivo suficiente")
    assert err and "permiso" in err.lower()
    err, _ = obj._autorizar({"usuario": "oiis.winepi", "rol": "SUPER_ADMIN"}, "X", "obj", "corto")
    assert err and "motivo" in err.lower()
    err, m = obj._autorizar({"usuario": "oiis.winepi", "rol": "SUPER_ADMIN"}, "X", "obj", "  Se amplía   el plazo  ")
    assert err is None and m == "Se amplía el plazo"


def test_permiso_configuracion_existe_y_se_categoriza():
    from src.permisos import PERMISOS
    from src.auditoria import ETIQUETAS, CAMBIOS_DE_CONFIGURACION
    assert "CONFIGURACION" in PERMISOS
    assert all(a in ETIQUETAS for a in CAMBIOS_DE_CONFIGURACION)


# ---------------------------------------------------------------- Excel corporativo

def test_excel_corporativo_no_deja_formulas_y_conserva_numeros():
    import pandas as pd
    from openpyxl import load_workbook
    from src.excel_corporativo import generar_excel_df
    df = pd.DataFrame({"Red": ["=HYPERLINK(\"http://x\")", "ICA"], "Envíos": [3, 5], "% de cumplimiento": [50.0, 100.0]})
    wb = load_workbook(io.BytesIO(generar_excel_df(df, hoja="Prueba", titulo="Prueba")))
    ws = wb.active
    celdas = [c for fila in ws.iter_rows() for c in fila if c.value is not None]
    peligrosa = [c for c in celdas if isinstance(c.value, str) and c.value.startswith("=")]
    assert peligrosa and all(c.data_type == "s" for c in peligrosa)     # se guarda como TEXTO, no como fórmula
    assert any(isinstance(c.value, (int, float)) and c.value == 5 for c in celdas)


# ---------------------------------------------------------------- sesiones (SIRE + SIREA)

def test_inactividad_acepta_el_nombre_de_sire(monkeypatch):
    import importlib
    import src.config as config
    monkeypatch.delenv("SESION_INACTIVIDAD_MINUTOS", raising=False)
    monkeypatch.setenv("SESION_INACTIVIDAD_MIN", "45")
    try:
        importlib.reload(config)
        assert config.Config.SESION_INACTIVIDAD_MINUTOS == 45
        assert config.Config.SESION_INACTIVIDAD_MIN == 45
    finally:
        monkeypatch.delenv("SESION_INACTIVIDAD_MIN", raising=False)
        importlib.reload(config)
