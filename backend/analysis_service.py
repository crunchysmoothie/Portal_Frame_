"""Isolated analysis jobs and report artifacts for the local application API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any, Mapping, Sequence
from uuid import uuid4

from connection_workflow.cad import (
    dwg_converter_status,
    write_connection_dwg,
    write_connection_dxf,
    write_connection_pdf,
)
from connection_workflow.design import (
    design_base_plate_connections,
    design_portal_connections,
)
from connection_workflow.report import write_connection_report_html
from reporting_workflow.calculations import (
    ReportScope,
    load_calculation_sheet_data,
    write_html_report,
    write_json_data,
)
from reporting_workflow.markup import write_markup
from reporting_workflow.boq import (
    build_structural_boq_takeoff,
    build_truss_structural_boq_takeoff,
    write_structural_boq_xlsx,
)
from reporting_workflow.civil_boq import build_civil_boq_takeoff, write_civil_boq_xlsx
from foundation_workflow.design import design_pad_foundations
from reporting_workflow.snapshot import load_analysis_snapshot
from portal_workflow.preview import build_preview_geometry
from portal_workflow.prokon_export import (
    build_gable_columns_comparison,
    build_girder_comparison,
    build_portal_comparison,
    build_truss_comparison,
    write_comparison_bundle,
)
from portal_workflow.runner import run_analysis
from truss_workflow import (
    build_truss_analysis_snapshot,
    design_truss,
    preview_truss,
    write_truss_html,
    write_truss_json,
    write_truss_markup_html,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_ROOT = PROJECT_ROOT / "output" / "analysis" / "jobs"
_JOB_ID = re.compile(r"^[0-9a-f]{12}$")
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="structural-analysis")
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
    structural_system = str(payload.get("structural_system", "Portal frame"))
    if structural_system not in {"Portal frame", "Truss"}:
        raise ValueError("structural_system must be 'Portal frame' or 'Truss'.")
    if structural_system == "Truss" and not isinstance(payload.get("truss_data"), Mapping):
        raise ValueError("truss_data must be an object for Truss analysis.")
    # This validates the complete geometry and finite layout choices before the
    # heavier analysis job is accepted.
    if structural_system == "Truss":
        preview_truss(payload)
    else:
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


def _design_summary(
    calculation_data,
    analysis_id: str,
    connection_design: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
    gable_columns = [
        {
            "name": item.get("name", ""),
            "section": item.get("section", ""),
            "utilisation": item.get("utilisation", 0.0),
            "status": (
                "PASS"
                if float(item.get("utilisation", 0.0)) <= 1.0
                else "FAIL"
            ),
        }
        for item in bracing.get("gable_columns", [])
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
        "additional_permanent_roof_loads_kpa": project.get(
            "additional_permanent_roof_loads_kpa", {}
        ),
        "additional_permanent_roof_load_total_kpa": project.get(
            "additional_permanent_roof_load_total_kpa", 0
        ),
        "minimum_additional_permanent_roof_load_total_kpa": project.get(
            "minimum_additional_permanent_roof_load_total_kpa", 0
        ),
        "portal_sections": {
            "rafter": project.get("rafter_section", ""),
            "column": project.get("column_section", ""),
        },
        "haunches": {
            "source_rafter_section": project.get("rafter_section", ""),
            "source_section_depth_mm": project.get(
                "rafter_section_depth_mm", 0
            ),
            "source_flange_width_mm": project.get(
                "rafter_flange_width_mm", 0
            ),
            "source_clear_web_depth_mm": project.get(
                "rafter_clear_web_depth_mm", 0
            ),
            "source_flange_thickness_mm": project.get(
                "rafter_flange_thickness_mm", 0
            ),
            "maximum_cut_depth_mm": project.get(
                "maximum_haunch_cut_depth_mm", 0
            ),
            "eaves": {
                "used": project.get("use_eaves_haunch", "No") == "Yes",
                "length_mm": project.get("eaves_haunch_length_mm", 0),
                "left_length_mm": project.get(
                    "left_eaves_haunch_length_mm",
                    project.get("eaves_haunch_length_mm", 0),
                ),
                "right_length_mm": project.get(
                    "right_eaves_haunch_length_mm",
                    project.get("eaves_haunch_length_mm", 0),
                ),
                "depth_mode": project.get(
                    "eaves_haunch_depth_mode", "Specified Depth"
                ),
                "depth_mm": project.get("eaves_haunch_depth_mm", 0),
            },
            "apex": {
                "used": project.get("use_apex_haunch", "No") == "Yes",
                "length_mm": project.get("apex_haunch_length_mm", 0),
                "depth_mode": project.get(
                    "apex_haunch_depth_mode", "Specified Depth"
                ),
                "depth_mm": project.get("apex_haunch_depth_mm", 0),
            },
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
            "uses_permanent_deflection_baseline": project.get(
                "use_permanent_deflection_baseline", True
            ),
            "ignored_vertical_limit_combinations": (
                ["1.1 DL + 1.0 LL"]
                if project.get(
                    "ignore_1_1_dl_1_0_ll_vertical_deflection_limit", False
                )
                else []
            ),
            "max_horizontal_deflection_mm": frame.get(
                "max_horizontal_deflection_mm", 0
            ),
            "horizontal_deflection_ratio": frame.get(
                "horizontal_deflection_ratio"
            ),
            "horizontal_combination": frame.get(
                "horizontal_deflection_combination", ""
            ),
            "max_vertical_deflection_mm": frame.get(
                "max_vertical_deflection_mm", 0
            ),
            "vertical_deflection_ratio": frame.get(
                "vertical_deflection_ratio"
            ),
            "vertical_combination": frame.get(
                "vertical_deflection_combination", ""
            ),
            "vertical_deflection_basis": frame.get(
                "vertical_deflection_basis", ""
            ),
            "permanent_baseline_deflection_mm": frame.get(
                "permanent_baseline_deflection_mm", 0
            ),
            "total_vertical_deflection_mm": frame.get(
                "total_vertical_deflection_mm", 0
            ),
            "signed_permanent_baseline_deflection_mm": frame.get(
                "signed_permanent_baseline_deflection_mm", 0
            ),
            "signed_total_vertical_deflection_mm": frame.get(
                "signed_total_vertical_deflection_mm", 0
            ),
            "signed_variable_vertical_deflection_mm": frame.get(
                "signed_variable_vertical_deflection_mm", 0
            ),
            "roof_drainage_status": frame.get(
                "roof_drainage_status", "PASS"
            ),
            "roof_drainage_failures": frame.get(
                "roof_drainage_failures", []
            ),
            "ignored_vertical_deflections": frame.get(
                "ignored_vertical_deflections", []
            ),
        },
        "steel_mass_breakdown": frame.get("steel_mass_breakdown", {}),
        "gable_columns": gable_columns,
        "bracing_members": brace_members,
        "load_case_visualisation": dict(calculation_data.visualisation),
        "warnings": list(calculation_data.warnings),
        "connection_design": dict(connection_design or {}),
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
        if payload.get("structural_system") == "Truss":
            result = design_truss(payload)
            truss_snapshot = build_truss_analysis_snapshot(
                result, payload, analysis_id
            )
            connection_result = design_base_plate_connections(truss_snapshot)
            result["connection_design"] = connection_result
            result["validation_status"] = (
                "CALCULATION DRAFT - truss members, eave columns and column "
                "base plates calculated; truss joints and independent "
                "verification outstanding"
            )
            result["warnings"] = [
                (
                    "CALCULATION SCOPE: truss member actions, axial resistance, "
                    "slenderness, vertical deflection, eave columns and column "
                    "base plates are calculated. Truss bearings, gussets, "
                    "splices, restraint connections and independent project "
                    "verification remain outstanding."
                    if str(item).startswith("CALCULATION SCOPE:")
                    else item
                )
                for item in result.get("warnings", [])
            ]
            truss_snapshot["results"]["connection_design"] = connection_result
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(
                json.dumps(truss_snapshot, indent=2), encoding="utf-8"
            )
            report_html = write_truss_html(
                result, report_dir / "preliminary_truss_design_report.html"
            )
            report_json = write_truss_json(
                result, report_dir / "preliminary_truss_design_report.json"
            )
            markup_html = write_truss_markup_html(
                result, markup_dir / "truss_member_markup.html"
            )
            connection_path = directory / "connections" / "connection_design.json"
            connection_path.parent.mkdir(parents=True, exist_ok=True)
            connection_path.write_text(
                json.dumps(connection_result, indent=2), encoding="utf-8"
            )
            connection_report = write_connection_report_html(
                connection_result,
                report_dir / "truss_base_plate_calculations.html",
            )
            connection_pdf = write_connection_pdf(
                connection_result,
                markup_dir / "truss_base_plate_markup.pdf",
            )
            connection_dxf = write_connection_dxf(
                connection_result,
                markup_dir / "truss_base_plate_markup.dxf",
            )
            comparison = build_truss_comparison(result)
            comparison_with_columns = build_truss_comparison(
                result, include_columns=True
            )
            girder_comparison = build_girder_comparison(result)
            gable_comparison = build_gable_columns_comparison(
                result.get("bracing_design", {}),
                comparison["load_combinations"],
                analysis_id=analysis_id,
                source_system="Truss",
            )
            comparison_bundle = write_comparison_bundle({
                "truss": comparison,
                "truss-with-columns": comparison_with_columns,
                "girder": girder_comparison,
                "gable-columns": gable_comparison,
            }, directory / "prokon")
            comparison_paths = comparison_bundle["models"]["truss"]
            prokon_artifacts = {
                "prokon-input-json": str(comparison_paths["json"]),
                "prokon-input-a03": str(comparison_paths["a03"]),
                "prokon-package-zip": str(comparison_bundle["zip"]),
            }
            for key, paths in comparison_bundle["models"].items():
                prokon_artifacts[f"prokon-{key}-json"] = str(paths["json"])
                prokon_artifacts[f"prokon-{key}-a03"] = str(paths["a03"])
            job.update(
                {
                    "status": "complete",
                    "completed": _now(),
                    "message": "Preliminary truss, girder and eave-column design is complete.",
                    "snapshot_path": str(snapshot_path),
                    "design_summary": result,
                    "artifact_paths": {
                        "truss-report-html": str(report_html),
                        "truss-report-json": str(report_json),
                        "truss-markup-html": str(markup_html),
                        "connection-design-json": str(connection_path),
                        "connection-report-html": str(connection_report),
                        "connection-markup-pdf": str(connection_pdf),
                        "connection-markup-dxf": str(connection_dxf),
                        **prokon_artifacts,
                    },
                }
            )
            _write_job(job)
            return

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
            scope=ReportScope(payload.get("report_scope", ReportScope.CRITICAL.value)),
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
        connection_result = design_portal_connections(
            load_analysis_snapshot(written_snapshot)
        )
        portal_snapshot = load_analysis_snapshot(written_snapshot)
        comparison = build_portal_comparison(portal_snapshot)
        gable_comparison = build_gable_columns_comparison(
            portal_snapshot.get("results", {}).get("bracing_design", {}),
            comparison["load_combinations"],
            analysis_id=analysis_id,
            source_system="Portal frame",
        )
        comparison_bundle = write_comparison_bundle({
            "portal-frame": comparison,
            "gable-columns": gable_comparison,
        }, directory / "prokon")
        comparison_paths = comparison_bundle["models"]["portal-frame"]
        connection_path = directory / "connections" / "connection_design.json"
        connection_path.parent.mkdir(parents=True, exist_ok=True)
        connection_path.write_text(
            json.dumps(connection_result, indent=2), encoding="utf-8"
        )
        connection_report = write_connection_report_html(
            connection_result,
            report_dir / "portal_connection_calculations.html",
        )
        connection_pdf = write_connection_pdf(
            connection_result,
            markup_dir / "portal_connection_markup.pdf",
        )
        connection_dxf = write_connection_dxf(
            connection_result,
            markup_dir / "portal_connection_markup.dxf",
        )
        converter = dwg_converter_status()
        connection_dwg: Path | None = None
        if converter["available"]:
            try:
                connection_dwg = write_connection_dwg(
                    connection_dxf,
                    markup_dir / "portal_connection_markup.dwg",
                )
                converter = {
                    **converter,
                    "created": True,
                    "reason": "AutoCAD created the calculated 2D DWG.",
                }
            except Exception as exc:
                converter = {
                    **converter,
                    "created": False,
                    "reason": "AutoCAD could not create the DWG during this run.",
                    "error_type": type(exc).__name__,
                }
        else:
            converter = {**converter, "created": False}

        artifact_paths = {
            "design-report-html": str(report_html),
            "design-report-json": str(report_json),
            "markup-html": str(markup_html),
            "connection-design-json": str(connection_path),
            "connection-report-html": str(connection_report),
            "connection-markup-pdf": str(connection_pdf),
            "connection-markup-dxf": str(connection_dxf),
            "prokon-input-json": str(comparison_paths["json"]),
            "prokon-input-a03": str(comparison_paths["a03"]),
            "prokon-package-zip": str(comparison_bundle["zip"]),
        }
        for key, paths in comparison_bundle["models"].items():
            artifact_paths[f"prokon-{key}-json"] = str(paths["json"])
            artifact_paths[f"prokon-{key}-a03"] = str(paths["a03"])
        if connection_dwg is not None:
            artifact_paths["connection-markup-dwg"] = str(connection_dwg)
        if markup_pdf is not None:
            artifact_paths["markup-pdf"] = str(markup_pdf)

        design_summary = _design_summary(
            calculation_data,
            analysis_id,
            connection_result,
        )
        design_summary["connection_exports"] = {
            "formats": [
                "PDF",
                "DXF",
                *(["DWG"] if connection_dwg is not None else []),
            ],
            "three_dimensional_export": False,
            "dwg": converter,
        }
        job.update(
            {
                "status": "complete",
                "completed": _now(),
                "message": (
                    "Frame analysis, member design and post-analysis connection "
                    "calculations are complete."
                ),
                "snapshot_path": str(written_snapshot),
                "design_summary": design_summary,
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


def design_foundations(
    analysis_id: str, inputs: Mapping[str, Any]
) -> dict[str, Any]:
    """Run and persist a post-analysis isolated-pad design."""

    job = get_analysis_job(analysis_id)
    if job.get("status") != "complete":
        raise ValueError("Foundation design requires a completed analysis.")
    snapshot_value = job.get("snapshot_path")
    if not snapshot_value:
        raise ValueError("The completed analysis has no foundation-reaction snapshot.")
    snapshot_path = Path(snapshot_value)
    if not snapshot_path.is_file():
        raise ValueError("The analysis snapshot is unavailable.")
    snapshot = load_analysis_snapshot(snapshot_path)
    result = design_pad_foundations(snapshot, inputs)
    support_quantities = snapshot.get("results", {}).get(
        "foundation_support_quantities", {}
    )
    if support_quantities:
        for support in result.get("supports", []):
            support["quantity"] = int(
                support_quantities.get(str(support.get("node", "")), 1)
            )
        result["whole_building_support_count"] = sum(
            int(item.get("quantity", 1)) for item in result.get("supports", [])
        )
    output_path = _job_dir(analysis_id) / "foundation" / "foundation_design.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    artifact_paths = dict(job.get("artifact_paths", {}))
    artifact_paths["foundation-design-json"] = str(output_path)
    job["artifact_paths"] = artifact_paths
    job["foundation_design"] = result
    _write_job(job)
    return result


def create_structural_boq(
    analysis_id: str,
    additional_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create and persist a tender-format structural-steel BOQ workbook."""

    job = get_analysis_job(analysis_id)
    if job.get("status") != "complete":
        raise ValueError("Structural BOQ export requires a completed analysis.")
    snapshot_value = job.get("snapshot_path")
    if not snapshot_value:
        raise ValueError("The completed analysis has no BOQ quantity snapshot.")
    snapshot_path = Path(snapshot_value)
    if not snapshot_path.is_file():
        raise ValueError("The completed analysis snapshot is unavailable.")
    connection_design = (
        job.get("design_summary", {}).get("connection_design", {})
    )
    snapshot = load_analysis_snapshot(snapshot_path)
    if job.get("design_summary", {}).get("structural_system") == "Truss":
        takeoff = build_truss_structural_boq_takeoff(
            snapshot,
            connection_design,
            additional_items,
        )
    else:
        takeoff = build_structural_boq_takeoff(
            snapshot,
            connection_design,
            additional_items,
        )
    output_dir = _job_dir(analysis_id) / "boq"
    workbook_path = write_structural_boq_xlsx(
        takeoff,
        output_dir / "structural_steel_boq.xlsx",
    )
    takeoff_path = output_dir / "structural_steel_boq_quantities.json"
    takeoff_path.write_text(json.dumps(takeoff, indent=2), encoding="utf-8")
    artifact_paths = dict(job.get("artifact_paths", {}))
    artifact_paths.update({
        "structural-steel-boq-xlsx": str(workbook_path),
        "structural-steel-boq-json": str(takeoff_path),
    })
    job["artifact_paths"] = artifact_paths
    job["structural_boq"] = {
        "generated": takeoff["generated"],
        "fabricated_steel_mass_t": takeoff["fabricated_steel_mass_t"],
        "calculated_item_count": (
            len(takeoff["steel_items"])
            + len(takeoff["bolt_items"])
            + len(takeoff["cladding_items"])
        ),
        "additional_item_count": len(takeoff["additional_items"]),
    }
    _write_job(job)
    return {
        "status": "complete",
        "summary": job["structural_boq"],
        "download_url": (
            f"/api/analysis/{analysis_id}/artifacts/"
            "structural-steel-boq-xlsx"
        ),
        "quantities_download_url": (
            f"/api/analysis/{analysis_id}/artifacts/"
            "structural-steel-boq-json"
        ),
    }


def create_civil_boq(
    analysis_id: str,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the first civil/concrete BOQ sheet from the supplied example."""

    job = get_analysis_job(analysis_id)
    if job.get("status") != "complete":
        raise ValueError("Civil BOQ export requires a completed analysis.")
    snapshot_value = job.get("snapshot_path")
    if not snapshot_value:
        raise ValueError("The completed analysis has no civil-quantity snapshot.")
    foundation = job.get("foundation_design")
    if not foundation:
        raise ValueError("Run the foundation design before creating the civil BOQ.")
    snapshot = load_analysis_snapshot(Path(snapshot_value))
    takeoff = build_civil_boq_takeoff(
        snapshot,
        foundation,
        inputs,
        job.get("design_summary", {}).get("connection_design", {}),
    )
    output_dir = _job_dir(analysis_id) / "boq"
    workbook_path = write_civil_boq_xlsx(takeoff, output_dir / "civil_concrete_boq.xlsx")
    json_path = output_dir / "civil_concrete_boq_quantities.json"
    json_path.write_text(json.dumps(takeoff, indent=2), encoding="utf-8")
    artifact_paths = dict(job.get("artifact_paths", {}))
    artifact_paths["civil-boq-xlsx"] = str(workbook_path)
    artifact_paths["civil-boq-json"] = str(json_path)
    job["artifact_paths"] = artifact_paths
    job["civil_boq"] = {
        "generated": _now(),
        "item_count": len(takeoff["items"]),
    }
    _write_job(job)
    return {
        "status": "complete",
        "summary": job["civil_boq"],
        "download_url": f"/api/analysis/{analysis_id}/artifacts/civil-boq-xlsx",
        "quantities_download_url": f"/api/analysis/{analysis_id}/artifacts/civil-boq-json",
    }
