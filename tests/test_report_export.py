"""Roadmap 12: Word export, the report link in notifications, report quality in the evaluation."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.cli import main as cli
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.integrations.events import events_from_message
from ma_pmo.reports import render, store

SCOPE = "PORTFOLIO#2026-Q1"


def _run(kind="status", lang=None):
    from ma_pmo.core.i18n import use_lang

    with use_lang(lang):
        return ReportingAgent().run({"goal": "report", "task_ref": SCOPE, "kind": kind,
                                     "as_of": "2026-02-16"})


def test_word_export_has_the_report_sections(tmp_path):
    docx = pytest.importorskip("docx")
    _run("exception", lang="ko")
    rid, content = store.latest(SCOPE, "exception")
    doc = docx.Document(io.BytesIO(render.render_bytes(content, rid, "docx")))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "예외 보고서" in text and "직전 보고 이후" in text and "권고 조치" in text
    assert doc.tables  # header and the sections' tables
    out = tmp_path / "r.docx"
    assert cli(["report", "export", rid, "--format", "docx", "--out", str(out)]) == 0
    assert out.read_bytes()[:2] == b"PK"  # a zip, as .docx files are
    assert cli(["report", "export", rid, "--format", "docx"]) == 1  # needs --out
    with pytest.raises(ValueError):
        render.render(content, rid, "docx")  # binary: render_bytes only


def test_the_api_serves_word():
    pytest.importorskip("docx")
    from ma_pmo.api.main import app

    _run("status")
    rid, _ = store.latest(SCOPE, "status")
    r = TestClient(app).get(f"/reports/{rid}/export", params={"format": "docx"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_the_notification_links_to_the_report():
    out = _run("executive")
    rid, _ = store.latest(SCOPE)
    msg = AgentMessage(sender="A5", receiver="A1", intent=Intent.INFORM, task_ref=SCOPE,
                       payload=MessagePayload(schema_="report.v1",
                                              data=out["outputs"][0]["data"]))
    [event] = events_from_message(msg, False)
    assert event.url.endswith(f"/reports?id={rid}") and event.data["report_id"] == rid
    assert event.title.startswith("Executive summary ready")


def test_report_quality_counts_checked_narratives(monkeypatch):
    from ma_pmo.core.schemas.payloads.report_v1 import ReportV1

    def llm(text):
        return lambda *a, **k: ReportV1(scope=SCOPE, executive_summary=text, project_status=[])

    before = store.quality()
    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", llm("3 projects."))
    _run("status")
    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", llm("PROJ-31 is 95% done."))
    _run("status")
    after = store.quality()
    assert after["llm_checked"] - before["llm_checked"] == 2
    assert after["llm_replaced"] - before["llm_replaced"] == 1
    assert "95" in after["ungrounded_examples"]
    assert 0 < after["faithful_rate"] < 1
