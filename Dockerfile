# SIREA: imagen única; la usan la web (app) y el proceso programado (programador).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Lima \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Usuario sin privilegios. El arranque (docker-entrypoint.sh) entra como root solo para dejar la credencial
# de Google legible por "sire" y baja de inmediato a ese usuario; la aplicación nunca corre como root.
RUN useradd --create-home --uid 10001 sire \
    && mkdir -p /app/storage/logs /app/storage/backups /app/storage/envios /app/storage/temp \
    && chown -R sire:sire /app/storage \
    && sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod 0755 /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]

EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
