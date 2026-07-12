# Codex Fix Request: Wind Loading Feature Merge Blockers

Please fix the critical merge blockers on branch `feature/ruan/finish-wind-loading` before this feature is merged into `main`.

## Context

This repository is a portal frame analysis tool. The current feature branch adds and expands wind loading support, including normal/canopy and mono/duo pitched cases.

The branch pulls and compiles, and focused wind-load generation works for:

- Normal Duo Pitched
- Canopy Duo Pitched
- Normal Mono Pitched
- Canopy Mono Pitched

However, there are design-safety issues in the generated load combinations and load-case semantics.

## Critical Fixes Required

### 1. ULS combinations currently ignore generated roof dead loads

In `user_input.py`, ULS combinations use only the `D` load case:

- `1.5 DL`
- `1.2 DL + 1.6 LL`
- wind ULS combinations with `D`

But `add_dead_loads()` generates rafter dead loads under:

- `D_MAX`
- `D_MIN`

The analysis also adds member self-weight under `D` in `portal_frame_analysis.py`.

This means ULS strength checks include self-weight, but not the generated roof dead loads from `add_dead_loads()`. That can under-design members.

Please update the ULS combinations so they correctly include `D_MAX` for gravity/downward combinations and `D_MIN` for uplift/stability combinations, consistent with the SLS pattern already used in `add_load_cases()`.

Review these locations:

- `user_input.py`, `add_load_cases()`
- `user_input.py`, `add_ULS()`
- `user_input.py`, `add_dead_loads()`
- `portal_frame_analysis.py`, `build_model()`

### 2. W90 ULS combination labels conflict with actual factors

The W90 ULS combinations are named as `0.9 DL + ...`, but the factors currently use `D: 1.1`.

Example:

```python
{"name": "0.9 DL + 1.3 W90_0.2", "factors": {"D": 1.1, "W90_0.2": 1.3}}
```

Please make the combination names and factors consistent. For uplift-type wind combinations, verify whether the correct stabilizing dead-load factor should be `0.9`, and ensure `D_MIN` is included if generated roof dead load should contribute as stabilizing load.

Review these locations:

- `user_input.py`, `add_load_cases()`
- `user_input.py`, `add_ULS()`

## High-Risk Fix / Clarification

### 3. Canopy `W90_0.2` and `W90_0.3` semantics are inconsistent

In `generate_wind_loading.py`, canopy structural loading maps:

- `W90_0.2` to a downward load
- `W90_0.3` to an upward load

For normal buildings, these case names represent internal pressure variants, not simply up/down load direction.

Please either:

- preserve consistent semantics for `W90_0.2` and `W90_0.3`, or
- introduce clearer canopy-specific load case names and update load combinations accordingly.

Review:

- `generate_wind_loading.py`, `_process_canopy_structural()`
- `user_input.py`, load cases and load combinations

## Secondary Improvement

### 4. Avoid hiding real runtime/data bugs as failed trial sections

`portal_frame_analysis.py` currently suppresses broad `ValueError` and `RuntimeError` exceptions during section search. This is acceptable for true unstable trial models, but it can also hide broken load cases or model data issues.

Please narrow this handling if practical, or add diagnostics so genuine data/model errors are not reported only as "No acceptable section found".

Review:

- `portal_frame_analysis.py`, `analyze_combination()`

## Verification Requested

After making changes, please run:

```powershell
.\.venv314\Scripts\python.exe -m py_compile wind_loads.py generate_wind_loading.py user_input.py portal_frame_analysis.py strength_checks.py frame_model.py member_strength_checks.py run_full_analysis.py
```

Then run a focused generation check for these combinations:

- Normal Duo Pitched
- Canopy Duo Pitched
- Normal Mono Pitched
- Canopy Mono Pitched

For each case, confirm:

- `member_loads` are generated
- all expected wind cases appear
- ULS combinations include the correct dead-load components
- uplift combinations do not use unconservative stabilizing dead-load factors

## Acceptance Criteria

- ULS strength checks include the generated roof dead loads where appropriate.
- `D_MAX` and `D_MIN` are used intentionally and consistently.
- W90 combination names match their factors.
- Canopy wind load cases have clear, correct semantics.
- The project compiles.
- Focused wind-load generation passes for all four roof/building type combinations listed above.
