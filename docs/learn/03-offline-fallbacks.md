# 3. Deterministic fallbacks: offline first

**English | [한국어](03-offline-fallbacks.ko.md)** · [Course map](README.md)

## Goal

Design agent steps that keep working when the model is unavailable, slow or wrong — and see
why that also makes the system testable.

## Concept

Every LLM step in MA-PMO has a **deterministic twin**: rules, algorithms or templates that
produce a valid output of the same schema. The LLM path improves the result; the fallback
guarantees there is one.

```
try:   output = llm.complete_structured(prompt, Schema)   # better wording, judgment
except: output = rules(data)                              # always valid, always on time
```

Three things follow:

1. **Availability** — a missing key or a provider outage degrades quality, not service.
2. **Testability** — CI runs the whole pipeline with no network and gets the same answer twice.
3. **A baseline** — the fallback is the "no LLM" arm of an experiment for free.

Some steps should *never* be an LLM call. Critical-path scheduling is arithmetic; MA-PMO
computes it with CPM (`ma_pmo/agents/cpm.py`), not a prompt.

## In MA-PMO

- `ma_pmo/agents/orchestrator.py` → `orchestrator_rules.py`: rule-based routing and synthesis
  when the LLM call fails (look for `route_fallback`, `synthesize_fallback` in the logs).
- `ma_pmo/agents/reporting.py`: `_fallback_report()` builds the executive report from data.
- `ma_pmo/agents/knowledge.py`: an extractive answer from the lessons-learned corpus, with
  citations, when generation is unavailable.
- `ma_pmo/agents/cpm.py`, `allocation.py`, `gates.py`, `risk_signals.py`: deterministic cores.

## Try it

Run the evaluation with no key at all:

```bash
env -u ANTHROPIC_API_KEY ma-pmo eval
```

Every hypothesis still gets a number. Now read `ma_pmo/agents/reporting.py` and find the
`except` that keeps the report coming.

## Seeing fallbacks

With `OTEL_ENABLED=true` every fallback is marked on its trace span (`ma_pmo.fallback=true` plus
a `fallback` event), next to the failed LLM call that caused it — see
[lecture 8](08-operating-agents.md) and [infra/otel](../../infra/otel/README.md).

## Pitfalls

- **Catching too much.** A fallback must catch *the LLM failing*, not bugs in your own code.
  Log the error (as the orchestrator does) so fallbacks are counted, not hidden.
- **A fallback with a different shape.** It must return the same schema, or consumers break
  exactly when you can least afford it.
- **Never measuring the gap.** If you do not compare LLM and fallback output, you do not know
  what the LLM is worth — or whether it is worse.

## Checkpoint

1. Which A5 report fields would you allow the LLM to change, and which must always come from
   data?
2. How would you alert on "we have been on the fallback path all day"?
3. Why does a deterministic fallback make the regression tests in lecture 6 possible?

Next: [4. Human-in-the-loop gates](04-human-in-the-loop.md)
