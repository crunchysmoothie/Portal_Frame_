"""Printable, auditable calculation sheets for isolated pad foundations."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence


def _number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _text(value: Any) -> str:
    return escape(str(value if value not in (None, "") else "-"))


def _rows(items: Sequence[tuple[str, Any, str]]) -> str:
    return "".join(
        f"<tr><th>{escape(label)}</th><td>{_text(value)}</td><td>{escape(unit)}</td></tr>"
        for label, value, unit in items
    )


def _case_rows(cases: Sequence[Mapping[str, Any]], columns: Sequence[tuple[str, str, int]]) -> str:
    body = []
    for case in cases:
        cells = [f"<td>{_text(case.get('combination'))}</td>"]
        for key, _label, digits in columns:
            cells.append(f"<td>{_number(case.get(key), digits)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(body) or '<tr><td colspan="12">No stored cases.</td></tr>'


def _table_header(columns: Sequence[tuple[str, str, int]]) -> str:
    return "<th>Combination</th>" + "".join(
        f"<th>{escape(label)}</th>" for _key, label, _digits in columns
    )


def _support_sheet(support: Mapping[str, Any], inputs: Mapping[str, Any]) -> str:
    service = support.get("serviceability", {})
    structural = support.get("structural", {})
    stability = support.get("uls_stability", {})
    bearing = service.get("bearing", {})
    sls_sliding = service.get("sliding", {})
    uplift = service.get("uplift", {})
    uls_sliding = stability.get("sliding", {})
    overturning = stability.get("overturning", {})
    structural_checks = structural.get("checks", [])
    check_rows = "".join(
        "<tr>"
        f"<td>{_text(item.get('name'))}</td>"
        f"<td>{_number(item.get('demand'), 3)}</td>"
        f"<td>{_number(item.get('capacity'), 3)}</td>"
        f"<td>{_text(item.get('units'))}</td>"
        f"<td>{_number(item.get('utilisation'), 3)}</td>"
        f"<td class=\"{str(item.get('status', '')).lower()}\">{_text(item.get('status'))}</td>"
        "</tr>"
        for item in structural_checks
    )
    service_columns = (
        ("vertical_reaction_kN", "V (kN)", 2),
        ("horizontal_reaction_kN", "H (kN)", 2),
        ("transferred_base_moment_kNm", "Mbase (kNm)", 2),
        ("q_min_kpa", "qmin (kPa)", 2),
        ("q_max_kpa", "qmax (kPa)", 2),
        ("bearing_utilisation", "Bearing util.", 3),
        ("sliding_safety_factor", "Sliding SF", 2),
        ("overturning_safety_factor", "OT SF", 2),
    )
    structural_columns = (
        ("vertical_reaction_kN", "V (kN)", 2),
        ("horizontal_reaction_kN", "H (kN)", 2),
        ("transferred_base_moment_kNm", "Mbase (kNm)", 2),
        ("design_q_max_kpa", "q*max (kPa)", 2),
        ("required_steel_frame_mm2_per_m", "As req L", 1),
        ("required_steel_transverse_mm2_per_m", "As req B", 1),
        ("governing_utilisation", "Gov. util.", 3),
    )
    stability_columns = (
        ("sliding_normal_force_kN", "N (kN)", 2),
        ("horizontal_reaction_kN", "H (kN)", 2),
        ("sliding_friction_resistance_kN", "Rf (kN)", 2),
        ("sliding_passive_resistance_kN", "Rp (kN)", 2),
        ("sliding_safety_factor", "Sliding SF", 2),
        ("overturning_safety_factor", "OT SF", 2),
    )
    return f"""
<section class="sheet support-sheet">
  <header><div><h1>Isolated Pad Foundation</h1><p>Support {_text(support.get('node'))}</p></div>
  <div class="status {str(support.get('status', '')).lower()}">{_text(support.get('status'))}</div></header>
  <h2>Governing calculation substitutions</h2>
  <div class="equations">
    <p><strong>Plan area:</strong> A = L x B = {_number(inputs.get('length_m'))} x {_number(inputs.get('width_m'))} = {_number(float(inputs.get('length_m', 0) or 0) * float(inputs.get('width_m', 0) or 0), 3)} m2</p>
    <p><strong>SLS bearing:</strong> q = N/A +/- 6M/(B L2); governing qmax = {_number(bearing.get('q_max_kpa'))} kPa &lt;= {_number(inputs.get('permissible_bearing_kpa'))} kPa, utilisation {_number(bearing.get('utilisation'), 3)}.</p>
    <p><strong>ULS sliding:</strong> R = mu N + Rp = {_number(uls_sliding.get('friction_resistance_kN'))} + {_number(uls_sliding.get('passive_resistance_kN'))} = {_number(uls_sliding.get('total_resistance_kN'))} kN; SF = R/H = {_number(uls_sliding.get('safety_factor'))} (required {_number(stability.get('required_sliding_safety_factor'))}).</p>
    <p><strong>ULS overturning:</strong> SF = Mstabilising / Moverturning = {_number(overturning.get('stabilising_moment_kNm'))} / {_number(overturning.get('overturning_moment_kNm'))} = {_number(overturning.get('safety_factor'))}.</p>
    <p><strong>Uplift:</strong> net vertical action = {_number(uplift.get('net_vertical_kN'))} kN; status {_text(uplift.get('status'))}.</p>
  </div>
  <h2>Service bearing and stability cases</h2>
  <table class="wide"><thead><tr>{_table_header(service_columns)}</tr></thead><tbody>{_case_rows(service.get('cases', []), service_columns)}</tbody></table>
  <h2>ULS reinforced-concrete cases</h2>
  <table class="wide"><thead><tr>{_table_header(structural_columns)}</tr></thead><tbody>{_case_rows(structural.get('cases', []), structural_columns)}</tbody></table>
  <h2>Governing reinforced-concrete checks</h2>
  <table><thead><tr><th>Check</th><th>Demand</th><th>Capacity</th><th>Units</th><th>Utilisation</th><th>Status</th></tr></thead><tbody>{check_rows}</tbody></table>
  <h2>ULS stability cases</h2>
  <table class="wide"><thead><tr>{_table_header(stability_columns)}</tr></thead><tbody>{_case_rows(stability.get('cases', []), stability_columns)}</tbody></table>
  <p class="footnote">All reactions and governing combination names are reproduced from the stored analysis snapshot. Checks marked as hold points or input-required are not converted into automatic acceptance.</p>
</section>"""


def build_foundation_report_html(
    result: Mapping[str, Any], project: Mapping[str, Any] | None = None
) -> str:
    """Return printable HTML calculation sheets for a completed design result."""

    project = project or {}
    inputs = result.get("inputs", {})
    derived = result.get("derived", {})
    automatic = result.get("automatic_design", {})
    assumptions = "".join(f"<li>{_text(item)}</li>" for item in result.get("assumptions", []))
    warnings = "".join(f"<li>{_text(item)}</li>" for item in result.get("warnings", []))
    references = "".join(f"<li>{_text(item)}</li>" for item in result.get("references", []))
    input_rows = _rows((
        ("Plan shape", inputs.get("plan_shape", automatic.get("plan_shape")), ""),
        ("Footing length", _number(inputs.get("length_m")), "m"),
        ("Footing breadth", _number(inputs.get("width_m")), "m"),
        ("Plan aspect ratio", _number(automatic.get("plan_aspect_ratio", max(float(inputs.get('length_m', 1) or 1), float(inputs.get('width_m', 1) or 1)) / min(float(inputs.get('length_m', 1) or 1), float(inputs.get('width_m', 1) or 1))), 3), "<= 1.500"),
        ("Footing thickness", _number(inputs.get("thickness_mm"), 0), "mm"),
        ("Loaded area", f"{_number(inputs.get('loaded_length_mm'), 0)} x {_number(inputs.get('loaded_width_mm'), 0)}", "mm"),
        ("Concrete strength", _number(inputs.get("concrete_strength_mpa"), 0), "MPa"),
        ("Reinforcement", f"T{_number(inputs.get('bar_diameter_mm'), 0)} @ {_number(inputs.get('bar_spacing_mm'), 0)}", "mm each way"),
        ("Nominal cover", _number(inputs.get("cover_mm"), 0), "mm"),
        ("Permissible bearing", _number(inputs.get("permissible_bearing_kpa")), "kPa"),
        ("Soil cover", _number(inputs.get("soil_cover_depth_m")), "m"),
        ("Base friction coefficient", _number(inputs.get("friction_coefficient")), ""),
        ("Passive resistance", inputs.get("passive_resistance"), ""),
    ))
    derived_rows = _rows((
        ("Concrete volume per pad", _number(derived.get("footing_volume_m3"), 3), "m3"),
        ("Footing self-weight", _number(derived.get("footing_self_weight_kN")), "kN"),
        ("Soil cover weight", _number(derived.get("soil_cover_weight_kN")), "kN"),
        ("Pedestal self-weight", _number(derived.get("pedestal_self_weight_kN")), "kN"),
        ("Effective depth", _number(derived.get("effective_depth_mm"), 0), "mm"),
        ("Provided steel", _number(derived.get("provided_steel_mm2_per_m"), 1), "mm2/m"),
        ("Rankine Kp", _number(derived.get("passive_coefficient_kp"), 3), ""),
    ))
    support_sheets = "".join(
        _support_sheet(support, inputs) for support in result.get("supports", [])
    )
    css = """
@page{size:A4 landscape;margin:12mm}*{box-sizing:border-box}body{font:10px Arial,sans-serif;color:#17333a;margin:0;background:#eef2f2}.sheet{width:277mm;min-height:190mm;margin:8mm auto;padding:10mm;background:#fff;break-after:page;page-break-after:always}.sheet:last-child{break-after:auto;page-break-after:auto}header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #176b68;margin-bottom:8px}h1{font-size:22px;margin:0 0 3px}h2{font-size:13px;color:#0d4846;margin:10px 0 4px}p{margin:3px 0}.status{font-size:18px;font-weight:bold;padding:7px 12px;border-radius:5px}.pass{color:#116443;background:#e4f5ee}.fail{color:#9a2f29;background:#fce8e6}.grid{display:grid;grid-template-columns:1fr 1fr;gap:8mm}table{width:100%;border-collapse:collapse;margin:3px 0 8px}th,td{border:1px solid #b8c7c5;padding:3px 4px;text-align:left;vertical-align:top}thead th{background:#176b68;color:white}.wide{font-size:8px}.equations{border-left:4px solid #176b68;background:#f4f8f7;padding:5px 8px}.warning{background:#fff4d9;border-left:5px solid #b87900;padding:7px}.footnote{font-size:8px;color:#526866}@media print{body{background:#fff}.sheet{margin:0;padding:8mm}}
"""
    title = _text(project.get("name") or project.get("project_name") or "PortalFrame project")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Foundation calculation sheets</title><style>{css}</style></head><body>
<section class="sheet"><header><div><h1>Foundation Calculation Sheets</h1><p>{title}</p></div><div class="status {str(result.get('status', '')).lower()}">{_text(result.get('status'))}</div></header>
<p><strong>Design standard:</strong> {_text(result.get('standard'))} | <strong>Mode:</strong> {_text(result.get('mode'))} | <strong>Common support count:</strong> {_text(result.get('whole_building_support_count', len(result.get('supports', []))))}</p>
<div class="grid"><div><h2>Selected footing</h2><table>{input_rows}</table></div><div><h2>Derived quantities</h2><table>{derived_rows}</table></div></div>
<h2>Calculation method</h2><div class="equations"><p>Bearing: q = N/A +/- 6M/(B L2), with triangular contact used when e &gt; L/6.</p><p>Sliding: R = mu N + Rp and SF = R/H. Passive resistance, when enabled, uses Rp = 0.5 gamma Kp D2 B times the entered mobilisation factor and the stated ULS partial factor.</p><p>Overturning: SF = stabilising moment / overturning moment. Reinforced-concrete flexure, one-way shear and punching shear follow the selected standard.</p></div>
<div class="grid"><div><h2>Assumptions</h2><ul>{assumptions}</ul></div><div><h2>Warnings and exclusions</h2><div class="warning"><ul>{warnings}</ul></div></div>
<h2>References</h2><ul>{references}</ul></section>{support_sheets}</body></html>"""


def write_foundation_report_html(
    result: Mapping[str, Any], path: str | Path, project: Mapping[str, Any] | None = None
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_foundation_report_html(result, project), encoding="utf-8")
    return path.resolve()
