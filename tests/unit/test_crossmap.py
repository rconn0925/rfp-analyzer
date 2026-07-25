"""Cross-mapping: gaps are the deliverable, so they must be found and named."""

from __future__ import annotations

from rfp_analyzer.pipeline.analysis.crossmap import cross_map, gap_summary
from rfp_analyzer.pipeline.models import Requirement, SourceRef


def _req(rid: str, obligation: str, req_type: str, page: int = 1) -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=rid,
        verbatim_text=obligation,
        atomic_obligation=obligation,
        binding_keyword="shall",
        req_type=req_type,
        verified=True,
        source_ref=SourceRef(
            file_id="f1",
            filename="sol.pdf",
            section_label="L" if req_type == "instruction" else "M",
            doc_role="base_solicitation",
            page=page,
            verified=True,
            match="exact",
            score=100.0,
        ),
    )


PHASE_IN_L = "Submit a phase-in transition plan covering the 90 day period."
PHASE_IN_M = "The Government will evaluate the feasibility of the phase-in transition plan."


def test_matching_l_and_m_are_linked_both_ways():
    reqs = [_req("L1", PHASE_IN_L, "instruction"), _req("M1", PHASE_IN_M, "evaluation")]
    by_id = {m.requirement_id: m for m in cross_map(reqs)}
    assert by_id["L1"].gap_kind == "mapped"
    assert by_id["M1"].gap_kind == "mapped"
    assert "M1" in by_id["L1"].counterpart_ids
    assert "L1" in by_id["M1"].counterpart_ids


def test_l_without_m_is_flagged():
    reqs = [
        _req("L1", "Submit a signed bank reference showing financial resources.", "instruction"),
        _req("M1", "The Government will evaluate the offeror's safety DART rate.", "evaluation"),
    ]
    by_id = {m.requirement_id: m for m in cross_map(reqs)}
    assert by_id["L1"].gap_kind == "l_without_m"
    assert by_id["L1"].counterpart_ids == []
    assert "not be scored" in by_id["L1"].rationale


def test_m_without_l_is_flagged():
    reqs = [
        _req("L1", "Submit a signed bank reference showing financial resources.", "instruction"),
        _req("M1", "The Government will evaluate the offeror's safety DART rate.", "evaluation"),
    ]
    by_id = {m.requirement_id: m for m in cross_map(reqs)}
    assert by_id["M1"].gap_kind == "m_without_l"
    assert "no Section L instruction" in by_id["M1"].rationale


def test_sow_without_either_is_flagged():
    reqs = [_req("C1", "Maintain SPRS registration through final payment.", "sow_pws")]
    result = cross_map(reqs)
    assert result[0].gap_kind == "sow_without_either"


def test_sow_matching_an_instruction_is_mapped_not_flagged():
    duty = "Submit a Certificate of Insurance per Section F."
    reqs = [_req("C1", duty, "sow_pws"), _req("L1", duty, "instruction")]
    by_id = {m.requirement_id: m for m in cross_map(reqs)}
    assert by_id["C1"].gap_kind == "mapped"


def test_every_requirement_gets_a_row_including_gaps():
    """A matrix that filtered out unmapped rows would hide the whole finding."""
    reqs = [
        _req("L1", PHASE_IN_L, "instruction"),
        _req("M1", PHASE_IN_M, "evaluation"),
        _req("C1", "Provide janitorial services for the facilities.", "sow_pws"),
    ]
    result = cross_map(reqs)
    assert len(result) == 3
    assert {m.requirement_id for m in result} == {"L1", "M1", "C1"}


def test_bucketing_uses_req_type_not_section_label():
    """An instruction living in an attachment is still an L-side duty."""
    req = _req("A1", PHASE_IN_L, "instruction")
    req.source_ref.section_label = "J"
    other = _req("M1", PHASE_IN_M, "evaluation")
    by_id = {m.requirement_id: m for m in cross_map([req, other])}
    assert by_id["A1"].gap_kind == "mapped"


def test_score_is_zero_when_unmapped_and_positive_when_mapped():
    reqs = [_req("L1", PHASE_IN_L, "instruction"), _req("M1", PHASE_IN_M, "evaluation")]
    by_id = {m.requirement_id: m for m in cross_map(reqs)}
    assert by_id["L1"].score > 0
    assert cross_map([_req("C1", "Unrelated duty about vehicles.", "sow_pws")])[0].score == 0.0


def test_is_deterministic():
    reqs = [_req("L1", PHASE_IN_L, "instruction"), _req("M1", PHASE_IN_M, "evaluation")]
    assert [m.model_dump() for m in cross_map(reqs)] == [m.model_dump() for m in cross_map(reqs)]


def test_gap_summary_counts_every_kind():
    reqs = [
        _req("L1", "Submit a signed bank reference showing financial resources.", "instruction"),
        _req("M1", "The Government will evaluate the offeror's safety DART rate.", "evaluation"),
        _req("C1", "Provide janitorial services for the facilities.", "sow_pws"),
    ]
    summary = gap_summary(cross_map(reqs))
    assert summary["l_without_m"] == 1
    assert summary["m_without_l"] == 1
    assert summary["sow_without_either"] == 1
    assert summary["mapped"] == 0


def test_empty_input_yields_no_rows():
    assert cross_map([]) == []


def test_delegated_l_to_m_pattern_is_a_known_false_gap():
    """Regression guard for the measured LIMITATION in crossmap.py.

    N4008526R0033's Section L delegates content to M ("responses to each
    non-price factor as specified in Section M"), so M carries the substantive
    submittal instructions. Similarity alone reports those as m_without_l, which
    is wrong — they are the RFP's structure, not gaps. This test PINS the current
    (known-wrong) behaviour so a future factor-anchored fix is a visible change
    rather than a silent one.
    """
    reqs = [
        _req(
            "L1",
            "Include in the non-price proposal a response to each non-price factor "
            "specified in Section M.",
            "instruction",
        ),
        _req(
            "M1",
            "Submit a narrative demonstrating understanding of and approach to the "
            "PWS service requirements.",
            "evaluation",
        ),
    ]
    by_id = {m.requirement_id: m for m in cross_map(reqs)}
    assert by_id["M1"].gap_kind == "m_without_l", (
        "if this now maps, the factor-anchored fix landed — update the LIMITATION note"
    )
