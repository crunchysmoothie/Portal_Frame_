"""Deterministic two-dimensional pin-jointed truss models.

The module is intentionally independent of the portal-frame finite-element
model.  Geometry is expressed in millimetres, nodal loads in kN, elastic
modulus in MPa and member areas in mm2.  Positive member force is tension.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class TrussNode:
    name: str
    x_mm: float
    y_mm: float
    role: str


@dataclass(frozen=True)
class TrussMember:
    name: str
    i_node: str
    j_node: str
    role: str


@dataclass(frozen=True)
class PrattTrussGeometry:
    span_mm: float
    depth_mm: float
    roof_rise_mm: float
    design_span_mm: float
    topology: str
    roof_form: str
    chord_form: str
    bay_spans_mm: tuple[float, ...]
    bay_panel_counts: tuple[int, ...]
    panel_count: int
    panel_width_mm: float
    nodes: tuple[TrussNode, ...]
    members: tuple[TrussMember, ...]
    top_node_names: tuple[str, ...]
    left_support: str
    right_support: str
    support_nodes: tuple[str, ...]

    @property
    def bearing_nodes(self) -> tuple[str, ...]:
        """Nodes where the truss bears on a column or longitudinal girder."""

        return self.support_nodes

    @property
    def support_vertical_members(self) -> tuple[str, ...]:
        """Verticals aligned with an external column or girder bearing."""

        return tuple(
            member.name for member in self.members
            if member.role == "support_vertical"
        )

    def to_dict(self) -> dict:
        return {
            "topology": self.topology,
            "roof_form": self.roof_form,
            "chord_form": self.chord_form,
            "span_mm": self.span_mm,
            "depth_mm": self.depth_mm,
            "roof_rise_mm": self.roof_rise_mm,
            "design_span_mm": self.design_span_mm,
            "bay_spans_mm": list(self.bay_spans_mm),
            "bay_panel_counts": list(self.bay_panel_counts),
            "panel_count": self.panel_count,
            "panel_width_mm": self.panel_width_mm,
            "left_support": self.left_support,
            "right_support": self.right_support,
            "support_nodes": list(self.support_nodes),
            "bearing_nodes": list(self.bearing_nodes),
            "support_vertical_members": list(self.support_vertical_members),
            "top_node_names": list(self.top_node_names),
            "nodes": [asdict(node) for node in self.nodes],
            "members": [asdict(member) for member in self.members],
        }


def select_even_panel_count(
    span_mm: float,
    depth_mm: float,
    maximum_panel_width_mm: float = 2100.0,
) -> int:
    """Choose a symmetric panel count close to 45-degree diagonal geometry."""

    if span_mm <= 0 or depth_mm <= 0 or maximum_panel_width_mm <= 0:
        raise ValueError("Span, depth and maximum panel width must be positive.")
    minimum = max(4, math.ceil(span_mm / maximum_panel_width_mm))
    target = max(minimum, round(span_mm / depth_mm))
    candidates = sorted({
        value
        for value in (target - 2, target - 1, target, target + 1, target + 2, minimum, minimum + 1)
        if value >= minimum and value >= 4 and value % 2 == 0
    })
    if not candidates:
        candidates = [minimum if minimum % 2 == 0 else minimum + 1]
    return min(
        candidates,
        key=lambda count: (
            abs(span_mm / count - depth_mm),
            span_mm / count > maximum_panel_width_mm,
            count,
        ),
    )


def generate_pratt_truss(
    span_mm: float,
    depth_mm: float,
    maximum_panel_width_mm: float = 2100.0,
) -> PrattTrussGeometry:
    """Generate a symmetric, statically determinate duo-pitched Pratt truss."""

    panel_count = select_even_panel_count(
        span_mm, depth_mm, maximum_panel_width_mm
    )
    panel_width = span_mm / panel_count
    if panel_width > maximum_panel_width_mm + 1e-6:
        raise ValueError("The selected panel layout exceeds the maximum panel width.")

    nodes: list[TrussNode] = [
        TrussNode(f"B{index}", index * panel_width, 0.0, "bottom_chord")
        for index in range(panel_count + 1)
    ]
    for index in range(1, panel_count):
        x = index * panel_width
        y = depth_mm * (1.0 - abs(2.0 * x / span_mm - 1.0))
        nodes.append(TrussNode(f"T{index}", x, y, "top_chord"))

    top_names = ["B0", *(f"T{index}" for index in range(1, panel_count)), f"B{panel_count}"]
    members: list[TrussMember] = []
    for index in range(panel_count):
        members.append(TrussMember(
            f"BC{index + 1}", f"B{index}", f"B{index + 1}", "bottom_chord"
        ))
        members.append(TrussMember(
            f"TC{index + 1}", top_names[index], top_names[index + 1], "top_chord"
        ))
    for index in range(1, panel_count):
        members.append(TrussMember(
            f"V{index}", f"B{index}", f"T{index}", "vertical"
        ))

    middle = panel_count // 2
    diagonal_index = 1
    for index in range(1, middle):
        members.append(TrussMember(
            f"D{diagonal_index}", f"T{index}", f"B{index + 1}", "diagonal"
        ))
        diagonal_index += 1
    for index in range(middle + 1, panel_count):
        members.append(TrussMember(
            f"D{diagonal_index}", f"T{index}", f"B{index - 1}", "diagonal"
        ))
        diagonal_index += 1

    expected = 2 * len(nodes) - 3
    if len(members) != expected:
        raise RuntimeError(
            f"Generated Pratt truss has {len(members)} members; expected {expected}."
        )
    return PrattTrussGeometry(
        span_mm=float(span_mm),
        depth_mm=float(depth_mm),
        roof_rise_mm=float(depth_mm),
        design_span_mm=float(span_mm),
        topology="Pratt",
        roof_form="Duo Pitched",
        chord_form="Horizontal bottom chord",
        bay_spans_mm=(float(span_mm),),
        bay_panel_counts=(panel_count,),
        panel_count=panel_count,
        panel_width_mm=panel_width,
        nodes=tuple(nodes),
        members=tuple(members),
        top_node_names=tuple(top_names),
        left_support="B0",
        right_support=f"B{panel_count}",
        support_nodes=("B0", f"B{panel_count}"),
    )


def generate_parallel_chord_warren_truss(
    bay_spans_mm: list[float] | tuple[float, ...],
    roof_rise_mm: float,
    depth_mm: float,
    maximum_panel_width_mm: float = 1700.0,
) -> PrattTrussGeometry:
    """Backward-compatible wrapper for the generic Warren generator."""

    return generate_truss_geometry(
        bay_spans_mm,
        "Duo Pitched",
        roof_rise_mm,
        depth_mm,
        maximum_panel_width_mm,
        topology="Warren with verticals",
        chord_form="Parallel chords",
    )


def generate_truss_geometry(
    bay_spans_mm: list[float] | tuple[float, ...],
    roof_form: str,
    roof_rise_mm: float,
    depth_mm: float,
    maximum_panel_width_mm: float = 1700.0,
    *,
    topology: str = "Warren with verticals",
    chord_form: str = "Parallel chords",
) -> PrattTrussGeometry:
    """Generate a supported mono/duo-pitched truss from engineering inputs."""

    bays = tuple(float(value) for value in bay_spans_mm)
    if len(bays) < 1 or min((*bays, roof_rise_mm, depth_mm, maximum_panel_width_mm)) <= 0:
        raise ValueError("Bay spans, roof rise, truss depth and purlin spacing must be positive.")
    if roof_form not in {"Duo Pitched", "Mono Pitched"}:
        raise ValueError("Trusses support Duo Pitched or Mono Pitched roofs.")
    if topology not in {"Warren with verticals", "Pratt", "Howe"}:
        raise ValueError("Unsupported truss topology.")
    if chord_form not in {"Parallel chords", "Horizontal bottom chord"}:
        raise ValueError("Unsupported chord form.")
    total_span = sum(bays)
    x_positions = [0.0]
    support_indices = [0]
    panel_counts: list[int] = []
    apex_x_mm = total_span / 2.0
    for span in bays:
        bay_start = x_positions[-1]
        bay_end = bay_start + span
        target_count = select_even_panel_count(
            span, depth_mm, maximum_panel_width_mm
        )
        if (
            roof_form == "Duo Pitched"
            and bay_start + 1e-6 < apex_x_mm < bay_end - 1e-6
        ):
            left_length = apex_x_mm - bay_start
            right_length = bay_end - apex_x_mm
            left_count = max(1, math.ceil(left_length / maximum_panel_width_mm))
            right_count = max(1, math.ceil(right_length / maximum_panel_width_mm))
            while left_count + right_count < target_count:
                if left_length / left_count >= right_length / right_count:
                    left_count += 1
                else:
                    right_count += 1
            if (left_count + right_count) % 2:
                if left_length / left_count >= right_length / right_count:
                    left_count += 1
                else:
                    right_count += 1
            x_positions.extend(
                bay_start + left_length * index / left_count
                for index in range(1, left_count + 1)
            )
            x_positions.extend(
                apex_x_mm + right_length * index / right_count
                for index in range(1, right_count + 1)
            )
            count = left_count + right_count
        else:
            count = target_count
            panel_width = span / count
            x_positions.extend(
                bay_start + panel_width * index
                for index in range(1, count + 1)
            )
        panel_counts.append(count)
        support_indices.append(len(x_positions) - 1)
    panel_counts_tuple = tuple(panel_counts)

    def roof_profile(x_mm: float) -> float:
        if roof_form == "Mono Pitched":
            return roof_rise_mm * x_mm / total_span
        half = total_span / 2.0
        return roof_rise_mm * (
            x_mm / half if x_mm <= half else (total_span - x_mm) / half
        )

    bottom_nodes = [
        TrussNode(
            f"B{index}", x_mm,
            roof_profile(x_mm) if chord_form == "Parallel chords" else 0.0,
            "bottom_chord",
        )
        for index, x_mm in enumerate(x_positions)
    ]
    support_index_set = set(support_indices)
    top_nodes = [
        TrussNode(
            f"T{index}",
            x_mm,
            roof_profile(x_mm) + depth_mm,
            "bearing" if index in support_index_set else "top_chord",
        )
        for index, x_mm in enumerate(x_positions)
    ]
    members: list[TrussMember] = []
    panel_count = len(x_positions) - 1
    for index in range(panel_count):
        members.append(TrussMember(
            f"BC{index + 1}", f"B{index}", f"B{index + 1}", "bottom_chord"
        ))
        members.append(TrussMember(
            f"TC{index + 1}", f"T{index}", f"T{index + 1}", "top_chord"
        ))
    for index in range(panel_count + 1):
        members.append(TrussMember(
            f"V{index + 1}",
            f"B{index}",
            f"T{index}",
            "support_vertical" if index in support_index_set else "vertical",
        ))

    global_index = 0
    diagonal_index = 1
    for bay_panel_count in panel_counts_tuple:
        for local_index in range(bay_panel_count):
            if topology == "Warren with verticals" and local_index % 2 == 0:
                i_node = f"T{global_index + local_index}"
                j_node = f"B{global_index + local_index + 1}"
            elif topology == "Warren with verticals":
                i_node = f"B{global_index + local_index}"
                j_node = f"T{global_index + local_index + 1}"
            else:
                toward_centre = local_index < bay_panel_count / 2
                if topology == "Howe":
                    toward_centre = not toward_centre
                if toward_centre:
                    i_node = f"T{global_index + local_index}"
                    j_node = f"B{global_index + local_index + 1}"
                else:
                    i_node = f"B{global_index + local_index}"
                    j_node = f"T{global_index + local_index + 1}"
            members.append(TrussMember(
                f"D{diagonal_index}", i_node, j_node, "diagonal"
            ))
            diagonal_index += 1
        global_index += bay_panel_count

    support_nodes = tuple(f"T{index}" for index in support_indices)
    return PrattTrussGeometry(
        span_mm=total_span,
        depth_mm=float(depth_mm),
        roof_rise_mm=float(roof_rise_mm),
        design_span_mm=max(bays),
        topology=topology,
        roof_form=roof_form,
        chord_form=chord_form,
        bay_spans_mm=bays,
        bay_panel_counts=panel_counts_tuple,
        panel_count=panel_count,
        panel_width_mm=max(
            x_positions[index + 1] - x_positions[index]
            for index in range(panel_count)
        ),
        nodes=tuple([*bottom_nodes, *top_nodes]),
        members=tuple(members),
        top_node_names=tuple(f"T{index}" for index in range(panel_count + 1)),
        left_support=support_nodes[0],
        right_support=support_nodes[-1],
        support_nodes=support_nodes,
    )


def generate_flat_lattice_girder(
    span_mm: float,
    depth_mm: float,
    panel_count: int,
    *,
    topology: str = "Warren with verticals",
) -> PrattTrussGeometry:
    """Generate one simply-supported flat-chord longitudinal lattice girder."""

    if min(span_mm, depth_mm) <= 0 or panel_count < 2:
        raise ValueError("Girder span, depth and panel count must be positive.")
    if topology not in {"Warren with verticals", "Pratt", "Howe"}:
        raise ValueError("Unsupported girder topology.")
    panel_width = float(span_mm) / int(panel_count)
    bottom_nodes = [
        TrussNode(f"B{index}", index * panel_width, 0.0, "bottom_chord")
        for index in range(panel_count + 1)
    ]
    top_nodes = [
        TrussNode(f"T{index}", index * panel_width, float(depth_mm), "top_chord")
        for index in range(panel_count + 1)
    ]
    members: list[TrussMember] = []
    for index in range(panel_count):
        members.extend([
            TrussMember(f"BC{index + 1}", f"B{index}", f"B{index + 1}", "bottom_chord"),
            TrussMember(f"TC{index + 1}", f"T{index}", f"T{index + 1}", "top_chord"),
        ])
    for index in range(panel_count + 1):
        members.append(TrussMember(f"V{index + 1}", f"B{index}", f"T{index}", "vertical"))
    for index in range(panel_count):
        if topology == "Warren with verticals":
            left_top = index % 2 == 0
        else:
            left_top = index < panel_count / 2
            if topology == "Howe":
                left_top = not left_top
        i_node = f"T{index}" if left_top else f"B{index}"
        j_node = f"B{index + 1}" if left_top else f"T{index + 1}"
        members.append(TrussMember(f"D{index + 1}", i_node, j_node, "diagonal"))
    return PrattTrussGeometry(
        span_mm=float(span_mm),
        depth_mm=float(depth_mm),
        roof_rise_mm=0.0,
        design_span_mm=float(span_mm),
        topology=topology,
        roof_form="Flat",
        chord_form="Parallel chords",
        bay_spans_mm=(float(span_mm),),
        bay_panel_counts=(int(panel_count),),
        panel_count=int(panel_count),
        panel_width_mm=panel_width,
        nodes=tuple([*bottom_nodes, *top_nodes]),
        members=tuple(members),
        top_node_names=tuple(f"T{index}" for index in range(panel_count + 1)),
        left_support="B0",
        right_support=f"B{panel_count}",
        support_nodes=("B0", f"B{panel_count}"),
    )


def member_length_mm(
    geometry: PrattTrussGeometry, member: TrussMember
) -> float:
    nodes = {node.name: node for node in geometry.nodes}
    i_node = nodes[member.i_node]
    j_node = nodes[member.j_node]
    return math.hypot(j_node.x_mm - i_node.x_mm, j_node.y_mm - i_node.y_mm)


def calculate_chord_restraint_layout(
    geometry: PrattTrussGeometry,
    top_every_n_purlins: int | float,
    bottom_every_n_purlins: int | float,
) -> dict:
    """Calculate full-building chord restraint at every Nth purlin line."""

    nodes = {node.name: node for node in geometry.nodes}
    def chord_layout(
        node_names: list[str], member_prefix: str, requested_interval: int | float
    ) -> dict:
        interval_value = float(requested_interval)
        if not interval_value.is_integer() or interval_value < 1:
            raise ValueError("Chord restraint intervals must be whole purlin counts.")
        interval = int(interval_value)
        indices = list(range(0, geometry.panel_count + 1, interval))
        if indices[-1] != geometry.panel_count:
            indices.append(geometry.panel_count)
        pairs = list(zip(indices, indices[1:]))
        intervals = []
        effective_lengths: dict[str, float] = {}
        for start_index, end_index in pairs:
            start = nodes[node_names[start_index]]
            end = nodes[node_names[end_index]]
            interval_length = math.hypot(
                end.x_mm - start.x_mm, end.y_mm - start.y_mm
            )
            intervals.append({
                "start_node": start.name,
                "end_node": end.name,
                "panel_spaces": end_index - start_index,
                "length_mm": interval_length,
            })
            for member_index in range(start_index, end_index):
                effective_lengths[f"{member_prefix}{member_index + 1}"] = interval_length
        restraint_names = list(dict.fromkeys(
            name
            for start_index, end_index in pairs
            for name in (node_names[start_index], node_names[end_index])
        ))
        return {
            "brace_every_n_purlins": interval,
            "coverage": "Entire building length",
            "restraint_nodes": [
                {
                    "name": name,
                    "x_mm": nodes[name].x_mm,
                    "y_mm": nodes[name].y_mm,
                }
                for name in restraint_names
            ],
            "intervals": intervals,
            "maximum_spacing_mm": max(
                interval["length_mm"] for interval in intervals
            ),
            "member_effective_lengths_mm": effective_lengths,
        }

    return {
        "basis": (
            "Chord restraint is assumed to continue over the entire building "
            "length at every selected Nth purlin line."
        ),
        "top_chord": chord_layout(
            list(geometry.top_node_names), "TC", top_every_n_purlins
        ),
        "bottom_chord": chord_layout(
            [f"B{index}" for index in range(geometry.panel_count + 1)],
            "BC",
            bottom_every_n_purlins,
        ),
    }


def analyse_truss(
    geometry: PrattTrussGeometry,
    areas_mm2: Mapping[str, float],
    node_loads_kn: Mapping[str, tuple[float, float]],
    *,
    elastic_modulus_mpa: float = 200_000.0,
) -> dict:
    """Solve one linear-elastic pin-jointed load case."""

    if elastic_modulus_mpa <= 0:
        raise ValueError("Elastic modulus must be positive.")
    nodes = {node.name: node for node in geometry.nodes}
    ordered_nodes = list(geometry.nodes)
    indices = {node.name: index for index, node in enumerate(ordered_nodes)}
    dof_count = 2 * len(ordered_nodes)
    stiffness = np.zeros((dof_count, dof_count), dtype=float)

    member_data: dict[str, tuple[float, float, float, float]] = {}
    for member in geometry.members:
        area = float(areas_mm2.get(member.name, 0.0))
        if area <= 0:
            raise ValueError(f"Member {member.name} must have a positive area.")
        i_node = nodes[member.i_node]
        j_node = nodes[member.j_node]
        dx = j_node.x_mm - i_node.x_mm
        dy = j_node.y_mm - i_node.y_mm
        length = math.hypot(dx, dy)
        if length <= 0:
            raise ValueError(f"Member {member.name} has zero length.")
        c = dx / length
        s = dy / length
        axial = area * elastic_modulus_mpa / length
        element = axial * np.array([
            [c * c, c * s, -c * c, -c * s],
            [c * s, s * s, -c * s, -s * s],
            [-c * c, -c * s, c * c, c * s],
            [-c * s, -s * s, c * s, s * s],
        ])
        dofs = [
            2 * indices[member.i_node], 2 * indices[member.i_node] + 1,
            2 * indices[member.j_node], 2 * indices[member.j_node] + 1,
        ]
        for row, global_row in enumerate(dofs):
            for column, global_column in enumerate(dofs):
                stiffness[global_row, global_column] += element[row, column]
        member_data[member.name] = (length, c, s, area)

    force = np.zeros(dof_count, dtype=float)
    for node_name, components in node_loads_kn.items():
        if node_name not in indices:
            raise ValueError(f"Load references unknown node {node_name!r}.")
        fx_kn, fy_kn = components
        force[2 * indices[node_name]] += float(fx_kn) * 1000.0
        force[2 * indices[node_name] + 1] += float(fy_kn) * 1000.0

    restrained = {2 * indices[geometry.left_support]}
    restrained.update(
        2 * indices[support] + 1 for support in geometry.support_nodes
    )
    free = [index for index in range(dof_count) if index not in restrained]
    displacement = np.zeros(dof_count, dtype=float)
    try:
        displacement[free] = np.linalg.solve(
            stiffness[np.ix_(free, free)], force[free]
        )
    except np.linalg.LinAlgError as exc:
        raise ValueError("The truss stiffness matrix is singular or unstable.") from exc

    reactions_n = stiffness @ displacement - force
    member_forces: dict[str, float] = {}
    for member in geometry.members:
        length, c, s, area = member_data[member.name]
        dofs = [
            2 * indices[member.i_node], 2 * indices[member.i_node] + 1,
            2 * indices[member.j_node], 2 * indices[member.j_node] + 1,
        ]
        extension = np.dot(np.array([-c, -s, c, s]), displacement[dofs])
        member_forces[member.name] = float(
            area * elastic_modulus_mpa / length * extension / 1000.0
        )

    return {
        "node_displacements_mm": {
            node.name: {
                "dx": float(displacement[2 * indices[node.name]]),
                "dy": float(displacement[2 * indices[node.name] + 1]),
            }
            for node in ordered_nodes
        },
        "member_forces_kn": member_forces,
        "reactions_kn": {
            support: {
                "fx": (
                    float(reactions_n[2 * indices[support]] / 1000.0)
                    if support == geometry.left_support else 0.0
                ),
                "fy": float(reactions_n[2 * indices[support] + 1] / 1000.0),
            }
            for support in geometry.support_nodes
        },
    }
