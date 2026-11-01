"""Built-in notifiers: Slack (incoming webhook) and a generic JSON webhook.

Both take an optional `httpx.Client` so tests can inject a mock transport.
"""
from __future__ import annotations

from typing import Any

import httpx

from ma_pmo.core.config import Settings
from ma_pmo.integrations.base import Event, EventType

_EMOJI = {
    EventType.APPROVAL_REQUESTED: ":raising_hand:",
    EventType.APPROVAL_RESOLVED: ":white_check_mark:",
    EventType.RISK_DETECTED: ":rotating_light:",
    EventType.GATE_FAILED: ":vertical_traffic_light:",
    EventType.REPORT_GENERATED: ":memo:",
    EventType.TEST: ":wave:",
}


class SlackNotifier:
    """Posts Block Kit messages to a Slack incoming webhook."""

    name = "slack"

    def __init__(self, webhook_url: str, *, timeout: float = 5.0,
                 client: httpx.Client | None = None) -> None:
        self.webhook_url = webhook_url
        self.client = client or httpx.Client(timeout=timeout)

    @classmethod
    def from_settings(cls, settings: Settings) -> SlackNotifier:
        return cls(settings.slack_webhook_url, timeout=settings.integration_timeout_sec)

    def payload(self, event: Event) -> dict[str, Any]:
        emoji = _EMOJI.get(event.type, ":bell:")
        blocks: list[dict[str, Any]] = [
            {"type": "header", "text": {"type": "plain_text", "text": f"{event.title}"[:150]}},
        ]
        if event.summary:
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": event.summary[:2900]}}
            )
        context = [f"{emoji} `{event.type.value}`"]
        if event.task_ref:
            context.append(event.task_ref)
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(context)}]}
        )
        if event.url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open MA-PMO"},
                            "url": event.url,
                        }
                    ],
                }
            )
        # `text` is the fallback shown in notifications and by clients without Block Kit
        return {"text": f"{emoji} {event.title}", "blocks": blocks}

    def send(self, event: Event) -> None:
        resp = self.client.post(self.webhook_url, json=self.payload(event))
        resp.raise_for_status()


class WebhookNotifier:
    """POSTs the event as JSON to any URL (n8n, Zapier, Discord bridges, your own service)."""

    name = "webhook"

    def __init__(self, url: str, *, timeout: float = 5.0,
                 client: httpx.Client | None = None) -> None:
        self.url = url
        self.client = client or httpx.Client(timeout=timeout)

    @classmethod
    def from_settings(cls, settings: Settings) -> WebhookNotifier:
        return cls(settings.webhook_url, timeout=settings.integration_timeout_sec)

    def payload(self, event: Event) -> dict[str, Any]:
        return {"source": "ma-pmo", "event": event.as_dict()}

    def send(self, event: Event) -> None:
        resp = self.client.post(self.url, json=self.payload(event))
        resp.raise_for_status()
