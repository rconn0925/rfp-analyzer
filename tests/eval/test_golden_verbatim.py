"""Golden-set locatability test (EXTR-02 / threat T-02-09).

Every ``verbatim_text`` in ``golden_set.json`` must be a contiguous substring of
its cited page after grounding-identical normalization. Skips when the gitignored
primary corpus / document-map artifact is absent (CI mirrors the Phase 1
corpus-skip pattern).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.golden import check_golden

GOLDEN = Path(check_golden.__file__).with_name("golden_set.json")


def _pages_or_skip():
    pages = check_golden.load_page_text()
    if pages is None:
        pytest.skip("primary-ucf corpus/document-map unavailable (gitignored)")
    return pages


def test_every_verbatim_is_locatable():
    _pages_or_skip()
    checked, n_fail, failures = check_golden.check()
    assert checked >= 30, f"golden set unexpectedly small: {checked}"
    assert n_fail == 0, "unlocatable golden verbatims:\n" + "\n".join(failures)


def test_golden_set_shape():
    """Structural invariants that need no corpus — runs everywhere including CI."""
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    reqs = doc["requirements"]
    assert len(reqs) >= 30
    sections = {r["section"] for r in reqs}
    assert {"L", "M"} <= sections
    assert sections & {"C", "C-Annex-SOW"}, "must cover a C/SOW source"
    ids = [r["requirement_id"] for r in reqs]
    assert len(ids) == len(set(ids)), "requirement_id values must be unique"
    for r in reqs:
        assert r["verbatim_text"].strip()
        assert r["atomic_obligation"].strip()
        assert isinstance(r["page"], int)
        assert r["binding_keyword"] in {"shall", "must", "will", "should", "shall not", "none"}
        if r["parent_id"] is not None:
            assert r["parent_id"] in set(ids), "parent_id must reference a sibling"
