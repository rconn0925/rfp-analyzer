"""Shared eval fixtures: the golden set and the recorded Claude extraction.

Loaders live here (not inside a test) so the CLI report path, the metrics tests,
and any future eval can all read the same artifacts the same way.
"""

from __future__ import annotations

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent
GOLDEN_PATH = EVAL_DIR / "golden" / "golden_set.json"
DRAFTS_PATH = EVAL_DIR / "fixtures" / "golden_drafts.jsonl"


def load_golden(path: Path | str = GOLDEN_PATH) -> list[dict]:
    """Return the golden set's requirement rows (the ``requirements`` array)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc["requirements"]


def load_golden_doc(path: Path | str = GOLDEN_PATH) -> dict:
    """Return the whole golden document, including ``match_rule`` and ``counts``."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
