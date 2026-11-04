# Lab 4 — Build a custom tracker

**English | [한국어](README.ko.md)** · Lecture: [07 Integrations and failure isolation](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/07-integrations.md)

Agents never read Jira, a database or a spreadsheet directly. They call one method,
`get_portfolio_status(portfolio_id)`, and get back a plain dict. That narrow seam is what lets
MA-PMO run on demo data, Jira or — after this lab — a folder of CSV files.

**You will practice:** implementing a data contract exactly, handling "not found" as data
instead of an exception, and proving the integration works by feeding it to a real agent
algorithm (A2's critical-path method).

## Files

- `csv_tracker.py` — the only file you edit.
- `data/` — portfolio.csv, projects.csv, tasks.csv in the evaluation template layout.

## Steps

1. **Not found.** If `portfolio_id` is not in portfolio.csv, return
   `{"portfolio_id": ..., "found": False, "projects": []}`.
2. **Tasks.** Each tasks.csv row becomes `{"task_id", "wbs", "effort", "deps",
   "percent_complete"}`. Numbers are floats; `deps` is a list split on `;` (`[]` when empty).
3. **Projects.** One dict per project with `project_id`, `skill`, `status`, `planned_start`,
   `planned_finish`, `deadline`, its `tasks`, and `percent_complete` weighted by effort
   (Σ effort × % ÷ Σ effort), rounded to one decimal.
4. **Portfolio.** Return `portfolio_id`, `name`, `period`, `found: True` and `projects`.
   Compare with `ma_pmo/connectors/jira_mock.py`, which builds the same shape from the DB.
5. **Spec.** Set `SPEC.kind` to `"tracker"`.

## Check

```bash
ma-pmo learn check 4
```

The last check runs the planning agent's CPM on your output and expects the critical path
T-1401 → T-1402 → T-1403.

## Think about it

What should happen when tasks.csv mentions a project that projects.csv does not have? Where
would you report it so a PMO notices — and why not in the middle of an agent run?
