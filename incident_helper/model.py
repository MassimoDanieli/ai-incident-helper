"""Data model for an incident."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Phases a timeline event can belong to. Order matters only for display.
PHASES = [
    "impact_start",  # first sign of user impact
    "detection",  # alert fired, page sent, someone noticed
    "investigation",  # diagnosis, hypotheses, checking logs
    "mitigation_action",  # rollback, failover, restart, scale-up started
    "mitigated",  # impact reduced / stopped
    "resolved",  # back to normal
    "communication",  # status updates, customer comms
    "other",
]


@dataclass
class TimelineEvent:
    time: datetime
    text: str
    phase: str = "other"
    phase_source: str = "heuristic"  # heuristic | ai | manual


@dataclass
class LogLine:
    time: datetime | None
    raw: str


@dataclass
class MetricPoint:
    time: datetime
    value: float


@dataclass
class MetricSeries:
    name: str
    unit: str
    points: list[MetricPoint]


@dataclass
class Message:
    time: str
    user: str
    text: str


@dataclass
class Incident:
    incident_id: str
    start_time: datetime
    end_time: datetime
    title: str = ""
    severity: str = ""
    services: list[str] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    logs: list[LogLine] = field(default_factory=list)
    metrics: list[MetricSeries] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    comms_platform: str = ""
    notes: str = ""

    def first(self, *phases: str) -> TimelineEvent | None:
        for ev in self.timeline:
            if ev.phase in phases:
                return ev
        return None


@dataclass
class Metrics:
    """Durations measured from ``start_time`` (impact start).

    TTD  time to detect      -> first detection event
    TTA  time to act         -> first mitigation action
    TTM  time to mitigate    -> impact reduced (falls back to resolution)
    TTR  time to resolve     -> end_time
    None means the timeline does not say; never a fake zero.
    """

    ttd: timedelta | None
    tta: timedelta | None
    ttm: timedelta | None
    ttr: timedelta

    def minutes(self) -> dict[str, float | None]:
        return {k: (round(v.total_seconds() / 60, 1) if v is not None else None) for k, v in self.__dict__.items()}
