# Guía de despliegue de SIRE en Windows (Docker Desktop)

## 1. Una sola vez
1. Instalar **Docker Desktop** (con WSL 2) y abrirlo. En *Settings → General* activar **Start Docker Desktop when you sign in**.
2. En el equipo: desactivar la suspensión/hibernación (Configuración → Sistema → Inicio/apagado y suspensión → *Nunca*). Si el equipo duerme, la app y el programador se detienen.
3. Copiar la carpeta del proyecto, por ejemplo a `C:\SIRE\`.
4. Crear la carpeta `credentials\` con `service_account.json` (la cuenta de servicio) y copiar `.env.example` como `.env`. Completar **todas** las líneas marcadas con `<<< COMPLETAR`. **El `.env` y `credentials\` nunca se suben a GitHub ni se envían por correo.**
5. En Supabase (SQL Editor) ejecutar, en este orden, los SQL de la carpeta `sql\` que falten: `09`, `10` y **`11_auditoria_permisos_repositorio.sql`** (todos se pueden repetir sin riesgo).
6. Compartir las 3 carpetas de Drive (principal, duplicados y respaldos) con la cuenta de servicio como **Editor** o **Gestor de contenido**.

## 2. Levantar la aplicación
En PowerShell, dentro de `C:\SIRE\`:

```powershell
docker compose up -d --build
docker compose ps          # app y programador deben decir "healthy"
docker compose logs -f app # Ctrl+C para salir
```
Se abre en `http://localhost:8501` (o `http://<IP-del-equipo>:8501` para el resto del personal; permitir el puerto 8501 en el *Firewall de Windows*).

> En Windows con Docker Desktop **no hace falta** ajustar permisos de `storage\`. (Solo en un servidor Linux haría falta `sudo chown -R 10001:10001 storage` antes de levantar.)

## 3. HTTPS (recomendado: las contraseñas viajan por la red)
1. En `.env`:
   ```
   APP_BIND=127.0.0.1
   SIRE_HOST=nombre-o-IP-del-equipo      # por ejemplo sire-oiis o 10.20.30.40
   PROXY_CONFIABLE=true
   ```
2. Levantar con el perfil https:
   ```powershell
   docker compose --profile https up -d --build
   ```
3. Permitir en el Firewall de Windows los puertos **80 y 443** (y ya no el 8501). El personal entra por `https://<SIRE_HOST>`. Ejemplo (PowerShell como administrador): `New-NetFirewallRule -DisplayName "SIRE HTTPS" -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow -Profile Domain,Private`. Desde otra PC se comprueba con `Test-NetConnection <SIRE_HOST> -Port 443`. En el propio equipo servidor se sigue entrando por `http://localhost:8501`.
4. **Certificado.** Con `tls internal` (por defecto) el navegador avisa «conexión no privada» hasta instalar el certificado raíz de Caddy en cada PC:
   ```powershell
   docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt .\caddy-root.crt
   ```
   Instalar `caddy-root.crt` en *Entidades de certificación raíz de confianza* (TI puede distribuirlo por directiva de grupo). Si TI entrega un certificado institucional, copiar `sire.crt` y `sire.key` a `certs\` y cambiar en `Caddyfile` la línea `tls internal` por `tls /certs/sire.crt /certs/sire.key`.
5. **Sobre la IP en la auditoría:** Docker Desktop en Windows puede mostrar la IP interna de Docker (por ejemplo `172.x.x.x`) en lugar de la del equipo del visitante. Compruébelo en *Control de actividad* tras un ingreso desde otra PC. Si sale la interna, la IP solo es referencial; el usuario, la hora y la acción se registran igual.

## 4. Primera puesta en marcha en la aplicación
1. Ingresar como `oiis.winepi` → **Gestión de Drive → Probar acceso** en las 3 carpetas.
2. **Permisos de operación**: asignar a cada persona solo lo que necesita (descarga masiva, retiro, respaldo manual, ver auditoría).
3. **Control de actividad → Verificar ahora**: debe decir «Registro íntegro».
4. Hacer una descarga masiva y un retiro de un archivo de prueba y comprobar que llegan los correos (con copia a `AUDITORIA_COPIA_EMAIL`). **Retirar un archivo de prueba y confirmar si se puede restaurar desde la papelera de Drive** (depende de quién sea dueño del archivo).

## 5. Día a día
| Acción | Comando |
|---|---|
| Ver estado | `docker compose ps` |
| Ver errores | `docker compose logs --tail 100 app` |
| Reiniciar | `docker compose restart` |
| Actualizar a una versión nueva | reemplazar el código (conservando `.env`, `credentials\` y `storage\`) y `docker compose up -d --build` |
| Detener | `docker compose down` |

## 6. Copias de seguridad que le corresponden al equipo
- Guardar una copia de **`.env` y `credentials\service_account.json`** en un lugar seguro y distinto al equipo (sin correo ni chat).
- Los respaldos de datos van solos a la carpeta BACKUPS de Drive; desde v6.1 incluyen la auditoría y los permisos.

## Verificación previa al despliegue

Antes de abrir el sistema al personal (y cada vez que cambie credenciales):

```
docker compose exec -u sire app python verificar_despliegue.py
docker compose exec -u sire app python verificar_despliegue.py --enviar-prueba su.correo@dominio.pe
```

Debe terminar en «0 falla(s)». Es de solo lectura y nunca muestra claves. Use `-u sire` para que la prueba se haga con el mismo usuario que la aplicación.

### Cambiar credenciales sin reconstruir

1. Edite `.env` (por ejemplo `SUPABASE_KEY` o `EMAIL_PASSWORD`).
2. `docker compose up -d --force-recreate` (`restart` no relee el `.env`).
3. Ejecute la verificación de arriba.
