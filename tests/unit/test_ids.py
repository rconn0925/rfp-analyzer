"""Behavior tests for content-derived stable requirement IDs (Pattern 4).

requirement_id must be identical across re-runs (order-independent, content
hash), collapse normalize-equivalent verbatims, and keep atomic siblings and
repeat occurrences distinct. display_label is the renumberable human label —
never the stable key.
"""

import re

from rfp_analyzer.pipeline.ids import display_label, requirement_id


def test_requirement_id_is_deterministic():
    """Identical args produce an identical REQ-<10hex> id across calls."""
    a = requirement_id("file-1", "The offeror shall submit a volume.", 0, 0)
    b = requirement_id("file-1", "The offeror shall submit a volume.", 0, 0)
    assert a == b
    assert re.fullmatch(r"REQ-[0-9a-f]{10}", a)


def test_atomic_siblings_get_distinct_ids():
    """Same verbatim span, different atomic_ord → different ids."""
    verbatim = "The offeror shall submit A, B, and C."
    r1 = requirement_id("file-1", verbatim, 0, 0)
    r2 = requirement_id("file-1", verbatim, 0, 1)
    r3 = requirement_id("file-1", verbatim, 0, 2)
    assert len({r1, r2, r3}) == 3


def test_repeat_occurrence_gets_distinct_id():
    """The same sentence appearing twice (different occurrence) → different ids."""
    verbatim = "The contractor shall comply."
    first = requirement_id("file-1", verbatim, 0, 0)
    second = requirement_id("file-1", verbatim, 1, 0)
    assert first != second


def test_normalize_equivalent_verbatims_collapse_to_one_id():
    """Whitespace/ligature variants that normalize equal yield the SAME id."""
    clean = requirement_id("file-1", "shall submit the final file", 0, 0)
    noisy = requirement_id("file-1", "shall submit  the ﬁnal  fi-\nle", 0, 0)
    assert clean == noisy


def test_different_file_ids_get_distinct_ids():
    """The same verbatim in different files gets different ids."""
    a = requirement_id("file-1", "shall comply", 0, 0)
    b = requirement_id("file-2", "shall comply", 0, 0)
    assert a != b


def test_display_label_is_human_readable():
    """display_label composes section label + ordinal (renumberable, not the key)."""
    assert display_label("L", 3) == "L-3"
    assert display_label("L.4.2", 1) == "L.4.2-1"
