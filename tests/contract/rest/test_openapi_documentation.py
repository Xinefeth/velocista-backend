"""Contract: every endpoint is documented in Swagger (summary, description, errors) in English."""

import re

import pytest

from velocista.main import create_app

SPANISH_CHARS = re.compile(r"[áéíóúñ¿¡Á-ÚÑ]")
# Operations that cannot fail with a business error (read-only catalogs, log append)
NO_ERRORS_EXPECTED = {
    "listComponentTypes",
    "listComponents",
    "listInventory",
    "listRobots",
    "listSlots",
    "listControllers",
    "listReconciledControllers",
    "listProfiles",
    "listRuns",
    "listEvents",
    "createEvent",
    "createComponent",  # only fails with 422 (documented in its description)
}


@pytest.fixture(scope="module")
def spec():
    return create_app().openapi()


@pytest.fixture(scope="module")
def operations(spec):
    return [
        (path, method, op) for path, item in spec["paths"].items() for method, op in item.items()
    ]


def test_api_has_title_description_and_tags(spec):
    assert len(spec["info"]["description"]) > 100
    assert {t["name"] for t in spec["tags"]} >= {
        "health",
        "auth",
        "catalog",
        "builder",
        "optimization",
        "runs",
        "rules",
        "events",
        "control",
        "devices",
    }
    assert all(t.get("description") for t in spec["tags"])


def test_every_operation_has_summary_and_description(operations):
    missing = [
        op["operationId"]
        for _, _, op in operations
        if not op.get("summary")
        or op["summary"] == op["operationId"]
        or len(op.get("description", "")) < 30
    ]
    assert missing == []


def test_documentation_text_is_english(operations):
    offenders = [
        op["operationId"]
        for _, _, op in operations
        if SPANISH_CHARS.search(op.get("summary", "") + op.get("description", ""))
    ]
    assert offenders == []


def test_operations_that_can_fail_document_their_errors(operations):
    undocumented = []
    for _, _, op in operations:
        if op["operationId"] in NO_ERRORS_EXPECTED:
            continue
        errors = [code for code in op["responses"] if code.startswith(("4", "5")) and code != "422"]
        if not errors:
            undocumented.append(op["operationId"])
    assert undocumented == []


def test_business_errors_reference_the_standard_error_model(spec):
    response = spec["paths"]["/api/robots/{robot_id}"]["get"]["responses"]["404"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith("/BusinessError")
