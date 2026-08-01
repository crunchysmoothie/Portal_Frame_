"""Canonical 2D connection drawings with PDF, DXF and optional DWG output.

The module deliberately keeps one page-coordinate primitive model as the source
for every 2D output.  ReportLab and ezdxf are renderers only; neither renderer
reconstructs connection geometry independently.

All sheet coordinates and engineering dimensions are millimetres.  Drawings
are calculation-review markups and intentionally omit utilisation and design
status text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
from typing import Any, Iterable, Mapping, Sequence

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas as reportlab_canvas

from haunch_geometry import haunch_cut_depth_check, haunch_cut_error
from member_database import load_member_database


A3_WIDTH_MM = 420.0
A3_HEIGHT_MM = 297.0
MM_TO_PT = 72.0 / 25.4
PROJECT_ROOT = Path(__file__).resolve().parent
DWG_CONVERTER_CANDIDATES = (
    Path(r"C:\Program Files\Autodesk\AutoCAD LT 2027\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2026\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2023\accoreconsole.exe"),
)


def _select_dwg_converter(
    candidates: Sequence[Path] = DWG_CONVERTER_CANDIDATES,
) -> Path:
    """Select the newest supported installed AutoCAD Core Console."""

    return next((path for path in candidates if path.is_file()), candidates[0])


DWG_CONVERTER = _select_dwg_converter()

DXF_LAYERS = (
    "OBJECT",
    "HIDDEN",
    "CENTRE",
    "BOLTS",
    "WELDS",
    "DIMS",
    "TEXT",
    "HATCH",
    "BORDER",
)

_LAYER_COLOURS = {
    "OBJECT": 7,
    "HIDDEN": 8,
    "CENTRE": 4,
    "BOLTS": 2,
    "WELDS": 1,
    "DIMS": 5,
    "TEXT": 7,
    "HATCH": 8,
    "BORDER": 7,
}

_PDF_COLOURS = {
    "OBJECT": (0.08, 0.12, 0.12),
    "HIDDEN": (0.42, 0.48, 0.47),
    "CENTRE": (0.20, 0.45, 0.55),
    "BOLTS": (0.10, 0.20, 0.20),
    "WELDS": (0.65, 0.12, 0.10),
    "DIMS": (0.08, 0.25, 0.76),
    "TEXT": (0.08, 0.12, 0.12),
    "HATCH": (0.45, 0.50, 0.49),
    "BORDER": (0.04, 0.07, 0.07),
}


class ConnectionDrawingError(ValueError):
    """Raised when calculated connection geometry cannot form a valid sheet."""


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height

    def inset(self, amount: float) -> "Rect":
        return Rect(
            self.x + amount,
            self.y + amount,
            max(0.0, self.width - 2.0 * amount),
            max(0.0, self.height - 2.0 * amount),
        )

    def contains(self, other: "Rect", tolerance: float = 1e-6) -> bool:
        return (
            other.x >= self.x - tolerance
            and other.y >= self.y - tolerance
            and other.right <= self.right + tolerance
            and other.top <= self.top + tolerance
        )

    def intersects(self, other: "Rect", gap: float = 0.0) -> bool:
        return not (
            self.right + gap <= other.x
            or other.right + gap <= self.x
            or self.top + gap <= other.y
            or other.top + gap <= self.y
        )


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str = "OBJECT"
    width_mm: float = 0.25
    dashed: bool = False
    pdf_only: bool = False


@dataclass(frozen=True)
class Polyline:
    points: tuple[tuple[float, float], ...]
    layer: str = "OBJECT"
    width_mm: float = 0.30
    closed: bool = False
    dashed: bool = False


@dataclass(frozen=True)
class Circle:
    x: float
    y: float
    radius: float
    layer: str = "BOLTS"
    width_mm: float = 0.25


@dataclass(frozen=True)
class Text:
    x: float
    y: float
    value: str
    height_mm: float = 3.0
    layer: str = "TEXT"
    max_width_mm: float | None = None
    bold: bool = False
    align: str = "left"
    collision: bool = True
    allowed_zone: str | None = None
    pdf_only: bool = False

    def lines(self) -> tuple[str, ...]:
        if "\n" in self.value:
            raw = self.value.splitlines()
        else:
            raw = [self.value]
        if not self.max_width_mm:
            return tuple(raw)
        # Helvetica's average engineering-uppercase glyph is about 0.56h.
        characters = max(8, int(self.max_width_mm / (0.56 * self.height_mm)))
        wrapped: list[str] = []
        for line in raw:
            wrapped.extend(
                textwrap.wrap(
                    line,
                    width=characters,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                or [""]
            )
        return tuple(wrapped)

    def bounds(self) -> Rect:
        lines = self.lines()
        width = max(
            (
                min(
                    len(line) * self.height_mm * 0.56,
                    self.max_width_mm or math.inf,
                )
                for line in lines
            ),
            default=0.0,
        )
        line_height = self.height_mm * 1.32
        height = max(line_height, len(lines) * line_height)
        if self.align == "center":
            x = self.x - width / 2.0
        elif self.align == "right":
            x = self.x - width
        else:
            x = self.x
        return Rect(x, self.y - self.height_mm * 0.25, width, height)


@dataclass(frozen=True)
class LinearDimension:
    p1: tuple[float, float]
    p2: tuple[float, float]
    base: tuple[float, float]
    angle: float
    text: str
    layer: str = "DIMS"


Primitive = Line | Polyline | Circle | Text | LinearDimension


@dataclass
class ConnectionSheet:
    sheet_id: str
    layout_name: str
    title: str
    subtitle: str
    primitives: list[Primitive] = field(default_factory=list)
    zones: dict[str, Rect] = field(default_factory=dict)
    object_bounds: list[Rect] = field(default_factory=list)

    def add(self, *items: Primitive) -> None:
        self.primitives.extend(items)

    def validate_collisions(self) -> None:
        """Validate deterministic text placement and drawing-sheet boundaries."""

        page = Rect(8.0, 8.0, A3_WIDTH_MM - 16.0, A3_HEIGHT_MM - 16.0)
        labelled: list[tuple[Text, Rect]] = []
        for primitive in self.primitives:
            if not isinstance(primitive, Text) or not primitive.collision:
                continue
            bounds = primitive.bounds()
            if not page.contains(bounds, tolerance=0.4):
                raise ConnectionDrawingError(
                    f"{self.sheet_id}: text outside A3 border: {primitive.value!r}."
                )
            if primitive.allowed_zone:
                zone = self.zones.get(primitive.allowed_zone)
                if zone is None or not zone.contains(bounds, tolerance=0.4):
                    raise ConnectionDrawingError(
                        f"{self.sheet_id}: text {primitive.value!r} leaves "
                        f"reserved zone {primitive.allowed_zone!r}."
                    )
            labelled.append((primitive, bounds))

        for index, (left_text, left) in enumerate(labelled):
            for right_text, right in labelled[index + 1 :]:
                if left.intersects(right, gap=0.35):
                    raise ConnectionDrawingError(
                        f"{self.sheet_id}: overlapping text boxes: "
                        f"{left_text.value!r} and {right_text.value!r}."
                    )

        dimension_texts = [
            primitive
            for primitive in self.primitives
            if isinstance(primitive, Text) and primitive.layer == "DIMS"
        ]
        for text_item in dimension_texts:
            bounds = text_item.bounds()
            for object_box in self.object_bounds:
                if bounds.intersects(object_box, gap=0.5):
                    raise ConnectionDrawingError(
                        f"{self.sheet_id}: dimension text overlaps an object: "
                        f"{text_item.value!r}."
                    )
        callout_texts = [
            primitive
            for primitive in self.primitives
            if isinstance(primitive, Text)
            and primitive.layer == "TEXT"
            and primitive.collision
        ]
        for text_item in callout_texts:
            bounds = text_item.bounds()
            for object_box in self.object_bounds:
                if bounds.intersects(object_box, gap=0.35):
                    raise ConnectionDrawingError(
                        f"{self.sheet_id}: callout text overlaps an object: "
                        f"{text_item.value!r}."
                    )


@dataclass(frozen=True)
class _ViewTransform:
    source: Rect
    target: Rect
    scale: float
    offset_x: float
    offset_y: float

    @classmethod
    def fit(cls, source: Rect, target: Rect) -> "_ViewTransform":
        if source.width <= 0 or source.height <= 0:
            raise ConnectionDrawingError("View source geometry must have positive size.")
        scale = min(target.width / source.width, target.height / source.height)
        drawn_w = source.width * scale
        drawn_h = source.height * scale
        offset_x = target.x + (target.width - drawn_w) / 2.0 - source.x * scale
        offset_y = target.y + (target.height - drawn_h) / 2.0 - source.y * scale
        return cls(source, target, scale, offset_x, offset_y)

    def point(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.offset_x + x * self.scale,
            self.offset_y + y * self.scale,
        )

    def rect(self, rect: Rect) -> Rect:
        x, y = self.point(rect.x, rect.y)
        return Rect(x, y, rect.width * self.scale, rect.height * self.scale)


def _number(value: Any, name: str, *, positive: bool = True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConnectionDrawingError(f"{name} must be numeric.") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = "positive and finite" if positive else "finite"
        raise ConnectionDrawingError(f"{name} must be {qualifier}.")
    return number


def _integer(value: Any, name: str, *, minimum: int = 1) -> int:
    number = _number(value, name)
    integer = int(round(number))
    if abs(number - integer) > 1e-6 or integer < minimum:
        raise ConnectionDrawingError(f"{name} must be an integer >= {minimum}.")
    return integer


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConnectionDrawingError(f"{name} is missing or invalid.")
    return value


def _section(designation: str) -> Mapping[str, Any]:
    database = load_member_database(PROJECT_ROOT / "member_database.csv")
    for sections in database.values():
        if designation in sections:
            section = sections[designation]
            for key in ("h", "b", "tw", "tf"):
                _number(section.get(key), f"section {designation} {key}")
            return section
    raise ConnectionDrawingError(
        f"Section {designation!r} is not present in member_database.csv."
    )


def _safe_layout_name(prefix: str, value: str, used: set[str]) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    base = f"{prefix}_{cleaned or 'CONNECTION'}"[:31]
    name = base
    counter = 2
    while name.casefold() in used:
        suffix = f"_{counter}"
        name = f"{base[:31-len(suffix)]}{suffix}"
        counter += 1
    used.add(name.casefold())
    return name


def _fmt(value: float) -> str:
    rounded = round(value)
    return f"{rounded:d}" if abs(value - rounded) < 0.05 else f"{value:.1f}"


def _line_box(points: Sequence[tuple[float, float]]) -> Rect:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _add_sheet_frame(sheet: ConnectionSheet) -> None:
    sheet.add(
        Polyline(
            ((8, 8), (412, 8), (412, 289), (8, 289)),
            layer="BORDER",
            width_mm=0.55,
            closed=True,
        ),
        Line(8, 274, 412, 274, layer="BORDER", width_mm=0.45),
        Text(
            14,
            279,
            sheet.title,
            height_mm=5.1,
            bold=True,
            collision=False,
        ),
        Text(
            408,
            280,
            sheet.sheet_id,
            height_mm=2.8,
            align="right",
            collision=False,
        ),
        Text(
            14,
            275.2,
            sheet.subtitle,
            height_mm=2.5,
            collision=False,
        ),
        Text(
            408,
            275.2,
            "A3 LANDSCAPE - ALL DIMENSIONS mm - DO NOT SCALE",
            height_mm=2.4,
            align="right",
            collision=False,
        ),
    )


def _add_zone_title(
    sheet: ConnectionSheet,
    zone: Rect,
    title: str,
    *,
    zone_name: str,
) -> None:
    sheet.add(
        Line(
            zone.x,
            zone.top - 7.0,
            zone.right,
            zone.top - 7.0,
            layer="BORDER",
            width_mm=0.2,
        ),
        Text(
            zone.x + 2.0,
            zone.top - 5.0,
            title,
            height_mm=3.1,
            bold=True,
            allowed_zone=zone_name,
        ),
    )


def _add_horizontal_dimension(
    sheet: ConnectionSheet,
    x1: float,
    x2: float,
    object_y: float,
    dim_y: float,
    label: str,
    *,
    allowed_zone: str,
) -> None:
    tick = 1.25
    sheet.add(
        Line(x1, object_y, x1, dim_y, layer="DIMS", width_mm=0.15, pdf_only=True),
        Line(x2, object_y, x2, dim_y, layer="DIMS", width_mm=0.15, pdf_only=True),
        Line(x1, dim_y, x2, dim_y, layer="DIMS", width_mm=0.20, pdf_only=True),
        Line(
            x1 - tick,
            dim_y - tick,
            x1 + tick,
            dim_y + tick,
            layer="DIMS",
            pdf_only=True,
        ),
        Line(
            x2 - tick,
            dim_y - tick,
            x2 + tick,
            dim_y + tick,
            layer="DIMS",
            pdf_only=True,
        ),
        Text(
            (x1 + x2) / 2.0,
            dim_y + 1.4,
            label,
            height_mm=2.5,
            layer="DIMS",
            align="center",
            allowed_zone=allowed_zone,
            pdf_only=True,
        ),
        LinearDimension(
            p1=(x1, object_y),
            p2=(x2, object_y),
            base=(x1, dim_y),
            angle=0.0,
            text=label,
        ),
    )


def _add_vertical_dimension(
    sheet: ConnectionSheet,
    y1: float,
    y2: float,
    object_x: float,
    dim_x: float,
    label: str,
    *,
    allowed_zone: str,
) -> None:
    tick = 1.25
    sheet.add(
        Line(object_x, y1, dim_x, y1, layer="DIMS", width_mm=0.15, pdf_only=True),
        Line(object_x, y2, dim_x, y2, layer="DIMS", width_mm=0.15, pdf_only=True),
        Line(dim_x, y1, dim_x, y2, layer="DIMS", width_mm=0.20, pdf_only=True),
        Line(
            dim_x - tick,
            y1 - tick,
            dim_x + tick,
            y1 + tick,
            layer="DIMS",
            pdf_only=True,
        ),
        Line(
            dim_x - tick,
            y2 - tick,
            dim_x + tick,
            y2 + tick,
            layer="DIMS",
            pdf_only=True,
        ),
        Text(
            dim_x + 1.8,
            (y1 + y2) / 2.0,
            label,
            height_mm=2.5,
            layer="DIMS",
            allowed_zone=allowed_zone,
            pdf_only=True,
        ),
        LinearDimension(
            p1=(object_x, y1),
            p2=(object_x, y2),
            base=(dim_x, y1),
            angle=90.0,
            text=label,
        ),
    )


def _bolt_row_positions(
    data: Mapping[str, Any],
    *,
    plate_bottom: float,
    plate_top: float,
) -> list[float]:
    """Project the calculated end distance and pitch onto a drawn plate."""

    scale = (plate_top - plate_bottom) / float(data["plate_height"])
    return [
        plate_bottom
        + (float(data["end"]) + row * float(data["pitch"])) * scale
        for row in range(int(data["rows"]))
    ]


def _add_bolt_row_dimensions(
    sheet: ConnectionSheet,
    data: Mapping[str, Any],
    *,
    plate_bottom: float,
    plate_top: float,
    row_positions: Sequence[float],
    object_x: float,
    dim_x: float,
    allowed_zone: str,
) -> None:
    """Dimension both end distances and every individual bolt-row pitch."""

    if not row_positions:
        return
    _add_vertical_dimension(
        sheet,
        plate_bottom,
        row_positions[0],
        object_x,
        dim_x,
        _fmt(float(data["end"])),
        allowed_zone=allowed_zone,
    )
    for lower, upper in zip(row_positions, row_positions[1:]):
        _add_vertical_dimension(
            sheet,
            lower,
            upper,
            object_x,
            dim_x,
            _fmt(float(data["pitch"])),
            allowed_zone=allowed_zone,
        )
    _add_vertical_dimension(
        sheet,
        row_positions[-1],
        plate_top,
        object_x,
        dim_x,
        _fmt(float(data["end"])),
        allowed_zone=allowed_zone,
    )


def _add_leader(
    sheet: ConnectionSheet,
    target: tuple[float, float],
    elbow: tuple[float, float],
    text_origin: tuple[float, float],
    text: str,
    *,
    allowed_zone: str,
    max_width_mm: float,
    attach: str = "left",
) -> None:
    tx, ty = text_origin
    text_item = Text(
        tx,
        ty,
        text,
        height_mm=2.5,
        max_width_mm=max_width_mm,
        allowed_zone=allowed_zone,
    )
    if attach == "left":
        leader_end = (text_item.bounds().x - 1.5, ty + 1.0)
    elif attach == "right":
        leader_end = (text_item.bounds().right + 1.5, ty + 1.0)
    else:
        raise ConnectionDrawingError(f"Unsupported leader attachment {attach!r}.")
    sheet.add(
        Polyline(
            (target, elbow, leader_end),
            layer="TEXT",
            width_mm=0.18,
        ),
        text_item,
    )


def _add_hatch_rect(sheet: ConnectionSheet, rect: Rect, spacing: float = 3.2) -> None:
    # Clipped 45-degree hatch represented by deterministic line segments.
    start = rect.x - rect.height
    value = start
    while value <= rect.right:
        x1 = max(rect.x, value)
        y1 = rect.y + max(0.0, rect.x - value)
        x2 = min(rect.right, value + rect.height)
        y2 = rect.y + min(rect.height, rect.right - value)
        if x2 > x1 + 1e-6:
            sheet.add(Line(x1, y1, x2, y2, layer="HATCH", width_mm=0.10))
        value += spacing


def _add_crosshair(sheet: ConnectionSheet, x: float, y: float, radius: float) -> None:
    sheet.add(
        Circle(x, y, radius, layer="BOLTS"),
        Line(x - radius * 1.6, y, x + radius * 1.6, y, layer="CENTRE"),
        Line(x, y - radius * 1.6, x, y + radius * 1.6, layer="CENTRE"),
    )


def _add_rect_outline(
    sheet: ConnectionSheet,
    rect: Rect,
    *,
    layer: str = "OBJECT",
    width_mm: float = 0.30,
) -> None:
    sheet.add(
        Polyline(
            (
                (rect.x, rect.y),
                (rect.right, rect.y),
                (rect.right, rect.top),
                (rect.x, rect.top),
            ),
            closed=True,
            layer=layer,
            width_mm=width_mm,
        )
    )


def _i_profile_points(section: Mapping[str, Any]) -> tuple[tuple[float, float], ...]:
    h = float(section["h"])
    b = float(section["b"])
    tw = float(section["tw"])
    tf = float(section["tf"])
    return (
        (-h / 2, -b / 2),
        (-h / 2 + tf, -b / 2),
        (-h / 2 + tf, -tw / 2),
        (h / 2 - tf, -tw / 2),
        (h / 2 - tf, -b / 2),
        (h / 2, -b / 2),
        (h / 2, b / 2),
        (h / 2 - tf, b / 2),
        (h / 2 - tf, tw / 2),
        (-h / 2 + tf, tw / 2),
        (-h / 2 + tf, b / 2),
        (-h / 2, b / 2),
    )


def _validate_base_support(support: Mapping[str, Any]) -> dict[str, Any]:
    name = str(support.get("support", "")).strip()
    if not name:
        raise ConnectionDrawingError("Base-plate support name is missing.")
    plate = _mapping(support.get("plate"), f"base plate {name}")
    length = _number(plate.get("length_mm"), f"base plate {name} length")
    width = _number(plate.get("width_mm"), f"base plate {name} width")
    thickness = _number(
        plate.get("provided_thickness_mm"), f"base plate {name} thickness"
    )
    holding = _mapping(
        support.get("holding_down_bolts"), f"base plate {name} holding-down bolts"
    )
    anchorage = _mapping(
        holding.get("anchorage_estimate"),
        f"base plate {name} Red Book anchorage estimate",
    )
    layout = _mapping(holding.get("layout"), f"base plate {name} bolt layout")
    diameter = _number(layout.get("diameter_mm"), f"base plate {name} bolt diameter")
    hole = _number(layout.get("hole_diameter_mm"), f"base plate {name} hole diameter")
    end = _number(layout.get("end_distance_mm"), f"base plate {name} end distance")
    edge = _number(layout.get("edge_distance_mm"), f"base plate {name} edge distance")
    pitch = _number(layout.get("pitch_mm"), f"base plate {name} pitch")
    gauge = _number(layout.get("gauge_mm"), f"base plate {name} gauge")
    count = _integer(layout.get("bolt_count"), f"base plate {name} bolt count")
    if count != 4:
        raise ConnectionDrawingError(
            f"Base plate {name} requires a four-bolt calculated layout."
        )
    if abs(2.0 * end + pitch - length) > 1.0:
        raise ConnectionDrawingError(
            f"Base plate {name} bolt end-distance chain does not equal plate length."
        )
    if abs(2.0 * edge + gauge - width) > 1.0:
        raise ConnectionDrawingError(
            f"Base plate {name} bolt edge-distance chain does not equal plate width."
        )
    points = layout.get("coordinates_from_plate_centre_mm")
    if not isinstance(points, Sequence) or len(points) != 4:
        raise ConnectionDrawingError(
            f"Base plate {name} requires four explicit bolt-centre coordinates."
        )
    coordinates = []
    for index, point in enumerate(points, start=1):
        item = _mapping(point, f"base plate {name} bolt {index}")
        coordinates.append(
            (
                _number(item.get("x"), f"base plate {name} bolt {index} x", positive=False),
                _number(item.get("y"), f"base plate {name} bolt {index} y", positive=False),
            )
        )
    column_name = str(support.get("column_section", "")).strip()
    column = _section(column_name)
    stiffener = support.get("stiffeners", {})
    if stiffener and not isinstance(stiffener, Mapping):
        raise ConnectionDrawingError(f"Base plate {name} stiffener data is invalid.")
    if stiffener.get("required"):
        for key in ("height_mm", "length_mm", "provided_thickness_mm"):
            _number(stiffener.get(key), f"base plate {name} stiffener {key}")
    return {
        "name": name,
        "plate": plate,
        "length": length,
        "width": width,
        "thickness": thickness,
        "holding": holding,
        "anchorage": anchorage,
        "layout": layout,
        "diameter": diameter,
        "hole": hole,
        "end": end,
        "edge": edge,
        "pitch": pitch,
        "gauge": gauge,
        "coordinates": coordinates,
        "column_name": column_name,
        "column": column,
        "stiffener": stiffener,
    }


def _validate_haunch_location(location: Mapping[str, Any]) -> dict[str, Any]:
    connection_value = location.get("connection", {})
    nested_type = (
        connection_value.get("connection_type", "")
        if isinstance(connection_value, Mapping)
        else ""
    )
    connection_type = str(
        location.get("connection_type", nested_type)
    ).strip()
    name = str(location.get("location", "")).strip()
    if connection_type not in {"eaves_end_plate", "apex_splice"}:
        connection_type = {
            "Eaves haunch": "eaves_end_plate",
            "Apex haunch": "apex_splice",
        }.get(name, "")
    if connection_type not in {"eaves_end_plate", "apex_splice"}:
        raise ConnectionDrawingError(
            f"Unsupported haunch connection location {name!r}."
        )
    name = (
        "Apex haunch"
        if connection_type == "apex_splice"
        else "Eaves haunch"
    )
    connection = _mapping(location.get("connection"), f"{name} connection")
    plate = _mapping(connection.get("plate"), f"{name} end plate")
    bolts = _mapping(connection.get("bolts"), f"{name} bolts")
    plate_height = _number(plate.get("height_mm"), f"{name} plate height")
    plate_width = _number(plate.get("width_mm"), f"{name} plate width")
    plate_thickness = _number(
        plate.get("provided_thickness_mm"), f"{name} plate thickness"
    )
    rows = _integer(bolts.get("row_count"), f"{name} bolt row count", minimum=2)
    columns = _integer(bolts.get("columns"), f"{name} bolt columns")
    if columns != 2:
        raise ConnectionDrawingError(f"{name} requires a two-column bolt layout.")
    count = _integer(bolts.get("bolt_count"), f"{name} bolt count")
    if count != rows * columns:
        raise ConnectionDrawingError(f"{name} bolt count does not match its grid.")
    diameter = _number(bolts.get("diameter_mm"), f"{name} bolt diameter")
    hole = _number(bolts.get("hole_diameter_mm"), f"{name} hole diameter")
    edge = _number(bolts.get("edge_distance_mm"), f"{name} edge distance")
    end = _number(bolts.get("end_distance_mm"), f"{name} end distance")
    pitch = _number(bolts.get("pitch_mm"), f"{name} pitch")
    gauge = _number(bolts.get("gauge_mm"), f"{name} gauge")
    if abs(2.0 * edge + gauge - plate_width) > 1.0:
        raise ConnectionDrawingError(
            f"{name} bolt edge-distance chain does not equal plate width."
        )
    if abs(2.0 * end + (rows - 1) * pitch - plate_height) > 1.0:
        raise ConnectionDrawingError(
            f"{name} bolt end/pitch chain does not equal plate height."
        )
    length = _number(location.get("length_mm"), f"{name} haunch length")
    depth = _number(location.get("added_depth_mm"), f"{name} depth")
    rafter_name = str(location.get("rafter_section", "")).strip()
    stored_rafter = location.get("source_rafter_geometry")
    if isinstance(stored_rafter, Mapping) and all(
        key in stored_rafter for key in ("h", "b", "tw", "tf")
    ):
        rafter = {
            **stored_rafter,
            "Designation": rafter_name,
        }
    else:
        rafter = _section(rafter_name)
    cut_check = haunch_cut_depth_check(rafter, depth)
    if not cut_check.is_valid:
        raise ConnectionDrawingError(
            haunch_cut_error(rafter_name, cut_check)
        )
    column_name = str(location.get("column_section", "")).strip()
    column = (
        _section(column_name)
        if connection_type == "eaves_end_plate"
        else None
    )
    stiffener = connection.get("stiffeners", {})
    if stiffener and not isinstance(stiffener, Mapping):
        raise ConnectionDrawingError(f"{name} stiffener data is invalid.")
    if stiffener.get("required"):
        for key in ("height_mm", "length_mm", "provided_thickness_mm"):
            _number(stiffener.get(key), f"{name} stiffener {key}")
        _integer(stiffener.get("count"), f"{name} stiffener count")
        if not str(stiffener.get("position", "")).strip():
            raise ConnectionDrawingError(
                f"{name} stiffener position must be provided."
            )
    return {
        "name": name,
        "connection_type": connection_type,
        "connection": connection,
        "plate": plate,
        "bolts": bolts,
        "plate_height": plate_height,
        "plate_width": plate_width,
        "plate_thickness": plate_thickness,
        "rows": rows,
        "count": count,
        "diameter": diameter,
        "hole": hole,
        "edge": edge,
        "end": end,
        "pitch": pitch,
        "gauge": gauge,
        "length": length,
        "depth": depth,
        "cut_check": cut_check,
        "rafter_name": rafter_name,
        "rafter": rafter,
        "column_name": column_name,
        "column": column,
        "stiffener": stiffener,
    }


def _build_base_sheet(
    support: Mapping[str, Any],
    layout_name: str,
) -> ConnectionSheet:
    data = _validate_base_support(support)
    name = data["name"]
    sheet = ConnectionSheet(
        sheet_id=f"BP-{name}",
        layout_name=layout_name,
        title=f"BASE PLATE {name} - PLAN, SECTION AND COMPONENT DETAIL",
        subtitle=(
            f"COLUMN {data['column_name']} | "
            f"PLATE {_fmt(data['length'])} x {_fmt(data['width'])} x "
            f"{_fmt(data['thickness'])}"
        ),
    )
    sheet.zones = {
        "plan": Rect(14, 91, 185, 177),
        "section": Rect(207, 91, 199, 177),
        "detail": Rect(14, 14, 185, 68),
        "notes": Rect(207, 14, 199, 68),
    }
    _add_sheet_frame(sheet)
    _add_zone_title(sheet, sheet.zones["plan"], "PLAN OF BASE PLATE", zone_name="plan")
    _add_zone_title(sheet, sheet.zones["section"], "SECTION A-A", zone_name="section")
    _add_zone_title(
        sheet,
        sheet.zones["detail"],
        "FLAT BASE-STIFFENER DETAIL",
        zone_name="detail",
    )
    _add_zone_title(sheet, sheet.zones["notes"], "FABRICATION NOTES", zone_name="notes")

    # Plan geometry is scaled from the actual calculated plate and section.
    plan_object = Rect(
        -data["length"] / 2.0,
        -data["width"] / 2.0,
        data["length"],
        data["width"],
    )
    plan_target = Rect(36, 129, 112, 103)
    plan_transform = _ViewTransform.fit(plan_object, plan_target)
    plate_draw = plan_transform.rect(plan_object)
    sheet.add(
        Polyline(
            (
                (plate_draw.x, plate_draw.y),
                (plate_draw.right, plate_draw.y),
                (plate_draw.right, plate_draw.top),
                (plate_draw.x, plate_draw.top),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.40,
        )
    )
    profile_points = tuple(
        plan_transform.point(x, y)
        for x, y in _i_profile_points(data["column"])
    )
    sheet.add(Polyline(profile_points, closed=True, layer="OBJECT", width_mm=0.33))
    cx, cy = plan_transform.point(0.0, 0.0)
    sheet.add(
        Line(cx, plate_draw.y - 4, cx, plate_draw.top + 4, layer="CENTRE", dashed=True),
        Line(plate_draw.x - 4, cy, plate_draw.right + 4, cy, layer="CENTRE", dashed=True),
    )
    bolt_draw_points = [
        plan_transform.point(x, y) for x, y in data["coordinates"]
    ]
    bolt_radius = max(1.5, data["hole"] * plan_transform.scale / 2.0)
    for x, y in bolt_draw_points:
        _add_crosshair(sheet, x, y, bolt_radius)
    sheet.object_bounds.append(plate_draw)

    left = min(x for x, _ in bolt_draw_points)
    right = max(x for x, _ in bolt_draw_points)
    bottom = min(y for _, y in bolt_draw_points)
    top = max(y for _, y in bolt_draw_points)
    _add_horizontal_dimension(
        sheet,
        plate_draw.x,
        plate_draw.right,
        plate_draw.top,
        plate_draw.top + 24,
        _fmt(data["length"]),
        allowed_zone="plan",
    )
    _add_horizontal_dimension(
        sheet,
        plate_draw.x,
        left,
        plate_draw.top,
        plate_draw.top + 13,
        _fmt(data["end"]),
        allowed_zone="plan",
    )
    _add_horizontal_dimension(
        sheet,
        left,
        right,
        plate_draw.top,
        plate_draw.top + 13,
        _fmt(data["pitch"]),
        allowed_zone="plan",
    )
    _add_horizontal_dimension(
        sheet,
        right,
        plate_draw.right,
        plate_draw.top,
        plate_draw.top + 13,
        _fmt(data["end"]),
        allowed_zone="plan",
    )
    _add_vertical_dimension(
        sheet,
        plate_draw.y,
        plate_draw.top,
        plate_draw.x,
        plate_draw.x - 18,
        _fmt(data["width"]),
        allowed_zone="plan",
    )
    _add_vertical_dimension(
        sheet,
        plate_draw.y,
        bottom,
        plate_draw.right,
        plate_draw.right + 10,
        _fmt(data["edge"]),
        allowed_zone="plan",
    )
    _add_vertical_dimension(
        sheet,
        bottom,
        top,
        plate_draw.right,
        plate_draw.right + 10,
        _fmt(data["gauge"]),
        allowed_zone="plan",
    )
    _add_vertical_dimension(
        sheet,
        top,
        plate_draw.top,
        plate_draw.right,
        plate_draw.right + 10,
        _fmt(data["edge"]),
        allowed_zone="plan",
    )
    _add_leader(
        sheet,
        bolt_draw_points[-1],
        (155, 194),
        (161, 190),
        (
            f"4-M{_fmt(data['diameter'])} GRADE "
            f"{data['holding'].get('steel_grade', '8.8')} HOLDING-DOWN BOLTS\n"
            f"HOLES DIA {_fmt(data['hole'])}\n"
            "MIN CENTRE CLEAR OF COLUMN FACE "
            f"{_fmt(float(data['layout'].get('minimum_section_face_clearance_mm', 0.0)))}"
        ),
        allowed_zone="plan",
        max_width_mm=34,
    )
    _add_leader(
        sheet,
        (cx, cy),
        (35, 251),
        (36, 249),
        f"COLUMN {data['column_name']}\nCENTRED ON PLATE",
        allowed_zone="plan",
        max_width_mm=34,
    )

    # Strong-axis section with calculated plate/bolt spacing.
    col_h = float(data["column"]["h"])
    col_tf = float(data["column"]["tf"])
    col_tw = float(data["column"]["tw"])
    shown_column_height = min(max(col_h, 320.0), 520.0)
    anchorage_length = float(data["anchorage"]["anchorage_length_mm"])
    anchor_plate_side = float(data["anchorage"]["anchor_plate_length_mm"])
    anchor_plate_thickness = float(
        data["anchorage"]["minimum_anchor_plate_thickness_mm"]
    )
    section_source = Rect(
        -data["length"] / 2.0 - 80.0,
        -anchorage_length - anchor_plate_thickness - 30.0,
        data["length"] + 160.0,
        (
            shown_column_height
            + anchorage_length
            + anchor_plate_thickness
            + 70.0
        ),
    )
    section_target = Rect(225, 120, 130, 126)
    section_transform = _ViewTransform.fit(section_source, section_target)
    plate_actual = Rect(
        -data["length"] / 2.0,
        0.0,
        data["length"],
        data["thickness"],
    )
    plate_section = section_transform.rect(plate_actual)
    _add_hatch_rect(sheet, plate_section, 2.6)
    sheet.add(
        Polyline(
            (
                (plate_section.x, plate_section.y),
                (plate_section.right, plate_section.y),
                (plate_section.right, plate_section.top),
                (plate_section.x, plate_section.top),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.38,
        )
    )
    flange_left = section_transform.rect(
        Rect(-col_h / 2.0, data["thickness"], col_tf, shown_column_height)
    )
    flange_right = section_transform.rect(
        Rect(col_h / 2.0 - col_tf, data["thickness"], col_tf, shown_column_height)
    )
    web_section = section_transform.rect(
        Rect(-col_tw / 2.0, data["thickness"], col_tw, shown_column_height)
    )
    for part in (flange_left, flange_right, web_section):
        _add_hatch_rect(sheet, part, 2.6)
        sheet.add(
            Polyline(
                (
                    (part.x, part.y),
                    (part.right, part.y),
                    (part.right, part.top),
                    (part.x, part.top),
                ),
                closed=True,
                layer="OBJECT",
                width_mm=0.28,
            )
        )
    anchor_xs = (-data["pitch"] / 2.0, data["pitch"] / 2.0)
    anchor_plate_draws = []
    for anchor_x in anchor_xs:
        top_point = section_transform.point(anchor_x, data["thickness"] + 22.0)
        bottom_point = section_transform.point(anchor_x, -anchorage_length)
        anchor_plate = section_transform.rect(
            Rect(
                anchor_x - anchor_plate_side / 2.0,
                -anchorage_length - anchor_plate_thickness,
                anchor_plate_side,
                anchor_plate_thickness,
            )
        )
        anchor_plate_draws.append(anchor_plate)
        sheet.add(
            Line(
                top_point[0],
                top_point[1],
                bottom_point[0],
                bottom_point[1],
                layer="BOLTS",
                width_mm=0.35,
            ),
            Line(
                top_point[0] - 4,
                top_point[1],
                top_point[0] + 4,
                top_point[1],
                layer="BOLTS",
                width_mm=0.45,
            ),
        )
        _add_hatch_rect(sheet, anchor_plate, 1.8)
        _add_rect_outline(
            sheet,
            anchor_plate,
            layer="BOLTS",
            width_mm=0.30,
        )
    # Track the actual solid rectangles rather than one coarse bounding box;
    # the latter would incorrectly treat the clear space between anchor rods
    # as occupied drawing geometry.
    sheet.object_bounds.extend(
        [
            plate_section,
            flange_left,
            flange_right,
            web_section,
            *anchor_plate_draws,
        ]
    )
    _add_horizontal_dimension(
        sheet,
        plate_section.x,
        plate_section.right,
        plate_section.y,
        plate_section.y - 16,
        _fmt(data["length"]),
        allowed_zone="section",
    )
    _add_leader(
        sheet,
        (plate_section.right - 2, (plate_section.y + plate_section.top) / 2),
        (365, 167),
        (368, 165),
        (
            f"BASE PLATE {_fmt(data['length'])} x {_fmt(data['width'])} "
            f"x {_fmt(data['thickness'])}"
        ),
        allowed_zone="section",
        max_width_mm=34,
    )
    _add_leader(
        sheet,
        section_transform.point(data["pitch"] / 2, -45),
        (365, 131),
        (368, 129),
        (
            f"M{_fmt(data['diameter'])} HD BOLT | "
            f"ANCHORAGE {_fmt(anchorage_length)}\n"
            f"ANCHOR PLATE {_fmt(anchor_plate_side)} x "
            f"{_fmt(anchor_plate_side)} x "
            f"{_fmt(anchor_plate_thickness)} MIN\n"
            "25 MPa CONCRETE | VERIFY 7d EDGE DISTANCE"
        ),
        allowed_zone="section",
        max_width_mm=34,
    )
    _add_leader(
        sheet,
        (web_section.x, plate_section.top),
        (365, 204),
        (368, 202),
        "CONTINUOUS COLUMN-TO-PLATE WELD\nSIZE TO CONNECTION CALCULATIONS",
        allowed_zone="section",
        max_width_mm=34,
    )

    # Separate rectangular flat-plate stiffener detail.
    stiffener = data["stiffener"]
    detail_zone = sheet.zones["detail"]
    if stiffener.get("required"):
        stiff_h = float(stiffener["height_mm"])
        stiff_l = float(stiffener["length_mm"])
        source = Rect(0, 0, stiff_l, stiff_h)
        target = Rect(41, 25, 78, 39)
        transform = _ViewTransform.fit(source, target)
        stiff_rect = transform.rect(source)
        _add_hatch_rect(sheet, stiff_rect, 2.5)
        sheet.add(
            Polyline(
                (
                    (stiff_rect.x, stiff_rect.y),
                    (stiff_rect.right, stiff_rect.y),
                    (stiff_rect.right, stiff_rect.top),
                    (stiff_rect.x, stiff_rect.top),
                ),
                closed=True,
                layer="OBJECT",
                width_mm=0.35,
            )
        )
        sheet.object_bounds.append(stiff_rect)
        _add_horizontal_dimension(
            sheet,
            stiff_rect.x,
            stiff_rect.right,
            stiff_rect.y,
            stiff_rect.y - 8,
            _fmt(stiff_l),
            allowed_zone="detail",
        )
        _add_vertical_dimension(
            sheet,
            stiff_rect.y,
            stiff_rect.top,
            stiff_rect.x,
            stiff_rect.x - 9,
            _fmt(stiff_h),
            allowed_zone="detail",
        )
        sheet.add(
            Text(
                130,
                50,
                (
                    f"{int(stiffener.get('count', 0))}-PL"
                    f"{_fmt(float(stiffener['provided_thickness_mm']))}\n"
                    "FLAT RECTANGULAR PLATE"
                ),
                height_mm=2.7,
                max_width_mm=54,
                allowed_zone="detail",
            )
        )
    else:
        sheet.add(
            Text(
                detail_zone.x + 8,
                detail_zone.y + 29,
                "BASE STIFFENERS: NONE",
                height_mm=3.0,
                bold=True,
                allowed_zone="detail",
            )
        )

    notes = (
        "1. HD-BOLT TOOL AND EDGE CLEARANCES FOLLOW RED BOOK TABLES 6.17 AND 6.19.",
        "2. PROVIDE STANDARD WASHERS AND NUTS TO THE BOLT GRADE.",
        "3. PROVIDE THE CALCULATED RED BOOK ANCHORAGE AND ANCHOR PLATES SHOWN.",
        "4. STIFFENERS, WHEN SHOWN, ARE FLAT RECTANGULAR PLATES.",
        "5. VERIFY 7d CONCRETE EDGE, PEDESTAL REINFORCEMENT, GROUT AND TOLERANCES.",
    )
    for index, note in enumerate(notes):
        sheet.add(
            Text(
                213,
                65 - index * 9.5,
                note,
                height_mm=2.45,
                max_width_mm=186,
                allowed_zone="notes",
            )
        )
    sheet.validate_collisions()
    return sheet


def _add_end_plate_elevation(
    sheet: ConnectionSheet,
    data: Mapping[str, Any],
    *,
    zone: Rect,
    zone_name: str,
) -> None:
    plate_w = float(data["plate_width"])
    plate_h = float(data["plate_height"])
    source = Rect(-plate_w / 2, -plate_h / 2, plate_w, plate_h)
    target = Rect(zone.x + 39, zone.y + 35, 92, zone.height - 67)
    transform = _ViewTransform.fit(source, target)
    plate = transform.rect(source)
    sheet.add(
        Polyline(
            (
                (plate.x, plate.y),
                (plate.right, plate.y),
                (plate.right, plate.top),
                (plate.x, plate.top),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.38,
        )
    )
    rafter = data["rafter"]
    rafter_h = float(rafter["h"])
    rafter_b = min(float(rafter["b"]), plate_w)
    rafter_tw = min(float(rafter["tw"]), rafter_b)
    rafter_tf = min(float(rafter["tf"]), rafter_h / 2.0)
    top_y = plate_h / 2.0
    beam_bottom_y = top_y - rafter_h
    haunch_bottom_y = max(
        -plate_h / 2.0,
        beam_bottom_y - float(data["depth"]),
    )
    projected_components = (
        Rect(-rafter_b / 2.0, top_y - rafter_tf, rafter_b, rafter_tf),
        Rect(
            -rafter_tw / 2.0,
            beam_bottom_y + rafter_tf,
            rafter_tw,
            max(rafter_h - 2.0 * rafter_tf, 0.1),
        ),
        Rect(-rafter_b / 2.0, beam_bottom_y, rafter_b, rafter_tf),
        Rect(
            -rafter_tw / 2.0,
            haunch_bottom_y + rafter_tf,
            rafter_tw,
            max(beam_bottom_y - haunch_bottom_y - rafter_tf, 0.1),
        ),
        Rect(-rafter_b / 2.0, haunch_bottom_y, rafter_b, rafter_tf),
    )
    for component in projected_components:
        _add_rect_outline(
            sheet,
            transform.rect(component),
            layer="OBJECT",
            width_mm=0.24,
        )
    cx, cy = transform.point(0, 0)
    sheet.add(
        Line(cx, plate.y - 4, cx, plate.top + 4, layer="CENTRE", dashed=True),
        Line(plate.x - 4, cy, plate.right + 4, cy, layer="CENTRE", dashed=True),
    )
    first_y = -plate_h / 2.0 + float(data["end"])
    bolt_points = []
    bolt_row_y: list[float] = []
    for row in range(int(data["rows"])):
        row_y = transform.point(0.0, first_y + row * float(data["pitch"]))[1]
        bolt_row_y.append(row_y)
        for x in (-float(data["gauge"]) / 2.0, float(data["gauge"]) / 2.0):
            point = transform.point(x, first_y + row * float(data["pitch"]))
            bolt_points.append(point)
            radius = max(1.4, float(data["hole"]) * transform.scale / 2.0)
            _add_crosshair(sheet, point[0], point[1], radius)
    sheet.object_bounds.append(plate)
    left = min(x for x, _ in bolt_points)
    right = max(x for x, _ in bolt_points)
    _add_horizontal_dimension(
        sheet,
        plate.x,
        plate.right,
        plate.top,
        plate.top + 20,
        _fmt(plate_w),
        allowed_zone=zone_name,
    )
    _add_horizontal_dimension(
        sheet,
        plate.x,
        left,
        plate.top,
        plate.top + 10,
        _fmt(float(data["edge"])),
        allowed_zone=zone_name,
    )
    _add_horizontal_dimension(
        sheet,
        left,
        right,
        plate.top,
        plate.top + 10,
        _fmt(float(data["gauge"])),
        allowed_zone=zone_name,
    )
    _add_horizontal_dimension(
        sheet,
        right,
        plate.right,
        plate.top,
        plate.top + 10,
        _fmt(float(data["edge"])),
        allowed_zone=zone_name,
    )
    _add_vertical_dimension(
        sheet,
        plate.y,
        plate.top,
        plate.x,
        plate.x - 18,
        _fmt(plate_h),
        allowed_zone=zone_name,
    )
    _add_bolt_row_dimensions(
        sheet,
        data,
        plate_bottom=plate.y,
        plate_top=plate.top,
        row_positions=bolt_row_y,
        object_x=plate.right,
        dim_x=plate.right + 9,
        allowed_zone=zone_name,
    )
    _add_leader(
        sheet,
        bolt_points[-1],
        (zone.right - 43, zone.y + zone.height * 0.57),
        (zone.right - 40, zone.y + zone.height * 0.55),
        (
            f"{int(data['count'])}-M{_fmt(float(data['diameter']))} "
            f"GRADE 8.8 BOLTS\nHOLES DIA {_fmt(float(data['hole']))}"
        ),
        allowed_zone=zone_name,
        max_width_mm=35,
    )
    sheet.add(
        Text(
            zone.x + 38,
            zone.y + 14,
            (
                f"END PLATE {_fmt(plate_h)} x {_fmt(plate_w)} x "
                f"{_fmt(float(data['plate_thickness']))}"
            ),
            height_mm=2.65,
            allowed_zone=zone_name,
        )
    )


def _add_haunch_donor_detail(
    sheet: ConnectionSheet,
    data: Mapping[str, Any],
    *,
    zone: Rect,
    zone_name: str,
) -> None:
    length = float(data["length"])
    depth = float(data["depth"])
    tf = float(data["rafter"]["tf"])
    # The donor contains the retained bottom flange and tapered web only.
    # The removed top flange is deliberately absent.
    source = Rect(0.0, -depth, length, depth + tf)
    target = Rect(zone.x + 32, zone.y + 18, zone.width - 92, zone.height - 37)
    transform = _ViewTransform.fit(source, target)
    weld_start = transform.point(0.0, 0.0)
    weld_end = transform.point(length, 0.0)
    web_bottom_start = transform.point(0.0, -max(depth - tf, 0.0))
    web_bottom_end = transform.point(length, 0.0)
    flange_outer_start = transform.point(0.0, -depth)
    flange_outer_end = transform.point(length, -tf)
    sheet.add(
        Polyline(
            (weld_start, weld_end, web_bottom_start),
            closed=True,
            layer="OBJECT",
            width_mm=0.34,
        ),
        Polyline(
            (
                web_bottom_start,
                web_bottom_end,
                flange_outer_end,
                flange_outer_start,
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.40,
        ),
        Line(
            weld_start[0],
            weld_start[1],
            weld_end[0],
            weld_end[1],
            layer="WELDS",
            width_mm=0.55,
        ),
    )
    donor_box = _line_box(
        (weld_start, weld_end, web_bottom_start, flange_outer_start, flange_outer_end)
    )
    sheet.object_bounds.append(donor_box)
    _add_horizontal_dimension(
        sheet,
        weld_start[0],
        weld_end[0],
        max(weld_start[1], weld_end[1]),
        max(weld_start[1], weld_end[1]) + 11,
        _fmt(length),
        allowed_zone=zone_name,
    )
    _add_vertical_dimension(
        sheet,
        flange_outer_start[1],
        weld_start[1],
        weld_start[0],
        weld_start[0] - 12,
        _fmt(depth),
        allowed_zone=zone_name,
    )
    _add_leader(
        sheet,
        ((weld_start[0] + weld_end[0]) / 2, weld_start[1]),
        (zone.right - 57, zone.y + 34),
        (zone.right - 53, zone.y + 32),
        "TOP FLANGE REMOVED\nWEB WELDED TO MAIN RAFTER",
        allowed_zone=zone_name,
        max_width_mm=47,
    )
    _add_leader(
        sheet,
        (
            (flange_outer_start[0] + flange_outer_end[0]) / 2,
            (flange_outer_start[1] + flange_outer_end[1]) / 2,
        ),
        (zone.right - 57, zone.y + 18),
        (zone.right - 53, zone.y + 16),
        "RETAINED BOTTOM FLANGE",
        allowed_zone=zone_name,
        max_width_mm=47,
    )


def _add_haunch_stiffener_detail(
    sheet: ConnectionSheet,
    data: Mapping[str, Any],
    *,
    zone: Rect,
    zone_name: str,
) -> None:
    """Add one calculated typical flat-plate detail and its fabrication callout."""

    stiffener = data["stiffener"]
    if not stiffener.get("required"):
        return

    height = float(stiffener["height_mm"])
    length = float(stiffener["length_mm"])
    thickness = float(stiffener["provided_thickness_mm"])
    count = int(stiffener["count"])
    position = str(stiffener["position"]).strip().upper()

    source = Rect(0.0, 0.0, length, height)
    target = Rect(zone.right - 61.0, zone.y + 19.0, 44.0, 32.0)
    transform = _ViewTransform.fit(source, target)
    plate = transform.rect(source)
    _add_hatch_rect(sheet, plate, 2.5)
    sheet.add(
        Polyline(
            (
                (plate.x, plate.y),
                (plate.right, plate.y),
                (plate.right, plate.top),
                (plate.x, plate.top),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.35,
        )
    )
    sheet.object_bounds.append(plate)
    _add_horizontal_dimension(
        sheet,
        plate.x,
        plate.right,
        plate.y,
        zone.y + 10.0,
        _fmt(length),
        allowed_zone=zone_name,
    )
    _add_vertical_dimension(
        sheet,
        plate.y,
        plate.top,
        plate.x,
        plate.x - 9.0,
        _fmt(height),
        allowed_zone=zone_name,
    )
    sheet.add(
        Text(
            zone.right - 80.0,
            zone.top - 17.0,
            (
                "TYPICAL FLAT STIFFENER PLATE\n"
                f"{count}-PL{_fmt(thickness)} | "
                f"{_fmt(height)} HIGH x {_fmt(length)} LONG\n"
                f"POSITION: {position}"
            ),
            height_mm=2.35,
            max_width_mm=74.0,
            allowed_zone=zone_name,
        )
    )


def _build_eaves_sheet(
    location: Mapping[str, Any],
    layout_name: str,
) -> ConnectionSheet:
    data = _validate_haunch_location(location)
    sheet = ConnectionSheet(
        sheet_id="HC-EAVES",
        layout_name=layout_name,
        title="EAVES RAFTER-TO-COLUMN BOLTED END-PLATE CONNECTION",
        subtitle=(
            f"COLUMN {data['column_name']} | RAFTER {data['rafter_name']} | "
            f"HAUNCH L={_fmt(data['length'])}, CUT DEPTH={_fmt(data['depth'])} | "
            f"LIMIT hw+tf={_fmt(data['cut_check'].maximum_cut_depth_mm)}"
        ),
    )
    sheet.zones = {
        "ga": Rect(14, 94, 188, 174),
        "plate": Rect(210, 94, 196, 174),
        "donor": Rect(14, 14, 188, 71),
        "notes": Rect(210, 14, 196, 71),
    }
    _add_sheet_frame(sheet)
    _add_zone_title(sheet, sheet.zones["ga"], "CONNECTION GENERAL ARRANGEMENT", zone_name="ga")
    _add_zone_title(sheet, sheet.zones["plate"], "END-PLATE ELEVATION", zone_name="plate")
    _add_zone_title(sheet, sheet.zones["donor"], "HAUNCH DONOR CUT DETAIL", zone_name="donor")
    _add_zone_title(sheet, sheet.zones["notes"], "FABRICATION CALLOUTS", zone_name="notes")

    ga = sheet.zones["ga"]
    column_x1, column_x2 = 48.0, 76.0
    column_y1, column_y2 = 118.0, 244.0
    plate_x = 79.0
    plate_bottom_y, plate_top_y = 143.0, 233.0
    plate_scale = (plate_top_y - plate_bottom_y) / float(data["plate_height"])
    rafter_top_y = plate_top_y
    rafter_bottom_y = rafter_top_y - float(data["rafter"]["h"]) * plate_scale
    joint_y = rafter_top_y
    rafter_depth_draw = rafter_top_y - rafter_bottom_y
    slope = 0.13
    rafter_end_x = 174.0
    upper_y_end = rafter_top_y + slope * (rafter_end_x - plate_x)
    lower_y_start = rafter_bottom_y
    lower_y_end = upper_y_end - rafter_depth_draw
    sheet.add(
        Polyline(
            (
                (column_x1, column_y1),
                (column_x2, column_y1),
                (column_x2, column_y2),
                (column_x1, column_y2),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.42,
        ),
        Line(plate_x, 143, plate_x, 233, layer="OBJECT", width_mm=0.65),
        Line(plate_x, joint_y, rafter_end_x, upper_y_end, layer="OBJECT", width_mm=0.55),
        Line(plate_x, lower_y_start, rafter_end_x, lower_y_end, layer="OBJECT", width_mm=0.55),
    )
    # Show the rolled column and rafter flange thicknesses, not only their
    # overall bounding outlines.
    column_tf_draw = max(
        1.2,
        min(
            3.0,
            float(data["column"]["tf"])
            / float(data["column"]["h"])
            * (column_x2 - column_x1),
        ),
    )
    sheet.add(
        Line(
            column_x1 + column_tf_draw,
            column_y1,
            column_x1 + column_tf_draw,
            column_y2,
            layer="OBJECT",
            width_mm=0.25,
        ),
        Line(
            column_x2 - column_tf_draw,
            column_y1,
            column_x2 - column_tf_draw,
            column_y2,
            layer="OBJECT",
            width_mm=0.25,
        ),
        Line(
            plate_x,
            joint_y - 1.7,
            rafter_end_x,
            upper_y_end - 1.7,
            layer="OBJECT",
            width_mm=0.24,
        ),
        Line(
            plate_x,
            lower_y_start + 1.7,
            rafter_end_x,
            lower_y_end + 1.7,
            layer="OBJECT",
            width_mm=0.24,
        ),
    )
    haunch_toe_x = 155.0
    haunch_bottom_at_plate = max(
        plate_bottom_y,
        lower_y_start - float(data["depth"]) * plate_scale,
    )
    haunch_bottom_toe = (
        lower_y_start
        + slope * (haunch_toe_x - plate_x)
    )
    sheet.add(
        Polyline(
            (
                (plate_x, lower_y_start),
                (haunch_toe_x, haunch_bottom_toe),
                (plate_x, haunch_bottom_at_plate),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.40,
        ),
        Line(
            plate_x,
            haunch_bottom_at_plate - 2.1,
            haunch_toe_x,
            haunch_bottom_toe - 2.1,
            layer="OBJECT",
            width_mm=0.60,
        ),
        Line(plate_x, lower_y_start, haunch_toe_x, haunch_bottom_toe, layer="WELDS", width_mm=0.5),
    )
    # Flat transverse stiffeners are rectangular plates across the column.
    if data["stiffener"].get("required"):
        stiffener_count = int(data["stiffener"]["count"])
        projection_thickness = min(
            5.0,
            max(
                2.0,
                float(data["stiffener"]["provided_thickness_mm"]) * 0.3,
            ),
        )
        for index in range(stiffener_count):
            fraction = index / max(stiffener_count - 1, 1)
            centre_y = lower_y_start + fraction * (joint_y - lower_y_start)
            rect = Rect(
                column_x1 + 2,
                centre_y - projection_thickness / 2.0,
                column_x2 - column_x1 - 4,
                projection_thickness,
            )
            _add_hatch_rect(sheet, rect, 2.3)
            sheet.add(
                Polyline(
                    (
                        (rect.x, rect.y),
                        (rect.right, rect.y),
                        (rect.right, rect.top),
                        (rect.x, rect.top),
                    ),
                    closed=True,
                    layer="OBJECT",
                    width_mm=0.3,
                )
            )
    bolt_row_y = _bolt_row_positions(
        data,
        plate_bottom=plate_bottom_y,
        plate_top=plate_top_y,
    )
    for y in bolt_row_y:
        # In the GA the bolts are represented by their axes only.  Keeping
        # the dashed line on the column/end-plate side avoids implying that
        # the bolt passes through the rafter flange.
        sheet.add(
            Line(61.0, y, plate_x, y, layer="BOLTS", width_mm=0.26, dashed=True)
        )
    _add_bolt_row_dimensions(
        sheet,
        data,
        plate_bottom=plate_bottom_y,
        plate_top=plate_top_y,
        row_positions=bolt_row_y,
        object_x=column_x1,
        dim_x=38.0,
        allowed_zone="ga",
    )
    sheet.object_bounds.extend(
        [
            Rect(
                column_x1,
                column_y1,
                column_x2 - column_x1,
                column_y2 - column_y1,
            ),
            Rect(plate_x - 0.8, 143, 1.6, 90),
            _line_box(((plate_x, joint_y), (rafter_end_x, upper_y_end))).inset(-0.8),
            _line_box(((plate_x, lower_y_start), (rafter_end_x, lower_y_end))).inset(-0.8),
            _line_box(
                ((plate_x, lower_y_start), (haunch_toe_x, haunch_bottom_toe))
            ).inset(-0.8),
            _line_box(
                ((plate_x, haunch_bottom_at_plate), (haunch_toe_x, haunch_bottom_toe))
            ).inset(-0.8),
        ]
    )
    _add_leader(
        sheet,
        (118, 174),
        (153, 157),
        (157, 154),
        f"TAPERED HAUNCH\nL={_fmt(data['length'])}, DEPTH={_fmt(data['depth'])}",
        allowed_zone="ga",
        max_width_mm=35,
    )
    _add_leader(
        sheet,
        (plate_x, 224),
        (116, 251),
        (120, 249),
        (
            f"END PLATE {_fmt(data['plate_height'])} x "
            f"{_fmt(data['plate_width'])} x {_fmt(data['plate_thickness'])}"
        ),
        allowed_zone="ga",
        max_width_mm=63,
    )
    if data["stiffener"].get("required"):
        _add_leader(
            sheet,
            (62, joint_y),
            (95, 126),
            (100, 123),
            (
                f"{int(data['stiffener']['count'])}-PL"
                f"{_fmt(float(data['stiffener']['provided_thickness_mm']))} "
                "FLAT TRANSVERSE STIFFENERS - SEE DETAIL"
            ),
            allowed_zone="ga",
            max_width_mm=76,
        )

    _add_end_plate_elevation(
        sheet,
        data,
        zone=sheet.zones["plate"],
        zone_name="plate",
    )
    _add_haunch_donor_detail(
        sheet,
        data,
        zone=sheet.zones["donor"],
        zone_name="donor",
    )
    _add_haunch_stiffener_detail(
        sheet,
        data,
        zone=sheet.zones["notes"],
        zone_name="notes",
    )
    notes = (
        "1. HAUNCH TOP FLANGE IS REMOVED; WEB IS WELDED TO THE MAIN RAFTER.",
        "2. HAUNCH BOTTOM FLANGE IS RETAINED AND FOLLOWS THE TAPER.",
        (
            "3. TRANSVERSE STIFFENERS ARE FLAT RECTANGULAR PLATES."
            if data["stiffener"].get("required")
            else "3. TRANSVERSE STIFFENERS ARE NOT REQUIRED."
        ),
        "4. BOLT PITCH, GAUGE, END AND EDGE DISTANCES ARE CALCULATED.",
        (
            "5. PROVIDE END-PLATE AND STIFFENER WELDS TO CONNECTION CALCULATIONS."
            if data["stiffener"].get("required")
            else "5. PROVIDE END-PLATE WELDS TO CONNECTION CALCULATIONS."
        ),
    )
    for index, note in enumerate(notes):
        sheet.add(
            Text(
                216,
                68 - index * 10.0,
                note,
                height_mm=2.45,
                max_width_mm=100,
                allowed_zone="notes",
            )
        )
    sheet.validate_collisions()
    return sheet


def _build_apex_sheet(
    location: Mapping[str, Any],
    layout_name: str,
) -> ConnectionSheet:
    data = _validate_haunch_location(location)
    sheet = ConnectionSheet(
        sheet_id="HC-APEX",
        layout_name=layout_name,
        title="APEX RAFTER-TO-RAFTER BOLTED SPLICE CONNECTION",
        subtitle=(
            f"RAFTERS {data['rafter_name']} BOTH SIDES | "
            f"HAUNCH L={_fmt(data['length'])} PER SLOPE, "
            f"CUT DEPTH={_fmt(data['depth'])} | "
            f"LIMIT hw+tf={_fmt(data['cut_check'].maximum_cut_depth_mm)}"
        ),
    )
    sheet.zones = {
        "ga": Rect(14, 94, 188, 174),
        "plate": Rect(210, 94, 196, 174),
        "donor": Rect(14, 14, 188, 71),
        "notes": Rect(210, 14, 196, 71),
    }
    _add_sheet_frame(sheet)
    _add_zone_title(sheet, sheet.zones["ga"], "SYMMETRICAL APEX SPLICE", zone_name="ga")
    _add_zone_title(sheet, sheet.zones["plate"], "END-PLATE ELEVATION", zone_name="plate")
    _add_zone_title(sheet, sheet.zones["donor"], "TYPICAL HAUNCH DONOR CUT", zone_name="donor")
    _add_zone_title(sheet, sheet.zones["notes"], "FABRICATION CALLOUTS", zone_name="notes")

    apex_x = 108.0
    plate_bottom_y, plate_top_y = 142.0, 232.0
    plate_scale = (plate_top_y - plate_bottom_y) / data["plate_height"]
    apex_y = plate_top_y
    left_x, right_x = 34.0, 182.0
    slope = 0.16
    depth_draw = data["rafter"]["h"] * plate_scale
    haunch_flange_draw = max(data["rafter"]["tf"] * plate_scale, 1.2)
    haunch_bottom_y = max(
        plate_bottom_y + haunch_flange_draw,
        apex_y - depth_draw - data["depth"] * plate_scale,
    )
    left_top_y = apex_y - slope * (apex_x - left_x)
    right_top_y = apex_y - slope * (right_x - apex_x)
    sheet.add(
        Line(left_x, left_top_y, apex_x - 2, apex_y, layer="OBJECT", width_mm=0.55),
        Line(
            left_x,
            left_top_y - depth_draw,
            apex_x - 2,
            apex_y - depth_draw,
            layer="OBJECT",
            width_mm=0.55,
        ),
        Line(apex_x + 2, apex_y, right_x, right_top_y, layer="OBJECT", width_mm=0.55),
        Line(
            apex_x + 2,
            apex_y - depth_draw,
            right_x,
            right_top_y - depth_draw,
            layer="OBJECT",
            width_mm=0.55,
        ),
        Line(apex_x - 2, plate_bottom_y, apex_x - 2, plate_top_y, layer="OBJECT", width_mm=0.6),
        Line(apex_x + 2, plate_bottom_y, apex_x + 2, plate_top_y, layer="OBJECT", width_mm=0.6),
    )
    left_toe = 55.0
    right_toe = 161.0
    left_lower_toe_y = left_top_y - depth_draw + slope * (left_toe - left_x)
    right_lower_toe_y = right_top_y - depth_draw - slope * (right_toe - right_x)
    sheet.add(
        Polyline(
            (
                (apex_x - 2, apex_y - depth_draw),
                (left_toe, left_lower_toe_y),
                (apex_x - 2, haunch_bottom_y),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.38,
        ),
        Polyline(
            (
                (apex_x + 2, apex_y - depth_draw),
                (right_toe, right_lower_toe_y),
                (apex_x + 2, haunch_bottom_y),
            ),
            closed=True,
            layer="OBJECT",
            width_mm=0.38,
        ),
        Line(apex_x - 2, plate_bottom_y, left_toe, left_lower_toe_y - haunch_flange_draw, layer="OBJECT", width_mm=0.6),
        Line(apex_x + 2, plate_bottom_y, right_toe, right_lower_toe_y - haunch_flange_draw, layer="OBJECT", width_mm=0.6),
        Line(apex_x - 2, apex_y - depth_draw, left_toe, left_lower_toe_y, layer="WELDS", width_mm=0.5),
        Line(apex_x + 2, apex_y - depth_draw, right_toe, right_lower_toe_y, layer="WELDS", width_mm=0.5),
    )
    bolt_row_y = _bolt_row_positions(
        data,
        plate_bottom=plate_bottom_y,
        plate_top=plate_top_y,
    )
    for y in bolt_row_y:
        sheet.add(
            Line(
                apex_x - 8,
                y,
                apex_x + 8,
                y,
                layer="BOLTS",
                width_mm=0.26,
                dashed=True,
            )
        )
    _add_bolt_row_dimensions(
        sheet,
        data,
        plate_bottom=plate_bottom_y,
        plate_top=plate_top_y,
        row_positions=bolt_row_y,
        object_x=apex_x - 8,
        dim_x=25.0,
        allowed_zone="ga",
    )
    sheet.object_bounds.extend(
        [
            Rect(apex_x - 2.8, 142, 5.6, 90),
            _line_box(((left_x, left_top_y), (apex_x - 2, apex_y))).inset(-0.8),
            _line_box(
                ((left_x, left_top_y - depth_draw), (apex_x - 2, apex_y - depth_draw))
            ).inset(-0.8),
            _line_box(((apex_x + 2, apex_y), (right_x, right_top_y))).inset(-0.8),
            _line_box(
                ((apex_x + 2, apex_y - depth_draw), (right_x, right_top_y - depth_draw))
            ).inset(-0.8),
            _line_box(
                ((apex_x - 2, apex_y - depth_draw), (left_toe, left_lower_toe_y))
            ).inset(-0.8),
            _line_box(
                ((apex_x + 2, apex_y - depth_draw), (right_toe, right_lower_toe_y))
            ).inset(-0.8),
        ]
    )
    _add_leader(
        sheet,
        (apex_x, 224),
        (146, 245),
        (150, 242),
        "MATCHED END PLATES\nRAFTER-TO-RAFTER SPLICE",
        allowed_zone="ga",
        max_width_mm=41,
    )
    _add_leader(
        sheet,
        (74, 172),
        (80, 132),
        (25, 126),
        (
            f"TAPERED HAUNCH EACH SIDE\nL={_fmt(data['length'])}, "
            f"DEPTH={_fmt(data['depth'])}"
        ),
        allowed_zone="ga",
        max_width_mm=64,
        attach="right",
    )
    if data["stiffener"].get("required"):
        _add_leader(
            sheet,
            (apex_x - 2, 180),
            (145, 130),
            (150, 127),
            (
                f"{int(data['stiffener']['count'])}-PL"
                f"{_fmt(float(data['stiffener']['provided_thickness_mm']))} "
                "FLAT STIFFENERS - SEE DETAIL"
            ),
            allowed_zone="ga",
            max_width_mm=41,
        )
    _add_end_plate_elevation(
        sheet,
        data,
        zone=sheet.zones["plate"],
        zone_name="plate",
    )
    _add_haunch_donor_detail(
        sheet,
        data,
        zone=sheet.zones["donor"],
        zone_name="donor",
    )
    _add_haunch_stiffener_detail(
        sheet,
        data,
        zone=sheet.zones["notes"],
        zone_name="notes",
    )
    notes = (
        "1. THIS IS A RAFTER-TO-RAFTER SPLICE; NO COLUMN OCCURS AT THE APEX.",
        "2. PROVIDE MATCHED END PLATES NORMAL TO THE RAFTER CENTRELINES.",
        "3. HAUNCH TOP FLANGES ARE REMOVED; RETAIN BOTTOM FLANGES.",
        "4. STIFFENERS, WHEN REQUIRED, ARE FLAT RECTANGULAR PLATES.",
        "5. BOLT PITCH, GAUGE, END AND EDGE DISTANCES ARE CALCULATED.",
    )
    for index, note in enumerate(notes):
        sheet.add(
            Text(
                216,
                68 - index * 10.0,
                note,
                height_mm=2.45,
                max_width_mm=100,
                allowed_zone="notes",
            )
        )
    sheet.validate_collisions()
    return sheet


def build_connection_sheets(
    result: Mapping[str, Any],
) -> list[ConnectionSheet]:
    """Build validated A3 connection sheets from one connection-design result."""

    if not isinstance(result, Mapping):
        raise ConnectionDrawingError("Connection design result must be a mapping.")
    base_plates = _mapping(result.get("base_plates", {}), "base_plates")
    haunches = _mapping(result.get("haunch_connections", {}), "haunch_connections")
    supports = base_plates.get("supports", [])
    locations = haunches.get("locations", [])
    if not isinstance(supports, Sequence) or isinstance(supports, (str, bytes)):
        raise ConnectionDrawingError("base_plates.supports must be a sequence.")
    if not isinstance(locations, Sequence) or isinstance(locations, (str, bytes)):
        raise ConnectionDrawingError("haunch_connections.locations must be a sequence.")

    sheets: list[ConnectionSheet] = []
    used_layouts: set[str] = set()
    for support_value in supports:
        support = _mapping(support_value, "base-plate support")
        if not support.get("plate"):
            continue
        support_name = str(support.get("support", "BASE"))
        sheets.append(
            _build_base_sheet(
                support,
                _safe_layout_name("BP", support_name, used_layouts),
            )
        )
    for location_value in locations:
        location = _mapping(location_value, "haunch connection")
        if not location.get("connection", {}).get("plate"):
            continue
        location_name = str(location.get("location", ""))
        connection_value = location.get("connection", {})
        nested_type = (
            connection_value.get("connection_type", "")
            if isinstance(connection_value, Mapping)
            else ""
        )
        connection_type = str(
            location.get("connection_type", nested_type)
        ).strip()
        if not connection_type:
            connection_type = {
                "Eaves haunch": "eaves_end_plate",
                "Apex haunch": "apex_splice",
            }.get(location_name, "")
        if connection_type == "eaves_end_plate":
            sheets.append(
                _build_eaves_sheet(
                    location,
                    _safe_layout_name("HC", "EAVES", used_layouts),
                )
            )
        elif connection_type == "apex_splice":
            sheets.append(
                _build_apex_sheet(
                    location,
                    _safe_layout_name("HC", "APEX", used_layouts),
                )
            )
        else:
            raise ConnectionDrawingError(
                f"Unsupported connection location {location_name!r}."
            )
    if not sheets:
        raise ConnectionDrawingError(
            "No calculated base-plate or haunch connection geometry is available."
        )
    return sheets


def _set_pdf_layer_style(pdf: reportlab_canvas.Canvas, layer: str, width: float) -> None:
    colour = _PDF_COLOURS.get(layer, _PDF_COLOURS["OBJECT"])
    pdf.setStrokeColorRGB(*colour)
    pdf.setFillColorRGB(*colour)
    pdf.setLineWidth(max(width, 0.10) * MM_TO_PT)
    if layer == "HIDDEN":
        pdf.setDash(3.0 * MM_TO_PT, 2.0 * MM_TO_PT)
    elif layer == "CENTRE":
        pdf.setDash([6.0 * MM_TO_PT, 2.0 * MM_TO_PT, 1.0 * MM_TO_PT, 2.0 * MM_TO_PT])
    else:
        pdf.setDash()


def _render_pdf_primitive(
    pdf: reportlab_canvas.Canvas,
    primitive: Primitive,
) -> None:
    if isinstance(primitive, Line):
        _set_pdf_layer_style(pdf, primitive.layer, primitive.width_mm)
        if primitive.dashed and primitive.layer not in {"HIDDEN", "CENTRE"}:
            pdf.setDash(3.0 * MM_TO_PT, 2.0 * MM_TO_PT)
        pdf.line(
            primitive.x1 * MM_TO_PT,
            primitive.y1 * MM_TO_PT,
            primitive.x2 * MM_TO_PT,
            primitive.y2 * MM_TO_PT,
        )
        return
    if isinstance(primitive, Polyline):
        _set_pdf_layer_style(pdf, primitive.layer, primitive.width_mm)
        if primitive.dashed and primitive.layer not in {"HIDDEN", "CENTRE"}:
            pdf.setDash(3.0 * MM_TO_PT, 2.0 * MM_TO_PT)
        path = pdf.beginPath()
        first = primitive.points[0]
        path.moveTo(first[0] * MM_TO_PT, first[1] * MM_TO_PT)
        for x, y in primitive.points[1:]:
            path.lineTo(x * MM_TO_PT, y * MM_TO_PT)
        if primitive.closed:
            path.close()
        pdf.drawPath(path, stroke=1, fill=0)
        return
    if isinstance(primitive, Circle):
        _set_pdf_layer_style(pdf, primitive.layer, primitive.width_mm)
        pdf.circle(
            primitive.x * MM_TO_PT,
            primitive.y * MM_TO_PT,
            primitive.radius * MM_TO_PT,
            stroke=1,
            fill=0,
        )
        return
    if isinstance(primitive, LinearDimension):
        # PDF dimensions are drawn by their accompanying PDF-only primitives;
        # this semantic entity is reserved for native CAD output.
        return
    if isinstance(primitive, Text):
        _set_pdf_layer_style(pdf, primitive.layer, 0.15)
        font = "Helvetica-Bold" if primitive.bold else "Helvetica"
        font_size = primitive.height_mm * MM_TO_PT
        pdf.setFont(font, font_size)
        y = primitive.y
        # Text.y is the lower-left baseline of the complete text box.  Draw
        # wrapped source lines in reverse baseline order so the first source
        # line remains the visual top line.
        for line in reversed(primitive.lines()):
            text_width = pdf.stringWidth(line, font, font_size)
            x = primitive.x * MM_TO_PT
            if primitive.align == "center":
                x -= text_width / 2.0
            elif primitive.align == "right":
                x -= text_width
            pdf.drawString(x, y * MM_TO_PT, line)
            y += primitive.height_mm * 1.32
        return
    raise TypeError(f"Unsupported drawing primitive {type(primitive)!r}.")


def write_connection_pdf(
    result: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Write a vector, multi-page A3-landscape PDF from canonical primitives."""

    sheets = build_connection_sheets(result)
    output = Path(path)
    if output.suffix.lower() != ".pdf":
        raise ConnectionDrawingError("Connection PDF path must end in .pdf.")
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = reportlab_canvas.Canvas(str(output), pagesize=landscape(A3))
    pdf.setTitle("Portal-frame connection markup")
    for sheet in sheets:
        for primitive in sheet.primitives:
            _render_pdf_primitive(pdf, primitive)
        pdf.showPage()
    pdf.save()
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("ReportLab did not create a non-empty connection PDF.")
    return output.resolve()


def _add_dxf_layers(doc: ezdxf.document.Drawing) -> None:
    for name in DXF_LAYERS:
        if name in doc.layers:
            continue
        linetype = (
            "DASHED"
            if name == "HIDDEN"
            else ("CENTER" if name == "CENTRE" else "CONTINUOUS")
        )
        doc.layers.add(
            name,
            color=_LAYER_COLOURS[name],
            linetype=linetype,
        )
    if "PF-1-1" not in doc.dimstyles:
        doc.dimstyles.new(
            "PF-1-1",
            dxfattribs={
                "dimtxt": 2.5,
                "dimasz": 1.6,
                "dimdec": 0,
                "dimtad": 1,
                "dimexo": 0.8,
                "dimexe": 1.25,
            },
        )


def _render_dxf_primitive(
    layout: Any,
    primitive: Primitive,
    *,
    offset: tuple[float, float] = (0.0, 0.0),
) -> None:
    ox, oy = offset
    if isinstance(primitive, Line):
        if primitive.pdf_only:
            return
        attrs = {"layer": primitive.layer}
        if primitive.dashed and primitive.layer not in {"HIDDEN", "CENTRE"}:
            attrs["linetype"] = "DASHED"
        layout.add_line(
            (primitive.x1 + ox, primitive.y1 + oy),
            (primitive.x2 + ox, primitive.y2 + oy),
            dxfattribs=attrs,
        )
        return
    if isinstance(primitive, Polyline):
        attrs = {"layer": primitive.layer}
        if primitive.dashed and primitive.layer not in {"HIDDEN", "CENTRE"}:
            attrs["linetype"] = "DASHED"
        layout.add_lwpolyline(
            [(x + ox, y + oy) for x, y in primitive.points],
            close=primitive.closed,
            dxfattribs=attrs,
        )
        return
    if isinstance(primitive, Circle):
        layout.add_circle(
            (primitive.x + ox, primitive.y + oy),
            primitive.radius,
            dxfattribs={"layer": primitive.layer},
        )
        return
    if isinstance(primitive, LinearDimension):
        dimension = layout.add_linear_dim(
            base=(primitive.base[0] + ox, primitive.base[1] + oy),
            p1=(primitive.p1[0] + ox, primitive.p1[1] + oy),
            p2=(primitive.p2[0] + ox, primitive.p2[1] + oy),
            angle=primitive.angle,
            dimstyle="PF-1-1",
            dxfattribs={"layer": primitive.layer},
        )
        dimension.dimension.dxf.text = primitive.text
        dimension.render()
        return
    if isinstance(primitive, Text):
        if primitive.pdf_only:
            return
        lines = primitive.lines()
        if len(lines) == 1:
            align = {
                "left": TextEntityAlignment.LEFT,
                "center": TextEntityAlignment.CENTER,
                "right": TextEntityAlignment.RIGHT,
            }[primitive.align]
            entity = layout.add_text(
                lines[0],
                dxfattribs={
                    "layer": primitive.layer,
                    "height": primitive.height_mm,
                    "style": "Standard",
                },
            )
            entity.set_placement(
                (primitive.x + ox, primitive.y + oy),
                align=align,
            )
        else:
            mtext = layout.add_mtext(
                "\\P".join(lines),
                dxfattribs={
                    "layer": primitive.layer,
                    "char_height": primitive.height_mm,
                    "style": "Standard",
                },
            )
            mtext.dxf.insert = (primitive.x + ox, primitive.y + oy)
            mtext.dxf.attachment_point = 7  # bottom-left
            if primitive.max_width_mm:
                mtext.dxf.width = primitive.max_width_mm
        return
    raise TypeError(f"Unsupported drawing primitive {type(primitive)!r}.")


def write_connection_dxf(
    result: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Write R2018 DXF sheets to model space and named A3 paper layouts."""

    sheets = build_connection_sheets(result)
    output = Path(path)
    if output.suffix.lower() != ".dxf":
        raise ConnectionDrawingError("Connection DXF path must end in .dxf.")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2018", units=units.MM, setup=True)
    doc.header["$INSUNITS"] = units.MM
    doc.header["$MEASUREMENT"] = 1
    # Open in model space.  Some downstream DXF/DWG viewers ignore paper
    # layouts, which previously made otherwise valid exports appear empty.
    doc.header["$TILEMODE"] = 1
    _add_dxf_layers(doc)
    modelspace = doc.modelspace()
    sheet_spacing = A3_WIDTH_MM + 20.0
    for index, sheet in enumerate(sheets):
        if index == 0 and "Layout1" in doc.layouts:
            doc.layouts.rename("Layout1", sheet.layout_name)
            layout = doc.layouts.get(sheet.layout_name)
        else:
            layout = doc.layouts.new(sheet.layout_name)
        try:
            layout.page_setup(
                size=(A3_WIDTH_MM, A3_HEIGHT_MM),
                margins=(0, 0, 0, 0),
                units="mm",
            )
        except (AttributeError, TypeError, ValueError):
            # Older ezdxf releases still retain a valid paperspace layout; the
            # page attributes below keep A3 metadata explicit.
            layout.dxf.plot_paper_size = (
                f"{A3_WIDTH_MM:.1f} x {A3_HEIGHT_MM:.1f} MM"
            )
        for primitive in sheet.primitives:
            _render_dxf_primitive(layout, primitive)
            _render_dxf_primitive(
                modelspace,
                primitive,
                offset=(index * sheet_spacing, 0.0),
            )
    doc.saveas(output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("ezdxf did not create a non-empty connection DXF.")
    return output.resolve()


def dwg_converter_status() -> dict[str, Any]:
    """Return the selected supported AutoCAD Core Console installation."""

    available = DWG_CONVERTER.is_file()
    product = DWG_CONVERTER.parent.name
    return {
        "available": available,
        "path": str(DWG_CONVERTER),
        "product": product,
        "reason": (
            f"{product} Core Console is available."
            if available
            else "No supported AutoCAD or AutoCAD LT Core Console was found."
        ),
    }


def _concise_converter_output(value: str | None, limit: int = 360) -> str:
    """Collapse console control characters without flooding the UI or logs."""

    # AutoCAD Core Console emits UTF-16-style output on Windows even when
    # subprocess text mode decodes it as the active ANSI encoding.  Removing
    # the interleaved NULs restores readable diagnostics.
    cleaned = re.sub(r"\s+", " ", (value or "").replace("\x00", "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    leading = max(80, limit // 2 - 3)
    trailing = max(80, limit - leading - 5)
    return f"{cleaned[:leading]} ... {cleaned[-trailing:]}"


def write_connection_dwg(
    dxf_path: str | Path,
    dwg_path: str | Path,
) -> Path:
    """Convert one DXF to DWG with the selected AutoCAD Core Console."""

    source = Path(dxf_path).resolve()
    target = Path(dwg_path).resolve()
    if source.suffix.lower() != ".dxf":
        raise ConnectionDrawingError("DWG conversion source must be a .dxf file.")
    if target.suffix.lower() != ".dwg":
        raise ConnectionDrawingError("DWG conversion target must end in .dwg.")
    if not source.is_file() or source.stat().st_size <= 0:
        raise FileNotFoundError(f"DXF source is missing or empty: {source}")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing DWG: {target}")
    if not DWG_CONVERTER.is_file():
        raise FileNotFoundError(
            "No supported AutoCAD or AutoCAD LT Core Console is available. "
            "Checked: "
            + ", ".join(str(path) for path in DWG_CONVERTER_CANDIDATES)
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if any(character in str(target) for character in ("\r", "\n", '"')):
        raise ConnectionDrawingError("DWG target path contains unsupported characters.")

    script_path: Path | None = None
    error_sidecar = target.parent / "acad.err"
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".scr",
            prefix="portal_connection_",
            dir=target.parent,
            encoding="utf-8",
            newline="\n",
            delete=False,
        ) as script:
            script.write(
                "_.FILEDIA\n0\n"
                "_.CMDDIA\n0\n"
                "_.TILEMODE\n1\n"
                "_.ZOOM\n_E\n"
                "_.SAVEAS\n2018\n"
                f'"{target}"\n'
                "_.QUIT\n"
            )
            script_path = Path(script.name)
        completed = subprocess.run(
            [
                str(DWG_CONVERTER),
                "/i",
                str(source),
                "/s",
                str(script_path),
                "/l",
                "en-US",
            ],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(target.parent),
        )
        if completed.returncode != 0:
            message = _concise_converter_output(
                completed.stderr or completed.stdout
            )
            raise RuntimeError(
                "AutoCAD Core Console failed to convert DXF to DWG"
                + (f": {message}" if message else ".")
            )
        if not target.is_file() or target.stat().st_size <= 0:
            message = _concise_converter_output(
                completed.stderr or completed.stdout
            )
            raise RuntimeError(
                "AutoCAD Core Console reported success but produced no non-empty DWG"
                + (f": {message}" if message else ".")
            )
        return target
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            "AutoCAD Core Console exceeded the 180 second DWG conversion timeout."
        ) from exc
    finally:
        if script_path is not None and script_path.is_file():
            script_path.unlink()
        if error_sidecar.is_file():
            try:
                error_sidecar.unlink()
            except OSError:
                # A locked diagnostic must not hide the converter result.
                pass
