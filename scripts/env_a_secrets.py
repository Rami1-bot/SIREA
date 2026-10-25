"""
Convierte su .env (y credentials/service_account.json) en el texto que se
pega en Streamlit Community Cloud → App settings → Secrets.

Uso, desde la carpeta del proyecto y con el entorno virtual activado:

    python scripts/env_a_secrets.py > secretos_para_streamlit.txt

Abra secretos_para_streamlit.txt, copie TODO y péguelo en el cuadro
«Secrets» de Streamlit Cloud. Después BORRE ese archivo: contiene sus claves.

No envía nada a ningún lado: solo lee dos archivos locales e imprime.
"""

import json
import sys
from pathlib import Path

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent

# Variables que en la nube no aplican o se fijan aquí.
OMITIR = {"GOOGLE_CREDENTIALS_PATH", "DB_PATH", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
          "GOOGLE_AUTH_TYPE", "LOG_FORMAT"}
# En la nube el programador corre cada 15 min (GitHub Actions): el latido se considera vigente 40 min.
FIJAR = {"STORAGE_MODE": "drive", "TZ": "America/Lima", "ENVIRONMENT": "production", "PROGRAMADOR_LATIDO_MAX_MIN": "40"}


def main() -> int:
    env_path = RAIZ / ".env"
    if not env_path.exists():
        print("No se encontró el archivo .env en la carpeta del proyecto.", file=sys.stderr)
        return 1
    valores = {k: (v or "").strip().strip('"').strip("'") for k, v in dotenv_values(env_path).items()}
    valores.update(FIJAR)

    lineas = ["# Secretos de SIREA para Streamlit Community Cloud (generado por scripts/env_a_secrets.py)",
              "# NO subir este texto a GitHub.", ""]
    for k in sorted(valores):
        if k in OMITIR or not k or k.startswith("#") or valores[k] == "":
            continue   # los vacíos se omiten: equivalen a "no configurado" y evitan errores al convertir números
        lineas.append(f"{k} = {json.dumps(valores[k], ensure_ascii=False)}")

    cred = RAIZ / (valores.get("GOOGLE_CREDENTIALS_PATH") or "credentials/service_account.json")
    cred = cred if cred.exists() else RAIZ / "credentials" / "service_account.json"
    if cred.exists():
        datos = json.loads(cred.read_text(encoding="utf-8"))
        compacto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
        lineas += ["", "# Cuenta de servicio de Google Drive (contenido completo del JSON en una sola línea)",
                   f"GOOGLE_CREDENTIALS_JSON = {json.dumps(compacto, ensure_ascii=False)}"]
    else:
        print("Aviso: no se encontró credentials/service_account.json; Drive no funcionará en la nube.", file=sys.stderr)

    print("\n".join(lineas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
