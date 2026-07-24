"""Unit tests for TOC disambiguation and the section tree builder (01-05 Task 2).

Synthetic ParsedFile fixtures only — no corpus needed, CI-safe. Test 1 is
the Pitfall 1 regression: the SF33 Block 9 / TOC page lists every section on
page 1 and must never seed section starts.
"""

from rfp_analyzer.pipeline.models import BlockInfo, PageInfo, ParsedFile
from rfp_analyzer.pipeline.sectioning.tree import (
    TOC_MIN_DISTINCT_HEADINGS,
    build_section_tree,
    find_toc_pages,
)

BODY = "The contractor shall provide widgets and related services under this contract."


def make_page(number: int, text: str, *, quality: str = "ok") -> PageInfo:
    return PageInfo(page_number=number, quality=quality, char_count=len(text), text=text)


def make_pdf_file(pages: list[PageInfo]) -> ParsedFile:
    return ParsedFile(
        file_id="abc123def456-base",
        filename="base.pdf",
        sha256="0" * 64,
        file_type="pdf",
        parse_status="ok",
        page_count=len(pages),
        pages=pages,
    )


def make_docx_file(blocks: list[BlockInfo]) -> ParsedFile:
    return ParsedFile(
        file_id="def456abc123-attach",
        filename="attachment.docx",
        sha256="1" * 64,
        file_type="docx",
        parse_status="ok",
        blocks=blocks,
    )


TOC_LINES = [
    "TABLE OF CONTENTS",
    "SECTION A - SOLICITATION/CONTRACT FORM .......... 2",
    "SECTION B - SUPPLIES OR SERVICES AND PRICES/COSTS .......... 4",
    "SECTION C - DESCRIPTION/SPECIFICATIONS/STATEMENT OF WORK .......... 8",
    "SECTION H - SPECIAL CONTRACT REQUIREMENTS .......... 20",
    "SECTION I - CONTRACT CLAUSES .......... 30",
    "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS .......... 40",
    "SECTION M - EVALUATION FACTORS FOR AWARD .......... 50",
]


def make_ucf_file_with_toc() -> ParsedFile:
    """55-page file: TOC on page 1, real L on page 40, real M on page 50."""
    pages = [make_page(1, "\n".join(TOC_LINES))]
    for n in range(2, 40):
        pages.append(make_page(n, BODY))
    pages.append(
        make_page(
            40,
            "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS\n" + BODY,
        )
    )
    for n in range(41, 50):
        pages.append(make_page(n, BODY))
    pages.append(make_page(50, "SECTION M - EVALUATION FACTORS FOR AWARD\n" + BODY))
    for n in range(51, 56):
        pages.append(make_page(n, BODY))
    return make_pdf_file(pages)


class TestTocDisambiguation:
    def test_toc_page_never_seeds_sections(self):
        # Pitfall 1: every section "begins" on page 1 without TOC handling.
        file = make_ucf_file_with_toc()
        sections = build_section_tree(file)
        labels = {s.label for s in sections}
        assert labels == {"L", "M"}
        node_l = next(s for s in sections if s.label == "L")
        assert node_l.locator.kind == "pages"
        assert node_l.locator.page_start == 40
        assert find_toc_pages(file) == [1]
        assert all(s.locator.page_start != 1 for s in sections)

    def test_many_headings_page_is_toc_even_without_dot_leaders(self):
        assert TOC_MIN_DISTINCT_HEADINGS == 4
        toc_no_leaders = "\n".join(
            [
                "SECTION A - SOLICITATION/CONTRACT FORM",
                "SECTION B - SUPPLIES OR SERVICES AND PRICES/COSTS",
                "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
                "SECTION M - EVALUATION FACTORS FOR AWARD",
            ]
        )
        pages = [
            make_page(1, toc_no_leaders),
            make_page(2, BODY),
            make_page(3, "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS\n" + BODY),
            make_page(4, BODY),
            make_page(5, "SECTION M - EVALUATION FACTORS FOR AWARD\n" + BODY),
        ]
        file = make_pdf_file(pages)
        assert find_toc_pages(file) == [1]
        sections = build_section_tree(file)
        node_l = next(s for s in sections if s.label == "L")
        assert node_l.locator.page_start == 3

    def test_section_spans_and_nesting(self):
        pages = []
        for n in range(1, 40):
            pages.append(make_page(n, BODY))
        pages.append(
            make_page(
                40,
                "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS\n" + BODY,
            )
        )
        pages.append(make_page(41, "L.1 General\n" + BODY))
        for n in range(42, 45):
            pages.append(make_page(n, BODY))
        pages.append(make_page(45, "L.4 Proposal format\n" + BODY))
        for n in range(46, 50):
            pages.append(make_page(n, BODY))
        pages.append(make_page(50, "SECTION M - EVALUATION FACTORS FOR AWARD\n" + BODY))
        for n in range(51, 53):
            pages.append(make_page(n, BODY))
        file = make_pdf_file(pages)

        sections = build_section_tree(file)
        node_l = next(s for s in sections if s.label == "L")
        node_m = next(s for s in sections if s.label == "M")
        assert node_l.detection == "heading"
        assert (node_l.locator.page_start, node_l.locator.page_end) == (40, 49)
        assert (node_m.locator.page_start, node_m.locator.page_end) == (50, 52)

        assert [c.label for c in node_l.children] == ["L.1", "L.4"]
        child_l1, child_l4 = node_l.children
        assert child_l1.detection == "paragraph_numbering"
        assert (child_l1.locator.page_start, child_l1.locator.page_end) == (41, 44)
        assert (child_l4.locator.page_start, child_l4.locator.page_end) == (45, 49)

    def test_docx_block_spans_with_styles_and_without(self):
        blocks = []
        for i in range(10):
            blocks.append(BlockInfo(ordinal=i, kind="paragraph", text=BODY, style="Normal"))
        blocks.append(
            BlockInfo(
                ordinal=10,
                kind="paragraph",
                text="SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
                style="Heading 1",
            )
        )
        for i in range(11, 50):
            blocks.append(BlockInfo(ordinal=i, kind="paragraph", text=BODY, style="Normal"))
        blocks.append(
            BlockInfo(
                ordinal=50,
                kind="paragraph",
                text="SECTION M - EVALUATION FACTORS FOR AWARD",
                style="Heading 1",
            )
        )
        for i in range(51, 60):
            blocks.append(BlockInfo(ordinal=i, kind="paragraph", text=BODY, style="Normal"))
        sections = build_section_tree(make_docx_file(blocks))
        node_l = next(s for s in sections if s.label == "L")
        node_m = next(s for s in sections if s.label == "M")
        assert node_l.locator.kind == "blocks"
        assert (node_l.locator.block_start, node_l.locator.block_end) == (10, 49)
        assert (node_m.locator.block_start, node_m.locator.block_end) == (50, 59)

        # Pitfall 4 fallback: no heading styles at all, text heuristics only.
        unstyled = [
            BlockInfo(ordinal=0, kind="paragraph", text="Attachment 3", style=None),
            BlockInfo(
                ordinal=1,
                kind="paragraph",
                text="SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
                style=None,
            ),
            BlockInfo(ordinal=2, kind="paragraph", text=BODY, style=None),
        ]
        sections = build_section_tree(make_docx_file(unstyled))
        assert len(sections) == 1
        assert sections[0].label == "L"
        assert (sections[0].locator.block_start, sections[0].locator.block_end) == (1, 2)

    def test_mid_document_cross_reference_does_not_steal_the_section_start(self):
        # WR-06 regression: "SECTION L of this solicitation is amended as
        # follows" is line-start anchored and matches SECTION_HEADING with the
        # whole sentence captured as the title. Because the start rule prefers
        # the LAST qualifying occurrence, the cross-reference used to beat the
        # real page-40 heading and drag the span and title with it.
        pages = []
        for n in range(1, 40):
            pages.append(make_page(n, BODY))
        pages.append(
            make_page(
                40,
                "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS\n" + BODY,
            )
        )
        for n in range(41, 45):
            pages.append(make_page(n, BODY))
        pages.append(
            make_page(45, "SECTION L of this solicitation is amended as follows:\n" + BODY)
        )
        for n in range(46, 50):
            pages.append(make_page(n, BODY))
        pages.append(make_page(50, "SECTION M - EVALUATION FACTORS FOR AWARD\n" + BODY))
        pages.append(make_page(51, BODY))

        sections = build_section_tree(make_pdf_file(pages))
        node_l = next(s for s in sections if s.label == "L")
        assert node_l.locator.page_start == 40
        assert node_l.title == "INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS"
        assert node_l.role == "instructions"

    def test_cross_reference_alone_does_not_fabricate_a_section(self):
        # A file whose only "SECTION M" mention is prose must emit no M node.
        pages = [
            make_page(1, BODY),
            make_page(2, "SECTION M is hereby deleted in its entirety.\n" + BODY),
            make_page(3, BODY),
        ]
        assert build_section_tree(make_pdf_file(pages)) == []

    def test_real_headings_are_not_mistaken_for_cross_references(self):
        # The guard must not eat legitimate UCF titles.
        pages = [
            make_page(1, BODY),
            make_page(2, "SECTION C - DESCRIPTION/SPECIFICATIONS/STATEMENT OF WORK\n" + BODY),
            make_page(3, "SECTION J - LIST OF ATTACHMENTS\n" + BODY),
            make_page(4, "SECTION M - EVALUATION FACTORS FOR AWARD\n" + BODY),
        ]
        sections = build_section_tree(make_pdf_file(pages))
        assert {s.label for s in sections} == {"C", "J", "M"}

    def test_zero_candidates_yields_honest_empty_list(self):
        # Never fabricate nodes; scanned pages (text == "") contribute nothing.
        body_only = make_pdf_file([make_page(1, BODY), make_page(2, BODY)])
        assert build_section_tree(body_only) == []

        scanned = make_pdf_file(
            [
                make_page(1, "", quality="scanned"),
                make_page(2, "", quality="scanned"),
            ]
        )
        assert build_section_tree(scanned) == []
        assert find_toc_pages(scanned) == []

    def test_role_title_attachment_gets_instructions_role(self):
        # must_have truth 4: "Proposal Submission Instructions" attachment
        # with no "SECTION L" literal still gets the instructions role.
        file = make_pdf_file(
            [
                make_page(1, "PROPOSAL SUBMISSION INSTRUCTIONS\nOfferors shall submit volumes."),
                make_page(2, BODY),
            ]
        )
        sections = build_section_tree(file)
        assert len(sections) == 1
        assert sections[0].role == "instructions"
        assert sections[0].detection == "role_title"
        assert (sections[0].locator.page_start, sections[0].locator.page_end) == (1, 2)
