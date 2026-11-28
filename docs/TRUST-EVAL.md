# Dynamic trust evaluation

**English | [한국어](TRUST-EVAL.ko.md)**

Whether A4's confidence becomes more accurate when it learns, organisation by organisation, from
outcomes as they become known, instead of using one table fitted once on everybody's history.
Reproduce with:

```bash
ma-pmo benchmark trust bench-data --out trust.json
```

## Why

A4's confidence comes from a fixed table: for each kind of evidence a task can show (blocked,
stalled, moving), the share of such issues that slipped in the benchmark's training releases
([BENCHMARK.md](BENCHMARK.md), roadmap 11). Organisations differ. The transfer evaluation of the
Hugging Face models showed that a model loses accuracy on an organisation it was not trained on.
A table that learns from an organisation's own outcomes as they arrive could follow that
organisation better.

## Method (set before the first run)

- **Data.** The public Jira benchmark replay (`ma-pmo benchmark prepare`), as of 14 days before
  each release. The split is the one A4's table was fitted with: the earliest 70% of releases
  train the table, and the latest 30% are the test.
- **Static.** A4's confidence for an issue is its evidence kind's slip rate in the training
  releases, as today.
- **Dynamic.** It starts from the same rate and updates it with the organisation's
  (`collection`'s) own outcomes:

  `(w × prior + slipped) / (w + n)`

  - `n` and `slipped` count that organisation's issues of the same evidence kind whose outcome
    was known before this prediction's as-of date.
  - An outcome is known once its release date plus the benchmark's one-day grace has passed.
  - The prior's weight `w` is fixed at 20 issues before the run. 5 and 50 are reported as well,
    but do not decide.
  - Outcomes from the training releases count as known history too, but only for the
    organisation they belong to.
- **No leakage.** A test checks that no prediction uses an outcome whose release date plus
  grace falls on or after the prediction's as-of date.

## Criteria (set before the first run)

All on the test releases, with `w` = 20:

| criterion | target |
|---|---|
| Brier score | dynamic lower than static, with the 95% bootstrap interval of the difference (resampling releases) entirely below 0 |
| ECE, all test issues | dynamic at most static |
| ECE per organisation | the mean over organisations with at least 100 test issues: dynamic at most static |
| leakage | none (the test above) |

Also reported, without a target: the results 28 days before release, `w` = 5 and 50, and how
many issues A4's risk-controlled threshold (`HITL_RISK_ALPHA` = 0.2) would commit without a
person, and how many of those were wrong.

**Decision.** If all four hold, a runtime version follows in a separate change: MA-PMO records an
outcome when the tracker shows a task done or past due, and A4 uses these counts per workspace.
If they do not hold, the fixed table stays and the result is reported as it is.
