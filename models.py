from dataclasses import dataclass, asdict
from typing import Dict, Optional
import math

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
    roof_pitch: Optional[float] = None

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
    building_type: Optional[str] = None
    building_roof: Optional[str] = None
    eaves_height: Optional[float] = None
    apex_height: Optional[float] = None
    gable_width: Optional[float] = None
    rafter_spacing: Optional[float] = None
    building_length: Optional[float] = None
    col_bracing_spacing: Optional[int] = None
    rafter_bracing_spacing: Optional[int] = None
    roof_pitch: Optional[float] = None

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
