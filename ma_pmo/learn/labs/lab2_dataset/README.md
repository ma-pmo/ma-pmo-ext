# Lab 2 — Repair an organization dataset

**English | [한국어](README.ko.md)** · Lecture: [05 Measuring agents](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/05-measuring-agents.md)

A PMO exported its portfolio to the evaluation template, but the export has mistakes. An
evaluation on broken data produces confident-looking numbers that mean nothing, so the
harness refuses to run until the data validates. Your job: make it validate **without
throwing data away**.

**You will practice:** reading validator output, fixing data at the source, and why ground
truth labels decide whether a metric like H3 (risk detection) is meaningful.

## Files

- `data/*.csv`, `data/baselines.json` — the export (same layout as `ma-pmo template data`).

## Steps

1. Run the validator and read every message:
   ```bash
   ma-pmo template validate learn/lab2/data
   ```
2. Fix each error in the CSV files (any spreadsheet or text editor works). There are seven:
   an impossible date, a percentage over 100, a duplicated task id, a dependency cycle, a
   dependency on a task that does not exist, a weekly capacity over 168 hours, and a risk
   severity that is not on the allowed list.
3. Repair rows instead of deleting them: the duplicated `T-102` row is really `T-103`
   (WBS 1.3, after T-102); `T-320` is a typo; ACME-2 starts with `T-201`.
4. When validation passes, evaluate your data in its own database:
   ```bash
   ma-pmo eval --data learn/lab2/data
   ```

## Check

```bash
ma-pmo learn check 2
```

## Think about it

H3 compares the risk agent against `risk_labels.csv`. What happens to precision and recall
if a project has no label, or the label is wrong? Why does the validator warn about a
missing label instead of guessing one?
