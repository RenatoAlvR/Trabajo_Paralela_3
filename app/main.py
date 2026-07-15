"""Servicio ReST - Resumen estadístico de ventas (Cruz Morada).

Endpoints:
    GET  /v1/estadisticas/ventas   -> estadísticas con filtros por query params.
    POST /v1/estadisticas/ventas   -> estadísticas con filtros en el body.
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .errors import (
    ApiError,
    error_body,
    from_status,
    internal_error,
    service_unavailable,
    validation_error,
)
from .filters import FilterError, UnknownFilter, build_predicate
from .loader import store
from .schemas import PostBody, Resumen
from .stats import compute_stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carga desatendida: el CSV se procesa al iniciar la aplicación.
    store.load(config.CSV_PATH)
    # Métricas precomputadas: el resumen global (sin filtros) se calcula UNA
    # sola vez al arranque y se guarda en memoria, de modo que un GET sin
    # filtros lo devuelve al instante sin recorrer los 3,2M de registros.
    store.resumen_global = compute_stats(store.df, config.METRIC_COLUMN, [])
    yield


app = FastAPI(
    title="Cruz Morada - Servicio ReST de Resumen Estadístico",
    version="1.0.0",
    description="Resumen estadístico de ventas con procesamiento paralelo (Polars).",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Manejadores de errores (formato estándar del enunciado)
# --------------------------------------------------------------------------- #
@app.exception_handler(ApiError)
async def _api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status,
        content=error_body(exc.status, exc.detail, exc.title, exc.error_code, exc.error_label, request.method),
    )


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(request: Request, exc: RequestValidationError):
    err = validation_error("El cuerpo de la solicitud no tiene un formato válido")
    return JSONResponse(
        status_code=err.status,
        content=error_body(err.status, err.detail, err.title, err.error_code, err.error_label, request.method),
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Reformatea los errores HTTP que emite el framework (404 ruta inexistente,
    # 405 método no permitido, 415 media type no soportado, etc.) al formato
    # estándar del enunciado, en lugar del JSON por defecto de FastAPI.
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail.strip() else None
    err = from_status(exc.status_code, detail)
    return JSONResponse(
        status_code=err.status,
        content=error_body(err.status, err.detail, err.title, err.error_code, err.error_label, request.method),
    )


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    err = internal_error(f"Error interno inesperado: {exc}")
    return JSONResponse(
        status_code=err.status,
        content=error_body(err.status, err.detail, err.title, err.error_code, err.error_label, request.method),
    )


# --------------------------------------------------------------------------- #
# Lógica compartida
# --------------------------------------------------------------------------- #
def _make_predicates(items):
    preds = []
    for consulta, valor in items:
        try:
            preds.append(build_predicate(consulta, valor))
        except UnknownFilter:
            raise validation_error(f"La consulta '{consulta}' no es un filtro soportado")
        except FilterError as e:
            raise validation_error(str(e))
    return preds


def _run(predicates):
    if not store.loaded or store.df is None:
        raise service_unavailable(
            "Los datos aún no están disponibles; el servicio está cargando el CSV"
        )
    try:
        return compute_stats(store.df, config.METRIC_COLUMN, predicates)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise internal_error(f"Error al calcular las estadísticas: {e}")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
async def root():
    """La raíz redirige a la documentación interactiva (Swagger UI)."""
    return RedirectResponse(url="/docs")


@app.get(config.API_BASE, response_model=Resumen)
async def get_estadisticas(
    GENERO: Optional[str] = None,
    EDAD: Optional[str] = None,
    CANAL: Optional[str] = None,
    CODIGO_PRODUCTO: Optional[str] = None,
    ID_PERSONA: Optional[str] = None,
    LOCAL: Optional[str] = None,
    FECHA_DESDE: Optional[str] = None,
    FECHA_HASTA: Optional[str] = None,
):
    provided = {
        "GENERO": GENERO,
        "EDAD": EDAD,
        "CANAL": CANAL,
        "CODIGO_PRODUCTO": CODIGO_PRODUCTO,
        "ID_PERSONA": ID_PERSONA,
        "LOCAL": LOCAL,
        "FECHA_DESDE": FECHA_DESDE,
        "FECHA_HASTA": FECHA_HASTA,
    }
    items = [(k, v) for k, v in provided.items() if v is not None]
    if not items:
        # GET sin filtros -> métricas PRECOMPUTADAS al arranque (acceso
        # inmediato, sin recorrer los 3,2M de registros). Cumple el objetivo 1a.
        if store.resumen_global is None:
            raise service_unavailable("Las métricas precomputadas aún no están disponibles")
        return store.resumen_global
    return _run(_make_predicates(items))


@app.post(config.API_BASE, response_model=Resumen)
async def post_estadisticas(body: PostBody):
    if not body.consultas:
        raise validation_error("El campo 'consultas' no puede estar vacío o nulo")
    items = [(c.consulta, c.valor) for c in body.consultas]
    return _run(_make_predicates(items))
