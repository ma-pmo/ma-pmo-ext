# Causal risk evaluation

**English | [한국어](CAUSAL-EVAL.ko.md)**

A4 knows which signals go together with a slip: a task that is blocked, not started or
unassigned two weeks before its release slips more often. A project manager needs to know
something else: if the blocker is cleared, the task started or the task assigned, how much
less likely is the slip? This document fixes the questions, the method and the criteria
**before any estimate is computed**. The estimates and the code follow in a later change:

```bash
ma-pmo benchmark causal bench-data --out causal.json
```

## Questions

On the public Jira benchmark ([BENCHMARK.md](BENCHMARK.md)), for every issue scheduled for a
release, as the tracker stood 14 days before the release date (`T`), three questions:

| treatment at T | defined as | what a PMO would do about it |
|---|---|---|
| blocked | `blocked_by_open` > 0: another open issue blocks it | clear the blocker |
| not started | `started` = 0: still in a not-started status | start it |
| unassigned | `has_assignee` = 0 | assign it |

For each, the estimand is the **average effect on the probability of slipping**, in percentage
points: the slip rate if every issue had the treatment minus the rate if none had it. An issue
slips if it is not resolved by its release date (the benchmark's labels, `run.py`).

`reschedules` is not a treatment. An issue is usually moved because it is already late, so
it is part of the outcome more than a cause.

## Method

- **Adjustment set.** The covariates are things fixed before the treatment, or not caused by
  it:
  - `priority`;
  - issue type (`bug`, `feature`, `task`);
  - `age_days`;
  - `blocks` (how many issues it blocks);
  - `has_estimate`;
  - the release's open issues (`release_open`, `release_open_share`);
  - the organisation, one-hot.

  Excluded, because the treatment can cause them:
  - status-derived features (`in_review`, `since_status_days`, `status_changes`);
  - the other treatments;
  - `assignee_load`;
  - `days_left`, which is the same for every issue at T.
- **Estimator.** Augmented inverse probability weighting (AIPW), with 5-fold cross-fitting.
  Both the propensity and the outcome model are scikit-learn's histogram gradient boosting with
  default settings and seed 0. Propensities are clipped to [0.01, 0.99].
- **Overlap.** Issues whose propensity falls outside [0.05, 0.95] are left out of the estimate;
  how many is reported.
- **Uncertainty.** A 95% interval from the influence function, with standard errors clustered by
  release (issues of the same release are not independent).
- **For comparison.** The naive difference in slip rates between treated and untreated issues,
  with no adjustment.

## Criteria (set before any estimate)

A treatment's effect counts as **supported** only if all of these hold:

| check | passes when |
|---|---|
| overlap | at least 90% of issues have a propensity within [0.05, 0.95] |
| balance | after weighting, every covariate's standardized mean difference is below 0.1 in absolute value |
| placebo | with the treatment shuffled within each release, the estimate's 95% interval contains 0 and the estimate is under 1 percentage point in absolute value |
| stability | leaving out one organisation at a time, every estimate has the same sign as the full one |
| precision | the 95% interval excludes 0 |

**Decision.** Only supported effects can be shown to people (step 3 of the plan: A4's alerts
saying what would help, with the estimate and its interval). Effects that are not supported are
reported, labelled as such, and not used. Passing these checks does not prove a cause. Effort,
skill and team history are not in the data, and they can confound all three treatments. A
supported effect is an estimate that survived the checks, and is reported as that.

Nothing in the method or the criteria changes after the first estimate. If something has to,
the change, its reason and the result under both versions are reported.
