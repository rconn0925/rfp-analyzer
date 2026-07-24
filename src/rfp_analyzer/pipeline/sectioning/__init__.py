"""Sectioning stage: UCF heading detection and section tree building (plan 01-05)."""

from rfp_analyzer.pipeline.sectioning.headings import (
    PARA_NUMBER,
    PART_HEADING,
    ROLE_TITLES,
    SECTION_HEADING,
    HeadingCandidate,
    find_heading_candidates,
    match_role_title,
    normalize_line,
)

__all__ = [
    "PARA_NUMBER",
    "PART_HEADING",
    "ROLE_TITLES",
    "SECTION_HEADING",
    "HeadingCandidate",
    "find_heading_candidates",
    "match_role_title",
    "normalize_line",
]
