"""Sequence validation; state mutates only after a complete valid message."""

from dataclasses import dataclass, field

from .contract import validate


@dataclass
class SessionState:
    hello: dict | None = None
    config: dict | None = None
    telemetry: dict | None = None
    last_ms: int = -1
    seq: int = -1
    active: str | None = None
    seen_runs: set = field(default_factory=set)
    laps: dict = field(default_factory=dict)
    lost: int = 0

    def accept(self, message):
        validate(message, self.hello)
        kind = message["type"]
        if message["t_ms"] < self.last_ms:
            raise ValueError("Session clock decreased")
        if self.hello is None and kind != "hello":
            raise ValueError("Expected hello")
        if self.hello is not None and self.config is None and kind != "config":
            raise ValueError("Expected config after hello")
        if kind == "hello":
            if self.hello is not None:
                raise ValueError("Unexpected hello; load is not supported by this integration")
            self.hello = message
        elif kind == "config":
            self.config = message
        elif kind == "telemetry":
            if message["seq"] <= self.seq:
                return False
            if message.get("run_id") != self.active:
                raise ValueError("Telemetry does not match active run")
            self.lost += message["seq"] - self.seq - 1
            self.seq = message["seq"]
            self.telemetry = message
        elif kind == "event":
            run = message["run_id"]
            event = message["event"]
            if event == "run_started":
                if run in self.seen_runs:
                    return False
                if self.active:
                    raise ValueError("Run already active")
                self.active = run
                self.seen_runs.add(run)
                self.laps = {}
            else:
                if run != self.active:
                    raise ValueError("Event does not match active run")
                if event == "lap":
                    number = message["lap"]
                    if number in self.laps:
                        if self.laps[number] != message["lap_ms"]:
                            raise ValueError("Conflicting duplicate lap")
                        return False
                    self.laps[number] = message["lap_ms"]
                if event == "run_finished":
                    self.active = None
        self.last_ms = message["t_ms"]
        return True
