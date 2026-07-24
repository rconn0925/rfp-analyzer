"""The single canonical text normalizer shared by grounding, ids, and sweep.

Federal PDFs wrap words with hyphens ("require-\\nments"), carry ligature glyphs
("ﬁ"), and vary whitespace; a model quote normalizes those away. Applying the
same fold to both a quote and its page text is what lets them compare equal
(Pitfall 5). Do not fork variants — every module that compares or hashes text
imports this one function so the canonical form is identical everywhere.
"""

import re
import unicodedata

_DEHYPHENATE = re.compile(r"(\w)[-\xad]\s*\n\s*(\w)")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Fold text to its canonical comparison form.

    NFKC (folds ligatures/width variants), then heal soft line-break hyphens
    (plain ``-`` and U+00AD), then collapse all whitespace runs to a single
    space and strip. Idempotent: ``normalize(normalize(x)) == normalize(x)``.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _DEHYPHENATE.sub(r"\1\2", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()
