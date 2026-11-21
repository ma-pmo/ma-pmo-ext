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

## What changed since the last report

Each report is compared with the earlier reports of the same scope, kind and projects. Rules find
what changed, cite the facts behind it, suggest an action, and rank it so exceptions come first:

| insight | when | severity |
|---|---|---|
| a tolerance breached | not breached in the previous report | high |
| back within tolerance | breached in the previous report | low |
| status worse / better | the project's RAG moved | high if now red, else medium / low |
| forecast slipped | the forecast finish moved 7 or more days later | medium; high if now late |
| no progress | an unfinished project did not move since an earlier-dated report | medium |
| new high risk | A4 rates it high or critical; the previous report read A4 and had not | high |
| SPI falling | the portfolio SPI fell three reports in a row | medium |

They appear under "Since the last report", lead the rule narrative, and high ones add their action.
The first report of a scope and kind has nothing to compare with.

## Checking the LLM's narrative

The LLM gets the figures and the insights and is told to use only them. Then every number, date and
id in its summary, risks, actions and project lines is checked against the facts: a date must be
one in the facts, an id a project (or a task, lesson or risk the facts quote), and a number a figure
at the precision written (52.9 matches 52.94; −7 may be written as 7). Small whole numbers up to 10
and years pass. One unmatched item replaces the whole narrative with the rule narrative, and the
trace marks the fallback. The report's footer says which happened, and `grounding` in report.v2
lists what was checked and what did not match. Wording is not judged.

## Reading and downloading

In the dashboard, **Reports** lists them newest first (filter by kind), shows the selected one as
it will be downloaded, and has buttons to download it as HTML, Markdown, CSV or JSON, to print it
(or save it as PDF), and to write a new one by running a report workflow.

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
| `GET /reports/{id}/export?format=md\|html\|csv\|json\|docx` | a download; `&inline=true` opens HTML in the browser |

Formats: Markdown for wikis and chat, HTML to read or print to PDF from the browser, CSV (one row per
project) for spreadsheets, JSON for other tools, and Word (`docx`, with `pip install "ma-pmo[export]"`;
without it the endpoint answers 501). The report is rendered in the language it was written in.

Elsewhere:

- The `report.generated` notification (Slack, webhook) is titled with the report's kind and links
  to it on the Reports page (`MA_PMO_PUBLIC_URL/reports?id=...`).
- The MCP server's `latest_report` tool gives an AI assistant the newest report, or one by id or
  kind, as Markdown.
- `ma-pmo eval` and `GET /eval` (`reports`) count how the stored reports' narratives were written:
  how many an LLM wrote, how many were replaced for a figure not in the facts, the share that
  matched (`faithful_rate`) and examples of what did not.

## Settings

| variable | default | meaning |
|---|---|---|
| `MA_PMO_TOLERANCE_SPI` | 0.9 | a project below this SPI is outside tolerance |
| `MA_PMO_TOLERANCE_SLIP_DAYS` | 0 | days a forecast may pass the deadline |
| `MA_PMO_REPORT_AS_OF` | today | report as of this date (YYYY-MM-DD) |

## Limits

- SPI swings early in a project, when little planned value has accrued, so forecasts and the
  "forecast slipped" insight are noisy in the first weeks.
- The plan baseline is a straight line from planned start to planned finish. A tracker with a
  time-phased baseline would give a better planned value.
- A2 keeps its CPM finish (one person per task at 8 hours a day) for the order of the work, and
  since 0.9 also reports the same earned-value forecast as the report (`forecast_finish`); its
  slippage KPI and A6's "SPI ≥ 0.8" use this SPI too (`agents/evm.py`).
- PDF comes from printing the HTML (the dashboard's Print / PDF button); there is no server-side
  PDF, which would need a rendering engine with fonts for Korean.
