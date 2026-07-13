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
