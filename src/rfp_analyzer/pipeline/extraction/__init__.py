"""Extraction stage: turn a Phase 1 ``DocumentMap`` into grounded Requirements.

The engine is Claude Code on Ross's subscription, reached through a file-mediated
replay seam rather than an in-process call — see ``replay.py`` for why.

Modules:

- ``chunker.py`` — pure transformation over the map: walks every file and
  section, concatenates ok-quality page text, and records a ``page_map`` linking
  char ranges back to source page numbers so grounding can compute a verified
  page reference. Also owns ``chunk_key``, the identity that joins an exported
  chunk to its recorded drafts.
- ``prompt.py`` — the verbatim-fidelity + atomic-split system prompt.
- ``replay.py`` — the engine seam: loads drafts recorded by Claude Code and
  replays them through the ``ExtractFn`` injection point, counting any chunk the
  recording did not cover.
- ``extract.py`` — orchestration: chunk -> drafts -> grounded, atomic,
  stably-identified, typed Requirements.

This stage makes NO network calls at all: no model runtime, no API. Every module
here is pure Python over local files, which is what lets the whole extraction
path run in CI from a committed artifact.
"""
