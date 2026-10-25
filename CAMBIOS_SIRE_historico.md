# SIRE · Versión mejorada

## Qué cambió
- **Nuevo estilo en toda la interfaz**: inicio, envío de reporte, acuses en pantalla (azul: a tiempo; rojo: tardío; ámbar: con observaciones), acceso de redes, acceso del administrador y panel.
- **Logo de EsSalud sin fondo**, en azul sobre fondo claro y en blanco sobre fondo azul (`assets/essalud-azul.png`, `assets/essalud-blanco.png`).
- **Contraseñas seguras** (`src/password_policy.py`): mínimo 10 caracteres, mayúsculas y minúsculas, número y símbolo; se rechazan las muy usadas, las que contienen el usuario, la red, el nombre o palabras como «EsSalud» u «OIIS», y las secuencias o repeticiones. Cada requisito incumplido muestra el porqué, y hay un desplegable «¿Por qué pedimos esto?». Se aplica en: cambio obligatorio de la red, alta/edición de administradores, credenciales de red (individual y carga masiva) y `resetear_password_admin.py`.
- **Sugerencias de usuario con un clic** al crear administradores (usuario vacío, ya existente o demasiado común).
- **Correos formales**: «Estimado/a …:», «Por medio del presente…», cierre «Atentamente» con la firma de la OIIS y, si se configura `CONTACTO_EMAIL`, la línea de consultas. Asuntos con «EsSalud» y tildes correctas.
- **Revisión de ortografía y trato de usted** en mensajes, historial y scripts.

## Novedades de la versión 4 (entrega 1)

### 1. La semana activa ahora sí se guarda
- Causa: el guardado hacía un `UPDATE` que no hace nada si la fila `semana_activa` no existe (o la base no la acepta) y la pantalla igual decía «guardado».
- Ahora `DatabaseManager.guardar_configuracion()` actualiza o **crea** la fila y **vuelve a leerla** para comprobar. Si la base no la guarda, la pantalla muestra el motivo en rojo (por ejemplo, permisos de la clave de Supabase) en lugar de fingir éxito.
- La semana activa es un valor **manual** definido por los administradores; el sistema no la calcula. El cambio queda en el historial («CAMBIAR_CONFIGURACION», con el valor anterior y el nuevo).
- La copia en `.env` pasó a ser solo respaldo (en Docker puede ser de solo lectura y ya no impide guardar).

### 2. Calendario en Configuración
- **Fecha de corte**: calendario (domingo como primer día) y lista de horas; «23:59:59» es la primera opción.
- Bajo la semana activa se muestra su rango real (domingo a sábado) según el año activo, p. ej. «Semana 41 de 2026: 11/10 – 17/10/2026».
- **Años epidemiológicos** (agregar y editar): fechas de inicio y fin con calendario. Para un año nuevo se proponen solas con la regla estándar (la semana 1 es la que contiene el 4 de enero): 2026 empieza el 04/01/2026; 2027, el 03/01/2027. El número de semanas (52 o 53) también se propone; todo se puede corregir. Lógica pura y probada en `src/calendario_epi.py`.
- Si el inicio elegido no es domingo, se advierte.
- Nota: la fecha de fin ahora es el **sábado** que cierra la última semana (antes era el domingo con que empezaba la última).
- Los nombres de los meses del calendario salen en inglés (limitación de Streamlit).

### 3. Eliminar duplicados de Drive
- Causa probable: con el rol «Gestor de contenido» Drive permite enviar a la **papelera**, pero no borrar definitivamente; el borrado definitivo fallaba, el error se descartaba y la pantalla avisaba éxito de todos modos.
- Ahora se intenta primero la **papelera** (recuperable 30 días desde la papelera de Drive) y, si no se puede, el borrado definitivo. Un archivo que ya no existe cuenta como eliminado.
- El resultado es **real**: si un archivo no se pudo quitar de Drive, el registro del duplicado **se conserva** y se muestra el motivo para poder reintentar. En modo local solo se borra dentro de `storage/`.
- Los archivos eliminados quedan en la **papelera** de la cuenta de servicio; en una unidad compartida, se pueden ver desde la papelera de esa unidad.

### 4. Cambiar el nombre de usuario (Cuentas del panel)
- Nuevo bloque «Cambiar el nombre de usuario» (solo `oiis.winepi`).
- El usuario de `oiis.winepi` **nunca** cambia y **nadie** puede tomar ese nombre (tampoco con otras mayúsculas).
- Reglas: 3 a 40 caracteres (letras, números, punto, guion, guion bajo), sin repetir uno existente (sin distinguir mayúsculas) ni genérico.
- Al cambiarlo se cierran las sesiones de esa cuenta (debe ingresar con el usuario nuevo) y queda en el historial («CAMBIAR_USUARIO»). El historial anterior conserva el usuario con el que se hizo cada acción.

### Pruebas
`test_flujo.py` (código real sobre Supabase simulado): 86 verificaciones, 0 fallas, incluidas las de usuario, configuración, Drive y calendario.

### Próxima entrega (v4, parte 2)
Proceso programado en un contenedor aparte (zona horaria America/Lima): propuesta automática de semana y corte al cerrar el corte, recordatorios y validación entre administradores, «ya validado por…», Excel «Resumen de cumplimiento por red», envío a la entidad externa tras la validación y respaldo cada dos cortes a la carpeta `BACKUPS` de Drive.

## Novedades de la versión 3

### 1. Cuentas del panel (solo `oiis.winepi`)
Nueva sección **Cuentas del panel** (menú «Solo SUPER_ADMIN»), visible y utilizable únicamente por el SUPER_ADMIN principal (usuario `oiis.winepi`, configurable con `SUPERADMIN_PRINCIPAL`). Permite:
- modificar nombre, correo, rol y estado de cualquier administrador o SUPER_ADMIN;
- restablecer la contraseña de otra cuenta (cumple la política de contraseñas fuertes, cierra las sesiones de esa cuenta y queda en el historial);
- cambiar su propia contraseña (pide la actual).
La cuenta principal no puede quitarse el rol ni desactivarse. La restricción se valida también en el servidor (`AuthManager.es_superadmin_principal`), no solo en el menú. Crear y eliminar administradores sigue en «Administradores».

### 2. Envíos duplicados: acuse naranja y carpeta aparte
- Si una red confirma que desea reenviar un centro ya enviado en la semana, el archivo se guarda en **otra carpeta de Drive** (`GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID`; si se deja vacía se crea una subcarpeta `DUPLICADOS` dentro de la carpeta principal) y **no reemplaza** al original.
- Acuse **naranja** en pantalla y por correo, y alerta naranja a los administradores.
- «Control de duplicados» lista los duplicados recibidos y permite eliminarlos (con su archivo de Drive, si se desea). Se registran como estado «Observado» con la observación «ENVÍO DUPLICADO», sin cambiar el esquema de la base.
- Compartir la carpeta de duplicados con la cuenta de servicio como **Editor**.

### 3. Usuarios frecuentes que sí funcionan
Después de un envío correcto, el navegador recuerda nombres, apellidos y correo (hasta 6 personas). La próxima vez aparece «Usuarios frecuentes en este equipo»: un clic completa los tres campos. Se guardan **solo en ese navegador** (no en el servidor) y se pueden quitar uno a uno o «Olvidar todos». Componente: `components/frecuentes`.

### 4. Doble verificación del correo
El correo se escribe dos veces y deben coincidir. Se espera `nombre@essalud.gob.pe`; si el dominio parece un error de tipeo («esalud.gob.pe», «gmial.com», «essalud.pe»…) se propone la corrección con un clic; para cualquier otro dominio (por ejemplo un gmail excepcional) se exige marcar una confirmación expresa. Antes de enviar se muestra a qué correo llegará el acuse. Lógica en `src/validacion_correo.py`.

### 5. Cambio de contraseña de las redes con aprobación
- El **primer** cambio (de la contraseña genérica a una propia) sigue siendo obligatorio y libre.
- Los **cambios posteriores** requieren aprobar una solicitud: en «Mi progreso» la red completa un mensaje predefinido (nombre, correo con doble verificación y texto editable) y lo envía.
- Recibe un **acuse por correo**; los administradores reciben una alerta por correo (`EMAIL_ADMINS`) y una **notificación dentro del panel** (aviso en el panel de control y contador en el menú «Solicitudes de contraseña»).
- En esa pantalla el SUPER_ADMIN lee el sustento, **intercambia mensajes con la red** (ambos lados ven la conversación), y **aprueba o rechaza**. Al aprobar, el cambio de contraseña se habilita automáticamente en la pantalla de la red durante `HORAS_VALIDEZ_CAMBIO_PASSWORD` horas (24 por defecto) y se cierra al usarse. La regla se exige también en el servidor.
- Una red solo puede tener una solicitud abierta; puede cancelarla. Si la contraseña se olvidó, sigue valiendo «Credenciales de red».
- **Requiere ejecutar `sql/09_solicitudes_cambio_password.sql`** en el SQL Editor de Supabase. Mientras no exista, las redes no podrán cambiar su contraseña por su cuenta (queda bloqueado por seguridad) y la pantalla de administración lo avisa.

### 6. Envíos tardíos en «Mi progreso»
Nueva sección **Envíos tardíos** con indicadores de la semana actual y del periodo elegido, tabla por semana (recibidos, dentro del plazo, tardíos y centros con envío tardío) y gráfico de barras. Usa el mismo rango de semanas que «Evolución semanal». Los duplicados no se cuentan.

## Variables nuevas
- `CONTACTO_EMAIL` (opcional): correo de consultas que se muestra en el inicio y en los correos.
- `GOOGLE_DRIVE_FOLDER_DUPLICADOS_ID` (opcional): carpeta de Drive para los duplicados. Escriba solo el ID, sin comillas ni espacios.
- `SUPERADMIN_PRINCIPAL` (por defecto `oiis.winepi`): único usuario que usa «Cuentas del panel».
- `HORAS_VALIDEZ_CAMBIO_PASSWORD` (por defecto `24`): horas de vigencia de una solicitud aprobada.

## Orden para poner en marcha esta versión
1. Ejecutar `sql/09_solicitudes_cambio_password.sql` en Supabase.
2. Crear la carpeta de duplicados en Drive, compartirla como Editor con la cuenta de servicio y copiar su ID en `.env`.
3. Confirmar que el usuario `oiis.winepi` existe con rol SUPER_ADMIN.
4. Reiniciar la aplicación.

# Novedades de la versión 5

Esta entrega incluye todo lo de la versión 4 y suma lo siguiente.

## 1. Carpetas de Drive (arreglo)
- **«No se pudo activar la carpeta»**: la causa era que la base de datos (Supabase) rechaza un cambio masivo sin condición. Ahora solo se desactiva la carpeta que está activa y, después de activar, se **comprueba** que quedó guardado; si algo falla se restaura la anterior y se muestra el motivo.
- El panel **Gestión de Drive** muestra ahora «Carpetas configuradas en el servidor»: principal, **duplicados** y **respaldos (BACKUPS)**, con su estado, el ID abreviado y un botón **Probar acceso**. Estas carpetas vienen del `.env`; por eso BACKUPS **no aparece** en «Carpetas registradas» (esa lista es solo para carpetas de envíos).
- Las carpetas de duplicados y de respaldos **no se pueden activar** como carpeta de envíos.

## 2. Control de duplicados por semana
Selector de semana: **semana activa** (por defecto) u **otra semana** del año. Todas las acciones (revisar, conservar, eliminar de Drive) se aplican a la semana elegida.

## 3. Cierre de corte, validación y recordatorios (proceso programado)
- Al pasar la fecha de corte el sistema **propone** la nueva semana y el nuevo corte (avisa si cae en feriado) y la aplica **de forma provisional**.
- Avisa por correo a los administradores con el resumen de cumplimiento (borrador) adjunto.
- **3 recordatorios** el día hábil siguiente: **08:00, 12:00 y 16:00** (hora de Lima; configurable con `RECORDATORIOS_CIERRE_HORAS`). Se detienen apenas **una** persona valida; las demás reciben un único aviso de «ya validado».
- Una persona valida o corrige en **Configuración → Validar la semana propuesta**; también aparece como aviso en el Panel de control.

## 4. Informe por semana (nuevo panel)
Elija una semana (actual u otra) y vea el cumplimiento por red, el Excel descargable, la **validación del resumen** y el **envío a la entidad externa**: la entidad se registra una vez (nombre, apellidos, correo) y el envío solo se habilita tras validar. También hay envío manual con mensaje propio y reintento si un correo falló.

## 5. Respaldos (nuevo panel)
- Automático **cada 2 cortes**, en el momento del corte, a la carpeta **BACKUPS** de Drive (subcarpeta con fecha y hora exactas), con reintentos y acuse por correo. No incluye contraseñas.
- Respaldo manual e historial en la sección **Respaldos**. El estado del programador (latido) se ve en el panel.

## Puesta en marcha de la versión 5
1. Ejecutar `sql/10_programador_cierres_respaldos.sql` en Supabase (es seguro repetirlo).
2. Crear la carpeta BACKUPS en Drive, compartirla con la cuenta de servicio como **Gestor de contenido** (o Editor) y poner el ID en `.env`: `GOOGLE_DRIVE_FOLDER_BACKUPS_ID=ID_SIN_COMILLAS` (también vale `BACKUPS_ID`). Use siempre un ID real o deje la línea vacía; un texto de ejemplo como `el_id_de_la_carpeta` hace que falle el acceso.
3. Con Docker: `docker compose up -d --build` levanta **dos contenedores** (`sire-app` y `sire-programador`). El programador usa el mismo `.env` y la carpeta `credentials/`. Zona horaria: `America/Lima`.
4. Sin Docker (Windows, pruebas): active el entorno virtual (`.\venv\Scripts\activate`), ejecute `pip install -r requirements.txt` y luego `python -m streamlit run app.py`. Si aparece `No module named 'supabase'` es que se usó el Python global y no el del entorno virtual. El proceso programado se prueba aparte con `python -m src.programador`.
5. Reiniciar la aplicación.

# Novedades de la versión 6

Esta entrega incluye todo lo de la versión 5 y suma descarga masiva, limpieza del repositorio con trazabilidad y un control de la actividad de administradores.

## 1. Permisos de operación (solo oiis.winepi)
- Nueva sección **Trazabilidad → Permisos de operación**. Solo el SUPER_ADMIN principal (`oiis.winepi`) asigna o revoca permisos; ni siquiera otro SUPER_ADMIN los tiene por defecto.
- Permisos: **Descarga masiva**, **Retiro del repositorio** (también habilita eliminar duplicados), **Respaldo manual** y **Ver auditoría**.
- Cada permiso es por persona, con alcance opcional por **redes** y **vencimiento** (se apaga solo). Se avisa por correo al asignar y al revocar.

## 2. Descarga y limpieza (nueva sección)
- Selectores de **año, semana y redes** (con la opción **Todas**; opcionalmente incluye duplicados).
- **Descargar**: un solo ZIP con una carpeta por red y un `MANIFIESTO.csv` con la huella SHA-256 de cada archivo. Si supera `DESCARGA_MASIVA_MAX_MB` se parte en varios ZIP. Al descargar se envía un **acuse** a la persona y al principal, y queda en el registro.
- **Dónde se guarda**: una página web no puede escribir en una carpeta cualquiera del equipo. Para elegir la carpeta cada vez, active en Chrome/Edge *Configuración → Descargas → «Preguntar dónde guardar cada archivo»*.
- **Retirar del repositorio**: envía los archivos a la **papelera de Drive** (recuperable). Exige un motivo (categoría + explicación) y escribir la confirmación `RETIRAR S{semana}-{año}`. Si se retira sin descarga previa se marca como señal. Los registros de envío en la base de datos **no se borran**.
- Si quien pide el retiro **no** es oiis.winepi, la solicitud queda **pendiente** y él la aprueba o rechaza (con motivo); al aprobar se ejecuta. oiis.winepi ejecuta directamente. Solo él puede hacer el **borrado definitivo** (no pasa por la papelera).
- Cada retiro genera un **Excel profesional** (resumen + detalle por archivo) y un **acuse por correo** a quien lo pidió y al principal; también se ve en la interfaz. Los retiros parciales o con error se pueden reintentar.

## 3. Control de actividad
- Qué hizo cada administrador y SUPER_ADMIN **(incluido oiis.winepi)**: descargas, retiros, duplicados, respaldos, permisos y más, con fecha, hora, IP y resultado.
- **Señales para revisar**: retiro sin descarga previa, retiro de muchos archivos, borrado definitivo, acciones fuera del horario laboral.
- Filtros por periodo, persona, tipo de acción y resultado; **Excel de auditoría** de 5 hojas; botón **Verificar integridad**.
- Lo ve oiis.winepi y quien tenga el permiso «Ver auditoría». Duplicados y respaldos (manuales y automáticos) quedan registrados igual.

## 4. Seguridad del registro
- El registro es de **solo escritura** (la base rechaza modificar o borrar) y **encadenado con SHA-256**: alterar o quitar una fila rompe la cadena y «Verificar integridad» lo detecta.
- Si no se puede registrar una acción sensible, **la acción no se ejecuta**.
- Limitación honesta: quien tenga acceso de administrador a Supabase podría desactivar el bloqueo. Por eso los acuses por correo y `AUDITORIA_COPIA_EMAIL` sirven como registro independiente; se recomienda configurarlo.

## Cambios de comportamiento
- Los ADMIN y los SUPER_ADMIN que no sean oiis.winepi **ya no pueden eliminar duplicados ni hacer respaldos manuales** hasta que se les asigne el permiso.
- Limpiar logs en «Historial y logs» queda solo para oiis.winepi y se registra.
- La papelera de Drive sigue contando para la cuota: use el borrado definitivo (solo principal) si hace falta liberar espacio. En modo local (sin Drive) el retiro es permanente.

## Puesta en marcha de la versión 6
1. Ejecutar `sql/11_auditoria_permisos_repositorio.sql` en Supabase (es seguro repetirlo).
2. Nuevas variables opcionales en `.env` (ver `.env.example`): `DESCARGA_MASIVA_MAX_MB`, `AUDITORIA_COPIA_EMAIL`, `ALERTA_RETIRO_MAX_ARCHIVOS`, `HORARIO_LABORAL_INICIO`, `HORARIO_LABORAL_FIN`.
3. Reiniciar la aplicación (con Docker: `docker compose up -d --build`).
4. Ingresar como oiis.winepi → **Permisos de operación** y asignar lo necesario a cada persona.

# Novedades de la versión 6.1 (revisión final)

- **IP de auditoría más confiable**: ya no se acepta el encabezado `X-Forwarded-For` enviado por el visitante (se podía falsear). Solo se usa si `PROXY_CONFIABLE=true` (con el proxy HTTPS incluido).
- **Logs sin datos personales**: `httpx` y librerías de red dejaron de escribir cada consulta (con usuarios, correos, códigos) en `app.log` y la consola.
- **Respaldos más completos**: incluyen `auditoria_acciones`, `permisos_operaciones`, `descargas_masivas`, `solicitudes_retiro` y `retiros_archivos` (se omiten solas si la tabla aún no existe).
- **HTTPS opcional** con Caddy (`docker compose --profile https up -d`, ver `Caddyfile` y `GUIA_DESPLIEGUE_WINDOWS.md`). Nuevas variables: `APP_BIND`, `SIRE_HOST`, `PROXY_CONFIABLE`.
- **Arreglo: activar un año epidemiológico** hacía un UPDATE sin condición que Supabase rechaza; ahora se desactivan los demás años con condición y, si el año no existe, se conserva el activo.
- **Menos consultas repetidas**: la semana activa, el corte y el año activo se recuerdan 10 segundos y se olvidan al guardar cualquier cambio.
- Se retiró código sin uso en `configuracion.py` y se agregó `GUIA_DESPLIEGUE_WINDOWS.md`.

# Novedades de la versión 6.2

- **Cortes de conexión a Supabase en Windows** («[WinError 10035] No se puede completar de forma inmediata una operación de desbloqueo de socket», «ConnectionTerminated», «Invalid input … in state CLOSED», y un «400 Bad Request» de Cloudflare): la librería de Supabase usaba una sola conexión HTTP/2 compartida entre las sesiones de Streamlit. Ahora (`src/conexion_supabase.py`) se usa HTTP/1.1, se reintentan solo las lecturas cuando la conexión se corta (nunca las escrituras) y las conexiones inactivas se cierran pronto. Variable opcional `SUPABASE_HTTP2=true` para volver a lo anterior.

# Novedades de la versión 6.3

- **Contraseñas de más de 72 bytes**: la versión 5 de bcrypt rechaza lo que excede 72 bytes (las tildes y la «ñ» cuentan doble). La política no ponía tope, así que una contraseña muy larga podía romper el alta o el cambio de contraseña con un error. Ahora la política exige **máximo 64 caracteres (y 72 bytes)** con un mensaje claro, y `hash_password` avisa con claridad si algo supera el límite.
- **Verificación de contraseña silenciosa**: `verificar_password` ya no imprime el detalle de la excepción; deja en el log solo el tipo de problema (por ejemplo, un hash dañado).
- **`resetear_password_admin.py`**: pregunta si también se debe **reactivar la cuenta** (`activo = true`) y la contraseña generada automáticamente se comprueba contra el usuario.
- Se confirmó que el login de administradores (`src/auth.py`) y el de las redes (`src/auth_red.py`) usan las mismas funciones `hash_password` y `verificar_password` que el script, así que el hash generado es compatible.

## v6.4 — Diagnóstico claro cuando Drive no se puede leer

- `Descarga y limpieza`: si ningún archivo se puede leer, ahora se muestra el MOTIVO real del primero y la lista de archivos con su causa (antes solo decía «No se pudo leer ningún archivo de Drive»).
- `DriveManager.descargar_archivo_detallado`: distingue 404 (movido/eliminado o sin acceso a la carpeta), 401/403 (sin permiso de lectura) y fallas de red/DNS desde el contenedor.
- Sin cambios en base de datos, `.env` ni Docker. Basta reconstruir: `docker compose up -d --build`.

## v6.5 — Credencial de Drive ilegible en Docker (Windows) y fin del respaldo «local» silencioso

- **Causa hallada en el piloto:** el contenedor (usuario sin privilegios) recibía `Permission denied` al leer `credentials/service_account.json` montado desde Windows; el sistema caía en silencio a modo LOCAL y no encontraba los archivos de Drive.
- `docker-entrypoint.sh` (nuevo): arranca como root solo para copiar la credencial a `/run/sire/` (modo 0400, dueño `sire`) y baja de inmediato a `sire` con `setpriv`. La aplicación nunca corre como root; la credencial sigue sin ir dentro de la imagen.
- `get_drive_manager()`: si Drive no conecta ya NO pasa a modo local en silencio (los envíos habrían quedado fuera de Drive). Ahora falla con un mensaje claro y el envío del remitente se rechaza con aviso. Solo para pruebas: `STORAGE_FALLBACK_LOCAL=true`.
- «Gestión de Drive» muestra el error de conexión en lugar de romperse; los respaldos quedan registrados como fallidos si Drive no está disponible.
- La descarga masiva ahora también sabe leer envíos que quedaron guardados en el servidor (`storage/`) durante algún periodo de modo local.
- Reconstruir con `docker compose up -d --build`. Sin cambios de base de datos.
- **Hallazgo de seguridad:** `.dockerignore` solo excluía `.env`; un `.env.respaldo` (o cualquier `.env.*`, `*.respaldo`, `*.bak`) dentro de la carpeta se copiaba a la imagen con `COPY . .`, dejando secretos dentro de la imagen. Ahora quedan excluidos de la imagen y de git (`.env.example` sí se conserva).
- **Higiene de secretos:** `.dockerignore` y `.gitignore` ahora excluyen `.env.*` (menos `.env.example`), `*.respaldo`, `*.bak`, `caddy-root.crt`, y el `.gitignore` también `storage/envios/*` y `storage/logs/*`. Antes una copia como `.env.respaldo` se metía dentro de la imagen de Docker.

## v6.6 — Verificación previa al despliegue

- `verificar_despliegue.py` (nuevo, solo lectura, no imprime secretos): revisa variables del `.env`, usuario sin privilegios, credencial de Google, conexión y tablas de Supabase (migraciones 09/10/11), administrador principal y cuentas activas, cadena de auditoría, carpetas de Drive (escribir y quitar) y el inicio de sesión SMTP. Uso: `docker compose exec -u sire app python verificar_despliegue.py` (añadir `--enviar-prueba correo@dominio.pe` para un correo de prueba).
- **HTTPS por IP (probado en el piloto):** el `Caddyfile` ahora define `default_sni {$SIRE_HOST}`. Sin esto, al entrar por una IP (`https://10.0.83.50`) el navegador no envía el nombre del servidor y mostraba `ERR_SSL_PROTOCOL_ERROR`. Tras el cambio, el acceso desde otra PC y el envío de un reporte funcionaron.

## v6.7 — Guía de servidor y limpieza previa a producción

- `GUIA_DESPLIEGUE_SERVIDOR.md` (nueva): comandos completos para instalar en el servidor definitivo (Linux/Windows), servidor sin internet (`docker save/load`), USB, un solo programador, actualización y marcha atrás.
- `sql/99_limpieza_previa_a_produccion.sql` (nuevo, opcional): borra solo los datos operativos de prueba (envíos, descargas, retiros, solicitudes de contraseña, logs) y conserva administradores, redes, configuración, cierres y auditoría. Por defecto hace una prueba en seco (`rollback`).

## v6.8 — Validación por nombre de archivo, reenvíos parciales y formulario

**Qué cambia para quien envía**
- **Apellidos primero, luego Nombres** en el formulario (también en los usuarios frecuentes y en la confirmación).
- **Tipo de reporte se completa solo** al adjuntar el ZIP, igual que los centros: la 2.ª letra del nombre (`c` consulta externa, `e` emergencia, `h` hospitalización). Si hay archivos de nombre libre se respeta además lo ya marcado.
- **Semana y año se validan con el nombre** (`pe4026jj.204` → emergencia, semana 40, año 2026). Si no coinciden con la semana/año elegidos, el envío se **bloquea** con un mensaje claro (por ejemplo, `pc3926ij.282` en la semana 40). Un ZIP con semanas mezcladas se rechaza (un ZIP por semana). También se comprueba que la semana exista en ese año epidemiológico (52 o 53). La validación se repite en el servidor al enviar.
- Solo se leen tipo, semana y año; la primera letra, `jj`/`ij` y el resto no se usan, y **nunca se abre el contenido** de los archivos.
- **Nombres libres** (sin ese formato) se aceptan con aviso y quedan anotados en la observación del envío.
- **Centros con 1 o 2 tipos:** no se exige que estén los tres.

**Reenvíos parciales**
- El duplicado ahora se decide **por archivo: centro + tipo + semana + año** (antes, por ZIP completo). Si un ZIP trae centros/tipos ya recibidos **y** nuevos, se **divide automáticamente**: lo nuevo se registra como envío normal (carpeta principal) y lo repetido como duplicado (carpeta de duplicados). El remitente confirma en el mismo cuadro de diálogo, recibe **un solo acuse** (que cita el código del duplicado) y la OIIS recibe la alerta del duplicado. El ZIP original no se modifica.
- Mismo centro con otro tipo (p. ej. ya envió `c`, ahora envía `h`) **no** es duplicado.
- Si los nombres no permiten verificar centro+tipo se conserva la regla anterior.

**Huellas (ayuda adicional, no bloquea)**
- Cada archivo guarda su huella SHA-256 (no el contenido). Si un archivo es idéntico al enviado por la misma red en otra semana, el envío queda **OBSERVADO** con la nota «Posible reenvío de archivos de otra semana» y la OIIS recibe la alerta. Se ignoran archivos muy pequeños (< 512 bytes).

**Base de datos (opcional, recomendado)**
- Ejecutar `sql/12_envios_detalle_archivos.sql` (agrega `envios.detalle_archivos`). **Sin esa columna todo funciona**: el envío se registra igual y los duplicados se deducen de los centros y tipos del formulario, pero no hay comparación de huellas y la detección es menos exacta. `verificar_despliegue.py` avisa si falta.
- Reconstruir con `docker compose up -d --build`.

## v6.9 — ZIP de otra red bloqueado y mensajes que dicen qué corregir

- **Un ZIP que no es de la red elegida ya no pasa.** Cada código de centro que traen los nombres se cruza con el catálogo de todas las redes:
  - ningún archivo es de la red elegida → **se bloquea** y se indica de qué red es (por ejemplo, «Código 282 · H. I RIOJA → red SAN MARTÍN… cambie “Red asistencial”»);
  - **mezcla** de la red elegida con archivos de otras redes → **se bloquea**, listando qué archivos son de otra red y pidiendo quitarlos;
  - códigos que no existen en el catálogo: si no hay ningún archivo de la red se bloquea; si vienen junto a los de la red, pasa como **OBSERVADO** con nota para la OIIS.
  - Archivos sin código en el nombre no se pueden comprobar y no cuentan. La misma validación se repite en el servidor al enviar.
- **Mensaje de semana/año más claro:** «Los archivos son de la semana 39/2026, pero usted eligió la semana 40/2026», con la lista de archivos y qué hacer. Si el ZIP mezcla semanas, se lista cuántos archivos hay de cada una.
- **Botón «Usar semana X/AAAA»:** si todos los archivos son de una misma semana distinta a la elegida, un clic corrige Semana y Año del formulario.
- Sin cambios de base de datos. Reconstruir con `docker compose up -d --build`.

## v7.0 — Observaciones, reemplazo de envíos y sin alertas por correo a la OIIS

**Antes de usarla:** ejecutar `sql/13_observaciones_envio.sql` en Supabase (crea la tabla `observaciones_envio`; sin ella todo funciona, pero no se guardan observaciones y el módulo avisa que falta). Opcional: `GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID` (si no se define, se crea la carpeta `REEMPLAZADOS` dentro de la carpeta principal). Reconstruir con `docker compose up -d --build`. Los envíos anteriores a esta versión no se trasladan a Observaciones.

**Formulario de envío**
- Nuevo recuadro **«Agregar una observación (opcional)»**, siempre visible, independiente de si hay problemas. Máximo **1000 caracteres** y advertencia «No incluya datos de pacientes ni datos personales». Nunca es obligatoria. Quien envía la ve repetida en su acuse.
- En el cuadro de «Posible envío duplicado» aparece un botón **«Reemplazar los ya enviados»** cuando es seguro hacerlo.

**Reemplazar**
- El ZIP completo se registra como **envío normal** y los archivos anteriores de esos centros/tipos **no se borran**: pasan a la carpeta **REEMPLAZADOS** (`REEMPLAZADOS/<red>/SEMANA_<s>_<año>`).
  - Envío anterior reemplazado por completo → su ZIP va a REEMPLAZADOS y el registro queda «ENVÍO REEMPLAZADO» (deja de contar).
  - Reemplazo parcial → el ZIP original completo se guarda en REEMPLAZADOS y en su lugar queda `*_VIGENTE.zip` con solo lo que sigue vigente.
- Solo se ofrece si **todos** los archivos repetidos se pueden identificar archivo por archivo, y **no** si el resumen de esa semana ya fue **validado o enviado** (entonces va como duplicado). El servidor repite esta comprobación.
- Se avisa por correo a quien envió lo anterior (si es otra persona), queda en auditoría (`ENVIO_REEMPLAZO`) y en Observaciones. Si Drive falla al mover algo, el envío nuevo igual queda registrado, se informa y la OIIS lo ve en Observaciones.

**Panel: módulo «Observaciones»** (visible para todos los roles del panel)
- Fecha y hora, quién envió (correo), red, código, semana/año, motivo (Observado, Duplicado, Reemplazo, Sustento) y sustento con vista previa y texto completo al elegirlo.
- Pestañas **Pendientes / Revisadas**, filtros (red, semana, fechas), marcar como revisadas (seleccionadas o todas), descarga CSV/Excel.
- Un contador discreto en el menú: «Observaciones (N)».

**Sin alertas por correo**
- Los envíos tardíos, observados y duplicados **ya no envían correo a la OIIS ni a administradores**, y el panel de control ya no muestra el cartel de duplicados. Se pueden reactivar en **Configuración → Alertas por correo** (`alertas_correo_admin`, apagado por defecto). Los correos de seguridad (contraseñas, respaldos, cierres) y el acuse a quien envía no cambian.

## v7.1 — Cierre manual del corte, Mi progreso detallado y observación visible

**Cierre manual (cuando el proceso programado está caído o Docker se apagó)**
- Si el corte venció y nadie lo cerró, **Configuración** muestra el panel «El corte venció y no se cerró solo» con el botón **«Cerrar el corte ahora»** (con casilla de confirmación). Hace lo mismo que el proceso automático: cierra la semana, propone la siguiente y el siguiente corte como **provisionales**, avisa por correo y evalúa el respaldo que toque; después se validan o corrigen en el mismo lugar. Si pasaron más de 72 h, el proceso automático no lo cierra solo, pero la persona sí puede hacerlo desde aquí. Es idempotente: pulsarlo dos veces no duplica nada. Queda en auditoría (`CIERRE_MANUAL`).
- En las demás secciones del panel aparece un aviso con el botón «Cerrar ahora». En el menú, burbuja discreta: **«Configuración (1)»** (corte vencido o semana por validar) y **«Respaldos (!)»** (proceso programado sin latido).
- El aviso «El proceso dejó de responder» ahora explica qué hacer mientras tanto y cómo reactivarlo (`docker compose up -d`).
- **Respaldo manual:** ya existía en **Respaldos → «Respaldar ahora»**; requiere el permiso «respaldo manual» (se asigna en «Permisos de operación»).

**Mi progreso (vista de la red)** — nueva sección «Envíos y observaciones de su red», por semana: quién envió (apellidos y nombres, fecha y hora, centros, tipos, archivos, código y estado: a tiempo, tardío, duplicado, con observaciones o reemplazado), cuadro de qué se recibió por centro y tipo (c/e/h), y las observaciones de la red con su estado «pendiente de revisión» o «revisada por la OIIS». Descarga en CSV y Excel. Solo lectura y solo de su red; no genera avisos.

**Formulario** — la observación pasó a ser la **sección 5 «Observación (opcional)»**, siempre visible; si el envío es tardío o trae archivos con nombre libre, el texto sugiere explicar el motivo. Sigue siendo opcional y de hasta 1000 caracteres.

Sin cambios de base de datos. Reconstruir con `docker compose up -d --build`.

## v7.2 — Observaciones separadas de las fallas técnicas y reintento de reemplazos

**Qué pasó en el piloto:** un reemplazo no pudo mover el archivo anterior a REEMPLAZADOS porque Drive respondió 403 `insufficientFilePermissions`. Mover archivos exige más permiso que subirlos: dentro de una misma unidad compartida, la cuenta de servicio necesita el rol **Gestor de contenido** (o superior); entre dos unidades distintas, además, ser **Administrador** de la unidad de origen.

**Cómo dejarlo funcionando:** en `.env` deje **vacío** `GOOGLE_DRIVE_FOLDER_REEMPLAZADOS_ID` (así REEMPLAZADOS es una subcarpeta de la carpeta principal), compruebe en Drive que la cuenta de servicio sea «Gestor de contenido» en esa unidad y reinicie con `docker compose up -d --build`.

**Observaciones (panel)** — ahora con cuatro pestañas:
- **Comentarios de las redes:** solo lo que escribió quien envía (aunque el envío también sea duplicado u observado; el motivo se ve en la columna Motivo).
- **Envíos por revisar:** observados, duplicados y reemplazos marcados por el sistema, sin comentario.
- **Fallas técnicas:** lo que el sistema no pudo completar (p. ej. mover un archivo en Drive), con el detalle técnico y el botón **«Reintentar»**; si sale bien, se marca como atendida y se avisa a quien envió lo anterior. También se puede «Marcar como atendida» a mano. Las redes no las ven.
- **Revisadas:** el historial.
- El menú muestra «Observaciones (N)» con los comentarios y envíos por revisar, y un « !» si hay fallas técnicas. Solo se ven en el panel: no se envía correo.
- La Excel exportada incluye la columna «Categoría».

**Para quien envía:** si el reemplazo no pudo completarse, ve un mensaje neutro («Reemplazo en proceso… la OIIS completará el reemplazo»), sin códigos ni errores técnicos. En «Mi progreso» las fallas técnicas no aparecen.

**Base de datos (opcional, recomendado):** ejecutar `sql/14_observaciones_categorias.sql` (agrega el motivo FALLA y la columna `datos`; reclasifica como falla las que ya quedaron registradas como «Reemplazo»). Sin esto todo funciona, pero las fallas aparecen como «Reemplazo» y no se pueden reintentar.
