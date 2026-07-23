# Phase 1: Parsing & Structure Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-22
**Phase:** 1-Parsing & Structure Foundation
**Areas discussed:** Test corpus, Scanned-page handling, CLI output format, Repo & scaffolding (all delegated to Claude)

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Test corpus | Which real federal RFP packages prove Phase 1 works? How many, sourced how, include hostile + non-UCF specimens? | ✓ (delegated) |
| Scanned-page handling | Flag-and-surface only for v1, or build OCR fallback now? | ✓ (delegated) |
| CLI output format | Machine JSON artifact, human-readable tree report, or both? | ✓ (delegated) |
| Repo & scaffolding | Public GitHub from day 1? CI with pytest from Phase 1? | ✓ (delegated) |

**User's choice:** "fable take the wheel, i trust your judgement on all of this."
**Notes:** User delegated all four gray areas to Claude's judgment. Decisions were made against the research corpus (.planning/research/) rather than discussed interactively.

---

## Claude's Discretion

All four areas resolved by Claude:
- **Test corpus:** 3-package minimum (clean UCF multi-file, scanned-hostile, non-UCF FAR Part 12), manually downloaded from SAM.gov website; files gitignored with committed MANIFEST.md
- **Scanned pages:** flag-and-surface only, no OCR in Phase 1; Docling deferred pending eval evidence
- **CLI output:** both — canonical Pydantic JSON document map + human-readable section tree to stdout
- **Repo:** public GitHub from day 1; uv + ruff + pytest + GitHub Actions CI from the start; cost instrumentation scaffolding included

Plus implementation-level discretion: section-detection heuristics, quality-gate thresholds, JSON schema details, CLI naming.

## Deferred Ideas

- OCR fallback via Docling — adopt only on eval evidence in a later phase
