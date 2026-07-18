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

The first draft validates and previews the request payload. The Run analysis
button remains disabled until `POST /api/analysis` is implemented.
