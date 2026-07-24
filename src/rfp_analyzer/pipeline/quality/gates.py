"""Per-page quality metrics and status classification (RESEARCH Pattern 5).

Every threshold here is a named module-level constant with a
:class:`QualityThresholds` override path, so corpus calibration (assumption
A1: initial values are explicitly corpus-tunable) never touches logic.

D-03: pages that classify as anything other than ``"ok"`` are flagged and
surfaced — the quality stage (``headers.apply_quality``) empties their text
so garbage never flows downstream. No text-recovery fallback runs in Phase 1
(D-04: deferred).

DoS posture (T-01-10): all metrics are single-pass O(n) string scans —
no regex, no backtracking; page text is already bounded upstream by the
discovery stage's file-size cap.
"""

from dataclasses import dataclass
from typing import Literal

from rfp_analyzer.pipeline.models import PageInfo

PageStatus = Literal["ok", "scanned", "empty", "low_text", "gibberish"]

SCANNED_MAX_CHARS = 20
"""Below this char_count a page has effectively no text layer: with images
it is a scanned image-only page, without images it is empty (A1)."""

LOW_TEXT_CHARS = 150
"""A page with images and fewer chars than this is a partial scan or a
stamped/signature page — too little text to trust (A1)."""

GIBBERISH_ALPHA_RATIO = 0.5
"""Minimum alphabetic share of non-space chars; below it the text layer is
symbol soup from a broken font encoding (A1)."""

GIBBERISH_CID_RATIO = 0.02
"""Max ``(cid:`` markers per char: pdfminer emits ``(cid:NNN)`` for glyphs
with no Unicode mapping — a classic garbage-text signal (A1)."""

GIBBERISH_REPLACEMENT_MAX = 5
"""Max U+FFFD replacement chars before the page counts as gibberish (A1)."""


@dataclass(frozen=True)
class QualityThresholds:
    """Injectable knob bundle for corpus tuning (defaults per A1)."""

    scanned_max_chars: int = SCANNED_MAX_CHARS
    low_text_chars: int = LOW_TEXT_CHARS
    gibberish_alpha_ratio: float = GIBBERISH_ALPHA_RATIO
    gibberish_cid_ratio: float = GIBBERISH_CID_RATIO
    gibberish_replacement_max: int = GIBBERISH_REPLACEMENT_MAX


DEFAULT_THRESHOLDS = QualityThresholds()
"""Resolved at call time by :func:`classify_page` (not bound at import), so
tests and tuning runs can swap it without reloading the module."""


def compute_page_metrics(text: str) -> dict[str, float]:
    """Single-pass quality metrics for one page's raw text.

    Returns ``alpha_ratio`` (alphabetic / non-space chars; 0.0 when the
    denominator is 0 — an empty page is not an error), ``printable_ratio``
    (printable-or-whitespace / total chars), ``cid_count`` and
    ``replacement_char_count``.
    """
    non_space = 0
    alpha = 0
    printable = 0
    for ch in text:
        if not ch.isspace():
            non_space += 1
            if ch.isalpha():
                alpha += 1
        if ch.isprintable() or ch.isspace():
            printable += 1
    return {
        "alpha_ratio": alpha / non_space if non_space else 0.0,
        "printable_ratio": printable / len(text) if text else 0.0,
        "cid_count": float(text.count("(cid:")),
        "replacement_char_count": float(text.count("�")),
    }


def classify_page(page: PageInfo, thresholds: QualityThresholds | None = None) -> PageStatus:
    """Classify one PDF page per RESEARCH Pattern 5 status rules.

    Order matters: the scanned/empty/low_text checks use ``char_count`` from
    parse time (pdfplumber's glyph count), before any text rewriting; the
    gibberish checks use text-derived ratios. Metrics computed here are
    merged into ``page.metrics`` (parse-time keys win — reuse, don't
    recompute) so the document map carries them for reporting.
    """
    t = thresholds if thresholds is not None else DEFAULT_THRESHOLDS
    computed = compute_page_metrics(page.text)
    # Parse-time metrics (cid_count, replacement_char_count, has_images)
    # take precedence over recomputed values.
    page.metrics = {**computed, **page.metrics}

    has_images = page.metrics.get("has_images", 0.0) > 0.0
    if page.char_count < t.scanned_max_chars:
        return "scanned" if has_images else "empty"
    if has_images and page.char_count < t.low_text_chars:
        return "low_text"

    alpha_ratio = page.metrics["alpha_ratio"]
    cid_count = page.metrics.get("cid_count", 0.0)
    replacement_count = page.metrics.get("replacement_char_count", 0.0)
    if alpha_ratio < t.gibberish_alpha_ratio:
        return "gibberish"
    if cid_count / max(page.char_count, 1) > t.gibberish_cid_ratio:
        return "gibberish"
    if replacement_count > t.gibberish_replacement_max:
        return "gibberish"
    return "ok"
