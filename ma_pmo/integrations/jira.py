"""Jira Cloud tracker — builds the portfolio status agents read from real Jira issues.

Each Jira project key in `JIRA_PROJECT_KEYS` becomes one MA-PMO project and its issues
become tasks. Mapping:

| MA-PMO              | Jira                                                              |
|---------------------|-------------------------------------------------------------------|
| task effort (hours) | original time estimate, else story points × 8, else 8             |
| task progress (%)   | status category: done = 100, in progress = time-tracking % or 50  |
| task dependencies   | "is blocked by" issue links                                      |
| planned start       | earliest issue creation date                                      |
| planned finish      | latest due date of unfinished issues (else latest due date)       |
| deadline            | latest due date in the project                                    |
| status color        | red: overdue unfinished issues · amber: blocked issues · green    |

Uses the Jira Cloud REST API v3 (`/rest/api/3/search/jql`) with basic auth
(account email + API token).
"""
from __future__ import annotations

from typing import Any

import httpx

from ma_pmo.core.config import Settings
from ma_pmo.integrations.mapping import HOURS_PER_POINT, IssueRecord, build_project

_FIELDS = [
    "summary", "status", "duedate", "created", "timeoriginalestimate",
    "issuelinks", "project", "components", "aggregateprogress",
]
_MAX_ISSUES = 1000


class JiraTracker:
    name = "jira"

    def __init__(self, base_url: str, email: str, api_token: str, project_keys: list[str], *,
                 story_points_field: str = "", timeout: float = 10.0,
                 client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_keys = project_keys
        self.story_points_field = story_points_field
        self.client = client or httpx.Client(timeout=timeout, auth=(email, api_token))

    @classmethod
    def from_settings(cls, settings: Settings) -> JiraTracker:
        keys = [k.strip() for k in settings.jira_project_keys.split(",") if k.strip()]
        return cls(
            settings.jira_base_url, settings.jira_email, settings.jira_api_token, keys,
            story_points_field=settings.jira_story_points_field,
            timeout=max(settings.integration_timeout_sec, 10.0),
        )

    # ── IssueTrackerConnector ─────────────────────────────────────
    def get_portfolio_status(self, portfolio_id: str) -> dict:
        projects = [self._project(key, self._issues(key)) for key in self.project_keys]
        return {
            "portfolio_id": portfolio_id,
            "name": f"Jira · {', '.join(self.project_keys)}",
            "period": "",
            "found": True,
            "projects": projects,
        }

    # ── REST ──────────────────────────────────────────────────────
    def _issues(self, project_key: str) -> list[dict[str, Any]]:
        fields = list(_FIELDS)
        if self.story_points_field:
            fields.append(self.story_points_field)
        params: dict[str, Any] = {
            "jql": f'project = "{project_key}" ORDER BY created ASC',
            "fields": ",".join(fields),
            "maxResults": 100,
        }
        issues: list[dict[str, Any]] = []
        while len(issues) < _MAX_ISSUES:
            resp = self.client.get(f"{self.base_url}/rest/api/3/search/jql", params=params)
            resp.raise_for_status()
            body = resp.json()
            issues.extend(body.get("issues", []))
            token = body.get("nextPageToken")
            if body.get("isLast", True) or not token:
                break
            params["nextPageToken"] = token
        return issues

    # ── mapping ───────────────────────────────────────────────────
    def _effort(self, fields: dict[str, Any]) -> float:
        seconds = fields.get("timeoriginalestimate")
        if seconds:
            return round(seconds / 3600, 1)
        points = fields.get(self.story_points_field) if self.story_points_field else None
        if isinstance(points, (int, float)) and points > 0:
            return float(points) * HOURS_PER_POINT
        return 8.0

    @staticmethod
    def _progress(fields: dict[str, Any]) -> float:
        category = ((fields.get("status") or {}).get("statusCategory") or {}).get("key")
        if category == "done":
            return 100.0
        if category == "indeterminate":
            pct = (fields.get("aggregateprogress") or {}).get("percent")
            return float(pct) if isinstance(pct, (int, float)) and pct > 0 else 50.0
        return 0.0

    @staticmethod
    def _blocked_by(fields: dict[str, Any]) -> list[str]:
        deps = []
        for link in fields.get("issuelinks") or []:
            inward = (link.get("type") or {}).get("inward", "")
            if "blocked by" in inward and link.get("inwardIssue"):
                deps.append(link["inwardIssue"]["key"])
        return deps

    def _project(self, key: str, issues: list[dict[str, Any]]) -> dict:
        records = []
        for issue in issues:
            f = issue.get("fields") or {}
            components = [c.get("name", "") for c in f.get("components") or []]
            records.append(IssueRecord(
                key=issue["key"], effort=self._effort(f), progress=self._progress(f),
                deps=self._blocked_by(f),
                created=str(f["created"])[:10] if f.get("created") else None,
                due=f.get("duedate"), skill=components[0] if components else None,
            ))
        return build_project(key, records)
