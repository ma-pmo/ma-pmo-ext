# Lab 1 — Write a notifier plugin

**English | [한국어](README.ko.md)** · Lecture: [07 Integrations and failure isolation](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/07-integrations.md)

Agents raise events — an approval is waiting, a high risk appeared, a gate failed. Notifiers
deliver them. In this lab you write a notifier that appends every event to a local
[JSON Lines](https://jsonlines.org/) file, so a team can keep an audit inbox without Slack.

**You will practice:** the plugin contract (`name` + `send(event)` + `IntegrationSpec`),
filtering, configuration from the environment, and letting failures surface instead of
hiding them.

## Files

- `file_notifier.py` — the only file you edit.

## Steps

1. **Describe it.** Fill in `SPEC`: name `"file"`, kind `"notifier"`, a one-line description.
2. **Write events.** `send(event)` appends `json.dumps(event.as_dict())` plus a newline to
   `self.path`. One event = one line.
3. **Let errors out.** Do not wrap the write in `try/except`. If the folder does not exist,
   `send` must raise — the dispatcher (`ma_pmo/integrations/dispatch.py`) catches it, records
   `ok: false` and keeps the agents running. Swallowing the error would hide a broken setup.
4. **Filter.** Skip events whose severity is below `min_severity` (`info < warning < critical`).
   Raise `ValueError` in `__init__` for an unknown `min_severity`.
5. **Configure.** `from_settings` reads the path from `MA_PMO_NOTIFY_FILE`
   (default `ma-pmo-events.jsonl`) and the threshold from `MA_PMO_NOTIFY_FILE_MIN_SEVERITY`.

## Check

```bash
ma-pmo learn check 1
```

Each line is one requirement; a ✗ comes with a hint. Stuck? Compare with
`ma-pmo learn start 1 --solution`.

## Going further

Ship it as a real plugin: put the file in a package and register `SPEC` in its
`pyproject.toml` under `[project.entry-points."ma_pmo.integrations"]`. Then
`MA_PMO_INTEGRATIONS=file` turns it on and `GET /integrations` lists it
(see [docs/INTEGRATIONS.md](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/INTEGRATIONS.md)).
