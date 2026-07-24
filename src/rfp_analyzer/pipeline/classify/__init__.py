"""Classify stage: form signatures, doc roles, and package classification (plan 01-05)."""

from rfp_analyzer.pipeline.classify.forms import (
    AMENDMENT_FILENAME_RE,
    COMBINED_SYNOPSIS_MARKERS,
    FORM_SIGNATURES,
    FormMatch,
    assign_doc_role,
    detect_combined_synopsis,
    detect_form,
)
from rfp_analyzer.pipeline.classify.package import classify_package

__all__ = [
    "AMENDMENT_FILENAME_RE",
    "COMBINED_SYNOPSIS_MARKERS",
    "FORM_SIGNATURES",
    "FormMatch",
    "assign_doc_role",
    "classify_package",
    "detect_combined_synopsis",
    "detect_form",
]
