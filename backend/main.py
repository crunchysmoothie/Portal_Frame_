"""HTTP API for the PortalFrame application.

This first API seam intentionally exposes project state and completed analysis
snapshots.  Analysis submission will be added after the current command-line
inputs are extracted into validated request models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from analysis_snapshot import load_analysis_snapshot


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
            "submit_analysis": False,
            "generate_reports": False,
        },
    }


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
