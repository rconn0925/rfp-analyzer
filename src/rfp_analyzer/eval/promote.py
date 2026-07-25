"""Promote audited predictions into the golden set, correctly.

Extending the exhaustive scope means auditing every prediction in a page range
and adding the genuine requirements to ground truth. Doing that by hand went
wrong twice, in ways that both quietly *deflated* precision and were only caught
by checking whether the reported errors were the ones actually rejected:

1. **Deduplicating by verbatim dropped atomic siblings.** When a compound
   sentence is correctly split into three single-duty rows, ground truth held one.
   The one-to-one match rule then scored two correct rows as false positives.
   :func:`promote` keeps every prediction as its own golden row.

2. **Scoped matching hid whole pages.** ``score(..., scoped=True)`` restricts
   predictions to the footprint of the golden rows passed in — so pages inside the
   declared range that had no golden row yet were never offered for audit, and
   then reappeared as unmatched. :func:`promote` always scores ``scoped=False``
   over the full declared range.

A third failure has no code fix and is guarded instead: a page with no golden rows
AND no predictions is indistinguishable from an empty page. Page 62 of this
corpus hid that way — 3,804 characters of real content, invisible on both sides of
the ratio, inflating recall. :func:`unverified_pages` reports any declared page
with no evidence either way so a caller cannot claim exhaustiveness over a page
nobody read.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from rfp_analyzer.eval.scoring import score

_KEYWORDS = {"shall", "must", "will", "should", "shall not", "none"}


def _page_of(pred: Any) -> tuple[str | None, int | None]:
    ref = getattr(pred, "source_ref", None)
    return getattr(ref, "file_id", None), getattr(ref, "page", None)


def golden_row(pred: Any, section: str, req_type: str) -> dict:
    """Build one golden row from a prediction.

    Keyed on verbatim AND atomic obligation so atomic siblings — which share a
    verbatim but state different duties — get distinct ids instead of colliding.
    """
    ref = pred.source_ref
    key = hashlib.sha256(
        (pred.verbatim_text + "|" + pred.atomic_obligation).encode("utf-8")
    ).hexdigest()[:10]
    keyword = pred.binding_keyword if pred.binding_keyword in _KEYWORDS else "none"
    return {
        "requirement_id": f"GOLD-{key}",
        "section": section,
        "file_id": ref.file_id,
        "filename": ref.filename,
        "page": ref.page,
        "verbatim_text": pred.verbatim_text,
        "atomic_obligation": pred.atomic_obligation,
        "binding_keyword": keyword,
        "req_type": req_type,
        "parent_id": None,
        "provenance_pass": "C",
    }


def promote(
    predictions: Sequence[Any] | Iterable[Any],
    existing_golden: Sequence[dict],
    file_id: str,
    pages: Iterable[int],
    section: str,
    req_type: str,
    is_requirement: Callable[[Any], bool],
) -> tuple[list[dict], list[Any]]:
    """Return ``(new_golden_rows, rejected_predictions)`` for one page range.

    ``is_requirement`` is the audit: it decides, per prediction, whether the row
    is a genuine obligation. Everything it rejects is returned rather than
    discarded, so the false-positive count is auditable and can be written up.
    """
    pages = set(pages)
    golds_in = [
        g for g in existing_golden if g.get("file_id") == file_id and g.get("page") in pages
    ]
    preds_in = [p for p in predictions if _page_of(p) == (file_id, None) or (
        _page_of(p)[0] == file_id and _page_of(p)[1] in pages
    )]

    # scoped=False is load-bearing: see bug 2 in the module docstring.
    result = score(preds_in, golds_in, scoped=False)

    promoted: list[dict] = []
    rejected: list[Any] = []
    for pred in result["unmatched_preds"]:  # siblings included: see bug 1
        if is_requirement(pred):
            promoted.append(golden_row(pred, section, req_type))
        else:
            rejected.append(pred)
    return promoted, rejected


def unverified_pages(
    golden_doc: dict, predictions: Sequence[Any] | Iterable[Any]
) -> list[tuple[str, int]]:
    """Declared-exhaustive pages with neither a golden row nor a prediction.

    Such a page is unverified, not empty — nobody has demonstrated it holds no
    requirements. Claiming exhaustiveness over it silently inflates recall.
    """
    scope = golden_doc.get("exhaustive_scope") or {}
    declared: set[tuple[str, int]] = set()
    for entry in scope.get("ranges", []):
        for page in entry.get("pages", []):
            declared.add((entry.get("file_id"), page))
    if not declared:
        return []

    with_gold = {
        (g.get("file_id"), g.get("page")) for g in golden_doc.get("requirements", [])
    }
    with_pred = {_page_of(p) for p in predictions}
    return sorted(declared - with_gold - with_pred)
