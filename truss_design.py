"""Generic preliminary truss and eave-column design workflow.

This iteration deliberately exposes its assumptions.  It reuses the existing
PortalFrame load-generation and combination logic, analyses a 2D pin-jointed
mono/duo-pitched trusses, groups chord sections by fabricated span, sizes web
members from equal angles or conservative
back-to-back equal-angle pairs, iterates self-weight, and checks span/180 nodal
deflection, and sizes the eave columns from truss reactions and wall wind.
Reference markups are verification examples, not product templates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any, Mapping

from bracing_design import load_bracing_database
from truss_layout import build_truss_layout
from truss_column_design import (
    describe_concrete_centre_columns,
    design_centre_columns_axial,
    design_eave_columns,
)
from truss_loading import build_panel_point_loads, factored_node_loads, with_self_weight
from truss_model import (
    PrattTrussGeometry,
    analyse_truss,
    calculate_chord_restraint_layout,
    generate_flat_lattice_girder,
    generate_truss_geometry,
    member_length_mm,
)


PHI = 0.9
BUCKLING_EXPONENT = 1.34
COMPRESSION_SLENDERNESS_LIMIT = 200.0
TENSION_SLENDERNESS_LIMIT = 300.0
DEFAULT_E_MPA = 200_000.0
DEFAULT_FY_MPA = 355.0
MINIMUM_ANGLE_LEG_MM = 50.0
MINIMUM_ANGLE_THICKNESS_MM = 5.0
PLATEWORK_COST_ALLOWANCE = 0.08
DEFAULT_DATABASE = Path(__file__).with_name("bracing_member_database.csv")


@dataclass(frozen=True)
class AngleCandidate:
    designation: str
    base_designation: str
    configuration: str
    area_mm2: float
    mass_kg_m: float
    rx_mm: float
    ry_mm: float
    rv_mm: float

    @property
    def minimum_radius_mm(self) -> float:
        radii = [value for value in (self.rx_mm, self.ry_mm, self.rv_mm) if value > 0]
        return min(radii) if radii else 0.0


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_angle_candidates(
    database_path: str | Path = DEFAULT_DATABASE,
) -> list[AngleCandidate]:
    """Load single and conservative back-to-back equal-angle candidates."""

    rows = load_bracing_database(database_path).get("Equal Angles", [])
    candidates: list[AngleCandidate] = []
    for row in rows:
        area = _float(row.get("A")) * 1000.0
        mass = _float(row.get("m"))
        rx = _float(row.get("rx"))
        ry = _float(row.get("ry")) or rx
        rv = _float(row.get("rv"))
        leg_h = _float(row.get("h"))
        leg_b = _float(row.get("b"))
        thickness = _float(row.get("t"))
        name = str(row.get("Designation", "")).strip()
        if not name or min(area, mass, rx, ry, rv) <= 0:
            continue
        if (
            leg_h < MINIMUM_ANGLE_LEG_MM
            or leg_b < MINIMUM_ANGLE_LEG_MM
            or thickness < MINIMUM_ANGLE_THICKNESS_MM
        ):
            continue
        candidates.append(AngleCandidate(
            designation=f"L {name}", base_designation=name,
            configuration="Single equal angle", area_mm2=area, mass_kg_m=mass,
            rx_mm=rx, ry_mm=ry, rv_mm=rv,
        ))
        candidates.append(AngleCandidate(
            designation=f"2L {name}", base_designation=name,
            configuration="Back-to-back equal angles", area_mm2=2.0 * area,
            mass_kg_m=2.0 * mass,
            # A symmetric heel-to-heel pair removes the single angle's weak
            # principal-axis radius. No further spacing benefit is assumed
            # until the gusset gap and stitch details are defined.
            rx_mm=rx, ry_mm=max(ry, rx), rv_mm=rx,
        ))
    if not candidates:
        raise ValueError(
            "No equal-angle sections at or above 50x50x5 are available for truss design."
        )
    return sorted(
        candidates,
        key=lambda item: (item.mass_kg_m, item.area_mm2, item.designation),
    )


def bounded_depth_candidates_mm(
    minimum_depth_mm: float,
    maximum_depth_mm: float,
    increment_mm: float,
) -> list[float]:
    """Return inclusive candidates between explicit engineering depth limits."""

    if min(minimum_depth_mm, maximum_depth_mm, increment_mm) <= 0:
        raise ValueError("Depth limits and increment must be positive.")
    if maximum_depth_mm < minimum_depth_mm:
        raise ValueError("Maximum depth must be at least minimum depth.")
    values = []
    value = minimum_depth_mm
    while value <= maximum_depth_mm + 1e-6:
        values.append(round(value, 6))
        value += increment_mm
    if maximum_depth_mm - values[-1] > 1e-6:
        values.append(float(maximum_depth_mm))
    return values


def _effective_length_mm(
    geometry: PrattTrussGeometry,
    member,
    restraint_layout: Mapping[str, Any],
) -> float:
    actual = member_length_mm(geometry, member)
    if member.role == "top_chord":
        return max(
            actual,
            float(restraint_layout["top_chord"]["member_effective_lengths_mm"][member.name]),
        )
    if member.role == "bottom_chord":
        return max(
            actual,
            float(restraint_layout["bottom_chord"]["member_effective_lengths_mm"][member.name]),
        )
    return actual


def _resistances(
    candidate: AngleCandidate,
    effective_length_mm: float,
    *,
    fy_mpa: float,
    elastic_modulus_mpa: float,
) -> dict[str, float]:
    radius = candidate.minimum_radius_mm
    slenderness_ratio = effective_length_mm / radius if radius > 0 else math.inf
    nondimensional = slenderness_ratio * math.sqrt(
        fy_mpa / (math.pi ** 2 * elastic_modulus_mpa)
    )
    tension_kn = PHI * candidate.area_mm2 * fy_mpa / 1000.0
    compression_kn = tension_kn * (
        1.0 + nondimensional ** (2.0 * BUCKLING_EXPONENT)
    ) ** (-1.0 / BUCKLING_EXPONENT)
    return {
        "tension_kn": tension_kn,
        "compression_kn": compression_kn,
        "slenderness_ratio": slenderness_ratio,
        "nondimensional_slenderness": nondimensional,
    }


def _check_details(
    candidate: AngleCandidate, check: Mapping[str, float]
) -> dict[str, Any]:
    component_utilisations = {
        "tension_resistance": float(check["tension_utilisation"]),
        "compression_resistance": float(check["compression_utilisation"]),
        "slenderness": float(check["slenderness_utilisation"]),
    }
    governing_check = max(component_utilisations, key=component_utilisations.get)
    return {
        "minimum_radius_mm": candidate.minimum_radius_mm,
        "governing_check": governing_check,
        "design_calculation": {
            "design_tension_resistance_kn": float(check["tension_kn"]),
            "design_compression_resistance_kn": float(check["compression_kn"]),
            "slenderness_ratio": float(check["slenderness_ratio"]),
            "nondimensional_slenderness": float(
                check["nondimensional_slenderness"]
            ),
            "slenderness_limit": float(check["slenderness_limit"]),
            "component_utilisations": component_utilisations,
            "governing_check": governing_check,
            "governing_utilisation": float(check["utilisation"]),
        },
    }


def _select_member(
    candidates: list[AngleCandidate],
    tension_kn: float,
    compression_kn: float,
    effective_length_mm: float,
    minimum_area_mm2: float,
    *,
    fy_mpa: float,
    elastic_modulus_mpa: float,
) -> tuple[AngleCandidate, dict[str, float]]:
    for candidate in candidates:
        if candidate.area_mm2 + 1e-9 < minimum_area_mm2:
            continue
        resistance = _resistances(
            candidate, effective_length_mm,
            fy_mpa=fy_mpa, elastic_modulus_mpa=elastic_modulus_mpa,
        )
        tension_util = tension_kn / resistance["tension_kn"] if tension_kn > 0 else 0.0
        compression_util = (
            compression_kn / resistance["compression_kn"] if compression_kn > 0 else 0.0
        )
        slenderness_limit = (
            COMPRESSION_SLENDERNESS_LIMIT if compression_kn > 1e-9
            else TENSION_SLENDERNESS_LIMIT
        )
        slenderness_util = resistance["slenderness_ratio"] / slenderness_limit
        utilisation = max(tension_util, compression_util, slenderness_util)
        if utilisation <= 1.0 + 1e-9:
            return candidate, {
                **resistance,
                "tension_utilisation": tension_util,
                "compression_utilisation": compression_util,
                "slenderness_limit": slenderness_limit,
                "slenderness_utilisation": slenderness_util,
                "utilisation": utilisation,
            }
    raise ValueError(
        f"No equal-angle candidate passes T={tension_kn:.1f} kN, "
        f"C={compression_kn:.1f} kN and effective length {effective_length_mm:.0f} mm."
    )


def _fabrication_groups(
    geometry: PrattTrussGeometry,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Build practical chord and web groups within each fabricated span."""

    groups: dict[str, list[str]] = {}
    member_to_group: dict[str, str] = {}
    member_by_name = {member.name: member for member in geometry.members}

    def minimum_three_chunks(names: list[str]) -> list[list[str]]:
        """Partition consecutive webs without creating one- or two-panel groups."""

        count = len(names)
        if count <= 5:
            return [names] if names else []
        complete, remainder = divmod(count, 3)
        sizes = [3] * complete
        if remainder == 1:
            sizes[-1] = 4
        elif remainder == 2:
            sizes[-1] = 5
        chunks = []
        start = 0
        for size in sizes:
            chunks.append(names[start:start + size])
            start += size
        return chunks

    panel_start = 0
    diagonal_start = 1
    for span_index, panel_count in enumerate(geometry.bay_panel_counts, 1):
        for role, prefix in (("top_chord", "TC"), ("bottom_chord", "BC")):
            group_name = f"{role}_span_{span_index}"
            names = [
                f"{prefix}{index}"
                for index in range(panel_start + 1, panel_start + panel_count + 1)
            ]
            groups[group_name] = names
            member_to_group.update({name: group_name for name in names})

        vertical_names = [
            f"V{index + 1}"
            for index in range(panel_start, panel_start + panel_count + 1)
            if member_by_name[f"V{index + 1}"].role == "vertical"
        ]
        diagonal_names = [
            f"D{index}"
            for index in range(diagonal_start, diagonal_start + panel_count)
        ]
        for role, names in (
            ("vertical", vertical_names),
            ("diagonal", diagonal_names),
        ):
            for group_index, chunk in enumerate(minimum_three_chunks(names), 1):
                group_name = f"{role}_span_{span_index}_group_{group_index}"
                groups[group_name] = chunk
                member_to_group.update({name: group_name for name in chunk})

        panel_start += panel_count
        diagonal_start += panel_count

    for member in geometry.members:
        if member.name in member_to_group:
            continue
        group_name = (
            f"bearing_vertical_{member.name}"
            if member.role == "support_vertical"
            else f"individual_{member.name}"
        )
        groups[group_name] = [member.name]
        member_to_group[member.name] = group_name
    return groups, member_to_group


def _select_fabrication_group(
    candidates: list[AngleCandidate],
    member_names: list[str],
    envelopes: Mapping[str, Mapping[str, Any]],
    effective_lengths_mm: Mapping[str, float],
    minimum_areas_mm2: Mapping[str, float],
    *,
    fy_mpa: float,
    elastic_modulus_mpa: float,
) -> tuple[AngleCandidate, dict[str, dict[str, float]]]:
    """Select one section that passes every member in a fabrication group."""

    minimum_area = max(minimum_areas_mm2[name] for name in member_names)
    for candidate in candidates:
        if candidate.area_mm2 + 1e-9 < minimum_area:
            continue
        checks: dict[str, dict[str, float]] = {}
        for name in member_names:
            envelope = envelopes[name]
            try:
                _, checks[name] = _select_member(
                    [candidate],
                    float(envelope["maximum_tension_kn"]),
                    float(envelope["maximum_compression_kn"]),
                    effective_lengths_mm[name],
                    minimum_area,
                    fy_mpa=fy_mpa,
                    elastic_modulus_mpa=elastic_modulus_mpa,
                )
            except ValueError:
                break
        if len(checks) == len(member_names):
            return candidate, checks
    raise ValueError(
        "No common equal-angle section passes fabrication group "
        f"{', '.join(member_names)}."
    )


def _fabrication_group_summary(
    member_schedule: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in member_schedule:
        grouped.setdefault(str(item["fabrication_group"]), []).append(item)
    result = []
    for group_name, members in grouped.items():
        if not (group_name.startswith("top_chord") or group_name.startswith("bottom_chord")):
            continue
        governing = max(members, key=lambda item: float(item["utilisation"]))
        result.append({
            "group": group_name,
            "role": governing["role"],
            "span": int(group_name.rsplit("_", 1)[-1]),
            "section": governing["section"]["designation"],
            "member_count": len(members),
            "members": [item["member"] for item in members],
            "governing_member": governing["member"],
            "governing_utilisation": governing["utilisation"],
        })
    return sorted(result, key=lambda item: (item["span"], item["role"]))


def _web_fabrication_group_summary(
    member_schedule: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Summarise practical web groups used for procurement and fabrication."""

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in member_schedule:
        group_name = str(item["fabrication_group"])
        if group_name.startswith(("vertical_span_", "diagonal_span_")):
            grouped.setdefault(group_name, []).append(item)
    result = []
    for group_name, members in grouped.items():
        parts = group_name.split("_")
        governing = max(members, key=lambda item: float(item["utilisation"]))
        result.append({
            "group": group_name,
            "role": governing["role"],
            "span": int(parts[2]),
            "group_index": int(parts[-1]),
            "section": governing["section"]["designation"],
            "member_count": len(members),
            "members": [item["member"] for item in members],
            "governing_member": governing["member"],
            "governing_utilisation": governing["utilisation"],
        })
    return sorted(
        result,
        key=lambda item: (item["span"], item["role"], item["group_index"]),
    )


def _select_grouped_members(
    geometry: PrattTrussGeometry,
    candidates: list[AngleCandidate],
    envelopes: Mapping[str, Mapping[str, Any]],
    restraint_layout: Mapping[str, Any],
    minimum_areas_mm2: Mapping[str, float],
    *,
    fy_mpa: float,
    elastic_modulus_mpa: float,
) -> tuple[dict[str, AngleCandidate], dict[str, str]]:
    groups, member_to_group = _fabrication_groups(geometry)
    effective_lengths = {
        member.name: _effective_length_mm(geometry, member, restraint_layout)
        for member in geometry.members
    }
    selections: dict[str, AngleCandidate] = {}
    previous_web_section: dict[tuple[str, str], AngleCandidate] = {}
    for group_name, member_names in groups.items():
        selected, _ = _select_fabrication_group(
            candidates,
            member_names,
            envelopes,
            effective_lengths,
            minimum_areas_mm2,
            fy_mpa=fy_mpa,
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        if group_name.startswith(("vertical_span_", "diagonal_span_")):
            parts = group_name.split("_")
            series = (parts[0], parts[2])
            previous = previous_web_section.get(series)
            if previous is not None and selected.area_mm2 < previous.area_mm2:
                _, retained_checks = _select_fabrication_group(
                    [previous],
                    member_names,
                    envelopes,
                    effective_lengths,
                    minimum_areas_mm2,
                    fy_mpa=fy_mpa,
                    elastic_modulus_mpa=elastic_modulus_mpa,
                )
                retained_utilisation = max(
                    check["utilisation"] for check in retained_checks.values()
                )
                if retained_utilisation >= 0.75 - 1e-9:
                    selected = previous
            previous_web_section[series] = selected
        selections.update({name: selected for name in member_names})
    return selections, member_to_group


def _analyse_combinations(
    geometry: PrattTrussGeometry,
    selections: Mapping[str, AngleCandidate],
    cases: Mapping[str, Mapping[str, tuple[float, float]]],
    combinations: list[dict],
    *,
    elastic_modulus_mpa: float,
    area_overrides_mm2: Mapping[str, float] | None = None,
) -> dict[str, dict]:
    areas = {name: selection.area_mm2 for name, selection in selections.items()}
    if area_overrides_mm2:
        areas.update({
            name: float(area)
            for name, area in area_overrides_mm2.items()
        })
    return {
        combination["name"]: analyse_truss(
            geometry,
            areas,
            factored_node_loads(cases, combination),
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        for combination in combinations
    }


def _force_envelopes(
    geometry: PrattTrussGeometry,
    combination_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    envelopes = {}
    for member in geometry.members:
        forces = {
            name: float(result["member_forces_kn"][member.name])
            for name, result in combination_results.items()
        }
        tension_name = max(forces, key=forces.get)
        compression_name = min(forces, key=forces.get)
        envelopes[member.name] = {
            "maximum_tension_kn": max(0.0, forces[tension_name]),
            "tension_combination": tension_name,
            "maximum_compression_kn": max(0.0, -forces[compression_name]),
            "compression_combination": compression_name,
            "forces_by_combination_kn": forces,
        }
    return envelopes


def _maximum_vertical_deflection(
    results: Mapping[str, Mapping[str, Any]],
) -> tuple[float, str, str]:
    maximum = 0.0
    governing_combination = ""
    governing_node = ""
    for combination, result in results.items():
        for node_name, movement in result["node_displacements_mm"].items():
            value = abs(float(movement["dy"]))
            if value > maximum:
                maximum = value
                governing_combination = combination
                governing_node = node_name
    return maximum, governing_combination, governing_node


def _deflection_visualisation(
    geometry: PrattTrussGeometry,
    results: Mapping[str, Mapping[str, Any]],
    combinations: list[dict],
    limit_mm: float,
) -> dict[str, Any]:
    """Return compact, renderer-ready SLS nodal displacement results."""

    factors_by_name = {
        str(combination["name"]): dict(combination.get("factors", {}))
        for combination in combinations
    }
    return {
        "structural_system": "Truss",
        "geometry": geometry.to_dict(),
        "deflection_limit_mm": float(limit_mm),
        "combinations": [
            {
                "name": name,
                "kind": "SLS",
                "factors": factors_by_name.get(name, {}),
                "node_displacements_mm": {
                    node_name: {
                        "dx": float(movement["dx"]),
                        "dy": float(movement["dy"]),
                    }
                    for node_name, movement in result["node_displacements_mm"].items()
                },
            }
            for name, result in results.items()
        ],
    }


def _mass_kg(
    geometry: PrattTrussGeometry,
    selections: Mapping[str, AngleCandidate],
) -> float:
    by_name = {member.name: member for member in geometry.members}
    return sum(
        selection.mass_kg_m * member_length_mm(geometry, by_name[name]) / 1000.0
        for name, selection in selections.items()
        if by_name[name].role != "support_vertical"
    )


def _member_masses_for_self_weight(
    geometry: PrattTrussGeometry,
    selections: Mapping[str, AngleCandidate],
) -> dict[str, float]:
    roles = {member.name: member.role for member in geometry.members}
    return {
        name: (
            0.0 if roles[name] == "support_vertical" else selection.mass_kg_m
        )
        for name, selection in selections.items()
    }


def _individually_optimised_web_mass_kg(
    geometry: PrattTrussGeometry,
    current_selections: Mapping[str, AngleCandidate],
    candidates: list[AngleCandidate],
    envelopes: Mapping[str, Mapping[str, Any]],
    restraint_layout: Mapping[str, Any],
    minimum_areas_mm2: Mapping[str, float],
    *,
    fy_mpa: float,
    elastic_modulus_mpa: float,
) -> float:
    """Return a comparison mass with every ordinary web independently selected."""

    comparison = dict(current_selections)
    for member in geometry.members:
        if member.role not in {"vertical", "diagonal"}:
            continue
        envelope = envelopes[member.name]
        selected, _ = _select_member(
            candidates,
            float(envelope["maximum_tension_kn"]),
            float(envelope["maximum_compression_kn"]),
            _effective_length_mm(geometry, member, restraint_layout),
            float(minimum_areas_mm2[member.name]),
            fy_mpa=fy_mpa,
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        comparison[member.name] = selected
    return _mass_kg(geometry, comparison)


def _loads_with_direct_self_weight(
    geometry: PrattTrussGeometry,
    base_loads: Mapping[str, Mapping[str, tuple[float, float]]],
    member_masses_kg_m: Mapping[str, float],
    factor: float,
) -> dict[str, dict[str, tuple[float, float]]]:
    result = {
        case: {node: [float(value[0]), float(value[1])] for node, value in loads.items()}
        for case, loads in base_loads.items()
    }
    nodes = {node.name: node for node in geometry.nodes}
    for member in geometry.members:
        i_node, j_node = nodes[member.i_node], nodes[member.j_node]
        length_m = math.hypot(
            j_node.x_mm - i_node.x_mm, j_node.y_mm - i_node.y_mm
        ) / 1000.0
        weight_kn = (
            float(member_masses_kg_m[member.name]) * length_m * 9.80665 / 1000.0
        )
        for loads in result.values():
            for node_name in (member.i_node, member.j_node):
                target = loads.setdefault(node_name, [0.0, 0.0])
                target[1] -= factor * weight_kn / 2.0
    return {
        case: {node: tuple(value) for node, value in loads.items()}
        for case, loads in result.items()
    }


def _analyse_direct_cases(
    geometry: PrattTrussGeometry,
    selections: Mapping[str, AngleCandidate],
    loads_by_case: Mapping[str, Mapping[str, tuple[float, float]]],
    elastic_modulus_mpa: float,
) -> dict[str, dict]:
    areas = {name: selection.area_mm2 for name, selection in selections.items()}
    return {
        name: analyse_truss(
            geometry, areas, loads, elastic_modulus_mpa=elastic_modulus_mpa
        )
        for name, loads in loads_by_case.items()
    }


def _girder_reaction_loads(
    truss_geometry: PrattTrussGeometry,
    truss_results: Mapping[str, Mapping[str, Any]],
    girder_panel_count: int,
    girder_bays: int,
) -> dict[str, dict[str, tuple[float, float]]]:
    internal_supports = list(truss_geometry.support_nodes[1:-1])
    if not internal_supports:
        return {}
    panels_per_building_bay = girder_panel_count // girder_bays
    loads_by_case = {}
    for case_name, result in truss_results.items():
        reactions = [
            float(result["reactions_kn"][support]["fy"])
            for support in internal_supports
        ]
        bearing_reaction = max(reactions, key=abs)
        loads_by_case[case_name] = {
            f"T{bay * panels_per_building_bay}": (0.0, -bearing_reaction)
            for bay in range(girder_bays + 1)
        }
    return loads_by_case


def _design_lattice_girder(
    truss_geometry: PrattTrussGeometry,
    uls_results: Mapping[str, Mapping[str, Any]],
    sls_results: Mapping[str, Mapping[str, Any]],
    building_layout: Mapping[str, Any],
    truss_data: Mapping[str, Any],
    candidates: list[AngleCandidate],
) -> dict[str, Any]:
    """Search the lightest repeated longitudinal girder within entered limits."""

    girders = list(building_layout.get("girders", []))
    if not girders:
        return {"status": "NOT_REQUIRED"}
    girder_bays = int(truss_data["girder_span_bays"])
    span_mm = float(truss_data["girder_span_mm"])
    spacing_mm = span_mm / girder_bays
    elastic_modulus_mpa = _float(
        truss_data.get("elastic_modulus_mpa"), DEFAULT_E_MPA
    )
    fy_mpa = _float(truss_data.get("fy_mpa"), DEFAULT_FY_MPA)
    depth_values = bounded_depth_candidates_mm(
        _float(truss_data.get("girder_minimum_depth_mm"), 2000.0),
        _float(truss_data.get("girder_maximum_depth_mm"), 4000.0),
        _float(truss_data.get("girder_depth_increment_mm"), 250.0),
    )
    passing = []
    rejected = []
    for depth_mm in depth_values:
        try:
            panels_per_bay = max(2, math.ceil(spacing_mm / depth_mm))
            if panels_per_bay % 2:
                panels_per_bay += 1
            panel_count = girder_bays * panels_per_bay
            geometry = generate_flat_lattice_girder(
                span_mm, depth_mm, panel_count,
                topology=str(truss_data.get("topology", "Warren with verticals")),
            )
            restraint = calculate_chord_restraint_layout(
                geometry, panels_per_bay, panels_per_bay
            )
            uls_base = _girder_reaction_loads(
                truss_geometry, uls_results, panel_count, girder_bays
            )
            sls_base = _girder_reaction_loads(
                truss_geometry, sls_results, panel_count, girder_bays
            )
            selections = {member.name: candidates[0] for member in geometry.members}
            minimum_areas = {member.name: 0.0 for member in geometry.members}
            _, member_to_group = _fabrication_groups(geometry)
            limit_mm = span_mm / _float(
                truss_data.get("girder_deflection_denominator"), 360.0
            )
            for iteration in range(1, 11):
                masses = {name: item.mass_kg_m for name, item in selections.items()}
                uls_loads = _loads_with_direct_self_weight(
                    geometry, uls_base, masses, 1.35
                )
                analysed_uls = _analyse_direct_cases(
                    geometry, selections, uls_loads, elastic_modulus_mpa
                )
                envelopes = _force_envelopes(geometry, analysed_uls)
                next_selections, _ = _select_grouped_members(
                    geometry,
                    candidates,
                    envelopes,
                    restraint,
                    minimum_areas,
                    fy_mpa=fy_mpa,
                    elastic_modulus_mpa=elastic_modulus_mpa,
                )
                for member in geometry.members:
                    selected = next_selections[member.name]
                    # Keep the self-weight iteration monotonic. Once a section
                    # is required, a later load redistribution cannot silently
                    # downgrade it and create a two-section oscillation.
                    minimum_areas[member.name] = max(
                        minimum_areas[member.name], selected.area_mm2
                    )
                sls_loads = _loads_with_direct_self_weight(
                    geometry, sls_base,
                    {name: item.mass_kg_m for name, item in next_selections.items()},
                    1.0,
                )
                analysed_sls = _analyse_direct_cases(
                    geometry, next_selections, sls_loads, elastic_modulus_mpa
                )
                maximum_deflection, deflection_case, deflection_node = (
                    _maximum_vertical_deflection(analysed_sls)
                )
                if maximum_deflection > limit_mm:
                    stiffness_factor = max(
                        1.05, 1.02 * maximum_deflection / limit_mm
                    )
                    for name, selected in next_selections.items():
                        minimum_areas[name] = max(
                            minimum_areas[name],
                            selected.area_mm2 * stiffness_factor,
                        )
                unchanged = all(
                    next_selections[name].designation == selections[name].designation
                    for name in selections
                )
                selections = next_selections
                if maximum_deflection <= limit_mm and unchanged:
                    break
            else:
                raise ValueError("Girder section iteration did not converge.")

            uls_loads = _loads_with_direct_self_weight(
                geometry, uls_base,
                {name: item.mass_kg_m for name, item in selections.items()},
                1.35,
            )
            analysed_uls = _analyse_direct_cases(
                geometry, selections, uls_loads, elastic_modulus_mpa
            )
            envelopes = _force_envelopes(geometry, analysed_uls)
            member_checks = []
            for member in geometry.members:
                selected = selections[member.name]
                envelope = envelopes[member.name]
                effective_length = _effective_length_mm(geometry, member, restraint)
                _, check = _select_member(
                    [selected], envelope["maximum_tension_kn"],
                    envelope["maximum_compression_kn"], effective_length, 0.0,
                    fy_mpa=fy_mpa, elastic_modulus_mpa=elastic_modulus_mpa,
                )
                member_checks.append({
                    "member": member.name,
                    "role": member.role,
                    "fabrication_group": member_to_group[member.name],
                    "i_node": member.i_node,
                    "j_node": member.j_node,
                    "length_mm": member_length_mm(geometry, member),
                    "effective_length_mm": effective_length,
                    "section": asdict(selected),
                    **{
                        key: value for key, value in envelope.items()
                        if key != "forces_by_combination_kn"
                    },
                    **check,
                    **_check_details(selected, check),
                })
            governing = max(member_checks, key=lambda item: item["utilisation"])
            mass_kg = _mass_kg(geometry, selections)
            repeated_span_count = sum(item["span_count"] for item in girders)
            passing.append({
                "status": "PASS",
                "geometry": geometry.to_dict(),
                "mass_per_span_kg": mass_kg,
                "repeated_span_count": repeated_span_count,
                "total_mass_kg": mass_kg * repeated_span_count,
                "member_schedule": member_checks,
                "chord_fabrication_groups": _fabrication_group_summary(member_checks),
                "governing_strength": {
                    "member": governing["member"],
                    "section": governing["section"]["designation"],
                    "check": governing["governing_check"],
                    "utilisation": governing["utilisation"],
                },
                "serviceability": {
                    "limit": f"Span/{_float(truss_data.get('girder_deflection_denominator'), 360.0):g}",
                    "limit_mm": limit_mm,
                    "maximum_vertical_deflection_mm": maximum_deflection,
                    "governing_combination": deflection_case,
                    "governing_node": deflection_node,
                    "utilisation": maximum_deflection / limit_mm,
                },
                "load_basis": (
                    "Largest absolute internal truss-bearing reaction is repeated "
                    "at each truss grid along one simply-supported girder span."
                ),
                "restraint_layout": restraint,
            })
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({"depth_mm": depth_mm, "reason": str(exc)})
    if not passing:
        details = "; ".join(
            f"{item['depth_mm']:.0f} mm: {item['reason']}" for item in rejected
        )
        raise ValueError(f"No lattice girder passes the entered depth limits. {details}")
    passing.sort(key=lambda item: (item["total_mass_kg"], item["mass_per_span_kg"]))
    best = passing[0]
    best["candidate_summary"] = {
        "attempted": len(depth_values),
        "passed": len(passing),
        "rejected": rejected,
    }
    return best


def _support_vertical_section_schedule(
    geometry: PrattTrussGeometry,
    building_layout: Mapping[str, Any],
    eave_column_design: Mapping[str, Any],
    girder_design: Mapping[str, Any],
    centre_column_design: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Assign the actual supporting column/girder section at every bearing line."""

    eave_section = {
        "designation": str(eave_column_design["section"]),
        "section_family": str(eave_column_design["section_family"]),
        "area_mm2": float(eave_column_design["area_mm2"]),
        "mass_kg_m": float(eave_column_design["mass_kg_m"]),
    }
    girder_verticals = [
        item
        for item in girder_design.get("member_schedule", [])
        if item.get("role") == "vertical"
    ]
    if girder_verticals:
        governing_girder_vertical = max(
            girder_verticals,
            key=lambda item: float(item["section"]["area_mm2"]),
        )
        girder_section = {
            "designation": str(
                governing_girder_vertical["section"]["designation"]
            ),
            "section_family": "Longitudinal lattice girder vertical",
            "area_mm2": float(
                governing_girder_vertical["section"]["area_mm2"]
            ),
            "mass_kg_m": float(
                governing_girder_vertical["section"]["mass_kg_m"]
            ),
        }
    else:
        girder_section = eave_section

    internal_support = str(
        building_layout.get("support_arrangement", {}).get(
            "internal_support", "Not required"
        )
    )
    centre_design = centre_column_design or {}
    schedule = []
    vertical_members = list(geometry.support_vertical_members)
    for index, (bearing_node, member_name) in enumerate(
        zip(geometry.bearing_nodes, vertical_members)
    ):
        is_outer = index in {0, len(vertical_members) - 1}
        if is_outer or internal_support != "Longitudinal girders":
            section = eave_section
            if not is_outer and centre_design.get("status") == "PASS":
                section = {
                    "designation": str(centre_design["section"]),
                    "section_family": str(centre_design["section_family"]),
                    "area_mm2": float(centre_design["area_mm2"]),
                    "mass_kg_m": float(centre_design["mass_kg_m"]),
                }
                source = "Designed axial centre column"
            else:
                source = (
                    "Main eave column"
                    if is_outer
                    else "Centre column using the preliminary main-column section"
                )
        else:
            section = girder_section
            source = "Longitudinal girder bearing vertical"
        schedule.append({
            "member": member_name,
            "bearing_node": bearing_node,
            "source": source,
            "section": dict(section),
        })
    return schedule


def _design_candidate(
    geometry: PrattTrussGeometry,
    building_data: Mapping[str, Any],
    wind_data: Mapping[str, Any],
    truss_data: Mapping[str, Any],
    candidates: list[AngleCandidate],
) -> dict[str, Any]:
    fy_mpa = _float(truss_data.get("fy_mpa"), DEFAULT_FY_MPA)
    elastic_modulus_mpa = _float(
        truss_data.get("elastic_modulus_mpa"), DEFAULT_E_MPA
    )
    load_bundle = build_panel_point_loads(
        building_data, wind_data, truss_data, geometry
    )
    restraint_layout = calculate_chord_restraint_layout(
        geometry,
        _float(truss_data.get("top_chord_brace_every_n_purlins"), 1),
        _float(truss_data.get("bottom_chord_brace_every_n_purlins"), 2),
    )
    selections = {member.name: candidates[0] for member in geometry.members}
    minimum_areas = {member.name: 0.0 for member in geometry.members}
    _, member_to_group = _fabrication_groups(geometry)
    deflection_limit_mm = geometry.design_span_mm / _float(
        truss_data.get("deflection_denominator"), 180.0
    )
    building_layout = build_truss_layout(
        building_data, truss_data, geometry, restraint_layout
    )
    converged = False
    last_mass = 0.0

    for iteration in range(1, 13):
        member_masses = _member_masses_for_self_weight(geometry, selections)
        cases = with_self_weight(
            load_bundle["cases"], geometry, member_masses
        )
        uls_results = _analyse_combinations(
            geometry, selections, cases, load_bundle["uls_combinations"],
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        envelopes = _force_envelopes(geometry, uls_results)
        next_selections, _ = _select_grouped_members(
            geometry,
            candidates,
            envelopes,
            restraint_layout,
            minimum_areas,
            fy_mpa=fy_mpa,
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        for member in geometry.members:
            selection = next_selections[member.name]
            # Self-weight can move a member either side of a database boundary.
            # Retaining the largest required area makes the iteration stable
            # and conservatively includes the resulting weight increase.
            minimum_areas[member.name] = max(
                minimum_areas[member.name], selection.area_mm2
            )

        cases = with_self_weight(
            load_bundle["cases"], geometry,
            _member_masses_for_self_weight(geometry, next_selections),
        )
        sls_results = _analyse_combinations(
            geometry, next_selections, cases, load_bundle["sls_combinations"],
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        maximum_deflection, _, _ = _maximum_vertical_deflection(sls_results)
        if maximum_deflection > deflection_limit_mm:
            stiffness_factor = max(1.05, 1.02 * maximum_deflection / deflection_limit_mm)
            for name, selection in next_selections.items():
                minimum_areas[name] = max(
                    minimum_areas[name], selection.area_mm2 * stiffness_factor
                )

        mass = _mass_kg(geometry, next_selections)
        unchanged = all(
            next_selections[name].designation == selections[name].designation
            for name in selections
        )
        mass_converged = last_mass > 0 and abs(mass - last_mass) / last_mass <= 0.005
        selections = next_selections
        last_mass = mass
        if maximum_deflection <= deflection_limit_mm and unchanged and mass_converged:
            converged = True
            break

    if not converged:
        raise ValueError("Section/self-weight/deflection iteration did not converge in 12 cycles.")

    final_cases = with_self_weight(
        load_bundle["cases"], geometry,
        _member_masses_for_self_weight(geometry, selections),
    )
    uls_results = _analyse_combinations(
        geometry, selections, final_cases, load_bundle["uls_combinations"],
        elastic_modulus_mpa=elastic_modulus_mpa,
    )
    sls_results = _analyse_combinations(
        geometry, selections, final_cases, load_bundle["sls_combinations"],
        elastic_modulus_mpa=elastic_modulus_mpa,
    )
    eave_column_design = design_eave_columns(
        geometry,
        uls_results,
        sls_results,
        load_bundle["uls_combinations"],
        load_bundle["sls_combinations"],
        load_bundle["eave_column_wall_actions"],
        building_layout,
        building_data,
    )
    girder_design = _design_lattice_girder(
        geometry,
        uls_results,
        sls_results,
        building_layout,
        truss_data,
        candidates,
    )
    if (
        str(building_layout.get("support_arrangement", {}).get("internal_support"))
        == "Centre columns"
        and bool(truss_data.get("design_centre_columns", False))
    ):
        if str(truss_data.get("centre_column_material", "Steel")) == "Steel":
            centre_column_design = design_centre_columns_axial(
                geometry,
                uls_results,
                load_bundle["uls_combinations"],
                building_layout,
                truss_data,
                building_data,
            )
        else:
            centre_column_design = describe_concrete_centre_columns(
                building_layout, truss_data, building_data
            )
    else:
        centre_column_design = {
            "status": "NOT_DESIGNED",
            "material": "Steel",
            "total_mass_kg": 0.0,
            "assumptions": [
                "Centre columns are idealised as supports and use the main eave-column section only as a preliminary stiffness proxy.",
            ],
        }
    support_vertical_schedule: list[dict[str, Any]] = []
    support_area_overrides: dict[str, float] = {}
    for _support_iteration in range(1, 5):
        proposed_schedule = _support_vertical_section_schedule(
            geometry,
            building_layout,
            eave_column_design,
            girder_design,
            centre_column_design,
        )
        proposed_areas = {
            item["member"]: float(item["section"]["area_mm2"])
            for item in proposed_schedule
        }
        if proposed_areas == support_area_overrides:
            break
        support_vertical_schedule = proposed_schedule
        support_area_overrides = proposed_areas
        uls_results = _analyse_combinations(
            geometry,
            selections,
            final_cases,
            load_bundle["uls_combinations"],
            elastic_modulus_mpa=elastic_modulus_mpa,
            area_overrides_mm2=support_area_overrides,
        )
        sls_results = _analyse_combinations(
            geometry,
            selections,
            final_cases,
            load_bundle["sls_combinations"],
            elastic_modulus_mpa=elastic_modulus_mpa,
            area_overrides_mm2=support_area_overrides,
        )
        eave_column_design = design_eave_columns(
            geometry,
            uls_results,
            sls_results,
            load_bundle["uls_combinations"],
            load_bundle["sls_combinations"],
            load_bundle["eave_column_wall_actions"],
            building_layout,
            building_data,
        )
        girder_design = _design_lattice_girder(
            geometry,
            uls_results,
            sls_results,
            building_layout,
            truss_data,
            candidates,
        )
        if (
            str(building_layout.get("support_arrangement", {}).get("internal_support"))
            == "Centre columns"
            and bool(truss_data.get("design_centre_columns", False))
            and str(truss_data.get("centre_column_material", "Steel")) == "Steel"
        ):
            centre_column_design = design_centre_columns_axial(
                geometry,
                uls_results,
                load_bundle["uls_combinations"],
                building_layout,
                truss_data,
                building_data,
            )
    else:
        raise ValueError("Bearing support-section iteration did not converge.")

    envelopes = _force_envelopes(geometry, uls_results)
    support_schedule_by_member = {
        item["member"]: item for item in support_vertical_schedule
    }
    member_checks = []
    for member in geometry.members:
        envelope = envelopes[member.name]
        effective_length = _effective_length_mm(
            geometry, member, restraint_layout
        )
        if member.role == "support_vertical":
            support_item = support_schedule_by_member[member.name]
            if support_item["source"] == "Longitudinal girder bearing vertical":
                support_utilisation = float(
                    girder_design["governing_strength"]["utilisation"]
                )
            elif support_item["source"] == "Designed axial centre column":
                support_utilisation = float(
                    centre_column_design["governing_strength"]["utilisation"]
                )
            else:
                support_utilisation = float(
                    eave_column_design["governing_strength"]["utilisation"]
                )
            member_checks.append({
                "member": member.name,
                "role": member.role,
                "fabrication_group": member_to_group[member.name],
                "i_node": member.i_node,
                "j_node": member.j_node,
                "length_mm": member_length_mm(geometry, member),
                "effective_length_mm": effective_length,
                "section": support_item["section"],
                "section_source": support_item["source"],
                **{
                    key: value for key, value in envelope.items()
                    if key != "forces_by_combination_kn"
                },
                "tension_utilisation": 0.0,
                "compression_utilisation": 0.0,
                "slenderness_utilisation": 0.0,
                "utilisation": support_utilisation,
                "governing_check": "supporting_column_or_girder_design",
                "design_calculation": {
                    "governing_utilisation": support_utilisation,
                    "section_source": support_item["source"],
                    "bearing_node": support_item["bearing_node"],
                },
            })
            continue
        selection = selections[member.name]
        _, check = _select_member(
            [selection],
            envelope["maximum_tension_kn"],
            envelope["maximum_compression_kn"],
            effective_length,
            0.0,
            fy_mpa=fy_mpa,
            elastic_modulus_mpa=elastic_modulus_mpa,
        )
        member_checks.append({
            "member": member.name,
            "role": member.role,
            "fabrication_group": member_to_group[member.name],
            "i_node": member.i_node,
            "j_node": member.j_node,
            "length_mm": member_length_mm(geometry, member),
            "effective_length_mm": effective_length,
            "section": asdict(selection),
            **{
                key: value for key, value in envelope.items()
                if key != "forces_by_combination_kn"
            },
            **check,
            **_check_details(selection, check),
        })

    truss_member_checks = [
        item for item in member_checks
        if item["role"] != "support_vertical"
    ]
    governing = max(
        truss_member_checks, key=lambda item: item["utilisation"]
    )
    maximum_deflection, deflection_combination, deflection_node = (
        _maximum_vertical_deflection(sls_results)
    )
    if maximum_deflection > deflection_limit_mm + 1e-9:
        raise ValueError(
            f"Final bearing-section model deflection {maximum_deflection:.1f} mm "
            f"exceeds the {deflection_limit_mm:.1f} mm limit."
        )
    unique_sections = sorted({
        selection.designation
        for member_name, selection in selections.items()
        if member_name not in support_area_overrides
    } | {
        str(item["section"]["designation"])
        for item in support_vertical_schedule
    })
    practical_member_mass_kg = _mass_kg(geometry, selections)
    individually_optimised_web_mass_kg = _individually_optimised_web_mass_kg(
        geometry,
        selections,
        candidates,
        envelopes,
        restraint_layout,
        minimum_areas,
        fy_mpa=fy_mpa,
        elastic_modulus_mpa=elastic_modulus_mpa,
    )
    reactions = {
        combination: result["reactions_kn"]
        for combination, result in uls_results.items()
    }
    sls_reactions = {
        combination: result["reactions_kn"]
        for combination, result in sls_results.items()
    }
    return {
        "status": "PASS",
        "geometry": geometry.to_dict(),
        "building_layout": building_layout,
        "chord_restraint_layout": restraint_layout,
        "mass_kg": practical_member_mass_kg,
        "individually_optimised_web_mass_kg": individually_optimised_web_mass_kg,
        "fabrication_group_mass_premium_kg": (
            practical_member_mass_kg - individually_optimised_web_mass_kg
        ),
        "unique_section_count": len(unique_sections),
        "unique_sections": unique_sections,
        "iterations": iteration,
        "member_schedule": member_checks,
        "chord_fabrication_groups": _fabrication_group_summary(member_checks),
        "web_fabrication_groups": _web_fabrication_group_summary(member_checks),
        "bearing_support_verticals": support_vertical_schedule,
        "centre_column_design": centre_column_design,
        "governing_strength": {
            "member": governing["member"],
            "role": governing["role"],
            "section": governing["section"]["designation"],
            "check": governing["governing_check"],
            "utilisation": governing["utilisation"],
            "tension_combination": governing["tension_combination"],
            "compression_combination": governing["compression_combination"],
        },
        "serviceability": {
            "limit": f"Span/{_float(truss_data.get('deflection_denominator'), 180.0):g}",
            "limit_mm": deflection_limit_mm,
            "maximum_vertical_deflection_mm": maximum_deflection,
            "governing_combination": deflection_combination,
            "governing_node": deflection_node,
            "utilisation": maximum_deflection / deflection_limit_mm,
        },
        "load_case_visualisation": _deflection_visualisation(
            geometry,
            sls_results,
            load_bundle["sls_combinations"],
            deflection_limit_mm,
        ),
        "support_reactions_uls_kn": reactions,
        "support_reactions_sls_kn": sls_reactions,
        "eave_column_design": eave_column_design,
        "girder_design": girder_design,
        "load_source": load_bundle["source"],
    }


def design_truss(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the lightest passing generic truss arrangements."""

    building_data = payload.get("building_data")
    wind_data = payload.get("wind_data")
    truss_data = payload.get("truss_data")
    if not all(isinstance(value, Mapping) for value in (building_data, wind_data, truss_data)):
        raise ValueError("Truss design requires building_data, wind_data and truss_data objects.")
    if building_data.get("building_roof") not in {"Duo Pitched", "Mono Pitched"}:
        raise ValueError("Trusses require a Duo Pitched or Mono Pitched roof.")
    if building_data.get("building_type") != "Normal":
        raise ValueError("The first truss iteration supports Normal enclosed buildings only.")

    bay_spans_mm = tuple(
        _float(value) for value in truss_data.get("transverse_bay_spans_mm", [])
    )
    if not bay_spans_mm or min(bay_spans_mm, default=0.0) <= 0:
        raise ValueError("Enter one or more positive transverse truss spans.")
    increment_mm = _float(truss_data.get("depth_increment_mm"), 200.0)
    depths = bounded_depth_candidates_mm(
        _float(truss_data.get("minimum_depth_mm"), 2000.0),
        _float(truss_data.get("maximum_depth_mm"), 4000.0),
        increment_mm,
    )
    candidates = load_angle_candidates()
    passing = []
    rejected = []
    for depth in depths:
        try:
            geometry = generate_truss_geometry(
                bay_spans_mm,
                str(building_data.get("building_roof")),
                _float(truss_data.get("roof_rise_mm"), 6000.0),
                depth,
                _float(truss_data.get("maximum_panel_width_mm"), 1700.0),
                topology=str(truss_data.get("topology", "Warren with verticals")),
                chord_form=str(truss_data.get("chord_form", "Parallel chords")),
            )
            passing.append(_design_candidate(
                geometry, building_data, wind_data, truss_data, candidates
            ))
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({"depth_mm": depth, "reason": str(exc)})

    if not passing:
        details = "; ".join(
            f"{item['depth_mm']:.0f} mm: {item['reason']}" for item in rejected
        )
        raise ValueError(f"No truss passes the entered depth limits. {details}")

    for result in passing:
        truss_count = len(result["building_layout"]["longitudinal"]["grid_labels"])
        result["truss_count"] = truss_count
        result["total_truss_mass_kg"] = result["mass_kg"] * truss_count
        result["arrangement_mass_kg"] = (
            result["total_truss_mass_kg"]
            + result["eave_column_design"]["total_mass_kg"]
            + float(result["girder_design"].get("total_mass_kg", 0.0))
            + float(result.get("centre_column_design", {}).get("total_mass_kg", 0.0))
        )
        result["lightest_member_arrangement_mass_kg"] = (
            result["individually_optimised_web_mass_kg"] * truss_count
            + result["eave_column_design"]["total_mass_kg"]
            + float(result["girder_design"].get("total_mass_kg", 0.0))
            + float(result.get("centre_column_design", {}).get("total_mass_kg", 0.0))
        )
        result["platework_cost_allowance_equivalent_kg"] = (
            PLATEWORK_COST_ALLOWANCE * result["arrangement_mass_kg"]
        )
        result["practical_cost_equivalent_kg"] = (
            result["arrangement_mass_kg"]
            + result["platework_cost_allowance_equivalent_kg"]
        )
    requested = max(1, int(_float(truss_data.get("ranked_solution_count"), 3)))
    lightest_order = sorted(
        passing,
        key=lambda item: (
            item["lightest_member_arrangement_mass_kg"],
            item["arrangement_mass_kg"],
        ),
    )
    practical_order = sorted(
        passing,
        key=lambda item: (
            item["practical_cost_equivalent_kg"],
            item["arrangement_mass_kg"],
        ),
    )
    for rank, result in enumerate(lightest_order, 1):
        result["lightest_mass_rank"] = rank
    for rank, result in enumerate(practical_order, 1):
        result["practical_rank"] = rank
        result["rank"] = rank
    ranked = practical_order[:requested]
    lightest_ranked = lightest_order[:requested]

    return {
        "engine": "preliminary_generic_truss_v0.6",
        "validation_status": "CALCULATION DRAFT - member resistance and serviceability checks complete; connection design and independent verification outstanding",
        "project": dict(payload.get("project", {})),
        "structural_system": "Truss",
        "design_basis": {
            "topology": str(truss_data.get("topology", "")),
            "roof_form": building_data.get("building_roof", ""),
            "chord_form": str(truss_data.get("chord_form", "")),
            "joint_model": "2D pinned member joints with an explicit bearing node at every transverse support; the aligned vertical uses the selected supporting column or girder section",
            "steel_grade": "S355JR",
            "fy_mpa": _float(truss_data.get("fy_mpa"), DEFAULT_FY_MPA),
            "load_standard": building_data.get("load_combination_standard", ""),
            "steel_standard": "SANS 10162 (edition not yet confirmed)",
            "depth_search": {
                "minimum_mm": _float(truss_data.get("minimum_depth_mm"), 2000.0),
                "maximum_mm": _float(truss_data.get("maximum_depth_mm"), 4000.0),
                "increment_mm": increment_mm,
            },
            "maximum_panel_width_mm": _float(
                truss_data.get("maximum_panel_width_mm"), 1700.0
            ),
            "chord_restraint_input": {
                "top_every_n_purlins": int(_float(
                    truss_data.get("top_chord_brace_every_n_purlins"), 1
                )),
                "bottom_every_n_purlins": int(_float(
                    truss_data.get("bottom_chord_brace_every_n_purlins"), 2
                )),
                "coverage": "Entire building length",
            },
            "selection_basis": "Practical cost-equivalent ranking with a separate lightest-member comparison",
            "member_selection": "One common top-chord and bottom-chord section per fabricated span; ordinary webs are grouped in at least three consecutive panels and only downsize once retained utilisation is below 75%",
            "minimum_web_group_panels": 3,
            "web_section_change_utilisation_threshold": 0.75,
            "platework_cost_allowance_fraction": PLATEWORK_COST_ALLOWANCE,
            "centre_column_design": {
                "enabled": bool(truss_data.get("design_centre_columns", False)),
                "material": str(truss_data.get("centre_column_material", "Steel")),
                "steel_section_order": str(truss_data.get("centre_column_steel_section_order", "")),
                "bracing_spacing_mm": _float(truss_data.get("centre_column_bracing_spacing_mm")),
                "loading": "Pure axial force (compression or uplift tension) from internal bearing-node reactions",
            },
            "minimum_base_angle": "50x50x5",
            "angle_configurations": ["Single equal angle", "Back-to-back equal angles"],
            "compression_slenderness_limit": COMPRESSION_SLENDERNESS_LIMIT,
            "tension_slenderness_limit": TENSION_SLENDERNESS_LIMIT,
            "resistance_model": {
                "phi": PHI,
                "buckling_exponent": BUCKLING_EXPONENT,
                "elastic_modulus_mpa": _float(
                    truss_data.get("elastic_modulus_mpa"), DEFAULT_E_MPA
                ),
            },
        },
        "ranked_solutions": ranked,
        "lightest_mass_solutions": lightest_ranked,
        "candidate_summary": {
            "attempted": len(depths),
            "passed": len(passing),
            "rejected": rejected,
        },
        "warnings": [
            "CALCULATION SCOPE: member actions, axial resistance, slenderness and vertical deflection are calculated; connection design and an independent project check remain outstanding.",
            "SANS 10160 and SANS 10162 editions must be confirmed before engineering validation.",
            "Existing PortalFrame load cases and combinations are reused; roof actions are converted to truss panel-point loads.",
            "No base angle smaller than 50x50x5 is considered so that the selected leg and thickness can accommodate the intended bolted detailing basis.",
            "Each top chord and bottom chord uses one common section within each transverse span; ordinary webs use practical groups of at least three consecutive panels and downsize only below 75% retained utilisation.",
            "The vertical aligned with every bearing is excluded from truss-angle optimisation and analysed with the selected supporting column or longitudinal-girder vertical area.",
            "Back-to-back equal angles are treated as symmetric heel-to-heel pairs with the single-angle x radius governing; no further gusset-gap benefit is used.",
            "The axial compression resistance curve is reused from the existing PortalFrame bracing implementation; angle flexural-torsional buckling is not separately benchmark-validated.",
            "Connection eccentricity, gussets, bolts, welds, bearings, splices and net-section rupture are not designed.",
            "Top- and bottom-chord restraint is assumed across the entire building at every selected Nth purlin; the purlins and restraint connections require separate verification.",
            "Global roof, vertical, chord and girder bracing members are not yet designed; calculated restraint positions are effective-length assumptions only.",
            "Crawl beams and concentrated hoist actions are excluded from the first truss iteration.",
            "Analysis is first-order linear elastic; geometric nonlinearity, erection stages and fabrication imperfections are excluded.",
            "Arrangement mass includes centre-column mass only when centre-column design is enabled and returns a calculated design; otherwise internal-column mass remains excluded and the main eave-column section is a stiffness proxy.",
            "Centre columns are checked for pure axial force only (compression or uplift tension, with no bending). Steel columns use the entered bracing spacing and section-order preference; concrete tilt-up inputs are recorded as a hold point pending a confirmed concrete design standard and reinforcement/erection basis.",
        ],
    }


def preview_truss(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return analysis-independent geometry for the middle search depth."""

    building_data = payload.get("building_data", {})
    truss_data = payload.get("truss_data", {})
    bay_spans_mm = tuple(
        _float(value) for value in truss_data.get("transverse_bay_spans_mm", [])
    )
    if not bay_spans_mm or min(bay_spans_mm, default=0.0) <= 0:
        raise ValueError("Enter one or more positive transverse truss spans.")
    depths = bounded_depth_candidates_mm(
        _float(truss_data.get("minimum_depth_mm"), 2000.0),
        _float(truss_data.get("maximum_depth_mm"), 4000.0),
        _float(truss_data.get("depth_increment_mm"), 200.0),
    )
    depth = depths[len(depths) // 2]
    geometry = generate_truss_geometry(
        bay_spans_mm,
        str(building_data.get("building_roof")),
        _float(truss_data.get("roof_rise_mm"), 6000.0),
        depth,
        _float(truss_data.get("maximum_panel_width_mm"), 1700.0),
        topology=str(truss_data.get("topology", "Warren with verticals")),
        chord_form=str(truss_data.get("chord_form", "Parallel chords")),
    )
    restraint_layout = calculate_chord_restraint_layout(
        geometry,
        _float(truss_data.get("top_chord_brace_every_n_purlins"), 1),
        _float(truss_data.get("bottom_chord_brace_every_n_purlins"), 2),
    )
    building_layout = build_truss_layout(
        building_data, truss_data, geometry, restraint_layout
    )
    girder_preview = None
    if building_layout.get("girders"):
        girder_depths = bounded_depth_candidates_mm(
            _float(truss_data.get("girder_minimum_depth_mm"), 2000.0),
            _float(truss_data.get("girder_maximum_depth_mm"), 4000.0),
            _float(truss_data.get("girder_depth_increment_mm"), 250.0),
        )
        girder_depth = girder_depths[len(girder_depths) // 2]
        girder_bays = int(_float(truss_data.get("girder_span_bays"), 2))
        span_mm = _float(truss_data.get("girder_span_mm"), 12000.0)
        panels_per_bay = max(2, math.ceil((span_mm / girder_bays) / girder_depth))
        if panels_per_bay % 2:
            panels_per_bay += 1
        girder_preview = generate_flat_lattice_girder(
            span_mm,
            girder_depth,
            girder_bays * panels_per_bay,
            topology=str(truss_data.get("topology", "Warren with verticals")),
        ).to_dict()
    return {
        "structural_system": "Truss",
        "preview_only": True,
        "provisional": True,
        "selected_preview_depth_mm": depth,
        "depth_candidates_mm": depths,
        "eaves_height_mm": _float(building_data.get("eaves_height"), 8000.0),
        "geometry": geometry.to_dict(),
        "building_layout": building_layout,
        "girder_preview": girder_preview,
        "chord_restraint_layout": restraint_layout,
        "warning": "Geometry preview only; no member adequacy or analysis result is shown.",
    }
