#!/usr/bin/env bash
# Levanta el servicio ReST. La carga del CSV ocurre de forma desatendida al iniciar.
#   CSV_PATH=data/ventas.csv ./run.sh
set -e
export CSV_PATH="${CSV_PATH:-data/ventas.csv}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
