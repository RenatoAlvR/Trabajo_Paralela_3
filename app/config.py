"""Configuración central del servicio.

Todos los valores pueden sobreescribirse por variable de entorno, lo que
permite una carga desatendida y parametrizable (CSV_PATH, etc.).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Ruta del CSV que se carga de forma desatendida al iniciar la aplicación.
# Mismo default que run.sh, Dockerfile y data/README.md; si la ruta exacta no
# existe, el loader busca el mayor CSV/CSV.GZ dentro de data/ (y lo loggea).
CSV_PATH = Path(os.getenv("CSV_PATH", str(DATA_DIR / "ventas_completas.csv")))

# Columna numérica sobre la que se calculan las estadísticas.
METRIC_COLUMN = os.getenv("METRIC_COLUMN", "monto_aplicado")

# Motor streaming de Polars (recomendado para archivos de gran volumen).
USE_STREAMING = os.getenv("USE_STREAMING", "1") == "1"

# ddof para la desviación estándar: 0 = poblacional, 1 = muestral.
STD_DDOF = int(os.getenv("STD_DDOF", "0"))

# Nota: no se descarta ninguna fila por edad. Las métricas globales usan TODAS
# las filas del archivo; la edad solo se usa cuando se aplica el filtro EDAD.

# Cantidad de decimales en la respuesta. ROUND_DECIMALS=none desactiva el
# redondeo (comparar contra la cadena, no contra el objeto None: viene de una
# variable de entorno, siempre es texto).
_round_decimals_env = os.getenv("ROUND_DECIMALS", "2").strip()
ROUND_DECIMALS = None if _round_decimals_env.lower() == "none" else int(_round_decimals_env)

# Ruta base de la API.
API_BASE = "/v1/estadisticas/ventas"

# Cantidad máxima de filtros en un POST. Sin límite, un AND anidado con miles
# de predicados puede desbordar el stack nativo del motor de Polars (DoS).
MAX_CONSULTAS = int(os.getenv("MAX_CONSULTAS", "100"))

# Tamaño máximo del cuerpo de una petición, en bytes (por defecto 1 MB). Un
# cuerpo mayor se rechaza con 413 ANTES de leerlo en memoria, para que una sola
# petición gigante no agote la RAM del servidor (DoS). Una lista de filtros
# legítima pesa unos pocos KB, así que 1 MB es holgado.
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(1_000_000)))
