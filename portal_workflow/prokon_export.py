"""Auditable PortalFrame to Prokon Frame Analysis comparison exports.

The canonical JSON is the source of truth.  The A03 writer uses a known-good
Prokon Frame Analysis file-version 12 seed and replaces only model input tables.
All coordinates are exported in m, forces in kN and moments in kNm.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import gzip
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping
import zipfile

from databases import member_database as mdb
from .inputs import display_load_case_name
from .model import load_portal_frame
from .analysis import build_model, resolve_candidate_haunch_data


SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = PROJECT_ROOT / "references" / "prokon_frame_analysis_v12.a03.gz.b64"


@dataclass(frozen=True)
class ProkonNode:
    id: int
    source_name: str
    x_m: float
    y_m: float
    z_m: float = 0.0


@dataclass(frozen=True)
class ProkonSection:
    name: str
    designation: str
    area_m2: float
    ixx_m4: float
    iyy_m4: float
    j_m4: float
    material: str = "Steel:S355JR"


@dataclass(frozen=True)
class ProkonMember:
    id: int
    source_name: str
    i_node: int
    j_node: int
    section: str
    release_i: str = ""
    release_j: str = ""


def _section_family(designation: str) -> str:
    return "H-Sections" if designation.startswith("H") else "I-Sections"


def _portal_selected_sections(snapshot: Mapping[str, Any]) -> tuple[str, str]:
    rows = list(snapshot["results"].get("members", []))
    column = next((str(row["section"]) for row in rows if row.get("member_type") == "column"), None)
    rafter_sections = [
        str(row["section"])
        for row in rows
        if row.get("member_type") == "rafter"
    ]
    rafter = next(
        (section for section in rafter_sections if " + haunch " not in section),
        rafter_sections[0] if rafter_sections else None,
    )
    if not column or not rafter:
        raise ValueError("The completed snapshot does not contain selected portal sections.")
    return column, rafter


def _section_from_portal(name: str, designation: str, props: Mapping[str, Any]) -> ProkonSection:
    return ProkonSection(
        name=name,
        designation=f"{designation} I1",
        area_m2=float(props["A"]) * 1e-3,
        ixx_m4=float(props["Ix"]) * 1e-6,
        iyy_m4=float(props["Iy"]) * 1e-6,
        j_m4=float(props["J"]) * 1e-9,
    )


def _direction(value: str) -> str:
    key = str(value)
    return {
        "FX": "X", "FY": "Y", "FZ": "Z",
        "Fx": "X", "Fy": "L", "Fz": "L",
    }.get(key, key[-1:].upper())


def _orient_local_load_for_prokon(load: dict[str, Any], element_length: float) -> dict[str, Any]:
    """Account for Prokon defining the local member axis by node-number order.

    PyNite retains the source i-to-j direction, whereas Prokon uses the smaller
    node number toward the larger node number even if the beam row is reversed.
    Reversing a local load therefore reverses its sign, swaps its end values,
    and mirrors any partial-load position.
    """
    if load.get("direction") != "L" or load["node_path"][0] < load["node_path"][1]:
        return load
    if "point_kn" in load:
        load["point_kn"] = -float(load["point_kn"])
        load["point_at_m"] = element_length - float(load["point_at_m"])
        return load
    original_w1 = float(load["w1_kn_m"])
    original_w2 = float(load["w2_kn_m"])
    load["w1_kn_m"] = -original_w2
    load["w2_kn_m"] = -original_w1
    start = 0.0 if load.get("start_m") is None else float(load["start_m"])
    length = element_length if load.get("length_m") is None else float(load["length_m"])
    mirrored_start = element_length - (start + length)
    load["start_m"] = None if mirrored_start <= 1e-9 else mirrored_start
    return load


def _factor_pairs(uls: Iterable[Mapping[str, Any]], sls: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sls_by_cases: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for combo in sls:
        sls_by_cases[tuple(sorted(combo.get("factors", {})))].append(combo)
    pairs = []
    for index, uls_combo in enumerate(uls, 1):
        key = tuple(sorted(uls_combo.get("factors", {})))
        candidates = sls_by_cases.get(key, [])
        sls_combo = candidates.pop(0) if candidates else {"name": "", "factors": {}}
        requested_id = str(uls_combo.get("name") or "")
        combination_id = (
            requested_id
            if len(requested_id) <= 11 and re.fullmatch(r"C\d+(?:\.\d+)?", requested_id)
            else f"C{index}"
        )
        pairs.append({
            "id": combination_id,
            "uls_name": str(uls_combo.get("name", "")),
            "sls_name": str(sls_combo.get("name", "")),
            "uls_factors": dict(uls_combo.get("factors", {})),
            "sls_factors": dict(sls_combo.get("factors", {})),
        })
    return pairs


def _load_case_aliases(cases: Iterable[str]) -> dict[str, str]:
    """Return unique Prokon-safe load-case names (six characters maximum)."""

    result: dict[str, str] = {}
    used: set[str] = set()
    sequence = 1
    for source in sorted({str(case) for case in cases}):
        preferred = display_load_case_name(source)
        if len(preferred) <= 6 and preferred not in used:
            alias = preferred
        else:
            while True:
                alias = f"LC{sequence:04d}"
                sequence += 1
                if alias not in used:
                    break
        result[source] = alias
        used.add(alias)
    return result


def build_portal_comparison(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build a canonical comparison model from one completed portal snapshot."""

    embedded = deepcopy(snapshot["input_data"])
    column_name, rafter_name = _portal_selected_sections(snapshot)
    database = mdb.load_member_database(
        PROJECT_ROOT / "databases" / "member_database.csv"
    )
    column = mdb.member_properties(_section_family(column_name), column_name, database)
    rafter = mdb.member_properties(_section_family(rafter_name), rafter_name, database)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        ) as temporary:
            json.dump(embedded, temporary)
            temporary_path = Path(temporary.name)
        data = resolve_candidate_haunch_data(
            load_portal_frame(str(temporary_path)), rafter
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    frame = build_model(rafter, column, data)
    for physical in frame.members.values():
        physical.descritize()

    ordered_nodes = sorted(
        frame.nodes.values(), key=lambda node: (float(node.X), float(node.Y), str(node.name))
    )
    node_ids = {str(node.name): index for index, node in enumerate(ordered_nodes, 1)}
    nodes = [
        ProkonNode(index, str(node.name), float(node.X) / 1000.0, float(node.Y) / 1000.0, float(node.Z) / 1000.0)
        for index, node in enumerate(ordered_nodes, 1)
    ]

    sections: dict[str, ProkonSection] = {
        "COL": _section_from_portal("COL", column_name, column),
        "RFT": _section_from_portal("RFT", rafter_name, rafter),
    }
    members: list[ProkonMember] = []
    source_chains: dict[str, list[int]] = {}
    next_haunch = 1
    haunch_section_by_designation: dict[str, str] = {}
    for source_name, physical in frame.members.items():
        chain = []
        for submember in physical.sub_members.values():
            props = getattr(submember, "portal_properties", None)
            if props:
                designation = str(props["Designation"])
                section_name = haunch_section_by_designation.get(designation, "")
                if not section_name:
                    section_name = f"H{next_haunch:02d}"
                    next_haunch += 1
                    haunch_section_by_designation[designation] = section_name
                    sections[section_name] = _section_from_portal(section_name, designation, props)
            else:
                source = next(item for item in data.members if item.name == source_name)
                section_name = "COL" if source.type.lower() == "column" else "RFT"
            member_id = len(members) + 1
            members.append(ProkonMember(
                member_id, source_name, node_ids[str(submember.i_node.name)],
                node_ids[str(submember.j_node.name)], section_name,
            ))
            chain.append(member_id)
        source_chains[source_name] = chain

    supports = []
    springs_by_node = {str(item["node"]): item for item in data.rotational_springs}
    for source_node, fixity in data.supports.items():
        spring = springs_by_node.get(str(source_node))
        supports.append({
            "node": node_ids[str(source_node)],
            "fixity": "".join(axis for axis, key in (("X", "DX"), ("Y", "DY"), ("Z", "DZ"), ("x", "RX"), ("y", "RY"), ("z", "RZ")) if fixity.get(key)),
            "rz_spring_knm_per_rad": (
                float(spring["stiffness"]) / 1000.0 if spring and spring.get("direction") == "RZ" else None
            ),
        })

    combinations = _factor_pairs(
        data.load_combinations, data.serviceability_load_combinations
    )
    combination_cases = {
        case for combo in combinations
        for case in [*combo["uls_factors"], *combo["sls_factors"]]
    }
    nodal_loads = []
    for node in data.nodes.values():
        for load in node.loads:
            if (load.case or "D") not in combination_cases:
                continue
            nodal_loads.append({
                "case": load.case or "D", "node": node_ids[node.name],
                "direction": str(load.direction),
                "magnitude": float(load.magnitude) / 1000.0 if str(load.direction).startswith("M") else float(load.magnitude),
            })
    node_by_id = {item.id: item for item in nodes}
    member_loads = []
    for member in data.members:
        element_path = [members[index - 1] for index in source_chains[member.name]]
        element_lengths = [
            math.dist(
                (node_by_id[item.i_node].x_m, node_by_id[item.i_node].y_m),
                (node_by_id[item.j_node].x_m, node_by_id[item.j_node].y_m),
            )
            for item in element_path
        ]
        total_length = sum(element_lengths)
        for load in member.loads:
            if (load.case or "D") not in combination_cases:
                continue
            load_start = 0.0 if load.x1 is None else float(load.x1) / 1000.0
            load_end = total_length if load.x2 is None else float(load.x2) / 1000.0
            loaded_length = max(load_end - load_start, 0.0)
            cumulative = 0.0
            for exported, element_length in zip(element_path, element_lengths):
                overlap_start = max(load_start, cumulative)
                overlap_end = min(load_end, cumulative + element_length)
                if overlap_end - overlap_start > 1e-9:
                    fraction_1 = (overlap_start - load_start) / loaded_length if loaded_length else 0.0
                    fraction_2 = (overlap_end - load_start) / loaded_length if loaded_length else 1.0
                    exported_load = {
                        "case": load.case or "D", "source_member": member.name,
                        "node_path": [exported.i_node, exported.j_node],
                        "direction": _direction(load.direction),
                        "w1_kn_m": (float(load.w1) + (float(load.w2) - float(load.w1)) * fraction_1) * 1000.0,
                        "w2_kn_m": (float(load.w1) + (float(load.w2) - float(load.w1)) * fraction_2) * 1000.0,
                        "start_m": None if overlap_start <= cumulative + 1e-9 else overlap_start - cumulative,
                        "length_m": None if overlap_start <= cumulative + 1e-9 and overlap_end >= cumulative + element_length - 1e-9 else overlap_end - overlap_start,
                    }
                    member_loads.append(_orient_local_load_for_prokon(exported_load, element_length))
                cumulative += element_length
        for load in member.point_loads:
            if (load.case or "D") not in combination_cases:
                continue
            point = float(load.x) / 1000.0
            cumulative = 0.0
            for index, (exported, element_length) in enumerate(zip(element_path, element_lengths)):
                if point <= cumulative + element_length + 1e-9 or index == len(element_path) - 1:
                    exported_load = {
                        "case": load.case or "D", "source_member": member.name,
                        "node_path": [exported.i_node, exported.j_node],
                        "direction": _direction(load.direction),
                        "point_kn": float(load.magnitude),
                        "point_at_m": max(0.0, min(point - cumulative, element_length)),
                    }
                    member_loads.append(_orient_local_load_for_prokon(exported_load, element_length))
                    break
                cumulative += element_length

    frame_data = data.frame_data[0]
    load_cases = {
        load["case"] for load in [*nodal_loads, *member_loads]
    } | {
        case for combo in combinations
        for case in [*combo["uls_factors"], *combo["sls_factors"]]
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "PortalFrame prokon_export",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_id": snapshot.get("analysis", {}).get("analysis_id", ""),
        "structural_system": "Portal frame",
        "units": {"distance": "m", "force": "kN", "moment": "kNm"},
        "analysis": {"domain": "XY plane", "type": "Linear", "self_weight_case": "D"},
        "nodes": [asdict(item) for item in nodes],
        "members": [asdict(item) for item in members],
        "sections": [asdict(item) for item in sections.values()],
        "supports": supports,
        "nodal_loads": nodal_loads,
        "member_loads": member_loads,
        "load_combinations": combinations,
        "load_case_map": _load_case_aliases(load_cases),
        "source_member_node_paths": {name: [members[index - 1].i_node for index in chain] + [members[chain[-1] - 1].j_node] for name, chain in source_chains.items()},
        "prokon_node_rules": {
            "bracing": "PortalFrame rafter/column subdivisions are retained as Prokon nodes.",
            "haunch": "Each PortalFrame eight-segment haunch station is an explicit Prokon node and section segment.",
        },
        "warnings": [
            "The Prokon model is an analysis comparison input, not an independent design verification.",
            "PortalFrame local Fy/Fz member loads are exported as Prokon local L loads with sign and position corrected for Prokon's smaller-to-larger node convention.",
            "Spring stiffness is exported from the value actually applied to the PortalFrame FE model after unit conversion.",
            f"Resolved haunch source section: {frame_data.get('resolved_haunch_source_section', rafter_name)}.",
        ],
    }


def build_truss_comparison(
    result: Mapping[str, Any], *, ranked_solution: int = 0,
    include_columns: bool = False,
) -> dict[str, Any]:
    """Build the truss-only or truss-with-columns Prokon comparison model."""

    best = list(result["ranked_solutions"])[ranked_solution]
    geometry = best["geometry"]
    nodes_in = list(geometry["nodes"])
    node_ids = {str(node["name"]): index for index, node in enumerate(nodes_in, 1)}
    column_height_mm = (
        float(best.get("eave_column_design", {}).get("height_mm", 0.0))
        if include_columns else 0.0
    )
    nodes = [{
        "id": node_ids[str(node["name"])],
        "source_name": node["name"],
        "x_m": float(node["x_mm"]) / 1000.0,
        "y_m": (float(node["y_mm"]) + column_height_mm) / 1000.0,
        "z_m": 0.0,
    } for node in nodes_in]
    schedule = {str(row["member"]): row for row in best["member_schedule"]}
    sections: dict[str, dict[str, Any]] = {}
    section_names: dict[str, str] = {}
    members = []
    for member in geometry["members"]:
        section = schedule[str(member["name"])]["section"]
        designation = str(section["designation"])
        if designation not in section_names:
            short = f"S{len(section_names) + 1:02d}"
            section_names[designation] = short
            area = float(section["area_mm2"])
            radius = min(float(section.get("rx_mm", 1.0)), float(section.get("ry_mm", 1.0)))
            inertia = area * radius**2 * 1e-12
            sections[short] = {
                "name": short, "designation": designation, "area_m2": area * 1e-6,
                "ixx_m4": inertia, "iyy_m4": inertia, "j_m4": max(inertia * 0.01, 1e-12),
                "material": "Steel:S355JR",
            }
        members.append({
            "id": len(members) + 1, "source_name": str(member["name"]),
            "i_node": node_ids[str(member["i_node"])], "j_node": node_ids[str(member["j_node"])],
            "section": section_names[designation], "release_i": "T", "release_j": "T",
        })
    support_names = [
        str(name) for name in geometry.get("support_nodes", [])
    ] or [
        str(geometry["left_support"]),
        str(geometry["right_support"]),
    ]
    column_bearings: list[str] = []
    base_node_ids: dict[str, int] = {}
    if include_columns:
        if column_height_mm <= 0.0:
            raise ValueError("The selected truss result has no positive column height.")
        internal_support = str(
            best.get("building_layout", {}).get("support_arrangement", {}).get(
                "internal_support", "Not required"
            )
        )
        column_bearings = [support_names[0], support_names[-1]]
        if internal_support == "Centre columns":
            column_bearings[1:1] = support_names[1:-1]
        vertical_schedule = {
            str(item["bearing_node"]): item
            for item in best.get("bearing_support_verticals", [])
        }
        database = mdb.load_member_database(
            PROJECT_ROOT / "databases" / "member_database.csv"
        )
        for column_index, bearing in enumerate(column_bearings, 1):
            schedule_item = vertical_schedule.get(bearing)
            if schedule_item is None:
                raise ValueError(f"No supporting-column section is stored for bearing {bearing}.")
            designation = str(schedule_item["section"]["designation"])
            section_name = f"C{column_index:02d}"
            props = mdb.member_properties(_section_family(designation), designation, database)
            sections[section_name] = asdict(
                _section_from_portal(section_name, designation, props)
            )
            top_node = next(node for node in nodes if node["source_name"] == bearing)
            base_id = len(nodes) + 1
            base_node_ids[bearing] = base_id
            nodes.append({
                "id": base_id,
                "source_name": f"BASE-{bearing}",
                "x_m": float(top_node["x_m"]),
                "y_m": 0.0,
                "z_m": 0.0,
            })
            members.append({
                "id": len(members) + 1,
                "source_name": f"COLUMN-{bearing}",
                "i_node": base_id,
                "j_node": node_ids[bearing],
                "section": section_name,
                "release_i": "",
                "release_j": "",
            })
    combinations = _factor_pairs(
        best["load_audit"]["uls_combinations"],
        best["load_audit"]["sls_combinations"],
    )
    combination_cases = {
        case for combo in combinations
        for case in [*combo["uls_factors"], *combo["sls_factors"]]
    }
    cases = best.get("load_audit", {}).get("characteristic_node_loads_kn", {})
    nodal_loads = [
        {"case": case, "node": node_ids[node], "direction": direction, "magnitude": value}
        for case, loads in cases.items() for node, components in loads.items()
        for direction, value in (("FX", float(components[0])), ("FY", float(components[1])))
        if case != "D" and case in combination_cases and abs(float(value)) > 1e-12
    ]
    column_member_loads = []
    if include_columns:
        wall_loads = best.get("load_audit", {}).get(
            "eave_column_member_loads", {}
        )
        for side, bearing in (("left", support_names[0]), ("right", support_names[-1])):
            for load in wall_loads.get(side, []):
                if load["case"] not in combination_cases:
                    continue
                column_member_loads.append({
                    "case": str(load["case"]),
                    "source_member": f"COLUMN-{bearing}",
                    "node_path": [base_node_ids[bearing], node_ids[bearing]],
                    "direction": "X",
                    "w1_kn_m": float(load["w1_kn_m"]),
                    "w2_kn_m": float(load["w2_kn_m"]),
                    "start_m": float(load["start_m"]),
                    "length_m": float(load["length_m"]),
                })
    support_rows = [{
        "node": node_ids[name],
        "fixity": "XY" if index == 0 else "Y",
        "rz_spring_knm_per_rad": None,
    } for index, name in enumerate(support_names) if name not in base_node_ids]
    support_rows.extend({
        "node": base_node_ids[name],
        "fixity": "XY" if name == column_bearings[0] else "Y",
        "rz_spring_knm_per_rad": None,
    } for name in column_bearings)
    load_cases = {
        load["case"] for load in [*nodal_loads, *column_member_loads]
    } | combination_cases
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "PortalFrame prokon_export",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_id": result.get("analysis_id", ""),
        "structural_system": "Truss with columns" if include_columns else "Truss",
        "units": {"distance": "m", "force": "kN", "moment": "kNm"},
        "analysis": {"domain": "XY plane", "type": "Linear", "self_weight_case": "D"},
        "nodes": nodes, "members": members, "sections": list(sections.values()),
        "supports": support_rows, "nodal_loads": nodal_loads,
        "member_loads": column_member_loads,
        "load_combinations": combinations,
        "load_case_map": _load_case_aliases(load_cases),
        "prokon_node_rules": {"bracing": "Every truss panel and restraint location is already a node.", "haunch": "Not applicable."},
        "warnings": [
            (
                "This export adds the selected main and centre-column sections below the truss bearings and applies the source portal's characteristic wall-wind load segments to the two main columns."
                if include_columns else
                "This export is the pin-jointed truss-only analysis model; columns and the longitudinal girder are exported as separate comparison models."
            ),
            "All truss member ends are released as Prokon truss members to match the PortalFrame axial-only solver.",
            "Prokon generates member self-weight in load case D; PortalFrame D nodal self-weight loads are not exported.",
            "Member I and J values are stiffness placeholders derived from area and radius of gyration; released truss axial response depends on E and area.",
        ],
    }


def build_girder_comparison(
    result: Mapping[str, Any], *, ranked_solution: int = 0,
) -> dict[str, Any] | None:
    """Build the selected longitudinal lattice-girder comparison model."""

    best = list(result["ranked_solutions"])[ranked_solution]
    girder = dict(best.get("girder_design", {}))
    if girder.get("status") != "PASS":
        return None
    geometry = girder["geometry"]
    nodes_in = list(geometry["nodes"])
    node_ids = {str(node["name"]): index for index, node in enumerate(nodes_in, 1)}
    schedule = {str(row["member"]): row for row in girder["member_schedule"]}
    sections: dict[str, dict[str, Any]] = {}
    section_names: dict[str, str] = {}
    members = []
    for member in geometry["members"]:
        section = schedule[str(member["name"])]["section"]
        designation = str(section["designation"])
        if designation not in section_names:
            short = f"S{len(section_names) + 1:02d}"
            section_names[designation] = short
            area = float(section["area_mm2"])
            radius = min(float(section.get("rx_mm", 1.0)), float(section.get("ry_mm", 1.0)))
            inertia = area * radius**2 * 1e-12
            sections[short] = {
                "name": short, "designation": designation, "area_m2": area * 1e-6,
                "ixx_m4": inertia, "iyy_m4": inertia,
                "j_m4": max(inertia * 0.01, 1e-12), "material": "Steel:S355JR",
            }
        members.append({
            "id": len(members) + 1, "source_name": str(member["name"]),
            "i_node": node_ids[str(member["i_node"])],
            "j_node": node_ids[str(member["j_node"])],
            "section": section_names[designation], "release_i": "T", "release_j": "T",
        })
    audit = girder.get("load_audit", {})
    combinations = _factor_pairs(
        audit.get("uls_combinations", []), audit.get("sls_combinations", [])
    )
    combination_cases = {
        case for combo in combinations
        for case in [*combo["uls_factors"], *combo["sls_factors"]]
    }
    nodal_loads = [
        {"case": case, "node": node_ids[node], "direction": direction, "magnitude": value}
        for case, loads in audit.get("characteristic_node_loads_kn", {}).items()
        for node, components in loads.items()
        for direction, value in (("FX", float(components[0])), ("FY", float(components[1])))
        if case != "D" and case in combination_cases and abs(float(value)) > 1e-12
    ]
    support_names = list(geometry.get("support_nodes", [])) or [
        geometry["left_support"], geometry["right_support"]
    ]
    load_cases = {load["case"] for load in nodal_loads} | combination_cases
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "PortalFrame prokon_export",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_id": result.get("analysis_id", ""),
        "structural_system": "Longitudinal girder",
        "units": {"distance": "m", "force": "kN", "moment": "kNm"},
        "analysis": {"domain": "XY plane", "type": "Linear", "self_weight_case": "D"},
        "nodes": [{
            "id": node_ids[str(node["name"])], "source_name": node["name"],
            "x_m": float(node["x_mm"]) / 1000.0,
            "y_m": float(node["y_mm"]) / 1000.0, "z_m": 0.0,
        } for node in nodes_in],
        "members": members,
        "sections": list(sections.values()),
        "supports": [{
            "node": node_ids[str(name)], "fixity": "XY" if index == 0 else "Y",
            "rz_spring_knm_per_rad": None,
        } for index, name in enumerate(support_names)],
        "nodal_loads": nodal_loads,
        "member_loads": [],
        "load_combinations": combinations,
        "load_case_map": _load_case_aliases(load_cases),
        "prokon_node_rules": {"bracing": "Every lattice-girder panel is a node.", "haunch": "Not applicable."},
        "warnings": [
            "This is one representative longitudinal lattice-girder span.",
            "The largest absolute characteristic internal truss-bearing reaction is repeated at every truss grid, matching the PortalFrame girder design basis.",
            "Prokon generates the girder member self-weight in load case D.",
        ],
    }


def build_gable_columns_comparison(
    bracing: Mapping[str, Any], combinations: Iterable[Mapping[str, Any]], *,
    analysis_id: str = "", source_system: str = "Portal frame",
) -> dict[str, Any] | None:
    """Build the independently pinned gable-column comparison model."""

    columns = list(bracing.get("gable_columns", []))
    if not columns:
        return None
    database = mdb.load_member_database(
        PROJECT_ROOT / "databases" / "member_database.csv"
    )
    nodes, members, supports = [], [], []
    sections: dict[str, dict[str, Any]] = {}
    member_loads = []
    pressure_by_case = {
        str(item["case"]): float(item["pressure_kpa"])
        for item in bracing.get("pressure_cases", [])
    }
    for index, column in enumerate(columns, 1):
        bottom, top = 2 * index - 1, 2 * index
        height_m = float(column["height_mm"]) / 1000.0
        x_m = float(column["x_mm"]) / 1000.0
        nodes.extend((
            {"id": bottom, "source_name": f'{column["name"]}-BASE', "x_m": x_m, "y_m": 0.0, "z_m": 0.0},
            {"id": top, "source_name": f'{column["name"]}-TOP', "x_m": x_m, "y_m": height_m, "z_m": 0.0},
        ))
        section_name = f"G{index:02d}"
        designation = str(column["section"])
        props = mdb.member_properties(str(column["section_type"]), designation, database)
        sections[section_name] = asdict(
            _section_from_portal(section_name, designation, props)
        )
        members.append({
            "id": index, "source_name": str(column["name"]),
            "i_node": bottom, "j_node": top, "section": section_name,
            "release_i": "", "release_j": "",
        })
        supports.extend((
            {"node": bottom, "fixity": "XY", "rz_spring_knm_per_rad": None},
            {"node": top, "fixity": "XY", "rz_spring_knm_per_rad": None},
        ))
        tributary_m = float(column["tributary_width_mm"]) / 1000.0
        for case, pressure_kpa in pressure_by_case.items():
            line_load = pressure_kpa * tributary_m
            if abs(line_load) > 1e-12:
                member_loads.append({
                    "case": case, "source_member": str(column["name"]),
                    "node_path": [bottom, top], "direction": "X",
                    "w1_kn_m": line_load, "w2_kn_m": line_load,
                    "start_m": None, "length_m": None,
                })
    canonical_combinations = [dict(item) for item in combinations]
    load_cases = {load["case"] for load in member_loads} | {
        case for combo in canonical_combinations
        for case in [*combo["uls_factors"], *combo["sls_factors"]]
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "PortalFrame prokon_export",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_id": analysis_id,
        "structural_system": f"{source_system} gable columns",
        "units": {"distance": "m", "force": "kN", "moment": "kNm"},
        "analysis": {"domain": "XY plane", "type": "Linear", "self_weight_case": "D"},
        "nodes": nodes, "members": members, "sections": list(sections.values()),
        "supports": supports, "nodal_loads": [], "member_loads": member_loads,
        "load_combinations": canonical_combinations,
        "load_case_map": _load_case_aliases(load_cases),
        "prokon_node_rules": {"bracing": "Each gable column is independently pinned at its base and roof restraint.", "haunch": "Not applicable."},
        "warnings": [
            "This model contains the internal gable columns only; corner portal/eave columns and the roof-bracing load path are separate models.",
            "Characteristic W90 pressures are applied over each calculated tributary width; the paired C1-C6 factors are retained for comparison.",
        ],
    }


def _fmt(value: Any, width: int, *, right: bool = False) -> str:
    if value is None:
        text = ""
    elif isinstance(value, float):
        text = f"{value:.8g}"
    else:
        text = str(value)
    if len(text) > width:
        text = text[:width]
    return text.rjust(width) if right else text.ljust(width)


def _row(widths: list[int], values: list[Any], right: set[int] | None = None) -> bytes:
    right = right or set()
    return ("|" + "|".join(_fmt(value, width, right=index in right) for index, (width, value) in enumerate(zip(widths, values))) + "|\r\n").encode("ascii")


def _replace_table(lines: list[bytes], anchor: bytes, rows: list[bytes]) -> None:
    anchor_index = next(index for index, line in enumerate(lines) if anchor in line)
    start = next(index for index in range(anchor_index + 1, len(lines)) if lines[index].lstrip().startswith(b"---"))
    end = next(index for index in range(start + 1, len(lines)) if lines[index].lstrip().startswith(b"---"))
    lines[start + 1:end] = rows or [b"| |\r\n"]


def _node_path_text(path: list[int]) -> str:
    return "-".join(str(item) for item in path)


def _compact_spring(value: float | None) -> str:
    if value is None:
        return ""
    numeric = float(value)
    if numeric and abs(numeric) >= 1000 and abs(numeric / 1000 - round(numeric / 1000)) < 1e-9:
        return f"{numeric / 1000:g}E3"
    return f"{numeric:.3g}"


def render_a03(model: Mapping[str, Any], template: str | Path = DEFAULT_TEMPLATE) -> bytes:
    """Render one canonical model into a Prokon Frame Analysis v12 A03 file."""

    encoded = "".join(Path(template).read_text(encoding="ascii").split()).encode("ascii")
    seed = gzip.decompress(base64.b64decode(encoded))
    # File version 12 is a text input block followed by an opaque Prokon tail.
    # Never split/rejoin that tail: doing so would normalise embedded newline
    # bytes and corrupt the seed. The underlay line is the final text setting
    # in all three supplied reference files.
    marker = b"Modeller underlay file name:\r\n"
    marker_at = seed.find(marker)
    if marker_at < 0:
        raise ValueError("The Prokon v12 template has no text/tail boundary marker.")
    text_end = marker_at + len(marker)
    text = seed[:text_end]
    binary_tail = seed[text_end:]
    lines = text.splitlines(keepends=True)

    now = datetime.now().astimezone().strftime("%Y/%m/%d %H:%M:%S")
    for index, line in enumerate(lines):
        if line.startswith(b"Created:"):
            lines[index] = f"Created: {now}\r\n".encode("ascii")
        elif line.startswith(b"TITLE :"):
            lines[index] = f"TITLE : PortalFrame comparison {model.get('analysis_id', '')}\r\n".encode("ascii")
        elif line.startswith(b" Analysis type:"):
            lines[index] = b" Analysis type:Linear      \r\n"
        elif line.startswith(b" Self weight to be added to:"):
            case = model.get("analysis", {}).get("self_weight_case") or ""
            case = model.get("load_case_map", {}).get(case, case)
            lines[index] = f" Self weight to be added to:{case}\r\n".encode("ascii")
        elif line.startswith(b"Text output file location:"):
            lines[index] = b"Text output file location:Sf.out\r\n"
        elif line.startswith(b"|7  |Steel:S355JR"):
            # PortalFrame steel density is 7.85e-8 kN/mm3 = 78.5 kN/m3.
            lines[index] = line.replace(b"   77.0000", b"   78.5000", 1)

    aliases = dict(model.get("load_case_map", {}))
    cases = sorted(set(aliases.values()))
    _replace_table(lines, b"Harmonic loading parameters", [_row([6, 10, 9], [case, "", ""]) for case in cases])
    _replace_table(lines, b"|Node  ", [_row([6, 7, 7, 5, 6, 4, 8, 8, 8, 11], [node["id"], node["x_m"], node["y_m"], node.get("z_m", 0.0), "", "", "", "", "", ""], {0, 1, 2, 3}) for node in model["nodes"]])
    _replace_table(lines, b"Beam element definition", [_row([23, 7, 5, 8, 8, 8, 8, 10, 3, 5], [f'{member["i_node"]}-{member["j_node"]}', member["section"], "", member.get("release_i", ""), member.get("release_j", ""), "", "", "", "", ""]) for member in model["members"]])

    support_rows = []
    for support in model["supports"]:
        spring = support.get("rz_spring_knm_per_rad")
        support_rows.append(_row([84, 6, 3, 3, 3, 3, 3, 3, 4, 8, 10, 11, 16, 3, 3, 3, 3, 3, 5], [support["node"], support["fixity"], "S" if spring is not None else "", "", "", "", "", "", _compact_spring(spring), "", "", "", "", "", "", "", "", "", ""], {0, 8}))
    _replace_table(lines, b"Translational fixity", support_rows)
    _replace_table(lines, b"Beam Section designation:", [_row([7, 25, 8, 10, 10, 8, 8, 8, 12, 13], [section["name"], section["designation"], section["area_m2"], "", "", section["ixx_m4"], section["iyy_m4"], section["j_m4"], section["material"], ""]) for section in model["sections"]])

    nodal_rows = []
    for load in model.get("nodal_loads", []):
        columns = {"FX": 2, "FY": 3, "FZ": 4, "MX": 5, "MY": 6, "MZ": 7}
        values = [aliases.get(load["case"], load["case"]), load["node"], "", "", "", "", "", "", "", "", ""]
        values[columns[str(load["direction"]).upper()]] = load["magnitude"]
        nodal_rows.append(_row([6, 6, 6, 6, 6, 7, 7, 7, 8, 10, 11], values, set(range(1, 8))))
    _replace_table(lines, b"Node  \xa6Px", nodal_rows)

    beam_rows = []
    represented_cases = {
        aliases.get(load["case"], load["case"])
        for load in [*model.get("nodal_loads", []), *model.get("member_loads", [])]
    }
    # Prokon creates its load-case registry from the load input tables. A case
    # used only for generated self-weight (normally D) therefore needs one
    # explicit blank beam-load row or Prokon reports that the case does not
    # exist when it reads the combinations and self-weight setting.
    for case in cases:
        if case not in represented_cases:
            beam_rows.append(_row(
                [6, 23, 9, 6, 5, 11, 11, 7, 7, 6, 8, 10, 5, 11],
                [case, "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ))
    for load in model.get("member_loads", []):
        beam_rows.append(_row([6, 23, 9, 6, 5, 11, 11, 7, 7, 6, 8, 10, 5, 11], [aliases.get(load["case"], load["case"]), _node_path_text(load["node_path"]), load["direction"], load.get("point_kn", ""), load.get("point_at_m", ""), load.get("w1_kn_m", ""), load.get("w2_kn_m", ""), load.get("start_m", ""), load.get("length_m", ""), "", "", "", "", ""], {3, 4, 5, 6, 7, 8}))
    _replace_table(lines, b"W low", beam_rows)

    combo_rows = []
    for combo in model.get("load_combinations", []):
        all_cases = list(dict.fromkeys([*combo["uls_factors"], *combo["sls_factors"]]))
        for case_index, case in enumerate(all_cases):
            combo_rows.append(_row([11, 6, 6, 6], [combo["id"] if case_index == 0 else "", aliases.get(case, case), combo["uls_factors"].get(case, ""), combo["sls_factors"].get(case, "")]))
        combo_rows.append(_row([11, 6, 6, 6], ["", "", "", ""]))
    _replace_table(lines, b"\xa6ULS   \xa6SLS", combo_rows)
    return b"".join(lines) + binary_tail


def _comparison_stem(model: Mapping[str, Any]) -> str:
    system = str(model.get("structural_system", "comparison")).lower()
    if system == "portal frame":
        return "portalframe_prokon_input"
    if system == "truss":
        return "truss_prokon_input"
    if system == "truss with columns":
        return "truss_with_columns_prokon_input"
    if system == "longitudinal girder":
        return "longitudinal_girder_prokon_input"
    if "gable columns" in system:
        prefix = "truss" if system.startswith("truss") else "portalframe"
        return f"{prefix}_gable_columns_prokon_input"
    return re.sub(r"[^a-z0-9]+", "_", system).strip("_") + "_prokon_input"


def write_comparison_package(model: Mapping[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stem = _comparison_stem(model)
    json_path = output / f"{stem}.json"
    a03_path = output / f"{stem}.A03"
    json_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    a03_path.write_bytes(render_a03(model))
    return {"json": json_path, "a03": a03_path}


def write_comparison_bundle(
    models: Mapping[str, Mapping[str, Any] | None], output_dir: str | Path,
) -> dict[str, Any]:
    """Write every available comparison model and one downloadable ZIP bundle."""

    output = Path(output_dir)
    written: dict[str, dict[str, Path]] = {}
    for key, model in models.items():
        if model is not None:
            written[key] = write_comparison_package(model, output)
    zip_path = output / "prokon_comparison_models.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for paths in written.values():
            for path in paths.values():
                archive.write(path, arcname=path.name)
    return {"models": written, "zip": zip_path}
