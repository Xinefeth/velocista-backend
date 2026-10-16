"""Bootstrap de esquema para DESARROLLO local (no para producción; en pista se usa Alembic).

`create_all()` crea las tablas del metadata contra la BD configurada. Útil para levantar rápido
en local sin migraciones. Importa el agregador de modelos para registrar todas las tablas.
"""

from __future__ import annotations

import velocista.infrastructure.persistence.models  # noqa: F401  (registra las tablas)
from velocista.infrastructure.persistence.db import Base, engine


def create_all() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_all()
    print("Esquema creado (create_all).")
