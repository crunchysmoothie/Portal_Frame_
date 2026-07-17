# Portal Frame Design Program — First-Time User Manual

## 1. Purpose and responsibility

This program generates and analyses a two-dimensional steel portal frame, selects passing portal-frame sections, designs the gable columns and longitudinal bracing for an enclosed building, stores the completed analysis, and produces HTML, JSON and PDF calculation reports.

The program is a design aid. A competent engineer must review the inputs, structural arrangement, load paths, selected sections, results, assumptions and exclusions before the design is issued or used for construction.

## 2. What the program currently designs

For a normal enclosed building, the program covers:

- Transverse portal-frame columns and rafters.
- Normal and canopy wind loading for mono- and duo-pitched roofs.
- Preliminary or opening-based final internal wind pressure.
- Pinned gable columns loaded about their strong axis and checked using the `Mcr` calculation.
- Roof X-bracing using tension-only angle members.
- User-selected longitudinal side-wall bracing: tension-only angle X-bracing, or CHS K-/A-bracing in tension and compression.
- A provisional lipped-channel purlin section used as the roof-bracing strut.
- A building-level steel mass summary for portal frames, bracing, gable columns and purlins.

For a canopy, no gable columns or enclosed-building gable bracing are inserted or designed.

## 3. Important current limitations

Read these limitations before starting a design:

- The transverse portal is a two-dimensional model.
- The current roof imposed load is fixed at `0.25 kPa`.
- The current roof permanent-load range is fixed at `0.25–0.35 kPa`, in addition to modelled member self-weight.
- These roof load intensities are presently defined in `user_input.py`, not in the main editable input block.
- Vertical and horizontal serviceability limits are currently span/150 and eaves height/150 respectively.
- Portal sections are selected only from database sections marked as preferred.
- Purlin compression resistance is deferred. Its section and reported mass are therefore provisional.
- The steel mass excludes girts, connections, base plates, cleats, bolts, welds and fabrication allowances.
- Final internal-pressure calculations assume wall openings are uniformly distributed and that the roof opening area is zero.
- If two or more wall faces are more than 30% open, the enclosed-building internal-pressure model is rejected.
- Mono-pitched portal geometry currently uses four fixed rafter divisions; `rafter_bracing_spacing` controls duo-pitched geometry only.

## 4. Files a user should know

| File | Purpose | Should the user edit it? |
|---|---|---|
| `run_full_analysis.py` | Main building and wind inputs; preferred program entry point | Yes |
| `input_data.json` | Generated model, loads and combinations | No |
| `member_database.csv` | Portal-frame I- and H-section properties | Only when maintaining the database |
| `bracing_member_database.csv` | Angle, CHS and lipped-channel properties | Only when maintaining the database |
| `output/analysis/analysis_results.json` | Stored completed analysis used for reporting | No |
| `design_calculations.py` | Generates reports from the stored analysis | No |

Always edit `run_full_analysis.py`, then rerun the analysis. Do not manually change `input_data.json`.

## 5. Starting the program

### 5.1 Open the correct folder

Open PowerShell or the PyCharm terminal in:

```text
C:\Users\ruan\PycharmProjects\PortalFrame\pythonProject
```

Confirm that the prompt is in this folder before running any commands.

### 5.2 Use the project Python environment

The project environment is `.venv314`. Run the program with its Python executable:

```powershell
.\.venv314\Scripts\python.exe --version
```

The currently verified environment uses Python 3.14 and includes NumPy, SciPy, PyNiteFEA and Tabulate. PDF export additionally requires the versions in `requirements-pdf.txt`.

If PDF packages are missing, install them into the project environment:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements-pdf.txt
```

## 6. Entering a new design

Open `run_full_analysis.py`. Only change the values near the top of `main()` unless you are intentionally modifying the program.

### 6.1 Select the building and design basis

```python
building_roof = "Duo Pitched"
building_type = "Normal"
wind_design_mode = "Prelim"
roof_accessibility = "Inaccessible"
load_combination_standard = "SANS 10160-1:2019"
blocking_factor = 0.0
```

Use the exact text shown below:

| Input | Accepted values | Meaning |
|---|---|---|
| `building_roof` | `"Duo Pitched"`, `"Mono Pitched"` | Roof form |
| `building_type` | `"Normal"`, `"Canopy"` | Enclosed building or open canopy |
| `wind_design_mode` | `"Prelim"`, `"Final design"` | Internal-pressure method |
| `roof_accessibility` | `"Accessible"`, `"Inaccessible"` | Selects the roof imposed-load accompanying factor |
| `load_combination_standard` | `"SANS 10160-1:2019"`, `"Pre-2019"` | Selects the implemented wind combination factor |
| `blocking_factor` | `0.0` to `1.0` | Canopy only: open to fully blocked below the canopy |

For a normal building, `blocking_factor` is ignored.

### 6.2 Enter the building geometry

```python
eaves_height = 6.5 * 1000
apex_height = 8.09 * 1000
gable_width = 18 * 1000
rafter_spacing = 6 * 1000
building_length = 42 * 1000
```

All five values are entered in millimetres. Multiplying metre values by `1000` makes the intended units clear.

| Input | Meaning |
|---|---|
| `eaves_height` | Height to the eaves |
| `apex_height` | Height to the apex or high side of a mono-pitched roof |
| `gable_width` | Transverse building span |
| `rafter_spacing` | Longitudinal spacing between transverse frame lines |
| `building_length` | Overall longitudinal building length |

The roof pitch is calculated automatically. Do not manually overwrite the `roof_pitch` expression in `building_data`.

The building-level portal-frame quantity is calculated as the number of longitudinal bays plus one frame line. A partial last bay is treated as requiring an additional frame.

### 6.3 Define the portal brace-node layout

```python
col_bracing_spacing = 1
rafter_bracing_spacing = 2
column_bracing_type = "X"
```

- `col_bracing_spacing` is the number of equal modelled intervals over each portal column. It must be at least 1.
- The selected X, K or A wall-bracing topology is repeated in every one of
  these vertical intervals. For example, `col_bracing_spacing = 2` creates a
  restraint at column midheight and two stacked bracing panels.
- For a duo-pitched roof, `rafter_bracing_spacing` is the number of equal intervals on each roof slope. Increasing it creates additional rafter nodes and possible purlin/gable-column connection points.
- A mono-pitched roof currently uses four fixed rafter divisions regardless of this input.

These values are integer counts, not distances in millimetres.

`column_bracing_type` selects the longitudinal bracing between portal columns:

- `"X"` selects tension-only angle cross-bracing. Angles must satisfy the reported tension/slenderness checks and cannot be smaller than 50x50x5.
- `"K"` selects CHS K-bracing checked in tension and compression.
- `"A"` selects CHS A-bracing checked in tension and compression.

The selected arrangement, member section and bay dimensions are shown in the calculation report.
Roof X-bracing continues across the complete roof width in each end braced bay.
Its transverse panel width is controlled by the purlin interval described below.

### 6.4 Define purlins, girts and the draughtsman markup layout

```python
purlin_section = "125x50x20x2.5"
purlin_max_spacing_mm = 1500
roof_bracing_purlin_interval = 3
girt_section = "125x50x20x2.5"
girt_max_spacing_mm = 1800
```

Cold-formed lipped-channel designations use `depthxflangexlipxthickness`, in
millimetres. The entered purlin must exist under `Lipped Channels` in
`bracing_member_database.csv`.

`purlin_max_spacing_mm` and `girt_max_spacing_mm` are maximum spacings. The
markup divides each roof slope and wall height into equal spaces no greater
than those values. `roof_bracing_purlin_interval` controls the roof X-brace
panel width: `1` braces every purlin space, `2` every second space, and so on.
The final panel approaching the ridge or eave is shortened where necessary.

The haunch length is fixed at `portal span / 15`, measured horizontally from
the column centreline. The markup identifies the tapered haunch as cut from
the selected rafter section.

After the design calculation report has been generated, create the standalone
A1 markup with:

```powershell
.\.venv314\Scripts\python.exe draughtsman_markup.py
```

This writes a printable HTML file and, when Microsoft Edge or Google Chrome is
available, prints the same HTML directly to PDF under `output/markup/`.

### 6.4 Define the gable columns

```python
gable_column_count = 3
gable_column_brace_intervals = 2
```

`gable_column_count` describes the internal columns on one gable end:

- It must be a positive odd number: `1`, `3`, `5`, and so on.
- One column is always located at the apex.
- Each increase of two adds a symmetric pair, one on either side of the apex.
- Columns can only be placed at available roof brace nodes.
- If the requested number is too large, either reduce it or increase `rafter_bracing_spacing` for a duo-pitched roof.

`gable_column_brace_intervals` is the number of equal laterally unbraced intervals over each pinned gable-column height. It must be at least 1.

For a canopy these inputs remain in the file but no gable columns are generated or designed.

### 6.5 Select the steel grade

```python
steel_grade = "Steel_S355"
```

Accepted values are:

- `"Steel_S355"`
- `"Steel_S275"`

### 6.6 Choose preliminary or final internal pressure

#### Preliminary design

```python
wind_design_mode = "Prelim"
```

Preliminary mode uses the conservative internal-pressure envelope:

```text
cpi = +0.2 and -0.3
```

Opening areas are not used in this mode.

#### Final design

```python
wind_design_mode = "Final design"
```

Enter the total opening area on each physical wall face in square metres:

```python
"opening_areas_m2": {
    "side_1": 0.0,
    "side_2": 0.0,
    "gable_1": 0.0,
    "gable_2": 0.0,
},
```

- `side_1` and `side_2` are the long walls parallel to the ridge.
- `gable_1` and `gable_2` are the two end walls.
- Use `0.0` for a face with no known openings.
- Each opening area must not exceed the calculated gross area of its wall.

The program evaluates both senses of the 0° and 90° wind directions. It determines whether a dominant wall exists and calculates the applicable internal-pressure envelope. Where there are no estimated openings, the program retains the conservative `+0.2/-0.3` envelope.

Final wall-opening inputs do not apply to canopies because canopy net-pressure coefficients are used.

### 6.7 Enter the wind data

```python
wind_data = {
    "wind": "3s gust",
    "fundamental_basic_wind_speed": 32,
    "return_period": 50,
    "terrain_category": "B",
    "topographic_factor": 1.0,
    "altitude": 830,
}
```

| Input | Unit or accepted value | Meaning |
|---|---|---|
| `wind` | Keep as `"3s gust"` | Current wind-speed basis label |
| `fundamental_basic_wind_speed` | m/s | Site fundamental basic wind speed |
| `return_period` | years | Design return period; must be greater than zero |
| `terrain_category` | `"A"`, `"B"`, `"C"`, `"D"` | Terrain roughness category |
| `topographic_factor` | dimensionless | Site topographic multiplier |
| `altitude` | m | Site altitude above sea level |

Confirm these values from the project design basis and the applicable wind standard.

## 7. Running the design analysis

Save `run_full_analysis.py`, then run:

```powershell
.\.venv314\Scripts\python.exe run_full_analysis.py
```

The program will:

1. Generate the portal nodes, members, supports and brace points.
2. Generate load cases and SLS/ULS combinations.
3. Calculate the wind zones and internal pressure.
4. Convert the wind zones into portal member loads.
5. Add the fixed roof imposed and permanent loads.
6. Search the preferred rafter and column sections.
7. Analyse the portal using PyNite.
8. Reject section pairs that fail strength, stability or serviceability.
9. Select the lightest passing portal-frame combination.
10. Design the gable columns and bracing for a normal building.
11. Calculate the building-level steel mass summary.
12. Store a complete analysis snapshot in `output/analysis/analysis_results.json`.
13. Open the interactive frame visualiser.

The section search can take several minutes. Do not close the terminal while it is running.

### Running without the visualiser

For a non-interactive run, use:

```powershell
.\.venv314\Scripts\python.exe -c "import run_full_analysis; run_full_analysis.main(render=False)"
```

This performs the same design and stores the same results without opening the PyNite display window.

## 8. Reviewing the analysis output

Before generating the report, review the terminal output.

### 8.1 Wind tables

Confirm that the printed wind pressures and zone lengths are reasonable for the geometry and wind inputs.

### 8.2 Selected portal sections

The program prints the lightest passing rafter and column sections and the mass of one transverse portal frame.

### 8.3 Deflections

Confirm the governing horizontal and vertical deflections and their load combinations. The current limits are:

```text
Vertical: span / 150
Horizontal: eaves height / 150
```

### 8.4 Strength results

The ULS result table reports each member, load combination, axial action, governing check, utilisation and status.

- `PASS` means the reported utilisation is not greater than 1.0 for the implemented checks.
- It does not remove the engineer’s obligation to review the model and checks.

If the program reports that no acceptable section was found, do not generate a final report. Review the geometry, loads, brace spacing, serviceability limits and available preferred sections.

## 9. Generating the design report

Only generate the report after a successful analysis.

### 9.1 Standard critical-results report

```powershell
.\.venv314\Scripts\python.exe design_calculations.py
```

This uses the stored analysis and produces the normal concise report without rerunning the frame analysis.

### 9.2 Full report

To report every stored member and load combination:

```powershell
.\.venv314\Scripts\python.exe design_calculations.py --scope full
```

### 9.3 One load-combination report

```powershell
.\.venv314\Scripts\python.exe design_calculations.py --scope load_combination --load-combination "1.2 DL + 1.6 LL"
```

The load-combination name must exactly match a stored combination.

### 9.4 HTML and JSON only

If PDF dependencies are unavailable:

```powershell
.\.venv314\Scripts\python.exe design_calculations.py --no-pdf
```

## 10. Report outputs

The default report command creates:

```text
output/calculations/portal_frame_calculation_sheet.html
output/calculations/portal_frame_calculation_sheet.json
output/pdf/portal_frame_calculation_sheet.pdf
```

The PDF is the normal document to review and issue. The HTML is useful for screen review, while the JSON contains the structured report data.

The report includes:

- Project and design basis.
- Geometry, selected sections and analysis summary.
- Portal-frame, bracing, gable-column and provisional purlin mass breakdown.
- Total estimated steel mass and stated exclusions.
- Assumptions and warnings.
- Load combinations.
- Deflection and reaction envelopes.
- Member classification, resistance and utilisation calculations.
- Gable-column and longitudinal-bracing design for normal buildings.
- Gable elevation and roof-bracing layout diagrams.

## 11. Stored-result safety check

The report generator compares the current `input_data.json` with the input stored in the completed analysis snapshot.

If the inputs changed after the analysis, report generation is rejected as stale. The correct workflow is:

1. Rerun `run_full_analysis.py`.
2. Confirm that the analysis completes successfully.
3. Rerun `design_calculations.py`.

The `--allow-stale-results` option exists for exceptional diagnostic work. Do not use it for a report that will be issued as a current design.

## 12. Iterating a design

For every design revision:

1. Edit only the intended values in `run_full_analysis.py`.
2. Save the file.
3. Run the full analysis again.
4. Review the selected sections, deflections, utilisations and layouts.
5. Generate a new report.
6. Review the PDF.
7. Copy the final input file, stored analysis and issued report into the project record system if required.

Report generation alone does not update the structural analysis.

## 13. Steel mass calculation

The report calculates the following categories:

### Portal frames

```text
number of frame lines × mass of one transverse portal frame
```

The mass of one portal is the total rafter length times the selected rafter kg/m plus the total column length times the selected column kg/m.

### Gable columns

The selected column mass per metre is multiplied by each gable-column height and by two gable ends.

### Bracing

The total includes the physical roof X-brace diagonals and side-wall CHS diagonals in the two end braced bays. A one-bay building uses one braced bay.

### Purlins

The number of rafter brace-node lines is multiplied by the full building length and the selected lipped-channel kg/m. This value remains provisional until the purlin compression check is implemented.

### Total

```text
portal frames + gable columns + bracing + purlins
```

Girts and connection steel are not currently included.

## 14. Common problems

### `ModuleNotFoundError`, for example NumPy or PyNite

The wrong Python executable is being used. Run the command with:

```powershell
.\.venv314\Scripts\python.exe
```

### Report says the analysis results are stale

The input changed after the last analysis. Rerun the full analysis before regenerating the report.

### Gable-column count must be odd

Use `1`, `3`, `5`, and so on. The apex column is mandatory.

### Requested gable columns exceed available brace points

Reduce `gable_column_count` or increase `rafter_bracing_spacing` for a duo-pitched roof.

### Final design requires four opening areas

Enter `side_1`, `side_2`, `gable_1` and `gable_2`, even where a value is zero.

### Opening area exceeds the wall area

Check that the input is the opening area in square metres, not square millimetres or a percentage.

### Enclosed-building model is rejected because two faces are over 30% open

The current normal-building pressure method is not applicable to that configuration. Review whether the structure should be treated using the canopy/free-roof provisions.

### No acceptable portal section is found

Review the loads, geometry, brace spacing and preferred-section database. The program only searches sections marked as preferred.

### No gable, angle or CHS section passes

Review the gable layout and loads, then confirm that the relevant section family and sizes exist in the databases.

### PDF generation fails

Install the verified PDF dependencies:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements-pdf.txt
```

The program specifically expects ReportLab 4.4.9 for the current PDF tables.

## 15. Minimum engineer review checklist

Before issuing a report, confirm:

- The correct project geometry and frame spacing were entered.
- The roof form and building type are correct.
- The wind speed, terrain, topography, altitude and return period are correct.
- The preliminary or final wind mode is appropriate.
- Final-design wall openings match the architectural information.
- Roof permanent and imposed loads are suitable for the project, noting the current built-in values.
- The gable-column arrangement matches the intended construction.
- Portal, gable and bracing layouts provide a continuous load path.
- Selected sections and steel grades are available.
- Strength utilisations and serviceability deflections are acceptable.
- The purlin design is completed separately until its compression check is implemented.
- Excluded secondary steel and connections are designed and quantified separately.
- The report input-verification status is current, not stale.
- The final PDF has been reviewed and signed according to the organisation’s quality system.
