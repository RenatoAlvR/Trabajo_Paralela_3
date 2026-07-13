"""Carga desatendida y procesamiento paralelo del CSV con Polars.

Soporta:
  * CSV sin comprimir (.csv)      -> lectura perezosa + motor streaming.
  * CSV comprimido con gzip (.gz) -> lectura con descompresión automática.
El separador (`;` o `,`) se autodetecta, al igual que la compresión.

Polars ejecuta la lectura y las agregaciones en paralelo sobre todos los
núcleos disponibles; el motor "streaming" procesa el archivo por chunks,
evitando cargar todo el volumen de una sola vez en memoria.
"""
import gzip
from datetime import date
from pathlib import Path

import polars as pl

from . import config

# Mapeo de las columnas originales (con espacios) a nombres canónicos.
RENAME = {
    "FECHA": "fecha",
    "CANAL": "canal",
    "SKU": "sku",
    "PRODUCTO": "producto",
    "UNIDADES": "unidades",
    "PORCENTAJE DESCUENTO": "porcentaje_descuento",
    "MONTO APLICADO": "monto_aplicado",
    "BOLETA": "boleta",
    "LOCAL": "local",
    "CODIGO CLIENTE": "codigo_cliente",
    "RUN CLIENTE": "run_cliente",
    "NOMBRES": "nombres",
    "APELLIDOS": "apellidos",
    "FECHA NACIMIENTO": "fecha_nacimiento",
    "GENERO": "genero",
}

# Fuerza tipos en columnas sensibles (evita inferencias erróneas int/float).
SCHEMA_OVERRIDES = {"MONTO APLICADO": pl.Float64}

# Extensiones de CSV reconocidas para la autodetección de archivo.
CSV_SUFFIXES = (".csv", ".csv.gz", ".gz")

GENERO_LABEL = (
    pl.when(pl.col("genero") == 1).then(pl.lit("Masculino"))
    .when(pl.col("genero") == 2).then(pl.lit("Femenino"))
    .when(pl.col("genero") == 3).then(pl.lit("Otro"))
    .otherwise(pl.lit("No especificado"))
    .alias("genero_label")
)


def _is_gzip(path: Path) -> bool:
    if str(path).lower().endswith(".gz"):
        return True
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def _first_line(path: Path, gz: bool) -> str:
    opener = gzip.open if gz else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        return f.readline()


def _detect_separator(header: str) -> str:
    counts = {sep: header.count(sep) for sep in (";", ",", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _resolve_path(path) -> Path:
    """Devuelve el CSV a cargar; si la ruta exacta no existe, busca el mayor
    archivo CSV/CSV.GZ dentro de la carpeta de datos."""
    path = Path(path)
    if path.exists():
        return path
    search_dir = path.parent if path.parent.exists() else config.DATA_DIR
    candidates = [
        p for p in search_dir.glob("*")
        if p.is_file() and str(p).lower().endswith(CSV_SUFFIXES)
    ]
    if not candidates:
        raise FileNotFoundError(f"No se encontró ningún CSV en: {search_dir}")
    return max(candidates, key=lambda p: p.stat().st_size)


def _edad_expr(hoy: date) -> pl.Expr:
    """Edad exacta en años a partir de la fecha de nacimiento."""
    fn = pl.col("fecha_nacimiento")
    ya_cumplio = (
        (pl.lit(hoy.month) > fn.dt.month())
        | ((pl.lit(hoy.month) == fn.dt.month()) & (pl.lit(hoy.day) >= fn.dt.day()))
    )
    return (
        (pl.lit(hoy.year) - fn.dt.year() - (~ya_cumplio).cast(pl.Int32))
        .cast(pl.Int32)
        .alias("edad")
    )


class DataStore:
    """Almacenamiento en memoria de los datos ya procesados."""

    def __init__(self):
        self.df: pl.DataFrame | None = None
        self.loaded = False
        self.source: Path | None = None
        self.rows_total = 0
        self.rows_dropped = 0

    def load(self, path) -> "DataStore":
        path = _resolve_path(path)
        gz = _is_gzip(path)
        separator = _detect_separator(_first_line(path, gz))
        hoy = date.today()

        read_kwargs = dict(
            separator=separator,
            infer_schema_length=10_000,
            schema_overrides=SCHEMA_OVERRIDES,
        )

        if gz:
            # scan_csv no admite gzip; read_csv descomprime automáticamente.
            lf = pl.read_csv(str(path), **read_kwargs).lazy()
        else:
            lf = pl.scan_csv(str(path), **read_kwargs)

        existentes = set(lf.collect_schema().names())
        lf = lf.rename({k: v for k, v in RENAME.items() if k in existentes})

        lf = lf.with_columns(
            pl.col("fecha").str.to_datetime(strict=False).alias("fecha"),
            pl.col("fecha_nacimiento").str.to_date(strict=False).alias("fecha_nacimiento"),
            pl.col("genero").cast(pl.Int64, strict=False).alias("genero"),
            pl.col("monto_aplicado").cast(pl.Float64, strict=False).alias("monto_aplicado"),
        ).with_columns(
            GENERO_LABEL,
            _edad_expr(hoy),
        )

        df = self._collect(lf, gz)

        # Descarta filas con fecha de nacimiento corrupta (edad implausible).
        valido = (
            pl.col("fecha_nacimiento").is_not_null()
            & (pl.col("edad") >= config.MIN_AGE)
            & (pl.col("edad") <= config.MAX_AGE)
        )
        self.rows_total = df.height
        df = df.filter(valido)
        self.rows_dropped = self.rows_total - df.height

        self.df = df
        self.loaded = True
        self.source = path
        return self

    @staticmethod
    def _collect(lf: pl.LazyFrame, gz: bool) -> pl.DataFrame:
        # Para gzip los datos ya están materializados (read_csv); collect es directo.
        if config.USE_STREAMING and not gz:
            try:
                return lf.collect(engine="streaming")
            except TypeError:
                return lf.collect(streaming=True)
        return lf.collect()


# Instancia global usada por la aplicación.
store = DataStore()
