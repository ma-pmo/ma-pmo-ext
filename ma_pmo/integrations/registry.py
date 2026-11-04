"""Integration registry: built-ins + third-party plugins, enabled through settings.

Enable integrations with `MA_PMO_INTEGRATIONS=slack,jira` (comma-separated names).
Third-party packages register more by exposing an `IntegrationSpec` under the
`ma_pmo.integrations` entry-point group, e.g. in their pyproject.toml:

    [project.entry-points."ma_pmo.integrations"]
    teams = "my_package.teams:SPEC"
"""
from __future__ import annotations

from importlib.metadata import entry_points

from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.core.config import Settings, get_settings
from ma_pmo.core.obs import get_logger
from ma_pmo.integrations.base import IntegrationSpec, Notifier
from ma_pmo.integrations.github import GitHubTracker
from ma_pmo.integrations.jira import JiraTracker
from ma_pmo.integrations.linear import LinearTracker
from ma_pmo.integrations.notifiers import SlackNotifier, WebhookNotifier

ENTRY_POINT_GROUP = "ma_pmo.integrations"
_log = get_logger("integrations")

BUILTINS: tuple[IntegrationSpec, ...] = (
    IntegrationSpec(
        name="slack",
        kind="notifier",
        description="Post approvals, risks, failed gates and reports to a Slack channel.",
        required_settings=("slack_webhook_url",),
        factory=SlackNotifier.from_settings,
    ),
    IntegrationSpec(
        name="webhook",
        kind="notifier",
        description="POST every event as JSON to any URL (n8n, Zapier, your own service).",
        required_settings=("webhook_url",),
        factory=WebhookNotifier.from_settings,
    ),
    IntegrationSpec(
        name="jira",
        kind="tracker",
        description="Read projects and issues from Jira Cloud instead of the demo data.",
        required_settings=("jira_base_url", "jira_email", "jira_api_token", "jira_project_keys"),
        factory=JiraTracker.from_settings,
    ),
    IntegrationSpec(
        name="github",
        kind="tracker",
        description="Read issues and milestones from GitHub repositories instead of the demo data.",
        required_settings=("github_repos",),
        factory=GitHubTracker.from_settings,
    ),
    IntegrationSpec(
        name="linear",
        kind="tracker",
        description="Read issues from Linear teams instead of the demo data.",
        required_settings=("linear_api_key", "linear_team_keys"),
        factory=LinearTracker.from_settings,
    ),
)


def _plugins() -> list[IntegrationSpec]:
    specs = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            spec = ep.load()
        except Exception as e:  # a broken plugin must not break the app
            _log.warning("integration_plugin_failed", entry_point=ep.name, error=str(e))
            continue
        if isinstance(spec, IntegrationSpec):
            specs.append(spec)
        else:
            _log.warning("integration_plugin_invalid", entry_point=ep.name)
    return specs


def available() -> dict[str, IntegrationSpec]:
    """All known integrations by name; built-ins win on name clashes."""
    specs: dict[str, IntegrationSpec] = {s.name: s for s in _plugins()}
    specs.update({s.name: s for s in BUILTINS})
    return specs


def enabled_names(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    return [n.strip().lower() for n in settings.integrations.split(",") if n.strip()]


def status(settings: Settings | None = None) -> list[dict]:
    """What is available, enabled and correctly configured (no secret values)."""
    settings = settings or get_settings()
    enabled = set(enabled_names(settings))
    out = []
    for name, spec in sorted(available().items()):
        missing = spec.missing_settings(settings)
        out.append(
            {
                "name": name,
                "kind": spec.kind,
                "description": spec.description,
                "enabled": name in enabled,
                "configured": not missing,
                "missing_settings": missing,
                "active": name in enabled and not missing,
            }
        )
    unknown = enabled - set(available())
    for name in sorted(unknown):
        out.append(
            {"name": name, "kind": "unknown", "description": "not installed", "enabled": True,
             "configured": False, "missing_settings": [], "active": False}
        )
    return out


def _active(kind: str, settings: Settings) -> list[IntegrationSpec]:
    specs = available()
    active = []
    for name in enabled_names(settings):
        spec = specs.get(name)
        if spec is None:
            _log.warning("integration_unknown", name=name)
            continue
        if spec.kind != kind:
            continue
        missing = spec.missing_settings(settings)
        if missing:
            _log.warning("integration_not_configured", name=name, missing=missing)
            continue
        active.append(spec)
    return active


def build_notifiers(settings: Settings | None = None) -> list[Notifier]:
    settings = settings or get_settings()
    return [spec.factory(settings) for spec in _active("notifier", settings)]


def get_tracker(settings: Settings | None = None) -> IssueTrackerConnector:
    """The enabled tracker integration, or the bundled demo-data connector."""
    settings = settings or get_settings()
    trackers = _active("tracker", settings)
    if trackers:
        if len(trackers) > 1:
            _log.warning("integration_multiple_trackers", using=trackers[0].name)
        tracker: IssueTrackerConnector = trackers[0].factory(settings)
        return tracker
    from ma_pmo.connectors.jira_mock import MockJiraConnector

    return MockJiraConnector()
