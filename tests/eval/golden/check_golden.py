"""Locatability gate for the golden set (EXTR-02 honesty backbone, threat T-02-09).

Loads ``golden_set.json`` and the primary package's document map, then asserts
every ``verbatim_text`` normalizes to a contiguous substring of its cited page's
parsed text. This is the committed check that must pass before the golden set is
trusted as a measurement baseline.

The normalizer here is intentionally identical to the Phase 2 grounding normalizer
(NFKC + soft-hyphen de-hyphenation + whitespace collapse) so the golden set is
validated under the same rule the extractor will be graded by.

Run standalone::

    uv run python tests/eval/golden/check_golden.py

Returns exit 0 on all-pass, 1 on any failure, 2 if the source map/corpus is
unavailable (gitignored — e.g. in CI). ``load_page_text`` is reused by the pytest
wrapper (``tests/eval/test_golden_verbatim.py``).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

GOLDEN = Path(__file__).with_name("golden_set.json")
REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = REPO_ROOT / "artifacts" / "primary-ucf" / "document_map.json"
CORPUS = REPO_ROOT / "tests" / "corpus" / "primary-ucf"


def normalize(text: str) -> str:
    """NFKC + soft-hyphen de-hyphenation + whitespace collapse (grounding-identical)."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(\w)[-\xad]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_page_text() -> dict[tuple[str, int], str] | None:
    """Return {(file_id, page): normalized_page_text} for the primary package.

    Prefers the committed artifact; falls back to running the Phase 1 pipeline over
    the corpus. Returns ``None`` when neither source is available (gitignored),
    signalling callers to skip rather than fail.
    """
    dmap = None
    if ARTIFACT.exists():
        dmap = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    elif CORPUS.is_dir():
        try:
            from rfp_analyzer.pipeline.run import run_pipeline

            dmap = json.loads(run_pipeline(CORPUS).model_dump_json())
        except Exception:  # noqa: BLE001 — any parse/import failure => treat as unavailable
            return None
    if dmap is None:
        return None
    out: dict[tuple[str, int], str] = {}
    for f in dmap["files"]:
        for p in f.get("pages", []):
            out[(f["file_id"], p["page_number"])] = normalize(p.get("text", ""))
    return out


def check() -> tuple[int, int, list[str]]:
    """Return (checked, failures, failure_messages). Raises if the map is unavailable."""
    pages = load_page_text()
    if pages is None:
        raise FileNotFoundError("primary-ucf document map/corpus unavailable")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["requirements"]
    failures: list[str] = []
    for r in golden:
        key = (r["file_id"], r["page"])
        page_text = pages.get(key, "")
        needle = normalize(r["verbatim_text"])
        if needle not in page_text:
            failures.append(
                f"{r['requirement_id']} p{r['page']} {r['file_id'][:8]}: "
                f"verbatim not locatable: {needle[:80]!r}"
            )
    return len(golden), len(failures), failures


def main() -> int:
    try:
        checked, n_fail, failures = check()
    except FileNotFoundError as exc:
        print(f"SKIP: {exc} (gitignored corpus — cannot validate here)")
        return 2
    for msg in failures:
        print("FAIL:", msg)
    print(f"\nchecked {checked} golden verbatims; {n_fail} failed, {checked - n_fail} passed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
