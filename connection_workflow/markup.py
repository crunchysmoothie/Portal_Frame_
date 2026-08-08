"""Coordinated fabrication-review SVG sheets for portal connections.

The drawings are generated from the same connection geometry and detailed
checks used by the calculation report. They intentionally distinguish
calculated dimensions from anchor information that is still required.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Mapping

from databases import load_member_database


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIMENSION_COLOUR = "#164BDB"
LINE_COLOUR = "#172321"
MUTED_COLOUR = "#526562"
WARNING_COLOUR = "#A35D00"


def _section(designation: str) -> Mapping[str, Any]:
    database = load_member_database(PROJECT_ROOT / "databases" / "member_database.csv")
    for family in database.values():
        if designation in family:
            return family[designation]
    return {"h": 250.0, "b": 150.0, "tw": 6.0, "tf": 10.0, "r1": 0.0}


def _n(value: Any, digits: int = 0) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _svg_defs() -> str:
    return f"""
<defs>
  <marker id="dim-arrow" markerWidth="8" markerHeight="8" refX="4" refY="4"
          orient="auto-start-reverse" markerUnits="strokeWidth">
    <path d="M 8 1 L 0 4 L 8 7" fill="none" stroke="{DIMENSION_COLOUR}"
          stroke-width="1.2"/>
  </marker>
  <marker id="leader-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5"
          orient="auto">
    <path d="M 0 0 L 9 4.5 L 0 9 Z" fill="{LINE_COLOUR}"/>
  </marker>
  <pattern id="section-hatch" width="8" height="8" patternUnits="userSpaceOnUse"
           patternTransform="rotate(45)">
    <line x1="0" y1="0" x2="0" y2="8" stroke="#778683" stroke-width="1"/>
  </pattern>
</defs>
<style>
  text{{font-family:Arial,sans-serif;fill:{LINE_COLOUR}}}
  .object{{fill:none;stroke:{LINE_COLOUR};stroke-width:2.3}}
  .heavy{{fill:none;stroke:{LINE_COLOUR};stroke-width:4}}
  .thin{{fill:none;stroke:{LINE_COLOUR};stroke-width:1.3}}
  .centre{{fill:none;stroke:#71817E;stroke-width:1;stroke-dasharray:12 5 2 5}}
  .hidden{{fill:none;stroke:#71817E;stroke-width:1.2;stroke-dasharray:7 5}}
  .dim{{fill:none;stroke:{DIMENSION_COLOUR};stroke-width:1.25;
        marker-start:url(#dim-arrow);marker-end:url(#dim-arrow)}}
  .ext{{fill:none;stroke:{DIMENSION_COLOUR};stroke-width:1}}
  .dimtext{{font-size:18px;fill:{DIMENSION_COLOUR}}}
  .label{{font-size:19px;font-weight:700}}
  .note{{font-size:17px}}
  .small{{font-size:14px}}
  .tiny{{font-size:12px}}
  .title{{font-size:27px;font-weight:700}}
  .subtitle{{font-size:21px;font-weight:700}}
  .warning{{fill:{WARNING_COLOUR};font-weight:700}}
</style>"""


def _dim_h(
    x1: float,
    x2: float,
    y: float,
    object_y: float,
    label: str,
) -> str:
    mid = (x1 + x2) / 2.0
    return (
        f'<line class="ext" x1="{x1:.1f}" y1="{object_y:.1f}" '
        f'x2="{x1:.1f}" y2="{y:.1f}"/>'
        f'<line class="ext" x1="{x2:.1f}" y1="{object_y:.1f}" '
        f'x2="{x2:.1f}" y2="{y:.1f}"/>'
        f'<line class="dim" x1="{x1:.1f}" y1="{y:.1f}" '
        f'x2="{x2:.1f}" y2="{y:.1f}"/>'
        f'<text class="dimtext" x="{mid:.1f}" y="{y - 7:.1f}" '
        f'text-anchor="middle">{escape(label)}</text>'
    )


def _dim_v(
    y1: float,
    y2: float,
    x: float,
    object_x: float,
    label: str,
) -> str:
    mid = (y1 + y2) / 2.0
    return (
        f'<line class="ext" x1="{object_x:.1f}" y1="{y1:.1f}" '
        f'x2="{x:.1f}" y2="{y1:.1f}"/>'
        f'<line class="ext" x1="{object_x:.1f}" y1="{y2:.1f}" '
        f'x2="{x:.1f}" y2="{y2:.1f}"/>'
        f'<line class="dim" x1="{x:.1f}" y1="{y1:.1f}" '
        f'x2="{x:.1f}" y2="{y2:.1f}"/>'
        f'<text class="dimtext" x="{x - 7:.1f}" y="{mid:.1f}" '
        f'text-anchor="middle" transform="rotate(-90 {x - 7:.1f} {mid:.1f})">'
        f'{escape(label)}</text>'
    )


def _leader(
    target_x: float,
    target_y: float,
    elbow_x: float,
    elbow_y: float,
    text_x: float,
    text_y: float,
    lines: list[str],
    *,
    text_class: str = "note",
) -> str:
    text = "".join(
        f'<tspan x="{text_x:.1f}" dy="{0 if index == 0 else 20}">'
        f'{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return (
        f'<polyline class="thin" points="{text_x - 8:.1f},{text_y - 5:.1f} '
        f'{elbow_x:.1f},{elbow_y:.1f} {target_x:.1f},{target_y:.1f}" '
        'marker-end="url(#leader-arrow)"/>'
        f'<text class="{escape(text_class)}" x="{text_x:.1f}" '
        f'y="{text_y:.1f}">{text}</text>'
    )


def _selected_weld(weld: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not weld:
        return {}
    return weld.get("selected_weld", weld)


def _weld_label(weld: Mapping[str, Any] | None) -> str:
    selected = _selected_weld(weld)
    if not selected:
        return "WELD: NOT REQUIRED"
    weld_type = str(selected.get("weld_type", "WELD")).upper()
    size = selected.get(
        "provided_size_mm",
        selected.get("equivalent_fillet_size_mm", 0.0),
    )
    if "JOINT PENETRATION" in weld_type:
        return f"CJP WELD (EQUIV. {_n(size)} mm FILLET)"
    return f"{_n(size)} mm {weld_type}"


def _i_plan(
    cx: float,
    cy: float,
    depth: float,
    width: float,
    web: float,
    flange: float,
    scale: float,
) -> str:
    d = depth * scale
    b = width * scale
    tw = max(web * scale, 4.0)
    tf = max(flange * scale, 5.0)
    x = cx - d / 2.0
    y = cy - b / 2.0
    return "".join([
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{tf:.1f}" height="{b:.1f}" '
        'fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
        f'<rect x="{x + d - tf:.1f}" y="{y:.1f}" width="{tf:.1f}" '
        f'height="{b:.1f}" fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
        f'<rect x="{cx - tw / 2.0:.1f}" y="{y:.1f}" width="{tw:.1f}" '
        f'height="{b:.1f}" fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
    ])


def _base_plate_sheet(
    support: Mapping[str, Any],
    detail: Mapping[str, Any],
) -> str:
    plate = support["plate"]
    bolts = support["holding_down_bolts"]
    layout = bolts["layout"]
    stiffener = support.get("stiffeners", {})
    section = _section(str(support.get("column_section", "")))
    length = float(plate["length_mm"])
    width = float(plate["width_mm"])
    thickness = float(plate["provided_thickness_mm"])
    scale = min(480.0 / max(length, 1.0), 350.0 / max(width, 1.0))
    px, py = 105.0, 205.0
    pw, ph = length * scale, width * scale
    cx, cy = px + pw / 2.0, py + ph / 2.0
    bolt_points = layout.get("coordinates_from_plate_centre_mm", [])
    bolt_svg = []
    for index, point in enumerate(bolt_points, start=1):
        bx = cx + float(point["x"]) * scale
        by = cy + float(point["y"]) * scale
        bolt_svg.append(
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="7.5" '
            'fill="#fff" stroke="#172321" stroke-width="2.4"/>'
            f'<line class="thin" x1="{bx - 11:.1f}" y1="{by:.1f}" '
            f'x2="{bx + 11:.1f}" y2="{by:.1f}"/>'
            f'<line class="thin" x1="{bx:.1f}" y1="{by - 11:.1f}" '
            f'x2="{bx:.1f}" y2="{by + 11:.1f}"/>'
            f'<text class="small" x="{bx + 10:.1f}" y="{by - 9:.1f}">{index}</text>'
        )
    x_coords = sorted({cx + float(point["x"]) * scale for point in bolt_points})
    y_coords = sorted({cy + float(point["y"]) * scale for point in bolt_points})
    left_bolt = x_coords[0] if x_coords else px
    right_bolt = x_coords[-1] if x_coords else px + pw
    top_bolt = y_coords[0] if y_coords else py
    bottom_bolt = y_coords[-1] if y_coords else py + ph
    plate_chain = "".join([
        _dim_h(px, px + pw, py - 82, py, _n(length)),
        _dim_h(px, left_bolt, py - 38, py, _n(layout["end_distance_mm"])),
        _dim_h(
            left_bolt,
            right_bolt,
            py - 38,
            py,
            _n(layout["pitch_mm"]),
        ),
        _dim_h(
            right_bolt,
            px + pw,
            py - 38,
            py,
            _n(layout["end_distance_mm"]),
        ),
        _dim_v(py, py + ph, px - 78, px, _n(width)),
        _dim_v(
            py,
            top_bolt,
            px + pw + 45,
            px + pw,
            _n(layout["edge_distance_mm"]),
        ),
        _dim_v(
            top_bolt,
            bottom_bolt,
            px + pw + 45,
            px + pw,
            _n(layout["gauge_mm"]),
        ),
        _dim_v(
            bottom_bolt,
            py + ph,
            px + pw + 45,
            px + pw,
            _n(layout["edge_distance_mm"]),
        ),
    ])
    column_svg = _i_plan(
        cx,
        cy,
        float(section["h"]),
        float(section["b"]),
        float(section["tw"]),
        float(section["tf"]),
        scale,
    )
    bolt_callout = (
        f"{int(layout['bolt_count'])} - M{_n(layout['diameter_mm'])} "
        f"GRADE {bolts.get('steel_grade', '8.8')} HOLDING-DOWN BOLTS"
    )
    plan_leaders = "".join([
        _leader(
            right_bolt,
            top_bolt,
            625,
            235,
            690,
            218,
            [bolt_callout, f"HOLES DIA {_n(layout['hole_diameter_mm'])}"],
        ),
        _leader(
            cx,
            cy,
            615,
            420,
            690,
            402,
            [f"COLUMN {support.get('column_section', '')}", "CENTRED ON PLATE"],
        ),
    ])

    # Section A-A through the column depth.
    sx, sy = 900.0, 490.0
    section_scale = min(440.0 / max(length, 1.0), 1.2)
    section_w = length * section_scale
    section_left = sx - section_w / 2.0
    plate_draw_t = max(thickness * section_scale, 10.0)
    col_draw_w = float(section["h"]) * section_scale
    col_left = sx - col_draw_w / 2.0
    section_parts = [
        f'<rect x="{section_left:.1f}" y="{sy:.1f}" width="{section_w:.1f}" '
        f'height="{plate_draw_t:.1f}" fill="url(#section-hatch)" '
        'stroke="#172321" stroke-width="2.5"/>',
        f'<rect x="{col_left:.1f}" y="{sy - 265:.1f}" width="{max(float(section["tf"]) * section_scale, 8):.1f}" '
        f'height="265" fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
        f'<rect x="{sx - max(float(section["tw"]) * section_scale, 5) / 2:.1f}" '
        f'y="{sy - 265:.1f}" width="{max(float(section["tw"]) * section_scale, 5):.1f}" '
        f'height="265" fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
        f'<rect x="{col_left + col_draw_w - max(float(section["tf"]) * section_scale, 8):.1f}" '
        f'y="{sy - 265:.1f}" width="{max(float(section["tf"]) * section_scale, 8):.1f}" '
        f'height="265" fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
    ]
    if stiffener.get("required"):
        sh = float(stiffener.get("height_mm", 0.0)) * section_scale
        sl = float(stiffener.get("length_mm", 0.0)) * section_scale
        section_parts.extend([
            f'<rect data-role="flat-stiffener" x="{col_left - sl:.1f}" '
            f'y="{sy - sh:.1f}" width="{sl:.1f}" height="{sh:.1f}" '
            'fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
            f'<rect data-role="flat-stiffener" x="{col_left + col_draw_w:.1f}" '
            f'y="{sy - sh:.1f}" width="{sl:.1f}" height="{sh:.1f}" '
            'fill="url(#section-hatch)" stroke="#172321" stroke-width="2"/>',
        ])
    # Anchor rods are indicative because embedment is an explicit input.
    for bx in (section_left + float(layout["end_distance_mm"]) * section_scale,
               section_left + section_w - float(layout["end_distance_mm"]) * section_scale):
        section_parts.append(
            f'<line class="hidden" x1="{bx:.1f}" y1="{sy - 28:.1f}" '
            f'x2="{bx:.1f}" y2="{sy + 175:.1f}"/>'
            f'<rect x="{bx - 12:.1f}" y="{sy - 34:.1f}" width="24" height="8" '
            'fill="none" stroke="#172321" stroke-width="2"/>'
            f'<path class="hidden" d="M {bx:.1f} {sy + 175:.1f} '
            f'l 28 0 l 0 -18"/>'
        )
    section_dims = "".join([
        _dim_h(section_left, section_left + section_w, sy + 190, sy + plate_draw_t, _n(length)),
    ])
    if stiffener.get("required"):
        section_dims += _dim_v(
            sy - float(stiffener["height_mm"]) * section_scale,
            sy,
            section_left - 75,
            col_left,
            _n(stiffener["height_mm"]),
        )
    base_weld = detail.get("column_to_base_plate_weld", {})
    stiffener_weld = detail.get("stiffener_checks", {}).get("weld")
    section_leaders = "".join([
        _leader(
            sx,
            sy - 5,
            1205,
            350,
            1260,
            335,
            [_weld_label(base_weld), "COLUMN TO BASE PLATE"],
        ),
        _leader(
            section_left
            + section_w
            - float(layout["end_distance_mm"]) * section_scale,
            sy + 120,
            1205,
            650,
            1260,
            630,
            [
                f"M{_n(layout['diameter_mm'])} ANCHOR",
                "EMBEDMENT: INPUT REQUIRED",
                "CONCRETE CHECK: INPUT REQUIRED",
            ],
        ),
        _leader(
            section_left + section_w - 8,
            sy + plate_draw_t / 2.0,
            1205,
            545,
            1260,
            530,
            [f"BASE PLATE {_n(length)} x {_n(width)} x {_n(thickness)}"],
        ),
    ])
    if stiffener.get("required"):
        section_leaders += _leader(
            col_left,
            sy - 55,
            1205,
            415,
            1260,
            400,
            [_weld_label(stiffener_weld), "STIFFENER BOTH SIDES"],
        )

    # Individual flat-plate stiffener detail. Calculation checks remain in the
    # separate connection report and are intentionally not repeated here.
    detail_x, detail_y = 155.0, 760.0
    if stiffener.get("required"):
        st_h = 205.0
        st_l = 235.0
        stiffener_detail = (
            f'<rect data-role="flat-stiffener-detail" x="{detail_x:.1f}" '
            f'y="{detail_y:.1f}" width="{st_l:.1f}" height="{st_h:.1f}" '
            'fill="url(#section-hatch)" stroke="#172321" stroke-width="2.5"/>'
            + _dim_v(
                detail_y,
                detail_y + st_h,
                detail_x - 40,
                detail_x,
                _n(stiffener["height_mm"]),
            )
            + _dim_h(
                detail_x,
                detail_x + st_l,
                detail_y + st_h + 45,
                detail_y + st_h,
                _n(stiffener["length_mm"]),
            )
            + f'<text class="note" x="{detail_x + 35:.1f}" '
            f'y="{detail_y + st_h + 80:.1f}">'
            f'{int(stiffener.get("count", 0))} - PL{_n(stiffener.get("provided_thickness_mm"))}'
            '</text>'
        )
    else:
        stiffener_detail = (
            f'<text class="note" x="{detail_x:.1f}" y="{detail_y + 65:.1f}">'
            'NO BASE STIFFENERS REQUIRED</text>'
        )
    notes = [
        "1. ALL DIMENSIONS ARE IN mm.",
        "2. HOLDING-DOWN BOLTS ARE LOCATED BY CALCULATED CENTRES.",
        "3. ANCHOR EMBEDMENT AND CONCRETE ANCHORAGE REQUIRE INPUT.",
        "4. STIFFENERS, WHEN SHOWN, ARE FLAT RECTANGULAR PLATES.",
        "5. VERIFY GROUT, PEDESTAL AND ERECTION DETAILS.",
        "6. DO NOT SCALE. USE FIGURED DIMENSIONS ONLY.",
    ]
    note_text = "".join(
        f'<text class="small" x="650" y="{805 + index * 30}">{escape(line)}</text>'
        for index, line in enumerate(notes)
    )
    return "".join([
        '<svg class="drawing-sheet" xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 1600 1100" role="img" '
        f'aria-label="Detailed base plate drawing {escape(str(support.get("support", "")))}">',
        '<rect width="1600" height="1100" fill="#fff"/>',
        _svg_defs(),
        f'<text class="title" x="55" y="48">BASE PLATE {escape(str(support.get("support", "")))} - GENERAL ARRANGEMENT AND DETAILS</text>',
        f'<text class="small" x="55" y="76">COLUMN {escape(str(support.get("column_section", "")))} | CONNECTION MARKUP | NOT FOR FABRICATION</text>',
        '<line class="heavy" x1="45" y1="92" x2="1555" y2="92"/>',
        f'<rect class="object" x="{px:.1f}" y="{py:.1f}" width="{pw:.1f}" height="{ph:.1f}"/>',
        f'<line class="centre" x1="{cx:.1f}" y1="{py - 20:.1f}" x2="{cx:.1f}" y2="{py + ph + 20:.1f}"/>',
        f'<line class="centre" x1="{px - 20:.1f}" y1="{cy:.1f}" x2="{px + pw + 20:.1f}" y2="{cy:.1f}"/>',
        column_svg,
        *bolt_svg,
        plate_chain,
        plan_leaders,
        f'<text class="subtitle" x="{cx:.1f}" y="620" text-anchor="middle">PLAN OF BASE PLATE</text>',
        '<line class="thin" x1="80" y1="630" x2="650" y2="630"/>',
        *section_parts,
        section_dims,
        section_leaders,
        '<text class="subtitle" x="900" y="725" text-anchor="middle">SECTION A-A</text>',
        '<line class="thin" x1="700" y1="735" x2="1100" y2="735"/>',
        stiffener_detail,
        (
            '<text class="subtitle" x="275" y="1040" text-anchor="middle">'
            'FLAT-PLATE STIFFENER DETAIL B</text>'
            if stiffener.get("required")
            else '<text class="subtitle" x="275" y="785" text-anchor="middle">'
            'BASE STIFFENERS</text>'
        ),
        note_text,
        '<rect class="thin" x="620" y="780" width="935" height="230"/>',
        '<text class="label" x="650" y="770">MARKUP NOTES</text>',
        '<rect class="heavy" x="35" y="25" width="1530" height="1040"/>',
        '</svg>',
    ])


def _haunch_sheet(
    location: Mapping[str, Any],
    detail: Mapping[str, Any],
) -> str:
    connection = location["connection"]
    plate = connection["plate"]
    bolts = connection["bolts"]
    stiffener = connection.get("stiffeners", {})
    rafter = _section(str(location.get("rafter_section", "")))
    column = _section(str(location.get("column_section", "")))
    plate_h = float(plate["height_mm"])
    plate_w = float(plate["width_mm"])
    plate_t = float(plate["provided_thickness_mm"])
    rows = int(bolts["row_count"])
    ep_scale = min(300.0 / max(plate_w, 1.0), 470.0 / max(plate_h, 1.0))
    ex, ey = 920.0, 160.0
    ew, eh = plate_w * ep_scale, plate_h * ep_scale
    ecx, ecy = ex + ew / 2.0, ey + eh / 2.0
    pitch = float(bolts["pitch_mm"]) * ep_scale
    gauge = float(bolts["gauge_mm"]) * ep_scale
    first_y = ecy - pitch * (rows - 1) / 2.0
    bolt_svg = []
    for row in range(rows):
        for sign in (-1.0, 1.0):
            bx = ecx + sign * gauge / 2.0
            by = first_y + row * pitch
            bolt_svg.append(
                f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="7" '
                'fill="#fff" stroke="#172321" stroke-width="2.2"/>'
                f'<line class="thin" x1="{bx - 10:.1f}" y1="{by:.1f}" '
                f'x2="{bx + 10:.1f}" y2="{by:.1f}"/>'
                f'<line class="thin" x1="{bx:.1f}" y1="{by - 10:.1f}" '
                f'x2="{bx:.1f}" y2="{by + 10:.1f}"/>'
            )
    left_bolt, right_bolt = ecx - gauge / 2.0, ecx + gauge / 2.0
    top_bolt, bottom_bolt = first_y, first_y + (rows - 1) * pitch
    endplate_dims = "".join([
        _dim_h(ex, ex + ew, ey - 58, ey, _n(plate_w)),
        _dim_h(
            ex,
            left_bolt,
            ey - 25,
            ey,
            _n(bolts["edge_distance_mm"]),
        ),
        _dim_h(
            left_bolt,
            right_bolt,
            ey - 25,
            ey,
            _n(bolts["gauge_mm"]),
        ),
        _dim_h(
            right_bolt,
            ex + ew,
            ey - 25,
            ey,
            _n(bolts["edge_distance_mm"]),
        ),
        _dim_v(ey, ey + eh, ex - 75, ex, _n(plate_h)),
        _dim_v(
            ey,
            top_bolt,
            ex + ew + 42,
            ex + ew,
            _n(bolts["end_distance_mm"]),
        ),
        _dim_v(
            top_bolt,
            bottom_bolt,
            ex + ew + 42,
            ex + ew,
            f"{rows - 1} @ {_n(bolts['pitch_mm'])}",
        ),
        _dim_v(
            bottom_bolt,
            ey + eh,
            ex + ew + 42,
            ex + ew,
            _n(bolts["end_distance_mm"]),
        ),
    ])
    bolt_callout = (
        f"{int(bolts['bolt_count'])} - M{_n(bolts['diameter_mm'])} "
        "GRADE 8.8 BOLTS"
    )
    endplate_leader = _leader(
        right_bolt,
        top_bolt,
        1245,
        245,
        1295,
        225,
        [
            f"{int(bolts['bolt_count'])} - M{_n(bolts['diameter_mm'])} GRADE 8.8",
            f"BOLTS; HOLES DIA {_n(bolts['hole_diameter_mm'])}",
        ],
    )

    # General arrangement: column, end plate, sloping rafter and haunch.
    joint_x = 270.0
    plate_x = joint_x + 32.0
    plate_top = 175.0
    plate_bottom = 620.0
    joint_y = 300.0
    arrangement = [
        '<rect x="150" y="125" width="120" height="540" fill="none" '
        'stroke="#172321" stroke-width="3"/>',
        '<line class="heavy" x1="170" y1="125" x2="170" y2="665"/>',
        '<line class="heavy" x1="250" y1="125" x2="250" y2="665"/>',
        f'<rect x="{plate_x:.1f}" y="{plate_top:.1f}" width="15" '
        f'height="{plate_bottom - plate_top:.1f}" fill="url(#section-hatch)" '
        'stroke="#172321" stroke-width="2.4"/>',
        f'<path class="heavy" d="M {plate_x + 15:.1f} {joint_y:.1f} '
        'L 730 215"/>',
        f'<path class="heavy" d="M {plate_x + 15:.1f} {joint_y + 72:.1f} '
        'L 730 287"/>',
        f'<path d="M {plate_x + 15:.1f} {joint_y + 72:.1f} '
        f'L {plate_x + 15:.1f} {joint_y + 295:.1f} L 650 302 Z" '
        'fill="none" stroke="#172321" stroke-width="3"/>',
        f'<line class="centre" x1="{plate_x - 20:.1f}" y1="{joint_y + 36:.1f}" '
        'x2="755" y2="258"/>',
    ]
    # Bolt heads in side view.
    for row in range(rows):
        by = plate_top + (
            float(bolts["end_distance_mm"])
            + row * float(bolts["pitch_mm"])
        ) / plate_h * (plate_bottom - plate_top)
        arrangement.append(
            f'<line class="thin" x1="{plate_x - 32:.1f}" y1="{by:.1f}" '
            f'x2="{plate_x + 32:.1f}" y2="{by:.1f}"/>'
            f'<rect x="{plate_x - 36:.1f}" y="{by - 7:.1f}" width="10" height="14" '
            'fill="#fff" stroke="#172321" stroke-width="2"/>'
            f'<rect x="{plate_x + 28:.1f}" y="{by - 7:.1f}" width="10" height="14" '
            'fill="#fff" stroke="#172321" stroke-width="2"/>'
        )
    if stiffener.get("required"):
        arrangement.extend([
            f'<rect data-role="flat-stiffener" x="170" y="{joint_y - 7:.1f}" '
            'width="80" height="14" fill="url(#section-hatch)" '
            'stroke="#172321" stroke-width="2"/>',
            f'<rect data-role="flat-stiffener" x="170" y="{joint_y + 65:.1f}" '
            'width="80" height="14" fill="url(#section-hatch)" '
            'stroke="#172321" stroke-width="2"/>',
        ])
    joint_leaders = "".join([
        _leader(
            480,
            400,
            520,
            490,
            550,
            485,
            [
                f"TAPERED HAUNCH L={_n(location.get('length_mm'))}",
                f"ADDED DEPTH {_n(location.get('added_depth_mm'))}",
            ],
        ),
        _leader(
            plate_x + 8,
            560,
            350,
            610,
            390,
            605,
            [f"END PLATE {_n(plate_h)} x {_n(plate_w)} x {_n(plate_t)}"],
        ),
    ])
    if stiffener.get("required"):
        joint_leaders += _leader(
            210,
            joint_y,
            350,
            160,
            400,
            150,
            [
                f"{int(stiffener.get('count', 0))} - PL{_n(stiffener.get('provided_thickness_mm'))}",
                "FLAT RECTANGULAR STIFFENERS",
            ],
        )

    # Section A-A through the bolted end plate.
    section_view = "".join([
        '<rect x="115" y="790" width="55" height="180" fill="url(#section-hatch)" '
        'stroke="#172321" stroke-width="2"/>',
        '<rect x="225" y="780" width="16" height="200" fill="url(#section-hatch)" '
        'stroke="#172321" stroke-width="2"/>',
        '<rect x="241" y="830" width="230" height="32" fill="url(#section-hatch)" '
        'stroke="#172321" stroke-width="2"/>',
        '<line class="centre" x1="90" y1="846" x2="500" y2="846"/>',
        '<line class="thin" x1="150" y1="820" x2="270" y2="820"/>',
        '<rect x="132" y="811" width="18" height="18" fill="#fff" '
        'stroke="#172321" stroke-width="2"/>',
        '<rect x="270" y="811" width="18" height="18" fill="#fff" '
        'stroke="#172321" stroke-width="2"/>',
        '<line class="thin" x1="150" y1="930" x2="270" y2="930"/>',
        '<rect x="132" y="921" width="18" height="18" fill="#fff" '
        'stroke="#172321" stroke-width="2"/>',
        '<rect x="270" y="921" width="18" height="18" fill="#fff" '
        'stroke="#172321" stroke-width="2"/>',
    ])
    weld = detail.get("end_plate_weld", {})
    section_view += _leader(
        250,
        840,
        485,
        815,
        515,
        805,
        [_weld_label(weld), "RAFTER/HAUNCH TO END PLATE"],
        text_class="small",
    )
    section_view += _leader(
        208,
        820,
        485,
        905,
        515,
        895,
        [bolt_callout],
        text_class="small",
    )
    section_view += _leader(
        233,
        945,
        485,
        975,
        515,
        965,
        [f"END PLATE PL{_n(plate_t)}"],
        text_class="small",
    )

    # Stiffener detail.
    stiff_x, stiff_y = 820.0, 800.0
    if stiffener.get("required"):
        stiff_detail = (
            f'<rect data-role="flat-stiffener-detail" x="{stiff_x:.1f}" '
            f'y="{stiff_y:.1f}" width="210" height="175" '
            'fill="url(#section-hatch)" stroke="#172321" stroke-width="2.5"/>'
            + _dim_v(
                stiff_y,
                stiff_y + 175,
                stiff_x - 38,
                stiff_x,
                _n(stiffener["height_mm"]),
            )
            + _dim_h(
                stiff_x,
                stiff_x + 210,
                stiff_y + 215,
                stiff_y + 175,
                _n(stiffener["length_mm"]),
            )
            + f'<text class="note" x="{stiff_x + 55:.1f}" y="{stiff_y + 145:.1f}">'
            f'{int(stiffener.get("count", 0))} - PL{_n(stiffener.get("provided_thickness_mm"))}</text>'
        )
    else:
        stiff_detail = (
            f'<rect class="hidden" x="{stiff_x:.1f}" y="{stiff_y:.1f}" '
            'width="250" height="175"/>'
            f'<text class="note" x="{stiff_x + 20:.1f}" y="{stiff_y + 90:.1f}">'
            'NO STIFFENERS REQUIRED</text>'
        )
    stiff_weld = detail.get("stiffener_checks", {}).get("weld")
    if stiffener.get("required"):
        stiff_detail += (
            f'<rect x="{stiff_x + 18:.1f}" y="{stiff_y + 42:.1f}" '
            'width="174" height="58" fill="#fff" opacity="0.88"/>'
            f'<text class="small" x="{stiff_x + 105:.1f}" '
            f'y="{stiff_y + 65:.1f}" text-anchor="middle">'
            f'{escape(_weld_label(stiff_weld))}</text>'
            f'<text class="small" x="{stiff_x + 105:.1f}" '
            f'y="{stiff_y + 88:.1f}" text-anchor="middle">'
            'WELD BOTH SIDES</text>'
        )
    notes = [
        "1. ALL DIMENSIONS ARE IN mm.",
        "2. STIFFENERS ARE FLAT RECTANGULAR PLATES.",
        "3. THE TAPERED HAUNCH IS A SEPARATE COMPONENT.",
        "4. BOLT CENTRES AND PLATE EDGES ARE CALCULATED.",
        "5. DO NOT SCALE. USE FIGURED DIMENSIONS ONLY.",
    ]
    note_text = "".join(
        f'<text class="tiny" x="1175" y="{815 + index * 34}">'
        f'{escape(line)}</text>'
        for index, line in enumerate(notes)
    )
    return "".join([
        '<svg class="drawing-sheet" xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 1600 1100" role="img" '
        f'aria-label="Detailed haunch connection drawing {escape(str(location.get("location", "")))}">',
        '<rect width="1600" height="1100" fill="#fff"/>',
        _svg_defs(),
        f'<text class="title" x="55" y="48">{escape(str(location.get("location", "HAUNCH")).upper())} - BOLTED END-PLATE CONNECTION</text>',
        f'<text class="small" x="55" y="76">COLUMN {escape(str(location.get("column_section", "")))} | RAFTER {escape(str(location.get("rafter_section", "")))} | CONNECTION MARKUP | NOT FOR FABRICATION</text>',
        '<line class="heavy" x1="45" y1="92" x2="1555" y2="92"/>',
        *arrangement,
        joint_leaders,
        '<text class="subtitle" x="390" y="690" text-anchor="middle">CONNECTION ELEVATION</text>',
        '<line class="thin" x1="80" y1="700" x2="740" y2="700"/>',
        f'<rect class="object" x="{ex:.1f}" y="{ey:.1f}" width="{ew:.1f}" height="{eh:.1f}"/>',
        f'<line class="centre" x1="{ecx:.1f}" y1="{ey - 15:.1f}" x2="{ecx:.1f}" y2="{ey + eh + 15:.1f}"/>',
        f'<line class="centre" x1="{ex - 15:.1f}" y1="{ecy:.1f}" x2="{ex + ew + 15:.1f}" y2="{ecy:.1f}"/>',
        *bolt_svg,
        endplate_dims,
        endplate_leader,
        f'<text class="subtitle" x="{ecx:.1f}" y="710" text-anchor="middle">END-PLATE ELEVATION</text>',
        '<line class="thin" x1="830" y1="720" x2="1290" y2="720"/>',
        section_view,
        '<text class="subtitle" x="285" y="765" text-anchor="middle">SECTION A-A - BOLTED JOINT</text>',
        '<line class="thin" x1="75" y1="775" x2="510" y2="775"/>',
        stiff_detail,
        '<text class="subtitle" x="925" y="765" text-anchor="middle">FLAT-PLATE STIFFENER DETAIL B</text>',
        '<line class="thin" x1="770" y1="775" x2="1080" y2="775"/>',
        '<rect class="thin" x="1145" y="780" width="410" height="230"/>',
        '<text class="label" x="1175" y="770">MARKUP NOTES</text>',
        note_text,
        '<rect class="heavy" x="35" y="25" width="1530" height="1040"/>',
        '</svg>',
    ])


def write_connection_markup_html(
    result: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Write coordinated dimensioned connection sheets as printable HTML."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    detailed = result.get("detailed_checks", {})
    base_details = {
        str(item.get("support", "")): item
        for item in detailed.get("base_plates", {}).get("supports", [])
    }
    haunch_details = {
        str(item.get("location", "")): item
        for item in detailed.get("haunch_connections", {}).get("locations", [])
    }
    sheets = []
    for support in result.get("base_plates", {}).get("supports", []):
        if support.get("plate") and support.get("holding_down_bolts", {}).get("layout"):
            sheets.append(
                _base_plate_sheet(
                    support,
                    base_details.get(str(support.get("support", "")), {}),
                )
            )
    for location in result.get("haunch_connections", {}).get("locations", []):
        if location.get("connection", {}).get("plate"):
            sheets.append(
                _haunch_sheet(
                    location,
                    haunch_details.get(str(location.get("location", "")), {}),
                )
            )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Portal-frame connection drawing sheets</title>
<style>
body{{font-family:Arial,sans-serif;margin:20px;color:#172321;background:#EEF2F1}}
main{{max-width:1600px;margin:auto}}
.notice{{background:#FFF3D6;border-left:5px solid #A35D00;padding:14px;margin:16px 0}}
.drawing-sheet{{display:block;width:100%;height:auto;background:#fff;
box-shadow:0 2px 10px #8B999755;margin:20px 0 34px}}
@media print{{
  @page{{size:A3 landscape;margin:8mm}}
  body{{margin:0;background:#fff}}
  h1,.intro,.notice{{display:none}}
  .drawing-sheet{{box-shadow:none;margin:0;page-break-after:always}}
}}
</style></head><body><main>
<h1>Portal-frame connection drawing sheets</h1>
<p class="intro">Coordinated plan, elevation, section and component details
generated directly from the connection calculations.</p>
<div class="notice"><strong>Calculation-review markup — not for fabrication.</strong>
Dimensions shown are calculated. Items identified as INPUT REQUIRED, including
concrete anchor embedment and breakout, must be resolved before issue.</div>
{''.join(sheets) or '<p>No connection drawing sheets are available.</p>'}
</main></body></html>"""
    output.write_text(document, encoding="utf-8")
    return output
