"""Column-aware text extraction for tabular spec sheets.

The defect this fixes, found while building the golden set: federal SOW annexes
are laid out as a three-column spec table —

    | Spec Item | Title                | Description                        |
    | 2.3.4     | Permits and          | The Contractor shall obtain all    |
    |           | Licenses             | required permits ... under this    |

pdfplumber reads a page line by line, left to right, so a visual row whose title
column is still wrapping gets spliced into the middle of the description
sentence:

    "...authorizations to **Licenses** perform work under this contract..."
    "...at least 30 calendar days written **Insurance** notice to the KO..."

That is not a cosmetic problem. It corrupts ``verbatim_text`` in the exported
matrix (a proposal manager reads gibberish), and it fragments sentences so a
requirement often cannot be quoted as one contiguous grounded span at all —
silently costing recall.

The fix reads the columns as columns: detect the description column's left edge,
split each visual line at it, and accumulate the label side and the body side
separately within each spec-item row. Descriptions come out contiguous and the
title stops appearing mid-sentence.

Detection is conservative — a page with no strong, repeatedly-used column edge
falls straight through to normal extraction, so ordinary prose pages are
untouched.
"""

from __future__ import annotations

from collections import Counter
from itertools import groupby

MIN_BODY_EDGE_SHARE = 0.25
"""Fraction of text lines that must start at the same x for it to be a column edge.

A real table's description column starts at the same x on most of its lines. A
prose page has no such repetition, which is what keeps this from firing on
ordinary text.
"""

MIN_EDGE_OFFSET = 40.0
"""Minimum points between the page's left margin and a candidate column edge.

Guards against mistaking a paragraph indent for a column.
"""

MIN_LINES = 6
"""Below this, "most lines start at the same x" is noise, not evidence."""

X_ROUND = 1
"""Rounding (points) when clustering line-start positions."""


def _lines(words: list[dict]) -> list[list[dict]]:
    """Group words into visual lines, each sorted left to right."""
    ordered = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    return [
        sorted(group, key=lambda w: w["x0"])
        for _top, group in groupby(ordered, key=lambda w: round(w["top"]))
    ]


def detect_body_edge(words: list[dict]) -> float | None:
    """Return the description column's left edge, or ``None`` if not columnar.

    The edge is the most common line-start x that sits well right of the page's
    left margin and accounts for a meaningful share of lines.
    """
    lines = _lines(words)
    if len(lines) < MIN_LINES:
        return None

    starts = [round(line[0]["x0"], X_ROUND) for line in lines if line]
    if not starts:
        return None

    left_margin = min(starts)
    candidates = Counter(x for x in starts if x - left_margin >= MIN_EDGE_OFFSET)
    if not candidates:
        return None

    edge, count = candidates.most_common(1)[0]
    if count / len(starts) < MIN_BODY_EDGE_SHARE:
        return None
    return float(edge)


HEADER_BAND_FRACTION = 0.12
"""Top fraction of the page treated as running-header space.

Lines there are emitted verbatim as their own lines rather than folded into a
spec-item row. Without this the repeated "Spec Item | Title | Description"
column header swallows the description text continuing from the previous page,
and — worse — the header stops being a standalone line, so the frequency-based
running-header stripper can no longer recognise and remove it.
"""


def extract_columnar_text(
    words: list[dict],
    edge: float,
    tolerance: float = 2.0,
    header_band: float | None = None,
) -> str:
    """Rebuild page text as label-column then body-column, per spec-item row.

    A row begins at any line whose leftmost word sits at the page's left margin
    (the spec-item number). Within a row, every word left of ``edge`` joins the
    label stream and everything at or right of it joins the body stream, so a
    wrapping title accumulates alongside the description instead of inside it.

    Lines inside the top ``header_band`` are passed through untouched, keeping
    running headers isolated for the stripper that runs later.
    """
    lines = _lines(words)
    if not lines:
        return ""

    left_margin = min(line[0]["x0"] for line in lines)
    split = edge - tolerance

    out: list[str] = []
    rows: list[tuple[list[str], list[str]]] = []
    label: list[str] = []
    body: list[str] = []
    started = False

    def flush() -> None:
        if started:
            rows.append((label, body))

    for line in lines:
        if header_band is not None and line[0]["top"] < header_band:
            flush()
            rows.append(([w["text"] for w in line], []))
            label, body = [], []
            started = False
            continue
        starts_row = line[0]["x0"] <= left_margin + tolerance
        if starts_row and started:
            rows.append((label, body))
            label, body = [], []
        started = True
        for word in line:
            (body if word["x0"] >= split else label).append(word["text"])
    flush()

    for label_words, body_words in rows:
        parts = [" ".join(label_words).strip(), " ".join(body_words).strip()]
        text = " ".join(part for part in parts if part)
        if text:
            out.append(text)
    return "\n".join(out)


def extract_text_columnar_aware(page, fallback: str) -> tuple[str, bool]:
    """Return ``(text, used_columns)`` for a pdfplumber page.

    Falls back to ``fallback`` (normal ``extract_text`` output) whenever the page
    is not a recognisable column table, so this can be applied to every page
    without risk to ordinary prose.
    """
    try:
        words = page.extract_words(x_tolerance=3, y_tolerance=3)
    except Exception:  # pragma: no cover - defensive; a bad page must not crash parsing
        return fallback, False
    edge = detect_body_edge(words)
    if edge is None:
        return fallback, False
    header_band = float(page.height) * HEADER_BAND_FRACTION
    text = extract_columnar_text(words, edge, header_band=header_band)
    if not text.strip():
        return fallback, False
    return text, True
