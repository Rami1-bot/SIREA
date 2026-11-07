# Configuración con `.streamlit/secrets.toml` (SIREA 3.5)

Desde SIREA 3.5 la configuración (claves de Supabase, correo, Drive, IA…) vive en **un solo archivo**:
`.streamlit/secrets.toml`. El `.env` sigue funcionando como respaldo, pero ya no hace falta.

> `secrets.toml` reemplaza al **.env**, no al entorno de Python. Las librerías (Streamlit, Supabase…)
> se instalan igual: Streamlit Cloud y Docker lo hacen solos; en una PC con Windows, con
> `pip install -r requirements.txt` (con o sin entorno virtual).

## 1. Crear el archivo

**Opción A: desde cero.** Copie la plantilla y complétela:

```powershell
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
notepad .streamlit\secrets.toml
```

Reemplace los valores marcados con `<<< COMPLETAR`. El texto va siempre entre comillas dobles.

**Opción B: si ya tiene un `.env`.** Conviértalo automáticamente:

```powershell
python scripts/env_a_secrets.py --archivo
```

Crea `.streamlit/secrets.toml` con todas sus variables y la cuenta de servicio de Google.

## 2. La cuenta de servicio de Google

Puede hacerlo de dos maneras (use una sola):

- **Dentro de `secrets.toml`**: copie cada valor de `service_account.json` en la sección
  `[gcp_service_account]` del final. La `private_key` va completa en una línea, con los `\n` tal cual.
- **Como archivo**: deje `credentials/service_account.json` y borre la sección `[gcp_service_account]`.

Una sección `[gcp_service_account]` con los valores de ejemplo se ignora: no reemplaza a su archivo.

## 3. Dónde se usa

| Dónde | Qué hacer |
|---|---|
| PC o servidor (`python -m streamlit run app.py`) | Nada más: el archivo se lee al arrancar. |
| Proceso programado (`python -m src.programador`) | También lo lee. |
| Docker (`docker compose up -d --build`) | La carpeta `.streamlit/` se monta en el contenedor; el `.env` pasa a ser opcional. |
| Streamlit Community Cloud | App settings → **Secrets**: pegue todo el contenido del archivo. |
| GitHub Actions (programador en la nube) | Cree cada clave como *repository secret* (ver `DESPLIEGUE_STREAMLIT_CLOUD.md`). |

**Prioridad:** variables del sistema → `secrets.toml` → `.env`. Si un valor está en dos lugares, gana el primero.

## 4. Comprobar

- Panel → **Salud del sistema** → «Revisar ahora» (o `python verificar_despliegue.py`). La primera fila dice
  de dónde salen los secretos y avisa si todavía queda un `.env`.
- Cuando todo funcione, puede borrar el `.env`.

## 5. Seguridad

- `.gitignore` y `.dockerignore` excluyen `.streamlit/secrets.toml`: no se sube a GitHub ni entra en la imagen.
- `SUPABASE_KEY` debe ser la **clave de servidor** (`service_role` o `sb_secret_…`). «Salud del sistema»
  marca como falla la clave pública: con la seguridad por filas de `sql/55`, la pública no ve datos.
- Si el archivo se compartió por error, cambie las claves (Supabase, contraseña de aplicación del correo,
  llave de la cuenta de servicio de Google, claves de Gemini y Groq).

## 6. «getaddrinfo failed» / «Sin conexión con la base de datos»

La PC no logra ubicar el servidor de Supabase. SIREA lo muestra en una franja roja arriba de la pantalla
(antes salía como «AÑO NO PERMITIDO: 2026. Años permitidos: » porque la lista llegaba vacía). Revise, en orden:

1. **Internet:** abra `https://SU-PROYECTO.supabase.co` en el navegador de esa misma PC.
2. **`SUPABASE_URL`** en `.streamlit/secrets.toml`: debe ser exactamente `https://xxxx.supabase.co`
   (sin espacios, sin `/rest/v1`, sin comillas de más). Si además existe una variable de Windows
   `SUPABASE_URL`, esa gana (ver «Prioridad»): bórrela o corríjala.
3. **Red de EsSalud:** si la salida a internet pasa por un proxy, defina `HTTPS_PROXY`
   (por ejemplo `http://proxy.essalud.gob.pe:8080`) en las variables de Windows o en `secrets.toml`,
   o conéctese a la VPN.
4. Compruebe con `python verificar_despliegue.py`.
