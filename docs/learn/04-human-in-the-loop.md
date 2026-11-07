# 4. Human-in-the-loop gates

**English | [한국어](04-human-in-the-loop.ko.md)** · [Course map](README.md)

## Goal

Decide which agent decisions must wait for a person, implement the gate in the message
protocol, and measure what it costs.

## Concept

Autonomy is not all-or-nothing. A good gate is:

- **Targeted** — only some decisions wait: high-impact (budget, scope, staffing, external
  communication) or low-confidence ones.
- **Built into the protocol** — not a UI afterthought. The message itself says it needs a
  person, so no consumer can skip the check.
- **Auditable** — who approved, when, and what they saw.
- **Measured** — approvals take time. Approval latency is a cost you track like any other.

## In MA-PMO

- `AgentMessage.needs_human_gate(threshold)` (`ma_pmo/core/schemas/message.py`): true when the
  sender set `human_gate_required` **or** `confidence` is below `HITL_CONFIDENCE_THRESHOLD`
  (default 0.6).
- `protocol.publish()` stores the message and, when gated, adds a `pending` approval.
- `ma_pmo/core/hitl.py` — `list_pending()` and `resolve(approval_id, approver, decision)`.
- API: `GET /approvals`, `POST /approvals/{id}`; dashboard: **Approvals** in the sidebar, with
  a badge counting what is pending.
- Integrations announce `approval.requested` and `approval.resolved` (lecture 7), so the gate
  reaches people where they already are.

## Try it

```bash
curl -s -X POST localhost:8000/demo/gated-message      # a low-confidence proposal
curl -s localhost:8000/approvals | python -m json.tool  # it is waiting
```

Open the dashboard (`make web`, then http://localhost:3000/approvals), approve it, and watch
the badge count drop.

## Does the run actually wait?

By default a run queues its approval and carries on, which suits reports and demos. With
`POST /scenarios/{id}/run?pause_on_gate=true` (or `"pause_on_gate": true` on `/orchestrate`) it
stops after the gated step
(`waiting_approval`): approving resumes from the next step, rejecting cancels the run. The state
is in the database, so the wait survives an API restart (`ma_pmo/core/runs.py`).

## Who approved?

With API authentication on (`MA_PMO_AUTH_MODE=api_key`), only keys with the `approver` role can
resolve approvals, and the recorded approver is the authenticated user — not whatever name the
request body carries. See [docs/AUTH.md](../AUTH.md).

## Choosing the threshold

Too low and risky actions slip through; too high and people rubber-stamp a flood of requests
— which is worse, because it *looks* safe. Start strict, measure approval volume and how often
people reject, then relax per decision type. Rejections are data: they show where an agent is
miscalibrated. [Lecture 8](08-operating-agents.md) measures exactly that.

## Checkpoint

1. A3 proposes moving one person between two projects at confidence 0.82. Gate it or not?
   What if the person is the only data engineer?
2. Why put `human_gate_required` in the message rather than in the dashboard code?
3. Which KPI would tell you the approval queue has become a bottleneck?

Next: [5. Measuring agents](05-measuring-agents.md)
