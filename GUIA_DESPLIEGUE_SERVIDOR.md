# SIRE – Despliegue en el servidor definitivo (Docker)

Esta guía es para quien instale SIRE en el equipo definitivo (servidor Linux o Windows con Docker).
Nunca pegue claves ni el `.env` en correos o chats.

## 0. Antes de empezar
- Docker instalado (`docker --version`, `docker compose version`).
- Una IP fija o un nombre DNS para el servidor, y los puertos **80 y 443** abiertos hacia él.
- Certificado institucional (`sire.crt` y `sire.key`) si TI lo entrega; si no, se usa el interno de Caddy y los navegadores avisarán.
- El servidor necesita internet para construir la imagen (Docker Hub y PyPI). Si no la tiene, ver la sección **A. Servidor sin internet**.
- Cuenta de servicio de Google con acceso a las 3 carpetas de Drive, y el proyecto de Supabase con las migraciones `sql/09`, `10` y `11` ya ejecutadas.

## 1. Copiar el proyecto
Lleve el ZIP del proyecto (no incluye claves) y descomprímalo.

**Linux**
```bash
sudo mkdir -p /opt/sire && cd /opt/sire
unzip /ruta/sistema_reporte_essalud_SIRE_MEJORADO_vX.zip
cd sistema_reporte_essalud
```
**Windows (PowerShell)**
```powershell
Expand-Archive .\sistema_reporte_essalud_SIRE_MEJORADO_vX.zip -DestinationPath D:\SIRE
cd D:\SIRE\sistema_reporte_essalud
```

## 2. Crear el `.env` y poner la credencial
**Linux**
```bash
cp .env.example .env && chmod 600 .env
nano .env                      # completar TODOS los valores marcados «COMPLETAR»
mkdir -p credentials
cp /ruta/segura/service_account.json credentials/service_account.json
chmod 600 credentials/service_account.json
sudo chown -R 10001:10001 storage
```
**Windows**
```powershell
Copy-Item .env.example .env
notepad .env
New-Item -ItemType Directory -Force credentials | Out-Null
Copy-Item "E:\ruta\segura\service_account.json" .\credentials\service_account.json
```
Valores clave del `.env` en producción:
```
STORAGE_MODE=drive
STORAGE_FALLBACK_LOCAL=false
APP_BIND=127.0.0.1
SIRE_HOST=nombre-dns-o-ip-del-servidor
PROXY_CONFIABLE=true
```

## 3. Certificado (si TI lo entregó)
Copie `sire.crt` y `sire.key` a `certs/` y en `Caddyfile` cambie `tls internal` por
`tls /certs/sire.crt /certs/sire.key`.

## 4. Levantar
```bash
docker compose --profile https up -d --build
docker compose ps
```
Los tres contenedores (`sire-app`, `sire-programador`, `sire-https`) deben quedar «Up» y los dos primeros «healthy».

## 5. Verificar
```bash
docker compose exec -u sire app python verificar_despliegue.py --enviar-prueba correo@dominio.pe
```
Debe terminar en «0 falla(s)». Luego abra `https://<SIRE_HOST>` desde otra PC.

## 6. Solo UN programador
El contenedor `programador` hace cierres, avisos y respaldos. **No debe correr en dos equipos a la vez.**
En el equipo de pruebas: `docker compose down`.

## 7. Arranque automático
Los contenedores usan `restart: unless-stopped`. En Linux: `sudo systemctl enable docker`.
En Windows con Docker Desktop el arranque ocurre al iniciar sesión de usuario, no al encender el equipo.

## 8. Operación diaria
```bash
docker compose ps                      # estado
docker compose logs --tail 100 app     # registros de la web
docker compose logs --tail 100 programador
docker compose restart app             # reiniciar la web
docker compose down                    # detener todo (los datos no se pierden)
docker compose up -d                   # volver a iniciar
```
Cambiar claves del `.env`: editar y ejecutar `docker compose up -d --force-recreate` (`restart` no relee el `.env`).

## 9. Actualizar a una versión nueva
1. Respaldar la carpeta (sobre todo `.env`, `credentials/`, `storage/`).
2. Descomprimir la versión nueva en otra carpeta y **copiar solo los archivos que cambian** (sin pisar `.env`, `credentials/`, `storage/`).
3. `docker compose up -d --build` y luego `verificar_despliegue.py`.
4. Marcha atrás: antes de actualizar, `docker tag sire:latest sire:anterior`; para volver, `docker tag sire:anterior sire:latest && docker compose up -d --force-recreate`.

## A. Servidor sin internet
En un equipo con internet y Docker, construir y exportar las imágenes:
```bash
docker compose --profile https build
docker pull caddy:2
docker save sire:latest caddy:2 -o sire-imagenes.tar
```
Llevar `sire-imagenes.tar` y el ZIP al servidor y allí:
```bash
docker load -i sire-imagenes.tar
docker compose --profile https up -d --no-build
```

## B. Transporte por USB
- El ZIP del proyecto no contiene secretos. El **`.env`** y **`service_account.json`** sí son secretos: use un USB cifrado (BitLocker To Go) o un medio autorizado por TI, y bórrelos del USB al terminar.
- Para producción conviene crear una **clave nueva** de la cuenta de servicio y revocar la del piloto.

## C. Datos de prueba
Si el servidor usa la misma base del piloto, la limpieza de datos de prueba está en
`sql/99_limpieza_previa_a_produccion.sql` (conserva administradores, redes y configuración; hace primero una prueba en seco).
