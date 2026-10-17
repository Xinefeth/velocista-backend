from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class RunNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(max_length=1000)


class SegmentOut(BaseModel):
    type: str
    duration_s: float
    angle_degrees: float
    accumulated_error: float | None


class LapOut(BaseModel):
    id: int
    run_id: int
    number: int
    time_s: float | None
    duration_s: float
    internal_time_ms: int | None
    accumulated_error: float | None
    lost_lines: int | None
    battery_v: float | None
    finished: bool
    time_source: Literal["finish", "telemetry"] | None
    reason: str
    sectors_s: list[float]
    segments: list[SegmentOut]


class RunOut(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: int
    number: int
    robot_id: str
    version_id: int
    setup_id: int
    profile_id: str
    controller_id: str
    parameters: dict[str, float]
    date: datetime
    source: Literal["sim", "robot"]
    mode: Literal["test", "competition"] | None
    line: Literal["black", "white"] | None
    battery_compensation: bool | None
    turbine_power_pct: float | None
    time_s: float | None
    finished: bool
    accumulated_error: float | None
    battery_v: float | None
    sectors_s: list[float]
    time_source: Literal["finish", "telemetry"] | None
    external_session_id: str | None = None
    external_run_id: str | None = None
    closure_status: str | None = None
    summary: dict | None = None
    config_changed: bool = False
    optimization_eligible: bool = False
    note: str
    j: float | None


class RunsPage(BaseModel):
    items: list[RunOut]
    total: int
    limit: int
    offset: int


class LapsPage(BaseModel):
    items: list[LapOut]
    total: int
    limit: int
    offset: int


class IngestSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    type: str = Field(min_length=1, max_length=30)
    duration_s: float = Field(ge=0)
    angle_degrees: float
    accumulated_error: float = Field(ge=0)


class IngestLap(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    number: int = Field(ge=1)
    time_s: float | None = Field(default=None, ge=0)
    duration_s: float = Field(ge=0)
    internal_time_ms: int | None = Field(default=None, ge=0)
    accumulated_error: float = Field(ge=0)
    lost_lines: int = Field(ge=0, validation_alias=AliasChoices("lost_lines", "lines_lost"))
    battery_v: float = Field(ge=0)
    finished: bool
    time_source: Literal["finish", "telemetry"] = "telemetry"
    reason: str = Field(default="", max_length=500)
    sectors_s: list[float] = Field(default_factory=list, max_length=64)
    segments: list[IngestSegment] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def validate_finish_time(self):
        if self.finished != (self.time_s is not None):
            raise ValueError("finished laps require time_s; unfinished laps must omit it")
        if any(value < 0 for value in self.sectors_s):
            raise ValueError("sector times must be non-negative")
        return self


class RunIngestion(BaseModel):
    """Payload sent by the simulation service after a run has finished."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    external_run_id: str = Field(min_length=1, max_length=120)
    robot_id: str = Field(min_length=1, max_length=40)
    version_id: int = Field(ge=1)
    setup_id: int = Field(ge=1)
    profile_id: str = Field(min_length=1, max_length=40)
    started_at: datetime
    finished_at: datetime
    mode: Literal["test", "competition"]
    line: Literal["black", "white"]
    battery_compensation: bool
    turbine_power_pct: float = Field(ge=0, le=100)
    laps: list[IngestLap] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_times_and_laps(self):
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("started_at and finished_at must include a timezone")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        numbers = [lap.number for lap in self.laps]
        if len(numbers) != len(set(numbers)):
            raise ValueError("lap numbers must be unique within a run")
        return self
