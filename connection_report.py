"""Auditable HTML calculation report for post-analysis connections."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Mapping


def _number(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _check_rows(checks: list[Mapping[str, Any]]) -> str:
    rows = []
    for check in checks:
        status = str(check.get("status", ""))
        rows.append(
            "<tr>"
            f"<td>{escape(str(check.get('reference', '')))}</td>"
            f"<td><strong>{escape(str(check.get('name', '')))}</strong><br>"
            f"<small>{escape(str(check.get('source', '')))}</small></td>"
            f"<td>{escape(str(check.get('equation', '')))}<br>"
            f"<small>{escape(str(check.get('substitution', '')))}</small></td>"
            f"<td>{_number(check.get('demand'))} / "
            f"{_number(check.get('resistance'))} "
            f"{escape(str(check.get('units', '')))}</td>"
            f"<td>{_number(check.get('utilisation'))}</td>"
            f'<td class="{escape(status.lower())}">{escape(status)}</td>'
            "</tr>"
        )
    return "".join(rows)


def _weld_rows(weld: Mapping[str, Any], reference: str) -> str:
    if not weld:
        return ""
    selected = weld.get("selected_weld", weld)
    actions = weld.get("actions", {})
    utilisation = selected.get("utilisation")
    status = str(selected.get("status", weld.get("status", "")))
    weld_type = str(
        selected.get("type", selected.get("weld_type", "Fillet"))
    )
    size = selected.get(
        "provided_size_mm",
        selected.get("weld_size_mm", selected.get("equivalent_fillet_size_mm")),
    )
    return (
        "<tr>"
        f"<td>{escape(reference)}</td>"
        f"<td><strong>{escape(weld_type)} weld group</strong><br>"
        f"<small>{escape(str(weld.get('source', 'Mahachi Chapter 7.8.')))}</small></td>"
        "<td>Elastic line-weld group: direct force plus moment</td>"
        f"<td>{_number(actions.get('resultant_kn_per_mm', selected.get('required_force_per_mm')))} / "
        f"{_number(selected.get('fillet_resistance_kn_per_mm', selected.get('resistance_kn_per_mm')))} kN/mm; "
        f"provided size {_number(size, 0)} mm</td>"
        f"<td>{_number(utilisation)}</td>"
        f'<td class="{escape(status.lower())}">{escape(status)}</td>'
        "</tr>"
    )


def _stiffener_rows(stiffener: Mapping[str, Any], prefix: str) -> str:
    if not stiffener or stiffener.get("status") == "NOT_REQUIRED":
        return ""
    rows = _check_rows(list(stiffener.get("checks", [])))
    return rows.replace("<td>", f"<td>{escape(prefix)}-", 1) if rows else ""


def _connection_section(
    title: str,
    item: Mapping[str, Any],
    *,
    weld_key: str,
) -> str:
    checks = list(item.get("checks", []))
    checks.extend(item.get("local_member_checks", []))
    rows = _check_rows(checks)
    rows += _weld_rows(item.get(weld_key, {}), f"{title[:2].upper()}-W")
    stiffener = item.get("stiffener_checks", {})
    rows += _check_rows(list(stiffener.get("checks", [])))
    rows += _weld_rows(stiffener.get("weld", {}), "ST-W")
    anchor = item.get("anchor_concrete")
    if anchor:
        rows += _check_rows(list(anchor.get("checks", [])))
    return (
        f"<section><h2>{escape(title)}</h2>"
        f'<p class="status-line">Status: '
        f'<strong class="{escape(str(item.get("status", "")).lower())}">'
        f'{escape(str(item.get("status", "")))}</strong></p>'
        "<table><thead><tr><th>Ref.</th><th>Check and basis</th>"
        "<th>Equation and substitution</th><th>Demand / resistance</th>"
        "<th>Util.</th><th>Status</th></tr></thead>"
        f"<tbody>{rows or '<tr><td colspan=\"6\">No checks.</td></tr>'}</tbody>"
        "</table></section>"
    )


def write_connection_report_html(
    result: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Write all completed, failed and input-required checks to HTML."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    detailed = result.get("detailed_checks", {})
    sections = []
    for support in detailed.get("base_plates", {}).get("supports", []):
        sections.append(
            _connection_section(
                f"Base plate {support.get('support', '')}",
                support,
                weld_key="column_to_base_plate_weld",
            )
        )
    for location in detailed.get("haunch_connections", {}).get("locations", []):
        sections.append(
            _connection_section(
                str(location.get("location", "Haunch connection")),
                location,
                weld_key="end_plate_weld",
            )
        )
    completed = "".join(
        f"<li>{escape(str(item))}</li>"
        for item in detailed.get("completed_check_scope", [])
    )
    required = "".join(
        f"<li>{escape(str(item))}</li>"
        for item in detailed.get("input_required_scope", [])
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Portal-frame connection calculations</title>
<style>
body{{font-family:Arial,sans-serif;margin:28px;color:#173C3A;background:#F6F8F7}}
main{{max-width:1450px;margin:auto}}section{{margin:28px 0}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:13px}}
th,td{{border:1px solid #CCD9D7;padding:8px;vertical-align:top;text-align:left}}
th{{background:#E7F0EF}}small{{color:#607472}}
.pass{{color:#16764f;font-weight:700}}.fail{{color:#b3261e;font-weight:700}}
.input_required,.pass_with_input_required,.pass_with_stiffeners,
.stiffener_required{{color:#9a6500;font-weight:700}}
.warning{{background:#FFF3D6;border-left:5px solid #C17B00;padding:14px}}
</style></head><body><main>
<h1>Post-analysis connection calculations</h1>
<p>Overall status: <strong class="{escape(str(result.get('status', '')).lower())}">
{escape(str(result.get('status', '')))}</strong></p>
<div class="warning"><strong>Engineering review required.</strong>
Checks marked INPUT_REQUIRED are deliberately not accepted. This report is not
a fabrication drawing.</div>
<h2>Calculated scope</h2><ul>{completed}</ul>
<h2>Inputs still required</h2><ul>{required}</ul>
{''.join(sections) or '<p>No portal-frame connection checks were generated.</p>'}
</main></body></html>"""
    output.write_text(document, encoding="utf-8")
    return output
