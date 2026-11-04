"""GitHub tracker — each repository in `GITHUB_REPOS` becomes one MA-PMO project.

Issues become tasks (pull requests are skipped). Mapping, on top of `mapping.build_project`:

| MA-PMO              | GitHub                                                              |
|---------------------|---------------------------------------------------------------------|
| task id             | `owner/repo#123`                                                    |
| effort (hours)      | label `hours:N`, or `points:N` / `sp:N` / `estimate:N` × 8, else 8   |
| progress (%)        | closed = 100 · open + label `in progress`/`doing`/`wip` = 50 · open = 0 |
| dependencies        | "blocked by #12" or "depends on owner/repo#12" in the issue body    |
| due date            | the issue's milestone due date                                      |
| skill               | label `skill:<name>`                                                |

Issues closed as "not planned" are left out. Uses the REST API (`GITHUB_TOKEN` is optional for
public repositories; without it GitHub allows 60 requests per hour).
"""
from __future__ import annotations

from typing import Any

import httpx

from ma_pmo.core.config import Settings
from ma_pmo.integrations.mapping import (
    DEFAULT_EFFORT,
    IssueRecord,
    blocked_by_in_text,
    build_project,
    effort_from_labels,
    skill_from_labels,
)

_API = "https://api.github.com"
_MAX_ISSUES = 1000
_IN_PROGRESS = {"in progress", "in-progress", "doing", "wip"}


class GitHubTracker:
    name = "github"

    def __init__(self, repos: list[str], token: str = "", *, base_url: str = _API,
                 timeout: float = 10.0, client: httpx.Client | None = None) -> None:
        self.repos = repos
        self.base_url = base_url.rstrip("/")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(timeout=timeout)
        self.headers = headers

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubTracker:
        repos = [r.strip() for r in settings.github_repos.split(",") if r.strip()]
        return cls(repos, settings.github_token,
                   timeout=max(settings.integration_timeout_sec, 10.0))

    def get_portfolio_status(self, portfolio_id: str) -> dict:
        return {
            "portfolio_id": portfolio_id,
            "name": f"GitHub · {', '.join(self.repos)}",
            "period": "",
            "found": True,
            "projects": [self._project(repo) for repo in self.repos],
        }

    def _issues(self, repo: str) -> list[dict[str, Any]]:
        url: str | None = f"{self.base_url}/repos/{repo}/issues"
        params: dict[str, Any] | None = {"state": "all", "per_page": 100, "direction": "asc"}
        issues: list[dict[str, Any]] = []
        while url and len(issues) < _MAX_ISSUES:
            resp = self.client.get(url, params=params, headers=self.headers)
            resp.raise_for_status()
            issues += [i for i in resp.json() if "pull_request" not in i]
            url, params = resp.links.get("next", {}).get("url"), None  # next URL has the query
        return issues

    def _project(self, repo: str) -> dict:
        records = []
        for issue in self._issues(repo):
            if issue.get("state_reason") == "not_planned":
                continue
            labels = [lb.get("name", "") for lb in issue.get("labels") or []]
            if issue.get("state") == "closed":
                progress = 100.0
            elif _IN_PROGRESS & {lb.lower() for lb in labels}:
                progress = 50.0
            else:
                progress = 0.0
            deps = [ref if "/" in ref else f"{repo}{ref}"
                    for ref in blocked_by_in_text(issue.get("body"))]
            due = (issue.get("milestone") or {}).get("due_on")
            records.append(IssueRecord(
                key=f"{repo}#{issue['number']}",
                effort=effort_from_labels(labels) or DEFAULT_EFFORT,
                progress=progress, deps=deps,
                created=(issue.get("created_at") or "")[:10] or None,
                due=due[:10] if due else None, skill=skill_from_labels(labels),
            ))
        return build_project(repo, records)
