# 6. Experiments, ablations and tests

**English | [한국어](06-experiments.ko.md)** · [Course map](README.md) · Lab: [Design an ablation](../../ma_pmo/learn/labs/lab3_ablation/README.md)

## Goal

Make claims about the system reproducible: declare experiments as code, isolate one agent's
contribution with an ablation, and pin behavior with smoke and regression tests.

## Concept

- **Experiment as code.** Which scenarios, how many repetitions, which portfolio, which agents
  removed — in a file you can review, version and rerun. Not a notebook cell.
- **Ablation.** Remove one component, keep everything else equal, compare. If the result does
  not change, the component is not doing what you claim — or the scenarios never exercise it.
- **Deterministic runs.** Thanks to the fallbacks in lecture 3, offline runs give the same
  answer twice. Repetitions then measure nothing; with an LLM in the loop they measure
  variance.
- **Two kinds of test.** *Smoke* tests ask "does the main path still work end to end?" and run
  in seconds. *Regression* tests pin known results on known data ("on the demo portfolio,
  PROJ-31 is red") and should fail only when behavior changes on purpose.

## In MA-PMO

- `ma_pmo/harness/spec.py` — the `Experiment` builder:
  `.with_scenarios(...)`, `.repeat(n)`, `.ablate("A7")`, `.on_scope(...)`.
- `ma_pmo/harness/runner.py` — `run_experiment()` runs every scenario × repetition and, for
  ablations, a baseline and an ablated run **only for scenarios that include that agent**.
- `ma_pmo/harness/experiments/` — built-ins (`a7_ablation`, `hypothesis_matrix`,
  `full_suite`). Files in `./experiments` are discovered automatically.
- `ma-pmo harness new my_exp --hypothesis H3` scaffolds an experiment *and* its test, and
  refuses an ablation that "changes nothing".
- Tests: `tests/test_smoke.py`, `tests/test_regression.py`; markers `smoke` and `regression`;
  `make test-smoke`, `make test-regression`. CI runs smoke first, then regression, then all.

## Try it

```bash
ma-pmo harness list
ma-pmo harness a7_ablation
ma-pmo harness new risk_focus --hypothesis H3 --repeat 3
```

## Pitfalls

- **Ablating an agent the scenario never calls.** The result is "no difference", which is
  true and useless. `ma-pmo learn scenarios` shows which scenarios use which agents.
- **Regression tests that pin noise.** Pin what should be stable (counts, verdicts, critical
  paths), not timestamps or LLM wording.
- **Experiments without a question.** Write the hypothesis in the description first.

## Lab

[Lab 3 — Design an ablation experiment](../../ma_pmo/learn/labs/lab3_ablation/README.md):
`ma-pmo learn start 3`. Write the H4 experiment that shows what A7 contributes.

## Checkpoint

1. Your ablation of A4 shows no change in findings. List three possible reasons.
2. Which belongs in a regression test: the number of red projects, or the report's first
   sentence?
3. When would you increase `repeat` above 1?

Next: [7. Integrations and failure isolation](07-integrations.md)
