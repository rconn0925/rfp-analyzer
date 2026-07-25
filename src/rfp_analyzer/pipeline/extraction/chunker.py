"""Section-scoped chunker: DocumentMap -> Chunk windows with page provenance.

RESEARCH Pattern 1. For every ``parse_status=="ok"`` file the chunker walks
every section (recursively), gathers the ``ok``-quality pages inside the
section's locator, concatenates their text, and builds a ``page_map`` of
``(char_start, char_end, page_number)`` tuples so a span later located in the
chunk text maps back to a real source page. This is what makes requirements
outside Sections L/M reachable (EXTR-04): attachments, Section C/H, and even a
file with no detected section structure all produce chunks.

Design choices (RESEARCH Pitfalls 3/4):

- **Non-ok pages are excluded** from both text and page_map — a scanned or
  gibberish page carries no trustworthy characters to ground against.
- **Oversize sections are windowed** into overlapping page windows (~1 page
  overlap) so no chunk exceeds ``max_input_chars`` and a requirement straddling
  a page break is not split. ``max_input_chars`` is an eval-tunable default,
  deliberately conservative to reserve model output room.
- **DOCX block spans never synthesize a PDF page.** A DOCX section emits a
  chunk with text from its blocks but an empty ``page_map`` — honest provenance
  over invented page numbers.
- **Sectionless files still emit chunks** over their ok pages (whole-file
  fallback) so no ok file is silently unreachable (EXTR-04 "every file").
"""

import hashlib
from collections.abc import Iterator

from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.models import (
    BlockSpan,
    Chunk,
    DocumentMap,
    PageInfo,
    PageSpan,
    ParsedFile,
    SectionNode,
)

_PAGE_JOINER = "\n"
"""Inserted between concatenated page texts; joiner chars belong to no page and
are therefore excluded from every page_map range."""


def chunk_key(text: str) -> str:
    """Return a stable ``CHK-<12hex>`` identity for a chunk's text.

    The join between an exported chunk and the drafts Claude Code records for it
    (see ``extraction.replay``). Keyed on ``normalize(text)`` ONLY — not on
    file_id — because the replay lookup runs inside the ``ExtractFn`` seam, which
    receives just ``chunk_text``. Two consequences, both intended:

    - **Content-derived, so drift is loud.** Re-chunking after a parser change
      shifts the key, and the stale recorded drafts fail to resolve and surface
      as unextracted chunks rather than silently grounding against text that
      moved underneath them (threat T-02-18).
    - **Identical text in two files shares one key.** Boilerplate (a repeated FAR
      clause page) is extracted once and replayed into both chunks, where each is
      grounded independently against its own page_map. Same input, same drafts —
      benign, and it avoids paying twice for identical text.

    Uses the same normalize() as grounding and ids, so whitespace/ligature
    variants of one chunk do not produce different keys.
    """
    digest = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
    return f"CHK-{digest[:12]}"


def iter_chunks(document_map: DocumentMap, max_input_chars: int = 24000) -> Iterator[Chunk]:
    """Yield section-scoped :class:`Chunk` windows over every ok file/section.

    ``max_input_chars`` caps each chunk's concatenated text; sections larger
    than the cap are split into overlapping page windows. The default (24000,
    ~6000 tokens) keeps each grammar-constrained model call small enough to
    complete reliably — an earlier 48000-char (~12k-token) chunk stalled the
    generation and wedged a full-corpus run. Smaller windows preserve recall
    (every page is still covered, just across more chunks) while bounding
    per-call latency. Eval-tunable (RESEARCH Open Question 1).
    """
    for file in document_map.files:
        if file.parse_status != "ok":
            continue
        sections = list(_walk_sections(file.sections))
        if sections:
            for section in sections:
                yield from _chunk_section(file, section, max_input_chars)
        else:
            # EXTR-04 whole-file fallback: a sectionless (often attachment) file
            # must still be reachable. Treat all its pages as one implicit section.
            yield from _chunk_pages(
                file,
                section_label=file.filename,
                role=None,
                pages=[p for p in file.pages if p.quality == "ok"],
                max_input_chars=max_input_chars,
            )


def _walk_sections(sections: list[SectionNode]) -> Iterator[SectionNode]:
    """Depth-first walk over the recursive section tree, parents before children."""
    for section in sections:
        yield section
        yield from _walk_sections(section.children)


def _chunk_section(
    file: ParsedFile, section: SectionNode, max_input_chars: int
) -> Iterator[Chunk]:
    label = section.label or section.role or file.filename
    if isinstance(section.locator, BlockSpan):
        # DOCX: never synthesize a PDF page. Emit text from the block span with
        # an empty page_map (page-grounding is out of scope for DOCX this phase).
        text = _docx_block_text(file, section.locator)
        if text:
            yield Chunk(
                file_id=file.file_id,
                filename=file.filename,
                section_label=label,
                role=section.role,
                doc_role=file.doc_role,
                text=text,
                page_map=[],
            )
        return

    # PDF PageSpan: gather ok pages inside the span, in page order.
    span: PageSpan = section.locator
    pages = [
        p
        for p in file.pages
        if span.page_start <= p.page_number <= span.page_end and p.quality == "ok"
    ]
    yield from _chunk_pages(file, label, section.role, pages, max_input_chars)


def _chunk_pages(
    file: ParsedFile,
    section_label: str,
    role: str | None,
    pages: list[PageInfo],
    max_input_chars: int,
) -> Iterator[Chunk]:
    for window in _window_pages(pages, max_input_chars):
        text, page_map = _assemble(window)
        yield Chunk(
            file_id=file.file_id,
            filename=file.filename,
            section_label=section_label,
            role=role,
            doc_role=file.doc_role,
            text=text,
            page_map=page_map,
        )


def _window_pages(pages: list[PageInfo], max_input_chars: int) -> Iterator[list[PageInfo]]:
    """Greedily pack pages into windows <= max_input_chars, overlapping by 1 page.

    A single page larger than the cap becomes its own window (never dropped);
    the next window then starts fresh with no overlap so packing always makes
    progress.
    """
    n = len(pages)
    i = 0
    while i < n:
        window: list[PageInfo] = []
        length = 0
        j = i
        while j < n:
            addition = len(pages[j].text) + (len(_PAGE_JOINER) if window else 0)
            if window and length + addition > max_input_chars:
                break
            window.append(pages[j])
            length += addition
            j += 1
        yield window
        if j >= n:
            break
        # Overlap by one page when more than a single page fit; otherwise advance
        # past the oversized page to guarantee progress.
        i = max(j - 1, i + 1)


def _assemble(pages: list[PageInfo]) -> tuple[str, list[tuple[int, int, int]]]:
    """Concatenate page texts and build the (char_start, char_end, page) map."""
    parts: list[str] = []
    page_map: list[tuple[int, int, int]] = []
    cursor = 0
    for idx, page in enumerate(pages):
        if idx > 0:
            parts.append(_PAGE_JOINER)
            cursor += len(_PAGE_JOINER)
        start = cursor
        parts.append(page.text)
        cursor += len(page.text)
        page_map.append((start, cursor, page.page_number))
    return "".join(parts), page_map


def _docx_block_text(file: ParsedFile, span: BlockSpan) -> str:
    """Concatenate DOCX block text within an inclusive ordinal span."""
    return "\n".join(
        b.text
        for b in file.blocks
        if span.block_start <= b.ordinal <= span.block_end and b.text
    )
