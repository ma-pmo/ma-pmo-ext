# Commitment evaluation

**English | [한국어](COMMITMENTS-EVAL.ko.md)**

Whether the obligations decisions create ([REVIEW.md](REVIEW.md#commitments)) are noticed when
they are missed, and left alone when they are kept. Reproduce with:

```bash
ma-pmo eval --commitments
```

## Criteria (set before the first run)

These were written and committed before the evaluation was run. Each must hold for commitments
and questions to count as working; every one is a count that must be zero.

| criterion | what counts | target |
|---|---|---:|
| missed and unnoticed | commitments not kept by their due date that never became `violated`, or whose debtor was never told (no escalation step, no logged notification) | 0 |
| kept but marked missed | commitments kept on time that became `violated` | 0 |
| missed and not escalated | missed commitments whose chain did not reach the accountable person within two steps' time | 0 |
| missed and decision not reopened | missed gate or approval conditions whose decision was not back in the approval queue after three steps' time | 0 |
| needless questions | questions asked about a fact that was present | 0 |
| unmarked defaults | defaults used for unanswered questions without the output marked unconfirmed | 0 |

Also reported, without a target: the added work for people (questions and escalation messages
per run) and the time from creation to resolution.

## Cases

- **Conditions.** The demo portfolio on its own calendar (as of 2026-02-16), where PROJ-14 and
  PROJ-31 pass G3 on condition (blocked tasks). A person approves each gate and attaches a
  condition of their own. Each gate therefore yields a gate condition, discharged by the tracker
  once the blocked tasks' predecessors are done, and an approval condition, discharged by a
  person with a reference. Due dates are 3, 7 and 14 days.
- **Questions.** PROJ-22 without a start date, so A2 asks for it. Answers are due in 1, 3 and 5
  days. A control run keeps the start date, so no question should be asked.
- **Stakeholders.** For each case the person or tracker is *on time* (the day before the due
  date), *late* (two days after it) or *absent* (never). Days pass one at a time; each day the
  stakeholder acts if it is their day, then the tracker is checked and the due-date sweep runs.

Every case runs in a throwaway workspace on the deterministic path (no LLM).
