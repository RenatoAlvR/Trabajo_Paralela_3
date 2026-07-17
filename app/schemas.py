"""Modelos Pydantic de solicitud/respuesta (documentados en Swagger)."""
from typing import List, Optional

from pydantic import BaseModel, Field


class Consulta(BaseModel):
    consulta: str = Field(..., examples=["CANAL"], description="Nombre del filtro")
    valor: str = Field(..., examples=["POS"], description="Valor a filtrar")


class PostBody(BaseModel):
    consultas: Optional[List[Consulta]] = Field(
        default=None,
        description="Lista de filtros a aplicar. No puede ser nula ni vacía.",
        examples=[[{"consulta": "GENERO", "valor": "Femenino"}, {"consulta": "CANAL", "valor": "POS"}]],
    )


class Resumen(BaseModel):
    suma: float
    conteo: int
    promedio: Optional[float]
    minimo: Optional[float]
    maximo: Optional[float]
    mediana: Optional[float]
    desviacion_estandar: Optional[float]


class ErrorEstandar(BaseModel):
    """Formato de error estándar del enunciado (Problem Detail extendido)."""

    detail: str = Field(..., examples=["El valor 'qwerqwer' no es un número entero válido para LOCAL"])
    instance: str = Field(..., examples=["/v1/estadisticas/ventas"])
    status: int = Field(..., examples=[400])
    title: str = Field(..., examples=["Bad Request"])
    type: str = Field(..., examples=["https://developer.mozilla.org/es/docs/Web/HTTP/Reference/Status/400"])
    timestamp: str = Field(..., examples=["2026-06-30T20:44:49.201437123Z"])
    errorCode: str = Field(..., examples=["VF"])
    errorLabel: str = Field(..., examples=["Validación Fallida"])
    method: str = Field(..., examples=["POST"])
