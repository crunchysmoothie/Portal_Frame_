# PortalFrame User Guide

PortalFrame is operated through its local browser interface. Structural inputs,
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

1. Enter the building geometry, wind data, supports, bracing, portal sections,
   and any crawl beams in the UI.
2. Review the scaled frame preview and validation messages.
3. Select **Run analysis**.
4. Review ULS utilisation and SLS deflection results. A utilisation above 1.0
   is a reported failure, not an analysis error.
5. Open the HTML calculation report or download the markup drawings.

Changing an input makes previous results stale. Run the analysis again before
using reports or drawings.

## Section selection

Rafters and columns may use **Automatic - lightest passing** or an explicit
section. An explicit section is analysed and reported as selected, including
utilisations and deflections above the acceptance limit.

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
