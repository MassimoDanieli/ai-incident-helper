"""Blameless post-mortem: computed facts + model-written analysis.

Everything that can be computed (durations, timeline, metric peaks) is
computed in code and put in the report verbatim. The model only writes what
needs judgement, in a fixed structure, and must say how sure it is about the
root cause. Without a model the report is still produced, with the judgement
sections left for humans to fill in.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .llm import strict_object
from .model import Incident, Metrics

SCHEMA = strict_object(
    {
        "title": {"type": "string", "description": "Short descriptive incident title."},
        "summary": {"type": "string", "description": "3-5 sentence executive summary."},
        "impact": {"type": "string", "description": "Who/what was affected, how much, for how long. Only from the data."},
        "root_cause": strict_object(
            {
                "statement": {"type": "string"},
                "confidence": {"type": "string", "enum": ["confirmed", "likely", "hypothesis"]},
                "evidence": {"type": "array", "items": {"type": "string"}, "description": "Quotes or facts from the timeline/logs/chat."},
            }
        ),
        "contributing_factors": {"type": "array", "items": {"type": "string"}},
        "what_went_well": {"type": "array", "items": {"type": "string"}},
        "what_went_wrong": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": strict_object(
                {
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": ["prevent", "detect", "mitigate", "process"]},
                    "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
                    "owner_hint": {"type": "string", "description": "Team or role, never a named individual."},
                    "rationale": {"type": "string"},
                }
            ),
        },
        "open_questions": {"type": "array", "items": {"type": "string"}, "description": "What the data cannot answer."},
    }
)

SYSTEM = """You are a senior SRE writing a blameless post-mortem.
Rules:
- Use only the facts provided. Never invent numbers, services or people.
- The durations given are computed already: quote them, do not recompute.
- Blameless: describe systems and decisions, not individual fault. Action
  item owners are teams or roles, never named people.
- Root cause: say "confirmed" only if the data states it explicitly;
  "likely" if strongly suggested; otherwise "hypothesis". Support it with
  concrete evidence lines from the input.
- Action items must be specific and checkable (not "improve monitoring").
  Cover prevention, faster detection and faster mitigation where relevant.
- Put anything the data cannot answer in open_questions.
Write in {language}."""


def _fmt(td: timedelta | None) -> str:
    if td is None:
        return "n/d"
    mins = int(td.total_seconds() // 60)
    return f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"{mins} min"


def facts_block(inc: Incident, m: Metrics) -> str:
    lines = [
        f"Incident: {inc.incident_id} {inc.title}".rstrip(),
        f"Start (impact): {inc.start_time:%Y-%m-%d %H:%M %Z}",
        f"End: {inc.end_time:%Y-%m-%d %H:%M %Z}",
        f"Computed: TTD={_fmt(m.ttd)} TTA={_fmt(m.tta)} TTM={_fmt(m.ttm)} TTR={_fmt(m.ttr)}",
    ]
    if inc.severity:
        lines.append(f"Severity: {inc.severity}")
    if inc.services:
        lines.append("Services: " + ", ".join(inc.services))
    lines.append("\nTimeline (phase in brackets):")
    lines += [f"- {e.time:%H:%M} [{e.phase}] {e.text}" for e in inc.timeline]
    if inc.logs:
        lines.append("\nLogs:")
        lines += [f"- {log.raw}" for log in inc.logs[:60]]
    if inc.metrics:
        lines.append("\nMetrics:")
        for s in inc.metrics:
            pts = ", ".join(f"{p.time:%H:%M}={p.value:g}" for p in s.points)
            lines.append(f"- {s.name} ({s.unit}): {pts}")
    if inc.messages:
        lines.append(f"\nChat ({inc.comms_platform or 'chat'}):")
        lines += [f"- {msg.time} {msg.user}: {msg.text}" for msg in inc.messages[:60]]
    if inc.notes:
        lines.append(f"\nNotes:\n{inc.notes}")
    return "\n".join(lines)


def analyse(inc: Incident, m: Metrics, client: Any, language: str = "Italian") -> dict[str, Any]:
    return client.complete(SYSTEM.format(language=language), facts_block(inc, m), schema=SCHEMA, schema_name="postmortem")


# --- rendering --------------------------------------------------------------

_L = {
    "Italian": {
        "pm": "Post-mortem",
        "facts": "Dati",
        "summary": "Sintesi",
        "impact": "Impatto",
        "timeline": "Timeline",
        "root": "Causa principale",
        "conf": "Affidabilità",
        "evidence": "Evidenze",
        "factors": "Fattori che hanno contribuito",
        "well": "Cosa ha funzionato",
        "wrong": "Cosa non ha funzionato",
        "actions": "Azioni",
        "questions": "Domande aperte",
        "metrics": "Metriche",
        "peak": "picco",
        "todo": "_Da compilare._",
        "gen": "Analisi generata da",
        "noai": "Analisi IA non eseguita: le sezioni di giudizio sono da compilare.",
        "phase": "Fase",
        "time": "Ora",
        "event": "Evento",
        "kind": "Tipo",
        "owner": "Responsabile",
        "why": "Perché",
        "conf_vals": {"confirmed": "confermata", "likely": "probabile", "hypothesis": "ipotesi"},
    },
    "English": {
        "pm": "Post-mortem",
        "facts": "Facts",
        "summary": "Summary",
        "impact": "Impact",
        "timeline": "Timeline",
        "root": "Root cause",
        "conf": "Confidence",
        "evidence": "Evidence",
        "factors": "Contributing factors",
        "well": "What went well",
        "wrong": "What went wrong",
        "actions": "Action items",
        "questions": "Open questions",
        "metrics": "Metrics",
        "peak": "peak",
        "todo": "_To be completed._",
        "gen": "Analysis generated by",
        "noai": "AI analysis not run: judgement sections are left to complete.",
        "phase": "Phase",
        "time": "Time",
        "event": "Event",
        "kind": "Kind",
        "owner": "Owner",
        "why": "Why",
        "conf_vals": {"confirmed": "confirmed", "likely": "likely", "hypothesis": "hypothesis"},
    },
}


def _bullets(items: list[str], todo: str) -> list[str]:
    items = [i for i in items if i.strip()]
    return [f"- {i}" for i in items] if items else [todo]


def render(inc: Incident, m: Metrics, analysis: dict[str, Any] | None, language: str = "Italian", model_label: str = "") -> str:
    t = _L.get(language, _L["English"])
    a = analysis or {}
    title = a.get("title") or inc.title or inc.incident_id
    out = [f"# {t['pm']} — {inc.incident_id}: {title}", ""]

    out += [
        f"## {t['facts']}",
        "",
        "| | |",
        "|---|---|",
        f"| Start | {inc.start_time:%Y-%m-%d %H:%M %Z} |",
        f"| End | {inc.end_time:%Y-%m-%d %H:%M %Z} |",
    ]
    if inc.severity:
        out.append(f"| Severity | {inc.severity} |")
    if inc.services:
        out.append(f"| Services | {', '.join(inc.services)} |")
    out += [
        f"| TTD (detect) | {_fmt(m.ttd)} |",
        f"| TTA (first action) | {_fmt(m.tta)} |",
        f"| TTM (mitigate) | {_fmt(m.ttm)} |",
        f"| TTR (resolve) | {_fmt(m.ttr)} |",
        "",
    ]

    out += [f"## {t['summary']}", "", a.get("summary") or t["todo"], ""]
    out += [f"## {t['impact']}", "", a.get("impact") or t["todo"], ""]

    out += [f"## {t['timeline']}", "", f"| {t['time']} | {t['phase']} | {t['event']} |", "|---|---|---|"]
    out += [f"| {e.time:%H:%M} | {e.phase} | {e.text.replace('|', '/')} |" for e in inc.timeline]
    out.append("")

    if inc.metrics:
        out += [f"## {t['metrics']}", ""]
        for s in inc.metrics:
            if s.points:
                peak = max(s.points, key=lambda p: p.value)
                first, last = s.points[0], s.points[-1]
                out.append(
                    f"- **{s.name}** ({s.unit}): {first.value:g} → {t['peak']} {peak.value:g} @ {peak.time:%H:%M} → {last.value:g} @ {last.time:%H:%M}"
                )
        out.append("")

    rc = a.get("root_cause")
    out += [f"## {t['root']}", ""]
    if rc:
        out += [rc["statement"], "", f"**{t['conf']}:** {t['conf_vals'].get(rc['confidence'], rc['confidence'])}", ""]
        if rc["evidence"]:
            out += [f"**{t['evidence']}:**", *[f"- {e}" for e in rc["evidence"]], ""]
    else:
        out += [t["todo"], ""]

    out += [f"## {t['factors']}", "", *_bullets(a.get("contributing_factors", []), t["todo"]), ""]
    out += [f"## {t['well']}", "", *_bullets(a.get("what_went_well", []), t["todo"]), ""]
    out += [f"## {t['wrong']}", "", *_bullets(a.get("what_went_wrong", []), t["todo"]), ""]

    out += [f"## {t['actions']}", ""]
    items = sorted(a.get("action_items", []), key=lambda x: x["priority"])
    if items:
        out += [f"| | {t['actions']} | {t['kind']} | {t['owner']} | {t['why']} |", "|---|---|---|---|---|"]
        out += [f"| {x['priority']} | {x['title']} | {x['kind']} | {x['owner_hint']} | {x['rationale']} |" for x in items]
    else:
        out.append(t["todo"])
    out.append("")

    if a.get("open_questions"):
        out += [f"## {t['questions']}", "", *[f"- {q}" for q in a["open_questions"]], ""]

    out.append(f"<sub>{t['gen']} {model_label}</sub>" if analysis else f"<sub>{t['noai']}</sub>")
    return "\n".join(out).rstrip() + "\n"
