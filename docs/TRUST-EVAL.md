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

## Results

10 organisations, 711 test releases, 41,648 test issues.

| as of | w | Brier static | Brier dynamic | difference, 95% | ECE static | ECE dynamic | ECE per organisation, static | ECE per organisation, dynamic | leaks |
|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **14 days** | **20** | 0.1333 | 0.1281 | −0.0074 to −0.0028 | 0.070 | 0.044 | 0.1231 | **0.1268** | 0 |
| 14 days | 5 | 0.1333 | 0.1283 | −0.0073 to −0.0025 | 0.070 | 0.043 | 0.1231 | 0.1336 | 0 |
| 14 days | 50 | 0.1333 | 0.1279 | −0.0075 to −0.0031 | 0.070 | 0.043 | 0.1231 | 0.1167 | 0 |
| 28 days | 20 | 0.1614 | 0.1569 | −0.0067 to −0.0023 | 0.060 | 0.035 | 0.1440 | 0.1069 | 0 |

The deciding row is the first: 14 days before release, `w` = 20.

| criterion | result |
|---|---|
| Brier score | pass: lower, and the interval is below 0 |
| ECE, all test issues | pass: 0.070 to 0.044 |
| ECE per organisation | **fail**: 0.1231 to 0.1268 |
| leakage | pass: none |

**Decision.** One criterion failed, so the fixed table stays and no runtime version is built.

What the numbers mean:

- **Learning per organisation helps on the whole.** Brier and the overall ECE improve at every
  setting, and the improvement is larger than the resampling noise.
- **It does not make each organisation better calibrated at the deciding setting.** With the
  prior worth 20 issues, the mean per-organisation ECE rises slightly (0.1231 to 0.1268). With
  a prior worth 5 issues it rises more, so updating too eagerly hurts. A prior worth 50 issues,
  and the 28-day horizon, lower it (0.1167 and 0.1069). Those settings were reported, not chosen,
  before the run. Adopting one now would be choosing it because it won, so it is left for an
  evaluation on other data, with that setting fixed beforehand.
- **The review threshold commits more alerts.** At α = 0.2, the static confidence lets 31,887
  test alerts through without a person, 10.7% of them wrong. The dynamic one lets 41,277
  through, 16.6% wrong. Both are within α, and the dynamic one needs fewer people's reviews.
- **Ten organisations is a small number for a per-organisation mean.** One or two organisations
  can move it.
