# tests/test_password_js_paridad.py
"""
SIREA 3.5 · La lista de requisitos que se marca en el navegador mientras la red escribe
(components/password_vivo.js) debe decir EXACTAMENTE lo mismo que el servidor
(src/password_policy.py, perfil «red»). Si alguien cambia una regla en un lado y no en el
otro, esta prueba falla.

Se ejecuta el JavaScript real con Node (se omite si Node no está instalado) sobre más de
3000 contraseñas: aleatorias, comunes, con el nombre de la red, con «EsSalud», con
secuencias y repeticiones, con tildes y ñ, frases largas y casos límite de longitud.
"""
import json
import random
import shutil
import string
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

_STUB = r"""
const fs = require('fs');
const datos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
global.window = {};
global.document = { addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
                    activeElement: null };
global.setTimeout = (f) => 0;
eval(fs.readFileSync(process.argv[3], 'utf8'));
const api = window.__sirePwVivo;
const out = datos.claves.map(p => { const r = api.evaluar(p, datos.cfg); return [r, api.nivel(p, r, datos.cfg)]; });
process.stdout.write(JSON.stringify(out));
"""


def _muestras(red: str):
    rnd = random.Random(2026)
    from src.password_policy import generar_legible
    base = ["", "a", "abc12", "abcdefg1", "abcdefgh", "12345678", "tumbes2026x", "Essalud2026", "essalud-2026",
            "0iis-ica-2026", "contraseña1", "ñandú-río-12", "password1", "qwerty123", "aaaa1234b", "abab1212ab",
            "costa-rosa-globo-cueva", "1234abcd", "dcba9876x", red.lower() + "2026", red.title() + "-segura-9",
            "x" * 64, "x" * 65, "ñ" * 36 + "1", "ñ" * 37, "Lima123!", "pass word 2026", "    ", "Ab1" * 4]
    alfabeto = string.ascii_letters + string.digits + "áéíóúñÑ-_.!@#$ "
    for _ in range(2200):
        n = rnd.randint(1, 26)
        base.append("".join(rnd.choice(alfabeto) for _ in range(n)))
    palabras = ["essalud", "oiis", "red", red.lower(), "hospital", "reporte", "semana", "costa", "sierra", "selva",
                "123", "2026", "abcd", "qwer", "aaaa", "zzzz", "p@ss", "l1ma", "s3guro"]
    for _ in range(1400):
        base.append(rnd.choice(["", "-", "_", "."]).join(rnd.choice(palabras) for _ in range(rnd.randint(1, 4))))
    base += [generar_legible([red]) for _ in range(100)]
    return list(dict.fromkeys(base))


@pytest.mark.skipif(not NODE, reason="Node no está instalado")
def test_requisitos_del_navegador_coinciden_con_el_servidor(tmp_path):
    from src.password_policy import PERFIL_RED, datos_para_navegador, evaluar, fuerza
    red = "AREQUIPA"
    contexto = [red]
    muestras = _muestras(red)
    assert len(muestras) > 3000
    cfg = datos_para_navegador(contexto)
    entrada = tmp_path / "entrada.json"
    entrada.write_text(json.dumps({"claves": muestras, "cfg": cfg}, ensure_ascii=False), encoding="utf-8")
    script = tmp_path / "correr.js"
    script.write_text(_STUB, encoding="utf-8")
    salida = subprocess.run([NODE, str(script), str(entrada), str(RAIZ / "components" / "password_vivo.js")],
                            capture_output=True, text=True, timeout=120, check=True)
    js = json.loads(salida.stdout)

    diferencias = []
    for p, (r_js, nivel_js) in zip(muestras, js):
        r_py = {r.clave: r.cumple for r in evaluar(p, contexto, None, PERFIL_RED)}
        if r_py != {k: bool(v) for k, v in r_js.items()}:
            diferencias.append((p, r_py, r_js))
        elif fuerza(p, contexto, None, PERFIL_RED)[0] != nivel_js:
            diferencias.append((p, "fuerza", fuerza(p, contexto, None, PERFIL_RED)[0], nivel_js))
    assert not diferencias, f"{len(diferencias)} diferencias, por ejemplo: {diferencias[:3]}"
