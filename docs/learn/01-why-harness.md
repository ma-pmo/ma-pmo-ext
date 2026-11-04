# 1. Why agents fail, and what a harness is

**English | [한국어](01-why-harness.ko.md)** · [Course map](README.md)

## Goal

Name the ways an LLM agent fails in an organization, and see which part of MA-PMO exists to
catch each one.

## The problem

An agent demo answers one question well, once. An agent *system* runs every day, on real
data, with other agents, and its output changes decisions about people and money. In that
setting the model is rarely what breaks. What breaks is everything around it:

| Failure | What it looks like in a PMO |
|---|---|
| Free-form output | the report agent writes "risk: moderate-ish" and the next agent cannot parse it |
| Silent drift | a prompt change makes risk alerts rarer; nobody notices for a month |
| Outage | the API key expires on Monday and the weekly status report never arrives |
| Overreach | an agent reallocates a team because its confidence was 0.41 |
| Unverifiable claims | "agents cut reporting time" — compared to what, measured how? |
| Brittle integrations | the Slack webhook is wrong and the whole pipeline throws |

## The harness

A **harness** is the engineering around the model that makes these failures visible,
contained or impossible. In MA-PMO it has six parts, one per remaining lecture:

```
           goal ─▶ A1 orchestrator ─▶ A2…A7 workers ─▶ synthesis ─▶ report
                     │      ▲              │
  contracts (2)  ────┘      │              ├──▶ audit log (2)
  fallbacks (3)  ───────────┘              ├──▶ approval queue (4)
  measurement (5) ◀── KPI telemetry ◀──────┤
  experiments (6) ── run scenarios, ablate agents
  integrations (7) ◀── events / tracker data (failure-isolated)
```

A useful test for every part: *if this were missing, how would we find out something went
wrong?* If the answer is "a user complains", the harness has a gap.

## In MA-PMO

- The agents: `ma_pmo/agents/` — A1 orchestrator, A2 planning (CPM), A3 resources, A4 risk,
  A5 reporting, A6 governance (stage gates), A7 knowledge (lessons learned with citations).
- The run: `ma_pmo/core/scenarios.py` executes a scenario in four phases — plan, execute,
  complete, insight — and records what each agent produced and how long it took.

## Try it

```bash
ma-pmo serve &                       # API on :8000
curl -s -X POST localhost:8000/scenarios/quarterly_review/run | python -m json.tool | head -60
```

Find in the output: which agents A1 delegated to, the schema of each result
(`schedule.v1`, `risk_alert.v1`, `report.v1`), and the KPI records in the insight phase.

## Checkpoint

1. Pick one row of the failure table. Which file in MA-PMO prevents or detects it?
2. Why is "the model got smarter" not a fix for silent drift?
3. Which failures can a unit test catch, and which need measurement over time?

Next: [2. Structured messages as contracts](02-structured-messages.md)
