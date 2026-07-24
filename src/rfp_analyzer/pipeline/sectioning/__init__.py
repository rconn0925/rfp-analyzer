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
from rfp_analyzer.pipeline.sectioning.tree import (
    TOC_MIN_DISTINCT_HEADINGS,
    build_section_tree,
    find_toc_pages,
)

__all__ = [
    "PARA_NUMBER",
    "PART_HEADING",
    "ROLE_TITLES",
    "SECTION_HEADING",
    "TOC_MIN_DISTINCT_HEADINGS",
    "HeadingCandidate",
    "build_section_tree",
    "find_heading_candidates",
    "find_toc_pages",
    "match_role_title",
    "normalize_line",
]
