"""Behavior tests for the document-map schema — the Phase 2 input contract."""

import pytest
from pydantic import TypeAdapter, ValidationError

from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import (
    BlockInfo,
    BlockSpan,
    DocumentMap,
    Locator,
    PageInfo,
    PageSpan,
    ParsedFile,
    SectionNode,
)


def _pdf_file() -> ParsedFile:
    return ParsedFile(
        file_id="aaaaaaaaaaaa-base-solicitation",
        filename="base_solicitation.pdf",
        sha256="a" * 64,
        file_type="pdf",
        parse_status="ok",
        doc_role="base_solicitation",
        page_count=2,
        pages=[
            PageInfo(
                page_number=1,
                quality="ok",
                char_count=1800,
                metrics={"alpha_ratio": 0.91, "cid_count": 0.0},
                text="SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
            ),
            PageInfo(
                page_number=2,
                quality="scanned",
                char_count=3,
                metrics={"alpha_ratio": 0.0},
                text="",
            ),
        ],
        stripped_headers=["W912DY-26-R-0012"],
        sections=[
            SectionNode(
                label="L",
                title="INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
                role="instructions",
                locator=PageSpan(page_start=1, page_end=2),
                detection="heading",
            )
        ],
        first_page_layout_text="SOLICITATION, OFFER AND AWARD",
    )


def _docx_file() -> ParsedFile:
    return ParsedFile(
        file_id="bbbbbbbbbbbb-attachment-1-sow",
        filename="attachment_1_sow.docx",
        sha256="b" * 64,
        file_type="docx",
        parse_status="ok",
        doc_role="attachment",
        page_count=None,
        blocks=[
            BlockInfo(ordinal=0, kind="paragraph", text="STATEMENT OF WORK", style="Heading 1"),
            BlockInfo(ordinal=1, kind="table", table=[["Task", "Due"], ["Kickoff", "TBD"]]),
        ],
        sections=[
            SectionNode(
                label="SOW",
                title="STATEMENT OF WORK",
                role="sow_pws",
                locator=BlockSpan(block_start=0, block_end=1),
                detection="role_title",
            )
        ],
    )


def test_document_map_json_round_trip():
    """PDF (PageSpan) + DOCX (BlockSpan) DocumentMap survives JSON round-trip intact."""
    original = DocumentMap(
        package_name="test-package",
        classification="partial_ucf",
        classification_evidence=["SECTION L heading found", "no SECTION M heading"],
        warnings=["No Section M heading found; package classified partial_ucf."],
        files=[_pdf_file(), _docx_file()],
    )
    restored = DocumentMap.model_validate_json(original.model_dump_json())
    assert restored == original


def test_locator_union_discriminates_on_kind():
    """Validating raw dicts against the Locator union yields the right model by "kind"."""
    adapter = TypeAdapter(Locator)

    page_span = adapter.validate_python({"kind": "pages", "page_start": 3, "page_end": 9})
    assert isinstance(page_span, PageSpan)
    assert page_span.page_start == 3
    assert page_span.page_end == 9

    block_span = adapter.validate_python({"kind": "blocks", "block_start": 0, "block_end": 41})
    assert isinstance(block_span, BlockSpan)
    assert block_span.block_start == 0
    assert block_span.block_end == 41


def test_document_map_defaults_include_version_and_zeroed_metrics():
    """DocumentMap() defaults: schema_version 1.0 and zeroed RunMetrics (D-09)."""
    doc_map = DocumentMap()
    assert doc_map.schema_version == "1.0"
    assert isinstance(doc_map.metrics, RunMetrics)
    assert doc_map.metrics.llm_calls == 0
    assert doc_map.metrics.input_tokens == 0
    assert doc_map.metrics.output_tokens == 0
    assert doc_map.metrics.estimated_cost_usd == 0.0


def test_page_info_rejects_unknown_quality():
    """PageInfo.quality only accepts the defined status vocabulary."""
    with pytest.raises(ValidationError):
        PageInfo(page_number=1, quality="fuzzy", char_count=10, metrics={}, text="")

    for quality in ("ok", "scanned", "empty", "low_text", "gibberish", "pending"):
        page = PageInfo(page_number=1, quality=quality, char_count=10, metrics={}, text="")
        assert page.quality == quality


def test_section_node_recursive_children_serialize():
    """SectionNode nests recursively (L -> L.4 -> L.4.2) and serializes the nesting."""
    tree = SectionNode(
        label="L",
        title="INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
        role="instructions",
        locator=PageSpan(page_start=10, page_end=40),
        detection="heading",
        children=[
            SectionNode(
                label="L.4",
                title="PROPOSAL SUBMISSION",
                role="instructions",
                locator=PageSpan(page_start=14, page_end=22),
                detection="paragraph_numbering",
                children=[
                    SectionNode(
                        label="L.4.2",
                        title="VOLUME II - TECHNICAL",
                        role="instructions",
                        locator=PageSpan(page_start=16, page_end=18),
                        detection="paragraph_numbering",
                    )
                ],
            )
        ],
    )

    dumped = tree.model_dump()
    assert dumped["children"][0]["label"] == "L.4"
    assert dumped["children"][0]["children"][0]["label"] == "L.4.2"

    restored = SectionNode.model_validate_json(tree.model_dump_json())
    assert restored == tree
    assert restored.children[0].children[0].label == "L.4.2"
