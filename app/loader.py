"""Carga desatendida y procesamiento paralelo del CSV con Polars.

Soporta:
  * CSV sin comprimir (.csv)      -> lectura perezosa + motor streaming.
  * CSV comprimido con gzip (.gz) -> lectura con descompresión automática.
El separador (`;`, `,`, tab o `|`) y la compresión se autodetectan.

Robustez frente a datos corruptos:
  * Todas las columnas se leen como texto (sin inferencia de tipos) y luego se
    convierten con casts tolerantes (strict=False): un valor ilegible se
    convierte en null en vez de abortar la carga completa del archivo.
  * Las cabeceras se normalizan (BOM, espacios, mayúsculas y tildes), por lo
    que se aceptan tanto "GENERO" como "GÉNERO".
  * Si falta una columna requerida se aborta el arranque con un mensaje claro.
  * NO se descarta ninguna fila: las métricas globales usan TODAS las filas del
    archivo. Una celda ilegible queda como null (casts tolerantes) y una edad
    implausible (nacimiento corrupto) simplemente no coincide con un filtro
    EDAD, pero la fila igual cuenta en los totales globales.

Polars ejecuta la lectura y las agregaciones en paralelo sobre todos los
núcleos disponibles; el motor "streaming" procesa el archivo por chunks,
evitando cargar todo el volumen de una sola vez en memoria.
"""
import gzip
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

import polars as pl

from . import config

logger = logging.getLogger("cruzmorada.loader")

# Mapeo de las columnas originales a nombres canónicos. Las claves se
# comparan tras normalizar cabeceras (_canon), de modo que "GÉNERO",
# "genero " o una cabecera con BOM también calzan.
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
    "GÉNERO": "genero",
}

# Columnas sin las cuales el servicio no puede operar (filtros + métrica).
REQUIRED = {
    "fecha", "canal", "sku", "monto_aplicado", "local",
    "codigo_cliente", "fecha_nacimiento", "genero",
}

# Columnas numéricas: cast tolerante tras leerlas como texto.
INT_COLS = ("sku", "unidades", "boleta", "local", "genero")
FLOAT_COLS = ("porcentaje_descuento", "monto_aplicado")

# Columnas que de verdad usan los filtros y las estadísticas (app/filters.py,
# app/stats.py). El resto del CSV (producto, nombres, apellidos, run, boleta,
# unidades, descuento...) se descarta tras derivar genero_label/edad: retenerlas
# en memoria no aporta nada y por sí solas pueden ser ~40% del DataFrame.
KEEP_COLS = (
    "fecha", "canal", "sku", "monto_aplicado", "local",
    "codigo_cliente", "genero_label", "edad",
)

# Extensiones de CSV reconocidas para la autodetección de archivo.
CSV_SUFFIXES = (".csv", ".csv.gz", ".gz")

GENERO_LABEL = (
    pl.when(pl.col("genero") == 1).then(pl.lit("Masculino"))
    .when(pl.col("genero") == 2).then(pl.lit("Femenino"))
    .when(pl.col("genero") == 3).then(pl.lit("Otro"))
    .otherwise(pl.lit("No especificado"))
    .alias("genero_label")
)


def _canon(name: str) -> str:
    """Normaliza una cabecera: sin tildes, sin BOM ni caracteres de formato
    (categoría Unicode Cf), sin espacios laterales, espacios internos
    colapsados y en mayúsculas."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(
        c for c in s
        if not unicodedata.combining(c) and unicodedata.category(c) != "Cf"
    )
    return re.sub(r"\s+", " ", s.strip().upper())


_RENAME_CANON = {_canon(k): v for k, v in RENAME.items()}


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
    archivo CSV/CSV.GZ dentro de la carpeta de datos (dejando registro en el
    log, para que un typo en CSV_PATH no cargue otro archivo sin que se note)."""
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
    elegido = max(candidates, key=lambda p: p.stat().st_size)
    logger.warning(
        "La ruta configurada '%s' no existe; se carga en su lugar el mayor CSV de %s: %s",
        path, search_dir, elegido,
    )
    return elegido


def _rename_map(columnas) -> dict:
    """Construye el mapa de renombrado con cabeceras normalizadas, evitando
    colisiones si dos cabeceras apuntan al mismo nombre canónico."""
    mapa, usados = {}, set()
    for col in columnas:
        canon = _canon(col)
        target = _RENAME_CANON.get(canon)
        # Tolerancia extra para GÉNERO leído con codificación dañada (G?NERO).
        if target is None and re.fullmatch(r"G.?NERO", canon):
            target = "genero"
        if target and target not in usados:
            mapa[col] = target
            usados.add(target)
    return mapa


def _texto(col: str) -> pl.Expr:
    """Columna como texto sin espacios laterales (null si no es convertible)."""
    return pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()


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
        self.rows_monto_null = 0
        # Resumen estadístico global (sin filtros) precomputado al arranque.
        self.resumen_global: dict | None = None

    def load(self, path) -> "DataStore":
        path = _resolve_path(path)
        gz = _is_gzip(path)
        separator = _detect_separator(_first_line(path, gz))
        hoy = date.today()

        # Sin inferencia de tipos: todo entra como texto y se convierte con
        # casts tolerantes. Así una celda corrupta no aborta la carga.
        read_kwargs = dict(
            separator=separator,
            encoding="utf8-lossy",
            truncate_ragged_lines=True,
        )

        try:
            if gz:
                # scan_csv no admite gzip; read_csv descomprime automáticamente.
                lf = pl.read_csv(str(path), infer_schema=False, **read_kwargs).lazy()
            else:
                lf = pl.scan_csv(str(path), infer_schema=False, **read_kwargs)
            existentes = lf.collect_schema().names()
        except pl.exceptions.NoDataError:
            raise ValueError(f"El archivo CSV está vacío: {path}")
        lf = lf.rename(_rename_map(existentes))

        columnas = set(lf.collect_schema().names())
        faltantes = REQUIRED - columnas
        if faltantes:
            raise ValueError(
                "El CSV no contiene columnas requeridas: "
                + ", ".join(sorted(faltantes))
                + f". Cabeceras encontradas: {existentes}"
            )

        exprs = [
            _texto("fecha").str.to_datetime(strict=False).alias("fecha"),
            _texto("fecha_nacimiento").str.to_date(strict=False).alias("fecha_nacimiento"),
            _texto("canal").alias("canal"),
            # Los UUID son case-insensitive: se normalizan a minúsculas.
            _texto("codigo_cliente").str.to_lowercase().alias("codigo_cliente"),
        ]
        exprs += [
            _texto(c).cast(pl.Int64, strict=False).alias(c)
            for c in INT_COLS if c in columnas
        ]
        exprs += [
            _texto(c).cast(pl.Float64, strict=False).alias(c)
            for c in FLOAT_COLS if c in columnas
        ]

        lf = (
            lf.with_columns(exprs)
            # Un MONTO APLICADO negativo es corrupto (un cobro no puede ser < 0):
            # se marca como null igual que un valor ilegible, para que quede
            # fuera de las 7 métricas. El 0 es válido (una venta puede ser gratis).
            .with_columns(
                pl.when(pl.col("monto_aplicado") < 0)
                .then(pl.lit(None, dtype=pl.Float64))
                .otherwise(pl.col("monto_aplicado"))
                .alias("monto_aplicado")
            )
            .with_columns(GENERO_LABEL, _edad_expr(hoy))
            .select(list(KEEP_COLS))
        )

        df = self._collect(lf, gz)

        # Un CSV con cabecera pero sin filas dejaría el servicio "vivo" pero
        # respondiendo métricas vacías sin ninguna señal del problema: mejor
        # abortar el arranque con un mensaje claro, como con columnas faltantes.
        if df.height == 0:
            raise ValueError(f"El CSV no contiene filas de datos (solo cabecera): {path}")

        # Política: el cargador NO descarta ninguna fila; las celdas ilegibles
        # quedan como null por los casts tolerantes. Quién cuenta en las métricas
        # lo decide `compute_stats`: una fila con MONTO nulo no aporta a las 7
        # estadísticas (no hay número que sumar/promediar), mientras que una
        # fecha o edad nula solo impide que la fila matchee filtros de fecha/edad,
        # pero sigue contando en el resto.
        self.rows_total = df.height
        # Filas con MONTO APLICADO corrupto: ilegible (cast fallido) o negativo.
        # Quedan como null y `compute_stats` las excluye de las 7 métricas.
        self.rows_monto_null = int(df.select(pl.col("monto_aplicado").is_null().sum()).item())
        if self.rows_monto_null:
            logger.warning(
                "%d fila(s) con MONTO APLICADO corrupto (ilegible o negativo); "
                "se excluyen de las métricas.", self.rows_monto_null,
            )

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
