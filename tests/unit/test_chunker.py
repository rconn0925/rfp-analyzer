"""Behavior tests for the section-scoped chunker (EXTR-04 reach + page_map).

The chunker turns a Phase 1 ``DocumentMap`` into ``Chunk`` windows that feed the
model and preserve page provenance for grounding. It must reach EVERY file and
section — attachments and Sections C/H, not just L/M — skip non-``ok`` pages, carry
each file's ``doc_role``, and window oversize sections without ever synthesizing a
PDF page for a DOCX block span.
"""

from rfp_analyzer.pipeline.extraction.chunker import iter_chunks
from rfp_analyzer.pipeline.models import (
    BlockInfo,
    BlockSpan,
    DocumentMap,
    PageInfo,
    PageSpan,
    ParsedFile,
    SectionNode,
)


def _page(n: int, text: str, quality: str = "ok") -> PageInfo:
    return PageInfo(page_number=n, quality=quality, char_count=len(text), text=text)


def _section(label: str, role: str | None, start: int, end: int) -> SectionNode:
    return SectionNode(
        label=label,
        title=label,
        role=role,
        locator=PageSpan(page_start=start, page_end=end),
        detection="heading",
    )


def _pdf(
    file_id: str,
    filename: str,
    doc_role: str,
    pages: list[PageInfo],
    sections: list[SectionNode],
) -> ParsedFile:
    return ParsedFile(
        file_id=file_id,
        filename=filename,
        sha256="0" * 64,
        file_type="pdf",
        parse_status="ok",
        doc_role=doc_role,
        pages=pages,
        sections=sections,
    )


def test_reaches_every_file_and_section_not_just_l_m():
    """L, M, an attachment SOW, and a Section C each yield >=1 chunk (EXTR-04)."""
    base = _pdf(
        "base-id",
        "base_solicitation.pdf",
        "base_solicitation",
        pages=[_page(n, f"page {n} text shall submit volume") for n in range(1, 10)],
        sections=[
            _section("L", "instructions", 1, 3),
            _section("M", "evaluation", 4, 6),
            _section("C", "sow_pws", 7, 9),
        ],
    )
    attachment = _pdf(
        "sow-id",
        "attachment_sow.pdf",
        "attachment",
        pages=[_page(n, f"sow page {n} the contractor shall perform") for n in range(1, 3)],
        sections=[_section("SOW", "sow_pws", 1, 2)],
    )
    dmap = DocumentMap(files=[base, attachment])

    labels = {c.section_label for c in iter_chunks(dmap)}
    assert {"L", "M", "C", "SOW"} <= labels


def test_page_map_covers_full_span_and_concatenates_in_order():
    """A section over pages 49..57 (all ok) yields one chunk mapping 49..57 in order."""
    pages = [_page(n, f"body of page {n}.") for n in range(49, 58)]
    f = _pdf(
        "f",
        "sol.pdf",
        "base_solicitation",
        pages=pages,
        sections=[_section("L", "instructions", 49, 57)],
    )
    chunks = list(iter_chunks(DocumentMap(files=[f])))
    assert len(chunks) == 1
    chunk = chunks[0]
    assert [pg for _, _, pg in chunk.page_map] == list(range(49, 58))
    # Each page's mapped char range indexes exactly its own source text.
    for start, end, page_number in chunk.page_map:
        assert chunk.text[start:end] == f"body of page {page_number}."
    # Text preserves page order.
    assert chunk.text.index("page 49") < chunk.text.index("page 57")


def test_non_ok_pages_are_skipped_and_excluded_from_page_map():
    """Scanned/gibberish/empty pages are dropped from text and page_map."""
    pages = [
        _page(1, "first ok page shall comply"),
        _page(2, "scanned garbage", quality="scanned"),
        _page(3, "third ok page must deliver"),
        _page(4, "", quality="empty"),
        _page(5, "gibberish soup", quality="gibberish"),
    ]
    f = _pdf(
        "f",
        "sol.pdf",
        "base_solicitation",
        pages=pages,
        sections=[_section("L", "instructions", 1, 5)],
    )
    chunks = list(iter_chunks(DocumentMap(files=[f])))
    assert len(chunks) == 1
    assert [pg for _, _, pg in chunks[0].page_map] == [1, 3]
    assert "garbage" not in chunks[0].text
    assert "gibberish" not in chunks[0].text


def test_oversize_section_is_windowed_with_overlap():
    """A section larger than max_input_chars splits into overlapping chunks.

    Each chunk's page_map must be correct for its OWN text (offsets from 0).
    """
    # Ten pages, 30 chars each; max_input_chars=70 fits 2 pages/window (61) not 3 (92).
    pages = [_page(n, f"page {n:02d} " + "x" * 22) for n in range(1, 11)]
    f = _pdf(
        "f",
        "sol.pdf",
        "base_solicitation",
        pages=pages,
        sections=[_section("C", "sow_pws", 1, 10)],
    )
    chunks = list(iter_chunks(DocumentMap(files=[f]), max_input_chars=70))
    assert len(chunks) > 1
    # Overlap: consecutive windows share at least one page number.
    for a, b in zip(chunks, chunks[1:], strict=False):
        a_pages = {pg for _, _, pg in a.page_map}
        b_pages = {pg for _, _, pg in b.page_map}
        assert a_pages & b_pages, "adjacent windows must overlap by ~1 page"
    # Every page 1..10 is covered by some window.
    covered = {pg for c in chunks for _, _, pg in c.page_map}
    assert covered == set(range(1, 11))
    # page_map offsets index into each chunk's own text.
    for c in chunks:
        for start, end, page_number in c.page_map:
            assert c.text[start:end].startswith(f"page {page_number:02d}")


def test_doc_role_flows_from_parsed_file_into_every_chunk():
    """Amendment-file chunks carry doc_role=='amendment'; base chunks 'base_solicitation'."""
    amendment = _pdf(
        "amd",
        "sf30_amendment.pdf",
        "amendment",
        pages=[_page(1, "Section L.4.2 is changed to read as follows")],
        sections=[_section("AMENDMENT", "other", 1, 1)],
    )
    base = _pdf(
        "base",
        "base.pdf",
        "base_solicitation",
        pages=[_page(1, "The offeror shall submit a technical volume")],
        sections=[_section("L", "instructions", 1, 1)],
    )
    dmap = DocumentMap(files=[amendment, base])
    by_file = {c.file_id: c for c in iter_chunks(dmap)}
    assert by_file["amd"].doc_role == "amendment"
    assert by_file["base"].doc_role == "base_solicitation"


def test_docx_block_span_section_never_synthesizes_a_page():
    """A DOCX section (BlockSpan) emits a chunk with an EMPTY page_map — no invented pages."""
    docx = ParsedFile(
        file_id="docx-att",
        filename="pws.docx",
        sha256="0" * 64,
        file_type="docx",
        parse_status="ok",
        doc_role="attachment",
        blocks=[
            BlockInfo(ordinal=0, kind="paragraph", text="The contractor shall staff the effort."),
            BlockInfo(ordinal=1, kind="paragraph", text="Deliverables must be monthly."),
        ],
        sections=[
            SectionNode(
                label="PWS",
                title="PWS",
                role="sow_pws",
                locator=BlockSpan(block_start=0, block_end=1),
                detection="heading",
            )
        ],
    )
    chunks = list(iter_chunks(DocumentMap(files=[docx])))
    assert len(chunks) == 1
    assert chunks[0].page_map == []
    assert chunks[0].doc_role == "attachment"
    assert "contractor shall" in chunks[0].text


def test_file_with_ok_pages_but_no_sections_still_yields_a_chunk():
    """EXTR-04: a sectionless attachment file is still reachable (whole-file fallback)."""
    f = _pdf(
        "flat",
        "cdrl_list.pdf",
        "attachment",
        pages=[_page(1, "CDRL A001 shall be delivered"), _page(2, "CDRL A002 must be delivered")],
        sections=[],
    )
    chunks = list(iter_chunks(DocumentMap(files=[f])))
    assert len(chunks) >= 1
    assert [pg for _, _, pg in chunks[0].page_map] == [1, 2]


def test_failed_files_are_ignored():
    """parse_status != 'ok' files produce no chunks."""
    f = ParsedFile(
        file_id="bad",
        filename="broken.pdf",
        sha256="0" * 64,
        file_type="pdf",
        parse_status="failed",
        doc_role="unknown",
        pages=[_page(1, "unreadable")],
        sections=[_section("L", "instructions", 1, 1)],
    )
    assert list(iter_chunks(DocumentMap(files=[f]))) == []
