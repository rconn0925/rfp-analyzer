"""Quality stage: per-page gates and header/footer stripping (plan 01-04)."""

from rfp_analyzer.pipeline.quality.gates import (
    DEFAULT_THRESHOLDS,
    QualityThresholds,
    classify_page,
    compute_page_metrics,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "QualityThresholds",
    "classify_page",
    "compute_page_metrics",
]
