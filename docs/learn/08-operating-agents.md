# 8. Operating agents: identity, traces, calibration

**English | [한국어](08-operating-agents.ko.md)** · [Course map](README.md) · Lab: [Calibrate the approval gate](../../ma_pmo/learn/labs/lab6_calibration/README.md)

## Goal

Run an agent system that other people depend on: know *who* did what, *why* a run behaved as it
did, and whether the safety gate actually filters the risky outputs.

## Concept

Lectures 2–4 built the controls. Operating them needs three more things:

1. **Identity.** An approval is only an audit record if it says who approved — and that person
   cannot be typed into a request body. Authentication turns "approver: alice" from a claim into
   a fact.
2. **Traces.** When quality drops on a Tuesday, logs tell you *that* something happened; a trace
   shows the run as a tree — workflow → agent → LLM call — with the failures and fallbacks on
   the exact step. Fallbacks that are only logged get noticed late.
3. **Calibration.** A confidence threshold filters risk only if confidence tracks correctness.
   Measure it (ECE, Brier), look at how many distinct values an agent ever reports, and choose
   the threshold from a table of *reviews vs. errors that slip through*, not by feel.

## In MA-PMO

- **Identity** — `ma_pmo/api/auth.py`: `MA_PMO_AUTH_MODE=api_key|custom`, roles `viewer`,
  `operator`, `approver`, `admin`; with auth on, the approver recorded on a decision is the
  authenticated user. The dashboard top bar warns while auth is off. Guide:
  [docs/AUTH.md](../AUTH.md).
- **Traces** — `ma_pmo/core/tracing.py`: `OTEL_ENABLED=true` turns each scenario run into
  `invoke_workflow` → `invoke_agent` → `chat` spans; failed LLM calls are errors and fallbacks
  set `ma_pmo.fallback=true`. Jaeger in one command: [infra/otel](../../infra/otel/README.md).
- **Calibration** — `ma_pmo/eval/calibration.py`: A4 risk alerts against labels and resolved
  approvals; verdicts calibrated / overconfident / underconfident / *uninformative* /
  insufficient, plus a threshold table. Shown by `ma-pmo eval`, the report and the Evaluation
  page.

## Try it

```bash
OTEL_ENABLED=true ma-pmo harness a7_ablation 2> spans.txt    # spans on stderr
grep -c '"ma_pmo.fallback": true' spans.txt                  # fallbacks this run

curl -X POST localhost:8000/scenarios/risk_escalation/run   # A4 alerts with a confidence
ma-pmo eval | sed -n '/\[calibration\]/,$p'
```

## Pitfalls

- **Auth only at the edge.** A proxy that authenticates but forwards an unsigned "user" header
  anyone can set is no identity. Trust a forwarded header only if the API is reachable solely
  through that proxy.
- **Recording prompts in traces.** Prompts can hold personal or confidential data; MA-PMO's
  spans carry ids, models, token counts and fallbacks, not text.
- **Confidence as a constant.** A deterministic agent that always reports 0.85 looks calibrated
  on average and still cannot separate good from bad alerts. Report *distinct values*, not only
  ECE.
- **Tuning on approvals alone.** Only gated messages ever get approved or rejected, so that
  sample is biased toward low confidence; keep a labeled sample too.

## Lab

[Lab 6 — Calibrate the approval gate](../../ma_pmo/learn/labs/lab6_calibration/README.md):
`ma-pmo learn start 6`. Implement Brier and ECE, then choose a threshold within a review budget.

## Checkpoint

1. Your team can review 10 proposals a week. The threshold table shows 0.8 → 9 reviews / 3
   slipped and 0.9 → 14 reviews / 0 slipped. What do you do?
2. Which span attribute would you alert on to catch "the LLM has been down since 9am"?
3. Why must the approver be taken from the authenticated request rather than the request body?

Back to the [course map](README.md).
