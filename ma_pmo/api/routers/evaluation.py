"""Evaluation — H1–H5 results, the evaluation report and the data template (§9).

GET  /eval                       : H1–H5 metrics as JSON (+ one-line verdict per hypothesis)
GET  /eval/report?format=md|html : evaluation report on the demo data
GET  /templates/data.zip         : evaluation data template (?empty=true for headers only)
POST /templates/validate         : check a filled-in template (zip in the request body)
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from ma_pmo.eval import workflow
from ma_pmo.eval.dataset import COLUMNS, generate_data_template, load_dataset
from ma_pmo.eval.harness import run_all
from ma_pmo.eval.report import build_report, render, summarize

router = APIRouter(tags=["eval"])

_MAX_UPLOAD = 5 * 1024 * 1024


def _has_telemetry() -> bool:
    from sqlalchemy import select

    from ma_pmo.db.models import KpiEvent
    from ma_pmo.db.session import get_session

    with get_session() as s:
        return s.scalars(select(KpiEvent.id).limit(1)).first() is not None


@router.get("/eval")
def evaluate(populate: bool | None = None) -> dict:
    """Compute H1–H5 metrics. populate=true runs the deterministic agents first; by default
    that happens only on an empty database, so opening the page does not queue new approvals."""
    if populate is None:
        populate = not _has_telemetry()
    results = run_all(populate=populate)
    return {**results, "summary": summarize(results)}


@router.get("/eval/retrieval")
def retrieval_quality() -> dict:
    """A7 lessons search on the labeled queries: lexical vs. offline vector search."""
    from ma_pmo.eval.retrieval import compare

    return compare()


@router.get("/eval/report")
def evaluation_report(format: str = "html") -> Response:
    if format not in ("md", "html"):
        raise HTTPException(status_code=400, detail="format must be md or html")
    results = workflow.evaluate_demo()
    report = build_report(results, scope=workflow.DEMO_SCOPE, source=workflow.demo_source())
    text = render(report, format)
    if format == "html":
        return HTMLResponse(text)
    return PlainTextResponse(
        text, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ma-pmo-evaluation-report.md"'},
    )


@router.get("/templates/data.zip")
def data_template(empty: bool = False) -> Response:
    with tempfile.TemporaryDirectory() as tmp:
        paths = generate_data_template(tmp, examples=not empty)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                zf.write(p, arcname=f"ma-pmo-eval-data/{p.name}")
    return Response(
        buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ma-pmo-eval-data.zip"'},
    )


@router.post("/templates/validate")
async def validate_template(request: Request) -> dict:
    """Validate a zip of the filled-in template without importing it anywhere."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="send the zip file as the request body")
    if len(body) > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="zip is larger than 5 MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="not a zip file") from e
    wanted = {*COLUMNS, "baselines.json"}
    with tempfile.TemporaryDirectory() as tmp, zf:
        # Only known template files are extracted, and the target path is built from our own
        # file names, never from archive paths (folders inside the zip are flattened).
        members = {Path(i.filename).name: i for i in zf.infolist() if not i.is_dir()}
        for name in sorted(wanted):
            info = members.get(name)
            if info is not None and info.file_size <= _MAX_UPLOAD:
                (Path(tmp) / name).write_bytes(zf.read(info))
        ds, issues = load_dataset(tmp)
    errors = [i for i in issues if i.level == "error"]
    return {
        "valid": not errors,
        "scope": ds.scope,
        "counts": {
            "projects": len(ds.projects),
            "tasks": sum(len(p["tasks"]) for p in ds.projects),
            "resources": len(ds.resources),
            "risk_labels": len(ds.labels),
        },
        "issues": [i.__dict__ for i in issues],
    }
