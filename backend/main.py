"""HTTP API for the PortalFrame application.

This first API seam intentionally exposes project state and completed analysis
snapshots.  Analysis submission will be added after the current command-line
inputs are extracted into validated request models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from analysis_snapshot import load_analysis_snapshot
from backend.analysis_service import (
    get_analysis_artifact,
    get_analysis_job,
    public_analysis_job,
    submit_analysis_job,
)
from preview_geometry import build_preview_geometry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "output" / "analysis" / "analysis_results.json"

app = FastAPI(
    title="PortalFrame API",
    description="Local application API for PortalFrame analysis and reporting.",
    version="0.1.0",
)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a small liveness response for the UI and local tooling."""

    return {"status": "ok", "service": "portalframe-api"}


@app.get("/api/project", tags=["system"])
def project_info() -> dict[str, Any]:
    """Describe the capabilities currently exposed by the application API."""

    return {
        "name": "PortalFrame",
        "api_version": app.version,
        "analysis_engine": "portal_frame_analysis",
        "capabilities": {
            "latest_analysis": DEFAULT_SNAPSHOT_PATH.exists(),
            "layout_preview": True,
            "submit_analysis": True,
            "generate_reports": True,
        },
    }


@app.post("/api/preview", tags=["preview"])
def preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Return analysis-independent frame, purlin, girt and bracing geometry."""

    try:
        return build_preview_geometry(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/analysis", status_code=202, tags=["analysis"])
def submit_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Queue a complete isolated analysis with deformation rendering disabled."""

    try:
        return submit_analysis_job(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/analysis/{analysis_id}/status", tags=["analysis"])
def analysis_status(analysis_id: str) -> dict[str, Any]:
    """Return queued, running, complete or failed status for one analysis."""

    try:
        return public_analysis_job(get_analysis_job(analysis_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/analysis/{analysis_id}/results", tags=["analysis"])
def analysis_results(analysis_id: str) -> dict[str, Any]:
    """Return the design summary and artifact links for a completed analysis."""

    try:
        job = get_analysis_job(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job["status"] not in {"complete", "failed"}:
        raise HTTPException(status_code=409, detail="Analysis is not complete.")
    return public_analysis_job(job)


@app.get("/api/analysis/{analysis_id}/artifacts/{artifact}", tags=["analysis"])
def analysis_artifact(analysis_id: str, artifact: str):
    """Download a generated design report or markup drawing artifact."""

    try:
        path = get_analysis_artifact(analysis_id, artifact)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type = {
        ".pdf": "application/pdf",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type=(
            "inline" if path.suffix.lower() == ".html" else "attachment"
        ),
    )


@app.get("/api/analysis/latest", tags=["analysis"])
def latest_analysis() -> dict[str, Any]:
    """Return the latest self-contained analysis snapshot, when available."""

    if not DEFAULT_SNAPSHOT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No completed analysis snapshot is available yet.",
        )

    try:
        return load_analysis_snapshot(DEFAULT_SNAPSHOT_PATH)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"The analysis snapshot could not be loaded: {exc}",
        ) from exc
