"""Project crawl-beam library and user-selection validation."""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


ONE_AT_A_TIME = "One at a time"
ALL_AT_ONCE = "All at the same time"


def crawl_beam_library() -> List[Dict]:
    """Return every crawl beam available in this project.

    Add one dictionary per installed crawl.  The library is independent of the
    ``Use Crawl Beams`` switch, so entries do not need to be commented out when
    a frame is analysed without crane loading.

    Required fields for a calculated hoist load are::

        {
            "name": "CB1",
            "slope": "left",
            "position_from_eaves_mm": 3500,
            "section_type": "I-Sections",
            "section": "203x133x25",
            "swl_kg": 2000,
            "hoist_trolley_mass_kg": 350,
            "lifting_attachment_mass_kg": 100,
            "hoist_class": "C2",
            "hoisting_speed_m_s": 0.15,
        }

    Optional supplier values include ``horizontal_load_kn``,
    ``diagonal_resultant_load_kn`` and manufacturer vertical reactions.
    """
    return [
        {
            "name": "CB1",
            "slope": "right",
            "position_from_eaves_mm": 8000,
            "section_type": "I-Sections",
            "section": "203x133x25",
            "swl_kg": 5000,
            "hoist_trolley_mass_kg": 350,
            "lifting_attachment_mass_kg": 100,
            "hoist_class": "C2",
            "hoisting_speed_m_s": 0.15,
        },
        {
            "name": "CB2",
            "slope": "left",
            "position_from_eaves_mm": 6000,
            "section_type": "I-Sections",
            "section": "203x133x25",
            "swl_kg": 5000,
            "hoist_trolley_mass_kg": 350,
            "lifting_attachment_mass_kg": 100,
            "hoist_class": "C2",
            "hoisting_speed_m_s": 0.15,
        },
    ]


def resolve_crawl_selection(
    use_crawl_beams: str,
    application: str,
    library: Iterable[Dict],
) -> Tuple[bool, str, List[Dict]]:
    """Validate the switches and return ``(enabled, mode, library_copy)``."""
    use_lookup = {"yes": True, "no": False}
    use_key = str(use_crawl_beams).strip().lower()
    if use_key not in use_lookup:
        raise ValueError('Use Crawl Beams must be "Yes" or "No".')

    mode_lookup = {
        ONE_AT_A_TIME.lower(): ONE_AT_A_TIME,
        ALL_AT_ONCE.lower(): ALL_AT_ONCE,
    }
    mode_key = str(application).strip().lower()
    if mode_key not in mode_lookup:
        raise ValueError(
            'Crawl application must be "One at a time" or "All at the same time".'
        )

    crawls = [dict(crawl) for crawl in library]
    names = [str(crawl.get("name", "")).strip() for crawl in crawls]
    if any(not name for name in names):
        raise ValueError("Every crawl in the crawl library requires a name.")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Crawl names must be unique (case-insensitive).")
    enabled = use_lookup[use_key]
    if enabled and not crawls:
        raise ValueError(
            'Use Crawl Beams is "Yes", but crawl_beam_library() contains no crawls.'
        )
    return enabled, mode_lookup[mode_key], crawls
