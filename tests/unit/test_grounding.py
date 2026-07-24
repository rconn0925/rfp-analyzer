"""Behavior tests for the EXTR-02 grounding backbone (verify.py).

``ground(verbatim, page_text)`` — normalize both sides, locate the quote in the
page (exact substring, then rapidfuzz fuzzy), return a scored span into the
*normalized page text* or ``None``. This is the hallucination gate: a quote that
cannot be located returns ``None`` and is never given an invented position.
"""

from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.grounding.verify import build_source_ref, ground
from rfp_analyzer.pipeline.models import Chunk

# --- ground(): normalize, locate, score --------------------------------------


def test_ground_exact_substring_scores_100():
    """A verbatim quote present in the page grounds exact with score 100.0."""
    page = "SECTION L. The offeror shall submit a technical volume by the due date."
    kind, start, end, score = ground("The offeror shall submit a technical volume", page)
    assert kind == "exact"
    assert score == 100.0
    # The returned span indexes the normalized page text.
    assert normalize(page)[start:end] == normalize("The offeror shall submit a technical volume")


def test_ground_ligature_and_hyphenation_still_exact():
    """A quote differing only by ligature/soft-hyphen grounds exact (both normalized)."""
    # Page text carries a fi-ligature and a soft line-break hyphen; the model quote
    # is the clean form. Normalization on both sides makes them identical.
    page = "The contractor shall provide the ﬁnal deliver-\nables to the Government."
    result = ground("The contractor shall provide the final deliverables", page)
    assert result is not None
    kind, _start, _end, score = result
    assert kind == "exact"
    assert score == 100.0


def test_ground_noisy_quote_matches_fuzzy_above_threshold():
    """Residual noise (a stray typo) still grounds fuzzy above the default threshold."""
    page = "The offeror shall submit the final technical volume no later than 3:00 PM."
    # 'finol' instead of 'final' — one edit, well above 92 partial_ratio.
    result = ground("The offeror shall submit the finol technical volume", page)
    assert result is not None
    kind, start, end, score = result
    assert kind == "fuzzy"
    assert score >= 92.0
    assert 0 <= start < end <= len(normalize(page))


def test_ground_absent_quote_returns_none():
    """A quote that is nowhere on the page returns None (below threshold)."""
    page = "The offeror shall submit a technical volume and a price volume."
    assert ground("Payment terms are net thirty days after invoice receipt", page) is None


def test_ground_empty_quote_returns_none():
    """An empty quote never spuriously grounds."""
    page = "The offeror shall submit a technical volume."
    assert ground("", page) is None


def test_ground_whitespace_only_quote_returns_none():
    """A whitespace-only quote never spuriously grounds."""
    page = "The offeror shall submit a technical volume."
    assert ground("   \n\t  ", page) is None


# --- build_source_ref(): map matched offset to a real page -------------------


def _chunk(text: str, page_map, doc_role: str = "base_solicitation") -> Chunk:
    return Chunk(
        file_id="aaaaaaaaaaaa-base-solicitation",
        filename="base_solicitation.pdf",
        section_label="L",
        role="instructions",
        doc_role=doc_role,
        text=text,
        page_map=page_map,
    )


def test_build_source_ref_computes_page_from_page_map():
    """A quote living in the page-50 region yields SourceRef.page == 50 (from the map)."""
    # chunk.text spans two pages; page_map bands are over the *normalized* chunk text.
    page49 = "SECTION L. General instructions apply. "
    page50 = "The offeror shall submit the past-performance volume separately."
    text = page49 + page50
    boundary = len(normalize(page49)) + 1  # +1 for the normalized space joining pages
    page_map = [(0, boundary, 49), (boundary, len(normalize(text)), 50)]

    ref = build_source_ref(
        "The offeror shall submit the past-performance volume", _chunk(text, page_map)
    )
    assert ref.verified is True
    assert ref.match in {"exact", "fuzzy"}
    assert ref.page == 50


def test_build_source_ref_copies_chunk_identity_on_hit():
    """A grounded ref copies file_id/filename/section_label from the chunk."""
    text = "The offeror shall submit a technical volume."
    page_map = [(0, len(normalize(text)), 49)]
    ref = build_source_ref("shall submit a technical volume", _chunk(text, page_map))
    assert ref.verified is True
    assert ref.file_id == "aaaaaaaaaaaa-base-solicitation"
    assert ref.filename == "base_solicitation.pdf"
    assert ref.section_label == "L"
    assert ref.page == 49
    assert ref.char_start is not None
    assert ref.char_end is not None


def test_build_source_ref_ungroundable_is_flagged_not_dropped():
    """An ungroundable quote -> verified=False, match='none', page=None (never dropped)."""
    text = "The offeror shall submit a technical volume."
    page_map = [(0, len(normalize(text)), 49)]
    ref = build_source_ref(
        "Invoices are payable net thirty days after receipt", _chunk(text, page_map)
    )
    assert ref.verified is False
    assert ref.match == "none"
    assert ref.page is None
    assert ref.char_start is None
    assert ref.char_end is None
    # Identity is still carried so the flag is traceable.
    assert ref.file_id == "aaaaaaaaaaaa-base-solicitation"


def test_build_source_ref_threads_doc_role_on_grounded_path():
    """A grounded amendment ref carries doc_role='amendment' (INTK-03 provenance)."""
    text = "Section L.4.2 is changed to read: the offeror shall submit two copies."
    page_map = [(0, len(normalize(text)), 3)]
    ref = build_source_ref(
        "the offeror shall submit two copies", _chunk(text, page_map, doc_role="amendment")
    )
    assert ref.verified is True
    assert ref.doc_role == "amendment"


def test_build_source_ref_threads_doc_role_on_ungroundable_path():
    """An ungroundable amendment quote STILL carries doc_role='amendment'.

    An amendment quote that cannot be grounded must still know it came from an
    amendment, or downstream INTK-03 gating silently loses the provenance.
    """
    text = "Section L.4.2 is changed to read: the offeror shall submit two copies."
    page_map = [(0, len(normalize(text)), 3)]
    ref = build_source_ref(
        "some hallucinated obligation not on this page",
        _chunk(text, page_map, doc_role="amendment"),
    )
    assert ref.verified is False
    assert ref.doc_role == "amendment"


def test_build_source_ref_page_only_ever_from_page_map():
    """A chunk whose map has pages {49, 50} can only ever yield page in {49, 50} or None.

    Reviewer-checkable invariant: the page number is never copied from anything
    other than chunk.page_map, asserted across a grounded and an ungroundable quote.
    """
    page49 = "SECTION L. General instructions apply here. "
    page50 = "The offeror shall submit the cost volume in a sealed envelope."
    text = page49 + page50
    boundary = len(normalize(page49)) + 1
    page_map = [(0, boundary, 49), (boundary, len(normalize(text)), 50)]

    grounded = build_source_ref(
        "shall submit the cost volume in a sealed envelope", _chunk(text, page_map)
    )
    assert grounded.page in {49, 50}

    missing = build_source_ref(
        "entirely unrelated boilerplate paragraph text", _chunk(text, page_map)
    )
    assert missing.page is None
