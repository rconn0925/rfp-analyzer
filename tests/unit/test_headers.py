"""Unit tests for running header/footer stripping and the apply_quality stage.

Synthetic ParsedFile fixtures only — no corpus needed, CI-safe.
"""

from rfp_analyzer.pipeline.models import BlockInfo, PageInfo, ParsedFile
from rfp_analyzer.pipeline.quality.headers import (
    HEADER_FREQ_THRESHOLD,
    apply_quality,
    detect_running_lines,
)

WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "julie"]


def make_page(
    number: int, text: str, *, char_count: int | None = None, has_images: float = 0.0
) -> PageInfo:
    return PageInfo(
        page_number=number,
        quality="pending",
        char_count=len(text) if char_count is None else char_count,
        metrics={
            "cid_count": float(text.count("(cid:")),
            "replacement_char_count": float(text.count("�")),
            "has_images": has_images,
        },
        text=text,
    )


def make_pdf_file(pages: list[PageInfo], *, parse_status: str = "ok") -> ParsedFile:
    return ParsedFile(
        file_id="abc123def456-test",
        filename="test.pdf",
        sha256="0" * 64,
        file_type="pdf",
        parse_status=parse_status,
        page_count=len(pages),
        pages=pages,
    )


def body_lines(word: str) -> list[str]:
    return [
        f"The contractor shall provide services for item {word} under this solicitation package.",
        f"Additional prose regarding deliverables {word} continues here with more detail.",
    ]


def make_running_header_file() -> ParsedFile:
    """10-page file: pages 1-9 share a header and a page-number footer."""
    pages = []
    for i in range(1, 10):
        word = WORDS[i - 1]
        text = "\n".join(["SOLICITATION W912DY-26-R-0012", *body_lines(word), f"Page {i} of 10"])
        pages.append(make_page(i, text))
    pages.append(make_page(10, "\n".join(body_lines(WORDS[9]))))
    return make_pdf_file(pages)


class TestRunningLineDetection:
    def test_header_and_footer_detected_and_stripped(self):
        file = apply_quality(make_running_header_file())
        assert len(file.stripped_headers) == 2
        for page in file.pages:
            assert "SOLICITATION" not in page.text
            assert "Page " not in page.text
            assert "contractor shall" in page.text  # body survives

    def test_page_number_variance_folds_to_one_pattern(self):
        # "Page 1 of 10" ... "Page 9 of 10" must count as ONE normalized
        # pattern (digits stripped before frequency counting), not nine.
        file = make_running_header_file()
        running = detect_running_lines(file.pages)
        page_patterns = [p for p in running if "PAGE" in p]
        assert page_patterns == ["PAGE OF"]

    def test_infrequent_line_not_stripped(self):
        # "DRAFT COPY" on 2 of 10 pages (20% < 40% threshold) survives.
        pages = []
        for i in range(1, 11):
            word = WORDS[i - 1]
            lines = body_lines(word)
            if i <= 2:
                lines = ["DRAFT COPY", *lines]
            pages.append(make_page(i, "\n".join(lines)))
        file = apply_quality(make_pdf_file(pages))
        assert file.stripped_headers == []
        assert "DRAFT COPY" in file.pages[0].text
        assert "DRAFT COPY" in file.pages[1].text

    def test_threshold_is_named_constant(self):
        assert HEADER_FREQ_THRESHOLD == 0.4

    def test_mid_page_body_line_matching_the_header_is_not_deleted(self):
        # WR-04 regression: removal must be scoped to the same top/bottom
        # bands that voted. The running header is the solicitation number,
        # and body text legitimately repeats it (amendment references,
        # signature blocks) — deleting those mid-page lines is silent
        # content loss feeding Phase 2 extraction.
        header = "SOLICITATION W912DY-26-R-0012"
        pages = []
        for i in range(1, 11):
            word = WORDS[i - 1]
            lines = [
                header,
                *body_lines(word),
                f"More prose about {word} deliverables and the associated reporting duties.",
                # Mid-page (index 4): a real body reference to the same number.
                header,
                f"Continued prose for {word} following the reference above.",
                *body_lines(word),
                f"Page {i} of 10",
            ]
            pages.append(make_page(i, "\n".join(lines)))

        file = apply_quality(make_pdf_file(pages))
        assert "SOLICITATION WDY--R-" in file.stripped_headers  # digit-stripped key

        for page in file.pages:
            lines = page.text.splitlines()
            assert lines[0] != header, "band header survived stripping"
            assert lines[-1].strip() != "", "band footer line left an artifact"
            assert header in lines, (
                f"page {page.page_number}: mid-page body reference was deleted"
            )
            assert page.text.count(header) == 1
            assert "contractor shall" in page.text


class TestApplyQuality:
    def test_scanned_page_flagged_and_emptied_no_pending_survives(self):
        scanned = make_page(1, "", char_count=0, has_images=1.0)
        ok_pages = [
            make_page(
                i,
                "\n".join(["CONTRACT NO W912DY", *body_lines(WORDS[i - 1])]),
            )
            for i in range(2, 6)
        ]
        file = apply_quality(make_pdf_file([scanned, *ok_pages]))
        assert file.pages[0].quality == "scanned"
        assert file.pages[0].text == ""  # D-03: excluded from usable text
        assert file.pages[0].metrics  # metrics kept for reporting
        for page in file.pages[1:]:
            assert page.quality == "ok"
            assert "CONTRACT NO" not in page.text  # header stripped
            assert "contractor shall" in page.text
        assert all(p.quality != "pending" for p in file.pages)

    def test_docx_file_passes_through_unchanged(self):
        file = ParsedFile(
            file_id="docx-file",
            filename="amendment.docx",
            sha256="1" * 64,
            file_type="docx",
            parse_status="ok",
            blocks=[
                BlockInfo(ordinal=0, kind="paragraph", text="Amendment 0001 details."),
                BlockInfo(ordinal=1, kind="paragraph", text="Second paragraph."),
            ],
        )
        result = apply_quality(file)
        assert result.blocks == file.blocks
        assert result.pages == []
        assert result.stripped_headers == []

    def test_failed_file_passes_through_untouched(self):
        file = ParsedFile(
            file_id="bad-file",
            filename="corrupt.pdf",
            sha256="2" * 64,
            file_type="pdf",
            parse_status="failed",
            error="pdfminer exploded",
        )
        result = apply_quality(file)
        assert result.parse_status == "failed"
        assert result.error == "pdfminer exploded"
        assert result.pages == []
        assert result.stripped_headers == []
