"""Printable report artifacts for generic preliminary truss designs."""

from __future__ import annotations

from html import escape
import json
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
        "</tr>"
        for item in schedule
    )


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
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Truss Design Calculation - Draft</title>
<style>
body{{font:14px Arial,sans-serif;color:#17333a;margin:28px;line-height:1.4}}
h1,h2{{color:#183b56}} h1{{margin-bottom:4px}} .warning{{background:#fce4d6;border-left:5px solid #c65911;padding:14px;margin:18px 0}}
.meta{{display:grid;grid-template-columns:180px 1fr;gap:5px 12px;background:#f4f7f9;padding:14px}}
table{{width:100%;border-collapse:collapse;margin:12px 0 24px}} th{{background:#183b56;color:white;text-align:left;padding:7px}}
td{{border-bottom:1px solid #c9d3d9;padding:6px;vertical-align:top}} tr:nth-child(even){{background:#f7fafb}}
.calc{{font-size:10px}} .formula{{background:#eef5f4;border-left:4px solid #258475;padding:12px;margin:12px 0 20px}}
small{{color:#667681}} @media print{{body{{margin:10mm}} .no-print{{display:none}}}}
</style></head><body>
<h1>Truss Design Calculation - Draft</h1><div><strong>{escape(str(result.get('validation_status', '')))}</strong></div>
<div class="meta">
<div>Project</div><div>{escape(str(project.get('name', 'Untitled project')))}</div>
<div>Project number</div><div>{escape(str(project.get('number', '')))}</div>
<div>Designer</div><div>{escape(str(project.get('designer', '')))}</div>
<div>Engine</div><div>{escape(str(result.get('engine', '')))}</div>
<div>Topology / joints</div><div>{escape(str(basis.get('topology', '')))} / {escape(str(basis.get('joint_model', '')))}</div>
<div>Standards</div><div>{escape(str(basis.get('load_standard', '')))}; {escape(str(basis.get('steel_standard', '')))}</div>
<div>Top-chord restraint</div><div>Every {top_restraint.get('brace_every_n_purlins', '')} purlin(s), full building length; maximum spacing {_number(top_restraint.get('maximum_spacing_mm', 0) / 1000, 2)} m</div>
<div>Bottom-chord restraint</div><div>Every {bottom_restraint.get('brace_every_n_purlins', '')} purlin(s), full building length; maximum spacing {_number(bottom_restraint.get('maximum_spacing_mm', 0) / 1000, 2)} m</div>
<div>Building layout</div><div>{_number(longitudinal.get('building_length_mm', 0) / 1000, 1)} m long; transverse bays {escape(' / '.join(_number(value / 1000, 1) for value in transverse.get('bay_spans_mm', [])))} m</div>
<div>Support sequence</div><div>{escape(' / '.join(str(value) for value in support_arrangement.get('sequence', [])))}</div>
  <div>Columns</div><div>{layout_columns.get('eave_count', '')} main eave columns; {layout_columns.get('internal_count', '')} internal support columns</div>
  <div>Rank 1 mass</div><div>{_number(best.get('total_truss_mass_kg', 0), 1)} kg trusses + {_number(eave_column.get('total_mass_kg', 0), 1)} kg eave columns + {_number(girder.get('total_mass_kg', 0), 1)} kg girders + {_number(centre_column.get('total_mass_kg', 0), 1)} kg centre columns = {_number(best.get('arrangement_mass_kg', 0), 1)} kg modelled arrangement</div>
  <div>Centre-column design</div><div>{escape(str(centre_column.get('status', 'NOT_DESIGNED')))}; {escape(str(centre_column.get('material', 'Steel')))}; {escape(str(centre_column.get('section', 'main-column proxy')))}; axial-only check</div>
  <div>Practical cost comparison</div><div>{_number(best.get('practical_cost_equivalent_kg', 0), 1)} kg-equivalent including an {_number(float(basis.get('platework_cost_allowance_fraction', 0)) * 100, 0)}% platework allowance; individually optimised-web comparison {_number(best.get('lightest_member_arrangement_mass_kg', 0), 1)} kg</div>
</div>
<div class="warning"><strong>Engineering hold point</strong><ul>{warnings}</ul></div>
<h2>Ranked passing solutions</h2>
<table><thead><tr><th>Practical rank</th><th>Depth (m)</th><th>Panels</th><th>Panel (mm)</th><th>Arrangement mass (kg)</th><th>Practical kg-eq.</th><th>Individual-web comparison (kg)</th><th>Unique sections</th><th>ULS util.</th><th>SLS dy / limit (mm)</th></tr></thead><tbody>{ranked_rows}</tbody></table>
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
<h2>Rank 1 truss member calculations</h2>
<table class="calc"><thead><tr><th>Member</th><th>Fabrication group</th><th>Section</th><th>L</th><th>KL</th><th>rmin</th><th>&lambda; / limit</th><th>T* / &phi;Tr (kN)</th><th>C* / &phi;Cr (kN)</th><th>U<sub>T</sub> / U<sub>C</sub> / U<sub>&lambda;</sub></th><th>Governing</th></tr></thead><tbody>{member_rows}</tbody></table>
<h2>Eave-column design</h2>
<table><tbody>
<tr><th>Selected section</th><td>{escape(str(eave_column.get('section', '')))}</td></tr>
<tr><th>Column count</th><td>{eave_column.get('column_count', '')}</td></tr>
<tr><th>Governing ULS</th><td>{escape(str(column_strength.get('combination', '')))} / {escape(str(column_strength.get('side', '')))}; utilisation {_number(column_strength.get('utilisation', 0), 3)}</td></tr>
<tr><th>Horizontal SLS</th><td>{_number(column_serviceability.get('maximum_horizontal_deflection_mm', 0), 1)} / {_number(column_serviceability.get('limit_mm', 0), 1)} mm; utilisation {_number(column_serviceability.get('utilisation', 0), 3)}</td></tr>
</tbody></table>
<h2>Longitudinal girder</h2>
<table><tbody>{girder_rows}</tbody></table>
{f'<h2>Girder member calculations</h2><table class="calc"><thead><tr><th>Member</th><th>Fabrication group</th><th>Section</th><th>L</th><th>KL</th><th>rmin</th><th>&lambda; / limit</th><th>T* / &phi;Tr (kN)</th><th>C* / &phi;Cr (kN)</th><th>U<sub>T</sub> / U<sub>C</sub> / U<sub>&lambda;</sub></th><th>Governing</th></tr></thead><tbody>{girder_member_rows}</tbody></table>' if girder_member_rows else ''}
<small>Positive truss-member action is tension. Member resistance and serviceability are calculated above. Connections, restraint-member capacity and internal-column member design are separate design items.</small>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path
