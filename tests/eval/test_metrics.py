"""The scorer's own correctness — the eval that guards the eval.

If ``score`` is wrong, every accuracy number this phase reports is wrong, so the
matching rule's edge cases are pinned here with tiny synthetic rows. No corpus,
no engine: runs everywhere including CI.
"""

from __future__ import annotations

import pytest

from tests.eval.conftest import load_golden, load_golden_doc
from tests.eval.metrics import MATCH_THRESHOLD, format_score_line, is_match, score


def gold(text: str, page: int = 1, file_id: str = "f1") -> dict:
    return {"file_id": file_id, "page": page, "verbatim_text": text}


class _Ref:
    def __init__(self, file_id, page):
        self.file_id = file_id
        self.page = page


class _Pred:
    """Minimal stand-in for a Requirement (nested source_ref provenance)."""

    def __init__(self, text: str, page: int | None = 1, file_id: str = "f1"):
        self.verbatim_text = text
        self.source_ref = _Ref(file_id, page)


SENTENCE = "The offeror shall submit a technical proposal not exceeding 30 pages."


def test_identical_text_same_page_matches():
    assert is_match(_Pred(SENTENCE), gold(SENTENCE))


def test_same_text_different_page_does_not_match():
    """The page gate is the point: a right quote on the wrong page is a defect."""
    assert not is_match(_Pred(SENTENCE, page=2), gold(SENTENCE, page=1))


def test_same_text_different_file_does_not_match():
    assert not is_match(_Pred(SENTENCE, file_id="other"), gold(SENTENCE, file_id="f1"))


def test_ungrounded_prediction_never_matches():
    """page=None (grounding failed) is not a deliverable requirement."""
    assert not is_match(_Pred(SENTENCE, page=None), gold(SENTENCE))


def test_unrelated_text_same_page_does_not_match():
    assert not is_match(_Pred("Invoices are payable in 30 days."), gold(SENTENCE))


def test_normalization_absorbs_hyphenation_and_whitespace():
    """Grounding-identical normalization, so a PDF line-break quote still matches."""
    wrapped = "The offeror shall submit a technical  pro-\nposal not exceeding 30 pages."
    assert is_match(_Pred(wrapped), gold(SENTENCE))


def test_precision_and_recall_are_separate_fields():
    result = score([_Pred(SENTENCE)], [gold(SENTENCE)])
    assert "precision" in result and "recall" in result and "f1" in result
    assert result["precision"] == pytest.approx(1.0)
    assert result["recall"] == pytest.approx(1.0)


def test_recall_and_precision_diverge_and_are_reported_distinctly():
    """One correct hit, one hallucination, one miss -> P=0.5, R=0.5 ... but the
    point is that a lopsided run reports lopsided numbers, not one blended score."""
    preds = [_Pred(SENTENCE), _Pred("Wholly invented obligation.", page=9)]
    golds = [gold(SENTENCE), gold("A second real obligation.", page=3)]
    result = score(preds, golds)
    assert result["matched"] == 1
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)

    # Now make it lopsided: many hallucinations, perfect recall.
    preds = [_Pred(SENTENCE)] + [_Pred(f"Invented {i}.", page=50 + i) for i in range(9)]
    result = score(preds, [gold(SENTENCE)])
    assert result["recall"] == pytest.approx(1.0)
    assert result["precision"] == pytest.approx(0.1)
    assert result["precision"] != result["recall"], "collapsing these hides the failure"


def test_each_gold_matched_at_most_once():
    """Two near-identical predictions must not both claim the same golden row."""
    preds = [_Pred(SENTENCE), _Pred(SENTENCE)]
    result = score(preds, [gold(SENTENCE)])
    assert result["matched"] == 1
    assert result["recall"] == pytest.approx(1.0)
    assert result["precision"] == pytest.approx(0.5)


def test_each_pred_matched_at_most_once():
    """One prediction cannot satisfy two distinct golden rows on the same page."""
    golds = [gold(SENTENCE), gold(SENTENCE)]
    result = score([_Pred(SENTENCE)], golds)
    assert result["matched"] == 1
    assert result["recall"] == pytest.approx(0.5)


def test_overbroad_quote_still_matches_documenting_token_set_leniency():
    """KNOWN LENIENCY of the declared match rule (golden_set.json match_rule).

    ``token_set_ratio`` compares token SETS, so a prediction whose text is a
    superset of the golden span scores 100 — quoting a whole paragraph that
    merely CONTAINS the required sentence matches as well as an exact quote.

    This is the rule 02-04 locked in and the golden set is built against it, so
    the scorer honors it rather than silently tightening. The consequence is real
    and belongs in EVAL.md: reported precision does not penalize over-broad
    verbatim spans, so a high score is not by itself evidence that spans are
    tight. ``verbatim_contract`` (exact locatable span) is what constrains that,
    enforced separately by test_golden_verbatim.py.
    """
    overbroad = _Pred(SENTENCE + " Additional unrelated trailing clause here.")
    assert is_match(overbroad, gold(SENTENCE)), "token_set_ratio is superset-tolerant"


def test_assignment_is_deterministic_under_ties():
    """Equally-scoring predictions must resolve the same way on every run, so a
    re-scored artifact never drifts."""
    exact = _Pred(SENTENCE)
    overbroad = _Pred(SENTENCE + " Additional unrelated trailing clause here.")
    first = score([overbroad, exact], [gold(SENTENCE)])
    second = score([overbroad, exact], [gold(SENTENCE)])
    assert first["matched"] == second["matched"] == 1
    assert first["unmatched_preds"] == second["unmatched_preds"]


def test_empty_predictions_yield_zero_without_error():
    result = score([], [gold(SENTENCE)])
    assert result["recall"] == 0.0
    assert result["precision"] == 0.0
    assert result["f1"] == 0.0


def test_empty_golds_yield_zero_without_error():
    assert score([_Pred(SENTENCE)], [])["recall"] == 0.0


def test_both_empty_yields_zero_without_error():
    assert score([], [])["f1"] == 0.0


def test_unmatched_golds_are_returned_for_gap_analysis():
    missed = gold("A second real obligation.", page=3)
    result = score([_Pred(SENTENCE)], [gold(SENTENCE), missed])
    assert result["unmatched_golds"] == [missed]


def test_format_score_line_states_precision_and_recall_separately():
    line = format_score_line(score([_Pred(SENTENCE)], [gold(SENTENCE)]))
    assert "precision=" in line and "recall=" in line and "F1=" in line


def test_threshold_matches_the_golden_sets_declared_rule():
    """Scorer and ground truth must not drift apart on the matching rule."""
    declared = load_golden_doc()["match_rule"]["threshold"]
    assert declared == MATCH_THRESHOLD


def test_golden_rows_score_perfectly_against_themselves():
    """Sanity floor: ground truth scored against itself is P=R=1.0. If this fails,
    the scorer disagrees with the golden set's own shape."""
    golds = load_golden()
    preds = [_Pred(g["verbatim_text"], g["page"], g["file_id"]) for g in golds]
    result = score(preds, golds)
    assert result["recall"] == pytest.approx(1.0)
    assert result["precision"] == pytest.approx(1.0)
