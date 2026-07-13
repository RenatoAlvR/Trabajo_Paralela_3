"""Configuración central del servicio.

Todos los valores pueden sobreescribirse por variable de entorno, lo que
permite una carga desatendida y parametrizable (CSV_PATH, etc.).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Ruta del CSV que se carga de forma desatendida al iniciar la aplicación.
CSV_PATH = Path(os.getenv("CSV_PATH", str(DATA_DIR / "ventas.csv")))

# Columna numérica sobre la que se calculan las estadísticas.
METRIC_COLUMN = os.getenv("METRIC_COLUMN", "monto_aplicado")

# Motor streaming de Polars (recomendado para archivos de gran volumen).
USE_STREAMING = os.getenv("USE_STREAMING", "1") == "1"

# ddof para la desviación estándar: 0 = poblacional, 1 = muestral.
STD_DDOF = int(os.getenv("STD_DDOF", "0"))

# Rango de edad plausible. Las filas con fecha de nacimiento no parseable o con
# edad fuera de [MIN_AGE, MAX_AGE] se consideran corruptas y se descartan al
# cargar (la fuente no ofrece forma de corregirlas).
MIN_AGE = int(os.getenv("MIN_AGE", "0"))
MAX_AGE = int(os.getenv("MAX_AGE", "120"))

# Cantidad de decimales en la respuesta (None = sin redondear).
ROUND_DECIMALS = int(os.getenv("ROUND_DECIMALS", "2"))

# Ruta base de la API.
API_BASE = "/v1/estadisticas/ventas"
