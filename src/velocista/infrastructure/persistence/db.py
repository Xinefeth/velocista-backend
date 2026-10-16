"""Acceso a datos: motor, sesiones y base declarativa.

Única capa que conoce SQLAlchemy. Los modelos ORM de cada contexto heredan de `Base`.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from velocista.infrastructure.config.settings import settings

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base de todos los modelos ORM. Cada contexto define sus tablas en su propio models/."""


def get_session() -> Iterator[Session]:
    """Una sesión por petición. Si algo falla se deshace la transacción; siempre se cierra."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
