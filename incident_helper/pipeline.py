"""High-level operations shared by the CLI and the Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from . import phases, postmortem
from .model import Incident, Metrics


@dataclass
class Analysis:
    incident: Incident
    metrics: Metrics
    report: dict[str, Any] | None
    markdown: str


def analyse(inc: Incident, client: Any | None = None, language: str = "Italian", classify: bool = True, write: bool = True) -> Analysis:
    """Classify the timeline, compute metrics and (optionally) write the post-mortem.

    ``client=None`` runs fully offline with keyword heuristics.
    """
    if client is not None and classify:
        phases.classify_ai(inc, client)
    else:
        phases.classify_heuristic(inc)
    m = phases.compute_metrics(inc)
    report = postmortem.analyse(inc, m, client, language) if (client is not None and write) else None
    md = postmortem.render(inc, m, report, language, getattr(client, "label", ""))
    return Analysis(inc, m, report, md)


def dashboard_rows(incidents: list[Incident]) -> list[dict[str, Any]]:
    rows = []
    for inc in incidents:
        if not any(e.phase_source == "ai" for e in inc.timeline):
            phases.classify_heuristic(inc)  # keeps phases set by hand in the YAML
        mins = phases.compute_metrics(inc).minutes()
        rows.append(
            {
                "incident": inc.incident_id,
                "start": inc.start_time.strftime("%Y-%m-%d %H:%M"),
                "severity": inc.severity,
                "TTD (min)": mins["ttd"],
                "TTA (min)": mins["tta"],
                "TTM (min)": mins["ttm"],
                "TTR (min)": mins["ttr"],
            }
        )
    return rows


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """Mean and median per metric, ignoring incidents where it is unknown.

    MTTR is the mean of TTR across incidents (v1 called a single incident's
    duration "MTTR").
    """
    out = {}
    for key in ("TTD (min)", "TTA (min)", "TTM (min)", "TTR (min)"):
        vals = [r[key] for r in rows if r[key] is not None]
        out[key] = {"mean": round(mean(vals), 1) if vals else None, "median": round(median(vals), 1) if vals else None, "n": len(vals)}
    return out
