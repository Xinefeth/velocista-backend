"""Unit: domain errors carry a stable reason and know nothing about HTTP."""

import pytest

from velocista.domain.shared.errors import Conflict, DomainError, Forbidden, NotFound, Validation


@pytest.mark.parametrize("error_type", [NotFound, Conflict, Validation, Forbidden])
def test_domain_error_keeps_reason_and_detail(error_type):
    error = error_type("some_reason", "Readable detail")
    assert isinstance(error, DomainError)
    assert (error.reason, error.detail) == ("some_reason", "Readable detail")
    assert str(error) == "Readable detail"
