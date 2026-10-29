# MA-PMO experiment harness

**English | [한국어](README.ko.md)**

A framework for defining, running and reporting **programmable experiments** on top of the scenarios, agents, KPIs and hypotheses. It makes paper evidence (H1–H5), ablations and regression measurements reproducible and automatic. Runs in-process — no API server or key needed.

## Layout

```
ma_pmo/harness/
├─ spec.py            # ExperimentSpec + Experiment (fluent builder)
├─ runner.py          # run_experiment: batches, repetitions, ablations
├─ collectors.py      # trace -> measurements, aggregation, hypothesis coverage
├─ reporters.py       # Markdown / JSON / CSV reports
├─ experiments/       # predefined experiments (EXPERIMENTS registry)
│  ├─ full_suite.py         # sweep of all 20 scenarios
│  ├─ hypothesis_matrix.py  # H1–H5 coverage + variance over 3 repetitions
│  └─ a7_ablation.py        # A7 knowledge ablation (H4)
├─ cli.py             # ma-pmo harness <experiment>
└─ results/           # outputs (.md/.json/.csv) — gitignored
```

## CLI

```bash
ma-pmo harness list                       # list experiments
ma-pmo harness full_suite                 # full sweep -> Markdown on stdout
ma-pmo harness hypothesis_matrix --save   # save results under harness/results/
MA_PMO_LANG=ko ma-pmo harness a7_ablation --save   # ablation report in Korean
make harness                              # = full_suite --save
```

## Python API

```python
from ma_pmo.harness import Experiment, run_experiment, render_markdown, write_report

spec = (
    Experiment("my_exp", "custom experiment")
    .with_scenarios("quarterly_review", "risk_rebalance")  # omit for all 20
    .repeat(5)                # repetitions (variance analysis)
    .ablate("A7")             # compare with an agent removed
    .on_scope("PORTFOLIO#2026-Q1")
)

result = run_experiment(spec)
print(render_markdown(result))     # paper-ready tables
write_report(result)               # save md/json/csv
```

## Report contents

- **Hypothesis coverage matrix**: H1–H5 × scenarios that test them
- **Per-scenario summary**: agents, time (mean ± std), outputs, messages, gated messages
- **Ablation**: how outputs and findings change when an agent is removed (e.g. citations lost without A7)
- **Raw data**: measurements from every run (JSON), CSV for spreadsheets

## Extending

1. Define `spec = Experiment(...)...` in `ma_pmo/harness/experiments/<name>.py`
2. Register it in `EXPERIMENTS` in `ma_pmo/harness/experiments/__init__.py`
3. Run `ma-pmo harness <name>`

For new measurements, add extraction logic to `collectors.collect_run`; for new tables, add a section to `reporters.render_markdown`.
