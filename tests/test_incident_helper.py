import json
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from incident_helper import extract, parser, phases, pipeline
from incident_helper.__main__ import main
from incident_helper.ai import GuardedClient, make_client
from incident_helper.llm import AIClient, AIConfig
from incident_helper.redact import redact

DATA = Path(__file__).resolve().parent.parent / "data"
EXAMPLES = sorted(DATA.glob("*.yaml"))


def fake(answer):
    seen = []

    def responder(system, user, schema):
        seen.append({"system": system, "user": user, "schema": schema})
        return answer(system, user, schema) if callable(answer) else answer

    client = GuardedClient(AIClient(AIConfig(provider="fake", model="fake"), fake_responder=responder), redact_input=False)
    client.seen = seen
    return client


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_all_examples_parse(path):
    inc = parser.load(path)
    assert inc.timeline and inc.end_time > inc.start_time
    assert all(e.time.tzinfo for e in inc.timeline)


def test_parse_details():
    inc = parser.load(DATA / "example_incident.yaml")
    assert inc.incident_id == "INC-2025-04-01"
    assert inc.timeline[1].text == "Alert fired: 'High latency'"
    assert inc.timeline[1].time.hour == 14 and inc.timeline[1].time.minute == 5
    assert inc.logs[0].time is not None and "TimeoutError" in inc.logs[0].raw
    assert inc.metrics[0].name == "latency_p95" and inc.metrics[0].points[1].value == 5200
    assert inc.messages[0].user == "Marco" and inc.comms_platform == "slack"


def test_timeline_crossing_midnight_and_manual_phase():
    inc = parser.load(
        "incident_id: X\nstart_time: 2026-01-01T23:50:00Z\nend_time: 2026-01-02T00:30:00Z\n"
        "timeline:\n  - '23:50 errors'\n  - {time: '00:05', text: 'paged', phase: detection}\n  - '00:30 recovered'\n"
    )
    assert inc.timeline[1].time.day == 2 and inc.timeline[2].time.day == 2
    assert inc.timeline[1].phase == "detection" and inc.timeline[1].phase_source == "manual"


@pytest.mark.parametrize(
    "text, err",
    [
        ("incident_id: X\nstart_time: 2026-01-01T10:00:00Z\n", "end_time"),
        ("incident_id: X\nstart_time: 2026-01-01T10:00:00Z\nend_time: 2026-01-01T09:00:00Z\n", "before"),
        (
            "incident_id: X\nstart_time: 2026-01-01T10:00:00Z\nend_time: 2026-01-01T11:00:00Z\ntimeline: ['no time here']\n",
            "without a time",
        ),
        (
            "incident_id: X\nstart_time: 2026-01-01T10:00:00Z\nend_time: 2026-01-01T11:00:00Z\ntimeline: [{time: '10:00', text: a, phase: bogus}]\n",
            "unknown phase",
        ),
        ("- just\n- a list\n", "mapping"),
        ("a: [unclosed\n", "invalid YAML"),
    ],
)
def test_parse_errors(text, err):
    with pytest.raises(parser.IncidentParseError, match=err):
        parser.load(text)


# --- phases & metrics ----------------------------------------------------------


def test_heuristic_metrics_on_v1_example():
    inc = phases.classify_heuristic(parser.load(DATA / "example_incident.yaml"))
    assert [e.phase for e in inc.timeline] == ["impact_start", "detection", "investigation", "mitigation_action", "resolved"]
    m = phases.compute_metrics(inc)
    assert m.ttd == timedelta(minutes=2)
    assert m.tta == timedelta(minutes=9)
    assert m.ttm == timedelta(minutes=54)  # no explicit "mitigated" -> resolution
    assert m.ttr == timedelta(minutes=54)


@pytest.mark.parametrize(
    "text, phase",
    [
        ("Slack: DevOps - investigating auth service", "investigation"),
        ("Slack: Ops - High CPU on payment-worker-2", "investigation"),
        ("Auto-remediation triggered: restart frontend pods", "mitigation_action"),
        ("Failover to standby node completed", "mitigated"),
        ("Latency returned to baseline", "resolved"),
        ("On-call paged automatically", "detection"),
    ],
)
def test_heuristic_phase_rules(text, phase):
    assert phases.heuristic_phase(text) == phase


def test_unknown_metrics_are_none_not_zero():
    inc = parser.load(
        "incident_id: X\nstart_time: 2026-01-01T10:00:00Z\nend_time: 2026-01-01T11:00:00Z\ntimeline: ['10:00 something odd']\n"
    )
    m = phases.compute_metrics(phases.classify_heuristic(inc))
    assert m.ttd is None and m.tta is None and m.ttm is None
    assert m.minutes()["ttr"] == 60.0


def test_ai_classification_overrides_heuristics_but_not_manual():
    inc = parser.load(
        "incident_id: X\nstart_time: 2026-01-01T10:00:00Z\nend_time: 2026-01-01T11:00:00Z\n"
        "timeline:\n  - '10:00 DB timeouts'\n  - '10:10 DBA: primary crash confirmed'\n"
        "  - {time: '10:20', text: 'promoted standby', phase: mitigation_action}\n  - '10:30 errors gone'\n"
    )
    answer = {"events": [{"index": 0, "phase": "impact_start"}, {"index": 1, "phase": "detection"}, {"index": 2, "phase": "other"}]}
    client = fake(answer)
    phases.classify_ai(inc, client)
    assert [e.phase for e in inc.timeline] == ["impact_start", "detection", "mitigation_action", "other"]
    assert [e.phase_source for e in inc.timeline] == ["ai", "ai", "manual", "heuristic"]  # index 3 missing -> heuristic
    assert "(fixed: mitigation_action)" in client.seen[0]["user"]


# --- post-mortem ---------------------------------------------------------------

ANALYSIS = {
    "title": "Failed DB primary",
    "summary": "The primary crashed.",
    "impact": "API unavailable for 55 minutes.",
    "root_cause": {
        "statement": "Primary node crash with incomplete WAL.",
        "confidence": "confirmed",
        "evidence": ["dba NOTE: primary crashed"],
    },
    "contributing_factors": ["No automatic failover"],
    "what_went_well": ["Alert fired in 2 minutes"],
    "what_went_wrong": ["Manual failover took 15 minutes"],
    "action_items": [
        {"title": "Automate failover", "kind": "mitigate", "priority": "P2", "owner_hint": "DB team", "rationale": "cut TTM"},
        {"title": "Fix WAL archiving", "kind": "prevent", "priority": "P1", "owner_hint": "DB team", "rationale": "data loss"},
    ],
    "open_questions": ["Why did the primary crash?"],
}


def test_postmortem_prompt_has_computed_facts_and_render_sorts_actions():
    inc = parser.load(DATA / "example_db_crash.yaml")
    client = fake(ANALYSIS)
    result = pipeline.analyse(inc, client, "Italian", classify=False)
    prompt = client.seen[0]["user"]
    assert "Computed: TTD=" in prompt and "WAL logs incomplete" in prompt and "Product: Client data" in prompt
    assert "Italian" in client.seen[0]["system"]
    md = result.markdown
    assert "## Causa principale" in md and "**Affidabilità:** confermata" in md
    assert md.index("Fix WAL archiving") < md.index("Automate failover")  # P1 before P2
    assert "| TTR (resolve) | 55 min |" in md
    assert "picco 78" in md


def test_offline_report_has_placeholders():
    result = pipeline.analyse(parser.load(DATA / "example_incident.yaml"), None, "English")
    assert result.report is None
    assert "_To be completed._" in result.markdown and "AI analysis not run" in result.markdown
    assert "| 14:05 | detection |" in result.markdown


# --- extraction ---------------------------------------------------------------

EXTRACTED = {
    "incident_id": "INC-2026-11-03",
    "title": "payments-api pool exhausted after v4.12.0",
    "severity": "SEV2",
    "services": ["payments-api", "ledger-db"],
    "start_time": "2026-11-03T09:38:00Z",
    "end_time": "2026-11-03T10:15:00Z",
    "timeline": [
        {"time": "2026-11-03T09:51:00Z", "text": "Rollback to v4.11.3 started", "phase": "mitigation_action"},
        {"time": "2026-11-03T09:41:00Z", "text": "5xx alert fired", "phase": "detection"},
        {"time": "2026-11-03T09:38:00Z", "text": "5xx spike begins", "phase": "impact_start"},
        {"time": "2026-11-03T10:04:00Z", "text": "Checkouts succeeding", "phase": "mitigated"},
        {"time": "2026-11-03T10:15:00Z", "text": "Resolved", "phase": "resolved"},
    ],
    "log_lines": ["2026-11-03T09:38:12Z payments-api ERROR HikariPool-1 - Connection is not available"],
    "messages": [{"time": "09:42", "user": "Priya", "text": "ack, looking"}],
    "notes": "Times assumed UTC.",
}


def test_extract_round_trips_through_yaml():
    client = fake(EXTRACTED)
    raw = (DATA / "raw" / "example_teams_export.txt").read_text()
    inc = extract.to_incident(extract.extract(raw, client, "2026-11-03"))
    assert [e.text for e in inc.timeline][0] == "5xx spike begins"  # sorted
    y = extract.to_yaml(inc)
    again = parser.load(y)
    assert again.severity == "SEV2" and again.timeline[1].phase == "detection"
    m = phases.compute_metrics(again)
    assert m.minutes() == {"ttd": 3.0, "tta": 13.0, "ttm": 26.0, "ttr": 37.0}
    assert "Incident date if not in the text: 2026-11-03" in client.seen[0]["user"]


# --- redaction & client factory -----------------------------------------------


def test_redaction():
    text = (
        "user=svc password=hunter2 from 10.1.2.3 mail priya@example.gov.uk "
        "key AKIAABCDEFGHIJKLMNOP Authorization: Bearer abcdefghijklmnop123 gh ghp_" + "a" * 36
    )
    out = redact(text)
    for secret in ("hunter2", "10.1.2.3", "priya@example.gov.uk", "AKIAABCDEFGHIJKLMNOP", "abcdefghijklmnop123", "ghp_"):
        assert secret not in out
    assert "password=[REDACTED]" in out and "[IP]" in out and "[EMAIL]" in out


def test_redaction_defaults_by_provider():
    assert make_client(env={"AI_PROVIDER": "anthropic"}).redact_input is True
    assert make_client(env={"AI_PROVIDER": "local", "AI_MODEL": "m", "AI_BASE_URL": "http://x/v1"}).redact_input is False
    assert make_client(env={"AI_PROVIDER": "anthropic", "INCIDENT_REDACT": "0"}).redact_input is False


def test_guarded_client_redacts_before_sending():
    inner = fake(EXTRACTED).client
    guarded = GuardedClient(inner, redact_input=True)
    seen = []
    inner.fake_responder = lambda s, u, sc: seen.append(u) or EXTRACTED
    guarded.complete("s", "password=hunter2 at 10.0.0.1", schema=extract.SCHEMA)
    assert "hunter2" not in seen[0] and "10.0.0.1" not in seen[0]


# --- dashboard & CLI -----------------------------------------------------------


def test_dashboard_aggregate_ignores_unknowns():
    rows = pipeline.dashboard_rows([parser.load(p) for p in EXAMPLES])
    assert len(rows) == 5
    agg = pipeline.aggregate(rows)
    assert agg["TTR (min)"]["n"] == 5
    assert agg["TTR (min)"]["mean"] == round(sum(r["TTR (min)"] for r in rows) / 5, 1)


def test_cli_offline_analyze_and_stats(tmp_path, capsys):
    out = tmp_path / "pm.md"
    js = tmp_path / "pm.json"
    assert main(["analyze", str(DATA / "example_db_crash.yaml"), "--no-ai", "--out", str(out), "--json", str(js)]) == 0
    assert "INC-2025-04-22" in out.read_text()
    assert json.loads(js.read_text())["metrics_min"]["ttr"] == 55.0
    assert main(["stats", str(DATA)]) == 0
    assert "MTTR:" in capsys.readouterr().out


def test_cli_without_config_explains(monkeypatch, capsys):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("AI_MODEL", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(["analyze", str(DATA / "example_incident.yaml")])
    assert exc.value.code == 2
    assert "--no-ai" in capsys.readouterr().err


def test_yaml_examples_are_valid_yaml():
    for p in DATA.rglob("*.y*ml"):
        assert isinstance(yaml.safe_load(p.read_text()), dict)
