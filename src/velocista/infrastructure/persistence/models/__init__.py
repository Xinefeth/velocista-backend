"""Agrega todos los modelos ORM para que `Base.metadata` conozca todas las tablas.

Importar este paquete registra las tablas (necesario para Alembic autogenerate y create_all).
A medida que se portan más contextos (runs, optimization, rules, auth), se añaden aquí.
"""

from velocista.infrastructure.persistence.models import (
    optimization,  # noqa: F401
    rules,  # noqa: F401
    runs,  # noqa: F401
)
from velocista.infrastructure.persistence.models.builder import (  # noqa: F401
    RobotModel,
    SlotModel,
    VersionModel,
    VersionPartModel,
)
from velocista.infrastructure.persistence.models.catalog import (  # noqa: F401
    ComponentModel,
    ComponentTypeModel,
    InventoryModel,
)
from velocista.infrastructure.persistence.models.config import RobotConfigModel  # noqa: F401
from velocista.infrastructure.persistence.models.event import EventModel  # noqa: F401
