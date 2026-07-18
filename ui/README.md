# PortalFrame Flet UI

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

On the Review step, select **Run analysis** to submit the validated inputs. The
UI shows job progress and then displays the member-design status, selected portal
sections, governing check, serviceability results, steel-mass breakdown and
bracing utilisations. **Download design report** and **Download markup drawings**
become available only for the completed, current input set.

If an input changes after analysis, run the analysis again before downloading
outputs. The browser UI does not open the legacy PyNite deformation renderer;
deflection checks are still calculated and included in the results.
