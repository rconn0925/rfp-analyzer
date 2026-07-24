"""Behavior tests for the shared text normalizer (grounding + ids + sweep).

The single canonical normalizer: quotes and page text must compare equal after
NFKC folding, soft-line-break de-hyphenation, and whitespace collapse (Pitfall 5).
"""

from rfp_analyzer.pipeline.grounding.normalize import normalize


def test_de_hyphenates_soft_line_break():
    """A word wrapped with a hyphen + newline heals into one token."""
    assert normalize("require-\nments") == "requirements"


def test_de_hyphenates_soft_hyphen_variant():
    """The U+00AD soft hyphen at a line wrap heals the same as a plain hyphen."""
    assert normalize("require\xad\nments") == "requirements"


def test_folds_nfkc_ligature():
    """NFKC folds the fi ligature so it matches plain characters."""
    assert normalize("ﬁle") == "file"


def test_collapses_whitespace_runs_to_single_space():
    """Runs of spaces, tabs, and newlines collapse to one space; result stripped."""
    assert normalize("  The   offeror\tshall\n\nsubmit.  ") == "The offeror shall submit."


def test_idempotent():
    """normalize(normalize(x)) == normalize(x) for noisy input."""
    raw = "  The offeror shall sub-\nmit the ﬁnal\t\tvolume.  "
    once = normalize(raw)
    assert normalize(once) == once


def test_quote_matches_page_text_after_normalization():
    """A model quote and its wrapped/ligatured page text compare equal normalized."""
    quote = "shall submit the final file"
    page = "...shall submit the ﬁnal  fi-\nle..."
    assert normalize(quote) in normalize(page)
