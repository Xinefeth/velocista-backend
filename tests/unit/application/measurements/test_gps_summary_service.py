"""CU-4: the GPS summary re-analyses stored trials and takes its limits from the configuration."""

from dataclasses import dataclass, field, replace

from support.measurement_fixtures import still_fixes
from velocista.application.measurements.use_cases import GpsErrorService
from velocista.domain.measurements.entities import GpsTrial
from velocista.domain.measurements.gps import trial_errors
from velocista.domain.measurements.gps_analysis import GpsConfig


@dataclass
class TrialsRepository:
    trials: list = field(default_factory=list)

    def list_gps_trials(self, device_id=None):
        return self.trials

    def add_gps_trial(self, trial):
        stored = replace(trial, id=len(self.trials) + 1)
        self.trials.append(stored)
        return stored


def legacy_trial(env="open", sigma=3.0, seed=1) -> GpsTrial:
    """Prueba guardada antes de CU-4: el resultado solo tiene lo de SP-06."""
    start = tuple(still_fixes(0, 0, n=20, sigma=sigma, seed=seed))
    end = tuple(still_fixes(40, 0, n=20, sigma=sigma, seed=seed + 100))
    return GpsTrial(
        "phone", "lugar", env, 40.0, start, end, result=trial_errors(start, end, 40.0), id=seed
    )


def test_legacy_trials_get_the_new_analysis():
    repo = TrialsRepository([legacy_trial(seed=s) for s in range(1, 6)])
    assert "by_wait" not in repo.trials[0].result
    summary = GpsErrorService(repo).summary()
    assert summary["environments"]["open"]["enough_data"] is True
    assert [w["usable_trials"] for w in summary["by_wait"]] == [5, 5, 5]
    assert summary["trials"] == 5 and summary["min_side_m"] > 0


def test_defaults_come_from_the_configuration_and_the_query_overrides_them():
    repo = TrialsRepository([legacy_trial(seed=s) for s in range(1, 4)])
    service = GpsErrorService(repo, GpsConfig(target_pct=5, min_trials=3))
    assert service.summary()["config"]["min_trials"] == 3
    assert service.summary()["conclusion"]["code"] == "ok"
    strict = service.summary(target_pct=20, min_trials=10)
    assert strict["config"]["target_pct"] == 20 and strict["config"]["min_trials"] == 10
    assert strict["conclusion"]["code"] == "insufficient_data"


def test_new_trial_is_stored_with_wait_and_accuracy_analysis():
    repo = TrialsRepository()
    trial = legacy_trial()
    stored = GpsErrorService(repo).add_trial(replace(trial, result=None, id=None))
    assert {"methods", "by_wait", "by_accuracy"} <= set(stored.result)
