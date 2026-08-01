# Portal Frame and Truss Designer User Guide

The application is operated through its local browser interface. Structural inputs,
analysis, design checks, reports, and markup drawings remain in the Python
application; users should not edit generated JSON or output files manually.

## Install and run

Use the project virtual environment from the repository root:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements.txt
.\.venv314\Scripts\python.exe run_designer.py
```

The launcher starts the local API and opens the Flet UI. If the browser does not
open, navigate to <http://127.0.0.1:8550>.

## Analysis workflow

1. Select **Portal frame** or **Truss** for the project.
2. Enter the shared building and wind data, then complete the selected system's
   design inputs.
3. Review the scaled geometry preview and validation messages.
4. Select **Run analysis**.
5. Review ULS utilisation and SLS deflection results. A utilisation above 1.0
   is a reported failure, not an analysis error.
6. Open the HTML calculation report. Portal-frame markup drawings remain
   available for portal-frame projects.

Changing an input makes previous results stale. Run the analysis again before
using reports or drawings.

Portal-frame **Design basis** includes an optional switch to ignore the vertical
span/deflection acceptance limit for `1.1 DL + 1.0 LL`. The combination is
still analysed and reported; only its vertical deflection is removed as an
automatic section-selection rejection criterion. Horizontal drift, all other
SLS limits and all ULS strength checks remain active.

Portal-frame vertical serviceability acceptance uses the incremental
variable-action displacement from a matching permanent-action baseline. The
baseline retains the same `D`, `D_MIN` and permanent crawl-load factors as each
SLS combination. Total and permanent deflections remain visible for audit.
Automatic sizing also checks the total deformed roof and rejects any generated
rafter segment that loses or reverses its original drainage fall, because that
condition can create a ponding low point.

The **Additional permanent roof actions** inputs apply to portal frames and
trusses. Services, ceiling, solar, fire-services and HVAC characteristic area
loads are all added to `D_MAX`. `D_MIN` includes ceiling, fire-services and
HVAC, while services and solar are excluded. When these inputs are all zero,
both `D_MAX` and `D_MIN` are zero; calculated structural member self-weight
remains in load case `D`. Portal-frame area loads are
multiplied by the frame spacing to obtain downward rafter line loads.

Use **Save inputs** to keep the current project form as a
`.portalframe.json` file. Use **Load inputs** in a later session to restore and
validate the form, then select **Run analysis**. The saved file contains inputs
only; it does not treat old results as a current analysis.

## Section selection

Rafters and columns may use **Automatic - lightest passing** or an explicit
section. An explicit section is analysed and reported as selected, including
utilisations and deflections above the acceptance limit. Manual section
dropdowns are ordered by section height, then flange width, then mass; this
display order does not change the automatic lightest-passing search.

Gable columns may use an explicitly selected I/H section, or automatic sizing
with **Automatic - lightest passing** or **Preferred sections first** ordering.
An explicit section is retained and reported with its actual utilisation,
including a FAIL when it is inadequate. Enter any positive whole number of
internal gable columns per end; the columns are placed at equal spacing across
the gable width, for both odd and even counts.

## Preliminary generic truss workflow

Truss mode provides a generic preliminary design path:

- mono- or duo-pitched trusses with three Warren layouts (**no verticals**,
  **verticals at intermediate purlins**, or **all verticals**), plus Pratt and
  Howe layouts;
- one comma-separated list of transverse span lengths; the entry count becomes
  the span count and their sum becomes the building width;
- main columns at the outer edges and either centre columns or longitudinal
  girders at internal span boundaries;
- user-entered truss depth limits and increments, with separate practical-cost
  and individually optimised-web mass comparisons;
- selectable equal-angle member search order: lightest passing, single angles
  first, or back-to-back angles first; the exact searched order is recorded;
- purlins at every truss vertical, so the purlin spacing also controls the
  maximum panel width;
- top- and bottom-chord restraint at every first, second, third, or other
  selected purlin line, assumed to continue across the entire building;
- existing PortalFrame dead, imposed, wind and SANS load-combination logic
  converted to nodal truss actions;
- additional services, ceiling, solar, fire-services and HVAC area loads;
- one common top-chord and bottom-chord section per fabricated transverse span;
- ordinary webs grouped over at least three consecutive panels, with a smaller
  section introduced only after the retained section utilisation drops below 75%;
- a dedicated bearing node at every support, where the aligned vertical uses the
  selected supporting column or longitudinal-girder vertical section;
- an 8% platework cost-equivalent allowance in the practical ranking;
- a minimum base angle of 50x50x5 for bolted detailing space;
- iterative member self-weight, axial strength/slenderness checks, and a
  user-set vertical-deflection limit (default Span/180);
- provisional eave-column sizing from truss vertical reactions and wall wind;
- optional centre-column design: steel columns are checked for pure axial force
  using an entered brace spacing and section-order preference; concrete tilt-up
  inputs are recorded explicitly as a hold point until the concrete standard,
  reinforcement and erection/bracing basis are confirmed;
- longitudinal lattice-girder sizing where selected, using the entered number of
  building bays and explicit girder-depth search limits;
- ranked solutions, member-by-member utilisation schedules, a member/section
  markup drawing, design checks and complete support reactions.

The truss output is a calculation draft. Member forces, axial resistance,
slenderness and vertical deflection are calculated and shown in the report.
The warning means that gussets, bolts, welds, bearings, restraint-member
capacity and an independent project check remain outstanding. SANS
editions must also be confirmed. Back-to-back angles are
treated as symmetric heel-to-heel pairs without any additional gusset-gap benefit.
Detailed truss connections, net-section rupture, gussets, bolts, welds, bearings, splices,
bracing-member design, concrete tilt-up capacity/detailing, crawl beams and
hoist actions are excluded from this iteration. If centre-column design is
disabled, internal columns remain idealised supports and their mass is excluded;
the main eave-column section is used only as a preliminary stiffness proxy.

## Post-analysis connections and automatic portal foundations

After a portal-frame analysis, enter the permissible bearing pressure, soil unit
weight, soil cover, base-friction coefficient and sliding-resistance basis. If
passive resistance is credited, also enter the soil friction angle and passive
mobilisation factor. The automatic common-pad search calculates the footing
length, width and height in practical increments.

Choose **Sliding Resisted** only where a separate restraint, such as a designed
tie or slab load path, will carry the horizontal action. That option removes pad
sliding from the automatic size search and records the external restraint as an
engineering hold point. Choose **Sliding Not Resisted** where the isolated pad
must resist sliding using base friction and any mobilised Rankine passive
pressure. ULS support reactions are already factored, so the required ULS
sliding safety factor defaults to 1.0; ULS overturning retains 1.5.

Passive resistance is excluded by default. Only enable it where a geotechnical
engineer confirms that retained, adequately compacted and drained soil will
remain available to mobilise the entered resistance throughout the design life.
The fixed preliminary RC assumptions remain SANS 10100-1, 25 MPa concrete,
500 MPa reinforcement, T16@150 bottom mesh, 75 mm cover and a 400 x 400 mm
loaded area.

Portal analysis automatically enables a separate **Connections** workflow once
the frame sections and actions are final. Base-plate bearing, plate bending,
bolt distances and steel interaction are checked. Haunch end plates and
supporting flanges include all three equivalent T-stub modes, prying, bearing,
bolt interaction and elastic weld-group design. Supporting-column checks cover
web tension yielding, compression crippling, compression buckling and panel
shear. Only failed unreinforced flange or concentrated web components trigger
calculated flat transverse stiffeners; failed panel shear remains a doubler-plate
or connection-revision hold point. The app shows each connection as an
interactive 3D inspection model, but does not export a 3D file.

Every haunch donor is cut from the selected rafter section. Its displayed and
checked maximum cut depth is `hw + tf`, using the clear web depth plus the
retained bottom-flange thickness from the member database. The donor top flange
is removed, its bottom flange is
retained, and the remaining web is welded to the main rafter. Manual depths
above this limit are rejected; automatic rafter selection excludes incompatible
sections.

Use **View calculation report** for the equation, numerical substitution,
demand, resistance and utilisation of every check. Use **View 2D PDF** or
download **DXF**/**DWG** for coordinated plan, elevation and section sheets with complete
plate dimensions, bolt dimension chains, bolt/hole callouts, weld requirements,
and stiffener details. Calculation utilisation and design-status text are kept
in the report and intentionally omitted from the fabrication markup.
The DWG button is enabled after the installed AutoCAD 2026 Core Console
successfully converts the calculated DXF; the PDF and DXF remain available if
that local converter cannot run.
Holding-down bolt steel and anchor-plate anchorage are estimated from Red Book
Table 4.6 using 25 MPa concrete. The stated embedment, anchor plate, minimum
`7d` concrete edge distance, pedestal geometry and reinforcement must still be
confirmed for the project; grout, shear keys and fabrication tolerances also
require project detailing.

## Crawl beams

Use **Add crawl beam** to open a crawl-beam input card. Enter its position and
loading details there. Added crawl beams appear on the frame preview and are
included in the generated analysis input.

## Results

- ULS combinations show member utilisation and internal-force diagrams.
- SLS combinations show horizontal and vertical deflection diagrams. Vertical
  acceptance is the variable-action increment from the permanent baseline;
  total deflection and roof-drainage status remain reported.
- Deflections include the corresponding span ratio, for example
  `Vertical 116.19 mm (Span/138)`.
- The report is printable HTML; use the browser print dialog to save a PDF.

All generated results remain subject to review by the responsible competent
engineer. A completed software run is not structural sign-off.

## Packaging boundary

`run_designer.py` is the application entry point. The files under `backend/`
and `ui/`, the analysis modules, `member_database.csv`, and
`bracing_member_database.csv` are runtime assets. `requirements-pdf.txt` is
optional and is only needed for the retained legacy equation-layout PDF helper;
the normal UI report uses printable HTML.
