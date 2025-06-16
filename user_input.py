from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class BuildingData:
    """Geometry and layout parameters for a portal frame."""

    building_type: str = "Normal"
    building_roof: str = "Duo Pitched"
    eaves_height: float = 5000.0  # mm
    apex_height: float = 7000.0   # mm
    gable_width: float = 8000.0   # mm
    rafter_spacing: float = 5000.0  # mm
    building_length: float = 50000.0  # mm
    col_bracing_spacing: int = 2
    rafter_bracing_spacing: int = 4
    roof_pitch: float | None = None

    def __post_init__(self) -> None:
        if self.roof_pitch is None:
            rise = self.apex_height - self.eaves_height
            run = self.gable_width / 2
            self.roof_pitch = math.degrees(math.atan2(rise, run))

    def to_dict(self) -> Dict[str, float | str | int]:
        return asdict(self)


@dataclass
class WindData:
    """Wind loading parameters."""

    wind: str = "3s gust"
    fundamental_basic_wind_speed: float = 36
    return_period: int = 50
    terrain_category: str = "B"
    topographic_factor: float = 1.0
    altitude: float = 1450.0
    # Updated from ``BuildingData``
    building_type: str | None = None
    building_roof: str | None = None
    eaves_height: float | None = None
    apex_height: float | None = None
    gable_width: float | None = None
    rafter_spacing: float | None = None
    building_length: float | None = None
    col_bracing_spacing: int | None = None
    rafter_bracing_spacing: int | None = None
    roof_pitch: float | None = None

    def update_from_building(self, b: BuildingData) -> None:
        self.building_type = b.building_type
        self.building_roof = b.building_roof
        self.eaves_height = b.eaves_height / 1000
        self.apex_height = b.apex_height / 1000
        self.gable_width = b.gable_width / 1000
        self.rafter_spacing = b.rafter_spacing / 1000
        self.building_length = b.building_length / 1000
        self.col_bracing_spacing = b.col_bracing_spacing
        self.rafter_bracing_spacing = b.rafter_bracing_spacing
        self.roof_pitch = b.roof_pitch

    def to_dict(self) -> Dict[str, float | str | int | None]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Geometry generation helpers
# ---------------------------------------------------------------------------

def _column_nodes(start_idx: int, count: int, x: float, y_start: float, y_end: float) -> List[Dict[str, float]]:
    step = (y_end - y_start) / (count - 1) if count > 1 else 0.0
    nodes = []
    for i in range(count):
        nodes.append({"name": f"N{start_idx + i}", "x": x, "y": round(y_start + i * step, 2), "z": 0})
    return nodes


def _duo_rafter_nodes(start_idx: int, num: int, gable_width: float, eaves_height: float, apex_height: float) -> List[Dict[str, float]]:
    nodes = []
    for i in range(1, num):
        x = round(i * (gable_width / num), 2)
        y = round(eaves_height + (apex_height - eaves_height) * (1 - abs(i - (num / 2)) / (num / 2)), 2)
        nodes.append({"name": f"N{start_idx}", "x": x, "y": y, "z": 0})
        start_idx += 1
    return nodes


def _mono_rafter_nodes(start_idx: int, num: int, gable_width: float, eaves_height: float, apex_height: float) -> List[Dict[str, float]]:
    nodes = []
    for i in range(1, num + 1):
        x = round(i * (gable_width / num), 2)
        y = round(eaves_height + (apex_height - eaves_height) * (i / num), 2)
        nodes.append({"name": f"N{start_idx}", "x": x, "y": y, "z": 0})
        start_idx += 1
    return nodes


def generate_nodes(b: BuildingData) -> List[Dict[str, float]]:
    """Create node coordinates for the frame based on ``b``."""
    nodes: List[Dict[str, float]] = []
    num_vertical = b.col_bracing_spacing + 2
    idx = 1

    # Left column
    nodes.extend(_column_nodes(idx, num_vertical, 0.0, 0.0, b.eaves_height))
    idx += num_vertical

    if b.building_roof == "Duo Pitched":
        num_diagonal = b.rafter_bracing_spacing * 2
        nodes.extend(_duo_rafter_nodes(idx, num_diagonal, b.gable_width, b.eaves_height, b.apex_height))
        idx += num_diagonal - 1
        nodes.extend(_column_nodes(idx, num_vertical, b.gable_width, b.eaves_height, 0.0))
    elif b.building_roof == "Mono Pitched":
        num_diagonal = b.rafter_bracing_spacing
        nodes.extend(_mono_rafter_nodes(idx, num_diagonal, b.gable_width, b.eaves_height, b.apex_height))
        idx += num_diagonal
        start = b.apex_height - b.apex_height / (num_vertical - 1)
        nodes.extend(_column_nodes(idx, num_vertical - 1, b.gable_width, start, 0.0))
    else:
        raise NotImplementedError(f"Roof type '{b.building_roof}' not handled")

    return nodes


def generate_supports(nodes: List[Dict[str, float]]) -> List[Dict[str, bool | str | float]]:
    return [
        {"node": nodes[0]["name"], "DX": True, "DY": True, "DZ": True, "RX": False, "RY": False, "RZ": False},
        {"node": nodes[-1]["name"], "DX": True, "DY": True, "DZ": True, "RX": False, "RY": False, "RZ": False},
    ]


def generate_members(nodes: List[Dict[str, float]]) -> List[Dict[str, float | str]]:
    members = []
    for i in range(1, len(nodes)):
        xi, yi = nodes[i - 1]["x"], nodes[i - 1]["y"]
        xj, yj = nodes[i]["x"], nodes[i]["y"]
        members.append({
            "name": f"M{i}",
            "i_node": nodes[i - 1]["name"],
            "j_node": nodes[i]["name"],
            "material": "Steel_S355",
            "type": "rafter" if xi != xj else "column",
            "length": round(math.hypot(xj - xi, yj - yi) / 1000, 3),
        })
    return members


def generate_nodal_loads(nodes: List[Dict[str, float]], b: BuildingData) -> List[Dict[str, float | str]]:
    apex_node = nodes[len(nodes) // 2]
    eaves_node = next(n for n in nodes if n["x"] == 0 and n["y"] == b.eaves_height)
    return [
        {"node": eaves_node["name"], "direction": "FX", "magnitude": 10, "case": "L"},
        {"node": apex_node["name"], "direction": "FY", "magnitude": -10, "case": "L"},
    ]


def generate_spring_supports(nodes: List[Dict[str, float]]) -> List[Dict[str, float | str]]:
    return [
        {"node": nodes[0]["name"], "direction": "RZ", "stiffness": 5e6},
        {"node": nodes[-1]["name"], "direction": "RZ", "stiffness": 5e6},
    ]


def write_json(filename: str, data: dict) -> None:
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


def update_json_file(filename: str, building: BuildingData, wind: WindData) -> None:
    nodes = generate_nodes(building)
    members = generate_members(nodes)
    supports = generate_supports(nodes)
    springs = generate_spring_supports(nodes)

    with open(filename, "r") as f:
        data = json.load(f)

    wind.update_from_building(building)

    data["frame_data"] = [building.to_dict()]
    data["nodes"] = nodes
    data["members"] = members
    data["supports"] = supports
    data["rotational_springs"] = springs
    data["wind_data"] = wind.to_dict()

    write_json(filename, data)
    print(f"Portal frame data saved to {filename}")


def add_wind_member_loads(filename: str) -> None:
    from generate_wind_loading import wind_loading

    with open(filename, "r") as f:
        data = json.load(f)

    loads = wind_loading(data)
    data.setdefault("member_loads", [])
    data["member_loads"] = loads

    write_json(filename, data)


def main() -> None:
    building = BuildingData()
    wind = WindData()
    filename = "input_data.json"
    update_json_file(filename, building, wind)
    add_wind_member_loads(filename)


if __name__ == "__main__":
    main()
