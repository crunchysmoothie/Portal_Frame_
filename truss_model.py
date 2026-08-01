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


WARREN_NO_VERTICALS = "Warren - no verticals"
WARREN_INTERMEDIATE_VERTICALS = "Warren - verticals at intermediate purlins"
WARREN_ALL_VERTICALS = "Warren - all verticals"
WARREN_TOPOLOGIES = (
    WARREN_NO_VERTICALS,
    WARREN_INTERMEDIATE_VERTICALS,
    WARREN_ALL_VERTICALS,
)


def normalise_truss_topology(topology: str) -> str:
    """Return the current topology name while accepting old saved projects."""

    value = str(topology).strip()
    if value == "Warren with verticals":
        return WARREN_ALL_VERTICALS
    return value


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
        topology=WARREN_ALL_VERTICALS,
        chord_form="Parallel chords",
    )


def generate_truss_geometry(
    bay_spans_mm: list[float] | tuple[float, ...],
    roof_form: str,
    roof_rise_mm: float,
    depth_mm: float,
    maximum_panel_width_mm: float = 1700.0,
    *,
    topology: str = WARREN_ALL_VERTICALS,
    chord_form: str = "Parallel chords",
) -> PrattTrussGeometry:
    """Generate a supported mono/duo-pitched truss from engineering inputs."""

    bays = tuple(float(value) for value in bay_spans_mm)
    if len(bays) < 1 or min((*bays, roof_rise_mm, depth_mm, maximum_panel_width_mm)) <= 0:
        raise ValueError("Bay spans, roof rise, truss depth and purlin spacing must be positive.")
    if roof_form not in {"Duo Pitched", "Mono Pitched"}:
        raise ValueError("Trusses support Duo Pitched or Mono Pitched roofs.")
    topology = normalise_truss_topology(topology)
    if topology not in {*WARREN_TOPOLOGIES, "Pratt", "Howe"}:
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
        selection_width = (
            maximum_panel_width_mm / 2.0
            if topology == WARREN_NO_VERTICALS
            else maximum_panel_width_mm
        )
        target_count = select_even_panel_count(
            span, depth_mm, selection_width
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
            if topology == WARREN_NO_VERTICALS:
                if left_count % 2:
                    left_count += 1
                if right_count % 2:
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

    support_index_set = set(support_indices)
    panel_count = len(x_positions) - 1
    if topology in {
        WARREN_NO_VERTICALS,
        WARREN_INTERMEDIATE_VERTICALS,
    }:
        (
            top_nodes,
            bottom_nodes,
            members,
            top_node_names,
        ) = _generate_classic_warren_members(
            x_positions=x_positions,
            support_indices=support_indices,
            panel_counts=panel_counts_tuple,
            roof_profile=roof_profile,
            depth_mm=depth_mm,
            chord_form=chord_form,
            intermediate_verticals=(
                topology == WARREN_INTERMEDIATE_VERTICALS
            ),
        )
    else:
        bottom_nodes = [
            TrussNode(
                f"B{index}", x_mm,
                roof_profile(x_mm) if chord_form == "Parallel chords" else 0.0,
                "bottom_chord",
            )
            for index, x_mm in enumerate(x_positions)
        ]
        top_nodes = [
            TrussNode(
                f"T{index}",
                x_mm,
                roof_profile(x_mm) + depth_mm,
                "bearing" if index in support_index_set else "top_chord",
            )
            for index, x_mm in enumerate(x_positions)
        ]
        members = []
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
                if topology == WARREN_ALL_VERTICALS and local_index % 2 == 0:
                    i_node = f"T{global_index + local_index}"
                    j_node = f"B{global_index + local_index + 1}"
                elif topology == WARREN_ALL_VERTICALS:
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
        top_node_names = tuple(f"T{index}" for index in range(panel_count + 1))

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
        top_node_names=tuple(top_node_names),
        left_support=support_nodes[0],
        right_support=support_nodes[-1],
        support_nodes=support_nodes,
    )


def _generate_classic_warren_members(
    *,
    x_positions: list[float],
    support_indices: list[int],
    panel_counts: tuple[int, ...],
    roof_profile,
    depth_mm: float,
    chord_form: str,
    intermediate_verticals: bool,
) -> tuple[
    list[TrussNode],
    list[TrussNode],
    list[TrussMember],
    tuple[str, ...],
]:
    """Generate stable, triangular Warren panels with optional load verticals.

    Diagonal intersection points occur at alternate top and bottom nodes.  The
    intermediate-vertical version adds a top-chord purlin point halfway
    between diagonal intersections and connects it to the bottom node below.
    """

    top_indices: set[int] = set(support_indices)
    # The bottom chord physically terminates at every bearing line.  These
    # nodes lie on the supporting column/girder line and are connected to the
    # top bearing node by a dedicated support vertical.
    bottom_indices: set[int] = set(support_indices)
    members: list[TrussMember] = []
    tc_index = bc_index = vertical_index = diagonal_index = 1
    start = 0
    for count in panel_counts:
        if count % 2:
            raise ValueError("Classic Warren layouts require an even panel count.")
        even_indices = list(range(start, start + count + 1, 2))
        odd_indices = list(range(start + 1, start + count, 2))
        top_indices.update(even_indices)
        bottom_indices.update(odd_indices)

        if intermediate_verticals:
            top_indices.update(odd_indices)
            for left, right in zip(range(start, start + count), range(start + 1, start + count + 1)):
                members.append(TrussMember(
                    f"TC{tc_index}", f"T{left}", f"T{right}", "top_chord"
                ))
                tc_index += 1
        else:
            for left, right in zip(even_indices, even_indices[1:]):
                members.append(TrussMember(
                    f"TC{tc_index}", f"T{left}", f"T{right}", "top_chord"
                ))
                tc_index += 1

        bottom_sequence = [start, *odd_indices, start + count]
        for left, right in zip(bottom_sequence, bottom_sequence[1:]):
            members.append(TrussMember(
                f"BC{bc_index}", f"B{left}", f"B{right}", "bottom_chord"
            ))
            bc_index += 1

        for index in odd_indices:
            members.extend([
                TrussMember(
                    f"D{diagonal_index}", f"T{index - 1}", f"B{index}", "diagonal"
                ),
                TrussMember(
                    f"D{diagonal_index + 1}", f"B{index}", f"T{index + 1}", "diagonal"
                ),
            ])
            diagonal_index += 2
            if intermediate_verticals:
                members.append(TrussMember(
                    f"V{vertical_index}", f"B{index}", f"T{index}", "vertical"
                ))
                vertical_index += 1
        start += count

    for support_number, index in enumerate(support_indices, 1):
        members.append(TrussMember(
            f"SV{support_number}",
            f"B{index}",
            f"T{index}",
            "support_vertical",
        ))

    support_set = set(support_indices)
    top_nodes = [
        TrussNode(
            f"T{index}",
            x_positions[index],
            roof_profile(x_positions[index]) + depth_mm,
            "bearing" if index in support_set else "top_chord",
        )
        for index in sorted(top_indices)
    ]
    bottom_nodes = [
        TrussNode(
            f"B{index}",
            x_positions[index],
            (
                roof_profile(x_positions[index])
                if chord_form == "Parallel chords"
                else 0.0
            ),
            "bottom_chord",
        )
        for index in sorted(bottom_indices)
    ]
    return (
        top_nodes,
        bottom_nodes,
        members,
        tuple(f"T{index}" for index in sorted(top_indices)),
    )


def generate_flat_lattice_girder(
    span_mm: float,
    depth_mm: float,
    panel_count: int,
    *,
    topology: str = WARREN_ALL_VERTICALS,
) -> PrattTrussGeometry:
    """Generate one simply-supported flat-chord longitudinal lattice girder."""

    if min(span_mm, depth_mm) <= 0 or panel_count < 2:
        raise ValueError("Girder span, depth and panel count must be positive.")
    topology = normalise_truss_topology(topology)
    if topology in {WARREN_NO_VERTICALS, WARREN_INTERMEDIATE_VERTICALS}:
        topology = WARREN_ALL_VERTICALS
    if topology not in {WARREN_ALL_VERTICALS, "Pratt", "Howe"}:
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
        if topology == WARREN_ALL_VERTICALS:
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
    def chord_layout(role: str, requested_interval: int | float) -> dict:
        interval_value = float(requested_interval)
        if not interval_value.is_integer() or interval_value < 1:
            raise ValueError("Chord restraint intervals must be whole purlin counts.")
        interval = int(interval_value)
        chord_members = [
            member for member in geometry.members if member.role == role
        ]
        if not chord_members:
            return {
                "brace_every_n_purlins": interval,
                "coverage": "Entire building length",
                "restraint_nodes": [],
                "intervals": [],
                "maximum_spacing_mm": 0.0,
                "member_effective_lengths_mm": {},
            }

        adjacency: dict[str, set[str]] = {}
        member_by_pair: dict[frozenset[str], TrussMember] = {}
        for member in chord_members:
            adjacency.setdefault(member.i_node, set()).add(member.j_node)
            adjacency.setdefault(member.j_node, set()).add(member.i_node)
            member_by_pair[frozenset((member.i_node, member.j_node))] = member

        components: list[list[str]] = []
        remaining = set(adjacency)
        while remaining:
            stack = [remaining.pop()]
            component: set[str] = set()
            while stack:
                name = stack.pop()
                if name in component:
                    continue
                component.add(name)
                for adjacent in adjacency.get(name, ()):
                    if adjacent not in component:
                        remaining.discard(adjacent)
                        stack.append(adjacent)
            components.append(sorted(
                component, key=lambda name: (nodes[name].x_mm, nodes[name].y_mm)
            ))

        intervals = []
        effective_lengths: dict[str, float] = {}
        restraint_names: list[str] = []
        for node_names in components:
            indices = list(range(0, len(node_names), interval))
            if indices[-1] != len(node_names) - 1:
                indices.append(len(node_names) - 1)
            for start_index, end_index in zip(indices, indices[1:]):
                selected_names = node_names[start_index:end_index + 1]
                path_members = [
                    member_by_pair[frozenset((left, right))]
                    for left, right in zip(selected_names, selected_names[1:])
                ]
                interval_length = sum(
                    member_length_mm(geometry, member)
                    for member in path_members
                )
                intervals.append({
                    "start_node": selected_names[0],
                    "end_node": selected_names[-1],
                    "panel_spaces": len(path_members),
                    "length_mm": interval_length,
                })
                for member in path_members:
                    effective_lengths[member.name] = interval_length
                restraint_names.extend((selected_names[0], selected_names[-1]))
        return {
            "brace_every_n_purlins": interval,
            "coverage": "Entire building length",
            "restraint_nodes": [
                {
                    "name": name,
                    "x_mm": nodes[name].x_mm,
                    "y_mm": nodes[name].y_mm,
                }
                for name in dict.fromkeys(restraint_names)
            ],
            "intervals": intervals,
            "maximum_spacing_mm": max(
                (item["length_mm"] for item in intervals), default=0.0
            ),
            "member_effective_lengths_mm": effective_lengths,
        }

    return {
        "basis": (
            "Chord restraint is assumed to continue over the entire building "
            "length at every selected Nth purlin line."
        ),
        "top_chord": chord_layout("top_chord", top_every_n_purlins),
        "bottom_chord": chord_layout(
            "bottom_chord", bottom_every_n_purlins
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
