"""Integrations — which are installed/enabled, and a test send.

GET  /integrations              : status of every known integration (no secret values)
POST /integrations/{name}/test  : send a test notification through one enabled notifier
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ma_pmo.core.config import get_settings
from ma_pmo.integrations import registry
from ma_pmo.integrations.dispatch import emit
from ma_pmo.integrations.events import make_test_event

router = APIRouter(tags=["integrations"])


@router.get("/integrations")
def list_integrations() -> list[dict]:
    return registry.status()


@router.post("/integrations/{name}/test")
def test_integration(name: str) -> dict:
    settings = get_settings()
    spec = registry.available().get(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown integration: {name}")
    if spec.kind != "notifier":
        raise HTTPException(status_code=400, detail=f"{name} is a {spec.kind}, not a notifier")
    missing = spec.missing_settings(settings)
    if missing:
        raise HTTPException(status_code=400, detail=f"missing settings: {', '.join(missing)}")
    results = emit([make_test_event()], notifiers=[spec.factory(settings)], settings=settings)
    ok = bool(results) and all(r["ok"] for r in results)
    return {"integration": name, "ok": ok, "results": results}
