# Subir SIREA a Streamlit Community Cloud

Streamlit Cloud toma el código desde **GitHub** y lo ejecuta en sus servidores. Las claves
(Supabase, correo, Gemini, Groq, Google Drive) **no van en GitHub**: se pegan en un cuadro
«Secrets» del panel de Streamlit.

## Paso 1 · Preparar los secretos (en su computadora)

Con el entorno virtual activado, dentro de la carpeta `sirea`:

```powershell
python scripts/env_a_secrets.py > secretos_para_streamlit.txt
```

Ese archivo contiene **todas sus claves** listas para pegar (incluida la cuenta de servicio de
Google, convertida a una sola línea). No lo suba a ningún lado; bórrelo al terminar el paso 4.

## Paso 2 · Subir el código a GitHub (repositorio **privado**)

1. En github.com → **New repository** → nombre `sirea` → **Private** → Create.
2. Con GitHub Desktop: *File → Add local repository* → elija la carpeta `sirea` → *Publish*.
   (o con git: `git init`, `git add .`, `git commit -m "SIREA v1.5"`, `git remote add origin …`, `git push -u origin main`).
3. **Antes del primer commit**, verifique en la lista de archivos que **NO** aparezcan:
   `.env`, `credentials/service_account.json`, `secretos_para_streamlit.txt`, `venv/`.
   El `.gitignore` ya los excluye; si alguno aparece, deténgase.

## Paso 3 · Crear la app en Streamlit Cloud

1. Entre a https://share.streamlit.io con su cuenta de GitHub.
2. **Create app → Deploy a public app from GitHub** (aunque el repo sea privado).
3. Repository: `su-usuario/sirea` · Branch: `main` · Main file path: `app.py`.
4. **Advanced settings**:
   - Python version: **3.12**.
   - Secrets: pegue **todo** el contenido de `secretos_para_streamlit.txt`.
5. **Deploy**. La primera vez tarda unos minutos (instala las dependencias).

## Paso 4 · Comprobar

- Abra la URL que le da Streamlit (`https://….streamlit.app`).
- Entre al panel → **Agente de IA → Estado → Probar los proveedores de IA** (ambos en verde).
- **Agente de IA → Evaluaciones** → correr cada skill → **Estado → Activar la IA**.
- Almacenamiento (Drive) → **Probar acceso** en las tres carpetas.
- Borre `secretos_para_streamlit.txt` de su computadora.

## Paso 5 (opcional) · Proceso programado (cierres, recordatorios, respaldos y corrida diaria del agente)

Streamlit Cloud solo ejecuta la web. El programador corre con **GitHub Actions**
(`.github/workflows/programador.yml`, cada 15 minutos):

1. En GitHub → su repositorio → **Settings → Secrets and variables → Actions → New repository secret**.
2. Cree, con el mismo valor que en Streamlit: `SUPABASE_URL`, `SUPABASE_KEY`, `GOOGLE_CREDENTIALS_JSON`,
   `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID`, `GOOGLE_DRIVE_FOLDER_BACKUPS_ID`,
   `EMAIL_REMITENTE`, `EMAIL_PASSWORD`, `EMAIL_NOMBRE_MOSTRAR`, `EMAIL_REPLY_TO`, `EMAIL_ADMINS`, `ADMIN_EMAIL`,
   `AUDITORIA_COPIA_EMAIL` (los que use). Para que el Agente Operativo corra solo cada día hábil, agregue
   también `GEMINI_API_KEY` (y si usa respaldo `GROQ_API_KEY`, `GROQ_MODEL`); opcional `AGENTE_HORA`.
   El agente solo **propone**: nada se envía hasta que alguien apruebe en la Bandeja.
3. **Actions → SIREA - proceso programado → Run workflow** para probarlo una vez. Debe terminar en verde.
4. En el panel (Respaldos / Configuración) el latido debe verse «activo».

Si no lo configura, la web funciona igual; solo el cierre de corte, los recordatorios y los respaldos
automáticos quedan manuales, y el agente corre solo cuando alguien pulsa «Correr ahora».

## Cosas que conviene saber

- **Se duerme**: en el plan gratuito, si nadie la usa por varios días la app «se duerme»; al abrirla
  hay un botón para despertarla (tarda ~1 minuto).
- **Cambiar una clave**: Streamlit Cloud → su app → ⋮ → **Settings → Secrets** → editar → Save
  (la app se reinicia sola).
- **Actualizar el código**: suba los cambios a GitHub; Streamlit redespliega solo.
- **Quién la ve**: por defecto cualquiera con el enlace ve la pantalla de inicio (el panel pide
  usuario y contraseña). En *Settings → Sharing* puede limitarla a correos invitados.
- **Datos**: los servidores de Streamlit están fuera del Perú. Para el curso (base de **demo**) está
  bien; para datos reales de EsSalud la opción correcta es un servidor institucional con Docker
  (ya incluido: `docker compose up -d --build`, con HTTPS opcional; ver `GUIA_DESPLIEGUE_SERVIDOR.md` y
  `GUIA_DESPLIEGUE_WINDOWS.md`). Es un buen punto para el informe (soberanía de datos).
