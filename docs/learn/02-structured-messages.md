# 2. Structured messages as contracts

**English | [한국어](02-structured-messages.ko.md)** · [Course map](README.md)

## Goal

Understand why agents in MA-PMO talk in validated, versioned messages instead of chat, and
what the append-only log buys you.

## Concept

Between two agents, free text is an API with no specification. It works until one side
rephrases. A **contract** fixes three things:

1. **Shape** — which fields exist and their types (validated, not hoped for).
2. **Version** — `risk_alert.v1`; a breaking change becomes `v2`, and both can coexist.
3. **Metadata** — who sent it, to whom, why (`intent`), about what (`task_ref`), and how sure
   the sender is (`confidence`).

Natural language still has a place — inside a field such as a report summary — but the
envelope around it is machine-checked.

## In MA-PMO

- `ma_pmo/core/schemas/message.py` — `AgentMessage` with `sender`, `receiver`, `intent`
  (`request` / `inform` / `propose` / `approve`), `task_ref`, `payload`, `confidence`,
  `human_gate_required`. `MessagePayload` rejects a schema name without a version.
- `ma_pmo/core/schemas/payloads/` — one Pydantic model per payload (`schedule.v1`,
  `risk_alert.v1`, `report.v1`, …). `protocol.validate_payload` checks the data against it.
- `ma_pmo/core/protocol.py` — `publish()` validates, appends the message to an
  **append-only** table, and queues it for approval when needed (lecture 4).
- `BaseAgent.structured()` (`ma_pmo/agents/base.py`) asks the LLM for output that must parse
  into the agent's schema — the same contract applies to model output.

## Why append-only

An audit log you can edit is a diary. Append-only means every decision can be replayed: who
proposed what, with which confidence, and what happened after. Later state (approved,
rejected) is recorded *next to* the message, never by changing it.

## Try it

```bash
curl -s 'localhost:8000/messages?task_ref=PORTFOLIO%232026-Q1' | python -m json.tool | head -40
```

Then break a contract on purpose in a Python shell:

```python
from ma_pmo.core.schemas.message import MessagePayload
MessagePayload(schema="risk_alert", data={})   # ValueError: version required
```

## Pitfalls

- **Optional everything.** A schema where every field is optional validates garbage.
- **Versioning by accident.** Renaming a field in place breaks old consumers; add `v2`.
- **Confidence as decoration.** If nothing reads `confidence`, it is noise. In MA-PMO it
  decides whether a person must approve (lecture 4).

## Checkpoint

1. A4 wants to add `mitigation_owner` to risk alerts. New version or not? Why?
2. What does the audit log let you answer that application logs do not?
3. Where would a malformed LLM output be caught, and what happens next? (Lecture 3.)

Next: [3. Deterministic fallbacks](03-offline-fallbacks.md)
