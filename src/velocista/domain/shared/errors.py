"""Errores de dominio. No dependen de ningún framework (ni FastAPI ni HTTP).

Cada error lleva un `reason` (código corto y estable que la consola usa para decidir el
mensaje final) y un `detail` legible. La capa `interface` mapea el TIPO de error a un
código HTTP; el dominio no conoce HTTP.
"""


class DomainError(Exception):
    """Base de todos los errores de reglas de negocio."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


class NotFound(DomainError):
    """La entidad pedida no existe. → HTTP 404."""


class Conflict(DomainError):
    """La operación choca con el estado actual. → HTTP 409."""


class Validation(DomainError):
    """Un dato rompe una invariante del dominio. → HTTP 422."""


class Forbidden(DomainError):
    """La operación no está permitida en el estado actual. → HTTP 403."""


class DeviceUnavailable(DomainError):
    pass
