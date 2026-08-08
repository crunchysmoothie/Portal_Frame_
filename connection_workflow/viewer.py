"""In-app Plotly models for completed portal-frame connection designs.

The viewer is deliberately display-only.  It builds figures in memory from the
existing ``connection_design`` result mapping and does not expose or call any
Plotly image/file export API.
"""

from __future__ import annotations

from functools import lru_cache
from html import escape
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import plotly.graph_objects as go
import plotly.io as pio

from .haunch_geometry import haunch_cut_depth_check
from databases import load_member_database


PROJECT_ROOT = Path(__file__).resolve().parent.parent

STEEL_FLANGE = "#607D8B"
STEEL_WEB = "#78909C"
PLATE_COLOUR = "#356F78"
BOLT_COLOUR = "#A6403A"
STIFFENER_COLOUR = "#C98218"
HAUNCH_WEB_COLOUR = "#47788F"
HAUNCH_FLANGE_COLOUR = "#315A70"
EDGE_COLOUR = "#203638"

MODEBAR_EXPORT_ITEMS = (
    "toImage",
    "sendDataToCloud",
    "editInChartStudio",
)

VIEWER_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,
    "showLink": False,
}

_EPSILON = 1e-7
_Vector = tuple[float, float, float]


@lru_cache(maxsize=1)
def _member_database() -> Mapping[str, Mapping[str, Mapping[str, Any]]]:
    return load_member_database(PROJECT_ROOT / "databases" / "member_database.csv")


def _section(designation: Any) -> Mapping[str, Any] | None:
    name = str(designation or "").strip()
    for family in _member_database().values():
        if name in family:
            return family[name]
    return None


def _source_rafter_section(location: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Prefer stored design-time geometry, with the database as legacy fallback."""

    stored = location.get("source_rafter_geometry")
    if isinstance(stored, Mapping) and all(
        key in stored for key in ("h", "b", "tw", "tf")
    ):
        return {
            **stored,
            "Designation": str(location.get("rafter_section", "")),
        }
    return _section(location.get("rafter_section"))


def _connection_kind(location: Mapping[str, Any]) -> str:
    connection_type = str(
        location.get(
            "connection_type",
            location.get("connection", {}).get("connection_type", ""),
        )
    ).casefold()
    if connection_type == "apex_splice":
        return "haunch_apex"
    if connection_type == "eaves_end_plate":
        return "haunch_eaves"
    return (
        "haunch_apex"
        if "apex" in str(location.get("location", "")).casefold()
        else "haunch_eaves"
    )


def _finite_positive(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0.0 else None


def _vector_add(*vectors: _Vector) -> _Vector:
    return tuple(sum(vector[index] for vector in vectors) for index in range(3))


def _vector_scale(vector: _Vector, scale: float) -> _Vector:
    return tuple(component * scale for component in vector)


def _vector_subtract(first: _Vector, second: _Vector) -> _Vector:
    return tuple(first[index] - second[index] for index in range(3))


def _dot(first: _Vector, second: _Vector) -> float:
    return sum(first[index] * second[index] for index in range(3))


def _cross(first: _Vector, second: _Vector) -> _Vector:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _length(vector: _Vector) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalise(vector: _Vector) -> _Vector:
    magnitude = _length(vector)
    if magnitude <= _EPSILON:
        raise ValueError("A geometry direction has zero length.")
    return _vector_scale(vector, 1.0 / magnitude)


def _up_normal(axis: _Vector) -> _Vector:
    """Return the section major-depth direction, biased upward in global Z."""

    axis = _normalise(axis)
    candidate = (-axis[2], 0.0, axis[0])
    if candidate[2] < 0.0:
        candidate = _vector_scale(candidate, -1.0)
    return _normalise(candidate)


def _slug(value: Any) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return cleaned or "connection"


def _view_records(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    used_keys: set[str] = set()

    def unique_key(base: str) -> str:
        candidate = base
        suffix = 2
        while candidate in used_keys:
            candidate = f"{base}:{suffix}"
            suffix += 1
        used_keys.add(candidate)
        return candidate

    base_plates = result.get("base_plates", {})
    if isinstance(base_plates, Mapping):
        for index, support in enumerate(base_plates.get("supports", ())):
            if not isinstance(support, Mapping):
                continue
            support_name = str(support.get("support", index + 1))
            records.append(
                {
                    "key": unique_key(f"base:{_slug(support_name)}"),
                    "label": f"Base plate {support_name}",
                    "kind": "base_plate",
                    "payload": support,
                }
            )

    haunches = result.get("haunch_connections", {})
    if isinstance(haunches, Mapping):
        for index, location in enumerate(haunches.get("locations", ())):
            if not isinstance(location, Mapping):
                continue
            name = str(location.get("location", f"Haunch {index + 1}"))
            kind = _connection_kind(location)
            records.append(
                {
                    "key": unique_key(f"haunch:{_slug(name)}"),
                    "label": name,
                    "kind": kind,
                    "payload": location,
                }
            )
    return records


def _basic_availability(record: Mapping[str, Any]) -> tuple[bool, str]:
    payload = record["payload"]
    if record["kind"] == "base_plate":
        plate = payload.get("plate", {})
        section = _section(payload.get("column_section"))
        dimensions = (
            plate.get("length_mm"),
            plate.get("width_mm"),
            plate.get("provided_thickness_mm"),
        )
        if section is None:
            return False, "The column section is not available."
        if any(_finite_positive(value) is None for value in dimensions):
            return False, "The base-plate dimensions are incomplete."
        return True, ""

    connection = payload.get("connection", {})
    plate = connection.get("plate", {})
    rafter = _source_rafter_section(payload)
    if rafter is None:
        return False, "The rafter section is not available."
    if record["kind"] == "haunch_eaves" and _section(
        payload.get("column_section")
    ) is None:
        return False, "The eaves column section is not available."
    if any(
        _finite_positive(value) is None
        for value in (
            payload.get("length_mm"),
            payload.get("added_depth_mm"),
            plate.get("height_mm"),
            plate.get("width_mm"),
            plate.get("provided_thickness_mm"),
        )
    ):
        return False, "The haunch or end-plate dimensions are incomplete."
    provided_depth = float(payload["added_depth_mm"])
    cut_check = haunch_cut_depth_check(rafter, provided_depth)
    if not cut_check.is_valid:
        return (
            False,
            f"Haunch cut depth {provided_depth:.1f} mm exceeds the "
            f"source-rafter limit of {cut_check.maximum_cut_depth_mm:.1f} mm.",
        )
    return True, ""


def list_connection_views(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return stable, UI-ready descriptors for all connection views.

    Invalid or incomplete connections remain listed so the UI can select them
    and display a clean unavailable-state figure.
    """

    views = []
    for record in _view_records(result):
        available, reason = _basic_availability(record)
        views.append(
            {
                "key": record["key"],
                "label": record["label"],
                "kind": record["kind"],
                "available": available,
                "reason": reason,
            }
        )
    return views


_BOX_FACES = (
    (0, 1, 2, 3),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (1, 2, 6, 5),
    (2, 3, 7, 6),
    (3, 0, 4, 7),
)
_BOX_EDGES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)


def _add_mesh(
    figure: go.Figure,
    *,
    vertices: Sequence[_Vector],
    triangles: Sequence[tuple[int, int, int]],
    edges: Sequence[tuple[int, int]],
    name: str,
    colour: str,
    meta: Mapping[str, Any],
    opacity: float = 1.0,
) -> None:
    figure.add_trace(
        go.Mesh3d(
            x=[point[0] for point in vertices],
            y=[point[1] for point in vertices],
            z=[point[2] for point in vertices],
            i=[triangle[0] for triangle in triangles],
            j=[triangle[1] for triangle in triangles],
            k=[triangle[2] for triangle in triangles],
            color=colour,
            opacity=opacity,
            name=name,
            meta=dict(meta),
            flatshading=True,
            lighting={
                "ambient": 0.65,
                "diffuse": 0.75,
                "specular": 0.15,
                "roughness": 0.8,
            },
            hovertemplate="%{fullData.name}<extra></extra>",
            showscale=False,
            showlegend=False,
        )
    )
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    edge_z: list[float | None] = []
    for start, end in edges:
        for point in (vertices[start], vertices[end]):
            edge_x.append(point[0])
            edge_y.append(point[1])
            edge_z.append(point[2])
        edge_x.append(None)
        edge_y.append(None)
        edge_z.append(None)
    figure.add_trace(
        go.Scatter3d(
            x=edge_x,
            y=edge_y,
            z=edge_z,
            mode="lines",
            line={"color": EDGE_COLOUR, "width": 2.2},
            name=f"{name} edges",
            meta={"role": "edge", "parent_role": meta.get("role", "")},
            hoverinfo="skip",
            showlegend=False,
        )
    )


def _add_box(
    figure: go.Figure,
    *,
    centre: _Vector,
    sizes: tuple[float, float, float],
    axes: tuple[_Vector, _Vector, _Vector],
    name: str,
    colour: str,
    role: str,
    member: str = "",
    opacity: float = 1.0,
    extra_meta: Mapping[str, Any] | None = None,
) -> None:
    if any(size <= _EPSILON for size in sizes):
        return
    axis_a, axis_b, axis_c = tuple(_normalise(axis) for axis in axes)
    signs = (
        (-1, -1, -1),
        (1, -1, -1),
        (1, 1, -1),
        (-1, 1, -1),
        (-1, -1, 1),
        (1, -1, 1),
        (1, 1, 1),
        (-1, 1, 1),
    )
    vertices = []
    for sign_a, sign_b, sign_c in signs:
        vertices.append(
            _vector_add(
                centre,
                _vector_scale(axis_a, sign_a * sizes[0] / 2.0),
                _vector_scale(axis_b, sign_b * sizes[1] / 2.0),
                _vector_scale(axis_c, sign_c * sizes[2] / 2.0),
            )
        )
    triangles = [
        triangle
        for first, second, third, fourth in _BOX_FACES
        for triangle in ((first, second, third), (first, third, fourth))
    ]
    meta = {
        "role": role,
        "member": member,
        "shape": (
            "flat_rectangular_plate" if role == "stiffener" else "box"
        ),
        "dimensions_mm": list(sizes),
    }
    if extra_meta:
        meta.update(extra_meta)
    _add_mesh(
        figure,
        vertices=vertices,
        triangles=triangles,
        edges=_BOX_EDGES,
        name=name,
        colour=colour,
        meta=meta,
        opacity=opacity,
    )


def _add_cylinder(
    figure: go.Figure,
    *,
    centre: _Vector,
    axis: _Vector,
    length_mm: float,
    diameter_mm: float,
    name: str,
    role: str,
    segments: int = 18,
) -> None:
    if length_mm <= _EPSILON or diameter_mm <= _EPSILON:
        return
    axis = _normalise(axis)
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    radial_u = _normalise(_cross(axis, reference))
    radial_v = _normalise(_cross(axis, radial_u))
    half_axis = _vector_scale(axis, length_mm / 2.0)
    end_centres = (
        _vector_subtract(centre, half_axis),
        _vector_add(centre, half_axis),
    )
    radius = diameter_mm / 2.0
    vertices: list[_Vector] = []
    for end_centre in end_centres:
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            vertices.append(
                _vector_add(
                    end_centre,
                    _vector_scale(radial_u, radius * math.cos(angle)),
                    _vector_scale(radial_v, radius * math.sin(angle)),
                )
            )
    vertices.extend(end_centres)
    first_centre = 2 * segments
    second_centre = first_centre + 1
    triangles: list[tuple[int, int, int]] = []
    edges: list[tuple[int, int]] = []
    for index in range(segments):
        following = (index + 1) % segments
        triangles.extend(
            (
                (index, following, segments + following),
                (index, segments + following, segments + index),
                (first_centre, following, index),
                (
                    second_centre,
                    segments + index,
                    segments + following,
                ),
            )
        )
        edges.extend(
            (
                (index, following),
                (segments + index, segments + following),
            )
        )
        if index % max(1, segments // 4) == 0:
            edges.append((index, segments + index))
    _add_mesh(
        figure,
        vertices=vertices,
        triangles=triangles,
        edges=edges,
        name=name,
        colour=BOLT_COLOUR,
        meta={
            "role": role,
            "shape": "cylinder",
            "diameter_mm": diameter_mm,
            "length_mm": length_mm,
        },
    )


def _add_i_section(
    figure: go.Figure,
    *,
    centre: _Vector,
    axis: _Vector,
    depth_axis: _Vector,
    length_mm: float,
    section: Mapping[str, Any],
    member: str,
    label: str,
) -> None:
    width_axis = (0.0, 1.0, 0.0)
    axis = _normalise(axis)
    depth_axis = _normalise(depth_axis)
    h = float(section["h"])
    b = float(section["b"])
    tw = float(section["tw"])
    tf = float(section["tf"])
    web_depth = max(h - 2.0 * tf, 0.0)
    flange_offset = (h - tf) / 2.0
    for index, sign in enumerate((-1.0, 1.0), 1):
        _add_box(
            figure,
            centre=_vector_add(
                centre, _vector_scale(depth_axis, sign * flange_offset)
            ),
            sizes=(length_mm, b, tf),
            axes=(axis, width_axis, depth_axis),
            name=f"{label} flange {index}",
            colour=STEEL_FLANGE,
            role="section_flange",
            member=member,
            extra_meta={"section": str(section.get("Designation", ""))},
        )
    _add_box(
        figure,
        centre=centre,
        sizes=(length_mm, tw, web_depth),
        axes=(axis, width_axis, depth_axis),
        name=f"{label} web",
        colour=STEEL_WEB,
        role="section_web",
        member=member,
        extra_meta={"section": str(section.get("Designation", ""))},
    )


def _root_cut_along_mm(
    *,
    origin: _Vector,
    axis: _Vector,
    depth_axis: _Vector,
    depth_mm: float,
    root_plane_x_mm: float,
) -> float:
    """Return the local distance that places a point on a global-X plane."""

    axis_x = float(axis[0])
    if abs(axis_x) <= _EPSILON:
        raise ValueError("The member axis cannot be cut on a global-X plane.")
    return (
        root_plane_x_mm
        - float(origin[0])
        - float(depth_axis[0]) * depth_mm
    ) / axis_x


def _add_i_section_to_root_plane(
    figure: go.Figure,
    *,
    origin: _Vector,
    axis: _Vector,
    depth_axis: _Vector,
    root_plane_x_mm: float,
    length_mm: float,
    section: Mapping[str, Any],
    member: str,
    label: str,
) -> None:
    """Extrude an I-section from a vertical root cut to its remote end."""

    width_axis = (0.0, 1.0, 0.0)
    axis = _normalise(axis)
    depth_axis = _normalise(depth_axis)
    h = float(section["h"])
    b = float(section["b"])
    tw = float(section["tw"])
    tf = float(section["tf"])
    web_depth = max(h - 2.0 * tf, 0.0)
    flange_offset = (h - tf) / 2.0

    def add_component(
        *,
        depth_centre_mm: float,
        depth_size_mm: float,
        width_mm: float,
        name: str,
        colour: str,
        role: str,
    ) -> None:
        depths = (
            depth_centre_mm - depth_size_mm / 2.0,
            depth_centre_mm + depth_size_mm / 2.0,
        )
        widths = (-width_mm / 2.0, width_mm / 2.0)

        def point(along_mm: float, width: float, depth: float) -> _Vector:
            return _vector_add(
                origin,
                _vector_scale(axis, along_mm),
                _vector_scale(width_axis, width),
                _vector_scale(depth_axis, depth),
            )

        near = [
            point(
                _root_cut_along_mm(
                    origin=origin,
                    axis=axis,
                    depth_axis=depth_axis,
                    depth_mm=depth,
                    root_plane_x_mm=root_plane_x_mm,
                ),
                width,
                depth,
            )
            for depth, width in (
                (depths[0], widths[0]),
                (depths[0], widths[1]),
                (depths[1], widths[1]),
                (depths[1], widths[0]),
            )
        ]
        far = [
            point(length_mm, width, depth)
            for depth, width in (
                (depths[0], widths[0]),
                (depths[0], widths[1]),
                (depths[1], widths[1]),
                (depths[1], widths[0]),
            )
        ]
        triangles = [
            triangle
            for first, second, third, fourth in _BOX_FACES
            for triangle in ((first, second, third), (first, third, fourth))
        ]
        _add_mesh(
            figure,
            vertices=near + far,
            triangles=triangles,
            edges=_BOX_EDGES,
            name=name,
            colour=colour,
            meta={
                "role": role,
                "member": member,
                "shape": "skew_cut_prism",
                "dimensions_mm": [length_mm, width_mm, depth_size_mm],
                "section": str(section.get("Designation", "")),
                "root_plane_x_mm": root_plane_x_mm,
            },
        )

    for index, sign in enumerate((-1.0, 1.0), 1):
        add_component(
            depth_centre_mm=sign * flange_offset,
            depth_size_mm=tf,
            width_mm=b,
            name=f"{label} flange {index}",
            colour=STEEL_FLANGE,
            role="section_flange",
        )
    add_component(
        depth_centre_mm=0.0,
        depth_size_mm=web_depth,
        width_mm=tw,
        name=f"{label} web",
        colour=STEEL_WEB,
        role="section_web",
    )


def _add_triangular_web(
    figure: go.Figure,
    *,
    origin: _Vector,
    axis: _Vector,
    depth_axis: _Vector,
    length_mm: float,
    rafter_depth_mm: float,
    added_depth_mm: float,
    web_thickness_mm: float,
    flange_thickness_mm: float,
    member: str,
    root_plane_x_mm: float | None = None,
) -> None:
    web_depth = added_depth_mm - flange_thickness_mm
    if web_depth <= _EPSILON:
        return
    polygon = (
        (0.0, -rafter_depth_mm / 2.0),
        (length_mm, -rafter_depth_mm / 2.0),
        (0.0, -rafter_depth_mm / 2.0 - web_depth),
    )
    width_axis = (0.0, 1.0, 0.0)
    vertices = [
        _vector_add(
            origin,
            _vector_scale(
                axis,
                (
                    _root_cut_along_mm(
                        origin=origin,
                        axis=axis,
                        depth_axis=depth_axis,
                        depth_mm=depth,
                        root_plane_x_mm=root_plane_x_mm,
                    )
                    if root_plane_x_mm is not None
                    and abs(along) <= _EPSILON
                    else along
                ),
            ),
            _vector_scale(depth_axis, depth),
            _vector_scale(width_axis, width_sign * web_thickness_mm / 2.0),
        )
        for width_sign in (-1.0, 1.0)
        for along, depth in polygon
    ]
    triangles = (
        (0, 1, 2),
        (3, 5, 4),
        (0, 3, 4),
        (0, 4, 1),
        (1, 4, 5),
        (1, 5, 2),
        (2, 5, 3),
        (2, 3, 0),
    )
    edges = (
        (0, 1),
        (1, 2),
        (2, 0),
        (3, 4),
        (4, 5),
        (5, 3),
        (0, 3),
        (1, 4),
        (2, 5),
    )
    _add_mesh(
        figure,
        vertices=vertices,
        triangles=triangles,
        edges=edges,
        name=f"{member.title()} tapered web",
        colour=HAUNCH_WEB_COLOUR,
        meta={
            "role": "haunch_web",
            "member": member,
            "shape": "tapered_web_plate",
            "thickness_mm": web_thickness_mm,
        },
    )


def _add_haunch_donor(
    figure: go.Figure,
    *,
    origin: _Vector,
    axis: _Vector,
    depth_axis: _Vector,
    length_mm: float,
    added_depth_mm: float,
    section: Mapping[str, Any],
    member: str,
    root_plane_x_mm: float | None = None,
) -> None:
    """Add the donor web and bottom flange; intentionally no donor top flange."""

    h = float(section["h"])
    b = float(section["b"])
    tw = float(section["tw"])
    tf = float(section["tf"])
    _add_triangular_web(
        figure,
        origin=origin,
        axis=axis,
        depth_axis=depth_axis,
        length_mm=length_mm,
        rafter_depth_mm=h,
        added_depth_mm=added_depth_mm,
        web_thickness_mm=tw,
        flange_thickness_mm=tf,
        member=member,
        root_plane_x_mm=root_plane_x_mm,
    )
    root_depth = -h / 2.0 - added_depth_mm + tf / 2.0
    root_along = (
        _root_cut_along_mm(
            origin=origin,
            axis=axis,
            depth_axis=depth_axis,
            depth_mm=root_depth,
            root_plane_x_mm=root_plane_x_mm,
        )
        if root_plane_x_mm is not None
        else 0.0
    )
    root_centre = _vector_add(
        origin,
        _vector_scale(axis, root_along),
        _vector_scale(depth_axis, root_depth),
    )
    toe_centre = _vector_add(
        origin,
        _vector_scale(axis, length_mm),
        _vector_scale(depth_axis, -h / 2.0 - tf / 2.0),
    )
    flange_vector = _vector_subtract(toe_centre, root_centre)
    flange_axis = _normalise(flange_vector)
    width_axis = (0.0, 1.0, 0.0)
    flange_depth_axis = _normalise(_cross(width_axis, flange_axis))
    _add_box(
        figure,
        centre=_vector_scale(_vector_add(root_centre, toe_centre), 0.5),
        sizes=(_length(flange_vector), b, tf),
        axes=(flange_axis, width_axis, flange_depth_axis),
        name=f"{member.title()} bottom flange",
        colour=HAUNCH_FLANGE_COLOUR,
        role="haunch_bottom_flange",
        member=member,
        extra_meta={"donor_top_flange": False},
    )


def _add_base_stiffeners(
    figure: go.Figure,
    *,
    stiffener: Mapping[str, Any],
    section: Mapping[str, Any],
    plate_thickness_mm: float,
) -> None:
    if not stiffener.get("required"):
        return
    count = max(int(stiffener.get("count", 0)), 0)
    height = _finite_positive(stiffener.get("height_mm"))
    plate_length = _finite_positive(stiffener.get("length_mm"))
    thickness = _finite_positive(stiffener.get("provided_thickness_mm"))
    if not count or height is None or plate_length is None or thickness is None:
        return
    column_h = float(section["h"])
    column_b = float(section["b"])
    positions = (
        (-1.0, -1.0),
        (-1.0, 1.0),
        (1.0, -1.0),
        (1.0, 1.0),
    )
    for index in range(count):
        direction, side = positions[index % len(positions)]
        _add_box(
            figure,
            centre=(
                direction * (column_h / 2.0 + plate_length / 2.0),
                side * column_b / 4.0,
                plate_thickness_mm / 2.0 + height / 2.0,
            ),
            sizes=(plate_length, thickness, height),
            axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            name=f"Base stiffener {index + 1}",
            colour=STIFFENER_COLOUR,
            role="stiffener",
            member="base",
        )


def _add_joint_stiffeners(
    figure: go.Figure,
    *,
    stiffener: Mapping[str, Any],
    plate_width_mm: float,
    plate_height_mm: float,
    apex: bool,
    column_centre_x: float = 0.0,
    column_section: Mapping[str, Any] | None = None,
    apex_levels_mm: tuple[float, float] | None = None,
    apex_level_source: str = "",
) -> None:
    if not stiffener.get("required"):
        return
    count = max(int(stiffener.get("count", 0)), 0)
    height = _finite_positive(stiffener.get("height_mm"))
    plate_length = _finite_positive(stiffener.get("length_mm"))
    thickness = _finite_positive(stiffener.get("provided_thickness_mm"))
    if not count or height is None or plate_length is None or thickness is None:
        return
    if apex:
        if apex_levels_mm is None:
            return
        for index in range(count):
            level = apex_levels_mm[index % len(apex_levels_mm)]
            centre = (0.0, 0.0, level)
            _add_box(
                figure,
                centre=centre,
                sizes=(plate_length, min(height, plate_width_mm), thickness),
                axes=(
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                ),
                name=f"Apex stiffener {index + 1}",
                colour=STIFFENER_COLOUR,
                role="stiffener",
                member="apex",
                extra_meta={
                    "orientation": "transverse",
                    "centre_mm": list(centre),
                    "level_mm": level,
                    "level_source": apex_level_source,
                },
            )
        return
    if column_section is None:
        return
    column_depth = float(column_section["h"])
    column_width = float(column_section["b"])
    column_flange_thickness = float(column_section["tf"])
    clear_between_flanges = max(
        column_depth - 2.0 * column_flange_thickness,
        0.0,
    )
    if clear_between_flanges <= _EPSILON:
        return
    levels = (
        -min(plate_height_mm * 0.32, height),
        min(plate_height_mm * 0.32, height),
    )
    for index in range(count):
        level = levels[index % len(levels)]
        _add_box(
            figure,
            centre=(column_centre_x, 0.0, level),
            sizes=(clear_between_flanges, column_width, thickness),
            axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            name=f"Eaves stiffener {index + 1}",
            colour=STIFFENER_COLOUR,
            role="stiffener",
            member="eaves",
            extra_meta={
                "orientation": "transverse",
                "spans_between_column_flanges": True,
                "clear_depth_mm": clear_between_flanges,
                "column_width_mm": column_width,
            },
        )


def _apex_stiffener_levels(
    bolts: Mapping[str, Any],
    *,
    rafter: Mapping[str, Any],
    added_depth_mm: float,
) -> tuple[tuple[float, float], str]:
    """Return lower/upper transverse-stiffener levels at the apex.

    Explicit calculated bolt centres are authoritative.  Legacy results may
    only contain the row count and pitch, so those values are used next.  A
    final geometry-only fallback follows the main-rafter top-flange and donor
    bottom-flange centrelines rather than inventing a plate at joint mid-depth.
    """

    coordinates = bolts.get("coordinates_from_plate_centre_mm", ())
    explicit_levels: list[float] = []
    if isinstance(coordinates, Sequence) and not isinstance(
        coordinates, (str, bytes)
    ):
        for point in coordinates:
            if not isinstance(point, Mapping):
                continue
            try:
                level = float(point["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(level):
                explicit_levels.append(level)
    if explicit_levels and min(explicit_levels) < max(explicit_levels):
        return (
            (min(explicit_levels), max(explicit_levels)),
            "calculated_outer_bolt_rows",
        )

    try:
        row_count = max(int(bolts.get("row_count", 0)), 0)
    except (TypeError, ValueError):
        row_count = 0
    pitch = _finite_positive(bolts.get("pitch_mm"))
    if row_count >= 2 and pitch is not None:
        outer_level = pitch * (row_count - 1) / 2.0
        return (
            (-outer_level, outer_level),
            "calculated_outer_bolt_rows",
        )

    section_depth = float(rafter["h"])
    flange_thickness = float(rafter["tf"])
    upper_flange_level = (section_depth - flange_thickness) / 2.0
    lower_flange_level = (
        -section_depth / 2.0
        - added_depth_mm
        + flange_thickness / 2.0
    )
    return (
        (lower_flange_level, upper_flange_level),
        "calculated_flange_centrelines",
    )


def _pitch_degrees(
    result: Mapping[str, Any], location: Mapping[str, Any]
) -> float:
    project = result.get("project", {})
    candidates: Iterable[Any] = (
        location.get("roof_pitch_deg"),
        project.get("roof_pitch_deg") if isinstance(project, Mapping) else None,
        result.get("roof_pitch_deg"),
        8.0,
    )
    for candidate in candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return max(0.0, min(abs(value), 30.0))
    return 8.0


def _apply_layout(
    figure: go.Figure,
    *,
    placeholder_reason: str = "",
) -> go.Figure:
    metadata: dict[str, Any] = {
        "connection_viewer": {
            "display_only": True,
            "three_dimensional_export": False,
            "placeholder": bool(placeholder_reason),
        }
    }
    if placeholder_reason:
        metadata["connection_viewer"]["reason"] = placeholder_reason
    figure.update_layout(
        title=(
            {
                "text": "3D connection preview unavailable",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 17, "color": "#526562"},
            }
            if placeholder_reason
            else None
        ),
        paper_bgcolor="#F7FAF9",
        plot_bgcolor="#F7FAF9",
        margin={"l": 0, "r": 0, "t": 42 if placeholder_reason else 8, "b": 0},
        showlegend=False,
        hovermode="closest",
        dragmode="orbit",
        modebar={"remove": list(MODEBAR_EXPORT_ITEMS)},
        meta=metadata,
        scene={
            "aspectmode": "data",
            "xaxis": {
                "visible": False,
                "showbackground": False,
                "showgrid": False,
                "zeroline": False,
            },
            "yaxis": {
                "visible": False,
                "showbackground": False,
                "showgrid": False,
                "zeroline": False,
            },
            "zaxis": {
                "visible": False,
                "showbackground": False,
                "showgrid": False,
                "zeroline": False,
            },
            "camera": {
                "projection": {"type": "orthographic"},
                "eye": {"x": 1.65, "y": 1.45, "z": 1.15},
                "up": {"x": 0.0, "y": 0.0, "z": 1.0},
            },
            "bgcolor": "#F7FAF9",
            "annotations": [],
        },
    )
    return figure


def _placeholder(reason: str) -> go.Figure:
    return _apply_layout(go.Figure(), placeholder_reason=reason)


def build_connection_viewer_html(
    result: Mapping[str, Any],
    view_key: str,
) -> str:
    """Return one self-contained in-memory page for the app's WebView.

    This is a runtime UI payload, not an artifact or an export. The Plotly
    bundle is embedded so the local viewer remains interactive offline.
    """

    figure = build_connection_figure(result, view_key)
    html = pio.to_html(
        figure,
        include_plotlyjs=True,
        full_html=True,
        config=dict(VIEWER_CONFIG),
        default_width="100%",
        default_height="100%",
        auto_play=False,
    )
    views = list_connection_views(result)
    options = "".join(
        (
            f'<option value="{escape(str(view["key"]), quote=True)}"'
            f'{" selected" if str(view["key"]) == str(view_key) else ""}'
            f'{" disabled" if not view["available"] else ""}>'
            f'{escape(str(view["label"]))}</option>'
        )
        for view in views
    )
    toolbar = (
        '<div class="connection-viewer-toolbar">'
        '<label for="connection-view-select">Connection to inspect</label>'
        f'<select id="connection-view-select">{options}</select>'
        "</div>"
    )
    navigation_script = (
        "<script>"
        "document.getElementById('connection-view-select')"
        ".addEventListener('change',function(){"
        "const next=new URL(window.location.href);"
        "next.searchParams.set('view',this.value);"
        "window.location.assign(next.toString());"
        "});"
        "</script>"
    )
    html = html.replace("<body>", f"<body>{toolbar}", 1)
    html = html.replace("</body>", f"{navigation_script}</body>", 1)
    return html.replace(
        "</head>",
        (
            "<style>"
            "html,body{width:100%;height:100%;margin:0;overflow:hidden;"
            "background:#F7FAF9}"
            "body{display:flex;flex-direction:column;"
            "font-family:Arial,sans-serif;color:#18302F}"
            ".connection-viewer-toolbar{box-sizing:border-box;display:flex;"
            "align-items:center;gap:12px;flex:0 0 auto;padding:10px 12px;"
            "background:#FFFFFF;border-bottom:1px solid #D7E1DF}"
            ".connection-viewer-toolbar label{font-size:13px;font-weight:600;"
            "white-space:nowrap}"
            ".connection-viewer-toolbar select{box-sizing:border-box;"
            "min-width:230px;max-width:420px;height:38px;padding:0 34px 0 10px;"
            "border:1px solid #93AAA7;border-radius:6px;background:#FFFFFF;"
            "color:#18302F;font-size:14px}"
            "body>div:not(.connection-viewer-toolbar){width:100%!important;"
            "height:auto!important;min-height:0;flex:1 1 auto}"
            ".plotly-graph-div,.plot-container,.svg-container{width:100%!important;"
            "height:100%!important}"
            "</style></head>"
        ),
        1,
    )


def _base_plate_figure(support: Mapping[str, Any]) -> go.Figure:
    plate = support["plate"]
    section = _section(support.get("column_section"))
    if section is None:
        return _placeholder("The selected column section is unavailable.")
    plate_length = float(plate["length_mm"])
    plate_width = float(plate["width_mm"])
    plate_thickness = float(plate["provided_thickness_mm"])
    figure = go.Figure()
    _add_box(
        figure,
        centre=(0.0, 0.0, 0.0),
        sizes=(plate_length, plate_width, plate_thickness),
        axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        name="Base plate",
        colour=PLATE_COLOUR,
        role="base_plate",
        member="base",
    )
    column_length = max(700.0, 2.25 * float(section["h"]))
    _add_i_section(
        figure,
        centre=(0.0, 0.0, plate_thickness / 2.0 + column_length / 2.0),
        axis=(0.0, 0.0, 1.0),
        depth_axis=(1.0, 0.0, 0.0),
        length_mm=column_length,
        section=section,
        member="column",
        label="Column",
    )
    layout = support.get("holding_down_bolts", {}).get("layout", {})
    bolt_diameter = _finite_positive(layout.get("diameter_mm"))
    if bolt_diameter is not None:
        anchor_length = max(140.0, 7.0 * bolt_diameter)
        for index, point in enumerate(
            layout.get("coordinates_from_plate_centre_mm", ()), 1
        ):
            try:
                x_value = float(point["x"])
                y_value = float(point["y"])
            except (KeyError, TypeError, ValueError):
                continue
            _add_cylinder(
                figure,
                centre=(
                    x_value,
                    y_value,
                    plate_thickness / 2.0 - anchor_length / 2.0,
                ),
                axis=(0.0, 0.0, 1.0),
                length_mm=anchor_length,
                diameter_mm=bolt_diameter,
                name=f"Anchor {index}",
                role="anchor",
            )
    _add_base_stiffeners(
        figure,
        stiffener=support.get("stiffeners", {}),
        section=section,
        plate_thickness_mm=plate_thickness,
    )
    return _apply_layout(figure)


def _haunch_bolts(
    figure: go.Figure,
    *,
    bolts: Mapping[str, Any],
    plate_thickness_mm: float,
    origin: _Vector = (0.0, 0.0, 0.0),
    axis: _Vector = (1.0, 0.0, 0.0),
    vertical_axis: _Vector = (0.0, 0.0, 1.0),
) -> None:
    row_count = max(int(bolts.get("row_count", 0)), 0)
    pitch = _finite_positive(bolts.get("pitch_mm"))
    gauge = _finite_positive(bolts.get("gauge_mm"))
    diameter = _finite_positive(bolts.get("diameter_mm"))
    if not row_count or pitch is None or gauge is None or diameter is None:
        return
    bolt_length = max(plate_thickness_mm + 55.0, 3.0 * diameter)
    coordinates = bolts.get("coordinates_from_plate_centre_mm", ())
    if not isinstance(coordinates, Sequence) or len(coordinates) != row_count * 2:
        first_z = -pitch * (row_count - 1) / 2.0
        coordinates = [
            {"x": side * gauge / 2.0, "y": first_z + row * pitch}
            for row in range(row_count)
            for side in (-1.0, 1.0)
        ]
    for index, point in enumerate(coordinates, 1):
        try:
            transverse = float(point["x"])
            vertical = float(point["y"])
        except (KeyError, TypeError, ValueError):
            continue
        _add_cylinder(
            figure,
            centre=_vector_add(
                origin,
                _vector_scale((0.0, 1.0, 0.0), transverse),
                _vector_scale(vertical_axis, vertical),
            ),
            axis=axis,
            length_mm=bolt_length,
            diameter_mm=diameter,
            name=f"Connection bolt {index}",
            role="bolt",
        )


def _eaves_figure(
    result: Mapping[str, Any],
    location: Mapping[str, Any],
) -> go.Figure:
    connection = location["connection"]
    plate = connection["plate"]
    rafter = _source_rafter_section(location)
    column = _section(location.get("column_section"))
    if rafter is None or column is None:
        return _placeholder("The eaves member section geometry is unavailable.")
    plate_h = float(plate["height_mm"])
    plate_w = float(plate["width_mm"])
    plate_t = float(plate["provided_thickness_mm"])
    haunch_length = float(location["length_mm"])
    added_depth = float(location["added_depth_mm"])
    pitch = math.radians(_pitch_degrees(result, location))
    rafter_axis = (math.cos(pitch), 0.0, math.sin(pitch))
    rafter_depth_axis = _up_normal(rafter_axis)
    plate_centre = (0.0, 0.0, -added_depth / 2.0)
    column_face_x = -plate_t / 2.0
    rafter_root_x = plate_t / 2.0
    rafter_origin = (rafter_root_x, 0.0, 0.0)
    rafter_length = max(900.0, haunch_length * 1.18)
    figure = go.Figure()
    _add_box(
        figure,
        centre=plate_centre,
        sizes=(plate_t, plate_w, plate_h),
        axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        name="Eaves end plate",
        colour=PLATE_COLOUR,
        role="end_plate",
        member="eaves",
    )
    column_centre_x = column_face_x - float(column["h"]) / 2.0
    column_length = max(
        1050.0,
        plate_h * 1.55,
        float(rafter["h"]) + 2.0 * added_depth,
    )
    plate_top_z = plate_centre[2] + plate_h / 2.0
    column_centre_z = plate_top_z + 50.0 - column_length / 2.0
    _add_i_section(
        figure,
        centre=(column_centre_x, 0.0, column_centre_z),
        axis=(0.0, 0.0, 1.0),
        depth_axis=(1.0, 0.0, 0.0),
        length_mm=column_length,
        section=column,
        member="column",
        label="Column",
    )
    _add_i_section_to_root_plane(
        figure,
        origin=rafter_origin,
        axis=rafter_axis,
        depth_axis=rafter_depth_axis,
        root_plane_x_mm=rafter_root_x,
        length_mm=rafter_length,
        section=rafter,
        member="rafter",
        label="Rafter",
    )
    _add_haunch_donor(
        figure,
        origin=rafter_origin,
        axis=rafter_axis,
        depth_axis=rafter_depth_axis,
        length_mm=min(haunch_length, rafter_length),
        added_depth_mm=added_depth,
        section=rafter,
        member="eaves haunch",
        root_plane_x_mm=rafter_root_x,
    )
    _haunch_bolts(
        figure,
        bolts=connection.get("bolts", {}),
        plate_thickness_mm=plate_t,
        origin=plate_centre,
        axis=(1.0, 0.0, 0.0),
        vertical_axis=(0.0, 0.0, 1.0),
    )
    _add_joint_stiffeners(
        figure,
        stiffener=connection.get("stiffeners", {}),
        plate_width_mm=plate_w,
        plate_height_mm=plate_h,
        apex=False,
        column_centre_x=column_centre_x,
        column_section=column,
    )
    return _apply_layout(figure)


def _apex_figure(
    result: Mapping[str, Any],
    location: Mapping[str, Any],
) -> go.Figure:
    connection = location["connection"]
    plate = connection["plate"]
    rafter = _source_rafter_section(location)
    if rafter is None:
        return _placeholder("The apex rafter section geometry is unavailable.")
    plate_h = float(plate["height_mm"])
    plate_w = float(plate["width_mm"])
    plate_t = float(plate["provided_thickness_mm"])
    haunch_length = float(location["length_mm"])
    added_depth = float(location["added_depth_mm"])
    pitch = math.radians(_pitch_degrees(result, location))
    outward_axes = (
        (-math.cos(pitch), 0.0, -math.sin(pitch)),
        (math.cos(pitch), 0.0, -math.sin(pitch)),
    )
    rafter_length = max(900.0, haunch_length * 1.18)
    figure = go.Figure()
    _add_box(
        figure,
        centre=(0.0, 0.0, 0.0),
        sizes=(plate_t, plate_w, plate_h),
        axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        name="Apex end plate",
        colour=PLATE_COLOUR,
        role="end_plate",
        member="apex",
    )
    for side_index, axis in enumerate(outward_axes, 1):
        depth_axis = _up_normal(axis)
        origin = _vector_scale(axis, plate_t / 2.0)
        member_name = f"apex rafter {side_index}"
        _add_i_section(
            figure,
            centre=_vector_add(
                origin, _vector_scale(axis, rafter_length / 2.0)
            ),
            axis=axis,
            depth_axis=depth_axis,
            length_mm=rafter_length,
            section=rafter,
            member=member_name,
            label=f"Apex rafter {side_index}",
        )
        _add_haunch_donor(
            figure,
            origin=origin,
            axis=axis,
            depth_axis=depth_axis,
            length_mm=min(haunch_length, rafter_length),
            added_depth_mm=added_depth,
            section=rafter,
            member=f"apex haunch {side_index}",
        )
    _haunch_bolts(
        figure,
        bolts=connection.get("bolts", {}),
        plate_thickness_mm=plate_t,
    )
    apex_levels, apex_level_source = _apex_stiffener_levels(
        connection.get("bolts", {}),
        rafter=rafter,
        added_depth_mm=added_depth,
    )
    _add_joint_stiffeners(
        figure,
        stiffener=connection.get("stiffeners", {}),
        plate_width_mm=plate_w,
        plate_height_mm=plate_h,
        apex=True,
        apex_levels_mm=apex_levels,
        apex_level_source=apex_level_source,
    )
    return _apply_layout(figure)


def build_connection_figure(
    result: Mapping[str, Any],
    view_key: str,
) -> go.Figure:
    """Build one display-only connection figure.

    Unknown, incomplete, or physically invalid geometry returns an empty,
    consistently styled placeholder rather than raising into the application.
    """

    record = next(
        (
            candidate
            for candidate in _view_records(result)
            if candidate["key"] == str(view_key)
        ),
        None,
    )
    if record is None:
        return _placeholder("The requested connection view does not exist.")
    available, reason = _basic_availability(record)
    if not available:
        return _placeholder(reason)
    try:
        if record["kind"] == "base_plate":
            return _base_plate_figure(record["payload"])
        if record["kind"] == "haunch_apex":
            return _apex_figure(result, record["payload"])
        return _eaves_figure(result, record["payload"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return _placeholder(f"The connection geometry is incomplete: {exc}")
