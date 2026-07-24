"""Unit tests for SF form signatures and the SF30 amendment ladder (01-05 Task 3).

Synthetic ParsedFile fixtures only — no corpus needed, CI-safe. The scanned
filename-fallback tests are the Pitfall 5 regression: a scanned SF30 must
never silently pass as a plain attachment.
"""

import pytest

from rfp_analyzer.pipeline.classify.forms import (
    AMENDMENT_FILENAME_RE,
    assign_doc_role,
    detect_combined_synopsis,
    detect_form,
)
from rfp_analyzer.pipeline.models import PageInfo, ParsedFile


def make_file(
    filename: str,
    page1_text: str = "",
    *,
    layout: str | None = None,
    scanned: bool = False,
) -> ParsedFile:
    page = PageInfo(
        page_number=1,
        quality="scanned" if scanned else "ok",
        char_count=len(page1_text),
        text=page1_text,
    )
    return ParsedFile(
        file_id="abc123def456-" + filename.rsplit(".", 1)[0].lower(),
        filename=filename,
        sha256="0" * 64,
        file_type="pdf",
        parse_status="ok",
        page_count=1,
        pages=[page],
        first_page_layout_text=layout,
    )


class TestDetectForm:
    def test_sf33_title_matches(self):
        file = make_file("base.pdf", "SOLICITATION, OFFER AND AWARD\n1. THIS CONTRACT IS RATED")
        match = detect_form(file)
        assert match is not None
        assert match.form == "sf33"

    def test_sf1449_current_variant_matches(self):
        file = make_file(
            "base.pdf",
            "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES",
        )
        match = detect_form(file)
        assert match is not None
        assert match.form == "sf1449"

    def test_sf1449_older_items_variant_with_slash_spacing_matches(self):
        # Case, whitespace, and slash-spacing tolerance on the pre-2021 title.
        file = make_file("base.pdf", "solicitation / contract / order for commercial items")
        match = detect_form(file)
        assert match is not None
        assert match.form == "sf1449"

    def test_sf30_title_matches_across_line_wrap(self):
        file = make_file("mod.pdf", "AMENDMENT OF SOLICITATION/\nMODIFICATION OF CONTRACT")
        match = detect_form(file)
        assert match is not None
        assert match.form == "sf30"

    def test_layout_text_fallback_when_default_text_misses(self):
        # Form layouts split titles across extracted words — layout mode is
        # the fallback (RESEARCH Pattern 4 note).
        file = make_file(
            "mod.pdf",
            "1. CONTRACT ID CODE",
            layout="AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT",
        )
        match = detect_form(file)
        assert match is not None
        assert match.form == "sf30"

    def test_plain_text_yields_none(self):
        file = make_file("sow.pdf", "The contractor shall provide services as described below.")
        assert detect_form(file) is None

    def test_combined_synopsis_markers_detected(self):
        file = make_file(
            "notice.pdf",
            "This notice constitutes a combined synopsis/solicitation prepared in "
            "accordance with the format in Subpart 12.6, as supplemented.",
        )
        assert detect_combined_synopsis(file) is not None
        assert detect_form(file) is None  # FAR 12.603 packages use NO form


class TestSf30Ladder:
    def test_rung1_form_text_with_amendment_number(self):
        file = make_file(
            "mod.pdf",
            "AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT\n"
            "1. CONTRACT ID CODE\n"
            "2. AMENDMENT/MODIFICATION NO. 0002\n"
            "3. EFFECTIVE DATE",
        )
        result = assign_doc_role(file)
        assert result.doc_role == "amendment"
        assert result.amendment_evidence == "form_text"
        assert result.amendment_number == "0002"

    def test_rung1_amendment_number_none_still_labeled(self):
        file = make_file("mod.pdf", "AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT")
        result = assign_doc_role(file)
        assert result.doc_role == "amendment"
        assert result.amendment_evidence == "form_text"
        assert result.amendment_number is None

    def test_rung1_amendment_number_from_layout_text(self):
        file = make_file(
            "mod.pdf",
            "AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT",
            layout="AMENDMENT/MODIFICATION NO.\nP00003",
        )
        result = assign_doc_role(file)
        assert result.amendment_number == "P00003"

    @pytest.mark.parametrize(
        "filename",
        ["Amendment_0001_signed.pdf", "sf30.pdf", "amdt2.pdf", "P00001.pdf"],
    )
    def test_rung2_scanned_page_with_amendment_filename(self, filename):
        # Pitfall 5 regression: scanned SF30 with no text layer must still be
        # labeled — honestly, as a filename-only (unverified) match.
        file = make_file(filename, "", scanned=True)
        result = assign_doc_role(file)
        assert result.doc_role == "amendment"
        assert result.amendment_evidence == "filename"

    def test_rung3_scanned_non_amendment_filename_is_not_amendment(self):
        file = make_file("attachment_J1.pdf", "", scanned=True)
        result = assign_doc_role(file)
        assert result.doc_role != "amendment"
        assert result.amendment_evidence is None

    def test_rung3_sf33_and_sf1449_are_base_solicitation(self):
        sf33 = assign_doc_role(make_file("base.pdf", "SOLICITATION, OFFER AND AWARD"))
        assert sf33.doc_role == "base_solicitation"
        sf1449 = assign_doc_role(
            make_file(
                "base.pdf",
                "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES",
            )
        )
        assert sf1449.doc_role == "base_solicitation"

    def test_rung3_plain_file_is_attachment(self):
        file = make_file("SOW_final.pdf", "The contractor shall provide services.")
        result = assign_doc_role(file)
        assert result.doc_role == "attachment"
        assert result.amendment_number is None


class TestAmendmentFilenameRegex:
    @pytest.mark.parametrize(
        "stem",
        ["Amendment_0001_signed", "sf30", "SF-30_scan", "amdt2", "mod_3", "P00001", "A00002"],
    )
    def test_amendment_style_names_match(self, stem):
        assert AMENDMENT_FILENAME_RE.search(stem) is not None

    @pytest.mark.parametrize("stem", ["attachment_J1", "SOW_final", "pricing_model_v2"])
    def test_non_amendment_names_do_not_match(self, stem):
        assert AMENDMENT_FILENAME_RE.search(stem) is None
