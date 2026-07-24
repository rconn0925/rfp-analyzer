"""Content-derived stable requirement IDs (Pattern 4).

Order-based counters are NOT stable — extraction order can shift between runs.
The stable key is a sha256 over ``file_id | normalize(verbatim) | occurrence |
atomic_ord``, so re-running assignment over identical inputs reproduces
identical ids. Keying off ``normalize(verbatim)`` (the same canonical form
grounding uses) means whitespace/ligature variants of one quote collapse to one
id. ``occurrence`` and ``atomic_ord`` keep repeated sentences and atomic
siblings distinct so no two real requirements collide.

Display labels (``display_label``) may renumber freely; ``requirement_id`` must
not — the hash is the machine key, the label is for humans/exports.
"""

import hashlib

from rfp_analyzer.pipeline.grounding.normalize import normalize


def requirement_id(file_id: str, verbatim: str, occurrence: int, atomic_ord: int) -> str:
    """Return a stable ``REQ-<10hex>`` id derived from content, not order.

    ``occurrence`` disambiguates identical sentences appearing more than once in
    one file; ``atomic_ord`` disambiguates atomic siblings sharing one verbatim
    span. Normalize-equivalent verbatims produce the same id.
    """
    norm = normalize(verbatim)
    key = f"{file_id}|{norm}|{occurrence}|{atomic_ord}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"REQ-{digest[:10]}"


def display_label(section_label: str, ordinal: int) -> str:
    """Return a human-readable label like ``"L-3"`` (renumberable, NOT the key).

    Use for the stdout report and Excel export; never persist as the stable
    identifier — that role belongs to :func:`requirement_id`.
    """
    return f"{section_label}-{ordinal}"
