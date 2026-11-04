# 7. Integrations and failure isolation

**English | [한국어](07-integrations.ko.md)** · [Course map](README.md) · Labs: [Notifier](../../ma_pmo/learn/labs/lab1_notifier/README.md) · [Tracker](../../ma_pmo/learn/labs/lab4_tracker/README.md)

## Goal

Connect agents to the tools an organization already uses — chat, webhooks, issue trackers —
through narrow plugin contracts, so that a broken integration can never take the agents down.

## Concept

Integrations face both ways:

- **Outbound (notifiers)** — events leave the system: "approval requested", "high risk
  detected", "gate failed", "report ready".
- **Inbound (trackers)** — data enters the system: projects, tasks, progress, dependencies.

Two rules keep them safe:

1. **Narrow seams.** A notifier has `name` and `send(event)`. A tracker has
   `get_portfolio_status(portfolio_id) -> dict`. Agents depend on the seam, never on Slack or
   Jira, so integrations can be swapped, mocked and tested alone.
2. **Best-effort delivery.** A notifier failure is caught and *recorded* by the dispatcher —
   the agent run continues. The notifier itself must not swallow errors, or nobody learns the
   webhook is broken.

## In MA-PMO

- `ma_pmo/integrations/base.py` — `Event`, `EventType`, the `Notifier` protocol and
  `IntegrationSpec` (name, kind, required settings, factory).
- `ma_pmo/integrations/registry.py` — built-ins (Slack, webhook, Jira) plus plugins from the
  `ma_pmo.integrations` entry-point group; enabled with `MA_PMO_INTEGRATIONS=slack,jira`;
  falls back to demo data when no tracker is active.
- `ma_pmo/integrations/dispatch.py` — `emit()` sends each event to each notifier and returns
  one `ok: true/false` row per attempt.
- `ma_pmo/connectors/jira_mock.py` and `ma_pmo/integrations/jira.py` — two trackers that return
  the same shape from different sources.
- `GET /integrations` shows what is enabled and configured (never secret values);
  `POST /integrations/{name}/test` sends a test event.

## Try it

```bash
curl -s localhost:8000/integrations | python -m json.tool
MA_PMO_INTEGRATIONS=webhook MA_PMO_WEBHOOK_URL=http://localhost:9/nowhere ma-pmo serve --port 8001 &
curl -s -X POST localhost:8001/integrations/webhook/test   # fails, and the API keeps running
```

## Pitfalls

- **Retry storms.** Retrying a dead webhook inside an agent run turns one outage into slow
  agents everywhere. Fail fast with a timeout; retry, if at all, outside the run.
- **Leaking secrets.** Status endpoints list *which* settings are missing, never their values.
- **Exceptions as "not found".** A tracker asked for an unknown portfolio returns
  `found: False` — data the agents can reason about — not a crash.

## Labs

- [Lab 1 — Write a notifier plugin](../../ma_pmo/learn/labs/lab1_notifier/README.md):
  `ma-pmo learn start 1`.
- [Lab 4 — Build a custom tracker](../../ma_pmo/learn/labs/lab4_tracker/README.md):
  `ma-pmo learn start 4`.

## Checkpoint

1. Your Slack notifier times out after 5 seconds on every event. What does a scenario run
   look like? What do the logs show?
2. Why does `IntegrationSpec` list required *setting names* instead of reading values itself?
3. A teammate wants A4 to call Jira directly "just this once". What do you lose?

You have finished the course. Back to the [course map](README.md) — and consider contributing
a lab of your own.
