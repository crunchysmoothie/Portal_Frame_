"""Tapered rafter-haunch properties and PyNite section assignment.

The haunch is treated as a cut length of the selected rafter welded below the
rafter.  PyNite physical members retain their original names and loads, while
their automatically generated sub-members receive constant properties sampled
at the sub-member midpoint.  Eight sub-members per haunch zone give a stable,
auditable approximation without replacing PyNite's beam formulation.
"""

from __future__ import annotations

from functools import lru_cache
import math
from typing import Any, Callable, Mapping

from Pynite.PhysMember import PhysMember


HAUNCH_SEGMENTS = 8
_TOLERANCE_MM = 1e-6


def _rect_plastic_modulus_about_x(
    width: float, y_bottom: float, y_top: float, plastic_axis: float
) -> float:
    """Return ``integral(abs(y-axis) dA)`` for one horizontal rectangle."""

    if y_top <= y_bottom or width <= 0:
        return 0.0
    if plastic_axis <= y_bottom:
        return width * (
            (y_top**2 - y_bottom**2) / 2
            - plastic_axis * (y_top - y_bottom)
        )
    if plastic_axis >= y_top:
        return width * (
            plastic_axis * (y_top - y_bottom)
            - (y_top**2 - y_bottom**2) / 2
        )
    return width * (
        ((plastic_axis - y_bottom) ** 2 + (y_top - plastic_axis) ** 2) / 2
    )


def _plastic_axis(rectangles: list[tuple[float, float, float]]) -> float:
    total_area = sum(width * (top - bottom) for width, bottom, top in rectangles)
    target = total_area / 2
    low = min(bottom for _, bottom, _ in rectangles)
    high = max(top for _, _, top in rectangles)
    for _ in range(80):
        middle = (low + high) / 2
        area_below = sum(
            width * max(0.0, min(top, middle) - bottom)
            for width, bottom, top in rectangles
        )
        if area_below < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _property_key(base: Mapping[str, Any], added_depth_mm: float) -> tuple:
    fields = (
        "Designation", "m", "h", "b", "tw", "tf", "r1", "hw", "A", "Ix",
        "Zex", "Zplx", "rx", "Iy", "Zey", "Zply", "ry", "J", "Cw",
        "Preferred",
    )
    return tuple(base.get(field) for field in fields) + (round(added_depth_mm, 6),)


@lru_cache(maxsize=4096)
def _composite_properties_cached(key: tuple) -> dict[str, Any]:
    (
        designation, _mass, h, b, tw, tf, r1, _hw, base_area_cm2,
        base_ix_cm4, _zex, _zplx, _rx, base_iy_cm4, _zey, _zply, _ry,
        base_j_cm4, base_cw, preferred, added_depth_mm,
    ) = key
    h = float(h)
    b = float(b)
    tw = float(tw)
    tf = float(tf)
    depth = max(float(added_depth_mm), 0.0)

    if depth <= _TOLERANCE_MM:
        return {
            "Designation": str(designation),
            "m": float(_mass),
            "h": h,
            "b": b,
            "tw": tw,
            "tf": tf,
            "r1": float(r1),
            "hw": float(_hw),
            "A": float(base_area_cm2),
            "Ix": float(base_ix_cm4),
            "Zex": float(_zex),
            "Zplx": float(_zplx),
            "rx": float(_rx),
            "Iy": float(base_iy_cm4),
            "Zey": float(_zey),
            "Zply": float(_zply),
            "ry": float(_ry),
            "J": float(base_j_cm4),
            "Cw": float(base_cw),
            "Preferred": preferred,
            "haunch_added_depth_mm": 0.0,
            "haunch_extra_area_mm2": 0.0,
        }

    # The inclined haunch flange terminates at the toe.  Its effective
    # thickness reduces only over the final flange thickness, making area and
    # Ixx converge smoothly to the parent rafter at the exact toe.
    added_flange_thickness = min(tf, depth)
    added_web_depth = max(depth - added_flange_thickness, 0.0)

    # The project database stores A in 10^3 mm2, I in 10^6 mm4, Z in
    # 10^3 mm3 and J in 10^3 mm4.
    base_area = float(base_area_cm2) * 1_000.0
    base_ix = float(base_ix_cm4) * 1_000_000.0
    base_iy = float(base_iy_cm4) * 1_000_000.0
    web_area = tw * added_web_depth
    flange_area = b * added_flange_thickness
    web_y = -h / 2 - added_web_depth / 2
    flange_y = -h / 2 - added_web_depth - added_flange_thickness / 2
    total_area = base_area + web_area + flange_area
    centroid_y = (
        web_area * web_y + flange_area * flange_y
    ) / total_area

    ix = base_ix + base_area * centroid_y**2
    if web_area:
        ix += (
            tw * added_web_depth**3 / 12
            + web_area * (web_y - centroid_y) ** 2
        )
    if flange_area:
        ix += (
            b * added_flange_thickness**3 / 12
            + flange_area * (flange_y - centroid_y) ** 2
        )
    iy = (
        base_iy
        + added_web_depth * tw**3 / 12
        + added_flange_thickness * b**3 / 12
    )
    j = (
        float(base_j_cm4) * 1_000.0
        + (added_web_depth * tw**3 + b * added_flange_thickness**3) / 3
    )

    top = h / 2
    bottom = -h / 2 - added_web_depth - added_flange_thickness
    zex = ix / max(top - centroid_y, centroid_y - bottom)
    zey = iy / (b / 2)

    # Rolled-section rectangles give an auditable plastic modulus estimate for
    # the built-up section. Root radii are conservatively omitted.
    rectangles = [
        (b, h / 2 - tf, h / 2),
        (tw, -h / 2 + tf, h / 2 - tf),
        (b, -h / 2, -h / 2 + tf),
    ]
    if added_web_depth:
        rectangles.append(
            (tw, -h / 2 - added_web_depth, -h / 2)
        )
    if added_flange_thickness:
        rectangles.append(
            (
                b,
                -h / 2 - added_web_depth - added_flange_thickness,
                -h / 2 - added_web_depth,
            )
        )
    pna = _plastic_axis(rectangles)
    zplx = sum(
        _rect_plastic_modulus_about_x(width, bottom_y, top_y, pna)
        for width, bottom_y, top_y in rectangles
    )
    zply = sum(
        height * width**2 / 4
        for width, bottom_y, top_y in rectangles
        for height in (top_y - bottom_y,)
    )

    area_cm2 = total_area / 1_000.0
    ix_cm4 = ix / 1_000_000.0
    iy_cm4 = iy / 1_000_000.0
    return {
        "Designation": f"{designation} + haunch {depth:.1f} mm",
        "m": area_cm2 * 7.85,
        "h": top - bottom,
        "b": b,
        "tw": tw,
        "tf": tf,
        "r1": float(r1),
        "hw": top - bottom - 2 * tf,
        "A": area_cm2,
        "Ix": ix_cm4,
        "Zex": zex / 1000.0,
        "Zplx": zplx / 1000.0,
        "rx": math.sqrt(ix / total_area),
        "Iy": iy_cm4,
        "Zey": zey / 1000.0,
        "Zply": zply / 1000.0,
        "ry": math.sqrt(iy / total_area),
        "J": j / 1_000.0,
        # Retaining the parent Cw is conservative for LTB; connection and
        # tapered-member stability remain explicit engineering hold points.
        "Cw": float(base_cw),
        "Preferred": preferred,
        "haunch_added_depth_mm": depth,
        "haunch_extra_area_mm2": web_area + flange_area,
    }


def composite_haunch_properties(
    base: Mapping[str, Any], added_depth_mm: float
) -> dict[str, Any]:
    """Return cached composite properties for one haunch cross-section."""

    return dict(_composite_properties_cached(_property_key(base, added_depth_mm)))


class HaunchProfile:
    """Resolve haunch depth at any point on a portal rafter."""

    def __init__(self, frame_data: Mapping[str, Any]):
        self.roof_type = str(frame_data.get("building_roof", "Duo Pitched"))
        self.span = float(frame_data["gable_width"])
        self.eaves = float(frame_data["eaves_height"])
        self.apex = float(frame_data["apex_height"])
        run = self.span / 2 if self.roof_type == "Duo Pitched" else self.span
        self.slope_length = math.hypot(run, self.apex - self.eaves)
        self.eaves_length = (
            float(frame_data.get("eaves_haunch_length", 0.0))
            if str(frame_data.get("use_eaves_haunch", "No")).lower() == "yes"
            else 0.0
        )
        self.eaves_depth = float(frame_data.get("eaves_haunch_depth", 0.0))
        self.apex_length = (
            float(frame_data.get("apex_haunch_length", 0.0))
            if str(frame_data.get("use_apex_haunch", "No")).lower() == "yes"
            else 0.0
        )
        self.apex_depth = float(frame_data.get("apex_haunch_depth", 0.0))

    @property
    def enabled(self) -> bool:
        return self.eaves_length > 0 or self.apex_length > 0

    def slope_position(self, x: float, y: float) -> float | None:
        del y
        run = self.span / 2 if self.roof_type == "Duo Pitched" else self.span
        if self.roof_type == "Duo Pitched":
            horizontal = x if x <= self.span / 2 else self.span - x
        else:
            horizontal = x
        if horizontal < -_TOLERANCE_MM or horizontal > run + _TOLERANCE_MM:
            return None
        return max(0.0, min(self.slope_length, horizontal / run * self.slope_length))

    def added_depth_at(self, x: float, y: float) -> float:
        position = self.slope_position(x, y)
        if position is None:
            return 0.0
        eaves_depth = 0.0
        if self.eaves_length and position < self.eaves_length:
            eaves_depth = self.eaves_depth * (1 - position / self.eaves_length)
        apex_distance = self.slope_length - position
        apex_depth = 0.0
        if self.apex_length and apex_distance < self.apex_length:
            apex_depth = self.apex_depth * (
                1 - apex_distance / self.apex_length
            )
        return max(eaves_depth, apex_depth)

    def discretisation_points(self) -> list[tuple[float, float]]:
        """Return internal global roof coordinates for the tapered zones."""

        positions: set[float] = set()
        if self.eaves_length:
            positions.update(
                self.eaves_length * index / HAUNCH_SEGMENTS
                for index in range(1, HAUNCH_SEGMENTS + 1)
            )
        if self.apex_length:
            positions.update(
                self.slope_length
                - self.apex_length * index / HAUNCH_SEGMENTS
                for index in range(1, HAUNCH_SEGMENTS + 1)
            )
        positions = {
            position
            for position in positions
            if _TOLERANCE_MM < position < self.slope_length - _TOLERANCE_MM
        }
        run = self.span / 2 if self.roof_type == "Duo Pitched" else self.span
        rise = self.apex - self.eaves
        points = [
            (
                run * position / self.slope_length,
                self.eaves + rise * position / self.slope_length,
            )
            for position in sorted(positions)
        ]
        if self.roof_type == "Duo Pitched":
            points.extend((self.span - x, y) for x, y in list(points))
        return points


class TaperedPhysMember(PhysMember):
    """PyNite physical member assigning cached sections after discretisation."""

    def __init__(
        self,
        *args,
        property_selector: Callable[[float, float], Mapping[str, Any] | None],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._property_selector = property_selector

    def descritize(self) -> None:  # PyNite uses this historical spelling.
        super().descritize()
        properties_by_name = getattr(
            self.model, "_portal_section_properties", {}
        )
        for sub_member in self.sub_members.values():
            midpoint_x = (sub_member.i_node.X + sub_member.j_node.X) / 2
            midpoint_y = (sub_member.i_node.Y + sub_member.j_node.Y) / 2
            properties = self._property_selector(midpoint_x, midpoint_y)
            if properties is None:
                continue
            section_name = str(properties["Designation"])
            if section_name not in self.model.sections:
                self.model.add_section(
                    section_name,
                    float(properties["A"]) * 1e3,
                    float(properties["Iy"]) * 1e6,
                    float(properties["Ix"]) * 1e6,
                    float(properties["J"]) * 1e3,
                )
            sub_member.section = self.model.sections[section_name]
            sub_member.portal_properties = dict(properties)
            properties_by_name[section_name] = dict(properties)
        self.model._portal_section_properties = properties_by_name


def haunch_extra_mass_kg(
    rafter: Mapping[str, Any], frame_data: Mapping[str, Any]
) -> float:
    """Return the added haunch mass for one complete transverse frame."""

    profile = HaunchProfile(frame_data)
    if not profile.enabled:
        return 0.0
    count = 2 if profile.roof_type == "Duo Pitched" else 1
    total = 0.0
    for zone_length, zone_depth in (
        (profile.eaves_length, profile.eaves_depth),
        (profile.apex_length, profile.apex_depth),
    ):
        if zone_length <= 0:
            continue
        segment_length = zone_length / HAUNCH_SEGMENTS
        for index in range(HAUNCH_SEGMENTS):
            fraction = 1 - (index + 0.5) / HAUNCH_SEGMENTS
            props = composite_haunch_properties(
                rafter, zone_depth * fraction
            )
            extra_mass_per_m = (
                float(props["m"]) - float(rafter["m"])
            )
            total += count * extra_mass_per_m * segment_length / 1000.0
    return total
