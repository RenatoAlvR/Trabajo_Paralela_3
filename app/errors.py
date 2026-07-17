"""Formato de errores estándar (Problem Detail, RFC 7807/9457) del enunciado."""
from datetime import datetime, timezone

from fastapi.responses import JSONResponse

# Media type estándar para Problem Detail (RFC 9457).
PROBLEM_JSON = "application/problem+json"

_STATUS_TYPE = "https://developer.mozilla.org/es/docs/Web/HTTP/Reference/Status/{}"


class ApiError(Exception):
    """Excepción de dominio que se traduce al cuerpo de error estándar."""

    def __init__(self, status, detail, title, error_code, error_label):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.title = title
        self.error_code = error_code
        self.error_label = error_label


def _now_iso():
    # Formato del enunciado: 2026-06-30T20:44:49.201437123Z (9 dígitos
    # fraccionarios). Python resuelve hasta microsegundos; se completa a
    # nanosegundos para calzar con el formato del ejemplo.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "000Z"


def error_body(status, detail, title, error_code, error_label, method, instance):
    return {
        "detail": detail,
        "instance": instance,
        "status": status,
        "title": title,
        "type": _STATUS_TYPE.format(status),
        "timestamp": _now_iso(),
        "errorCode": error_code,
        "errorLabel": error_label,
        "method": method,
    }


def problem_response(err, method, instance):
    """Respuesta HTTP de error como Problem Detail (RFC 9457): el cuerpo estándar
    del enunciado servido con el media type `application/problem+json`. Centraliza
    la construcción usada por todos los manejadores de excepciones. `instance` es
    la ruta real de la petición (`request.url.path`), no un valor fijo."""
    return JSONResponse(
        status_code=err.status,
        media_type=PROBLEM_JSON,
        content=error_body(
            err.status, err.detail, err.title, err.error_code, err.error_label, method, instance
        ),
    )


def validation_error(detail):
    """400 Bad Request - Validación Fallida (VF)."""
    return ApiError(400, detail, "Bad Request", "VF", "Validación Fallida")


def internal_error(detail):
    """500 Internal Server Error - Error Interno (IE)."""
    return ApiError(500, detail, "Internal Server Error", "IE", "Error Interno")


def service_unavailable(detail):
    """503 Service Unavailable - Servicio No Disponible (SND).

    Se usa cuando llega una petición pero los datos aún no están disponibles en
    memoria (p. ej. una consulta durante el arranque, antes de que termine la
    carga desatendida del CSV)."""
    return ApiError(503, detail, "Service Unavailable", "SND", "Servicio No Disponible")


# Catálogo status HTTP -> (title, errorCode, errorLabel). Cubre los casos del
# manejador de referencia del profesor (400/404/405/415/500) y añade tres
# propios (406/413/503). Cualquier status no listado usa la entrada por defecto.
_CATALOGO = {
    400: ("Bad Request", "VF", "Validación Fallida"),
    404: ("Not Found", "RNE", "Recurso No Encontrado"),
    405: ("Method Not Allowed", "MNP", "Método No Permitido"),
    406: ("Not Acceptable", "NA", "No Aceptable"),
    413: ("Payload Too Large", "CDG", "Carga Demasiado Grande"),
    415: ("Unsupported Media Type", "TNS", "Tipo de Contenido No Soportado"),
    500: ("Internal Server Error", "IE", "Error Interno"),
    503: ("Service Unavailable", "SND", "Servicio No Disponible"),
}
_DEFAULT = ("Error", "DC", "Error Desconocido")

_DETALLE_DEFECTO = {
    404: "El recurso solicitado no existe",
    405: "El método HTTP no está permitido en este recurso",
    406: "No se puede satisfacer el tipo de contenido solicitado (cabecera Accept)",
    413: "El cuerpo de la solicitud excede el tamaño permitido",
    415: "El tipo de contenido (Content-Type) no es soportado",
}


def from_status(status, detail=None):
    """Construye un ApiError con title/errorCode/errorLabel a partir del status
    HTTP. Permite reformatear cualquier error del framework (404/405/415/...) al
    formato estándar del enunciado."""
    title, code, label = _CATALOGO.get(status, _DEFAULT)
    if not detail:
        detail = _DETALLE_DEFECTO.get(status, title)
    return ApiError(status, detail, title, code, label)
