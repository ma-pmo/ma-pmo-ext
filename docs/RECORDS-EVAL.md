# Record completeness evaluation

**English | [한국어](RECORDS-EVAL.ko.md)**

Whether every decision leaves the record described in [REVIEW.md](REVIEW.md) (decision records,
reasons, provenance, communication log). Reproduce with:

```bash
ma-pmo eval --records
```

## Setup

- **Runs.** Every built-in scenario on the demo data (20 runs), and the 35 labelled cases of the
  [review evaluation](REVIEW-EVAL.md), reviewed with alternatives on (35 runs). Each run uses a
  throwaway workspace and the deterministic path (no LLM).
- **A stand-in person** decides every approval that reaches the queue. It rejects every other one
  and approves the rest. Where the rule asks for a reason (a rejection, or approving a decision a
  reviewer challenged), it first sends the decision without one, then with one.
- **Two stand-in notifiers** receive every event: one accepts it, one fails. So sent, failed and
  skipped attempts all occur, and nobody real is told. Runs inside the review harness are dry
  runs, so their events are logged as skipped, which also counts as a recorded attempt.

## Results

| measure | of what | scenarios | review cases |
|---|---|---:|---:|
| agent decisions recorded | commit-gate decisions with a decision record | 100% of 46 | 100% of 175 |
| person decisions recorded | decided approvals whose record is accepted or rejected | 100% of 28 | 100% of 148 |
| reason where required | rejections and overrides that keep the reason | 100% of 7 | 100% of 76 |
| refused without a reason | of those, refused when first sent without one | 100% of 7 | 100% of 76 |
| traceable to a step | records whose PROV export derives them from a step's message | 100% of 56 | 100% of 230 |
| notification attempts recorded | expected attempts against rows in the log | 100% of 178 | 100% of 577 |
| traceable to evidence (no target) | the message or its reviews cite evidence | 64% of 56 | 76% of 230 |

Notification attempts on the scenarios: 89 sent, 47 failed, 42 skipped. The failing notifier is
paused after three failures in a row, so later attempts to it are recorded as skipped.

## What it shows

- Every measure with a target reaches 100%. Without a reason, a rejection or an override is
  refused, so no person's decision on a challenged item goes unexplained.
- **Evidence is the open gap.** Some gate and report decisions cite no evidence themselves
  (10 of 46 on the scenarios: 6 gate and 4 report decisions), and their reviews cite none
  either. The record shows the gap; closing it means the agents should cite the
  signals they used. This is left for later work.

## Closing the evidence gap (target set before the change)

Gate decisions (A6) and reports (A5) are the decisions that cite nothing. A gate rests on tracker
fields (start date, deadline, tasks, planned finish, progress), and a report rests on the
messages it summarises (risks, gate reviews, lessons) and on each project's figures. The change
makes both agents cite those. The targets were committed before the change:

| measure | target |
|---|---:|
| traceable to evidence | 100% on the scenarios and on the review cases |
| cited evidence that resolves | 100%: every cited message is in the log, every cited tracker field exists on that project in the tracker, every cited lesson exists |
| every other measure above | still 100% |

A citation that points nowhere would raise the first measure without meaning anything, so the
second one is checked on every piece of evidence every record rests on.
