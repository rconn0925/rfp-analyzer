"""Behavior tests for the deterministic keyword sweep + reconciliation (EXTR-05).

The sweep is the model-free cross-check: a pure-Python regex pass over cleaned
page text that finds every binding-keyword sentence, then reconciles those hits
against the model's extraction to surface misses as ``MissedCandidate`` rows and
to supply the authoritative ``binding_keyword``. It over-generates by design — a
recall floor, not ground truth.
"""

from rfp_analyzer.pipeline.models import Requirement, SourceRef
from rfp_analyzer.pipeline.sweep import (
    SweepHit,
    flag_over_extractions,
    reconcile,
    sweep_hits,
)


def _req(verbatim: str, page: int, keyword: str = "should", file_id: str = "f") -> Requirement:
    return Requirement(
        requirement_id=f"REQ-{abs(hash((verbatim, page))) % 10**10:010d}",
        display_label="X-1",
        verbatim_text=verbatim,
        atomic_obligation=verbatim,
        binding_keyword=keyword,
        req_type="instruction",
        source_ref=SourceRef(
            file_id=file_id,
            filename="sol.pdf",
            section_label="L",
            page=page,
            char_start=0,
            char_end=len(verbatim),
            match="exact",
            score=100.0,
            verified=True,
            doc_role="base_solicitation",
        ),
        verified=True,
    )


def test_sweep_finds_only_binding_sentences_with_their_keyword():
    """Sentences with a binding keyword become hits; non-binding sentences do not."""
    text = (
        "This section describes the volumes. "
        "The offeror shall submit a technical volume. "
        "The Government may provide feedback. "
        "The contractor must maintain a QASP."
    )
    hits = sweep_hits(text, page_number=52)
    keywords = {h.binding_keyword for h in hits}
    assert keywords == {"shall", "must"}
    assert all(h.page == 52 for h in hits)
    assert any("technical volume" in h.verbatim_sentence for h in hits)
    assert not any("describes the volumes" in h.verbatim_sentence for h in hits)


def test_is_required_to_is_a_binding_keyword():
    """The multi-word 'is required to' / 'are required to' phrases are detected."""
    hits = sweep_hits("The offeror is required to register in SAM.", page_number=1)
    assert len(hits) == 1
    assert hits[0].binding_keyword == "is required to"


def test_shall_not_wins_over_shall_when_both_present():
    """A sentence carrying both 'shall not' and 'shall' reports 'shall not'."""
    text = "The offeror shall not disclose data and shall protect it."
    hits = sweep_hits(text, page_number=7)
    assert len(hits) == 1
    assert hits[0].binding_keyword == "shall not"


def test_abbreviation_guard_does_not_split_us_eg_no_or_section_numbers():
    """No./U.S./e.g. and section numbers like L.4.2 never split a sentence."""
    assert sweep_hits("The offeror shall furnish U.S. flag vessels.", 1)[0].verbatim_sentence == (
        "The offeror shall furnish U.S. flag vessels."
    )
    assert sweep_hits("The plan shall address risks, e.g. cost overruns.", 1)[
        0
    ].verbatim_sentence == "The plan shall address risks, e.g. cost overruns."
    assert sweep_hits("Submit No. 3 copies; the offeror shall label each.", 1)[
        0
    ].verbatim_sentence == "Submit No. 3 copies; the offeror shall label each."
    assert sweep_hits("Per L.4.2. the offeror shall comply.", 1)[0].verbatim_sentence == (
        "Per L.4.2. the offeror shall comply."
    )


def test_reconcile_uncovered_hit_becomes_exactly_one_missed_candidate():
    """A sweep hit no extracted requirement covers surfaces as one MissedCandidate."""
    hits = [
        SweepHit(page=52, verbatim_sentence="The offeror shall submit a technical volume.",
                 binding_keyword="shall", file_id="f"),
        SweepHit(page=52, verbatim_sentence="The contractor must maintain a QASP.",
                 binding_keyword="must", file_id="f"),
    ]
    # Only the first hit is covered by an extracted requirement.
    reqs = [_req("The offeror shall submit a technical volume.", page=52)]
    updated, missed = reconcile(reqs, hits)
    assert len(missed) == 1
    assert missed[0].verbatim_sentence == "The contractor must maintain a QASP."
    assert missed[0].binding_keyword == "must"
    assert missed[0].page == 52
    assert missed[0].file_id == "f"


def test_reconcile_sets_authoritative_binding_keyword_from_source():
    """The sweep's source-derived keyword overrides the model's guess (Pattern 6)."""
    hits = sweep_hits("The offeror shall submit a technical volume.", page_number=52)
    reqs = [_req("The offeror shall submit a technical volume.", page=52, keyword="should")]
    updated, missed = reconcile(reqs, hits)
    assert updated[0].binding_keyword == "shall"
    assert missed == []


def test_reconcile_matches_only_on_same_page():
    """A requirement on a different page never covers a hit."""
    hits = [
        SweepHit(page=52, verbatim_sentence="The contractor must maintain a QASP.",
                 binding_keyword="must", file_id="f"),
    ]
    reqs = [_req("The contractor must maintain a QASP.", page=99)]
    _, missed = reconcile(reqs, hits)
    assert len(missed) == 1


def test_flag_over_extractions_returns_requirements_with_no_sweep_support():
    """A requirement whose page has no matching sweep keyword is flagged for precision."""
    hits = sweep_hits("The offeror shall submit a technical volume.", page_number=52)
    supported = _req("The offeror shall submit a technical volume.", page=52)
    hallucinated = _req("The offeror will invent an obligation.", page=52)
    over = flag_over_extractions([supported, hallucinated], hits)
    over_ids = {r.requirement_id for r in over}
    assert hallucinated.requirement_id in over_ids
    assert supported.requirement_id not in over_ids
