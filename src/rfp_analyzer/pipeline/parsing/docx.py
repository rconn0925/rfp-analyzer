"""DOCX parsing via python-docx: ordered blocks, ordinal locators, zip-bomb guard.

Follows RESEARCH Pattern 2 (document-order block extraction):

- ``Document.iter_inner_content()`` yields paragraphs and tables interleaved
  in document order; each becomes a BlockInfo with a 0-indexed ordinal.
- DOCX has no fixed pages — locators are block ordinals, period. Never
  synthesize pagination for DOCX (RenderedPageBreak markers are unreliable
  across producers, Assumption A6).
- DOCX files are zip archives: a stdlib ``zipfile`` pre-open guard rejects
  decompression bombs (T-01-07) before python-docx ever touches the file.

Style names are recorded faithfully; heading detection (style-first with
text heuristics, Pitfall 4) belongs to the sectioning stage in plan 01-05.
"""

import zipfile
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from rfp_analyzer.pipeline.models import BlockInfo, ParsedFile
from rfp_analyzer.pipeline.parsing import sanitize_text

MAX_DOCX_UNCOMPRESSED = 1 * 1024**3
"""Total uncompressed-size cap (1 GiB) across all archive members."""

MAX_COMPRESSION_RATIO = 200
"""Max uncompressed/compressed ratio before a member is bomb-suspect."""


def _failed(name: str, sha256: str, file_id: str, error: str) -> ParsedFile:
    return ParsedFile(
        file_id=file_id,
        filename=name,
        sha256=sha256,
        file_type="docx",
        parse_status="failed",
        error=error,
        blocks=[],
    )


def _bomb_check(path: Path) -> str | None:
    """Return an error message if the archive looks like a decompression bomb."""
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > MAX_DOCX_UNCOMPRESSED:
            return (
                "decompression-bomb suspect: declared uncompressed size "
                f"{total_uncompressed} bytes exceeds cap of {MAX_DOCX_UNCOMPRESSED} bytes"
            )
        for info in infos:
            if info.compress_size > 0 and info.file_size / info.compress_size > (
                MAX_COMPRESSION_RATIO
            ):
                return (
                    "decompression-bomb suspect: member "
                    f"'{info.filename}' compression ratio exceeds {MAX_COMPRESSION_RATIO}x"
                )
    return None


def parse_docx(path: Path, *, sha256: str, file_id: str, filename: str | None = None) -> ParsedFile:
    """Parse one DOCX into a ParsedFile with ordered BlockInfo blocks.

    ``filename`` is the discovery-assigned name — the posix path relative to
    the package dir — so nested attachments keep the same identity the
    rejection records use. Defaults to the basename when not supplied.

    Never raises: bomb-suspect archives fail pre-parse, and any python-docx
    exception on malformed packages becomes ``parse_status="failed"``.
    """
    name = path.name if filename is None else filename
    try:
        bomb_error = _bomb_check(path)
    except Exception as exc:  # not a readable zip at all
        return _failed(name, sha256, file_id, str(exc) or type(exc).__name__)
    if bomb_error is not None:
        return _failed(name, sha256, file_id, bomb_error)

    blocks: list[BlockInfo] = []
    try:
        doc = Document(str(path))
        for i, item in enumerate(doc.iter_inner_content()):
            if isinstance(item, Paragraph):
                blocks.append(
                    BlockInfo(
                        ordinal=i,
                        kind="paragraph",
                        text=sanitize_text(item.text),
                        style=item.style.name if item.style is not None else None,
                    )
                )
            elif isinstance(item, Table):
                blocks.append(
                    BlockInfo(
                        ordinal=i,
                        kind="table",
                        table=[
                            [sanitize_text(cell.text) for cell in row.cells] for row in item.rows
                        ],
                    )
                )
    except Exception as exc:  # python-docx raises on malformed packages
        return _failed(name, sha256, file_id, str(exc) or type(exc).__name__)

    return ParsedFile(
        file_id=file_id,
        filename=name,
        sha256=sha256,
        file_type="docx",
        parse_status="ok",
        blocks=blocks,
    )
