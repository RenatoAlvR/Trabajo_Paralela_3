"""Formato de errores estándar (estilo RFC 7807) exigido por el enunciado."""
from datetime import datetime, timezone

from . import config

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
    # Formato: 2026-06-30T20:44:49.201437Z
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def error_body(status, detail, title, error_code, error_label, method):
    return {
        "detail": detail,
        "instance": config.API_BASE,
        "status": status,
        "title": title,
        "type": _STATUS_TYPE.format(status),
        "timestamp": _now_iso(),
        "errorCode": error_code,
        "errorLabel": error_label,
        "method": method,
    }


def validation_error(detail):
    """400 Bad Request - Validación Fallida (VF)."""
    return ApiError(400, detail, "Bad Request", "VF", "Validación Fallida")


def internal_error(detail):
    """500 Internal Server Error - Error Interno (IE)."""
    return ApiError(500, detail, "Internal Server Error", "IE", "Error Interno")
