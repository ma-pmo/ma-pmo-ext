"""Reports A5 produced, to read and download.

GET /reports                          : newest first (?scope=, ?kind=, ?limit=)
GET /reports/latest                   : the newest one (?scope=, ?kind=), as report.v2
GET /reports/{id}                     : one report as report.v2
GET /reports/{id}/export?format=...   : md | html | csv | json, as a download
                                        (?inline=true shows HTML in the browser instead)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ma_pmo.reports import render, store

router = APIRouter(tags=["reports"])


@router.get("/reports")
def list_reports(scope: str | None = None, kind: str | None = None, limit: int = 50) -> list:
    return store.list_reports(scope, kind, max(1, min(limit, 500)))


@router.get("/reports/latest")
def latest_report(scope: str | None = None, kind: str | None = None) -> dict:
    found = store.latest(scope, kind)
    if found is None:
        raise HTTPException(status_code=404, detail="no report yet")
    return {"id": found[0], **found[1]}


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict:
    content = store.get_report(report_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"unknown report {report_id!r}")
    return {"id": report_id, **content}


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, format: str = "html", inline: bool = False) -> Response:
    if format not in render.FORMATS:
        raise HTTPException(status_code=400, detail=f"format must be one of {render.FORMATS}")
    content = store.get_report(report_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"unknown report {report_id!r}")
    text = render.render(content, report_id, format)
    name = f"{report_id}-{content.get('kind', 'status')}-{content['facts']['as_of']}.{format}"
    disposition = "inline" if inline and format == "html" else "attachment"
    return Response(text, media_type=render.MEDIA[format],
                     headers={"Content-Disposition": f'{disposition}; filename="{name}"'})
