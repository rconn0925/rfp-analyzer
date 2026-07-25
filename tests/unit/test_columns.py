"""Column-aware extraction for tabular SOW annex spec sheets."""

from __future__ import annotations

from rfp_analyzer.pipeline.parsing.columns import (
    detect_body_edge,
    extract_columnar_text,
)


def _w(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top}


def _spec_table_words() -> list[dict]:
    """A three-column spec table whose Title column wraps mid-description.

    This is the exact shape that corrupted the real annex: the title
    "Permits and / Licenses" wraps onto the second visual line, where naive
    left-to-right reading splices "Licenses" into the description sentence.
    """
    return [
        # row: 2.3.4 | Permits and Licenses | The Contractor shall obtain ... perform work
        _w("2.3.4", 66, 100), _w("Permits", 120, 100), _w("and", 160, 100),
        _w("The", 210, 100), _w("Contractor", 240, 100), _w("shall", 300, 100),
        _w("obtain", 340, 100), _w("permits", 390, 100), _w("to", 450, 100),
        _w("Licenses", 120, 112),
        _w("perform", 210, 112), _w("work", 260, 112), _w("here.", 300, 112),
        # row: 2.3.5 | Insurance | Submit a Certificate ... (description wraps,
        # which is what real spec tables do and what makes the edge detectable)
        _w("2.3.5", 66, 130), _w("Insurance", 120, 130),
        _w("Submit", 210, 130), _w("a", 260, 130), _w("Certificate", 280, 130),
        _w("per", 210, 142), _w("Section", 250, 142), _w("F.", 300, 142),
        _w("Coverage", 210, 154), _w("must", 270, 154), _w("be", 310, 154),
        _w("maintained", 210, 166), _w("throughout.", 280, 166),
        _w("2.3.6", 66, 178), _w("Forms", 120, 178), _w("See", 210, 178), _w("J-05.", 240, 178),
        _w("Forms", 210, 190), _w("are", 250, 190), _w("listed", 280, 190),
        _w("in", 210, 202), _w("the", 230, 202), _w("annex.", 260, 202),
    ]


def _prose_words() -> list[dict]:
    """An ordinary single-column page: every line starts at the same margin."""
    return [
        w
        for i, top in enumerate(range(100, 220, 12))
        for w in (_w("The", 72, top), _w("offeror", 100, top), _w(f"shall{i}", 150, top))
    ]


class TestDetection:
    def test_finds_the_description_column_edge(self):
        assert detect_body_edge(_spec_table_words()) == 210.0

    def test_prose_page_is_not_columnar(self):
        """Conservative by design — ordinary pages must fall through untouched."""
        assert detect_body_edge(_prose_words()) is None

    def test_too_few_lines_is_not_columnar(self):
        words = [_w("2.1", 66, 100), _w("Title", 120, 100), _w("Body", 210, 100)]
        assert detect_body_edge(words) is None


class TestExtraction:
    def test_wrapping_title_no_longer_splices_into_the_description(self):
        """The actual defect: 'authorizations to Licenses perform work'."""
        text = extract_columnar_text(_spec_table_words(), 210.0)
        assert "obtain permits to perform work here." in text
        assert "to Licenses perform" not in text

    def test_title_is_kept_and_reassembled_before_its_description(self):
        text = extract_columnar_text(_spec_table_words(), 210.0)
        assert "2.3.4 Permits and Licenses The Contractor shall" in text

    def test_description_spanning_lines_is_contiguous(self):
        text = extract_columnar_text(_spec_table_words(), 210.0)
        assert "Submit a Certificate per Section F." in text

    def test_each_spec_item_starts_its_own_row(self):
        rows = extract_columnar_text(_spec_table_words(), 210.0).splitlines()
        assert sum(1 for r in rows if r.startswith("2.3.")) == 3

    def test_header_band_lines_stay_standalone(self):
        """Running headers must remain their own lines so the stripper can see
        them; folded into a row they both corrupt text and become unstrippable."""
        words = [_w("Spec", 66, 20), _w("Item", 90, 20), _w("Description", 210, 20)]
        words += _spec_table_words()
        text = extract_columnar_text(words, 210.0, header_band=40.0)
        assert text.splitlines()[0] == "Spec Item Description"

    def test_no_words_yields_empty(self):
        assert extract_columnar_text([], 210.0) == ""
