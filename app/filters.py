"""Validación y construcción de filtros -> predicados de Polars."""
import uuid
from datetime import datetime, timedelta, timezone

import polars as pl

# El enunciado especifica que FECHA viene en formato ISO 8601 UTC-4. La
# columna 'fecha' se almacena naive (sin zona) en ese huso; un filtro que
# llegue con offset explícito debe convertirse a UTC-4 antes de comparar,
# o el resultado queda desplazado hasta 24 h respecto de lo esperado.
_DATA_TZ = timezone(timedelta(hours=-4))

ALLOWED_GENERO = {"No especificado", "Masculino", "Femenino", "Otro"}
ALLOWED_CANAL = {"POS", "WEB", "APP", "CCT", "APR", "WPR"}

# Filtros soportados (nombres textuales exactos del enunciado).
ALLOWED_FILTERS = {
    "GENERO",
    "EDAD",
    "CANAL",
    "CODIGO_PRODUCTO",
    "ID_PERSONA",
    "LOCAL",
    "FECHA_DESDE",
    "FECHA_HASTA",
}


class FilterError(ValueError):
    """Valor inválido para un filtro (se traduce a 400 VF)."""


class UnknownFilter(KeyError):
    """Nombre de consulta no soportado (se traduce a 400 VF)."""


def _to_int(valor, label):
    try:
        v = int(str(valor).strip())
    except (ValueError, TypeError):
        raise FilterError(f"El valor '{valor}' no es un número entero válido para {label}")
    # Los datos se almacenan como Int64: fuera de ese rango no puede existir.
    if not -(2**63) <= v < 2**63:
        raise FilterError(f"El valor '{valor}' está fuera de rango para {label}")
    return v


def _to_datetime(valor, label):
    s = str(valor)
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        raise FilterError(f"El valor '{valor}' no es una fecha ISO-8601 válida para {label}")
    if dt.tzinfo is not None:
        # Convierte al huso de los datos (UTC-4) antes de quitar la zona;
        # así un offset explícito no queda comparado como si fuera naive.
        dt = dt.astimezone(_DATA_TZ)
    return dt.replace(tzinfo=None)


def build_predicate(consulta: str, valor) -> pl.Expr:
    """Devuelve el predicado de Polars para (consulta, valor) o lanza error."""
    c = str(consulta).upper().strip()

    if c not in ALLOWED_FILTERS:
        raise UnknownFilter(consulta)

    if c == "GENERO":
        if valor not in ALLOWED_GENERO:
            raise FilterError(f"El valor '{valor}' no es válido para GENERO")
        return pl.col("genero_label") == valor

    if c == "EDAD":
        return pl.col("edad") == _to_int(valor, "EDAD")

    if c == "CANAL":
        if valor not in ALLOWED_CANAL:
            raise FilterError(f"El valor '{valor}' no es válido para CANAL")
        return pl.col("canal") == valor

    if c == "CODIGO_PRODUCTO":
        return pl.col("sku") == _to_int(valor, "CODIGO_PRODUCTO")

    if c == "ID_PERSONA":
        try:
            u = uuid.UUID(str(valor).strip())
        except (ValueError, AttributeError, TypeError):
            raise FilterError(f"El valor '{valor}' no es un UUID válido para ID_PERSONA")
        # Forma canónica en minúsculas; la columna ya se normalizó al cargar.
        return pl.col("codigo_cliente") == str(u)

    if c == "LOCAL":
        return pl.col("local") == _to_int(valor, "LOCAL")

    if c == "FECHA_DESDE":
        return pl.col("fecha") >= _to_datetime(valor, "FECHA_DESDE")

    if c == "FECHA_HASTA":
        return pl.col("fecha") <= _to_datetime(valor, "FECHA_HASTA")

    raise UnknownFilter(consulta)  # inalcanzable, por seguridad
