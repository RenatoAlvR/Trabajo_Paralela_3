"""Pruebas de las DEFENSAS del cargador: normalización de cabeceras y casts
tolerantes. Política actual: NO se descarta ninguna fila; una celda ilegible
queda como null pero la fila se conserva y cuenta en los totales globales.

Nota: estos tests fabrican CSVs corruptos ad-hoc (en tmp, nunca en data/)
porque la corrupción no puede provocarse a voluntad con el archivo real; son
pruebas del mecanismo de tolerancia, no datos de prueba del servicio."""
import csv
from datetime import date

import pytest

from conftest import HEADERS, UUID_A

from app.loader import DataStore


def _fila(**overrides):
    hoy = date.today()
    base = {
        "FECHA": "2026-01-10T10:00:00",
        "CANAL": "POS",
        "SKU": "1095",
        "PRODUCTO": "EUCERIN SERUM DERMOP.40ML",
        "UNIDADES": "1",
        "PORCENTAJE DESCUENTO": "0.15",
        "MONTO APLICADO": "12500.0",
        "BOLETA": "100456",
        "LOCAL": "1999",
        "CODIGO CLIENTE": UUID_A,
        "RUN CLIENTE": "12.345.678-5",
        "NOMBRES": "JUAN",
        "APELLIDOS": "PÉREZ GÓMEZ",
        "FECHA NACIMIENTO": f"{hoy.year - 30}-01-01",
        "GÉNERO": "1",
    }
    base.update(overrides)
    return [base[h] for h in HEADERS]


def _write(path, filas, sep=","):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=sep)
        w.writerow(HEADERS)
        w.writerows(filas)


def test_no_descarta_filas_celdas_corruptas_quedan_null(tmp_path):
    """Política actual: NINGUNA fila se descarta. Una celda ilegible en
    cualquier columna queda como null, pero la fila se conserva y cuenta en los
    totales globales."""
    p = tmp_path / "ventas.csv"
    _write(p, [
        _fila(),                                          # válida
        _fila(**{"MONTO APLICADO": "no-es-numero"}),      # monto ilegible -> null, se conserva
        _fila(FECHA="banana"),                            # fecha ilegible -> null, se conserva
        _fila(**{"FECHA NACIMIENTO": "3000-99-99"}),      # nacimiento ilegible -> null, se conserva
        _fila(**{"FECHA NACIMIENTO": "1890-01-01"}),      # edad alta -> se conserva (sin filtro de edad)
        _fila(**{"GÉNERO": "zzz"}),                       # género ilegible -> "No especificado"
        _fila(LOCAL="abc"),                               # local ilegible -> null
    ])
    ds = DataStore().load(p)
    # NINGUNA fila se descarta: las 7 se conservan.
    assert ds.rows_total == 7
    assert ds.df.height == 7
    # Las celdas ilegibles quedan como null, sin romper la carga.
    assert ds.df["monto_aplicado"].null_count() == 1
    assert ds.df["fecha"].null_count() == 1
    # `fecha_nacimiento` no se retiene (solo se usa para derivar `edad`); un
    # nacimiento ilegible se refleja como `edad` nula.
    assert ds.df["edad"].null_count() == 1
    assert ds.df["local"].null_count() == 1
    # El género ilegible queda como "No especificado".
    assert "No especificado" in ds.df["genero_label"].to_list()


def test_monto_negativo_se_marca_como_corrupto(tmp_path):
    """Un MONTO APLICADO negativo se trata como corrupto (null) y queda fuera de
    las métricas; el 0 es válido y se conserva. La fila no se descarta."""
    p = tmp_path / "ventas.csv"
    _write(p, [
        _fila(),                                     # 12500.0 válido
        _fila(**{"MONTO APLICADO": "-500.0"}),       # negativo -> corrupto -> null
        _fila(**{"MONTO APLICADO": "0"}),            # cero -> válido, se conserva
    ])
    ds = DataStore().load(p)
    assert ds.df.height == 3                          # ninguna fila se descarta
    assert ds.df["monto_aplicado"].null_count() == 1  # solo el negativo es null
    assert ds.rows_monto_null == 1
    montos = ds.df["monto_aplicado"].to_list()
    assert 0.0 in montos                              # el 0 se conserva (válido)
    assert -500.0 not in montos                       # el negativo se anuló


def test_cabecera_con_bom_tilde_y_punto_y_coma(tmp_path):
    """BOM UTF-8 + cabecera GÉNERO con tilde + separador ';' se autodetectan."""
    p = tmp_path / "ventas.csv"
    contenido = chr(0xFEFF) + ";".join(HEADERS) + "\n" + ";".join(map(str, _fila())) + "\n"
    p.write_text(contenido, encoding="utf-8")
    ds = DataStore().load(p)
    assert ds.df.height == 1
    # Solo se retienen las columnas que usan filtros/estadísticas; `genero`
    # crudo se consume al derivar `genero_label` y no se conserva.
    assert {"fecha", "canal", "genero_label", "monto_aplicado"} <= set(ds.df.columns)
    assert "genero" not in ds.df.columns
    assert ds.df["genero_label"][0] == "Masculino"


def test_codigo_cliente_se_normaliza_a_minusculas(tmp_path):
    """Los UUID son case-insensitive: se almacenan en forma canónica."""
    p = tmp_path / "ventas.csv"
    _write(p, [_fila(**{"CODIGO CLIENTE": UUID_A.upper()})])
    ds = DataStore().load(p)
    assert ds.df["codigo_cliente"][0] == UUID_A


def test_columnas_requeridas_faltantes_aborta_con_mensaje_claro(tmp_path):
    p = tmp_path / "ventas.csv"
    p.write_text("FOO,BAR\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columnas requeridas"):
        DataStore().load(p)
