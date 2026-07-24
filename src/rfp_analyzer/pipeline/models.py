"""Document-map schema: the versioned contract Phase 2 consumes.

One :class:`DocumentMap` is produced per pipeline run and serialized to
``document_map.json``. Locations are expressed through the :data:`Locator`
union: PDFs use 1-indexed page spans, DOCX files use 0-indexed block-ordinal
spans (DOCX has no fixed pages — never synthesize page numbers for it).

Schema versioning: bump ``DocumentMap.schema_version`` on any breaking field
change; Phase 2 validates maps against this module on load.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from rfp_analyzer.pipeline.metrics import RunMetrics


class PageSpan(BaseModel):
    """A contiguous range of PDF pages, 1-indexed and inclusive."""

    kind: Literal["pages"] = "pages"
    page_start: int
    page_end: int


class BlockSpan(BaseModel):
    """A contiguous range of DOCX blocks.

    Ordinals are 0-indexed positions from ``Document.iter_inner_content()``
    (paragraphs and tables interleaved in document order), inclusive.
    """

    kind: Literal["blocks"] = "blocks"
    block_start: int
    block_end: int


Locator = Annotated[PageSpan | BlockSpan, Field(discriminator="kind")]
"""Location of a section within its source file, discriminated by ``kind``."""


class PageInfo(BaseModel):
    """Per-page parse output and quality status for a PDF page.

    ``quality`` starts as ``"pending"`` when a page is constructed at parse
    time, before the quality stage runs. Serialized document maps must never
    contain ``"pending"`` — the quality stage assigns every page a final
    status (``ok``/``scanned``/``empty``/``low_text``/``gibberish``).
    """

    page_number: int
    quality: Literal["ok", "scanned", "empty", "low_text", "gibberish", "pending"]
    char_count: int
    metrics: dict[str, float] = Field(default_factory=dict)
    text: str = ""


class BlockInfo(BaseModel):
    """One document-order block from a DOCX file (paragraph or table)."""

    ordinal: int
    kind: Literal["paragraph", "table"]
    text: str = ""
    style: str | None = None
    table: list[list[str]] | None = None


class SectionNode(BaseModel):
    """A node in the detected section hierarchy (recursive)."""

    label: str
    title: str
    role: (
        Literal[
            "instructions",
            "evaluation",
            "sow_pws",
            "special_requirements",
            "clauses",
            "attachments_list",
            "other",
        ]
        | None
    ) = None
    locator: Locator
    detection: Literal["form_anchor", "heading", "role_title", "paragraph_numbering"]
    children: list["SectionNode"] = Field(default_factory=list)


class ParsedFile(BaseModel):
    """Parse result and structural analysis for one file in the package."""

    file_id: str
    filename: str
    sha256: str
    file_type: Literal["pdf", "docx", "other"]
    """"other" is only valid on rejected records (unsupported/blocked files);
    parsed files are always "pdf" or "docx"."""
    parse_status: Literal["ok", "failed", "rejected"]
    error: str | None = None
    doc_role: Literal["base_solicitation", "amendment", "attachment", "unknown"] = "unknown"
    amendment_number: str | None = None
    amendment_evidence: Literal["form_text", "filename"] | None = None
    page_count: int | None = None
    pages: list[PageInfo] = Field(default_factory=list)
    blocks: list[BlockInfo] = Field(default_factory=list)
    stripped_headers: list[str] = Field(default_factory=list)
    sections: list[SectionNode] = Field(default_factory=list)
    first_page_layout_text: str | None = None
    """Layout-mode text of page 1, captured by the PDF parser for SF-form
    field extraction (e.g. SF30 Block 2 amendment number). None for DOCX."""


class DocumentMap(BaseModel):
    """Root artifact for one package run — the Phase 2 input contract."""

    schema_version: str = "1.0"
    package_name: str = ""
    classification: Literal["full_ucf", "partial_ucf", "non_ucf_commercial", "unknown"] = "unknown"
    classification_evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    files: list[ParsedFile] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
