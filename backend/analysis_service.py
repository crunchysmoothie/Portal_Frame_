"""Isolated analysis jobs and report artifacts for the local application API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any, Mapping
from uuid import uuid4

from design_calculations import (
    ReportScope,
    load_calculation_sheet_data,
    write_html_report,
    write_json_data,
)
from draughtsman_markup import write_markup
from preview_geometry import build_preview_geometry
from run_full_analysis import run_analysis


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_ROOT = PROJECT_ROOT / "output" / "analysis" / "jobs"
_JOB_ID = re.compile(r"^[0-9a-f]{12}$")
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="portal-analysis")
_LOCK = Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _validate_job_id(analysis_id: str) -> str:
    if not _JOB_ID.fullmatch(str(analysis_id)):
        raise KeyError("Unknown analysis job.")
    return str(analysis_id)


def _job_dir(analysis_id: str) -> Path:
    return JOBS_ROOT / _validate_job_id(analysis_id)


def _manifest_path(analysis_id: str) -> Path:
    return _job_dir(analysis_id) / "job.json"


def _write_job(job: Mapping[str, Any]) -> None:
    analysis_id = str(job["analysis_id"])
    path = _manifest_path(analysis_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(job), indent=2), encoding="utf-8")
    temporary.replace(path)
    with _LOCK:
        _JOBS[analysis_id] = dict(job)


def _normalise_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("The analysis request must be a JSON object.")
    for key in ("project", "building_data", "wind_data"):
        if not isinstance(payload.get(key), Mapping):
            raise ValueError(f"{key} must be an object.")
    # This validates the complete geometry and finite layout choices before the
    # heavier analysis job is accepted.
    build_preview_geometry(payload)
    required_wind = (
        "fundamental_basic_wind_speed",
        "return_period",
        "terrain_category",
        "topographic_factor",
        "altitude",
    )
    missing = [key for key in required_wind if key not in payload["wind_data"]]
    if missing:
        raise ValueError(f"wind_data is missing: {', '.join(missing)}.")
    # Round-trip through JSON to detach the worker input from caller mutations.
    return json.loads(json.dumps(payload))


def _design_summary(calculation_data, analysis_id: str) -> dict[str, Any]:
    frame = dict(calculation_data.frame_summary)
    project = dict(calculation_data.project)
    bracing = dict(calculation_data.bracing_design)
    brace_members = [
        {
            "member_type": item.get("member_type", ""),
            "section": item.get("section", ""),
            "utilisation": item.get("utilisation", 0.0),
        }
        for item in bracing.get("bracing_members", [])
    ]
    return {
        "analysis_id": analysis_id,
        "project": {
            "name": project.get("project_name", ""),
            "number": project.get("project_number", ""),
            "designer": project.get("designer", ""),
        },
        "building": {
            "type": project.get("building_type", ""),
            "roof": project.get("roof_type", ""),
            "span_mm": project.get("gable_width_mm", 0),
            "length_mm": project.get("building_length_mm", 0),
            "roof_pitch_deg": frame.get("roof_pitch_deg", 0),
        },
        "portal_sections": {
            "rafter": project.get("rafter_section", ""),
            "column": project.get("column_section", ""),
        },
        "governing_strength": {
            "status": frame.get("overall_status", ""),
            "member": frame.get("governing_member", ""),
            "member_type": frame.get("governing_member_type", ""),
            "combination": frame.get("governing_combination", ""),
            "check": frame.get("governing_check", ""),
            "utilisation": frame.get("governing_utilisation", 0),
        },
        "serviceability": {
            "max_horizontal_deflection_mm": frame.get(
                "max_horizontal_deflection_mm", 0
            ),
            "horizontal_combination": frame.get(
                "horizontal_deflection_combination", ""
            ),
            "max_vertical_deflection_mm": frame.get(
                "max_vertical_deflection_mm", 0
            ),
            "vertical_combination": frame.get(
                "vertical_deflection_combination", ""
            ),
        },
        "steel_mass_breakdown": frame.get("steel_mass_breakdown", {}),
        "bracing_members": brace_members,
        "load_case_visualisation": dict(calculation_data.visualisation),
        "warnings": list(calculation_data.warnings),
    }


def _run_job(analysis_id: str, payload: dict[str, Any]) -> None:
    job = get_analysis_job(analysis_id)
    job.update({"status": "running", "started": _now(), "message": "Running structural analysis."})
    _write_job(job)

    directory = _job_dir(analysis_id)
    input_path = directory / "input_data.json"
    snapshot_path = directory / "analysis_results.json"
    report_dir = directory / "report"
    markup_dir = directory / "markup"

    try:
        written_snapshot = run_analysis(
            payload["building_data"],
            payload["wind_data"],
            input_path=input_path,
            snapshot_path=snapshot_path,
            render=False,
            project_metadata=payload["project"],
        )
        if written_snapshot is None:
            raise RuntimeError("No acceptable portal-frame section pair was found.")

        calculation_data = load_calculation_sheet_data(
            written_snapshot,
            scope=ReportScope.CRITICAL,
        )
        report_html = write_html_report(
            calculation_data, report_dir / "portal_frame_design_report.html"
        )
        report_json = write_json_data(
            calculation_data, report_dir / "portal_frame_design_report.json"
        )
        report_source = json.loads(report_json.read_text(encoding="utf-8"))
        markup_html, markup_pdf = write_markup(
            report_source, markup_dir, create_pdf=True
        )

        artifact_paths = {
            "design-report-html": str(report_html),
            "design-report-json": str(report_json),
            "markup-html": str(markup_html),
        }
        if markup_pdf is not None:
            artifact_paths["markup-pdf"] = str(markup_pdf)

        job.update(
            {
                "status": "complete",
                "completed": _now(),
                "message": "Analysis, HTML design report and markup are complete.",
                "snapshot_path": str(written_snapshot),
                "design_summary": _design_summary(calculation_data, analysis_id),
                "artifact_paths": artifact_paths,
            }
        )
    except Exception as exc:
        job.update(
            {
                "status": "failed",
                "completed": _now(),
                "message": "Analysis failed.",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    _write_job(job)


def submit_analysis_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalised = _normalise_payload(payload)
    analysis_id = uuid4().hex[:12]
    job = {
        "analysis_id": analysis_id,
        "status": "queued",
        "created": _now(),
        "message": "Analysis is queued.",
    }
    _write_job(job)
    _EXECUTOR.submit(_run_job, analysis_id, normalised)
    return public_analysis_job(job)


def get_analysis_job(analysis_id: str) -> dict[str, Any]:
    analysis_id = _validate_job_id(analysis_id)
    with _LOCK:
        cached = _JOBS.get(analysis_id)
    if cached is not None:
        return dict(cached)
    path = _manifest_path(analysis_id)
    if not path.exists():
        raise KeyError("Unknown analysis job.")
    job = json.loads(path.read_text(encoding="utf-8"))
    with _LOCK:
        _JOBS[analysis_id] = dict(job)
    return job


def public_analysis_job(job: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        key: value
        for key, value in job.items()
        if key not in {"artifact_paths", "snapshot_path"}
    }
    artifacts = {}
    for key, path in job.get("artifact_paths", {}).items():
        artifacts[key] = {
            "filename": Path(path).name,
            "download_url": f"/api/analysis/{job['analysis_id']}/artifacts/{key}",
        }
    result["artifacts"] = artifacts
    return result


def get_analysis_artifact(analysis_id: str, artifact: str) -> Path:
    job = get_analysis_job(analysis_id)
    path_value = job.get("artifact_paths", {}).get(artifact)
    if path_value is None:
        raise KeyError("Unknown analysis artifact.")
    path = Path(path_value).resolve()
    directory = _job_dir(analysis_id).resolve()
    if directory not in path.parents or not path.is_file():
        raise KeyError("Analysis artifact is unavailable.")
    return path
