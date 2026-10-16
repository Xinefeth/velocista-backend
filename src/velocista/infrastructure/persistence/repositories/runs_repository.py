"""Implementación SQLAlchemy del port `RunRepository`.

Vive en `infrastructure`: es el único sitio que conoce el ORM. Traduce entre modelos
ORM (persistencia) y entidades de dominio.

NOTA: esqueleto de referencia. Falta el modelo ORM (`infrastructure/persistence/models/`)
y el mapeo fila→entidad; se completa al cablear la base de datos.
"""

from __future__ import annotations

from velocista.application.runs.ports import RunRepository
from velocista.domain.runs.entities import Run


class SqlAlchemyRunRepository(RunRepository):
    """Repositorio de corridas sobre SQLAlchemy."""

    def __init__(self, session) -> None:  # tipado: sqlalchemy.orm.Session
        self._session = session

    def get(self, run_id: int) -> Run | None:
        # TODO: consultar el modelo ORM y mapear a la entidad Run.
        raise NotImplementedError

    def list(self, *, limit: int, offset: int) -> tuple[list[Run], int]:
        # TODO: SELECT paginado + COUNT.
        raise NotImplementedError

    def save(self, run: Run) -> Run:
        # TODO: upsert del modelo ORM a partir de la entidad.
        raise NotImplementedError
