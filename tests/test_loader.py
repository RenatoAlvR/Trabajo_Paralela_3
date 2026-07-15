"""Pruebas de las DEFENSAS del cargador: normalización de cabeceras, casts
tolerantes y descarte contabilizado de filas corruptas.

Nota: estos tests fabrican CSVs corruptos ad-hoc (en tmp, nunca en data/)
porque la corrupción no puede provocarse a voluntad con el archivo real; son
pruebas del mecanismo de limpieza, no datos de prueba del servicio. La
robustez que verifican quedó demostrada con el CSV real: 2.810 filas
corruptas descartadas de 3.242.878 sin abortar la carga."""
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


def test_descarta_filas_corruptas_sin_abortar(tmp_path):
    """Celdas ilegibles en campos esenciales descartan solo esa fila; en
    campos no esenciales la fila se conserva con null."""
    p = tmp_path / "ventas.csv"
    _write(p, [
        _fila(),                                          # válida
        _fila(**{"MONTO APLICADO": "no-es-numero"}),      # monto corrupto -> fuera
        _fila(FECHA="banana"),                            # fecha corrupta -> fuera
        _fila(**{"FECHA NACIMIENTO": "3000-99-99"}),      # nacimiento ilegible -> fuera
        _fila(**{"FECHA NACIMIENTO": "1890-01-01"}),      # edad implausible -> fuera
        _fila(**{"GÉNERO": "zzz"}),                       # género ilegible -> se conserva
        _fila(LOCAL="abc"),                               # local ilegible -> se conserva
    ])
    ds = DataStore().load(p)
    assert ds.rows_total == 7
    assert ds.rows_dropped == 4
    assert ds.df.height == 3
    # El género ilegible queda como "No especificado", no rompe la carga.
    assert "No especificado" in ds.df["genero_label"].to_list()
    # El local ilegible queda null (esa fila no matchea filtros por LOCAL).
    assert ds.df["local"].null_count() == 1


def test_cabecera_con_bom_tilde_y_punto_y_coma(tmp_path):
    """BOM UTF-8 + cabecera GÉNERO con tilde + separador ';' se autodetectan."""
    p = tmp_path / "ventas.csv"
    contenido = chr(0xFEFF) + ";".join(HEADERS) + "\n" + ";".join(map(str, _fila())) + "\n"
    p.write_text(contenido, encoding="utf-8")
    ds = DataStore().load(p)
    assert ds.df.height == 1
    assert {"fecha", "canal", "genero", "genero_label", "monto_aplicado"} <= set(ds.df.columns)
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
