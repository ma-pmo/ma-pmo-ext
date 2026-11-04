# MCP server

**English | [한국어](MCP.ko.md)**

MA-PMO runs as a [Model Context Protocol](https://modelcontextprotocol.io) server, so AI
assistants and IDEs that speak MCP can ask it for portfolio status, schedules, risks and
evaluation results — and run scenarios — as tools.

```bash
pip install "ma-pmo[mcp]"
ma-pmo init-db               # once: demo portfolio + lessons learned
ma-pmo mcp                   # MCP over stdio
```

## Tools

| Tool | What it returns | Changes data |
|---|---|---|
| `portfolio_status` | projects with status colour, dates, progress, tasks | no |
| `schedule` | CPM schedule for one project: critical path, projected finish, slack | no |
| `risks` | risks detected by A4, newest first | no |
| `pending_approvals` | proposals waiting for a person | no |
| `list_scenarios` | the 20 lifecycle scenarios | no |
| `run_scenario` | runs a scenario through the agents and returns the four-phase trace | **yes** — audit log, KPIs, maybe new approvals |
| `evaluation` | H1–H5 verdicts with evidence | no |
| `search_lessons` | lessons learned with citations (A7) | no |

Read-only tools carry `read_only_hint`, so clients can call them without asking every time.
Tools that take `lang` answer in Korean with `lang="ko"`.

**Approving or rejecting is not a tool.** Human-in-the-loop decisions stay with a person, in
the dashboard or through the authenticated API ([docs/AUTH.md](AUTH.md)).

## Connect a client

**Claude Code**

```bash
claude mcp add ma-pmo -- ma-pmo mcp
```

**Claude Desktop** and other clients that use an `mcpServers` config:

```json
{
  "mcpServers": {
    "ma-pmo": {
      "command": "ma-pmo",
      "args": ["mcp"],
      "env": { "DB_URL": "sqlite:////absolute/path/to/ma_pmo.db", "MA_PMO_LANG": "en" }
    }
  }
}
```

Use an absolute `DB_URL`: clients start the server from their own working folder. Point it at
the same database as your API to see the same data.

Then ask, for example: *"Which projects are red, and what is on PROJ-31's critical path?"* or
*"Run the quarterly review scenario and summarise the insight phase."*

## Security

The stdio server runs as the local user who starts it, with that user's database access; it
does not pass through the HTTP API's authentication. Only add it to clients you trust with
that data. Integrations still apply: a scenario run can notify Slack or a webhook if you
enabled them.

## In code

- `ma_pmo/mcp_server.py` — `create_server()` builds the server; one function per tool.
- Tests: `tests/test_mcp.py` (in-process client; skipped when the extra is not installed).
