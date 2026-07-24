"""Extraction stage: turn a Phase 1 ``DocumentMap`` into grounded Requirements.

Modules:

- ``chunker.py`` — pure transformation over the map: walks every file and
  section, concatenates ok-quality page text, and records a ``page_map`` linking
  char ranges back to source page numbers so grounding can compute a verified
  page reference.
- ``prompt.py`` — the verbatim-fidelity + atomic-split system prompt.
- ``client.py`` — the ONLY network-touching module: the native Ollama call with
  the enforced ``num_ctx`` guard and grammar-constrained JSON output.
- ``extract.py`` — orchestration: chunk -> model -> grounded, atomic,
  stably-identified, typed Requirements.

Apart from ``client.py``'s localhost HTTP to the Ollama runtime (a library
making a network call, like a DB driver), no network, CLI, or queue imports live
in this stage.
"""
