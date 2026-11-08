# Reviews and evidence

**English | [한국어](REVIEW.ko.md)**

MA-PMO's agents gather their findings apart: each reads its own data, and by default no step sees
what another published. That keeps one agent's early conclusion from steering the others, but it
also means nobody checks one agent's decision against another's findings. A gate could pass a
project that the risk agent had just rated high. This page describes how decisions are checked
against what other steps published, with evidence a person can follow.

The design follows ArcticSwarm (Yoon et al., 2026, *ArcticSwarm: Deferring Early Consensus in
Long-Horizon Multi-Agent Research*, [arXiv:2609.01870](https://arxiv.org/abs/2609.01870)): gather
evidence in isolation, publish it to one board, and review it before anything is committed. It is
an independent implementation for project management; see [where MA-PMO differs](#where-ma-pmo-differs).

## Reading the board

A workflow step declares what it may read with `reads` (see
[PLUGINS.md](PLUGINS.md#what-a-step-may-read)): `isolated` (the default), `upstream` or `board`.
The executor enforces it: an isolated step's state has no `board`. A step that may read also gets
`board_steps`, the steps it may read including those that published nothing, so "A4 found no
risk" is not confused with "A4 did not run". `GET /runs/{id}/board` shows a run's posts and what
each step could read.

## Verdicts: `review.v1`

A review judges one **constraint** of one post and cites its evidence:

| Field | Meaning |
|---|---|
| `target` | the `message_id` under review |
| `constraint` | what is checked, e.g. `gate.no_open_high_risk` |
| `verdict` | `VERIFIED`, `CHALLENGE` (the constraint fails) or `ALTERNATIVE` (something else could be decided) |
| `role` | `builder` (the agent that made or consumes the output) or `dedicated` (a reviewer with no task of its own) |
| `evidence` | references: `message`, `tracker` (with `field`), `knowledge`, or `step` (a step that ran and published nothing about it) |

`VERIFIED` and `CHALLENGE` must cite evidence; `ALTERNATIVE` must describe the alternative.

## Builder review

When a workflow lets them read, two agents review their own output:

| Agent | Constraint | Holds when | Needs a readable |
|---|---|---|---|
| A6 | `gate.no_open_high_risk` | no risk alert for the project is high or critical | A4 step |
| A6 | `gate.staffed` | the allocation leaves none of the project's work unstaffed | A3 step |
| A6 | `gate.allocation_by_deadline` | the project's last planned week is not after its deadline week | A3 step |
| A5 | `report.covers_risks` | every project A4 rated medium or above is among the key risks | A4 step |

A6 posts one verdict per constraint and project next to each gate decision; the decision itself
does not change. A5 checks itself before publishing: a missing risk is added to the key risks,
then the verdict is posted. A constraint whose source step is not readable is not checked, and no
verdict is posted for it: not checked is not the same as verified.

Built-in workflows keep every step isolated for now, so nothing changes unless a workflow sets
`reads`. Example:

```json
{"id": "A6", "agent": "A6", "needs": ["A3", "A4"], "reads": "upstream",
 "params": {"gate": "G3-execution"}}
```

## Dedicated review: A8 Auditor

`"review": true` on a workflow has every run reviewed. When the run starts, the workflow is
extended (`WorkflowSpec.with_review`, saved with the run, so its graph shows it):

- isolated A5 and A6 steps read `upstream`, so they review their own decisions as above;
- an **A8 Auditor** step waits for every last step and reads the whole `board`.

A8 has no task of its own and decides nothing. It posts `role: dedicated` verdicts on every gate
decision and report on the board, using the same constraints as the builders but reading every
earlier stage, so it can check what a builder could not reach (for example a gate step that does
not wait for A3). It reads decisions and their sources only, never the builders' verdicts, and
where the two differ both stay on the board. A1 never routes a goal to A8.

```json
{"id": "risk_review", "review": true, "steps": [...]}
```

## Commit gate

At the end of a reviewed run, every decision on the board (each gate review and report) is
checked before it takes effect:

1. no reviewer, builder or dedicated, CHALLENGEs it;
2. every constraint that applies has a VERIFIED verdict from A8. A constraint applies when the
   agent it rests on ran in this run (A4 for risks, A3 for staffing and allocation).

A decision that meets both is **committed**. Any other is **review pending**: it goes to the
approval queue (`GET /approvals`), and the item's `review` lists the challenges with their
rationale and evidence, and the constraints nobody could check (`missing`; for example the
allocation check of a project with no deadline). A decision that already needed approval, such as
a failing gate, keeps its one approval, which gains the same detail. Approving or rejecting it is
an ordinary decision; the finished run stays as it is. Passing review never replaces an approval
that was required anyway.

The outcome per decision is saved with the run (`commit` in its state and in the scenario result).
In the 0.6.0 spike's ten portfolio variants, all nine gate conflicts are held with both reviewers'
challenges attached, the two report conflicts are fixed by A5 before the report commits, and the
controls are committed without asking anyone.

## Where MA-PMO differs

- Agents are mostly deterministic and already isolated, so the read side is what MA-PMO adds:
  reading is granted per step, publishing is always allowed.
- Checks are rules over posted data, not LLM judgements, so a verdict cannot claim support that
  is not on the board.
- When the commit gate's conditions are not met, ArcticSwarm spawns the missing reviews and, at a
  deadline, lets the conditions become advisory. MA-PMO sends the decision to a person instead and
  reports what is missing, so a run stays the static, resumable workflow it started as and a
  high-stakes decision never commits by timeout.

Coming next (Roadmap 7, [#71](https://github.com/ma-pmo/ma-pmo-ext/issues/71)): alternatives
for high-risk decisions, and the review shown in the dashboard.
