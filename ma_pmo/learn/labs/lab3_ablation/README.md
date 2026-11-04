# Lab 3 — Design an ablation experiment

**English | [한국어](README.ko.md)** · Lecture: [06 Experiments and tests](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/06-experiments.md)

Hypothesis H4 says the knowledge agent (A7) improves decisions by bringing lessons learned
into the run. An **ablation** tests that claim directly: run the same scenarios with and
without A7 and compare what the system produces.

**You will practice:** turning a hypothesis into a runnable experiment, choosing scenarios
that can actually show the effect, and keeping experiments small and reproducible.

## Files

- `experiments/h4_knowledge.py` — the experiment you write.

## Steps

1. List the scenarios and the agents each one uses:
   ```bash
   ma-pmo learn scenarios
   ```
2. Pick **2 to 5 scenarios that call A7**. Removing an agent from a scenario that never uses
   it changes nothing — it would only dilute the result.
3. Add `.ablate("A7")` and `.repeat(n)` with `n` between 1 and 3. Offline runs are
   deterministic, so more repetitions add time, not information.
4. Replace the `TODO` description with one sentence on what the experiment measures.
5. Run it like any harness experiment (after `ma-pmo init-db`):
   ```bash
   MA_PMO_EXPERIMENTS_DIR=learn/lab3/experiments ma-pmo harness h4_knowledge
   ```

## Check

```bash
ma-pmo learn check 3
```

The last check runs your experiment and expects fewer findings when A7 is removed.

## Think about it

Fewer findings without A7 supports H4, but does not prove better *decisions*. What would
you measure next — and which part of that needs a human?
