"""PDF parsing via pdfplumber: per-page text, raw quality metrics, memory safety.

Follows RESEARCH Pattern 1 (per-file parse with isolated failure):

- Any exception — pdfminer raises varied types on malformed PDFs — becomes a
  ParsedFile with ``parse_status="failed"``, never a crashed run (Pitfall 2).
- ``page.close()`` after consuming each page flushes pdfplumber's per-page
  cache; only our own PageInfo objects are retained (Pitfall 3 / T-01-09).
- Layout-mode extraction runs on page 1 only (feeds SF-form field
  detection in plan 01-05); body pages use default mode — layout mode is
  slower and injects artificial whitespace (RESEARCH anti-pattern).

Text is stored raw; the quality stage (plan 01-04) cleans it and assigns
final page quality — every page leaves here as ``quality="pending"``.
"""

from pathlib import Path

import pdfplumber

from rfp_analyzer.pipeline.models import PageInfo, ParsedFile
from rfp_analyzer.pipeline.parsing import sanitize_text
from rfp_analyzer.pipeline.parsing.columns import extract_text_columnar_aware


def _page_images(page) -> list:
    """Image objects on the page (Assumption A3: page.images, verified for
    pdfplumber 0.11.x; fall back to the raw objects dict if absent)."""
    try:
        return page.images
    except AttributeError:
        return page.objects.get("image", [])


def parse_pdf(path: Path, *, sha256: str, file_id: str, filename: str | None = None) -> ParsedFile:
    """Parse one PDF into a ParsedFile with per-page raw text and metrics.

    ``filename`` is the discovery-assigned name — the posix path relative to
    the package dir — so nested attachments keep the same identity the
    rejection records use. Defaults to the basename when not supplied.

    Never raises: malformed input returns ``parse_status="failed"`` with the
    exception message so the package run continues (per-file isolation).
    """
    name = path.name if filename is None else filename
    pages: list[PageInfo] = []
    columnar_pages: list[int] = []
    first_page_layout_text: str | None = None
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                # Sanitize before metrics: a lone surrogate IS a glyph with no
                # valid Unicode mapping, so counting it as a replacement char
                # feeds the gibberish gate exactly the signal it looks for.
                # Column-aware first: SOW annex spec tables are three-column, and
                # reading them line-by-line splices the wrapping Title column into
                # the middle of Description sentences. Falls through to the normal
                # reading for any page that is not a recognisable column table.
                raw, used_columns = extract_text_columnar_aware(
                    page, page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                )
                text = sanitize_text(raw)
                if used_columns:
                    columnar_pages.append(page.page_number)
                if page.page_number == 1:
                    # Must run before page.close() invalidates caches.
                    first_page_layout_text = sanitize_text(page.extract_text(layout=True) or "")
                pages.append(
                    PageInfo(
                        page_number=page.page_number,  # 1-indexed
                        quality="pending",
                        char_count=len(page.chars),
                        metrics={
                            "cid_count": float(text.count("(cid:")),
                            "replacement_char_count": float(text.count("�")),
                            "has_images": 1.0 if _page_images(page) else 0.0,
                        },
                        text=text,
                    )
                )
                page.close()  # flush cache — critical on 100-300 page PDFs
    except Exception as exc:  # pdfminer raises varied exception types
        return ParsedFile(
            file_id=file_id,
            filename=name,
            sha256=sha256,
            file_type="pdf",
            parse_status="failed",
            error=str(exc) or type(exc).__name__,
            pages=[],
        )
    return ParsedFile(
        file_id=file_id,
        filename=name,
        sha256=sha256,
        file_type="pdf",
        parse_status="ok",
        page_count=len(pages),
        pages=pages,
        first_page_layout_text=first_page_layout_text,
    )
