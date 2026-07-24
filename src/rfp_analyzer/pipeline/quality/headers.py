"""Running header/footer stripping and the quality-stage entry point.

Implements RESEARCH Pattern 5's cross-page frequency technique (assumption
A2): a line whose digit-stripped, whitespace-collapsed, uppercased form
appears in the top/bottom line bands of at least
:data:`HEADER_FREQ_THRESHOLD` of a file's OK pages is a running
header/footer — removed from those same bands in the stored page text and
recorded on the file for auditability (Pitfall 6: header noise must not
contaminate Phase 2 requirement extraction).

Removal is band-scoped exactly like detection: a body line that happens to
normalize to a running pattern is kept, because silently deleting mid-page
content is worse than leaving one stray header line in.

:func:`apply_quality` is the single quality-stage function: classify every
PDF page (gates), empty non-ok page text so garbage never flows downstream
(D-03 flag-and-surface; D-04: text-recovery fallbacks stay deferred — none
here), then strip running lines from ok pages. Order matters: classification
runs BEFORE stripping so stripping cannot change scanned/empty
determinations, and only OK pages vote in frequency counting (scanned pages
have no text to vote with).
"""

from collections import Counter
from collections.abc import Iterable

from rfp_analyzer.pipeline.models import PageInfo, ParsedFile
from rfp_analyzer.pipeline.quality.gates import QualityThresholds, classify_page

HEADER_FREQ_THRESHOLD = 0.4
"""A normalized line must appear on >= this fraction of a file's OK pages to
count as a running header/footer (A2 — corpus-tunable)."""

RUNNING_LINE_BAND = 2
"""How many physical lines at the top and bottom of each page are candidate
running-header/footer positions (A2 — corpus-tunable)."""

MIN_VOTING_PAGES = 2
"""Below this many voting pages, frequency is meaningless — a 'running'
line needs repetition, so short files get no stripping."""

_DIGITS = str.maketrans("", "", "0123456789")


def _normalize(line: str) -> str:
    """Fold a physical line to its frequency-counting key.

    Digits are stripped first so ``Page 3 of 120`` and ``Page 47 of 120``
    count as one pattern; whitespace runs collapse to single spaces; result
    is uppercased and stripped.
    """
    return " ".join(line.translate(_DIGITS).split()).upper()


def detect_running_lines(pages: Iterable[PageInfo]) -> set[str]:
    """Normalized line patterns that run across the given pages' line bands.

    Callers pass the OK-classified pages of one file; each page votes at
    most once per pattern. Pages with no text do not vote.
    """
    counts: Counter[str] = Counter()
    voters = 0
    for page in pages:
        lines = page.text.splitlines()
        if not lines:
            continue
        voters += 1
        band = lines[:RUNNING_LINE_BAND] + lines[-RUNNING_LINE_BAND:]
        keys = {_normalize(line) for line in band}
        keys.discard("")
        counts.update(keys)
    if voters < MIN_VOTING_PAGES:
        return set()
    cutoff = HEADER_FREQ_THRESHOLD * voters
    return {key for key, n in counts.items() if n >= cutoff}


def _strip_running_lines(text: str, running: set[str]) -> str:
    """Remove running-header/footer lines from one page's top/bottom bands.

    Removal scope MUST match detection scope. Filtering the whole page
    instead silently deleted body lines that merely normalized to a running
    pattern — and since the running header is typically the solicitation
    number and digits are stripped before comparison, that is a routine
    collision (amendment references, signature blocks, numeric table rows),
    not a theoretical one. Mid-page content feeds Phase 2 requirement
    extraction, so losing it is a data-integrity defect.
    """
    lines = text.splitlines()
    last_band_start = len(lines) - RUNNING_LINE_BAND
    return "\n".join(
        line
        for index, line in enumerate(lines)
        if not (
            (index < RUNNING_LINE_BAND or index >= last_band_start)
            and _normalize(line) in running
        )
    )


def apply_quality(file: ParsedFile, thresholds: QualityThresholds | None = None) -> ParsedFile:
    """Quality stage: classify pages, empty non-ok text, strip running lines.

    - ``parse_status`` != "ok" files pass through untouched.
    - DOCX files pass through: quality gates are per-PDF-page, and DOCX
      headers/footers live in section properties that python-docx never
      interleaves into body blocks — nothing to strip here.
    - PDF files leave with zero ``"pending"`` page statuses: non-ok pages
      keep their metrics for reporting but get ``text=""`` (D-03: excluded
      from downstream usable text); ok pages get running headers/footers
      removed, with the stripped patterns recorded in
      ``file.stripped_headers``.
    """
    if file.parse_status != "ok" or file.file_type != "pdf":
        return file

    for page in file.pages:
        page.quality = classify_page(page, thresholds)

    ok_pages = [p for p in file.pages if p.quality == "ok"]
    running = detect_running_lines(ok_pages)

    for page in file.pages:
        if page.quality != "ok":
            page.text = ""
        elif running:
            page.text = _strip_running_lines(page.text, running)

    file.stripped_headers = sorted(running)
    return file
