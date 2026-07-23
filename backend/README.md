# Portal Frame and Truss API

The API is the boundary between the Flet UI, the existing PortalFrame engine,
and the generic preliminary truss engine.

## Install

From the repository root:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r requirements.txt
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
- `POST /api/preview` - system-specific analysis-independent geometry.
- `POST /api/analysis` - validate the request and queue a structural analysis job.
- `GET /api/analysis/{analysis_id}/status` - retrieve queued, running, complete or failed status.
- `GET /api/analysis/{analysis_id}/results` - retrieve the completed design summary and artifact links.
- `GET /api/analysis/{analysis_id}/artifacts/{artifact}` - view the HTML design report inline or download a markup drawing.
- `GET /api/analysis/latest` — latest completed analysis snapshot, if one exists.

The preview geometry is suitable for SVG, Canvas or WebGL renderers. It does not
run structural analysis or verify member adequacy.

Analysis jobs use isolated folders under `output/analysis/jobs`. API analysis
keeps the engineering deflection calculations and results but disables the
legacy PyNite deformation window. Generated outputs remain subject to review by
the responsible competent engineer.
The API workflow generates the design report as printable HTML; it no longer
creates the legacy equation-layout PDF. The browser print dialog can save the
HTML report as a PDF when required.

Completed portal-frame results include a renderer-neutral `load_case_visualisation` object.
It contains all ULS and SLS combinations, factored member loads, member
utilisations, model geometry, local member axes, sampled global displacement
points and sampled axial, shear and bending-moment results. Deflection views use
SLS combinations only and utilisation views use ULS combinations only. The API
performs these calculations; clients should render the stored values rather than
reproduce engineering formulae.

Truss jobs return `preliminary_generic_truss_v0.4`, mass-ranked solutions,
transverse and longitudinal building geometry, automatic support layouts,
eave-column checks, optional longitudinal-girder design, calculated top- and
bottom-chord restraint nodes, member schedules, ULS reactions, governing checks
and printable HTML/JSON artifacts. Chords use a common section within each
fabricated span, web members are independently selected, and the minimum base
angle is 50x50x5. Restraint is selected as every Nth purlin and
is assumed across the whole building. Results remain preliminary until checked
against independent calculations and the applicable SANS editions are confirmed.
