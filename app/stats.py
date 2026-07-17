"""Cálculo del resumen estadístico usando el motor paralelo de Polars."""
from functools import reduce

import polars as pl

from . import config


def _round(value):
    if value is None or config.ROUND_DECIMALS is None:
        return value
    return round(float(value), config.ROUND_DECIMALS)


def compute_stats(df: pl.DataFrame, metric_col: str, predicates: list[pl.Expr]) -> dict:
    """Aplica los filtros y devuelve suma, conteo, promedio, min, max,
    mediana y desviación estándar sobre `metric_col`."""
    lf = df.lazy()
    if predicates:
        lf = lf.filter(reduce(lambda a, b: a & b, predicates))

    col = pl.col(metric_col)
    # Las filas con métrica nula no aportan a ninguna estadística: se excluyen
    # antes de agregar para que `conteo` cuadre exactamente con `suma/promedio`
    # (promedio = suma / conteo, tal como exige el enunciado).
    lf = lf.filter(col.is_not_null())
    agg = lf.select(
        col.sum().alias("suma"),
        pl.len().alias("conteo"),
        col.mean().alias("promedio"),
        col.min().alias("minimo"),
        col.max().alias("maximo"),
        col.median().alias("mediana"),
        col.std(ddof=config.STD_DDOF).alias("desviacion_estandar"),
    ).collect()

    row = agg.to_dicts()[0]
    conteo = int(row["conteo"] or 0)

    if conteo == 0:
        return {
            "suma": 0.0,
            "conteo": 0,
            "promedio": None,
            "minimo": None,
            "maximo": None,
            "mediana": None,
            "desviacion_estandar": None,
        }

    return {
        "suma": _round(row["suma"]),
        "conteo": conteo,
        "promedio": _round(row["promedio"]),
        "minimo": _round(row["minimo"]),
        "maximo": _round(row["maximo"]),
        "mediana": _round(row["mediana"]),
        "desviacion_estandar": _round(row["desviacion_estandar"]),
    }
