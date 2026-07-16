# Servicio ReST - Resumen estadístico de ventas (Cruz Morada)
# Imagen reproducible sobre Ubuntu 24.04 LTS (trae Python 3.12).
FROM ubuntu:24.04

# Entorno no interactivo y salida de Python sin buffer (logs en tiempo real).
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CSV_PATH=/app/data/ventas_completas.csv

# Python 3 + pip. Se limpia la caché de apt para reducir el tamaño de la imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dependencias primero (mejor cacheo de capas: solo se reinstala si cambian).
#    Ubuntu 24.04 aplica PEP 668 (entorno gestionado); dentro del contenedor es
#    seguro instalar a nivel de sistema con --break-system-packages.
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# 2) Código de la aplicación. El CSV NO se copia a la imagen: es pesado y se
#    monta como volumen en tiempo de ejecución (ver docker-compose.yml).
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY run.sh .

EXPOSE 8000

# Carga desatendida del CSV al iniciar (evento lifespan) + servidor uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
