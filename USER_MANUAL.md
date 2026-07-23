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

## Section selection

Rafters and columns may use **Automatic - lightest passing** or an explicit
section. An explicit section is analysed and reported as selected, including
utilisations and deflections above the acceptance limit.

## Preliminary generic truss workflow

Truss mode provides a generic preliminary design path:

- mono- or duo-pitched Warren-with-verticals, Pratt or Howe trusses;
- one comma-separated list of transverse span lengths; the entry count becomes
  the span count and their sum becomes the building width;
- main columns at the outer edges and either centre columns or longitudinal
  girders at internal span boundaries;
- user-entered truss depth limits and increments, with separate practical-cost
  and individually optimised-web mass comparisons;
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
- ranked solutions, member schedules, design checks and complete support reactions.

The truss output is a calculation draft. Member forces, axial resistance,
slenderness and vertical deflection are calculated and shown in the report.
The warning means that gussets, bolts, welds, bearings, restraint-member
capacity and an independent project check remain outstanding. SANS
editions must also be confirmed. Back-to-back angles are
treated as symmetric heel-to-heel pairs without any additional gusset-gap benefit.
Connections, net-section rupture, gussets, bolts, welds, bearings, splices,
bracing-member design, concrete tilt-up capacity/detailing, crawl beams and
hoist actions are excluded from this iteration. If centre-column design is
disabled, internal columns remain idealised supports and their mass is excluded;
the main eave-column section is used only as a preliminary stiffness proxy.

## Crawl beams

Use **Add crawl beam** to open a crawl-beam input card. Enter its position and
loading details there. Added crawl beams appear on the frame preview and are
included in the generated analysis input.

## Results

- ULS combinations show member utilisation and internal-force diagrams.
- SLS combinations show horizontal and vertical deflection diagrams.
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
