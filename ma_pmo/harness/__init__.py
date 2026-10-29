"""MA-PMO experiment harness — batch scenario runs, ablation, hypothesis evidence, reports.

A programmable experiment framework:
    from ma_pmo.harness import Experiment, run_experiment, render_markdown
    spec = Experiment("my_exp").with_scenarios("quarterly_review").repeat(3)
    result = run_experiment(spec)
    print(render_markdown(result))
"""
from ma_pmo.harness.reporters import render_json, render_markdown, write_report
from ma_pmo.harness.runner import run_experiment
from ma_pmo.harness.spec import Experiment, ExperimentSpec

__all__ = [
    "Experiment",
    "ExperimentSpec",
    "run_experiment",
    "render_markdown",
    "render_json",
    "write_report",
]
