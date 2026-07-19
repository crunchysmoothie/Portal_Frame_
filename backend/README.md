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

The available endpoints are:

- `GET /api/health` — liveness check.
- `GET /api/project` — exposed capability information.
- `POST /api/preview` - analysis-independent frame, purlin, girt and bracing geometry.
- `POST /api/analysis` - validate the request and queue a structural analysis job.
- `GET /api/analysis/{analysis_id}/status` - retrieve queued, running, complete or failed status.
- `GET /api/analysis/{analysis_id}/results` - retrieve the completed design summary and artifact links.
- `GET /api/analysis/{analysis_id}/artifacts/{artifact}` - download a generated design report or markup drawing.
- `GET /api/analysis/latest` — latest completed analysis snapshot, if one exists.

The preview geometry is suitable for SVG, Canvas or WebGL renderers. It does not
run structural analysis or verify member adequacy.

Analysis jobs use isolated folders under `output/analysis/jobs`. API analysis
keeps the engineering deflection calculations and results but disables the
legacy PyNite deformation window. Generated outputs remain subject to review by
the responsible competent engineer.

Completed results include a renderer-neutral `load_case_visualisation` object.
It contains all ULS and SLS combinations, factored member loads, member
utilisations, model geometry, local member axes and sampled global displacement
points. The API performs these calculations; clients should render the stored
values rather than reproduce engineering formulae.
