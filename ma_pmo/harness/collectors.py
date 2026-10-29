"""Collectors — extract measurements from scenario traces and aggregate repeated runs."""
from __future__ import annotations

import statistics


def collect_run(trace: dict, rep: int) -> dict:
    """Single scenario trace -> summary measurements."""
    execs = [p for p in trace["phases"] if p["phase"] == "execute"]
    insight: dict = next((p for p in trace["phases"] if p["phase"] == "insight"), {})
    return {
        "scenario_id": trace["scenario_id"],
        "title": trace["title"],
        "rep": rep,
        "agents": [p["agent"] for p in execs],
        "elapsed_ms": round(sum(p.get("elapsed_ms", 0) for p in execs), 1),
        "n_outputs": sum(len(p.get("results", [])) for p in execs),
        "n_messages": len(trace.get("communications", [])),
        "n_gated": sum(
            1 for c in trace.get("communications", []) if c.get("human_gate_required")
        ),
        "hypotheses": trace["hypotheses"],
        "findings": insight.get("findings", []),
        "kpi_delta": insight.get("kpi_delta", {}),
    }


def aggregate(runs: list[dict]) -> dict:
    """Aggregate repeated runs per scenario (mean, std)."""
    by_scn: dict[str, list[dict]] = {}
    for r in runs:
        by_scn.setdefault(r["scenario_id"], []).append(r)

    summary = []
    for sid, rs in by_scn.items():
        elapsed = [r["elapsed_ms"] for r in rs]
        summary.append(
            {
                "scenario_id": sid,
                "title": rs[0]["title"],
                "reps": len(rs),
                "agents": rs[0]["agents"],
                "hypotheses": rs[0]["hypotheses"],
                "elapsed_ms_mean": round(statistics.mean(elapsed), 1),
                "elapsed_ms_std": round(statistics.pstdev(elapsed), 1) if len(elapsed) > 1 else 0.0,
                "n_outputs": rs[0]["n_outputs"],
                "n_messages": rs[0]["n_messages"],
                "n_gated": rs[0]["n_gated"],
            }
        )
    return {"per_scenario": summary}


def hypothesis_coverage(runs: list[dict]) -> dict:
    """Per hypothesis H1–H5, the scenarios that test it (coverage matrix)."""
    cov: dict[str, set[str]] = {f"H{i}": set() for i in range(1, 6)}
    for r in runs:
        for h in r["hypotheses"]:
            cov.setdefault(h, set()).add(r["scenario_id"])
    return {h: sorted(s) for h, s in cov.items()}
