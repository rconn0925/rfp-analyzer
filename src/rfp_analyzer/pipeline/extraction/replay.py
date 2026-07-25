"""The extraction engine seam: replay requirement drafts recorded by Claude Code.

**Why this is a file, not a function call.** The extraction brain is Claude Code
running on Ross's Claude subscription (CLAUDE.md stack decision, 2026-07-24). A
Pro/Max subscription cannot be authenticated against programmatically — there is
no in-process call to make — so the engine step is human-in-the-loop shaped:

    rfp-analyzer chunks <pkg> --out chunks.jsonl   # pure Python: what to read
    (Claude Code reads the chunks and writes drafts.jsonl)
    rfp-analyzer extract <pkg> --drafts drafts.jsonl  # pure Python: ground + score

That indirection buys a property a live model call never had: **an extraction run
becomes an artifact.** A committed drafts.jsonl replays to a byte-identical
RequirementSet on any machine, with no GPU, no API key, and no sampling variance
anywhere in the pipeline. The eval number in EVAL.md is therefore auditable — you
can re-derive it — rather than one sample of a stochastic process. This replaced
the seed-and-temperature determinism juggling the retired local-model path needed.

Nothing here talks to a network. The module that did (the retired local-model
client) is gone; :class:`ExtractionParseError` moved here because ``extract.py``'s
per-chunk isolation contract depends on it and must outlive any particular engine.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from rfp_analyzer.pipeline.extraction.chunker import chunk_key
from rfp_analyzer.pipeline.models import RequirementBatch


class ExtractionParseError(ValueError):
    """A chunk's drafts could not be produced as a valid ``RequirementBatch``.

    Raised per chunk so the orchestrator records the failure and continues — one
    bad chunk never crashes a whole run. (Moved verbatim from the retired
    local-model client; ``extract.extract_requirements`` catches exactly this type.)
    """


class MissingDraftsError(ExtractionParseError):
    """No recorded drafts exist for this chunk.

    A subclass so the established isolation path in ``extract_requirements``
    still catches it, while :class:`ReplayEngine` can count it separately. The
    distinction matters: a chunk nobody extracted is NOT the same as a chunk
    genuinely containing zero requirements, and silently conflating the two would
    read as "clean run, nothing found" while hiding a coverage hole (T-02-20).
    """


class CorruptDraftsError(ValueError):
    """The drafts file is malformed. Fails the whole run, deliberately.

    Unlike a missing chunk, a corrupt recording means the artifact cannot be
    trusted at all — silently dropping the unreadable lines would understate
    recall and look like a model failure instead of a file failure.
    """


def load_drafts(path: Path | str) -> dict[str, RequirementBatch]:
    """Load a JSONL drafts recording into ``{chunk_key: RequirementBatch}``.

    Each line: ``{"chunk_key": "CHK-...", "requirements": [RequirementDraft, ...]}``.
    A malformed line, a missing key, or drafts failing schema validation raise
    :class:`CorruptDraftsError` naming the 1-indexed line number — a bad
    recording must fail loudly, never quietly lose requirements.
    """
    path = Path(path)
    if not path.exists():
        raise CorruptDraftsError(f"drafts file not found: {path}")

    out: dict[str, RequirementBatch] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorruptDraftsError(f"{path}:{lineno}: not valid JSON: {exc}") from exc
        key = record.get("chunk_key")
        if not key:
            raise CorruptDraftsError(f"{path}:{lineno}: missing 'chunk_key'")
        try:
            batch = RequirementBatch.model_validate(
                {"requirements": record.get("requirements", [])}
            )
        except ValidationError as exc:
            raise CorruptDraftsError(
                f"{path}:{lineno}: drafts for {key} do not match RequirementBatch: {exc}"
            ) from exc
        if key in out:
            raise CorruptDraftsError(
                f"{path}:{lineno}: duplicate chunk_key {key} — one recording per chunk"
            )
        out[key] = batch
    if not out:
        raise CorruptDraftsError(f"{path}: no draft records found (empty recording)")
    return out


class ReplayEngine:
    """An :data:`~rfp_analyzer.pipeline.extraction.extract.ExtractFn` over recorded drafts.

    Callable as ``(chunk_text, model, seed) -> RequirementBatch``, matching the
    injection point 02-05 established, so the orchestrator is unchanged. ``model``
    and ``seed`` are accepted and ignored: a replay has no sampling to control —
    they survive only as run provenance on the RequirementSet.

    Tracks coverage as it goes: :attr:`resolved_keys` and :attr:`missing_count`
    let the caller report how much of the package was actually extracted.
    """

    def __init__(self, drafts: dict[str, RequirementBatch]):
        self._drafts = drafts
        self.resolved_keys: set[str] = set()
        self.missing_keys: list[str] = []

    def __call__(self, chunk_text: str, model: str = "", seed: int = 0) -> RequirementBatch:
        key = chunk_key(chunk_text)
        batch = self._drafts.get(key)
        if batch is None:
            self.missing_keys.append(key)
            raise MissingDraftsError(
                f"no recorded drafts for chunk {key} — re-run `rfp-analyzer chunks` "
                f"and extract the missing chunk, or the run under-reports coverage"
            )
        self.resolved_keys.add(key)
        return batch

    @property
    def missing_count(self) -> int:
        """Chunks the pipeline asked for that the recording did not contain."""
        return len(self.missing_keys)

    @property
    def unused_count(self) -> int:
        """Recorded chunks the pipeline never asked for (stale/extra recordings)."""
        return len(set(self._drafts) - self.resolved_keys)


def replay_extract_fn(drafts: dict[str, RequirementBatch]) -> ReplayEngine:
    """Return a :class:`ReplayEngine` over ``drafts`` (the ExtractFn to inject)."""
    return ReplayEngine(drafts)
