"""Configuración del entorno de pruebas — SOLO DATOS REALES.

La suite se ejecuta exclusivamente contra el CSV real de producción
(``data/ventas_completas.csv`` o el CSV más grande dentro de ``data/``).

Para verificar los resultados de la API sin depender de Polars, un "oráculo"
independiente implementado con la librería estándar (csv + math) recorre el
mismo archivo una vez por sesión, replica las reglas de limpieza del cargador
(filas sin fecha, sin monto o con nacimiento implausible se descartan) y
acumula los montos de los subconjuntos que usan las pruebas. Así, la API
(Polars, paralelo) y el oráculo (Python puro, secuencial) deben coincidir
sobre los ~3,2 millones de registros: dos implementaciones independientes
validándose mutuamente.

Si el CSV real no está en ``data/``, las pruebas de API se omiten con un
mensaje indicando cómo obtenerlo (ver README).
"""
import csv
import gzip
import math
import os
import sys
from array import array
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pytest

# Permite importar el paquete `app` al ejecutar pytest desde cualquier lugar.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.loader import (  # noqa: E402
    _RENAME_CANON,
    _canon,
    _detect_separator,
    _resolve_path,
)

# Cabeceras del enunciado (con tilde, como el CSV real). Las usa test_loader
# para fabricar CSVs corruptos ad-hoc que ejercitan las defensas del cargador.
HEADERS = [
    "FECHA", "CANAL", "SKU", "PRODUCTO", "UNIDADES", "PORCENTAJE DESCUENTO",
    "MONTO APLICADO", "BOLETA", "LOCAL", "CODIGO CLIENTE", "RUN CLIENTE",
    "NOMBRES", "APELLIDOS", "FECHA NACIMIENTO", "GÉNERO",
]
UUID_A = "550e8400-e29b-41d4-a716-446655440000"

# Subconjuntos de montos que acumula el oráculo durante su única pasada.
_KEYS = (
    "total", "fem", "masc", "pos", "fem_pos",
    "edad0", "sku0", "uuid0", "local0", "desde", "hasta",
)


def esperado(montos) -> dict:
    """Calcula de forma independiente (sin Polars) las 7 métricas que debe
    devolver la API: redondeo a 2 decimales y desviación estándar poblacional.
    Usa math.fsum para que la suma sea exacta incluso con millones de filas."""
    n = len(montos)
    if n == 0:
        return {
            "suma": 0.0, "conteo": 0, "promedio": None, "minimo": None,
            "maximo": None, "mediana": None, "desviacion_estandar": None,
        }
    suma = math.fsum(montos)
    promedio = suma / n
    varianza = math.fsum((x - promedio) ** 2 for x in montos) / n
    ordenados = sorted(montos)
    mediana = (
        ordenados[n // 2] if n % 2
        else (ordenados[n // 2 - 1] + ordenados[n // 2]) / 2
    )
    return {
        "suma": round(suma, 2),
        "conteo": n,
        "promedio": round(promedio, 2),
        "minimo": round(min(montos), 2),
        "maximo": round(max(montos), 2),
        "mediana": round(mediana, 2),
        "desviacion_estandar": round(math.sqrt(varianza), 2),
    }


def _edad(nacimiento: date, hoy: date) -> int:
    """Edad exacta hoy — misma regla que el cargador."""
    cumplio = (hoy.month, hoy.day) >= (nacimiento.month, nacimiento.day)
    return hoy.year - nacimiento.year - (0 if cumplio else 1)


@dataclass
class _Fila:
    fecha: datetime
    fecha_s: str
    monto: float
    edad: int
    canal: str
    uuid: str
    genero: int | None
    sku: int | None
    local: int | None


def _indice(header) -> dict:
    """Mapea nombre canónico -> posición, con la misma normalización de
    cabeceras del cargador (BOM, tildes, espacios)."""
    idx = {}
    for i, nombre in enumerate(header):
        target = _RENAME_CANON.get(_canon(nombre))
        if target and target not in idx:
            idx[target] = i
    requeridas = (
        "fecha", "canal", "sku", "monto_aplicado", "local",
        "codigo_cliente", "fecha_nacimiento", "genero",
    )
    faltan = [c for c in requeridas if c not in idx]
    assert not faltan, f"El CSV real no contiene columnas requeridas: {faltan}"
    return idx


def _parse(row, idx, hoy) -> _Fila | None:
    """Replica la validez del cargador: None si la fila es corrupta en un
    campo esencial (fecha, monto, nacimiento/edad)."""
    try:
        fecha_s = row[idx["fecha"]].strip()
        fecha = datetime.fromisoformat(fecha_s)
        monto = float(row[idx["monto_aplicado"]].strip())
        nacimiento = date.fromisoformat(row[idx["fecha_nacimiento"]].strip())
    except (ValueError, IndexError):
        return None
    edad = _edad(nacimiento, hoy)
    if not (config.MIN_AGE <= edad <= config.MAX_AGE):
        return None

    def _int(col):
        try:
            return int(row[idx[col]].strip())
        except (ValueError, IndexError):
            return None

    return _Fila(
        fecha=fecha,
        fecha_s=fecha_s,
        monto=monto,
        edad=edad,
        canal=row[idx["canal"]].strip(),
        uuid=row[idx["codigo_cliente"]].strip().lower(),
        genero=_int("genero"),
        sku=_int("sku"),
        local=_int("local"),
    )


@dataclass
class Oracle:
    """Montos por subconjunto + valores de filtro tomados de la primera fila
    completamente válida del CSV real."""
    montos: dict
    fecha0: str
    edad0: int
    sku0: int
    local0: int
    uuid0: str


@pytest.fixture(scope="session")
def real_csv() -> Path:
    """Localiza el CSV real con la misma lógica de resolución del servicio."""
    try:
        return _resolve_path(config.CSV_PATH)
    except FileNotFoundError:
        pytest.skip(
            "No hay CSV real en data/. Descargue el archivo del enunciado y "
            "déjelo como data/ventas_completas.csv (ver README)."
        )


@pytest.fixture(scope="session")
def oracle(real_csv) -> Oracle:
    """Única pasada sobre el CSV real acumulando los montos por subconjunto."""
    hoy = date.today()
    es_gz = str(real_csv).lower().endswith(".gz")
    opener = gzip.open if es_gz else open

    with opener(real_csv, "rt", encoding="utf-8", errors="replace", newline="") as f:
        separator = _detect_separator(f.readline())
        f.seek(0)
        rd = csv.reader(f, delimiter=separator)
        idx = _indice(next(rd))

        # Fase 1: elegir la fila objetivo (primera totalmente parseable) que
        # define los valores de EDAD/SKU/LOCAL/UUID/FECHA a filtrar.
        objetivo = None
        for row in rd:
            p = _parse(row, idx, hoy)
            if p and p.genero is not None and p.sku is not None and p.local is not None:
                objetivo = p
                break
        assert objetivo, "El CSV real no tiene ninguna fila completamente válida"

        # Fase 2: pasada completa acumulando los subconjuntos.
        f.seek(0)
        rd = csv.reader(f, delimiter=separator)
        next(rd)
        sub = {k: array("d") for k in _KEYS}
        for row in rd:
            p = _parse(row, idx, hoy)
            if p is None:
                continue
            m = p.monto
            sub["total"].append(m)
            if p.genero == 2:
                sub["fem"].append(m)
                if p.canal == "POS":
                    sub["fem_pos"].append(m)
            elif p.genero == 1:
                sub["masc"].append(m)
            if p.canal == "POS":
                sub["pos"].append(m)
            if p.edad == objetivo.edad:
                sub["edad0"].append(m)
            if p.sku == objetivo.sku:
                sub["sku0"].append(m)
            if p.uuid == objetivo.uuid:
                sub["uuid0"].append(m)
            if p.local == objetivo.local:
                sub["local0"].append(m)
            if p.fecha >= objetivo.fecha:
                sub["desde"].append(m)
            if p.fecha <= objetivo.fecha:
                sub["hasta"].append(m)

    return Oracle(
        montos=sub,
        fecha0=objetivo.fecha_s,
        edad0=objetivo.edad,
        sku0=objetivo.sku,
        local0=objetivo.local,
        uuid0=objetivo.uuid,
    )


@pytest.fixture(scope="session")
def client(real_csv):
    """TestClient con la app cargando el CSV REAL al arrancar (lifespan).

    `app.config` lee CSV_PATH al importarse y otro módulo puede haberlo
    importado ya durante la recolección; por eso se setea el env var Y se
    parchea el atributo del módulo: el lifespan siempre carga el CSV real.
    """
    os.environ["CSV_PATH"] = str(real_csv)
    config.CSV_PATH = real_csv

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
