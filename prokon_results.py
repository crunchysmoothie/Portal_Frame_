"""Parse Prokon Frame Analysis text output and compare it with PortalFrame.

The comparison deliberately uses only results common to both reports:
SLS maximum nodal translations and ULS support reactions.  Prokon rounds its
text report to 0.01, so the generated differences inherit that precision.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any, Mapping


_RESULT_ROW = re.compile(
    r"^\s*(?:(\d+)\s+)?([A-Za-z0-9_]+)\s+"
    r"([-+0-9.Ee]+)\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)\s+"
    r"([-+0-9.Ee]+)\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)\s*$"
)


def parse_fout(path: str | Path) -> dict[str, Any]:
    """Return the SLS displacements and ULS/SLS reactions from ``f.out``."""
    lines = Path(path).read_text(encoding="latin-1", errors="replace").splitlines()
    title = next((line.split(":", 1)[1].strip() for line in lines if line.startswith(" TITLE :")), "")
    data: dict[str, Any] = {
        "title": title,
        "sls_displacements": [],
        "uls_reactions": [],
        "sls_reactions": [],
    }
    section: str | None = None
    node: int | None = None
    for line in lines:
        if "NODAL POINT DISPLACEMENTS at SLS" in line:
            section, node = "sls_displacements", None
            continue
        if "REACTIONS AT ULS" in line:
            section, node = "uls_reactions", None
            continue
        if "REACTIONS AT SLS (Combinations only)" in line:
            section, node = "sls_reactions", None
            continue
        if line.lstrip().startswith("EQUILIBRIUM CHECK") or "BEAM ELEMENT END FORCES" in line:
            section, node = None, None
            continue
        if section is None:
            continue
        match = _RESULT_ROW.match(line)
        if not match:
            continue
        if match.group(1):
            node = int(match.group(1))
        if node is None:
            continue
        combination_id = match.group(2)
        if not combination_id.startswith("PF"):
            continue
        values = [float(match.group(i)) for i in range(3, 9)]
        if section == "sls_displacements":
            keys = ("dx_mm", "dy_mm", "dz_mm", "rx_rad", "ry_rad", "rz_rad")
        else:
            keys = ("fx_kn", "fy_kn", "fz_kn", "mx_knm", "my_knm", "mz_knm")
        data[section].append({
            "node": node,
            "combination_id": combination_id,
            **dict(zip(keys, values)),
        })
    return data


def _difference(prokon: float, portal: float) -> tuple[float, float | None]:
    absolute = prokon - portal
    percent = None if abs(portal) < 1e-9 else absolute / abs(portal) * 100.0
    return absolute, percent


def compare_results(
    parsed: Mapping[str, Any],
    model: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Match Prokon combination IDs/nodes to PortalFrame names and compare."""
    combo_by_id = {row["id"]: row for row in model["load_combinations"]}
    source_node = {int(row["id"]): row["source_name"] for row in model["nodes"]}
    portal_deflections = {
        row["load_combination"]: row for row in snapshot["results"]["deflections"]
    }
    portal_reactions = {
        (row["node"], row["load_combination"]): row
        for row in snapshot["results"]["reactions"]
    }

    grouped_displacements: dict[str, list[Mapping[str, Any]]] = {}
    for row in parsed["sls_displacements"]:
        grouped_displacements.setdefault(row["combination_id"], []).append(row)
    deflection_rows: list[dict[str, Any]] = []
    for combo_id, prokon_rows in grouped_displacements.items():
        combo = combo_by_id.get(combo_id)
        if not combo or combo["sls_name"] not in portal_deflections:
            continue
        portal = portal_deflections[combo["sls_name"]]
        for axis, value_key, node_key in (
            ("x", "max_dx", "dx_node"),
            ("y", "total_max_dy", "total_dy_node"),
        ):
            prokon = max(prokon_rows, key=lambda row: abs(row[f"d{axis}_mm"]))
            prokon_value = abs(prokon[f"d{axis}_mm"])
            portal_value = abs(float(portal.get(
                value_key,
                portal.get("max_dy", 0.0) if axis == "y" else 0.0,
            )))
            delta, percent = _difference(prokon_value, portal_value)
            deflection_rows.append({
                "combination_id": combo_id,
                "load_combination": combo["sls_name"],
                "axis": axis.upper(),
                "portal_node": portal.get(
                    node_key,
                    portal.get("dy_node", "") if axis == "y" else "",
                ),
                "prokon_node": source_node.get(prokon["node"], str(prokon["node"])),
                "portal_mm": portal_value,
                "prokon_mm": prokon_value,
                "difference_mm": delta,
                "difference_percent": percent,
            })

    reaction_rows: list[dict[str, Any]] = []
    for row in parsed["uls_reactions"]:
        combo = combo_by_id.get(row["combination_id"])
        node_name = source_node.get(row["node"])
        if not combo or not node_name:
            continue
        portal = portal_reactions.get((node_name, combo["uls_name"]))
        if not portal:
            continue
        for component, prokon_key, portal_key, unit in (
            ("FX", "fx_kn", "fx", "kN"),
            ("FY", "fy_kn", "fy", "kN"),
            ("MZ", "mz_knm", "mz", "kNm"),
        ):
            prokon_value = float(row[prokon_key])
            portal_value = float(portal[portal_key])
            delta, percent = _difference(prokon_value, portal_value)
            reaction_rows.append({
                "combination_id": row["combination_id"],
                "load_combination": combo["uls_name"],
                "node": node_name,
                "component": component,
                "unit": unit,
                "portal": portal_value,
                "prokon": prokon_value,
                "difference": delta,
                "difference_percent": percent,
            })

    deflection_percentages = [abs(row["difference_percent"]) for row in deflection_rows if row["difference_percent"] is not None]
    reaction_percentages = [
        abs(row["difference_percent"])
        for row in reaction_rows
        if row["difference_percent"] is not None and abs(row["portal"]) >= 1.0
    ]
    return {
        "schema_version": 1,
        "analysis_id": snapshot.get("analysis", {}).get(
            "analysis_id", model.get("analysis_id")
        ),
        "prokon_export_analysis_id": model.get("analysis_id"),
        "prokon_title": parsed.get("title", ""),
        "notes": [
            "Positive deflection values are absolute maxima over exported nodes.",
            "Reaction signs use each program's reported global axes.",
            "Percentage reaction summary excludes PortalFrame components below 1.0 in their reported unit.",
            "Prokon f.out values are rounded to two decimals.",
        ],
        "summary": {
            "deflection_rows": len(deflection_rows),
            "reaction_rows": len(reaction_rows),
            "max_abs_deflection_difference_percent": max(deflection_percentages, default=None),
            "mean_abs_deflection_difference_percent": (
                sum(deflection_percentages) / len(deflection_percentages) if deflection_percentages else None
            ),
            "max_abs_reaction_difference_percent_for_magnitude_ge_1": max(reaction_percentages, default=None),
            "mean_abs_reaction_difference_percent_for_magnitude_ge_1": (
                sum(reaction_percentages) / len(reaction_percentages) if reaction_percentages else None
            ),
        },
        "deflections": deflection_rows,
        "uls_reactions": reaction_rows,
    }


def write_comparison(
    fout_path: str | Path,
    model_path: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write an audit JSON and two flat CSV comparison tables."""
    model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    comparison = compare_results(parse_fout(fout_path), model, snapshot)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": destination / "portalframe_prokon_results_comparison.json",
        "deflections_csv": destination / "portalframe_prokon_deflections.csv",
        "reactions_csv": destination / "portalframe_prokon_uls_reactions.csv",
    }
    paths["json"].write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    for key, rows_key in (("deflections_csv", "deflections"), ("reactions_csv", "uls_reactions")):
        rows = comparison[rows_key]
        with paths[key].open("w", newline="", encoding="utf-8-sig") as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    return paths


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    written = write_comparison(
        root / "output/prokon/current/f.out",
        root / "output/prokon/current/portalframe_prokon_input.json",
        root / "output/analysis/analysis_results.json",
        root / "output/prokon/current",
    )
    for kind, path in written.items():
        print(f"{kind}: {path}")
