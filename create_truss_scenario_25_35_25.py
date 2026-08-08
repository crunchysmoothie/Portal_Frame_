"""Generate the matched 25 m / 35 m / 25 m PortalFrame and Prokon truss model."""

from __future__ import annotations

import json
from pathlib import Path

from prokon_export import build_truss_comparison, write_comparison_package
from truss_design import design_truss
from truss_report import write_truss_html, write_truss_json, write_truss_markup_html
from ui.input_model import InputValidationError, build_analysis_payload


ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"C:\Users\ruan\Desktop\Projects Misc\Avco\3. caLCS\Avco-Racking-Warehouse.portalframe (1).json")
OUTPUT = ROOT / "output" / "truss_scenarios" / "25_35_25"


def main() -> None:
    saved = json.loads(SOURCE.read_text(encoding="utf-8"))
    raw = dict(saved["inputs"])
    raw.update(
        {
            "structural_system": "Truss",
            "building_type": "Normal",
            "building_roof": "Duo Pitched",
            "eaves_height_m": "6.5",
            "truss_eaves_height_m": "6.5",
            "truss_transverse_bay_spans_m": "25,35,25",
            "truss_spacing_m": "6",
            "truss_minimum_depth_m": "1.7",
            "truss_maximum_depth_m": "1.7",
            "truss_depth_increment_m": "0.1",
            "purlin_max_spacing_mm": "1700",
            "truss_roof_pitch_deg": "10",
            "truss_type": "Pratt",
            "truss_top_chord_brace_every_n_purlins": "2",
            "truss_bottom_chord_brace_every_n_purlins": "2",
            # 0.4 kPa minimum and 1.2 kPa maximum permanent roof action.
            "truss_ceiling_load_kpa": "0.4",
            "truss_services_load_kpa": "0.8",
            "truss_solar_load_kpa": "0",
            "truss_fire_load_kpa": "0",
            "truss_hvac_load_kpa": "0",
            "truss_ranked_solution_count": "1",
        }
    )
    try:
        payload = build_analysis_payload(raw)
    except InputValidationError as exc:
        print(exc.errors)
        raise
    result = design_truss(payload)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_truss_html(result, OUTPUT / "portalframe_truss_design.html")
    write_truss_json(result, OUTPUT / "portalframe_truss_design.json")
    write_truss_markup_html(result, OUTPUT / "portalframe_truss_markup.html")
    comparison = build_truss_comparison(result)
    write_comparison_package(comparison, OUTPUT / "prokon")
    (OUTPUT / "scenario_input.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(OUTPUT)
    print(json.dumps({
        "status": result.get("status"),
        "mass_kg": result.get("mass_kg"),
        "span_mm": result.get("ranked_solutions", [{}])[0].get("geometry", {}).get("span_mm"),
        "prokon_a03": str(OUTPUT / "prokon" / "truss_prokon_input.A03"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
