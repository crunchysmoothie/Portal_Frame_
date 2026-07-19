# PortalFrame Flet UI

## Run from PyCharm

Create one Python run configuration for `run_designer.py`, use the project root
as the working directory, and select the `.venv314` interpreter. The launcher
starts FastAPI on port 8000 and the Flet browser UI on port 8550, and stops both
when the run is stopped.

Install the UI and API dependencies from the repository root:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv314\Scripts\python.exe -m pip install -r requirements-api.txt
```

Run the API in one terminal:

```powershell
.\.venv314\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Run the UI in a browser from another terminal:

```powershell
.\.venv314\Scripts\python.exe -m flet.cli run --web --port 8550 ui/main.py
```

Open <http://127.0.0.1:8550> if the browser does not open automatically.

The UI validates and previews the request payload, provides a live SVG layout
preview, and keeps the main inputs visible in a persistent running summary. The
layout uses the shared Python roof calculation; it is not an analysis result.
The preview uses one physical scale in both directions, so a long building with
low eaves is not stretched into an unrealistically tall bracing elevation.

Portal rafters and columns can be left on **Automatic - lightest passing** or
set to an explicit I- or H-section. An explicit section is still checked through
the full SLS and ULS workflow; it is not treated as automatically adequate.

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

**View report** opens the printable HTML calculation sheet in the current browser tab;
use the browser Back action to return to the designer.
Use its **Print / save as PDF** action when a PDF is required. **Download markup
drawings** remains available for the completed, current input set.

If an input changes after analysis, run the analysis again before viewing or
downloading outputs. The browser UI does not open the legacy PyNite deformation window;
deflection checks and renderer data are still calculated and included in the
stored analysis snapshot.
