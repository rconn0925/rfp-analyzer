---
phase: 01-parsing-structure-foundation
reviewed: 2026-07-24T01:21:56Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - .github/workflows/ci.yml
  - src/rfp_analyzer/__init__.py
  - src/rfp_analyzer/cli.py
  - src/rfp_analyzer/pipeline/__init__.py
  - src/rfp_analyzer/pipeline/classify/__init__.py
  - src/rfp_analyzer/pipeline/classify/forms.py
  - src/rfp_analyzer/pipeline/classify/package.py
  - src/rfp_analyzer/pipeline/metrics.py
  - src/rfp_analyzer/pipeline/models.py
  - src/rfp_analyzer/pipeline/parsing/__init__.py
  - src/rfp_analyzer/pipeline/parsing/discover.py
  - src/rfp_analyzer/pipeline/parsing/docx.py
  - src/rfp_analyzer/pipeline/parsing/pdf.py
  - src/rfp_analyzer/pipeline/quality/__init__.py
  - src/rfp_analyzer/pipeline/quality/gates.py
  - src/rfp_analyzer/pipeline/quality/headers.py
  - src/rfp_analyzer/pipeline/run.py
  - src/rfp_analyzer/pipeline/sectioning/__init__.py
  - src/rfp_analyzer/pipeline/sectioning/headings.py
  - src/rfp_analyzer/pipeline/sectioning/tree.py
  - tests/corpus/MANIFEST.md
  - tests/corpus/manifest.json
  - tests/integration/__init__.py
  - tests/integration/conftest.py
  - tests/integration/test_corpus_packages.py
  - tests/unit/conftest.py
  - tests/unit/test_discover.py
  - tests/unit/test_docx.py
  - tests/unit/test_forms.py
  - tests/unit/test_headers.py
  - tests/unit/test_headings.py
  - tests/unit/test_models.py
  - tests/unit/test_package_classify.py
  - tests/unit/test_pdf.py
  - tests/unit/test_quality_gates.py
  - tests/unit/test_tree.py
findings:
  critical: 1
  warning: 7
  info: 11
  total: 19
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-07-24T01:21:56Z
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

The Phase 1 pipeline (discover → parse → quality → sectioning → classify, plus CLI and corpus tests) is well-structured with a clean library/CLI boundary, real hostile-input tests, and honest-degradation semantics. However, the review found one critical defect and several warnings that directly contradict the code's own documented contracts:

1. The pipeline's central promise — "never raises on hostile package content" — is false: discovery performs unguarded `stat()`/`open()`/`resolve()` calls, so a locked, unreadable, or mid-run-deleted file crashes the entire run (CR-01).
2. Two documented threat-model guards do not do what their docstrings claim: the pre-parse size cap fires only *after* the full file has been read and hashed (WR-01), and the Pitfall-5 "scanned SF30 must never silently pass as an attachment" ladder is bypassed by the corpus's own CID-gibberish failure mode (WR-02).
3. Header/footer stripping deletes matching lines from the *entire* page rather than the top/bottom bands the research pattern specifies — a silent content-loss vector feeding Phase 2 extraction (WR-04).
4. The `_choose_start` heuristic does the opposite of its docstring for mid-document cross-references (WR-06).

None of the quick-scan security patterns (hardcoded secrets, eval/exec, debug artifacts, empty catches) were found. The regex DoS posture (T-01-12) checks out: all patterns are anchored with bounded quantifiers, and there is an adversarial timing test.

## Critical Issues

### CR-01: `discover_files` crashes the whole pipeline on unreadable or vanished files, violating the never-raise contract

**File:** `src/rfp_analyzer/pipeline/parsing/discover.py:44-52, 84, 119`
**Issue:** `run_pipeline`'s docstring promises "Never raises on hostile package content," and discover.py's docstring says "discovery never raises on hostile input." Neither is true. Inside `discover_files`:
- `_file_identity` (line 50) does `path.open("rb")` with no exception handling. A file locked by another process (routine on Windows), a permission-denied file, or a file deleted between `rglob` and `open` raises `PermissionError`/`OSError`/`FileNotFoundError`, which propagates out of `discover_files`, out of `run_pipeline`, and crashes the CLI with a traceback instead of a rejected-file record.
- `path.stat()` (lines 119-120) is similarly unguarded and is called twice.
- `_is_within` calls `path.resolve()` (line 44), which can raise `OSError` on pathological symlink/junction loops on some platforms — exactly the hostile-input class T-01-08 claims to handle.

Per-file isolation is enforced in the parsers but not in the stage that runs *before* them, so a single bad directory entry takes down the entire package run.
**Fix:**
```python
for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
    filename = path.relative_to(package_dir).as_posix()
    try:
        if not _is_within(path, package_dir):
            ...  # existing containment rejection
            continue
        size = path.stat().st_size
        sha256, file_id = _file_identity(path)
    except OSError as exc:
        file_id = "0" * 12 + "-" + _STEM_SANITIZER.sub("-", path.stem.lower()).strip("-")[:40]
        discovered.append(DiscoveredFile(
            path=path, filename=filename, sha256="", file_id=file_id, kind="rejected",
            rejection=_rejection(filename, "", file_id, "other",
                                 f"unreadable file: {exc}"),
        ))
        continue
    ...
```
(Reuse `size` for the cap check instead of re-calling `stat()`; see WR-01 for ordering.)

## Warnings

### WR-01: Size cap enforced only after the whole file is read and hashed — the T-01-06 pre-parse DoS guard doesn't guard

**File:** `src/rfp_analyzer/pipeline/parsing/discover.py:109-121`
**Issue:** The docstring claims "per-file size cap before a parser ever opens it," but `_file_identity(path)` (line 109) streams and SHA-256-hashes the *entire file* before the size check on line 119 runs. A hostile 200 GB `huge.pdf` is fully read before being rejected for size — the exact resource-exhaustion the cap exists to prevent. Worse, files that will be rejected anyway (`.doc`, unsupported extensions) are also fully hashed first. The `stat()` result is also computed twice (lines 119 and 120).
**Fix:** Reorder: check `suffix` and `path.stat().st_size` first; only compute `_file_identity` for files that pass the extension allowlist and size cap. For rejected records where a hash is still wanted, either skip hashing (sha256="") or hash only after the size check passes.

### WR-02: Gibberish-text-layer SF30 silently classified as `attachment` — Pitfall 5 bypassed by the corpus's own CID-garbage failure mode

**File:** `src/rfp_analyzer/pipeline/classify/forms.py:93-94, 149-153`; `src/rfp_analyzer/pipeline/quality/headers.py:96-98`
**Issue:** Rung 2 of the SF30 ladder requires `not _has_page1_text(file)`. `apply_quality` empties `page.text` for non-ok pages, but **never clears `first_page_layout_text`**, which is captured at parse time from the raw page. So for an SF30 whose page 1 has a broken-font text layer (CID garbage — the exact hostility the corpus's Planset specimen documents, and which the quality gates classify `gibberish`):
- `_page1_text` returns `""` (emptied by quality),
- `first_page_layout_text` still contains non-empty garbage like `(cid:0)(cid:2)…`,
- `_has_page1_text` returns True, rung 2 is skipped,
- `detect_form` finds nothing in the garbage, so rung 3 assigns `attachment` — silently, with no evidence trail.

The module docstring says "a scanned SF30 must never silently pass as a plain attachment"; a gibberish-layer SF30 does exactly that. The unit tests only cover the clean-empty scanned case (`page1_text=""`, `layout=None`), so this hole is untested.
**Fix:** Treat an unusable page-1 text layer like a missing one. Either have `apply_quality` clear `first_page_layout_text` when page 1 is non-ok, or make rung 2 quality-aware:
```python
def _page1_usable(file: ParsedFile) -> bool:
    if file.file_type == "pdf" and file.pages and file.pages[0].quality != "ok":
        return False
    return _has_page1_text(file)
```
and use `not _page1_usable(file)` for rung 2.

### WR-03: `ParsedFile.filename` loses the relative path for parsed files — inconsistent with rejections and the discovery contract; nested same-basename files collide

**File:** `src/rfp_analyzer/pipeline/run.py:48-50`; `src/rfp_analyzer/pipeline/parsing/pdf.py:65, 74`; `src/rfp_analyzer/pipeline/parsing/docx.py:36, 105`
**Issue:** `discover_files` documents (and tests verify, `test_nested_files_discovered_with_relative_path`) that `filename` records the posix path relative to the package dir — the docstring explicitly cites nested SAM.gov zip layouts. But `run_pipeline` never passes `entry.filename` to the parsers; `parse_pdf`/`parse_docx` set `filename=path.name` (basename only). Result: rejected records carry `attachments/sow.pdf` while parsed records carry `sow.pdf` — two conventions in one document map — and two nested files with the same basename (e.g., `amd1/SF30.pdf`, `amd2/SF30.pdf`) produce indistinguishable `filename` values in the Phase 2 contract and the human report. (`file_id` stays unique via the sha prefix, which is the only reason this isn't critical.)
**Fix:** Thread the discovered filename through: add a `filename: str` keyword to `parse_pdf`/`parse_docx` and call them as `parse_pdf(entry.path, filename=entry.filename, sha256=..., file_id=...)`.

### WR-04: Running-header stripping deletes matching lines from the entire page, not just the top/bottom bands — silent content loss

**File:** `src/rfp_analyzer/pipeline/quality/headers.py:99-102`
**Issue:** Detection votes only on the top/bottom `RUNNING_LINE_BAND` lines, but removal filters **every line on the page** whose normalized (digit-stripped, uppercased) form is in the running set. Any body line that happens to normalize to a running pattern is silently deleted from stored text. This is realistic, not theoretical: the running header is typically the solicitation number, and body text legitimately contains standalone solicitation-number lines (amendment references, signature blocks); digit-stripping makes collisions broader (e.g., a numeric-heavy footer pattern can match structurally similar table rows mid-page). For a product whose stated core value is "if the extraction is wrong or incomplete, nothing else matters," silently deleting mid-page lines that feed Phase 2 requirement extraction is a data-integrity defect.
**Fix:** Strip only within the same bands that voted:
```python
lines = page.text.splitlines()
n = len(lines)
kept = [
    line for i, line in enumerate(lines)
    if not ((i < RUNNING_LINE_BAND or i >= n - RUNNING_LINE_BAND)
            and _normalize(line) in running)
]
page.text = "\n".join(kept)
```

### WR-05: `document_map.json` write can crash on unencodable extracted text (lone surrogates from hostile PDFs)

**File:** `src/rfp_analyzer/cli.py:164`
**Issue:** Page text flows raw from pdfminer into the JSON artifact. A malformed/hostile PDF whose ToUnicode CMap maps glyphs to surrogate code points yields Python strings containing lone surrogates; `model_dump_json()` / `write_text(..., encoding="utf-8")` then raises (`UnicodeEncodeError` or a pydantic-core serialization error), crashing the run at the final step — after the entire pipeline succeeded. The CLI already hardens stdout with `errors="replace"` (cli.py:178-181) but not the artifact write, and the quality stage never sanitizes surviving "ok" text.
**Fix:** Sanitize text at the quality stage (e.g., `text.encode("utf-8", "replace").decode("utf-8")` for ok pages), or harden the write: `map_path.write_bytes(document_map.model_dump_json(indent=2).encode("utf-8", errors="replace"))`.

### WR-06: `_choose_start` prefers the LAST qualifying occurrence, so a mid-document leading-line cross-reference beats the real section heading

**File:** `src/rfp_analyzer/pipeline/sectioning/tree.py:93-103`
**Issue:** The docstring claims the last-qualifying rule "guards against both the page-1 TOC and mid-document cross-references," but for cross-references it does the opposite. If the true `SECTION L` heading is on page 40 and page 45 begins with a line like `SECTION L of this solicitation is amended as follows` (line-start anchored, within `LEADING_LINE_LIMIT`, matches `SECTION_HEADING` with the tail captured as title), both occurrences precede Section M, so both qualify — and `qualifying[-1]` picks page 45. The section start shifts to the cross-reference and the reported span/title are wrong. The TOC case this rule targets is already handled separately by `_is_toc_page` exclusion, which weakens the justification for last-wins.
**Fix:** Prefer the FIRST qualifying occurrence on non-TOC pages (TOC pages are already excluded before occurrences are built), or keep last-wins but reject occurrences whose captured title continues as prose (e.g., title matching `^(OF|IS|WILL|SHALL)\b`). At minimum, correct the docstring and add a corpus/unit case pinning the intended behavior.

### WR-07: DOCX Word-generated TOC lines can fabricate `role_title` nodes — the TOC guard only covers the `heading` signal

**File:** `src/rfp_analyzer/pipeline/sectioning/tree.py:252-253`
**Issue:** In the DOCX branch, `_TOC_TRAILING_RE` skipping is applied only when `cand.signal == "heading"`. A Word TOC entry like `STATEMENT OF WORK .......... 12` matches `match_role_title` (substring match), becomes a `role_title` occurrence, and — in a file with no letter sections — is emitted as a top-level SOW node whose locator points at the TOC block, not the content. That violates the honesty invariant the module is built around (nodes only for real structure) and can feed a bogus `C`-slot signal into `classify_package` via `_section_key`.
**Fix:** Apply the TOC-trailing skip to all signals in the DOCX branch:
```python
if _TOC_TRAILING_RE.search(cand.title) or (
    cand.signal == "role_title" and _TOC_TRAILING_RE.search(block.text)
):
    continue
```

## Info

### IN-01: Unreachable `parser.error` in `main`

**File:** `src/rfp_analyzer/cli.py:190`
**Issue:** `argparse` subparsers constrain `args.command` to `None` or `"parse"`; both are handled above, so line 190 is dead code.
**Fix:** Delete it, or replace the `if` chain with a dispatch dict if more commands are coming.

### IN-02: `PART` headings are detected, prioritized, and tested — but can never produce a section node

**File:** `src/rfp_analyzer/pipeline/sectioning/tree.py:144` (filter `o.candidate.letter`); `headings.py:139-149`
**Issue:** `PART_HEADING` candidates carry `letter=None`, and `_build_tree` filters `heading_occs` down to letter-bearing occurrences, so PART nodes are silently dropped everywhere. The regex, its candidate branch, and its tests are effectively dead signal for output (they only consume a line's one-candidate slot).
**Fix:** Either emit PART nodes (as parents or standalone), or document that PART detection is intentionally output-inert in Phase 1.

### IN-03: `RunMetrics` docstring stage names don't match the keys `run_pipeline` writes

**File:** `src/rfp_analyzer/pipeline/metrics.py:14-16` vs `src/rfp_analyzer/pipeline/run.py:40-66`
**Issue:** Docstring says `"parsing"`, `"quality"`, `"sectioning"`, `"classify"`; actual keys are `discover`, `parse`, `quality`, `sectioning`, `classify`.
**Fix:** Update the docstring to the real key set.

### IN-04: `package_name` uses the unresolved dir name — empty string for `.`, inconsistent with the CLI's output-path naming

**File:** `src/rfp_analyzer/pipeline/run.py:76` vs `src/rfp_analyzer/cli.py:160`
**Issue:** `run_pipeline` uses `package_dir.name` (raw), so `rfp-analyzer parse .` yields `package_name=""` in the artifact, while the CLI derives the output folder from `package_dir.resolve().name or "package"`. Same run, two names.
**Fix:** Use `package_dir.resolve().name or "package"` in `run_pipeline` (or pass the resolved name in).

### IN-05: Magic number 40 in DOCX "page 1" approximation

**File:** `src/rfp_analyzer/pipeline/classify/forms.py:89`
**Issue:** `b.ordinal < 40` defines the DOCX "first page" window with an undocumented inline constant, unlike every other tunable in this codebase (named module constants).
**Fix:** `DOCX_PAGE1_BLOCKS = 40` module constant with an A-note docstring.

### IN-06: `_AMENDMENT_NUMBER_RE` accepts a single character — extraction-order noise can capture the next block label

**File:** `src/rfp_analyzer/pipeline/classify/forms.py:63-65`
**Issue:** On real SF30s the number sits in a form cell, and default-mode extraction can order text as `AMENDMENT/MODIFICATION NO. 3. EFFECTIVE DATE ... 0002`; the regex (`[A-Z0-9][A-Z0-9-]{0,19}`) then captures `3` (the next block's label) as the amendment number. No corpus test asserts extracted numbers.
**Fix:** Require ≥2 chars or an amendment-number shape (`\d{4}|[AP]\d{5,}`), and add a corpus assertion for the primary package's `0001`/`0002`.

### IN-07: Integration suite is cwd-dependent and never verifies corpus checksums

**File:** `tests/integration/conftest.py:18`; `tests/integration/test_corpus_packages.py:26`
**Issue:** `CORPUS_DIR = Path("tests/corpus")` is relative to the invocation cwd; running pytest from anywhere but the repo root silently skips (or empty-parametrizes) the whole suite. Also, `corpus_available()` accepts any non-empty package dir — a stale/partial corpus runs (and fails confusingly) rather than being detected, despite MANIFEST.md promising sha256 verification.
**Fix:** Anchor with `Path(__file__).resolve().parents[2] / "tests" / "corpus"`, and (optionally) verify manifest sha256s in `corpus_available()`, skipping with a "corpus mismatch" reason.

### IN-08: Containment-rejected files share a dummy identity — duplicate `file_id`s possible

**File:** `src/rfp_analyzer/pipeline/parsing/discover.py:90`
**Issue:** Every containment rejection gets `file_id = "000000000000-<stem>"`; two rejected files with the same sanitized stem in different subdirs produce identical `file_id`s, breaking the stable-identity property the field exists for.
**Fix:** Mix the relative path into the dummy id, e.g. hash `filename` for the prefix.

### IN-09: TOCTOU window between the containment check and parse-time open

**File:** `src/rfp_analyzer/pipeline/parsing/discover.py:89` vs `src/rfp_analyzer/pipeline/run.py:48-50`
**Issue:** Containment is validated at discovery time, but parsers reopen `entry.path` in a later stage; a symlink swapped in between is read from outside the package dir. Low risk for the Phase-1 local CLI, but this code is the declared foundation for the web/worker upload path.
**Fix:** Note it in the threat model now; when files become user uploads, re-validate (or open the file handle once at discovery and pass it through).

### IN-10: Bounded-heuristic edge cases: >120-char heading tails never match; headings ending in a bare number are treated as TOC lines in DOCX

**File:** `src/rfp_analyzer/pipeline/sectioning/headings.py:28-31`; `src/rfp_analyzer/pipeline/sectioning/tree.py:41, 252`
**Issue:** `SECTION_HEADING`'s `(.{0,120})$` makes the whole match fail when the tail exceeds 120 chars — a heading line merged with following prose by PDF extraction (common) is silently not a heading at all, rather than matched with a truncated title. Separately, `_TOC_TRAILING_RE`'s `\s\d{1,4}$` alternative marks any DOCX heading ending in a number (e.g., `SECTION J - ATTACHMENT 3` style titles, `... FY 2026`) as a Word TOC line and skips it. Both are A5/A7 corpus-tunable heuristics, flagged here so corpus calibration checks them deliberately.
**Fix:** For the 120 cap, drop `$` and let the group truncate (`(.{0,120})` without end anchor). For the TOC tail, require dot leaders or ≥2 trailing spaces before the number.

### IN-11: CI actions pinned by tag, not commit SHA

**File:** `.github/workflows/ci.yml:9-11`
**Issue:** `actions/checkout@v4` (floating major) and `astral-sh/setup-uv@v9.0.0` (tag) are mutable references; a compromised tag re-point compromises CI. Low severity for a public portfolio repo, standard hardening for the "sellable product" trajectory.
**Fix:** Pin to full commit SHAs with a version comment, e.g. `actions/checkout@<sha> # v4.x.y`.

---

_Reviewed: 2026-07-24T01:21:56Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
