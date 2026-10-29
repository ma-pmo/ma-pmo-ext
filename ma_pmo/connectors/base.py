"""Connector interface. Swap in real Jira/Redmine/ERP integrations with the same signature."""
from __future__ import annotations

from typing import Protocol


class IssueTrackerConnector(Protocol):
    def get_portfolio_status(self, portfolio_id: str) -> dict:
        """Fetch portfolio, project and task progress."""
        ...
