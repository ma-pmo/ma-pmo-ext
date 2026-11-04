# 5. Measuring agents: KPIs, hypotheses, baselines

**English | [한국어](05-measuring-agents.ko.md)** · [Course map](README.md) · Lab: [Repair a dataset](../../ma_pmo/learn/labs/lab2_dataset/README.md)

## Goal

Turn "the agents help" into claims that can be checked, and know what data each check needs.

## Concept

A measurable claim has four parts:

1. **A hypothesis** — "agents shorten the reporting cycle" (H1).
2. **A metric** — report cycle time in seconds, recorded on every run.
3. **A baseline** — how long it takes *without* agents. Without it, any number looks good.
4. **A verdict rule** — written down *before* looking at the result: supported if the
   reduction is positive; partly supported if it misses the target; insufficient data if
   there is nothing to compare.

Some metrics also need **ground truth**. Risk detection (H3) is only meaningful against labels
saying which projects really were in trouble. Precision without labels is a guess.

## In MA-PMO

- **Telemetry** — `ma_pmo/core/kpi.py` records events on five axes: `time`, `resource`,
  `delivery`, `risk`, `cost`. Agents call `kpi.record(...)` as they work (A2 records SPI and
  projected slippage); `record_llm_cost` tracks tokens and latency.
- **Hypotheses** — `ma_pmo/eval/harness.py`: H1 report time, H2 idle rate, H3 risk detection
  (precision/recall/F1 against labels), H4 the A7 ablation, H5 complexity strata.
- **Verdicts** — `ma_pmo/eval/report.py` `summarize()` applies the rules: supported / partly
  supported / not supported / insufficient data.
- **Your data** — `ma-pmo template data` writes the inputs a claim needs: projects, tasks,
  resources, **baselines.json** and **risk_labels.csv**. `ma-pmo template validate` refuses
  impossible values before they become confident-looking results.

## Try it

```bash
ma-pmo eval                                       # verdicts on the demo portfolio
ma-pmo template report --format html --out report.html
ma-pmo template data ./my-org && ma-pmo template validate ./my-org
ma-pmo eval --data ./my-org                       # isolated database, never mixed
```

## Pitfalls

- **Baselines from thin air.** A manual reporting time someone guessed makes H1 meaningless.
  Measure a few real cycles and write down how.
- **Changing the rule after seeing the result.** Fix thresholds first (H3 uses F1 ≥ 0.7 for
  "supported").
- **Mixing data.** Evaluating your organization's data in the demo database blends two
  portfolios. MA-PMO evaluates `--data` in its own SQLite file for this reason.
- **One number for everything.** Report the limitations next to the verdicts; the HTML report
  has a section for them.

## Lab

[Lab 2 — Repair an organization dataset](../../ma_pmo/learn/labs/lab2_dataset/README.md):
`ma-pmo learn start 2`. Fix seven errors without deleting data, then evaluate it.

## Checkpoint

1. H3 has precision 1.0 and recall 0.33. What happened, and what would you tell the PMO?
2. Which hypothesis has no meaning without `baselines.json`? Which without `risk_labels.csv`?
3. Why is "insufficient data" a better verdict than a default number?

Next: [6. Experiments, ablations and tests](06-experiments.md)
