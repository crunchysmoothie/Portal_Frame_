"""Versioned, self-contained storage for completed portal-frame analyses.

The snapshot is the hand-off boundary between engineering analysis and report
formatting. It stores the exact input JSON together with all calculated report
records so a report never needs to rebuild or reanalyse the finite-element model.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_SNAPSHOT_PATH = Path("output/analysis/analysis_results.json")
ENGINE_SOURCE_FILES = (
    "portal_frame_analysis.py",
    "strength_checks.py",
    "member_database.csv",
)


class StaleAnalysisError(RuntimeError):
    """Raised when the current input file differs from the analysed input."""


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes(source_root: str | Path) -> dict[str, str]:
    root = Path(source_root)
    return {
        name: file_sha256(root / name)
        for name in ENGINE_SOURCE_FILES
        if (root / name).exists()
    }


def create_analysis_snapshot(
    input_path: str | Path,
    results: Mapping[str, Any],
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Create a serialisable snapshot from one completed analysis."""

    input_path = Path(input_path).resolve()
    input_bytes = input_path.read_bytes()
    input_hash = hashlib.sha256(input_bytes).hexdigest()
    input_data = json.loads(input_bytes.decode("utf-8"))
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    analysis_id = hashlib.sha256(
        f"{input_hash}:{created}".encode("utf-8")
    ).hexdigest()[:16]
    root = Path(source_root).resolve() if source_root else Path(__file__).resolve().parent

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "analysis": {
            "analysis_id": analysis_id,
            "created": created,
            "input_file": str(input_path),
            "input_sha256": input_hash,
            "engine": "portal_frame_analysis",
            "source_sha256": _source_hashes(root),
        },
        "input_data": input_data,
        "results": dict(results),
    }


def write_analysis_snapshot(
    snapshot: Mapping[str, Any],
    output_path: str | Path = DEFAULT_SNAPSHOT_PATH,
) -> Path:
    """Write a snapshot as formatted JSON and return its path."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return output_path


def load_analysis_snapshot(path: str | Path = DEFAULT_SNAPSHOT_PATH) -> dict[str, Any]:
    """Load and validate the basic structure of an analysis snapshot."""

    path = Path(path)
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    version = snapshot.get("schema_version")
    if version != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported analysis snapshot schema {version!r}; "
            f"expected {SNAPSHOT_SCHEMA_VERSION}."
        )
    for key in ("analysis", "input_data", "results"):
        if key not in snapshot:
            raise ValueError(f"Analysis snapshot is missing {key!r}.")
    return snapshot


def validate_snapshot_input(
    snapshot: Mapping[str, Any],
    allow_stale: bool = False,
) -> str:
    """Check the current input against the analysed input and return its status.

    The embedded input keeps the snapshot self-contained. If the original input
    file still exists, a changed hash is rejected unless ``allow_stale`` is true.
    """

    analysis = snapshot["analysis"]
    input_path = Path(analysis["input_file"])
    if not input_path.exists():
        return "missing"
    current_hash = file_sha256(input_path)
    if current_hash == analysis["input_sha256"]:
        return "current"
    if allow_stale:
        return "stale-allowed"
    raise StaleAnalysisError(
        "The current input file differs from the stored analysis. "
        f"Re-run run_full_analysis.py before generating the report. "
        f"Analysed SHA-256: {analysis['input_sha256']}; "
        f"current SHA-256: {current_hash}."
    )
