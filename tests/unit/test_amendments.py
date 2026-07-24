"""Behavior tests for SF30 amendment change detection (INTK-03).

``flag_amendments`` flags change statements WITHOUT merging: a requirement is
only ever an amendment change when its ``source_ref.doc_role == "amendment"`` —
base-solicitation FAR clauses carrying the same change verbs must never be
false-flagged (the doc_role gate, not the regex, drives the decision). A change
statement referencing a base section marks those base rows ``possibly_modified``
with an ``affects`` back-pointer; both rows are always retained.
"""

from rfp_analyzer.pipeline.amendments import flag_amendments
from rfp_analyzer.pipeline.models import Requirement, SourceRef


def _req(
    req_id: str,
    verbatim: str,
    doc_role: str,
    section_label: str | None,
) -> Requirement:
    return Requirement(
        requirement_id=req_id,
        display_label=req_id,
        verbatim_text=verbatim,
        atomic_obligation=verbatim,
        binding_keyword="shall",
        req_type="instruction",
        source_ref=SourceRef(
            file_id=f"{doc_role}-file",
            filename=f"{doc_role}.pdf",
            section_label=section_label,
            page=1,
            char_start=0,
            char_end=len(verbatim),
            match="exact",
            score=100.0,
            verified=True,
            doc_role=doc_role,
        ),
        verified=True,
    )


def test_amendment_change_statement_is_flagged():
    """An amendment-sourced change statement gets is_amendment_change=True."""
    reqs = [
        _req(
            "REQ-amd000001",
            "Section L.4.2 is changed to read as follows: submit two copies.",
            doc_role="amendment",
            section_label="AMENDMENT",
        )
    ]
    out = flag_amendments(reqs)
    assert out[0].is_amendment_change is True


def test_referenced_base_row_marked_possibly_modified_with_affects_pointer():
    """A change referencing Section L.4.2 flags base L.4.2 rows and keeps both."""
    change = _req(
        "REQ-amd000002",
        "Section L.4.2 is changed to read as follows: submit two copies.",
        doc_role="amendment",
        section_label="AMENDMENT",
    )
    base_target = _req(
        "REQ-base000001",
        "The offeror shall submit one copy.",
        doc_role="base_solicitation",
        section_label="L.4.2",
    )
    base_other = _req(
        "REQ-base000002",
        "The offeror shall address evaluation factors.",
        doc_role="base_solicitation",
        section_label="M",
    )
    out = flag_amendments([change, base_target, base_other])
    # No merge: every row retained.
    assert len(out) == 3
    assert base_target.possibly_modified is True
    assert "REQ-amd000002" in base_target.affects
    # An unrelated section is untouched.
    assert base_other.possibly_modified is False
    assert base_other.affects == []


def test_base_only_set_produces_zero_change_flags():
    """With no amendment-sourced rows, nothing is flagged."""
    reqs = [
        _req("REQ-b1", "The offeror shall submit a plan.", "base_solicitation", "L"),
        _req("REQ-b2", "Proposals will be evaluated on price.", "base_solicitation", "M"),
    ]
    out = flag_amendments(reqs)
    assert all(r.is_amendment_change is False for r in out)
    assert all(r.possibly_modified is False for r in out)


def test_doc_role_gate_not_regex_drives_the_decision():
    """STRENGTHENED: identical change-verb text flags only the amendment row.

    A base_solicitation FAR clause ("is added in full text ... in lieu of the
    clause at 52.212-4") carries the exact change verbs the regex matches, yet
    must NOT be flagged — while an amendment row with the SAME text IS flagged.
    This proves the source_ref.doc_role gate, not the regex, is decisive.
    """
    far_text = (
        "The following clause is added in full text and applies in lieu of the "
        "clause at 52.212-4."
    )
    base_far = _req("REQ-basefar01", far_text, doc_role="base_solicitation", section_label="I")
    amendment_far = _req("REQ-amdfar01", far_text, doc_role="amendment", section_label="AMENDMENT")

    out = flag_amendments([base_far, amendment_far])
    assert base_far.is_amendment_change is False, "base FAR change-verbs must not be flagged"
    assert amendment_far.is_amendment_change is True, "amendment row with same verbs is flagged"
    assert len(out) == 2


def test_change_row_valid_without_amendment_number():
    """amendment_number is out of scope here; change rows are valid regardless."""
    reqs = [
        _req(
            "REQ-amd000003",
            "Paragraph H.1 is hereby revised.",
            doc_role="amendment",
            section_label="AMENDMENT",
        )
    ]
    out = flag_amendments(reqs)
    assert out[0].is_amendment_change is True


def test_various_change_verbs_are_detected():
    """The Pattern 7 change-verb family (revised/deleted/in lieu of/replaced) matches."""
    for verb_text in [
        "Clause 52.217-9 is hereby revised.",
        "The prior schedule is deleted and a new schedule inserted.",
        "This paragraph is replaced in its entirety.",
        "The delivery date is changed to read March 1.",
    ]:
        reqs = [_req("REQ-x", verb_text, "amendment", "AMENDMENT")]
        assert flag_amendments(reqs)[0].is_amendment_change is True, verb_text
