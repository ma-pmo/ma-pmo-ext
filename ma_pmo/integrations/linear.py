"""Linear tracker — each team in `LINEAR_TEAM_KEYS` becomes one MA-PMO project.

Issues become tasks. Mapping, on top of `mapping.build_project`:

| MA-PMO              | Linear                                                            |
|---------------------|-------------------------------------------------------------------|
| task id             | issue identifier, e.g. `ENG-42`                                   |
| effort (hours)      | estimate (points) × 8; label `hours:N` wins; else 8               |
| progress (%)        | state type completed = 100 · started = 50 · otherwise 0           |
| dependencies        | "blocks" relations pointing at the issue                          |
| due date            | issue due date                                                    |
| skill               | label `skill:<name>`                                              |

Canceled issues are left out. Uses the GraphQL API with a personal API key (`LINEAR_API_KEY`).
"""
from __future__ import annotations

from typing import Any

import httpx

from ma_pmo.core.config import Settings
from ma_pmo.integrations.mapping import (
    DEFAULT_EFFORT,
    HOURS_PER_POINT,
    IssueRecord,
    build_project,
    effort_from_labels,
    skill_from_labels,
)

_API = "https://api.linear.app/graphql"
_MAX_ISSUES = 1000
_QUERY = """
query Issues($team: String!, $after: String) {
  issues(first: 100, after: $after, filter: {team: {key: {eq: $team}}}) {
    nodes {
      identifier estimate createdAt dueDate
      state { type }
      labels { nodes { name } }
      inverseRelations { nodes { type issue { identifier } } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""
_PROGRESS = {"completed": 100.0, "started": 50.0}


class LinearTracker:
    name = "linear"

    def __init__(self, team_keys: list[str], api_key: str, *, url: str = _API,
                 timeout: float = 10.0, client: httpx.Client | None = None) -> None:
        self.team_keys = team_keys
        self.url = url
        self.headers = {"Authorization": api_key, "Content-Type": "application/json"}
        self.client = client or httpx.Client(timeout=timeout)

    @classmethod
    def from_settings(cls, settings: Settings) -> LinearTracker:
        keys = [k.strip() for k in settings.linear_team_keys.split(",") if k.strip()]
        return cls(keys, settings.linear_api_key,
                   timeout=max(settings.integration_timeout_sec, 10.0))

    def get_portfolio_status(self, portfolio_id: str) -> dict:
        return {
            "portfolio_id": portfolio_id,
            "name": f"Linear · {', '.join(self.team_keys)}",
            "period": "",
            "found": True,
            "projects": [self._project(team) for team in self.team_keys],
        }

    def _issues(self, team: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        after = None
        while len(issues) < _MAX_ISSUES:
            resp = self.client.post(self.url, headers=self.headers,
                                    json={"query": _QUERY, "variables": {"team": team,
                                                                         "after": after}})
            resp.raise_for_status()
            body = resp.json()
            if body.get("errors"):
                raise RuntimeError(f"Linear API error: {body['errors'][0].get('message')}")
            page = body["data"]["issues"]
            issues += page["nodes"]
            if not page["pageInfo"]["hasNextPage"]:
                break
            after = page["pageInfo"]["endCursor"]
        return issues

    def _project(self, team: str) -> dict:
        records = []
        for issue in self._issues(team):
            state = (issue.get("state") or {}).get("type", "")
            if state == "canceled":
                continue
            labels = [n.get("name", "") for n in (issue.get("labels") or {}).get("nodes", [])]
            estimate = issue.get("estimate")
            effort = effort_from_labels(labels) or (
                float(estimate) * HOURS_PER_POINT if isinstance(estimate, (int, float))
                and estimate > 0 else DEFAULT_EFFORT)
            deps = [n["issue"]["identifier"]
                    for n in (issue.get("inverseRelations") or {}).get("nodes", [])
                    if n.get("type") == "blocks" and n.get("issue")]
            records.append(IssueRecord(
                key=issue["identifier"], effort=effort, progress=_PROGRESS.get(state, 0.0),
                deps=deps, created=(issue.get("createdAt") or "")[:10] or None,
                due=issue.get("dueDate"), skill=skill_from_labels(labels),
            ))
        return build_project(team, records)
