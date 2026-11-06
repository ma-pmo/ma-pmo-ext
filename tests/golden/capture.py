"""Print what every scenario does, without timings or ids: `python tests/golden/capture.py`.

The golden test runs this in a fresh database and compares it with scenario_traces.json, so a
change to how workflows are stored or executed cannot silently change their results. Regenerate
scenario_traces.json only for an intended change, with DB_URL pointing at a new SQLite file.
"""
from __future__ import annotations

import json
import re
import sys

_DURATION = re.compile(r"\d+(\.\d+)?(s\b|초)")


def _finding(finding: dict) -> dict:
    return {**finding, "finding": _DURATION.sub("<time>", finding["finding"])}


def normalize(trace: dict) -> dict:
    phases = []
    for p in trace["phases"]:
        kind = p["phase"]
        if kind == "plan":
            phases.append({"plan": [(d["agent"], d["function"]) for d in p["delegations"]],
                           "detail": p["detail"]})
        elif kind == "execute":
            phases.append({"execute": p["agent"], "title": p["title"], "results": p["results"]})
        elif kind == "complete":
            phases.append({"complete": p["summary"]})
        else:
            phases.append({"insight": [_finding(f) for f in p["findings"]],
                           "hypotheses": p["hypotheses"],
                           "new_events": {k: v["new_events"] for k, v in p["kpi_delta"].items()}})
    return {
        "title": trace["title"], "scope": trace["scope"], "hypotheses": trace["hypotheses"],
        "phases": phases,
        "messages": [[m["sender"], m["receiver"], m["intent"], m["schema"], m["task_ref"],
                      m["confidence"], m["human_gate_required"]] for m in trace["communications"]],
    }


def main() -> None:
    from ma_pmo.core.i18n import use_lang
    from ma_pmo.core.scenarios import SCENARIOS, run_scenario
    from ma_pmo.db.init import main as init_db

    init_db()
    out = {}
    for lang in ("en", "ko"):
        with use_lang(lang):
            for scenario_id in SCENARIOS:
                out[f"{lang}/{scenario_id}"] = normalize(run_scenario(scenario_id))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
