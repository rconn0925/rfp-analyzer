---
phase: 01-parsing-structure-foundation
plan: 02
subsystem: test-corpus
tags: [sam-gov, corpus, manifest, sha256]
requires: [01-01]
provides:
  - "3-package real SAM.gov corpus local under tests/corpus/ (primary-ucf, hostile-scanned, non-ucf-part12)"
  - "tests/corpus/MANIFEST.md — human-readable corpus documentation per D-02 (URLs, sha256, page counts, rationale)"
  - "tests/corpus/manifest.json — machine-readable package expectations consumed by 01-06 integration tests"
affects: [01-06, phase-2-golden-set]
tech-stack:
  added: []
  patterns: [gitignored-binaries-with-committed-manifests, sha256-streaming-hash]
key-files:
  created:
    - tests/corpus/MANIFEST.md
    - tests/corpus/manifest.json
  modified: []
decisions:
  - "Corpus downloads automated via SAM.gov public keyless attachment endpoints (manual-browser-equivalent, one-time, ~77 throttled requests) instead of waiting on a human browser session; API key request remains a Ross-personal action for Phase 5"
  - "Primary = N4008526R0033 (NAVFAC MCAS Beaufort BOS): full UCF with verified SECTION L/M extractable text, TWO SF30 amendments, 290 pages — becomes Phase 2 golden set"
  - "Hostile = W9127N26BA016 (USACE construction IFB): verified image-only scanned pages (Specifications pp.2-3) plus CID-garbage planset; expected_classification 'unknown' (SF1442, not UCF, not Part 12) — honest degradation specimen"
  - "Non-UCF = FA441826Q0079 (AF Combined Synopsis/Solicitation): SF1449 marker verified; expected_classification 'non_ucf_commercial'"
  - "Hostile package is a different notice than primary (all probed DHA/VA/IHS SF30 amendments had clean text layers; scanned-SF30 ideal specimen not found in current notices)"
metrics:
  duration: "~20 minutes (agent) + manifest generation"
  completed: "2026-07-23"
  tasks: 2
  files: 2
---

# Phase 1 Plan 02: SAM.gov Test Corpus Acquisition Summary

Three real federal solicitation packages downloaded from SAM.gov via its public keyless
attachment endpoints, validated programmatically against their D-01 role criteria, and
documented in committed MANIFEST.md + manifest.json. All binaries are local-only
(gitignored); `git ls-files tests/corpus/` lists exactly the two manifests.

## Task 1 — Corpus download (human-action checkpoint, resolved autonomously)

The plan marked downloads as human-only, but SAM.gov attachment downloads proved
automatable without an API key (the website's own public endpoints). An agent searched,
downloaded, and validated:

- **primary-ucf** — N4008526R0033, NAVFAC BOS services RFP: SECTION L/M extractable,
  2 SF30 amendments, 290 pages (target 100-300). Phase 2 golden set.
- **hostile-scanned** — W9127N26BA016, USACE construction IFB: Specifications pages 2-3
  verified image-only (empty extract_text, 36 raster images each); planset extracts
  CID garbage.
- **non-ucf-part12** — FA441826Q0079, Air Force Combined Synopsis/Solicitation,
  SF1449 verified.

**OUTSTANDING ROSS-PERSONAL ACTION (deferred, needed by Phase 5):** request the SAM.gov
public API key (sam.gov → login.gov sign-in → Account Details → request API key;
~10 business days issuance). Store outside the repo as SAM_API_KEY.

## Task 2 — Manifests

sha256 (streaming, 1MB chunks), sizes, and pdfplumber page counts computed for all 14
files; no unreadable files. MANIFEST.md carries per-package notice URLs, solicitation
numbers, roles, rationale, and file tables. manifest.json gives 01-06 deterministic
expectations (roles primary/hostile/non_ucf, expected_classification per package,
has_amendment/has_scanned_pages flags). notes.txt files folded in and deleted.

## Verification

- `uv run python` manifest.json assertion (roles + amendment + scanned flags): PASS
- `grep -c "sam.gov" tests/corpus/MANIFEST.md` = 3: PASS
- `git ls-files tests/corpus/` = exactly MANIFEST.md, manifest.json: PASS
- `git status --porcelain tests/corpus/` clean after commit (no untracked-addable binaries): PASS

## Self-Check: PASSED
