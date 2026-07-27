# Portal Frame and Truss Flet UI

## Run from PyCharm

Create one Python run configuration for `run_designer.py`, use the project root
as the working directory, and select the `.venv314` interpreter. The launcher
starts FastAPI on port 8000 and the Flet browser UI on port 8550, and stops both
when the run is stopped.

Install the application dependencies from the repository root:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements.txt
```

Start the complete application:

```powershell
.\.venv314\Scripts\python.exe run_designer.py
```

Open <http://127.0.0.1:8550> if the browser does not open automatically.

The UI validates and previews the request payload, provides a live SVG layout
preview, and keeps the main inputs visible in a persistent running summary. The
layout uses the shared Python roof calculation; it is not an analysis result.
The preview uses one physical scale in both directions, so a long building with
low eaves is not stretched into an unrealistically tall bracing elevation.

Select one structural system per project. **Portal frame** retains the existing
workflow. **Truss** accepts one comma-separated list of transverse span lengths
and derives the building width and span count from it. It also accepts building
length, mono/duo roof form, three Warren layouts (no verticals, intermediate
purlin verticals, or all verticals), Pratt/Howe topology, chord form, purlin
spacing, explicit truss-depth limits and automatic support choice. For multiple
spans, internal supports can be centre columns or longitudinal girders spanning
a selected number of building bays. Truss and girder options are searched and
reported with both practical-cost and individually optimised-web mass rankings.
The truss member candidate search can be lightest passing, single angles first,
or back-to-back angles first; the selected and exact candidate order are stored.
The practical option groups ordinary webs over at least three consecutive panels,
only downsizes below 75% retained utilisation and includes an 8% platework
cost-equivalent allowance. Every support has a bearing node whose aligned vertical
uses the selected supporting column or girder section. The UI includes topology reference diagrams
and scaled truss, roof-layout and girder previews. Truss reports retain an
explicit calculation-scope notice and include a downloadable member markup
showing member names, section marks and governing utilisations. Truss and girder elevations use the same physical
scale horizontally and vertically. The calculation report shows the common
chord section per span and the member force, effective length, slenderness,
resistance and governing utilisation for every modelled angle.
Centre-column design is an explicit checkbox for multiple-span centre-column
layouts. Steel columns use axial internal bearing reactions, an entered brace
spacing and a selectable section order. Concrete tilt-up dimensions and
reinforcement are captured as a visible hold point rather than being presented
as a completed concrete capacity check.

The post-analysis **Connections** page is enabled only after a portal frame has
been designed. It shows governing utilisation for base plates and haunch
connections and links to the full equation-by-equation report and dimensioned
markup. The markup provides coordinated plan, elevation, section and component
details with full bolt dimension chains, plate sizes, weld callouts and
flat-stiffener dimensions. The same canonical 2D sheets are exported as a
vector PDF, R2018 DXF and DWG. The interactive Plotly model is for in-app
inspection only and exposes no 3D-file export. Bolt geometry, prying, plates, weld groups,
supporting-member effects and stiffeners are calculated. Concrete anchor
breakout, pull-out and embedment remain visibly `INPUT_REQUIRED`.
Connection drawings omit utilisation/status text; those values remain in the
calculation report. Haunch donors omit their top flange, retain the bottom
flange and enforce the displayed database-dimension limit `h - b`.

The Foundation page requests only soil unit weight and permissible bearing
pressure. It automatically searches a common pad length, width and height and
checks ULS sliding and overturning at safety factor 1.5. Fixed concrete,
reinforcement, cover, soil-cover and friction assumptions are visible and
repeated in the result.

Portal rafters and columns can be left on **Automatic - lightest passing** or
set to an explicit I- or H-section. An explicit section is still checked through
the full SLS and ULS workflow; it is not treated as automatically adequate.
Manual portal, gable and crawl section dropdowns are ordered by section height,
then width and mass without changing automatic design-search ordering.
Internal gable columns accept any positive count and are spaced evenly across
the gable width. Their I/H section can be selected explicitly and checked as
chosen, or automatic sizing can use either the lightest passing section or
preferred database sections first.

Use **Save inputs** in the header to create a versioned
`.portalframe.json` file. **Load inputs** restores that file, validates it
against the current application, and repopulates the complete form, including
configured crawl beams. Analysis results are deliberately not stored in the
input file; select **Run analysis** after loading.

On the Review step, select **Run analysis** to submit the validated inputs. The
UI shows job progress and then displays the member-design status, selected portal
sections, governing check, serviceability results, steel-mass breakdown and
bracing utilisations. Open the dedicated **Analysis** page to step through every
ULS and SLS combination. The Loading view shows factored magnitudes, source cases
and axes directly beside scaled arrows. Deflection, internal forces and utilisation
have independent diagrams. Deflection offers Dx and Dy and labels every analysed
node, and is restricted to SLS combinations. Utilisation is restricted to ULS
combinations. Internal forces provide axial N, shear Vy and bending moment Mz using
the stored PyNite local-member sign convention.

Completed truss designs expose every analysed SLS nodal displacement through the
same Analysis page. The truss view overlays an uncluttered magnified deformed shape
on the true-scale undeformed geometry, labels the governing node and reports the
exact displacement, limit, utilisation and display magnification. Truss force and
utilisation diagrams remain future work.

The shared **Design and Loading** page contains the common design basis, wind
inputs and additional permanent roof actions for both structural systems.
Portal-frame design basis also provides an optional switch to ignore only the
vertical span/deflection acceptance limit for `1.1 DL + 1.0 LL`. The result
remains analysed, displayed and reported; horizontal drift, other SLS limits
and all ULS checks continue to govern automatic section selection.
Vertical portal-frame acceptance is based on the algebraic variable-action
increment after subtracting the matching permanent-action displacement at each
node. The total deflection remains stored, and automatic sizing rejects any
total-load rafter segment that loses or reverses its original drainage fall.
Services, ceiling, solar, fire-services and HVAC loads are included in `D_MAX`.
`D_MIN` includes ceiling, fire-services and HVAC but excludes services and
solar. Portal inputs are converted from kPa to rafter line loads using the frame
spacing; truss inputs follow the same source-load path into panel-point actions.

**View report** opens the printable HTML calculation sheet in the current browser tab;
use the browser Back action to return to the designer.
Use its **Print / save as PDF** action when a PDF is required. **Download markup
drawings** remains available for the completed, current input set. Portal
results also provide **Open connection design**. The Connections page provides
**View calculation report**, **View 2D PDF**, **Download DXF** and
**Download DWG** for the calculated plates, bolts, distances, welds and
stiffeners.

If an input changes after analysis, run the analysis again before viewing or
downloading outputs. The browser UI does not open the legacy PyNite deformation window;
deflection checks and renderer data are still calculated and included in the
stored analysis snapshot.
