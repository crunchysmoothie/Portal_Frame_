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
bracing utilisations. The **Load combination explorer** steps through every ULS
and SLS combination and displays factored member loads, strength utilisation and
a clearly magnified deflected shape sampled from the analysed model. SLS views
show deflection but intentionally omit strength utilisation. Use **Open large
view** to inspect labels and arrows at desktop scale. **Download design report**
and **Download markup drawings** become available only for the completed,
current input set.

If an input changes after analysis, run the analysis again before downloading
outputs. The browser UI does not open the legacy PyNite deformation window;
deflection checks and renderer data are still calculated and included in the
stored analysis snapshot.
