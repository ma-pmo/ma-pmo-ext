# Lab 6 — Calibrate the approval gate

**English | [한국어](README.ko.md)** · Lecture: [08 Operating agents](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/08-operating-agents.md)

The approval gate sends low-confidence messages to a person. That is only a safeguard if an
agent's confidence means something. In this lab you measure it and pick a threshold the way a
PMO would: limited review time, and as few wrong outputs as possible slipping through.

**You will practice:** the Brier score, expected calibration error, and turning a metric into an
operating decision under a budget.

## Files

- `calibrate.py` — `brier(pairs)`, `ece(pairs, bins=10)`, `choose_threshold(pairs, max_review)`.
  Each pair is `(confidence, was_right)`.

## Steps

1. **Brier score** — the mean of `(confidence − outcome)²` with outcome 1 when right, 0 when wrong.
2. **ECE** — split confidence into 10 equal bins (the last also takes 1.0). For each non-empty
   bin add *share of samples × |accuracy − mean confidence|*. A model that says 0.8 and is right
   80% of the time contributes 0.
3. **Threshold** — a message goes to a person when `confidence < threshold`; a wrong output slips
   through when `confidence ≥ threshold`. Among the candidates that keep reviews within
   `max_review`, return the one with the fewest slips (ties: the lower threshold). Raise
   `ValueError` when none fits.
4. Compare with `ma-pmo eval` → `[calibration]` on the demo data (run a scenario with A4 first).

## Check

```bash
ma-pmo learn check 6
```

## Think about it

On the demo data A4 always reports 0.85, so its confidence is *uninformative*: no threshold can
separate its right and wrong alerts. What would you change in A4 — and why is "make the LLM say
a number" not enough?
