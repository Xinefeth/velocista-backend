"""Unit: mapping of domain error TYPE to HTTP status (interface layer rule)."""

import pytest

from velocista.domain.shared.errors import (
    Conflict,
    DeviceUnavailable,
    DomainError,
    Forbidden,
    NotFound,
    Validation,
)
from velocista.interface.rest.errors import _status_for


@pytest.mark.parametrize(
    "error_type,status",
    [
        (NotFound, 404),
        (Conflict, 409),
        (Validation, 422),
        (Forbidden, 403),
        (DeviceUnavailable, 503),
        (DomainError, 400),
    ],
)
def test_status_for_maps_each_error_type(error_type, status):
    assert _status_for(error_type("r", "d")) == status
