"""Golden-set promotion — regression tests for three measured eval bugs.

Each test here corresponds to a mistake that was actually made while extending
the exhaustive scope, and each one quietly corrupted a published number before it
was caught. They exist so extending the scope to the SOW annex cannot repeat them.
"""

from __future__ import annotations

from rfp_analyzer.eval.promote import golden_row, promote, unverified_pages
from rfp_analyzer.pipeline.models import Requirement, SourceRef

FILE = "f1"


def _req(rid: str, verbatim: str, atomic: str, page: int = 49) -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=rid,
        verbatim_text=verbatim,
        atomic_obligation=atomic,
        binding_keyword="shall",
        req_type="instruction",
        verified=True,
        source_ref=SourceRef(
            file_id=FILE, filename="Solicitation.pdf", section_label="L.5",
            doc_role="base_solicitation", page=page, verified=True,
            match="exact", score=100.0,
        ),
    )


COMPOUND = "The Offeror shall submit A, B and C."
ALWAYS = lambda p: True  # noqa: E731 - audit stub


class TestSiblingsBug:
    """BUG 1: deduplicating by verbatim dropped atomic siblings, so correct
    splitting was scored as false positives (precision read 0.757, not 0.950)."""

    def test_every_sibling_becomes_its_own_golden_row(self):
        preds = [
            _req("r1", COMPOUND, "Submit A."),
            _req("r2", COMPOUND, "Submit B."),
            _req("r3", COMPOUND, "Submit C."),
        ]
        promoted, rejected = promote(preds, [], FILE, {49}, "L", "instruction", ALWAYS)
        assert len(promoted) == 3
        assert not rejected

    def test_siblings_get_distinct_ids(self):
        preds = [_req("r1", COMPOUND, "Submit A."), _req("r2", COMPOUND, "Submit B.")]
        promoted, _ = promote(preds, [], FILE, {49}, "L", "instruction", ALWAYS)
        assert len({g["requirement_id"] for g in promoted}) == 2

    def test_id_keys_on_verbatim_and_atomic(self):
        a = golden_row(_req("r1", COMPOUND, "Submit A."), "L", "instruction")
        b = golden_row(_req("r2", COMPOUND, "Submit B."), "L", "instruction")
        assert a["requirement_id"] != b["requirement_id"]


class TestScopedMatchingBug:
    """BUG 2: scoped matching restricted candidates to pages that ALREADY had a
    golden row, so 28 predictions inside the declared range were never offered
    for audit and then reappeared as unmatched."""

    def test_pages_with_no_existing_golden_row_are_still_audited(self):
        existing = [{"file_id": FILE, "page": 49, "verbatim_text": "Something else."}]
        preds = [_req("r1", "A duty on an un-annotated page.", "Do it.", page=50)]
        promoted, _ = promote(preds, existing, FILE, {49, 50}, "L", "instruction", ALWAYS)
        assert len(promoted) == 1
        assert promoted[0]["page"] == 50

    def test_predictions_outside_the_range_are_left_alone(self):
        preds = [_req("r1", "Out of range.", "Do it.", page=99)]
        promoted, rejected = promote(preds, [], FILE, {49, 50}, "L", "instruction", ALWAYS)
        assert not promoted and not rejected


class TestAudit:
    def test_rejected_predictions_are_returned_not_discarded(self):
        """The false-positive count has to be auditable and writable-up."""
        preds = [_req("r1", "All inquires will be answered in writing.", "N/A")]
        promoted, rejected = promote(
            preds, [], FILE, {49}, "L", "instruction", lambda p: False
        )
        assert not promoted
        assert len(rejected) == 1

    def test_already_matched_predictions_are_not_re_promoted(self):
        existing = [{"file_id": FILE, "page": 49, "verbatim_text": COMPOUND}]
        promoted, _ = promote(
            [_req("r1", COMPOUND, "Submit A.")], existing, FILE, {49}, "L",
            "instruction", ALWAYS,
        )
        assert not promoted

    def test_non_enum_binding_keyword_degrades_to_none(self):
        req = _req("r1", "All contractors are required to register.", "Register.")
        req.binding_keyword = "are required to"
        assert golden_row(req, "L", "instruction")["binding_keyword"] == "none"


class TestUnverifiedPages:
    """BUG 3: a page with no golden rows AND no predictions looks identical to an
    empty page. Page 62 hid that way — 3,804 chars of real content, invisible on
    both sides of the ratio, inflating recall from 0.864 to a reported 0.985."""

    def _doc(self, pages, golden_pages):
        return {
            "exhaustive_scope": {"ranges": [{"file_id": FILE, "pages": pages}]},
            "requirements": [{"file_id": FILE, "page": p} for p in golden_pages],
        }

    def test_page_with_neither_evidence_is_reported(self):
        doc = self._doc([49, 50], [49])
        assert unverified_pages(doc, [_req("r1", "x", "y", page=49)]) == [(FILE, 50)]

    def test_page_covered_by_a_prediction_alone_is_not_reported(self):
        """A prediction proves someone looked, even if nothing was promoted."""
        doc = self._doc([49, 50], [49])
        preds = [_req("r1", "x", "y", page=49), _req("r2", "a", "b", page=50)]
        assert unverified_pages(doc, preds) == []

    def test_fully_evidenced_scope_reports_nothing(self):
        doc = self._doc([49], [49])
        assert unverified_pages(doc, [_req("r1", "x", "y", page=49)]) == []

    def test_no_declared_scope_reports_nothing(self):
        assert unverified_pages({"requirements": []}, []) == []


def test_the_real_golden_set_has_no_unverified_pages():
    """Guards the live artifact: every declared-exhaustive page has evidence."""
    import json
    from pathlib import Path

    from rfp_analyzer.pipeline.models import RequirementSet

    golden = Path("tests/eval/golden/golden_set.json")
    reqs = Path("artifacts/primary-ucf/requirements.json")
    if not reqs.exists():
        import pytest

        pytest.skip("no extraction artifact available")
    doc = json.loads(golden.read_text(encoding="utf-8"))
    rs = RequirementSet.model_validate_json(reqs.read_text(encoding="utf-8"))
    assert unverified_pages(doc, rs.requirements) == []
