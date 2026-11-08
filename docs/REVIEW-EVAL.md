# Review evaluation

**English | [한국어](REVIEW-EVAL.ko.md)**

What each part of the review stack ([REVIEW.md](REVIEW.md)) adds, measured the way ArcticSwarm
(Yoon et al., 2026, [arXiv:2609.01870](https://arxiv.org/abs/2609.01870), Table 3) tears its
review down: the same cases under cumulative conditions. Reproduce with:

```bash
ma-pmo eval --review
```

## Cases

The demo portfolio plus one project, PROJ-X, made from PROJ-22 (green, SPI 0.85, slack 7 days,
staffed) and changed so that a gate decision or the report contradicts another agent, or not.
Labels follow from the construction and PMO rules written down before the run: a red status or a
planned finish after the deadline is a high risk; a skill nobody has, or more work than a skill
can take in the 12-week horizon, is unstaffed; a plan whose last week is after the deadline week
is late; a project A4 rates medium or above belongs in the report's key risks. Every label is
checked against what the agents actually produced, before any reviewer runs.

35 cases: 23 with a conflict (25 gate conflicts, 6 report conflicts), 12 controls. Labels match what the agents produced: yes.

The real A3, A4, A6, A5 and A8 run on their deterministic path (no LLM) in a throwaway workspace,
on a G3 gate.

## Conditions

| Condition | What is on |
|---|---|
| main | nothing: every step isolated (0.6.0) |
| +builder | A6 and A5 read their upstream and review their own output; A5 adds missing risks |
| +auditor | an A8 step reviews every decision |
| +commit gate | decisions commit only when their reviews hold; the rest go to a person |
| +alternatives | A8 offers alternatives for the decisions it challenges |

## Results

Rates with 95% bootstrap intervals over cases (2,000 resamples, seed 7).

| Condition | Gate conflicts that reached a person | Conflicting gates committed | Report conflicts fixed | Controls held | Approvals added per run | Alternatives per conflict | LLM calls | Median run (ms) |
|---|---|---|---|---|---|---|---|---|
| main | 0% [0, 0] | 100% [100, 100] | 0% [0, 0] | 0% [0, 0] | 0.00 | 0.0 | 0 | 24 |
| +builder | 0% [0, 0] | 100% [100, 100] | 100% [100, 100] | 0% [0, 0] | 0.00 | 0.0 | 0 | 31 |
| +auditor | 0% [0, 0] | 100% [100, 100] | 100% [100, 100] | 0% [0, 0] | 0.00 | 0.0 | 0 | 40 |
| +commit gate | 100% [100, 100] | 0% [0, 0] | 100% [100, 100] | 0% [0, 0] | 0.57 | 0.0 | 0 | 43 |
| +alternatives | 100% [100, 100] | 0% [0, 0] | 100% [100, 100] | 0% [0, 0] | 0.57 | 1.6 | 0 | 44 |

- Builder review fixes every report conflict, because A5 can correct its own output. It changes
  nothing about gates: A6 records its challenges on the board, but nobody is asked.
- The auditor adds a second, independent verdict on every decision, and still nobody is asked.
- **The commit gate is the step that matters**: every gate conflict reaches a person with both
  sides attached (held and linked), no conflicting gate commits, and no control is held. The
  approvals it adds (0.57 a run) are exactly the conflicting passing gates (20 of 35 cases).
- Alternatives add 1.6 offers per conflict and change nothing about what commits.
- No condition makes an LLM call; the review stack adds about 20 ms to a run of this size.

## Workload on the demo data

The 20 built-in scenarios on the demo portfolio, with review off and on:

| Scenario | Decisions | Held | Newly queued | Already queued | Why | Run ms (off → on) |
|---|---|---|---|---|---|---|
| baseline_planning | 3 | 0 | 0 | 0 | – | 28 → 34 |
| burndown_alert | 1 | 0 | 0 | 0 | – | 25 → 26 |
| capacity_planning | 3 | 0 | 0 | 0 | – | 20 → 31 |
| change_control | 3 | 0 | 0 | 0 | – | 20 → 32 |
| compliance_audit | 4 | 0 | 0 | 0 | – | 14 → 17 |
| estimation_calibration | 1 | 0 | 0 | 0 | – | 19 → 21 |
| estimation_review | 0 | 0 | 0 | 0 | – | 14 → 17 |
| executive_briefing | 1 | 0 | 0 | 0 | – | 26 → 30 |
| go_nogo_decision | 4 | 1 | 0 | 1 | gate.no_open_high_risk | 19 → 28 |
| knowledge_kickoff | 3 | 0 | 0 | 0 | – | 20 → 22 |
| lessons_learned_closure | 4 | 0 | 0 | 0 | – | 17 → 20 |
| new_project_intake | 3 | 0 | 0 | 0 | – | 24 → 34 |
| portfolio_prioritization | 1 | 0 | 0 | 0 | – | 26 → 30 |
| quarterly_review | 1 | 0 | 0 | 0 | – | 22 → 25 |
| resource_conflict | 3 | 1 | 0 | 1 | gate.no_open_high_risk | 21 → 33 |
| risk_escalation | 4 | 1 | 0 | 1 | gate.no_open_high_risk | 20 → 28 |
| risk_rebalance | 3 | 1 | 0 | 1 | gate.no_open_high_risk | 21 → 33 |
| schedule_recovery | 0 | 0 | 0 | 0 | – | 23 → 24 |
| stage_gate_review | 3 | 1 | 0 | 1 | gate.no_open_high_risk | 22 → 29 |
| weekly_status | 1 | 0 | 0 | 0 | – | 15 → 17 |
| **all** | 46 | 5 | 0 | 5 | | |

Review queues **nothing new** on the demo data: the five decisions it holds are PROJ-31's gate
(rated high by A4), which A6 had already sent for approval, now with the challenge attached.

## Decisions (criteria set before the run)

| Part | Criterion | Result | Decision |
|---|---|---|---|
| Commit gate | surfaced ≥ 95%, controls held ≤ 5%, no added cost on the deterministic path | 100%, 0%, 0 LLM calls | **On by default** for every workflow; `"review": false` opts out |
| Alternatives | fewer conflicting commits than the commit gate alone | 0% → 0% (nothing left to reduce) | **Off by default**; `MA_PMO_REVIEW_ALTERNATIVES=true` turns them on |
| LLM contrarian | the same, for its cost | not run: no LLM in this evaluation | not built |

## Limits

- The cases are built, not observed: they show the review catches what it is designed to catch,
  and that it stays quiet on what it should not, not how often such conflicts happen. Real
  issue-tracker history (Roadmap 3, [#38](https://github.com/ma-pmo/ma-pmo-ext/issues/38)) is
  what can measure that, and this evaluation will be rerun on it.
- The labelling rules and the reviewers' rules come from the same PMO rules, so agreement shows
  the plumbing works end to end (posts reach readers, verdicts reach people), not that the rules
  are the right ones.
- Everything is deterministic, so the intervals only reflect which cases were sampled.
- ArcticSwarm's numbers are accuracy on open web research and are not comparable; only the shape
  of the ablation is borrowed.
