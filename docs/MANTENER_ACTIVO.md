# Robot de actividad: que Supabase no se pause

## Por qué hace falta

En el **plan gratuito**, Supabase pausa el proyecto si pasa unos 7 días con poca actividad en la base de datos.
Cuando eso ocurre, SIREA no puede leer ni guardar nada y el registro se llena de `getaddrinfo failed`
(la dirección `xxxx.supabase.co` deja de existir mientras el proyecto está pausado).

El proceso programado de SIREA (`python -m src.programador`) ya genera actividad cada minuto; si está
corriendo en un servidor, el proyecto no se pausa. El robot es para cuando **solo se usa la web** y nadie
la abre por varios días (feriados, vacaciones, fin de año).

> **Recomendación:** para un sistema del que dependen las redes, lo más seguro es el **plan de pago** de
> Supabase: no se pausa nunca y tiene copias de seguridad diarias. El robot es una buena red de seguridad,
> pero Supabase no garantiza que unas pocas consultas basten siempre.

## Si ya está pausado

1. Entre a supabase.com con la cuenta dueña del proyecto.
2. Abra el proyecto (aparece con la etiqueta «Paused») y pulse **Resume project**.
3. Espere 5–15 minutos: aunque el panel diga «Healthy», la dirección puede tardar en volver.
   SIREA se recupera solo (la franja de aviso se revisa cada 30 segundos).

El robot **evita** la pausa; no puede reactivar un proyecto ya pausado.

## Paso 1 · Base de datos (una vez)

Ejecute `sql/56_latido_robot.sql` en Supabase → SQL Editor (ya viene incluido en
`sql/ACTUALIZAR_TODO_SIREA_3_5.sql`). Crea la función `sirea_latido()`, que solo devuelve la hora:
así el robot puede usar la **clave pública** y la clave secreta no sale de su PC.

## Paso 2 · Elija dónde corre el robot (puede usar los dos)

### A) En una PC con Windows (la más simple)

1. En `.streamlit/secrets.toml` ya están `SUPABASE_URL` y `SUPABASE_KEY`; si quiere, agregue
   `SIREA_LATIDO_KEY = "su clave pública"` para que el robot use esa.
2. Doble clic en `scripts\instalar_robot_windows.bat`. Hace una prueba y crea la tarea
   **«SIREA - mantener activo»**: todos los días a las 08:30 (y al encender, si la PC estaba apagada).
3. Cada revisión queda anotada en `storage\logs\mantener_activo.log`.

Límite: si esa PC pasa más de una semana apagada, el robot no corre. Por eso conviene también la opción B.

### B) En GitHub (no depende de ninguna PC)

1. Suba el proyecto a un repositorio **privado** de GitHub (el `.gitignore` ya excluye `secrets.toml`
   y la cuenta de servicio de Google).
2. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**:
   - `SUPABASE_URL` → `https://xxxx.supabase.co`
   - `SUPABASE_ANON_KEY` → la clave **pública** (anon / `sb_publishable_…`). No ponga la secreta.
   - `SIREA_APP_URL` → (opcional) la dirección pública de SIREA.
3. **Actions → Mantener Supabase activo → Run workflow** para probarlo. Luego corre solo cada 2 días.
4. Si una ejecución falla, GitHub envía un correo al dueño del repositorio.

Nota: en repositorios **públicos**, GitHub desactiva las tareas programadas tras 60 días sin cambios;
en privados no. Use uno privado.

## Comprobar a mano

```
python scripts/mantener_activo.py --detalle
```

| Resultado | Significa |
|---|---|
| `✓ Supabase despierto (hora del servidor …)` | Todo bien |
| `✗ No se encuentra «xxxx.supabase.co» …` | Proyecto pausado, sin internet o dirección mal escrita |
| `✗ Supabase respondió 401/403` | La clave no corresponde a ese proyecto |
| `✗ Supabase respondió 5xx` | El proyecto se está reactivando: reintente en unos minutos |
