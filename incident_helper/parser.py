"""YAML incident files -> :class:`Incident`.

Accepted timeline formats (mixable):
    - "14:05 Alert fired"                       time on the incident's start day
    - "2025-04-01T14:05:00Z Alert fired"        full timestamp
    - {time: "14:05", text: "Alert fired", phase: detection}
Times earlier than the previous event are assumed to be past midnight.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .model import PHASES, Incident, LogLine, Message, MetricPoint, MetricSeries, TimelineEvent


class IncidentParseError(ValueError):
    pass


_HHMM = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.*)$", re.DOTALL)
_ISO_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)\s+(.*)$", re.DOTALL)


def parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time())
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise IncidentParseError(f"not a timestamp: {value!r}") from exc
    else:
        raise IncidentParseError(f"not a timestamp: {value!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _clock(day: datetime, hh: str, mm: str, ss: str | None) -> datetime:
    return day.replace(hour=int(hh), minute=int(mm), second=int(ss or 0), microsecond=0)


def parse_timeline(items: list[Any], start: datetime) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    day = start
    previous: datetime | None = None
    for raw in items or []:
        phase, source = "other", "heuristic"
        clock_only = False
        if isinstance(raw, dict):
            text = str(raw.get("text") or raw.get("event") or "").strip()
            when = raw.get("time")
            if raw.get("phase"):
                if raw["phase"] not in PHASES:
                    raise IncidentParseError(f"unknown phase {raw['phase']!r}; use one of {PHASES}")
                phase, source = raw["phase"], "manual"
            m = _HHMM.match(f"{when} x") if isinstance(when, str) else None
            if m:
                ts, clock_only = _clock(day, m.group(1), m.group(2), m.group(3)), True
            else:
                ts = parse_dt(when)
        else:
            line = str(raw).strip()
            if m := _ISO_PREFIX.match(line):
                ts, text = parse_dt(m.group(1)), m.group(2).strip()
            elif m := _HHMM.match(line):
                ts, text = _clock(day, m.group(1), m.group(2), m.group(3)), m.group(4).strip()
                clock_only = True
            else:
                raise IncidentParseError(f"timeline entry without a time: {line!r}")
        if clock_only and previous is not None and (previous - ts) > timedelta(hours=6):
            ts += timedelta(days=1)  # "23:50 ... 00:10": crossed midnight
            day = ts
        events.append(TimelineEvent(ts, text, phase, source))
        previous = ts
    return events


def parse_logs(items: list[Any]) -> list[LogLine]:
    out = []
    for raw in items or []:
        line = str(raw).strip()
        m = _ISO_PREFIX.match(line)
        out.append(LogLine(parse_dt(m.group(1)) if m else None, line))
    return out


def parse_metrics(block: dict[str, Any] | None) -> list[MetricSeries]:
    out = []
    for name, spec in (block or {}).items():
        points = [MetricPoint(parse_dt(v["timestamp"]), float(v["value"])) for v in spec.get("values", [])]
        out.append(MetricSeries(name, str(spec.get("unit", "")), sorted(points, key=lambda p: p.time)))
    return out


def from_dict(data: dict[str, Any]) -> Incident:
    if not isinstance(data, dict):
        raise IncidentParseError("incident file must be a YAML mapping")
    for key in ("incident_id", "start_time", "end_time"):
        if key not in data:
            raise IncidentParseError(f"missing required field {key!r}")
    start, end = parse_dt(data["start_time"]), parse_dt(data["end_time"])
    if end < start:
        raise IncidentParseError("end_time is before start_time")
    comms = data.get("team_comms") or {}
    return Incident(
        incident_id=str(data["incident_id"]),
        start_time=start,
        end_time=end,
        title=str(data.get("title", "")),
        severity=str(data.get("severity", "")),
        services=[str(s) for s in data.get("services", [])],
        timeline=parse_timeline(data.get("timeline", []), start),
        logs=parse_logs(data.get("logs", [])),
        metrics=parse_metrics(data.get("metrics")),
        messages=[
            Message(str(m.get("time", "")), str(m.get("user", "")), str(m.get("message", m.get("text", ""))))
            for m in comms.get("messages", [])
        ],
        comms_platform=str(comms.get("platform", "")),
        notes=str(data.get("notes", "")),
    )


def load(source: str | Path | bytes) -> Incident:
    """Load from a path, or from YAML bytes/text (e.g. a Streamlit upload)."""
    if isinstance(source, bytes):
        text = source.decode("utf-8")
    elif isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).exists()):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = str(source)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise IncidentParseError(f"invalid YAML: {exc}") from exc
    return from_dict(data)


def to_dict(inc: Incident) -> dict[str, Any]:
    """Inverse of :func:`from_dict` (used by the extractor to write YAML)."""

    def iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    data: dict[str, Any] = {"incident_id": inc.incident_id}
    if inc.title:
        data["title"] = inc.title
    if inc.severity:
        data["severity"] = inc.severity
    data["start_time"] = iso(inc.start_time)
    data["end_time"] = iso(inc.end_time)
    if inc.services:
        data["services"] = inc.services
    data["timeline"] = [
        {"time": iso(e.time), "text": e.text, **({"phase": e.phase} if e.phase_source != "heuristic" else {})} for e in inc.timeline
    ]
    if inc.logs:
        data["logs"] = [log.raw for log in inc.logs]
    if inc.messages:
        data["team_comms"] = {
            "platform": inc.comms_platform or "chat",
            "messages": [{"time": m.time, "user": m.user, "message": m.text} for m in inc.messages],
        }
    if inc.notes:
        data["notes"] = inc.notes
    return data
