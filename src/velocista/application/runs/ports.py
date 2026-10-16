"""Ports (interfaces) del contexto `runs`.

La capa `application` declara QUÉ necesita del exterior; `infrastructure` lo implementa.
Así el caso de uso no conoce SQLAlchemy ni la base de datos.
"""

from __future__ import annotations

from typing import Protocol

from velocista.domain.runs.entities import Run


class RunRepository(Protocol):
    """Puerto de persistencia de corridas."""

    def get(self, run_id: int) -> Run | None: ...

    def list(self, *, limit: int, offset: int) -> tuple[list[Run], int]:
        """Devuelve (items, total) para paginar."""
        ...

    def save(self, run: Run) -> Run: ...
