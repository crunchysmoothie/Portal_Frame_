"""Printable report artifacts for generic preliminary truss designs."""

from __future__ import annotations

from html import escape
import json
import math
from pathlib import Path
from typing import Any, Mapping


def write_truss_json(result: Mapping[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2), encoding="utf-8")
    return path


def _number(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return escape(str(value or ""))


def _member_calculation_rows(schedule: list[Mapping[str, Any]]) -> str:
    return "".join(
        "<tr>"
        f"<td>{escape(str(item.get('member', '')))}</td>"
        f"<td>{escape(str(item.get('role', '')).replace('_', ' '))}</td>"
        f"<td>{escape(str(item.get('i_node', '')))} - {escape(str(item.get('j_node', '')))}</td>"
        f"<td>{escape(str(item.get('fabrication_group', '')).replace('_', ' '))}</td>"
        f"<td>{escape(str(item.get('section', {}).get('designation', '')))}</td>"
        f"<td>{_number(item.get('length_mm', 0), 0)}</td>"
        f"<td>{_number(item.get('effective_length_mm', 0), 0)}</td>"
        f"<td>{_number(item.get('minimum_radius_mm', 0), 1)}</td>"
        f"<td>{_number(item.get('slenderness_ratio', 0), 1)} / {_number(item.get('slenderness_limit', 0), 0)}</td>"
        f"<td>{_number(item.get('maximum_tension_kn', 0), 1)} / {_number(item.get('tension_kn', 0), 1)}<br><small>{escape(str(item.get('tension_combination', '')))}</small></td>"
        f"<td>{_number(item.get('maximum_compression_kn', 0), 1)} / {_number(item.get('compression_kn', 0), 1)}<br><small>{escape(str(item.get('compression_combination', '')))}</small></td>"
        f"<td>{_number(item.get('tension_utilisation', 0), 3)} / {_number(item.get('compression_utilisation', 0), 3)} / {_number(item.get('slenderness_utilisation', 0), 3)}</td>"
        f"<td>{escape(str(item.get('governing_check', '')).replace('_', ' '))}: {_number(item.get('utilisation', 0), 3)}</td>"
        f"<td>{'PASS' if float(item.get('utilisation', 0) or 0) <= 1 else 'FAIL'}</td>"
        "</tr>"
        for item in schedule
    )


def _wind_audit_html(best: Mapping[str, Any]) -> str:
    audit = best.get("load_audit", {})
    wind = audit.get("wind_calculation", {})
    if not audit:
        return ""

    pressure_tables = []
    for table in audit.get("wind_zone_tables", []):
        rows = "".join(
            "<tr>"
            f"<td>{escape(str(item.get('zone', '')))}</td>"
            f"<td>{_number(item.get('cpe', 0), 2)}</td>"
            f"<td>{_number(item.get('zone_length_m', 0), 2)}</td>"
            f"<td>{_number(item.get('cpi=0.2_pressure_kpa', 0), 3)}</td>"
            f"<td>{_number(item.get('cpi=0.2_line_load_kn_m', 0), 3)}</td>"
            f"<td>{_number(item.get('cpi=-0.3_pressure_kpa', 0), 3)}</td>"
            f"<td>{_number(item.get('cpi=-0.3_line_load_kn_m', 0), 3)}</td>"
            "</tr>"
            for item in table.get("rows", [])
        )
        pressure_tables.append(
            f"<h3>{escape(str(table.get('label', 'Wind zones')))}</h3>"
            "<table class=\"wind-table\"><thead><tr>"
            "<th>Zone</th><th>cpe</th><th>Zone length (m)</th>"
            "<th>Net p, cpi=+0.2 (kPa)</th><th>Line load (kN/m)</th>"
            "<th>Net p, cpi=-0.3 (kPa)</th><th>Line load (kN/m)</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    resultant_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('case', '')))}</td>"
        f"<td>{item.get('loaded_node_count', '')}</td>"
        f"<td>{_number(item.get('sum_fx_kn', 0), 3)}</td>"
        f"<td>{_number(item.get('sum_fy_kn', 0), 3)}</td>"
        "</tr>"
        for item in audit.get("wind_case_resultants", [])
    )
    applied_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('case', '')))}</td>"
        f"<td>{escape(str(item.get('truss_member', '')))}</td>"
        f"<td>{escape(str(item.get('i_node', '')))} - {escape(str(item.get('j_node', '')))}</td>"
        f"<td>{_number(item.get('global_x_start_m', 0), 3)} to {_number(item.get('global_x_end_m', 0), 3)}</td>"
        f"<td>{_number(item.get('loaded_length_m', 0), 3)}</td>"
        f"<td>{escape(str(item.get('direction', '')))}</td>"
        f"<td>{_number(item.get('line_load_start_kn_m', 0), 3)} to {_number(item.get('line_load_end_kn_m', 0), 3)}</td>"
        f"<td>{_number(item.get('equivalent_i_fx_kn', 0), 3)}, {_number(item.get('equivalent_i_fy_kn', 0), 3)}</td>"
        f"<td>{_number(item.get('equivalent_j_fx_kn', 0), 3)}, {_number(item.get('equivalent_j_fy_kn', 0), 3)}</td>"
        "</tr>"
        for item in audit.get("applied_wind_segments", [])
    )

    def combination_rows(key: str) -> str:
        return "".join(
            "<tr>"
            f"<td>{escape(str(item.get('name', '')))}</td>"
            f"<td>{escape(', '.join(f'{case}={float(factor):g}' for case, factor in item.get('factors', {}).items()))}</td>"
            "</tr>"
            for item in audit.get(key, [])
            if any(
                str(case).upper().startswith("W")
                for case in item.get("factors", {})
            )
        )

    return f"""
<section id="wind-load-audit">
<h2 class="page-break">Wind loading calculation and truss application audit</h2>
<p>This section records the wind data and loads generated for the selected rank-1 geometry. Pressures are recovered from the generated line loads using the stated tributary truss spacing. The segment table is the actual source-load overlap converted to truss panel-point actions.</p>
<table><tbody>
<tr><th>Fundamental basic wind speed</th><td>{_number(wind.get('fundamental_basic_wind_speed_m_s', 0), 2)} m/s</td></tr>
<tr><th>Design basic wind speed</th><td>{_number(wind.get('design_basic_wind_speed_m_s', 0), 2)} m/s</td></tr>
<tr><th>Return period</th><td>{_number(wind.get('return_period_years', 0), 0)} years</td></tr>
<tr><th>Terrain</th><td>{escape(str(wind.get('terrain_category', '')))}; roughness factor {_number(wind.get('terrain_roughness_factor', 0), 4)}</td></tr>
<tr><th>Topography / altitude</th><td>{_number(wind.get('topographic_factor', 0), 3)} / {_number(wind.get('altitude_m', 0), 1)} m</td></tr>
<tr><th>Peak velocity pressure</th><td>{_number(wind.get('peak_velocity_pressure_kpa', 0), 3)} kPa</td></tr>
<tr><th>Roof pitch / tributary truss spacing</th><td>{_number(wind.get('roof_pitch_deg', 0), 3)} degrees / {_number(wind.get('tributary_width_m', 0), 3)} m</td></tr>
<tr><th>Internal pressure basis</th><td><code>{escape(json.dumps(wind.get('internal_pressure', {}), sort_keys=True))}</code></td></tr>
</tbody></table>
{"".join(pressure_tables)}
<h3>Characteristic wind-case resultants applied to one transverse truss</h3>
<table><thead><tr><th>Case</th><th>Loaded nodes</th><th>Sum Fx (kN)</th><th>Sum Fy (kN)</th></tr></thead><tbody>{resultant_rows}</tbody></table>
<h3>Applied wind line loads and equivalent panel-point actions</h3>
<p><small>{escape(str(audit.get('sign_convention', '')))}</small></p>
<table class="wind-segments"><thead><tr><th>Case</th><th>Top chord</th><th>Nodes</th><th>Global x-range (m)</th><th>Loaded slope length (m)</th><th>Direction</th><th>w start to end (kN/m)</th><th>At i: Fx, Fy (kN)</th><th>At j: Fx, Fy (kN)</th></tr></thead><tbody>{applied_rows}</tbody></table>
<h3>ULS wind combinations</h3>
<table><thead><tr><th>Combination</th><th>Factors</th></tr></thead><tbody>{combination_rows('uls_combinations')}</tbody></table>
<h3>SLS wind combinations</h3>
<table><thead><tr><th>Combination</th><th>Factors</th></tr></thead><tbody>{combination_rows('sls_combinations')}</tbody></table>
</section>
"""


def write_truss_markup_html(
    result: Mapping[str, Any], path: str | Path
) -> Path:
    """Write a member-marked rank-1 elevation and section schedule."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    solutions = list(result.get("ranked_solutions", []))
    if not solutions:
        raise ValueError("A truss markup requires at least one ranked solution.")
    best = solutions[0]
    geometry = best["geometry"]
    nodes = {
        str(item["name"]): item for item in geometry.get("nodes", [])
    }
    schedule = {
        str(item["member"]): item
        for item in best.get("member_schedule", [])
    }
    designations = sorted({
        str(item.get("section", {}).get("designation", ""))
        for item in schedule.values()
        if item.get("section", {}).get("designation")
    })
    section_marks = {
        designation: f"S{index}"
        for index, designation in enumerate(designations, 1)
    }

    width, height = 1800, 760
    plot_left, plot_right, plot_top, plot_bottom = 70, 1730, 110, 610
    x_values = [float(item["x_mm"]) for item in nodes.values()]
    y_values = [float(item["y_mm"]) for item in nodes.values()]
    min_x, max_x = min(x_values), max(x_values)
    min_y, max_y = min(y_values), max(y_values)
    scale = min(
        (plot_right - plot_left) / max(max_x - min_x, 1.0),
        (plot_bottom - plot_top) / max(max_y - min_y, 1.0),
    )
    fitted_width = (max_x - min_x) * scale
    fitted_height = (max_y - min_y) * scale
    origin_x = plot_left + (plot_right - plot_left - fitted_width) / 2
    baseline_y = plot_bottom - (plot_bottom - plot_top - fitted_height) / 2

    def sx(value: float) -> float:
        return origin_x + (value - min_x) * scale

    def sy(value: float) -> float:
        return baseline_y - (value - min_y) * scale

    role_colours = {
        "top_chord": "#173C3A",
        "bottom_chord": "#173C3A",
        "diagonal": "#C94B40",
        "vertical": "#3E8E89",
        "support_vertical": "#C17B00",
    }
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        '<style>text{font-family:Arial,sans-serif}.label{paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}</style>',
        f'<text x="50" y="48" font-size="28" font-weight="700" fill="#173C3A">{escape(str(result.get("project", {}).get("name", "Truss")))} - member markup</text>',
        f'<text x="50" y="78" font-size="16" fill="#607472">Rank 1 - {escape(str(geometry.get("topology", "")))} - depth {_number(float(geometry.get("depth_mm", 0)) / 1000, 2)} m - section order {escape(str(result.get("design_basis", {}).get("member_section_order", {}).get("selected", "")))}</text>',
    ]
    for member in geometry.get("members", []):
        name = str(member["name"])
        start = nodes[str(member["i_node"])]
        end = nodes[str(member["j_node"])]
        x1, y1 = sx(float(start["x_mm"])), sy(float(start["y_mm"]))
        x2, y2 = sx(float(end["x_mm"])), sy(float(end["y_mm"]))
        colour = role_colours.get(str(member.get("role", "")), "#173C3A")
        svg.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{colour}" stroke-width="4" stroke-linecap="round"/>'
        )
    for support in geometry.get("support_nodes", []):
        node = nodes[str(support)]
        x_value, y_value = sx(float(node["x_mm"])), sy(float(node["y_mm"]))
        svg.append(
            f'<path d="M {x_value - 11:.2f} {y_value + 15:.2f} '
            f'L {x_value + 11:.2f} {y_value + 15:.2f} L {x_value:.2f} '
            f'{y_value:.2f} Z" fill="#C17B00"/>'
        )
    svg.extend([
        '<text x="50" y="690" font-size="15" font-weight="700" fill="#173C3A">Full elevation overview - see enlarged labelled strips below</text>',
        '<text x="50" y="718" font-size="13" fill="#607472">Section marks and utilisations are calculation-review information. Connections are not shown.</text>',
        "</svg>",
    ])

    detail_svgs: list[str] = []
    # Keep the calculation markup legible when a truss has many short panels.
    # A strip normally carries no more than about fourteen member callouts.
    detail_count = min(8, max(1, int(math.ceil(len(schedule) / 14))))
    for detail_index in range(detail_count):
        zone_start = min_x + (max_x - min_x) * detail_index / detail_count
        zone_end = min_x + (max_x - min_x) * (detail_index + 1) / detail_count
        zone_members = [
            member
            for member in geometry.get("members", [])
            if zone_start - 1e-6
            <= (
                float(nodes[str(member["i_node"])]["x_mm"])
                + float(nodes[str(member["j_node"])]["x_mm"])
            ) / 2.0
            <= zone_end + 1e-6
        ]
        detail_width, detail_height = 1800, 560
        d_left, d_right, d_top, d_bottom = 60, 1740, 80, 470
        d_scale = min(
            (d_right - d_left) / max(zone_end - zone_start, 1.0),
            (d_bottom - d_top) / max(max_y - min_y, 1.0),
        )
        d_origin_x = d_left
        d_baseline = d_bottom - (
            (d_bottom - d_top) - (max_y - min_y) * d_scale
        ) / 2

        def dsx(value: float) -> float:
            return d_origin_x + (value - zone_start) * d_scale

        def dsy(value: float) -> float:
            return d_baseline - (value - min_y) * d_scale

        detail = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {detail_width} {detail_height}">',
            f'<rect width="{detail_width}" height="{detail_height}" fill="#FFFFFF"/>',
            '<style>text{font-family:Arial,sans-serif}</style>',
            f'<text x="50" y="40" font-size="23" font-weight="700" fill="#173C3A">Detail {detail_index + 1} of {detail_count} - x = {_number(zone_start / 1000, 1)} to {_number(zone_end / 1000, 1)} m</text>',
        ]
        for member_index, member in enumerate(zone_members):
            name = str(member["name"])
            start = nodes[str(member["i_node"])]
            end = nodes[str(member["j_node"])]
            x1, y1 = dsx(float(start["x_mm"])), dsy(float(start["y_mm"]))
            x2, y2 = dsx(float(end["x_mm"])), dsy(float(end["y_mm"]))
            item = schedule.get(name, {})
            designation = str(item.get("section", {}).get("designation", ""))
            section_mark = section_marks.get(designation, "-")
            utilisation = float(item.get("utilisation", 0.0) or 0.0)
            colour = role_colours.get(
                str(member.get("role", "")), "#173C3A"
            )
            detail.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" '
                f'y2="{y2:.2f}" stroke="{colour}" stroke-width="5" '
                f'stroke-linecap="round"/>'
            )
            dx, dy = x2 - x1, y2 - y1
            length_screen = max(math.hypot(dx, dy), 1.0)
            role = str(member.get("role", ""))
            label_x, label_y = (x1 + x2) / 2, (y1 + y2) / 2
            if role == "top_chord":
                label_y -= 18.0
            elif role == "bottom_chord":
                label_y += 28.0
            elif role in {"vertical", "support_vertical"}:
                # Keep vertical-member callouts aligned with their member so
                # they do not compete with the diagonal labels at mid-depth.
                label_y += 5.0
            else:
                offset = 14.0 if member_index % 2 == 0 else -18.0
                label_x -= dy / length_screen * offset
                label_y += dx / length_screen * offset
            label_text = (
                f"{name} / {section_mark} / U={utilisation:.2f}"
            )
            label_transform = (
                f' transform="rotate(-90 {label_x:.2f} {label_y:.2f})"'
                if role in {"vertical", "support_vertical"}
                else ""
            )
            detail.extend([
                f'<rect{label_transform} x="{label_x - 94:.2f}" y="{label_y - 17:.2f}" '
                f'width="188" height="22" rx="4" fill="#FFFFFF" '
                f'opacity="0.90"/>',
                f'<text{label_transform} class="label" x="{label_x:.2f}" y="{label_y:.2f}" '
                f'text-anchor="middle" font-size="16" font-weight="700" '
                f'fill="#102C2B">{escape(label_text)}</text>',
            ])
        detail.extend([
            '<text x="50" y="530" font-size="14" fill="#607472">Label format: member / section mark / governing utilisation. Geometry at one physical scale within this detail strip.</text>',
            "</svg>",
        ])
        detail_svgs.append("".join(detail))

    section_rows = "".join(
        "<tr>"
        f"<td>{section_marks[designation]}</td>"
        f"<td>{escape(designation)}</td>"
        f"<td>{escape(', '.join(sorted(name for name, item in schedule.items() if str(item.get('section', {}).get('designation', '')) == designation)))}</td>"
        "</tr>"
        for designation in designations
    )
    member_rows = "".join(
        "<tr>"
        f"<td>{escape(name)}</td>"
        f"<td>{escape(str(item.get('role', '')).replace('_', ' '))}</td>"
        f"<td>{section_marks.get(str(item.get('section', {}).get('designation', '')), '-')}</td>"
        f"<td>{escape(str(item.get('section', {}).get('designation', '')))}</td>"
        f"<td>{escape(str(item.get('i_node', '')))} - {escape(str(item.get('j_node', '')))}</td>"
        f"<td>{_number(item.get('maximum_tension_kn', 0), 1)}</td>"
        f"<td>{_number(item.get('maximum_compression_kn', 0), 1)}</td>"
        f"<td>{_number(item.get('utilisation', 0), 3)}</td>"
        "</tr>"
        for name, item in sorted(schedule.items())
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Truss member markup</title>
<style>
body{{font:14px Arial,sans-serif;color:#17333a;margin:24px}}
h1,h2{{color:#183b56}} svg{{width:100%;height:auto;border:1px solid #c9d3d9}}
table{{width:100%;border-collapse:collapse;margin:12px 0 28px}}
th{{background:#183b56;color:#fff;text-align:left;padding:7px}}
td{{border-bottom:1px solid #c9d3d9;padding:6px;vertical-align:top}}
tr:nth-child(even){{background:#f7fafb}}
.warning{{background:#fff4d9;border-left:5px solid #b87900;padding:12px}}
@media print{{body{{margin:8mm}} .page-break{{page-break-before:always}}}}
</style></head><body>
<div class="warning"><strong>Review markup.</strong> This drawing identifies calculated truss members, selected sections and governing utilisations. It is not a fabrication drawing and contains no connection detailing.</div>
{"".join(svg)}
<h2>Enlarged labelled member strips</h2>
{"".join(detail_svgs)}
<h2>Section schedule</h2>
<table><thead><tr><th>Mark</th><th>Section</th><th>Members</th></tr></thead><tbody>{section_rows}</tbody></table>
<h2 class="page-break">Member-by-member review schedule</h2>
<table><thead><tr><th>Member</th><th>Role</th><th>Mark</th><th>Section</th><th>Nodes</th><th>Max T* (kN)</th><th>Max C* (kN)</th><th>Util.</th></tr></thead><tbody>{member_rows}</tbody></table>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def write_truss_html(result: Mapping[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    project = result.get("project", {})
    solutions = list(result.get("ranked_solutions", []))
    ranked_rows = "".join(
        "<tr>"
        f"<td>{item.get('rank', '')}</td>"
        f"<td>{_number(item['geometry']['depth_mm'] / 1000, 2)}</td>"
        f"<td>{item['geometry']['panel_count']}</td>"
        f"<td>{_number(item['geometry']['panel_width_mm'], 0)}</td>"
        f"<td>{_number(item['arrangement_mass_kg'], 1)}</td>"
        f"<td>{_number(item['practical_cost_equivalent_kg'], 1)}</td>"
        f"<td>{_number(item['lightest_member_arrangement_mass_kg'], 1)}</td>"
        f"<td>{item['unique_section_count']}</td>"
        f"<td>{_number(item['governing_strength']['utilisation'], 3)}</td>"
        f"<td>{_number(item['serviceability']['maximum_vertical_deflection_mm'], 1)} / "
        f"{_number(item['serviceability']['limit_mm'], 1)}</td>"
        "</tr>"
        for item in solutions
    )
    best = solutions[0] if solutions else {}
    restraint = best.get("chord_restraint_layout", {})
    top_restraint = restraint.get("top_chord", {})
    bottom_restraint = restraint.get("bottom_chord", {})
    layout = best.get("building_layout", {})
    layout_columns = layout.get("columns", {})
    transverse = layout.get("transverse", {})
    longitudinal = layout.get("longitudinal", {})
    support_arrangement = layout.get("support_arrangement", {})
    eave_column = best.get("eave_column_design", {})
    centre_column = best.get("centre_column_design", {})
    purlins = best.get("purlins", {})
    column_strength = eave_column.get("governing_strength", {})
    column_serviceability = eave_column.get("serviceability", {})
    girder = best.get("girder_design", {})
    if girder.get("status") == "NOT_REQUIRED":
        girder_rows = '<tr><th>Status</th><td>Not required for this support arrangement</td></tr>'
    else:
        girder_rows = (
            f'<tr><th>Status</th><td>{escape(str(girder.get("status", "")))}</td></tr>'
            f'<tr><th>Lightest depth</th><td>{_number(girder.get("geometry", {}).get("depth_mm", 0) / 1000, 2)} m</td></tr>'
            f'<tr><th>Span</th><td>{_number(girder.get("geometry", {}).get("span_mm", 0) / 1000, 2)} m</td></tr>'
            f'<tr><th>Total girder mass</th><td>{_number(girder.get("total_mass_kg", 0), 1)} kg</td></tr>'
            f'<tr><th>Governing utilisation</th><td>{_number(girder.get("governing_strength", {}).get("utilisation", 0), 3)}</td></tr>'
        )
    member_rows = _member_calculation_rows(list(best.get("member_schedule", [])))
    chord_group_rows = "".join(
        "<tr>"
        f"<td>{item.get('span', '')}</td>"
        f"<td>{escape(str(item.get('role', '')).replace('_', ' ').title())}</td>"
        f"<td>{escape(str(item.get('section', '')))}</td>"
        f"<td>{item.get('member_count', '')}</td>"
        f"<td>{escape(str(item.get('governing_member', '')))}</td>"
        f"<td>{_number(item.get('governing_utilisation', 0), 3)}</td>"
        "</tr>"
        for item in best.get("chord_fabrication_groups", [])
    )
    web_group_rows = "".join(
        "<tr>"
        f"<td>{item.get('span', '')}</td>"
        f"<td>{escape(str(item.get('role', '')).replace('_', ' ').title())}</td>"
        f"<td>{item.get('group_index', '')}</td>"
        f"<td>{escape(str(item.get('section', '')))}</td>"
        f"<td>{item.get('member_count', '')}</td>"
        f"<td>{escape(str(item.get('governing_member', '')))}</td>"
        f"<td>{_number(item.get('governing_utilisation', 0), 3)}</td>"
        "</tr>"
        for item in best.get("web_fabrication_groups", [])
    )
    bearing_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('bearing_node', '')))}</td>"
        f"<td>{escape(str(item.get('member', '')))}</td>"
        f"<td>{escape(str(item.get('source', '')))}</td>"
        f"<td>{escape(str(item.get('section', {}).get('designation', '')))}</td>"
        f"<td>{_number(item.get('section', {}).get('area_mm2', 0), 0)}</td>"
        "</tr>"
        for item in best.get("bearing_support_verticals", [])
    )
    girder_member_rows = _member_calculation_rows(
        list(girder.get("member_schedule", []))
    )
    warnings = "".join(
        f"<li>{escape(str(item))}</li>" for item in result.get("warnings", [])
    )
    basis = result.get("design_basis", {})
    section_order = basis.get("member_section_order", {})
    ordered_candidates = section_order.get("candidate_designations", [])
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Truss Design Calculation - Draft</title>
<style>
body{{font:14px Arial,sans-serif;color:#17333a;margin:28px;line-height:1.4}}
h1,h2{{color:#183b56}} h1{{margin-bottom:4px}} .warning{{background:#fce4d6;border-left:5px solid #c65911;padding:14px;margin:18px 0}}
.meta{{display:grid;grid-template-columns:180px 1fr;gap:5px 12px;background:#f4f7f9;padding:14px}}
table{{width:100%;border-collapse:collapse;margin:12px 0 24px}} th{{background:#183b56;color:white;text-align:left;padding:7px}}
td{{border-bottom:1px solid #c9d3d9;padding:6px;vertical-align:top}} tr:nth-child(even){{background:#f7fafb}}
.calc{{font-size:10px}} .formula{{background:#eef5f4;border-left:4px solid #258475;padding:12px;margin:12px 0 20px}}
small{{color:#667681}} .wind-table,.wind-segments{{font-size:9px}} .page-break{{break-before:page;page-break-before:always}}
@page{{size:A4 landscape;margin:10mm}}
@media print{{body{{margin:0}} .no-print{{display:none}} tr{{break-inside:avoid;page-break-inside:avoid}}}}
</style></head><body>
<h1>Truss Design Calculation - Draft</h1><div><strong>{escape(str(result.get('validation_status', '')))}</strong></div>
<div class="meta">
<div>Project</div><div>{escape(str(project.get('name', 'Untitled project')))}</div>
<div>Project number</div><div>{escape(str(project.get('number', '')))}</div>
<div>Designer</div><div>{escape(str(project.get('designer', '')))}</div>
<div>Engine</div><div>{escape(str(result.get('engine', '')))}</div>
<div>Topology / joints</div><div>{escape(str(basis.get('topology', '')))} / {escape(str(basis.get('joint_model', '')))}</div>
<div>Truss member section order</div><div>{escape(str(section_order.get('selected', '')))}; {len(ordered_candidates)} candidates searched in the recorded order</div>
<div>Standards</div><div>{escape(str(basis.get('load_standard', '')))}; {escape(str(basis.get('steel_standard', '')))}</div>
<div>Top-chord restraint</div><div>Every {top_restraint.get('brace_every_n_purlins', '')} purlin(s), full building length; maximum spacing {_number(top_restraint.get('maximum_spacing_mm', 0) / 1000, 2)} m</div>
<div>Bottom-chord restraint</div><div>Every {bottom_restraint.get('brace_every_n_purlins', '')} purlin(s), full building length; maximum spacing {_number(bottom_restraint.get('maximum_spacing_mm', 0) / 1000, 2)} m</div>
<div>Building layout</div><div>{_number(longitudinal.get('building_length_mm', 0) / 1000, 1)} m long; transverse bays {escape(' / '.join(_number(value / 1000, 1) for value in transverse.get('bay_spans_mm', [])))} m</div>
<div>Support sequence</div><div>{escape(' / '.join(str(value) for value in support_arrangement.get('sequence', [])))}</div>
  <div>Columns</div><div>{layout_columns.get('eave_count', '')} main eave columns; {layout_columns.get('internal_count', '')} internal support columns</div>
  <div>Rank 1 mass</div><div>{_number(best.get('total_truss_mass_kg', 0), 1)} kg trusses + {_number(eave_column.get('total_mass_kg', 0), 1)} kg eave columns + {_number(girder.get('total_mass_kg', 0), 1)} kg girders + {_number(centre_column.get('total_mass_kg', 0), 1)} kg centre columns + {_number(purlins.get('mass_kg', 0), 1)} kg purlins = {_number(best.get('arrangement_mass_kg', 0), 1)} kg total modelled steel</div>
  <div>Purlin quantity</div><div>{escape(str(purlins.get('section', '')))}; {int(purlins.get('line_count', 0))} lines × {_number(purlins.get('building_length_m', 0), 1)} m = {_number(purlins.get('total_length_m', 0), 1)} m at {_number(purlins.get('mass_per_m_kg', 0), 2)} kg/m</div>
  <div>Centre-column design</div><div>{escape(str(centre_column.get('status', 'NOT_DESIGNED')))}; {escape(str(centre_column.get('material', 'Steel')))}; {escape(str(centre_column.get('section', 'main-column proxy')))}; axial-only check</div>
  <div>Practical cost comparison</div><div>{_number(best.get('practical_cost_equivalent_kg', 0), 1)} kg-equivalent including an {_number(float(basis.get('platework_cost_allowance_fraction', 0)) * 100, 0)}% platework allowance on primary truss, column and girder steel; purlins are included without that allowance. Individually optimised-web comparison {_number(best.get('lightest_member_arrangement_mass_kg', 0), 1)} kg total</div>
</div>
<div class="warning"><strong>Engineering hold point</strong><ul>{warnings}</ul></div>
{_wind_audit_html(best)}
<h2>Ranked passing solutions</h2>
<table><thead><tr><th>Practical rank</th><th>Depth (m)</th><th>Panels</th><th>Panel (mm)</th><th>Total modelled mass (kg)</th><th>Practical kg-eq.</th><th>Individual-web total (kg)</th><th>Unique sections</th><th>ULS util.</th><th>SLS dy / limit (mm)</th></tr></thead><tbody>{ranked_rows}</tbody></table>
<h2>Chord fabrication groups</h2>
<p>Each top chord and bottom chord uses one section designation throughout each transverse span.</p>
<table><thead><tr><th>Span</th><th>Chord</th><th>Common section</th><th>Members</th><th>Governing member</th><th>Util.</th></tr></thead><tbody>{chord_group_rows}</tbody></table>
<h2>Web fabrication groups</h2>
<p>Ordinary verticals and diagonals are grouped in at least three consecutive panels. A smaller section is introduced only when the retained section utilisation falls below 75%.</p>
<table><thead><tr><th>Span</th><th>Role</th><th>Group</th><th>Section</th><th>Members</th><th>Governing member</th><th>Util.</th></tr></thead><tbody>{web_group_rows}</tbody></table>
<h2>Bearing nodes and support verticals</h2>
<p>The vertical aligned with each bearing uses the selected supporting column or longitudinal-girder section and is excluded from truss-angle mass optimisation.</p>
<table><thead><tr><th>Bearing node</th><th>Vertical</th><th>Section source</th><th>Section</th><th>Area (mm²)</th></tr></thead><tbody>{bearing_rows}</tbody></table>
<h2>Implemented member design calculation</h2>
<div class="formula">
Minimum base angle: 50x50x5. For each member: &lambda; = KL / r<sub>min</sub>; &lambda;&#772; = &lambda;&radic;(f<sub>y</sub> / (&pi;&sup2;E));
&phi;T<sub>r</sub> = &phi;Af<sub>y</sub>; &phi;C<sub>r</sub> = &phi;T<sub>r</sub>[1 + &lambda;&#772;<sup>2n</sup>]<sup>-1/n</sup>.
The reported utilisation is max(T*/&phi;T<sub>r</sub>, C*/&phi;C<sub>r</sub>, &lambda;/&lambda;<sub>limit</sub>), with &phi;={_number(basis.get('resistance_model', {}).get('phi', 0.9), 2)} and n={_number(basis.get('resistance_model', {}).get('buckling_exponent', 1.34), 2)}.
The calculation uses f<sub>y</sub>={_number(basis.get('fy_mpa', 0), 0)} MPa, E={_number(basis.get('resistance_model', {}).get('elastic_modulus_mpa', 0), 0)} MPa, compression slenderness limit {_number(basis.get('compression_slenderness_limit', 0), 0)} and tension-only slenderness limit {_number(basis.get('tension_slenderness_limit', 0), 0)}.
</div>
<details><summary><strong>Exact truss section search order</strong></summary><p>{escape(' -> '.join(str(item) for item in ordered_candidates))}</p></details>
<h2>Rank 1 truss member calculations</h2>
<table class="calc"><thead><tr><th>Member</th><th>Role</th><th>Nodes</th><th>Fabrication group</th><th>Section</th><th>L</th><th>KL</th><th>rmin</th><th>&lambda; / limit</th><th>T* / &phi;Tr (kN)</th><th>C* / &phi;Cr (kN)</th><th>U<sub>T</sub> / U<sub>C</sub> / U<sub>&lambda;</sub></th><th>Governing</th><th>Status</th></tr></thead><tbody>{member_rows}</tbody></table>
<h2>Eave-column design</h2>
<table><tbody>
<tr><th>Selected section</th><td>{escape(str(eave_column.get('section', '')))}</td></tr>
<tr><th>Column count</th><td>{eave_column.get('column_count', '')}</td></tr>
<tr><th>Governing ULS</th><td>{escape(str(column_strength.get('combination', '')))} / {escape(str(column_strength.get('side', '')))}; utilisation {_number(column_strength.get('utilisation', 0), 3)}</td></tr>
<tr><th>Horizontal SLS</th><td>{_number(column_serviceability.get('maximum_horizontal_deflection_mm', 0), 1)} / {_number(column_serviceability.get('limit_mm', 0), 1)} mm; utilisation {_number(column_serviceability.get('utilisation', 0), 3)}</td></tr>
</tbody></table>
<h2>Longitudinal girder</h2>
<table><tbody>{girder_rows}</tbody></table>
{f'<h2>Girder member calculations</h2><table class="calc"><thead><tr><th>Member</th><th>Role</th><th>Nodes</th><th>Fabrication group</th><th>Section</th><th>L</th><th>KL</th><th>rmin</th><th>&lambda; / limit</th><th>T* / &phi;Tr (kN)</th><th>C* / &phi;Cr (kN)</th><th>U<sub>T</sub> / U<sub>C</sub> / U<sub>&lambda;</sub></th><th>Governing</th><th>Status</th></tr></thead><tbody>{girder_member_rows}</tbody></table>' if girder_member_rows else ''}
<small>Positive truss-member action is tension. Member resistance and serviceability are calculated above. Connections, restraint-member capacity and internal-column member design are separate design items.</small>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path
