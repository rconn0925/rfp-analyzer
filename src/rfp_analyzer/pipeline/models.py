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


# --- Phase 2: requirement extraction & grounding contract ---------------------


class SourceRef(BaseModel):
    """Computed, string-match-verified provenance for one requirement (EXTR-02).

    Never a model-emitted citation: ``page``/``char_start``/``char_end`` are
    located in the source page text after normalization. ``doc_role`` carries
    the owning ParsedFile.doc_role so INTK-03 amendment gating can distinguish
    amendment rows from base rows without re-reading the chunk — provenance kept
    explicit and reusable rather than an ``is_amendment`` bool. An unverifiable
    reference is representable (``verified=False``, ``page=None``), never forced
    to invent a page.
    """

    file_id: str
    filename: str
    section_label: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    match: Literal["exact", "fuzzy", "none"]
    score: float
    verified: bool
    doc_role: str


class RequirementDraft(BaseModel):
    """One model-extracted obligation before grounding and stable-ID assignment.

    Doubles as the engine's structured-output schema, so it stays flat — Literal enums
    only, no constrained numerics, no recursive nesting. ``verbatim_text`` is the
    exact source span (this grounds); ``atomic_obligation`` is the single-duty
    rewrite (display/analysis text, never grounded).
    """

    verbatim_text: str
    atomic_obligation: str
    binding_keyword: Literal["shall", "must", "will", "should", "shall not", "none"]
    type_guess: Literal[
        "instruction",
        "evaluation",
        "sow_pws",
        "special_requirements",
        "clause",
        "attachment",
        "other",
    ]
    parent_index: int | None = None


class RequirementBatch(BaseModel):
    """A chunk's worth of extracted drafts — the structured-output root."""

    requirements: list[RequirementDraft] = Field(default_factory=list)


class Chunk(BaseModel):
    """One section-scoped extraction window plus its page-offset map (EXTR-01).

    ``page_map`` records ``(char_start, char_end, page_number)`` per page so a
    grounded span located in ``text`` maps back to a source page number.
    """

    file_id: str
    filename: str
    section_label: str
    role: str | None = None
    doc_role: str
    text: str
    page_map: list[tuple[int, int, int]] = Field(default_factory=list)


class Requirement(BaseModel):
    """A grounded, stably-identified requirement row — the extraction deliverable.

    ``requirement_id`` is the content-derived stable key (never renumbered);
    ``display_label`` is the human label (renumberable). Amendment provenance
    (``is_amendment_change``, ``possibly_modified``, ``affects``) lets INTK-03
    flag modified rows without silently merging them.
    """

    requirement_id: str
    display_label: str
    verbatim_text: str
    atomic_obligation: str
    binding_keyword: str
    req_type: str
    source_ref: SourceRef
    verified: bool
    parent_id: str | None = None
    is_amendment_change: bool = False
    possibly_modified: bool = False
    affects: list[str] = Field(default_factory=list)


class MissedCandidate(BaseModel):
    """A deterministic-sweep keyword hit not covered by any extraction (EXTR-05)."""

    file_id: str
    page: int
    verbatim_sentence: str
    binding_keyword: str


class RequirementSet(BaseModel):
    """Root artifact for one extraction run — serialized to ``requirements.json``."""

    schema_version: str = "1.0"
    package_name: str = ""
    model_name: str = ""
    requirements: list[Requirement] = Field(default_factory=list)
    missed_candidates: list[MissedCandidate] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)


# --- Phase 3: analysis & export contract ---------------------------------------


class CrossMapping(BaseModel):
    """How one requirement relates across Sections L, M, and C/SOW (ANLZ-01).

    A federal proposal fails on gaps, not on prose: an L instruction with no M
    evaluation criterion means work nobody scores, and an M criterion with no L
    instruction means a score with nothing telling you to write it. Both are
    findings a proposal manager acts on, so both are first-class rows here rather
    than a filtered-out absence.
    """

    requirement_id: str
    counterpart_ids: list[str] = Field(default_factory=list)
    gap_kind: Literal[
        "l_without_m",
        "m_without_l",
        "sow_without_either",
        "mapped",
    ]
    rationale: str = ""
    score: float = 0.0
    """Similarity of the strongest counterpart match (0-100), 0.0 when unmapped."""


class OutlineNode(BaseModel):
    """One node of the proposal outline derived from Section L structure (ANLZ-02).

    ``node_id`` is a stable path key (e.g. ``"L.5.a"``) so requirement->node
    mapping survives renumbering of the human-facing ``title``.
    """

    node_id: str
    title: str
    volume: str = ""
    parent_node_id: str | None = None
    source_page: int | None = None


class ComplianceJudgment(BaseModel):
    """A graded compliance call for one requirement against a profile (ANLZ-04).

    ``rationale`` and ``confidence`` are mandatory companions to ``verdict``: an
    ungrounded verdict is not actionable, and a proposal manager needs to know
    which calls to re-check. ``UNKNOWN`` exists so the judge can decline rather
    than guess — a fabricated "Fully compliant" is the costliest failure here.
    """

    requirement_id: str
    verdict: Literal["fully_compliant", "partially_compliant", "non_compliant", "unknown"]
    rationale: str
    confidence: Literal["high", "medium", "low"]
    profile_evidence: list[str] = Field(default_factory=list)
    """Capability ids/snippets the verdict leans on — traceability, not decoration."""


class CapabilityProfile(BaseModel):
    """A company's capabilities, the yardstick compliance is judged against."""

    profile_id: str = "demo"
    company_name: str = ""
    is_fictional: bool = True
    """True for the demo profile. Surfaced in exports so a fictional judgment is
    never mistaken for a real assessment of a real company."""
    capabilities: list[str] = Field(default_factory=list)
    narrative: str = ""


class ComplianceMatrix(BaseModel):
    """Root artifact for one analysis run — serialized to ``matrix.json``.

    Carries the requirement set it was built from so an export is reproducible
    from a single file, and keeps analysis outputs in separate lists (rather than
    denormalized onto Requirement) so the extraction contract stays untouched.
    """

    schema_version: str = "1.0"
    package_name: str = ""
    profile: CapabilityProfile = Field(default_factory=CapabilityProfile)
    requirements: list[Requirement] = Field(default_factory=list)
    cross_mappings: list[CrossMapping] = Field(default_factory=list)
    outline: list[OutlineNode] = Field(default_factory=list)
    requirement_outline: dict[str, str] = Field(default_factory=dict)
    """requirement_id -> outline node_id. Every requirement gets a key; unmappable
    rows map to the explicit UNASSIGNED node rather than being dropped."""
    judgments: list[ComplianceJudgment] = Field(default_factory=list)
    missed_candidates: list[MissedCandidate] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
