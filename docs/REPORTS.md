# Reports

**English | [한국어](REPORTS.ko.md)**

A5 writes a report at the end of every workflow that has a reporting step. Since roadmap 12
([#88](https://github.com/ma-pmo/ma-pmo-ext/issues/88)) each report is stored as `report.v2`: the
figures are computed by MA-PMO, and only the summary, risks and actions are written by the LLM (or
by rules without one). Reports can be listed, read and downloaded from the API and the CLI.

## Kinds

A PMO sends different reports to different people. The kind is set on the workflow's A5 step.

| kind | for | sections |
|---|---|---|
| `status` | the team and PMO, every period (a PRINCE2 highlight report) | summary, key figures, projects, tolerances, risks, actions |
| `executive` | sponsors, one page | summary, key figures, exceptions, decisions needed, actions |
| `exception` | the board, when a tolerance is breached | summary, exceptions, risks, actions |
| `gate` | a stage gate or go/no-go meeting | summary, decisions needed, risks, tolerances, actions |
| `closure` | closing a project or phase | summary, projects, decisions, lessons, actions |

Built-in workflows already pick one:

| kind | workflows |
|---|---|
| status | weekly_status, estimation_calibration |
| executive | executive_briefing, quarterly_review, portfolio_prioritization |
| exception | risk_escalation, burndown_alert |
| gate | go_nogo_decision, compliance_audit |
| closure | lessons_learned_closure |

In your own workflow:

```json
{"id": "A5", "agent": "A5",
 "params": {"kind": "exception", "audience": "executive", "projects": ["PROJ-31"],
            "as_of": "2026-02-16"}}
```

`audience` (`executive` or `team`) defaults to the kind's reader, `projects` makes a project report
instead of a portfolio report, and `as_of` reports as of a past date.

## What is computed, and how

| figure | rule |
|---|---|
| progress | the tracker's effort-weighted progress |
| SPI | earned value / planned value at the as-of date. Planned value spreads the total effort evenly from the planned start to the planned finish. None before the planned start. |
| forecast finish | planned start + planned duration / SPI (the usual earned-value time estimate) |
| slack | deadline − forecast finish; negative is late |
| tolerances | SPI below `MA_PMO_TOLERANCE_SPI` (0.9), or a forecast more than `MA_PMO_TOLERANCE_SLIP_DAYS` (0) past the deadline |
| overall status | the worst project status; at least amber when a tolerance is breached |
| change | every figure next to its value in the previous report of the same scope, kind and projects |
| risks, gate decisions, lessons | what A4, A6 and A7 posted in the same run, when the step may read them (review is on by default) |
| decisions needed | failed or conditional gates, and items waiting in the approval queue |

The LLM gets these figures and is told to use them. Checking that its sentences match them is the
next step of roadmap 12.

## Reading and downloading

```bash
ma-pmo report list                                  # newest first; --kind, --scope
ma-pmo report show latest --kind executive          # Markdown in the terminal
ma-pmo report export RPT-1a2b3c4d --format html --out report.html
```

| endpoint | returns |
|---|---|
| `GET /reports?kind=&scope=&limit=` | list, newest first |
| `GET /reports/latest?kind=&scope=` | the newest report |
| `GET /reports/{id}` | one report as report.v2 JSON |
| `GET /reports/{id}/export?format=md\|html\|csv\|json` | a download; `&inline=true` opens HTML in the browser |

Formats: Markdown for wikis and chat, HTML to read or print to PDF from the browser, CSV (one row per
project) for spreadsheets, JSON for other tools. The report is rendered in the language it was
written in.

## Settings

| variable | default | meaning |
|---|---|---|
| `MA_PMO_TOLERANCE_SPI` | 0.9 | a project below this SPI is outside tolerance |
| `MA_PMO_TOLERANCE_SLIP_DAYS` | 0 | days a forecast may pass the deadline |
| `MA_PMO_REPORT_AS_OF` | today | report as of this date (YYYY-MM-DD) |

## Limits

- The plan baseline is a straight line from planned start to planned finish. A tracker with a
  time-phased baseline would give a better planned value.
- A2's CPM finish assumes one person at 8 hours a day per task, so it can differ from the report's
  forecast; the report uses the tracker's plan dates.
- A6's gate criterion "SPI ≥ 0.8" uses the effort-weighted completion ratio, not this time-based SPI.
- Coming next in roadmap 12: grounding the narrative in the figures, insights across reports, a
  reports page in the dashboard, docx and pdf export.
