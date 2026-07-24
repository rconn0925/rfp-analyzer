"""Extraction stage: turn a Phase 1 ``DocumentMap`` into model-sized chunks.

The chunker (``chunker.py``) is pure transformation over the map — it walks
every file and section, concatenates ok-quality page text, and records a
``page_map`` linking char ranges back to source page numbers so downstream
grounding can compute a verified page reference. No network, CLI, or queue
imports live here; the only network-touching module in this stage (the Ollama
client) is added by a separate plan.
"""
