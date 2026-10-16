"""DTOs de entrada/salida de los casos de uso de `runs`.

Objetos planos que viajan entre `application` e `interface`. No son entidades de dominio
ni esquemas HTTP; evitan que la capa de entrega toque las entidades directamente.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloseLapInput:
    run_id: int
    lap_number: int
    time_s: float | None
    accumulated_error: float
    time_source: str


@dataclass(frozen=True)
class Page:
    """Resultado paginado genérico (claves EN: items/total/limit/offset en la frontera)."""

    items: list
    total: int
    limit: int
    offset: int
