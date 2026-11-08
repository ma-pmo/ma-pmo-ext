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

## Where MA-PMO differs

- Agents are mostly deterministic and already isolated, so the read side is what MA-PMO adds:
  reading is granted per step, publishing is always allowed.
- Checks are rules over posted data, not LLM judgements, so a verdict cannot claim support that
  is not on the board.

Coming next (Roadmap 7, [#71](https://github.com/ma-pmo/ma-pmo-ext/issues/71)): a dedicated
reviewer, a commit gate that sends unreviewed or challenged decisions to a person, and
alternatives for high-risk decisions.
