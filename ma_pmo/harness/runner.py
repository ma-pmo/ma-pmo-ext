"""Experiment engine — runs scenario batches, repetitions and ablations in-process.

Calls core.scenarios directly without HTTP -> offline and reproducible.
"""
from __future__ import annotations

from ma_pmo.core.obs import get_logger
from ma_pmo.core.scenarios import SCENARIOS, run_scenario
from ma_pmo.harness.collectors import aggregate, collect_run, hypothesis_coverage
from ma_pmo.harness.spec import Experiment, ExperimentSpec

_log = get_logger("harness")


def _as_spec(spec: ExperimentSpec | Experiment) -> ExperimentSpec:
    return spec.build() if isinstance(spec, Experiment) else spec


def run_experiment(spec: ExperimentSpec | Experiment) -> dict:
    """Run an experiment spec and return raw runs, aggregates, coverage and ablation results."""
    spec = _as_spec(spec)
    scenario_ids = spec.scenarios or list(SCENARIOS)
    _log.info(
        "experiment_start",
        name=spec.name,
        scenarios=len(scenario_ids),
        repeat=spec.repeat,
        ablate=spec.ablate_agents,
    )

    runs: list[dict] = []
    for sid in scenario_ids:
        for rep in range(spec.repeat):
            trace = run_scenario(sid, spec.scope)
            runs.append(collect_run(trace, rep))

    result = {
        "experiment": spec.name,
        "description": spec.description,
        "scope": spec.scope,
        "config": {"scenarios": len(scenario_ids), "repeat": spec.repeat},
        "runs": runs,
        "aggregate": aggregate(runs),
        "coverage": hypothesis_coverage(runs),
    }

    if spec.ablate_agents:
        result["ablation"] = _run_ablation(scenario_ids, spec.ablate_agents, spec.scope)

    _log.info("experiment_done", name=spec.name, runs=len(runs))
    return result


def _run_ablation(scenario_ids: list[str], agents: list[str], scope: str) -> dict:
    """Compare outputs/findings against the baseline when each agent is removed.

    Runs baseline vs. ablated only for scenarios that include that agent.
    """
    out: dict[str, list[dict]] = {}
    for agent in agents:
        rows = []
        for sid in scenario_ids:
            if agent not in {a for a, _ in SCENARIOS[sid]["steps"]}:
                continue
            base = run_scenario(sid, scope)
            abl = run_scenario(sid, scope, drop_agents=(agent,))
            rows.append(
                {
                    "scenario_id": sid,
                    "baseline_outputs": _n_outputs(base),
                    "ablated_outputs": _n_outputs(abl),
                    "baseline_findings": _n_findings(base),
                    "ablated_findings": _n_findings(abl),
                    "delta_findings": _n_findings(base) - _n_findings(abl),
                }
            )
        out[agent] = rows
    return out


def _n_outputs(trace: dict) -> int:
    return sum(
        len(p.get("results", [])) for p in trace["phases"] if p["phase"] == "execute"
    )


def _n_findings(trace: dict) -> int:
    insight: dict = next((p for p in trace["phases"] if p["phase"] == "insight"), {})
    return len(insight.get("findings", []))
