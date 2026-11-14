"""Assign a phase to each timeline event, then compute TTD / TTA / TTM / TTR.

Two strategies:
- ``heuristic``: keyword rules (works offline; this is what v1 did, improved);
- ``ai``: the model reads the whole timeline, logs and chat and labels each
  event. It understands "DBA: primary node crash confirmed" is investigation,
  not detection, and "auto-remediation triggered" is a mitigation action.

Phases set by hand in the YAML (``phase:``) are never overwritten.
"""

from __future__ import annotations

import re

from .llm import AIClient, strict_object
from .model import PHASES, Incident, Metrics

_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "resolved",
        re.compile(r"\b(resolved|stabili[sz]ed|recovered|restored|back to normal|returned to (normal|baseline)|all clear)\b", re.I),
    ),
    (
        "mitigated",
        re.compile(r"\b(failover .*completed|mitigated|impact (stopped|reduced)|pods? restarted successfully|rollback completed)\b", re.I),
    ),
    (
        "mitigation_action",
        re.compile(
            r"\b(rollback|roll back|rolled back|failover|fail over|restart|remediation|scale[- ]?up|scaled|hotfix|"
            r"feature flag|disable[d]?|drain|reroute|revert)\b",
            re.I,
        ),
    ),
    ("detection", re.compile(r"\b(alert|alarm|paged?|on-?call|pagerduty|opsgenie|detected|noticed|reported by)\b", re.I)),
    ("communication", re.compile(r"\b(status ?page|customers? (notified|informed)|announce|comms?)\b", re.I)),
    ("investigation", re.compile(r"\b(investigat\w*|checking|confirmed|root cause|diagnos\w*|looking into|is it)\b|^(slack|teams):", re.I)),
]


def heuristic_phase(text: str) -> str:
    for phase, rx in _RULES:
        if rx.search(text):
            return phase
    return "other"


def classify_heuristic(inc: Incident) -> Incident:
    for i, ev in enumerate(inc.timeline):
        if ev.phase_source == "manual":
            continue
        phase = heuristic_phase(ev.text)
        if i == 0 and phase == "other":
            phase = "impact_start"
        ev.phase, ev.phase_source = phase, "heuristic"
    return inc


SCHEMA = strict_object(
    {
        "events": {
            "type": "array",
            "items": strict_object(
                {
                    "index": {"type": "integer"},
                    "phase": {"type": "string", "enum": PHASES},
                }
            ),
        }
    }
)

SYSTEM = """You are an SRE labelling an incident timeline.
Assign exactly one phase to every event index:
- impact_start: first sign of user-facing impact
- detection: the moment humans or alerting became aware (alert, page, report)
- investigation: diagnosis, confirming causes, reading logs, hypotheses
- mitigation_action: an action taken to reduce impact (rollback, failover, restart, scaling)
- mitigated: impact actually stopped or clearly reduced
- resolved: service fully back to normal
- communication: status updates to stakeholders or customers
- other: anything else
Use the logs and chat for context. Return every index exactly once."""


def classify_ai(inc: Incident, client: AIClient) -> Incident:
    if not inc.timeline:
        return inc
    lines = [
        f"[{i}] {ev.time:%H:%M} {ev.text}" + (f"  (fixed: {ev.phase})" if ev.phase_source == "manual" else "")
        for i, ev in enumerate(inc.timeline)
    ]
    ctx = []
    if inc.logs:
        ctx.append("Logs:\n" + "\n".join(log.raw for log in inc.logs[:40]))
    if inc.messages:
        ctx.append("Chat:\n" + "\n".join(f"{m.time} {m.user}: {m.text}" for m in inc.messages[:40]))
    user = "Timeline:\n" + "\n".join(lines) + ("\n\n" + "\n\n".join(ctx) if ctx else "")
    result = client.complete(SYSTEM, user, schema=SCHEMA, schema_name="timeline_phases")
    by_index = {e["index"]: e["phase"] for e in result["events"]}
    classify_heuristic(inc)  # fallback for any index the model skipped
    for i, ev in enumerate(inc.timeline):
        if ev.phase_source != "manual" and i in by_index:
            ev.phase, ev.phase_source = by_index[i], "ai"
    return inc


def compute_metrics(inc: Incident) -> Metrics:
    def since_start(*phases: str):
        ev = inc.first(*phases)
        return (ev.time - inc.start_time) if ev else None

    ttm = since_start("mitigated")
    if ttm is None:
        ttm = since_start("resolved")
    return Metrics(
        ttd=since_start("detection"),
        tta=since_start("mitigation_action"),
        ttm=ttm,
        ttr=inc.end_time - inc.start_time,
    )
