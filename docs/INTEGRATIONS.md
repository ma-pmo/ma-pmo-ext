# Integrations

**English | [한국어](INTEGRATIONS.ko.md)**

MA-PMO connects to the tools your team already uses through small, pluggable integrations.
Turn them on with environment variables — no code changes.

| Name | Kind | What it does |
|---|---|---|
| `slack` | notifier | Posts approvals, high-severity risks, failed gates and reports to a Slack channel |
| `webhook` | notifier | POSTs every event as JSON to any URL (n8n, Zapier, Make, your own service) |
| `jira` | tracker | Agents read real projects and issues from Jira Cloud instead of the demo data |

- **Notifiers** (outbound) receive events. Several can be active at once.
- **Trackers** (inbound) are where agents read portfolio data. One is active at a time; without one, the bundled demo portfolio is used.
- Integrations are **best effort**: if Slack is down or a URL is wrong, the error is logged and the agents keep working.

## Quick start

```bash
# .env
MA_PMO_INTEGRATIONS=slack,jira
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/XXXX
JIRA_BASE_URL=https://your-team.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...
JIRA_PROJECT_KEYS=PAY,DATA
```

Restart the API, then check and test:

```bash
curl localhost:8000/integrations              # enabled? configured? (no secrets shown)
curl -X POST localhost:8000/integrations/slack/test   # sends a test message
```

## Events

| Event | When |
|---|---|
| `approval.requested` | a message goes to the human approval queue |
| `approval.resolved` | someone approves or rejects it |
| `risk.detected` | A4 rates a risk `high` or `critical` |
| `gate.failed` | A6 fails a stage gate |
| `report.generated` | A5 produces an executive report |
| `integration.test` | `POST /integrations/{name}/test` |

Limit what is sent with `MA_PMO_NOTIFY_EVENTS=approval.requested,risk.detected`
(empty = all). Event titles follow the request language (`?lang=ko`) or `MA_PMO_LANG`.
`MA_PMO_PUBLIC_URL` sets the dashboard link in messages.

## Slack

1. In Slack: **Apps → Incoming Webhooks → Add to Slack**, pick a channel, copy the URL
   ([guide](https://api.slack.com/messaging/webhooks)).
2. Set `SLACK_WEBHOOK_URL` and add `slack` to `MA_PMO_INTEGRATIONS`.

Messages use Block Kit: a title, the details, the event type and project, and an
"Open MA-PMO" button.

## Generic webhook

Set `MA_PMO_WEBHOOK_URL` and add `webhook`. Each event is POSTed as:

```json
{
  "source": "ma-pmo",
  "event": {
    "type": "risk.detected",
    "title": "HIGH risk on PROJ-31",
    "summary": "...",
    "severity": "critical",
    "task_ref": "PORTFOLIO#2026-Q1/PROJ-31",
    "url": "http://localhost:3000/",
    "data": {"message_id": "...", "project_id": "PROJ-31", "...": "..."},
    "occurred_at": "2026-11-01T09:00:00+00:00"
  }
}
```

## Jira Cloud

1. Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.
2. Set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` and `JIRA_PROJECT_KEYS`
   (each key becomes one MA-PMO project), and add `jira` to `MA_PMO_INTEGRATIONS`.
3. Optional: `JIRA_STORY_POINTS_FIELD=customfield_10016` to use story points as effort.

How Jira data is mapped:

| MA-PMO | Jira |
|---|---|
| task effort (hours) | original time estimate, else story points × 8, else 8 |
| task progress | status category: Done = 100%, In Progress = time-tracking % (or 50%), To Do = 0% |
| dependencies | "is blocked by" links |
| planned start | earliest issue creation date |
| planned finish / deadline | latest due date of open issues / of all issues |
| status color | red: open issues past due · amber: blocked issues · green otherwise |

The resource master (people, skills, capacity) still comes from MA-PMO's database.

## Resource calendars (.ics)

A3 allocates work as if everyone is free every week unless it knows about meetings, leave and
holidays. Point it at a folder with one iCalendar file per person, named after the resource id:

```bash
MA_PMO_CALENDAR_DIR=./calendars      # ./calendars/R-01.ics, ./calendars/R-02.ics, ...
```

Export the file from any calendar app (Google Calendar: Settings → Import & export; Outlook:
Save calendar; Apple Calendar: File → Export). A3 then takes each person's busy hours off their
weekly capacity before allocating, so overloads appear where the calendar says they will.

Counting rules: Monday–Friday only, at most 8 busy hours per day; all-day events block the whole
day; events shown as free or cancelled are ignored; times are counted as written (no time-zone
conversion); recurring events count their first occurrence only, so export with occurrences
expanded. A person without a file is treated as fully available. Code:
`ma_pmo/connectors/calendar.py` — implement `busy_hours(resource_id, week)` for another source.

## Vector search for lessons learned (A7)

A7 finds lessons by whole-word overlap by default. Switch to vector search to also match
inflections and Korean words with particles attached, or plug in an embedding model for synonyms:

```bash
MA_PMO_RETRIEVER=vector                          # offline character n-gram vectors
MA_PMO_EMBEDDING_MODEL=ollama/nomic-embed-text   # optional: any LiteLLM embedding model
MA_PMO_EMBEDDING_API_BASE=http://localhost:11434 # optional: local or private endpoint
ma-pmo eval --retrieval                          # recall@1, recall@3, MRR on labeled queries
```

On the bundled labeled queries (`ma_pmo/fixtures/retrieval_eval.json`, 14 queries in English
and Korean) the offline vectors raise recall@3 from 0.857 to 1.0 and MRR from 0.774 to 0.964;
every gain is a Korean query whose words carry particles. If the embedding model cannot be
reached, A7 falls back to lexical search (logged, traced, and reported by `--retrieval`).
Citations are always returned. Code: `ma_pmo/connectors/vectordb.py`.

## Writing your own integration

An integration is an `IntegrationSpec`. Publish it from any Python package through the
`ma_pmo.integrations` entry-point group and enable it by name.

```python
# my_package/teams.py
import httpx
from ma_pmo.integrations import Event, IntegrationSpec

class TeamsNotifier:
    name = "teams"

    def __init__(self, url: str) -> None:
        self.url = url

    def send(self, event: Event) -> None:
        httpx.post(self.url, json={"text": f"**{event.title}**\n\n{event.summary}"},
                   timeout=5).raise_for_status()

SPEC = IntegrationSpec(
    name="teams",
    kind="notifier",
    description="Post events to Microsoft Teams",
    required_settings=(),
    factory=lambda settings: TeamsNotifier(url="https://..."),
)
```

```toml
# my_package/pyproject.toml
[project.entry-points."ma_pmo.integrations"]
teams = "my_package.teams:SPEC"
```

Then `pip install my-package` and set `MA_PMO_INTEGRATIONS=slack,teams`.

- A **notifier** needs a `name` and `send(event)`; raise on failure.
- A **tracker** needs `get_portfolio_status(portfolio_id) -> dict` in the shape of
  `ma_pmo/connectors/jira_mock.py`.
- Built-in integrations live in `ma_pmo/integrations/`; tests in
  `tests/test_integrations.py` show how to test against a mocked HTTP transport.
