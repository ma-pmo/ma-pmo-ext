# Lab 5 — Write an MCP tool

**English | [한국어](README.ko.md)** · Lecture: [07 Integrations and failure isolation](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/07-integrations.md) · Needs `pip install "ma-pmo[mcp]"`

MA-PMO's MCP server (`ma-pmo mcp`) lets AI assistants call agents as tools. In this lab you add
one: `project_health`, a single answer to "how is this project doing?" built from the tracker
and A2's critical-path method.

**You will practice:** writing a tool as a plain function first (testable without MCP), returning
"not found" as data, and marking a tool read-only so clients may call it without asking.

## Files

- `health_tool.py` — `project_health(project_id, portfolio_id)` and `register(server)`.

## Steps

1. Read the portfolio with `get_tracker().get_portfolio_status(portfolio_id)`.
2. For an unknown project, return `{"error": "unknown project '<id>'", "projects": [...ids]}`
   — an assistant can recover from that; an exception it cannot.
3. Run `compute_cpm(project["tasks"])` and return `project_id`, `status`, `percent_complete`,
   `critical_path` and `min_slack_days` (smallest slack among tasks that have slack; 0 if none).
4. In `register(server)`, add the function with `server.tool(annotations=ToolAnnotations(
   read_only_hint=True, ...))`. Compare with `ma_pmo/mcp_server.py`.

## Check

```bash
ma-pmo learn check 5
```

The last check starts a real MCP server in-process, registers your tool, lists it and calls it.

## Think about it

Why is there no `approve` tool in `ma_pmo/mcp_server.py`? Which of your own tools would you
mark `read_only_hint=False`, and what should a client do differently for those?
