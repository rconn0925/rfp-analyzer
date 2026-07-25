"""Accuracy scoring: how well an extraction run matches known ground truth.

Library code, not test-only, because the CLI reports precision and recall on
every extraction run that has a golden set to score against (success criterion
5) — the numbers are a product surface, not just a CI gate.
"""

from rfp_analyzer.eval.scoring import (
    MATCH_THRESHOLD,
    format_score_line,
    is_match,
    score,
)

__all__ = ["MATCH_THRESHOLD", "format_score_line", "is_match", "score"]
