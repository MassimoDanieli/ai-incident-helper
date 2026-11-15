"""Turn raw material (chat export, notes, log excerpts) into an incident file.

In v1 you had to write the YAML by hand. Here the model reads whatever you
have and drafts it; you review the YAML before analysing it.
"""

from __future__ import annotations

from typing import Any

import yaml

from .llm import strict_object
from .model import PHASES, Incident, Message, TimelineEvent
from .parser import from_dict, parse_dt, parse_logs, to_dict

MAX_INPUT_CHARS = 120_000

SCHEMA = strict_object(
    {
        "incident_id": {"type": "string", "description": "Use an id found in the text; otherwise INC-YYYY-MM-DD."},
        "title": {"type": "string"},
        "severity": {"type": "string", "description": "As stated in the text (e.g. SEV2, P1); empty if not stated."},
        "services": {"type": "array", "items": {"type": "string"}},
        "start_time": {"type": "string", "description": "ISO 8601 with timezone: first sign of impact."},
        "end_time": {"type": "string", "description": "ISO 8601 with timezone: service fully restored."},
        "timeline": {
            "type": "array",
            "items": strict_object(
                {
                    "time": {"type": "string", "description": "ISO 8601 with timezone."},
                    "text": {"type": "string"},
                    "phase": {"type": "string", "enum": PHASES},
                }
            ),
        },
        "log_lines": {"type": "array", "items": {"type": "string"}, "description": "Relevant log lines copied verbatim."},
        "messages": {
            "type": "array",
            "items": strict_object({"time": {"type": "string"}, "user": {"type": "string"}, "text": {"type": "string"}}),
        },
        "notes": {"type": "string", "description": "Anything relevant that does not fit elsewhere; mark uncertain inferences."},
    }
)

SYSTEM = """You turn raw incident material into a structured incident record.
Extract only what the text supports. Timestamps: use the dates and timezone
in the text; if only times are given, use the date of the incident and UTC
unless another timezone is stated, and say so in notes. Keep 5-25 timeline
events: the ones that matter for detection, diagnosis, mitigation and
recovery. Copy log lines verbatim. Keep people's names as written in chat
messages, but do not add names anywhere else."""


def extract(raw_text: str, client: Any, hint_date: str = "") -> dict[str, Any]:
    text = raw_text[:MAX_INPUT_CHARS]
    hint = f"Incident date if not in the text: {hint_date}\n\n" if hint_date else ""
    return client.complete(SYSTEM, f"{hint}Raw material:\n\n{text}", schema=SCHEMA, schema_name="incident_record")


def to_incident(result: dict[str, Any]) -> Incident:
    base = from_dict(
        {
            "incident_id": result["incident_id"],
            "start_time": result["start_time"],
            "end_time": result["end_time"],
            "title": result["title"],
            "severity": result["severity"],
            "services": result["services"],
            "notes": result["notes"],
        }
    )
    base.timeline = sorted(
        (TimelineEvent(parse_dt(e["time"]), e["text"], e["phase"], "ai") for e in result["timeline"]),
        key=lambda e: e.time,
    )
    base.logs = parse_logs(result["log_lines"])
    base.messages = [Message(m["time"], m["user"], m["text"]) for m in result["messages"]]
    return base


def to_yaml(inc: Incident) -> str:
    return yaml.safe_dump(to_dict(inc), sort_keys=False, allow_unicode=True, width=120)
