"""Evaluation harness package: golden-set ground truth + recall/precision scoring.

The golden set (``golden/golden_set.json``) is the measurement baseline for the
Phase 2 requirement-extraction bake-off. It is committed as text; the source PDFs
it references live under ``tests/corpus/primary-ucf`` (gitignored), so any check
that needs page text skips gracefully when the corpus/artifact is absent (mirrors
the Phase 1 corpus-skip pattern; CI has no corpus and no Ollama).
"""
