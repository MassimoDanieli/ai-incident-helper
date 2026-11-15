"""CLI: ``python -m incident_helper <command>``

analyze FILE.yaml [--no-ai] [--out report.md] [--json result.json]
extract NOTES.txt [--date 2026-11-14] [--out incident.yaml]
stats DIR_OR_FILES...            MTTR & co. across incidents (offline)
doctor                           show the resolved AI configuration
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import extract, parser, pipeline
from .ai import make_client, output_language
from .llm import AIConfigError


def _client_or_exit(no_ai: bool, redact_flag: bool | None):
    if no_ai:
        return None
    try:
        return make_client(redact_flag)
    except AIConfigError as exc:
        print(f"configuration error: {exc}\n(use --no-ai for the offline report)", file=sys.stderr)
        raise SystemExit(2) from exc


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def cmd_analyze(args) -> int:
    inc = parser.load(Path(args.file))
    client = _client_or_exit(args.no_ai, args.redact)
    result = pipeline.analyse(inc, client, args.language)
    if args.json:
        Path(args.json).write_text(
            json.dumps({"metrics_min": result.metrics.minutes(), "analysis": result.report}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    _write(result.markdown, args.out)
    return 0


def cmd_extract(args) -> int:
    raw = Path(args.file).read_text(encoding="utf-8", errors="replace")
    client = _client_or_exit(False, args.redact)
    inc = extract.to_incident(extract.extract(raw, client, args.date))
    _write(extract.to_yaml(inc), args.out)
    return 0


def cmd_stats(args) -> int:
    files: list[Path] = []
    for p in map(Path, args.paths):
        files += sorted(p.glob("*.y*ml")) if p.is_dir() else [p]
    incidents = []
    for f in files:
        try:
            incidents.append(parser.load(f))
        except parser.IncidentParseError as exc:
            print(f"skip {f}: {exc}", file=sys.stderr)
    rows = pipeline.dashboard_rows(incidents)
    agg = pipeline.aggregate(rows)
    if args.json:
        print(json.dumps({"incidents": rows, "aggregate": agg}, indent=2))
        return 0
    cols = ["incident", "TTD (min)", "TTA (min)", "TTM (min)", "TTR (min)"]
    print(" | ".join(f"{c:>14}" for c in cols))
    for r in rows:
        print(" | ".join(f"{('-' if r[c] is None else r[c])!s:>14}" for c in cols))
    print()
    for k, v in agg.items():
        print(f"{k:<10} mean {v['mean']}  median {v['median']}  (n={v['n']})")
    print(f"\nMTTR: {agg['TTR (min)']['mean']} min over {agg['TTR (min)']['n']} incidents")
    return 0


def cmd_doctor(args) -> int:
    client = _client_or_exit(False, args.redact)
    c = client.client.config
    print(json.dumps({"provider": c.provider, "model": c.model, "base_url": c.base_url, "redact_input": client.redact_input}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="incident_helper", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--redact", dest="redact", action="store_true", default=None, help="force redaction of prompts")
    p.add_argument("--no-redact", dest="redact", action="store_false", help="disable redaction")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="post-mortem for one incident")
    a.add_argument("file")
    a.add_argument("--no-ai", action="store_true", help="offline: heuristics only, no model call")
    a.add_argument("--language", default=output_language())
    a.add_argument("--out")
    a.add_argument("--json")
    a.set_defaults(func=cmd_analyze)

    e = sub.add_parser("extract", help="draft an incident YAML from raw notes/chat/logs")
    e.add_argument("file")
    e.add_argument("--date", default="", help="incident date if the text has only times")
    e.add_argument("--out")
    e.set_defaults(func=cmd_extract)

    s = sub.add_parser("stats", help="metrics across many incidents")
    s.add_argument("paths", nargs="+")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_stats)

    d = sub.add_parser("doctor", help="show AI configuration")
    d.set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
