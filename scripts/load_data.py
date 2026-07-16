"""Carga desatendida por CLI (alternativa al arranque del servidor).

Uso:
    python scripts/load_data.py [ruta_csv]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.loader import store  # noqa: E402


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else config.CSV_PATH
    store.load(path)
    df = store.df
    print(f"Cargado: {df.height} filas (sin descartes), {df.width} columnas desde {store.source}")
    print(f"Filas con monto nulo (informativo): {store.rows_monto_null}")
    print("Columnas:", ", ".join(df.columns))


if __name__ == "__main__":
    main()
