"""Pruebas de la API /v1/estadisticas/ventas — SOLO DATOS REALES.

La API (Polars, cómputo paralelo) se contrasta contra un oráculo
independiente (Python puro, ver conftest) sobre el CSV real de producción:

  * Éxito GET/POST con las 7 métricas redondeadas a 2 decimales.
  * Todos los filtros soportados (GENERO, EDAD, CANAL, CODIGO_PRODUCTO,
    ID_PERSONA, LOCAL, FECHA_DESDE, FECHA_HASTA) y combinaciones, con valores
    tomados de la primera fila válida del propio CSV real.
  * Validaciones 400 con la estructura exacta de error del enunciado.
  * Casos límite: filtros sin coincidencias (conteo=0, métricas nulas).
"""
import re

import pytest

from conftest import esperado

ENDPOINT = "/v1/estadisticas/ventas"

METRICAS = {
    "suma", "conteo", "promedio", "minimo", "maximo", "mediana",
    "desviacion_estandar",
}

ERROR_KEYS = {
    "detail", "instance", "status", "title", "type", "timestamp",
    "errorCode", "errorLabel", "method",
}

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$")

# LOCAL válido como Int64 pero imposible en los datos (para conteo=0).
LOCAL_INEXISTENTE = "4611686018427387904"


def post(client, consultas):
    return client.post(ENDPOINT, json={"consultas": consultas})


def check_resumen(body: dict, expected: dict):
    """El cuerpo debe traer exactamente las 7 métricas con los valores del
    oráculo. Tolerancia: redondeo a 2 decimales + margen relativo ínfimo por
    el distinto orden de suma en punto flotante (Polars suma en paralelo)."""
    assert set(body) == METRICAS
    assert body["conteo"] == expected["conteo"]
    for k, v in expected.items():
        if k == "conteo":
            continue
        if v is None:
            assert body[k] is None, f"{k} debería ser null"
        else:
            assert body[k] == pytest.approx(v, rel=1e-12, abs=0.011), k


def check_error_400(body: dict, method: str):
    """La estructura de error debe cumplir exactamente el esquema del enunciado."""
    assert set(body) == ERROR_KEYS
    assert body["status"] == 400
    assert body["title"] == "Bad Request"
    assert body["type"] == (
        "https://developer.mozilla.org/es/docs/Web/HTTP/Reference/Status/400"
    )
    assert body["errorCode"] == "VF"
    assert body["errorLabel"] == "Validación Fallida"
    assert body["instance"] == ENDPOINT
    assert body["method"] == method
    assert isinstance(body["detail"], str) and body["detail"]
    assert TIMESTAMP_RE.match(body["timestamp"]), body["timestamp"]


# --------------------------------------------------------------------------- #
# Éxito: GET / POST sobre la totalidad de los datos reales
# --------------------------------------------------------------------------- #
def test_get_sin_filtros_devuelve_las_7_metricas(client, oracle):
    r = client.get(ENDPOINT)
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["total"]))


def test_get_redondea_a_2_decimales(client):
    r = client.get(ENDPOINT)
    body = r.json()
    for k in METRICAS - {"conteo"}:
        valor = body[k]
        assert valor is not None
        assert round(valor, 2) == valor, f"{k} no está redondeado a 2 decimales"


def test_post_con_filtro_devuelve_las_7_metricas(client, oracle):
    r = post(client, [{"consulta": "CANAL", "valor": "POS"}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["pos"]))


# --------------------------------------------------------------------------- #
# Filtros soportados (valores tomados del propio CSV real)
# --------------------------------------------------------------------------- #
def test_filtro_genero_femenino_post(client, oracle):
    r = post(client, [{"consulta": "GENERO", "valor": "Femenino"}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["fem"]))


def test_filtro_genero_masculino_get(client, oracle):
    r = client.get(ENDPOINT, params={"GENERO": "Masculino"})
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["masc"]))


def test_filtro_edad(client, oracle):
    r = post(client, [{"consulta": "EDAD", "valor": str(oracle.edad0)}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["edad0"]))


def test_filtro_canal_get(client, oracle):
    r = client.get(ENDPOINT, params={"CANAL": "POS"})
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["pos"]))


def test_filtro_codigo_producto(client, oracle):
    r = post(client, [{"consulta": "CODIGO_PRODUCTO", "valor": str(oracle.sku0)}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["sku0"]))


def test_filtro_id_persona(client, oracle):
    r = post(client, [{"consulta": "ID_PERSONA", "valor": oracle.uuid0}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["uuid0"]))


def test_filtro_local(client, oracle):
    r = post(client, [{"consulta": "LOCAL", "valor": str(oracle.local0)}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["local0"]))


def test_filtro_fecha_desde(client, oracle):
    r = post(client, [{"consulta": "FECHA_DESDE", "valor": oracle.fecha0}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["desde"]))


def test_filtro_fecha_hasta(client, oracle):
    r = post(client, [{"consulta": "FECHA_HASTA", "valor": oracle.fecha0}])
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["hasta"]))


def test_filtro_rango_fechas_get(client, oracle):
    r = client.get(
        ENDPOINT,
        params={
            "FECHA_DESDE": oracle.fecha0,
            "FECHA_HASTA": "2099-01-01T00:00:00",
        },
    )
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["desde"]))


def test_filtros_combinados(client, oracle):
    r = post(
        client,
        [
            {"consulta": "GENERO", "valor": "Femenino"},
            {"consulta": "CANAL", "valor": "POS"},
        ],
    )
    assert r.status_code == 200
    check_resumen(r.json(), esperado(oracle.montos["fem_pos"]))


# --------------------------------------------------------------------------- #
# Validaciones: 400 Bad Request (errorCode VF)
# --------------------------------------------------------------------------- #
def test_post_consultas_vacias(client):
    r = post(client, [])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_post_consultas_nulas(client):
    r = client.post(ENDPOINT, json={"consultas": None})
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_post_body_vacio(client):
    r = client.post(ENDPOINT, json={})
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_post_consulta_sin_valor(client):
    r = post(client, [{"consulta": "GENERO"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_genero_no_permitido(client):
    r = post(client, [{"consulta": "GENERO", "valor": "Desconocido"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_canal_no_permitido(client):
    r = post(client, [{"consulta": "CANAL", "valor": "TELEPATIA"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


@pytest.mark.parametrize("filtro", ["EDAD", "LOCAL", "CODIGO_PRODUCTO"])
def test_texto_en_filtro_numerico(client, filtro):
    r = post(client, [{"consulta": filtro, "valor": "qwerqwer"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_entero_fuera_de_rango(client):
    r = post(client, [{"consulta": "LOCAL", "valor": "99999999999999999999"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_uuid_mal_formado(client):
    r = post(client, [{"consulta": "ID_PERSONA", "valor": "no-soy-un-uuid"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


@pytest.mark.parametrize("valor", ["2026-13-99", "no-es-fecha", "31/12/2026"])
@pytest.mark.parametrize("filtro", ["FECHA_DESDE", "FECHA_HASTA"])
def test_fecha_invalida(client, filtro, valor):
    r = post(client, [{"consulta": filtro, "valor": valor}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_consulta_desconocida(client):
    r = post(client, [{"consulta": "COLOR_FAVORITO", "valor": "morado"}])
    assert r.status_code == 400
    check_error_400(r.json(), "POST")


def test_validacion_en_get_usa_metodo_get(client):
    r = client.get(ENDPOINT, params={"EDAD": "abc"})
    assert r.status_code == 400
    check_error_400(r.json(), "GET")


# --------------------------------------------------------------------------- #
# Casos límite
# --------------------------------------------------------------------------- #
def test_sin_coincidencias_conteo_cero(client):
    r = post(client, [{"consulta": "LOCAL", "valor": LOCAL_INEXISTENTE}])
    assert r.status_code == 200
    body = r.json()
    assert set(body) == METRICAS
    assert body["conteo"] == 0
    assert body["suma"] == 0.0
    for k in ("promedio", "minimo", "maximo", "mediana", "desviacion_estandar"):
        assert body[k] is None


def test_sin_coincidencias_por_fecha_futura(client):
    r = client.get(ENDPOINT, params={"FECHA_DESDE": "2099-01-01T00:00:00"})
    assert r.status_code == 200
    assert r.json()["conteo"] == 0


# --------------------------------------------------------------------------- #
# Límite de tamaño del cuerpo (413)
# --------------------------------------------------------------------------- #
def test_body_demasiado_grande_413(client):
    """Un cuerpo por encima de 1 MB se rechaza con 413 (CDG) sin procesarse."""
    grande = "x" * 1_000_001
    r = client.post(ENDPOINT, json={"consultas": [{"consulta": "CANAL", "valor": grande}]})
    assert r.status_code == 413
    body = r.json()
    assert set(body) == ERROR_KEYS
    assert body["status"] == 413
    assert body["errorCode"] == "CDG"
    assert body["errorLabel"] == "Carga Demasiado Grande"
    assert body["method"] == "POST"
    assert r.headers["content-type"].startswith("application/problem+json")
