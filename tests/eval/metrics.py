"""Precision / recall / F1 of an extraction run against the golden set.

The objective accuracy signal for the phase (success criterion 5). The matching
rule is the one the golden set itself declares in its ``match_rule`` block, so
ground truth and scorer cannot drift apart:

    a predicted requirement matches a golden entry iff
      same file_id AND same page AND
      token_set_ratio(normalize(pred.verbatim), normalize(gold.verbatim)) >= 90

Three deliberate properties:

- **Precision and recall are separate fields, never collapsed into F1.** A run
  that hallucinates 50 extra requirements and one that misses 50 real ones can
  share an F1; only the split pair says which failure happened (threat T-02-17).
- **The page gate is real.** Text that matches on the wrong page is NOT a match.
  Grounding is the product's core claim, so a right-quote/wrong-page row is a
  defect, and the score must say so.
- **Ungrounded predictions cannot match anything** (their page is ``None``), so
  they count against precision. That is intended: an unverified row is not a
  deliverable requirement, and hiding it would flatter the score.

Pure stdlib + rapidfuzz over in-memory rows — no corpus, no engine, no network.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rapidfuzz import fuzz

from rfp_analyzer.pipeline.grounding.normalize import normalize

MATCH_THRESHOLD = 90.0
"""Fuzzy-overlap floor for a verbatim match, on rapidfuzz's 0-100 scale.

Mirrors ``golden_set.json``'s declared ``match_rule.threshold``. An eval knob
(RESEARCH assumption A2): raising it makes matching stricter (recall falls,
reported precision on true matches rises). Change it here and re-record EVAL.md —
never tune it to make a number look better.
"""


def _fields(item: Any) -> tuple[str | None, int | None, str]:
    """Return ``(file_id, page, verbatim_text)`` for a golden dict or a Requirement.

    Golden entries are plain dicts loaded from JSON; predictions are
    :class:`~rfp_analyzer.pipeline.models.Requirement` objects carrying their
    provenance on a nested ``source_ref``. Normalizing both to one tuple keeps
    the matching rule written exactly once.
    """
    if isinstance(item, dict):
        return item.get("file_id"), item.get("page"), item.get("verbatim_text") or ""
    ref = getattr(item, "source_ref", None)
    file_id = getattr(ref, "file_id", None)
    page = getattr(ref, "page", None)
    return file_id, page, getattr(item, "verbatim_text", "") or ""


def similarity(pred: Any, gold: Any) -> float:
    """Normalized fuzzy overlap (0-100) of two rows' verbatim text, ignoring location."""
    _pf, _pp, pred_text = _fields(pred)
    _gf, _gp, gold_text = _fields(gold)
    return fuzz.token_set_ratio(normalize(pred_text), normalize(gold_text))


def is_match(pred: Any, gold: Any, thresh: float = MATCH_THRESHOLD) -> bool:
    """True iff ``pred`` and ``gold`` share file_id and page AND overlap >= ``thresh``.

    A ``None`` page on either side never matches: an ungrounded prediction has no
    verified location, and a golden entry without a page is not usable ground
    truth. Location is checked before the (more expensive) fuzzy compare.
    """
    pred_file, pred_page, _ = _fields(pred)
    gold_file, gold_page, _ = _fields(gold)
    if pred_page is None or gold_page is None:
        return False
    if pred_file != gold_file or pred_page != gold_page:
        return False
    return similarity(pred, gold) >= thresh


def score(
    preds: Sequence[Any] | Iterable[Any],
    golds: Sequence[Any] | Iterable[Any],
    thresh: float = MATCH_THRESHOLD,
) -> dict[str, Any]:
    """Score predictions against ground truth; returns precision, recall, and F1.

    Matching is one-to-one and greedy by descending similarity: every candidate
    pair that clears the location gate and the threshold is ranked, then assigned
    best-first, so neither a prediction nor a golden entry is ever counted twice.
    (A naive first-fit loop lets one sloppy prediction consume a golden entry that
    a better prediction would have matched, understating both metrics.)

    Returned keys: ``precision``, ``recall``, ``f1``, ``matched``, ``total_preds``,
    ``total_golds``, ``unmatched_golds`` (the misses, for gap analysis) and
    ``unmatched_preds``. Empty inputs yield 0.0 metrics, never ZeroDivisionError.
    """
    preds = list(preds)
    golds = list(golds)

    candidates: list[tuple[float, int, int]] = []
    for pi, pred in enumerate(preds):
        for gi, gold in enumerate(golds):
            if is_match(pred, gold, thresh):
                candidates.append((similarity(pred, gold), pi, gi))
    # Best overlap first; ties broken by index so the assignment is deterministic.
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))

    taken_preds: set[int] = set()
    taken_golds: set[int] = set()
    for _sim, pi, gi in candidates:
        if pi in taken_preds or gi in taken_golds:
            continue
        taken_preds.add(pi)
        taken_golds.add(gi)

    matched = len(taken_golds)
    precision = matched / len(preds) if preds else 0.0
    recall = matched / len(golds) if golds else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": matched,
        "total_preds": len(preds),
        "total_golds": len(golds),
        "unmatched_golds": [g for i, g in enumerate(golds) if i not in taken_golds],
        "unmatched_preds": [p for i, p in enumerate(preds) if i not in taken_preds],
    }


def format_score_line(result: dict[str, Any]) -> str:
    """One-line human summary with precision and recall stated SEPARATELY.

    The exact string the CLI report prints, kept here so the report and the eval
    can never disagree about what a number means.
    """
    return (
        f"vs golden set: precision={result['precision']:.3f}, "
        f"recall={result['recall']:.3f}, F1={result['f1']:.3f} "
        f"({result['matched']}/{result['total_golds']} golden matched, "
        f"{result['total_preds']} predicted)"
    )
