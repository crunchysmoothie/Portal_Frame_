"""Portable, versioned PortalFrame input-file format."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Mapping

from ui.input_model import DEFAULT_VALUES


FILE_TYPE = "portalframe-inputs"
SCHEMA_VERSION = 1


class ProjectInputFileError(ValueError):
    """Raised when a saved input file cannot be safely restored."""


def dump_project_inputs(raw: Mapping[str, Any]) -> bytes:
    """Return a portable JSON file containing UI inputs, not analysis results."""

    inputs = {
        key: raw.get(key, default)
        for key, default in DEFAULT_VALUES.items()
        if key != "crawl_beams"
    }
    crawl_beams = raw.get("crawl_beams", [])
    inputs["crawl_beams"] = crawl_beams if isinstance(crawl_beams, list) else []
    document = {
        "file_type": FILE_TYPE,
        "schema_version": SCHEMA_VERSION,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
    }
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")


def load_project_inputs(contents: bytes | str) -> dict[str, Any]:
    """Parse a saved input file and merge missing fields with current defaults."""

    try:
        text = contents.decode("utf-8-sig") if isinstance(contents, bytes) else contents
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ProjectInputFileError("The selected file is not valid UTF-8 JSON.") from exc
    if not isinstance(document, dict) or document.get("file_type") != FILE_TYPE:
        raise ProjectInputFileError("This is not a PortalFrame saved-input file.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ProjectInputFileError(
            f"Unsupported saved-input version: {document.get('schema_version')!r}."
        )
    saved = document.get("inputs")
    if not isinstance(saved, dict):
        raise ProjectInputFileError("The saved-input file has no valid inputs object.")

    merged = dict(DEFAULT_VALUES)
    for key in DEFAULT_VALUES:
        if key in saved:
            merged[key] = saved[key]
    if not isinstance(merged.get("crawl_beams"), list):
        raise ProjectInputFileError("crawl_beams must be a list.")
    if any(not isinstance(item, dict) for item in merged["crawl_beams"]):
        raise ProjectInputFileError("Every crawl_beams item must be an object.")
    return merged
