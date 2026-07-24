# RFP Analyzer

Federal RFP compliance-matrix generator: ingest a federal government
RFP/solicitation package (PDF/DOCX — base solicitation, SF30 amendments,
attachments) and produce a fully populated compliance matrix — every
requirement extracted with section references, cross-mapped across Sections
L, M, and C/SOW/PWS, and judged against a company capabilities profile.

**Phase 1 (complete):** a pure Python parsing and structure library + CLI
that turns a package directory into a versioned JSON document map — per-file
identity, UCF section hierarchy with page ranges, per-page quality gates,
and amendment identification. No LLM calls in this phase.

## Usage

```bash
# Install (Python 3.12+, uv)
uv sync

# Parse a package directory of RFP files (PDF/DOCX)
uv run rfp-analyzer parse <package-dir> --out <artifacts-dir>
```

Every run emits two artifacts:

1. **`<artifacts-dir>/<package-name>/document_map.json`** — the canonical,
   versioned document map (Pydantic schema): per-file identity (sha256),
   parse status, doc role (base solicitation / SF30 amendment / attachment),
   per-page text with quality status, and the detected UCF section hierarchy
   with page (PDF) or block (DOCX) locators. This is the contract downstream
   extraction consumes.
2. **A human-readable report to stdout** — package classification
   (`full_ucf` / `partial_ucf` / `non_ucf_commercial` / `unknown`) with
   evidence, the section tree with page ranges, quality flags as contiguous
   range notes (e.g. `pages 2-3: scanned image, no text layer`), warnings,
   and a metrics footer (stage timings, `LLM cost: $0.00 (0 calls)` in
   Phase 1).

Exit codes: `0` success; `1` honest failure (classification `unknown` with
zero sections detected); `2` usage errors.

## Architecture

`src/rfp_analyzer/pipeline/` is a pure library — no CLI, HTTP, or queue
imports. Stages compose as `f(artifact) -> artifact`:

```
discover -> parse (pdf/docx) -> quality gates -> sectioning -> classify
```

The CLI (`src/rfp_analyzer/cli.py`) wraps `pipeline.run.run_pipeline` and
owns all presentation; the only allowed import direction is CLI -> pipeline.
`document_map.json` (schema in `pipeline/models.py`, versioned via
`schema_version`) is the sole contract later phases consume.

## Test Corpus

Integration tests run against three real federal solicitation packages
downloaded from SAM.gov. The binaries are gitignored (large public
documents); `tests/corpus/MANIFEST.md` documents each package with notice
URLs and sha256 checksums for reconstruction. Without the corpus present,
`tests/integration` auto-skips — CI stays green on manifests alone.

## Stack

- Python 3.12, managed with [uv](https://docs.astral.sh/uv/)
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF text/layout extraction (MIT)
- [python-docx](https://python-docx.readthedocs.io/) — DOCX parsing
- [Pydantic](https://docs.pydantic.dev/) v2 — versioned document-map schema
- ruff (lint + format), pytest (tests), GitHub Actions (CI)

## Development

```bash
uv sync --locked --dev
uv run pytest tests/unit tests/integration
uv run ruff check .
```

## Security

Secrets are provided via environment variables only — never committed to
this repository.

**Status: Phase 1 complete — parsing & structure foundation**
