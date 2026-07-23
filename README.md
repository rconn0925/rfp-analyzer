# RFP Analyzer

Federal RFP compliance-matrix generator: ingest a federal government
RFP/solicitation package (PDF/DOCX — base solicitation, SF30 amendments,
attachments) and produce a fully populated compliance matrix — every
requirement extracted with section references, cross-mapped across Sections
L, M, and C/SOW/PWS, and judged against a company capabilities profile.

**Phase 1 (current):** a pure Python parsing and structure library + CLI
that turns a package directory into a versioned JSON document map — per-file
identity, UCF section hierarchy with page ranges, per-page quality gates,
and amendment identification. No LLM calls in this phase.

## Stack

- Python 3.12, managed with [uv](https://docs.astral.sh/uv/)
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF text/layout extraction (MIT)
- [python-docx](https://python-docx.readthedocs.io/) — DOCX parsing
- [Pydantic](https://docs.pydantic.dev/) v2 — versioned document-map schema
- ruff (lint + format), pytest (tests), GitHub Actions (CI)

## Development

```bash
uv sync --locked --dev
uv run pytest tests/unit
uv run ruff check .
```

## Security

Secrets are provided via environment variables only — never committed to
this repository.

**Status: Phase 1 in progress**
