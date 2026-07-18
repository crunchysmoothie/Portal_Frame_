# PortalFrame API

The API is the boundary between the Flet UI and the existing PortalFrame
calculation/reporting code.

## Install

From the repository root:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements-api.txt
```

## Run locally

```powershell
.\.venv314\Scripts\python.exe -m uvicorn backend.main:app --reload
```

The interactive API documentation is then available at:

<http://127.0.0.1:8000/docs>

The initial endpoints are:

- `GET /api/health` — liveness check.
- `GET /api/project` — exposed capability information.
- `GET /api/analysis/latest` — latest completed analysis snapshot, if one exists.

Analysis submission will be added after the current command-line input defaults
are extracted into validated request models.
