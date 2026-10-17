"""Integration: SQLAlchemy repositories against a real PostgreSQL (no ORM mocking)."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from velocista.domain.shared.errors import Conflict, NotFound
from velocista.infrastructure.persistence.models.builder import RobotModel
from velocista.infrastructure.persistence.models.runs import RunModel
from velocista.infrastructure.persistence.repositories.optimization_repository import (
    SqlAlchemyOptimizationRepository,
)
from velocista.infrastructure.persistence.repositories.run_history_repository import (
    SqlAlchemyRunHistoryRepository,
)


@pytest.fixture
def session(db):
    with Session(bind=db, join_transaction_mode="create_savepoint") as session:
        yield session


def add_robot(session, robot_id="r1", short_code="R1"):
    session.add(
        RobotModel(id=robot_id, name="Robot", short_code=short_code, type="racer", firmware="1")
    )
    session.flush()


class TestRobotConstraints:
    def test_short_code_is_unique_at_database_level(self, session):
        add_robot(session, "r1", "SAME")
        session.add(RobotModel(id="r2", name="Other", short_code="SAME", type="racer"))
        with pytest.raises(IntegrityError):
            session.flush()


class TestOptimizationRepository:
    def test_list_setups_when_robot_missing_raises_not_found(self, session):
        with pytest.raises(NotFound):
            SqlAlchemyOptimizationRepository(session).list_setups("ghost", 10, 0)

    def test_get_controller_returns_seeded_parameters(self, session):
        controller = SqlAlchemyOptimizationRepository(session).get_controller("pid")
        assert {p["key"] for p in controller["parameters"]} == {"kp", "kd"}

    def test_get_controller_when_missing_returns_none(self, session):
        assert SqlAlchemyOptimizationRepository(session).get_controller("x") is None


class TestRunHistoryRepository:
    def test_get_run_when_missing_returns_none(self, session):
        assert SqlAlchemyRunHistoryRepository(session).get_run(999999) is None

    def test_list_runs_when_database_has_no_closed_runs_is_empty(self, session):
        page = SqlAlchemyRunHistoryRepository(session).list_runs()
        assert page["total"] == 0 and page["items"] == []

    def test_simulate_when_robot_has_no_current_version_raises_conflict(self, session):
        add_robot(session)
        with pytest.raises(Conflict) as error:
            SqlAlchemyRunHistoryRepository(session).simulate("r1")
        assert error.value.reason == "no_current_version"

    def test_simulated_runs_are_persisted_as_closed(self, client, build, db):
        robot_id, _, _ = build.robot_ready()
        client.post(f"/api/runs/simulated?robot_id={robot_id}")
        with Session(bind=db, join_transaction_mode="create_savepoint") as session:
            runs = session.scalars(select(RunModel)).all()
        assert len(runs) == 1 and runs[0].closed_at is not None and runs[0].source == "sim"
