#!/bin/sh
# SIREA: arranque del contenedor.
# Entra como root SOLO para copiar la credencial de Google a un sitio privado que lea el usuario "sire",
# y de inmediato baja a ese usuario sin privilegios (setpriv) para ejecutar la aplicación.
# Así no importa con qué permisos monte Windows/Docker Desktop la carpeta credentials/.
set -e

if [ "$(id -u)" = "0" ]; then
    RUTA="${GOOGLE_CREDENTIALS_PATH:-credentials/service_account.json}"
    case "$RUTA" in
        /*) ORIGEN="$RUTA" ;;
        *)  ORIGEN="/app/$RUTA" ;;
    esac
    if [ -f "$ORIGEN" ]; then
        mkdir -p /run/sire
        chown 10001:10001 /run/sire
        chmod 700 /run/sire
        install -m 400 -o 10001 -g 10001 "$ORIGEN" /run/sire/service_account.json
        export GOOGLE_CREDENTIALS_PATH=/run/sire/service_account.json
    else
        echo "AVISO: no se encontró la credencial de Google en $ORIGEN (¿se montó la carpeta credentials/?)" >&2
    fi
    export HOME=/home/sire
    exec setpriv --reuid=10001 --regid=10001 --clear-groups -- "$@"
fi

exec "$@"
