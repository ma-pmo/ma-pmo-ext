# Example agent plugin

**English | [한국어](README.ko.md)** · Guide: [docs/PLUGINS.md](../../docs/PLUGINS.md)

A complete MA-PMO agent in one small package: it estimates the cost of each project's remaining
work and sends projects over the limit to a person.

```bash
pip install ./examples/agent-plugin
ma-pmo agents                          # acme.budget is listed, source ma-pmo-budget-agent
curl -X POST localhost:8000/orchestrate -H 'content-type: application/json' \
  -d '{"goal": "budget check"}'
```

`ACME_HOURLY_RATE` (default 100) and `ACME_PROJECT_LIMIT` (default 30000) configure it. Run its
tests with `pytest examples/agent-plugin`.
