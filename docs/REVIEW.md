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

## Threads

Every message carries a conversation envelope (FIPA ACL `conversation-id`, `in-reply-to`,
`reply-by`): `conversation_id` is the run it was sent in (a new id outside a run), and a
`review.v1` verdict's `in_reply_to` is the decision it judges. `GET /messages/{id}/thread` returns
a message's conversation in time order with `replies` (a decision to its verdicts), and
`GET /messages?conversation=<run id>` lists one run's messages. Messages logged before 0.10 have
no envelope and come back alone.

## Decision records

Every decision leaves a record in MADR form (`GET /decisions`, filter by `kind`, `status` and
`subject`; `GET /decisions/{id}`):

- the commit gate writes one per agent decision: `committed`, or `proposed` while it waits for a
  person, with the evidence (`drivers`), the alternatives review offered (`options`), the
  proposing agent (`decision_makers`) and each reviewer's verdict (`consulted`);
- an approval turns it `accepted` or `rejected` and adds the approver and their reason
  (`outcome.justification`);
- publishing a workflow, setting a budget and deciding a replay recommendation are recorded too;
- fetched by id, a record lists whom it was told to (`informed`, from the communication log
  in docs/INTEGRATIONS.md);
- a newer decision on the same subject (the same project gate, say) marks the earlier one
  `superseded` and links to it.

In the dashboard, **Decision log** lists them (filter by kind, status and project) and shows one
in MADR order: context, drivers, options, outcome with the reason, consequences, decision
makers, consulted and informed, with a PROV-JSON download. On the approvals page each item has a
reason field; Reject, and Approve on a challenged decision, stay off until it is filled. A run's
view in Workflows shows its messages and notifications: each decision with the reviews that
answer it, and every notification attempt with its outcome.

`GET /decisions/{id}/provenance` exports one record as W3C PROV-JSON, so an auditor can check it
with standard PROV tools (for example the `prov` Python package, which reads it and prints
PROV-N):

- entities: the decision, the message it was made from, the reviews and the evidence they cite
  (other messages, tracker fields, lessons);
- activities: the run's steps, the commit gate or the person's approval;
- agents: A1-A8 as `prov:SoftwareAgent`, people as `prov:Person`;
- relations: `wasGeneratedBy`, `wasDerivedFrom`, `wasAssociatedWith`, `wasAttributedTo`,
  `wasInformedBy`.

A reason is required to reject, and to approve a decision a reviewer challenged (an override,
EU AI Act Art. 14(4)(d)). Without one `POST /approvals/{id}` returns 400; the approvals page asks
for it.

## Roles (RACI)

For each kind of decision (`gate`, `budget`, `allocation`, `risk`, `report`, `question`, ...,
or `*` for every kind) and each project (or all of them), people are **R**esponsible,
**A**ccountable, **C**onsulted or **I**nformed. Admins set them with `POST /roles`
`{kind, role, person, project}`. They are listed with `GET /roles`, resolved for one decision
with `GET /roles/who?kind=&project=`, and removed with `DELETE /roles/{id}`. The most specific
assignment wins: this kind in this project, then this kind everywhere, then `*` in this
project, then `*` everywhere.

- **Approvals go to A.** Once someone is Accountable for a decision, only they can approve or
  reject it; anyone else gets 403. Each queued item lists its `accountable`. With nobody
  assigned, anyone with the approver role decides, as before.
- **Notifications say who they are for.** `approval.requested` carries `recipients.decide` (A)
  and `recipients.consult` (C); `approval.resolved` carries `recipients.inform` (I).
- **Decision records name the people:** A among the decision makers, C among the consulted, I
  among the informed.
- **Commitments are owed by R to A.** A gate's conditions are owed by the Responsible and held
  by the Accountable, and a question is asked of the Responsible for `question`. Escalation's
  second step goes to the Accountable.

## Commitments

A decision can oblige someone to do something. Those obligations are kept as commitments: who
owes what to whom, by when (`GET /commitments`, filter by `state`, `debtor`, `project`).

- **Where they come from.** A conditional gate's conditions become commitments of the project
  team once the gate is in force: committed by the commit gate, or approved by a person. An
  approval can also attach conditions (`conditions: [{text, due, debtor}]`) and adopt an
  alternative that review offered (`adopt: [<message id>]`). An adopted "add 30 h/week until
  2026-W12" is due on that week's Friday.
- **States.** `conditional` until its antecedent holds, then `active`. From there it becomes
  `satisfied` when discharged, `violated` when cancelled by its debtor or when its due date
  passes, or `released` by its creditor (also after a violation, which ends the escalation). A
  conditional one that is cancelled becomes `cancelled`; one whose antecedent did not hold by
  `detach_by` becomes `expired`.
- **Operations.** `POST /commitments/{id}/{op}` with `detach`, `discharge` (with a
  `reference`), `cancel`, `release`, `delegate` (new debtor, `to`) or `assign` (new creditor,
  `to`). Each one is also a `commitment.v1` message in the decision's conversation, replying to
  it.
- **The tracker discharges what it can see.** `POST /commitments/check` re-runs the gate
  criterion behind each open gate condition and discharges the ones that now pass, citing the
  tracker.
- **Default due date.** Without a due date, a commitment is due `MA_PMO_COMMITMENT_DUE_DAYS`
  (14) days after the project calendar's today (`MA_PMO_REPORT_AS_OF` when set).
- **Due dates and escalation.** A sweep runs before every run, on every tracker webhook, from
  `POST /commitments/sweep`, and from `ma-pmo commitments sweep` (for cron). It moves overdue
  commitments to `violated`, then walks each violation along a chain, one step every
  `MA_PMO_COMMITMENT_ESCALATE_DAYS` (2):
  1. tell the debtor (`commitment.violated`);
  2. tell the accountable person, for now the creditor (`commitment.escalated`);
  3. reopen the decision (`decision.reopened`): its record becomes `reopened`, and it goes back
     to the approval queue with the missed obligation as the reason.

  Each step is a `commitment.v1` message and a notification, so the communication log shows
  it. A second sweep changes nothing, and a sweep after downtime takes every step that is due.
  A4 counts a project's violated commitments as a risk signal and rates the project high.

## Questions

An agent that lacks a fact it needs asks a person instead of guessing (A2A's input-required;
Horvitz's mixed-initiative principles). It may ask only for the facts on its reviewed list
(`core/questions.py`). For now that is A2 asking for a project's start date, since the critical
path is dated from it.

- **Only that step waits.** The asking step, and the steps that need it, wait; the others go on.
  The run ends as `input_required` and lists its questions.
- **Each question is a `question.v1` message and a commitment of the person asked** (kind
  `question`), so it is in the same list and follows the same due dates.
  `GET /questions` lists the open ones.
- **An answer resumes the run.** `POST /questions/{id}/answer` with `value` checks the answer
  against the question's type (`date`, `choice`, `yes_no`, `value`). The step runs again with it
  once no other question of the run is open.
- **No answer by the due date** (`MA_PMO_QUESTION_DUE_DAYS`, 3) **means the step uses the
  question's conservative default.** A2 plans from the as-of date, the latest start it can
  assume. That output is marked `unconfirmed`, and its message carries a confidence of 0.5 so a
  person sees it. The person asked, then the accountable person, are told; there is no decision
  to reopen.

## Builder review

When a workflow lets them read, two agents review their own output:

| Agent | Constraint | Holds when | Needs a readable |
|---|---|---|---|
| A6 | `gate.no_open_high_risk` | no risk alert for the project is high or critical | A4 step |
| A6 | `gate.staffed` | the allocation leaves none of the project's work unstaffed | A3 step |
| A6 | `gate.allocation_by_deadline` | the project's last planned week is not after its deadline week | A3 step |
| A5 | `report.covers_risks` | every project A4 rated medium or above is among the key risks | A4 step |

A6 posts one verdict per constraint and project next to each gate decision; the decision itself
does not change. A check judges the project, so whether it disagrees depends on the decision: for a
gate that *failed*, a broken constraint agrees with it and is `VERIFIED` on the same evidence (a
challenge would read as if the decision were wrong); A8 does the same. A5 checks itself before publishing: a missing risk is added to the key risks,
then the verdict is posted. A constraint whose source step is not readable is not checked, and no
verdict is posted for it: not checked is not the same as verified.

A step reads only what its workflow grants. Every reviewed workflow (the default, below) grants
A5 and A6 their `upstream`; any step can be given a mode explicitly:

```json
{"id": "A6", "agent": "A6", "needs": ["A3", "A4"], "reads": "upstream",
 "params": {"gate": "G3-execution"}}
```

## Dedicated review: A8 Auditor

Every run is reviewed unless its workflow says `"review": false` (on by default since the
[evaluation](REVIEW-EVAL.md)). When the run starts, the workflow is extended
(`WorkflowSpec.with_review`, saved with the run, so its graph shows it):

- isolated A5 and A6 steps read `upstream`, so they review their own decisions as above;
- an **A8 Auditor** step waits for every last step and reads the whole `board`.

A8 has no task of its own and decides nothing. It posts `role: dedicated` verdicts on every gate
decision and report on the board, using the same constraints as the builders but reading every
earlier stage, so it can check what a builder could not reach (for example a gate step that does
not wait for A3). It reads decisions and their sources only, never the builders' verdicts, and
where the two differ both stay on the board. A1 never routes a goal to A8.

```json
{"id": "quick_status", "review": false, "steps": [...]}
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

## Alternatives

Off by default (`MA_PMO_REVIEW_ALTERNATIVES=true` turns them on): the [evaluation](REVIEW-EVAL.md)
found they change nothing about what commits. When on, for every gate decision A8 challenges, it
also posts what a person could decide instead
(`ALTERNATIVE` verdicts with an `alternative` describing it), worked out from the posts behind the
challenge:

| Challenge | Alternative | Worked out from |
|---|---|---|
| `gate.no_open_high_risk` | pass on condition of A4's mitigation | the risk alert |
| `gate.staffed` | add N hours a week of the missing skill until the deadline | unstaffed hours, weeks to the deadline |
| `gate.allocation_by_deadline` | move the deadline to the week A3's plan ends, or add N hours a week | the plan's late hours, weeks to the deadline |

When they are on, a challenged decision needs at least one alternative before it can be decided;
without one, the held item lists `alternative` as missing. The approval item shows the alternatives next to the
challenges. They are offers for the person who decides, not decisions: nothing is changed by them.

The outcome per decision is saved with the run (`commit` in its state and in the scenario result).
In the 0.6.0 spike's ten portfolio variants, all nine gate conflicts are held with both reviewers'
challenges attached, the two report conflicts are fixed by A5 before the report commits, and the
controls are committed without asking anyone.

## In the dashboard

- **Approvals:** a held decision shows **Review pending**, and under it the challenges (constraint,
  reviewer, rationale and the posts they cite), the alternatives offered, and what was not
  checked.
- **Workflows:** the step table has a **Reads** column; pick a finished run to see its **Board**:
  each step's read mode, what it could read, how many posts and verdicts it made, and every
  decision committed or held (held ones link to the approval queue). A reviewed workflow says so
  next to its version.
- **Editor:** each step has a **Reads** menu, and **Review every run** turns `review` on.

Rationales and alternative summaries are written in the language the run ran in; constraint
names and labels follow the reader's language.

## Where MA-PMO differs

- Agents are mostly deterministic and already isolated, so the read side is what MA-PMO adds:
  reading is granted per step, publishing is always allowed.
- Checks are rules over posted data, not LLM judgements, so a verdict cannot claim support that
  is not on the board.
- ArcticSwarm opens an alternative or contrarian search before any answer commits; MA-PMO can
  offer alternatives for challenged decisions, worked out from the board without an LLM, and
  leaves them off by default because the evaluation found they change no commit. No LLM
  contrarian is built: the same evaluation would have to show it changes decisions for its cost.
- When the commit gate's conditions are not met, ArcticSwarm spawns the missing reviews and, at a
  deadline, lets the conditions become advisory. MA-PMO sends the decision to a person instead and
  reports what is missing, so a run stays the static, resumable workflow it started as and a
  high-stakes decision never commits by timeout.

The evaluation of each part, and the decisions it led to, is in [REVIEW-EVAL.md](REVIEW-EVAL.md).
Whether every decision leaves a complete record is measured in [RECORDS-EVAL.md](RECORDS-EVAL.md).

## Acknowledgement

The gated board, the builder and dedicated reviews with per-constraint verdicts, the commit gate
and the alternatives follow *ArcticSwarm: Deferring Early Consensus in Long-Horizon Multi-Agent
Research* by Soyoung Yoon, Boyi Liu, Yite Wang, Ruofan Wu, Canwen Xu, Nikki Lijing Kuang,
Seung-won Hwang, Yuxiong He and Zhewei Yao (2026), [arXiv:2609.01870](https://arxiv.org/abs/2609.01870),
licensed CC BY 4.0. MA-PMO implements these ideas independently for project management; it
contains no code from the ArcticSwarm repository.
