"""Canonical SANS 10160 loading-code edition selections."""

from __future__ import annotations


SANS_10160_LATEST_EDITIONS = (
    "Latest — SANS 10160-1:2019 Ed. 1.3; "
    "10160-2:2011 Ed. 1.1; 10160-3:2019 Ed. 2.1"
)
SANS_10160_PREVIOUS_EDITIONS = (
    "Previous — SANS 10160-1:2010 Ed. 1; "
    "10160-2:2011 Ed. 1.1; 10160-3:2011 Ed. 1.1"
)
SANS_10160_LOADING_CODES = (
    SANS_10160_LATEST_EDITIONS,
    SANS_10160_PREVIOUS_EDITIONS,
)

# Values written by earlier PortalFrame versions.  The short labels retain
# their original meaning; the temporary project-schedule value did not record
# an edition, so it migrates to the current/latest default.
_LEGACY_LOADING_CODE_MIGRATIONS = {
    "2019": SANS_10160_LATEST_EDITIONS,
    "SANS 10160-1:2019": SANS_10160_LATEST_EDITIONS,
    "Pre-2019": SANS_10160_PREVIOUS_EDITIONS,
    "Project C1-C6 schedule": SANS_10160_LATEST_EDITIONS,
}


def normalize_sans_10160_loading_code(value: object) -> str:
    """Return a canonical latest/previous edition-set value when possible."""

    text = str(value or "").strip()
    return _LEGACY_LOADING_CODE_MIGRATIONS.get(text, text)
