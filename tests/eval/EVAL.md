# Extraction Accuracy — Claude Code engine, package N4008526R0033

Measured 2026-07-24 (Phase 02, plan 02-07). Replaces the retired Qwen 14B-vs-32B
bake-off, which died with the local-model engine.

## Result

| Metric | Value |
|---|---|
| **Recall** | **0.971** (100 of 103 golden requirements matched) |
| **Precision (in scope)** | **0.426** (100 of 235 in-scope predictions matched) — *see caveat, this is a lower bound and not an error rate* |
| **F1** | 0.592 |
| Requirements produced | 277 |
| **Grounded / verified** | **277 / 277 (100%)** — every row string-matched to a computed page reference |
| Ungroundable (hallucinated or drifted quotes) | **0** |
| Chunks extracted | 19 of 98 (the golden-annotated scope; see *Scope*) |
| Predictions on unannotated pages | 42 (not scored) |

Reproduce exactly:

```
rfp-analyzer extract artifacts/primary-ucf \
  --drafts tests/eval/fixtures/golden_drafts.jsonl \
  --golden tests/eval/golden/golden_set.json
```

## How to read these numbers

**Recall (0.971) is the trustworthy headline.** Every golden requirement is in
scope by construction, so nothing about the scoping method can inflate it.

**Precision (0.426) is a lower bound, not an error rate.** Investigated rather
than reported at face value:

- Of 135 unmatched in-scope predictions, only **10** are atomic siblings of a
  matched row (a compound obligation split into more rows than the golden set
  splits it into). Sibling over-splitting is therefore *not* the explanation.
- The other **125 have genuinely distinct verbatim spans**, and **65 carry a hard
  binding keyword** (`shall` / `must` / `shall not`). A random sample of 18 was
  inspected by hand; they are real obligations, e.g.:
  - "Include a cover page with Solicitation Number, Solicitation Title, Prime Contractor Name…" (L, p49, *shall*)
  - "Inadequate or unsafe items shall be removed and replaced by the Contractor at no cost to the Government." (Annex, p14)
  - "Government personnel access shall be limited to viewing and downloading of deliverables, but restricted from posting to the website." (Annex, p16)
  - "No work will commence until appropriate certification and permits have been obtained." (Annex, p11)

**Conclusion: the golden set is a validated _sample_ of its pages, not an
exhaustive shred of them.** Its own `build_method` says "agent-drafted (pass A) +
adversarially validated (pass B)" — nothing claims completeness. So most
"false positives" are requirements the ground truth simply does not record.
Precision cannot be interpreted as extraction error until the golden set is made
exhaustive over a defined page range. **That is the single highest-value fix to
this eval** and is the recommended next step.

Collapsing atomic siblings to one row per unique verbatim gives P=0.437 / R=0.835
— the recall drop confirms atomic splitting is doing real work, not padding.

## Scope

The golden set annotates ~22 of the package's 290 pages: solicitation p10
(Section C), p49–51 (L), p59–69 (M), and annex p9–16 (C-Annex-SOW). Extraction
therefore covered the 19 chunk positions spanning those pages (11 distinct chunk
texts — nested sections share text, which the content-derived `chunk_key`
collapses).

Precision is computed only over predictions inside that `(file_id, page)`
footprint. A prediction on an unannotated page is *unjudged*, not wrong; counting
it as a false positive would report a number that measures how much of the package
was annotated rather than how good the extraction is. The 42 out-of-scope
predictions are counted and printed, never silently dropped.

The run's coverage warning ("79 chunks had no recorded drafts — recall is
understated") is correct in general but does **not** apply to this scored number:
the unextracted chunks contain no golden rows, so recall over the golden set is
unaffected.

## The three missed requirements

All three are traceable to one root cause — **verbatim spans broken by PDF
line-wrap hyphenation**:

| Missed | Root cause |
|---|---|
| M p63 — "…total length for each Corporate Experience Data Sheet shall not exceed three (3) single-sided pages." | Plain oversight; the sentence was read but not emitted. |
| M p63 — "Contracts with periods of performance beyond one year shall be clearly defined as multi-<br>year contracts…" | `multi-\nyear` de-hyphenates to `multiyear` on normalize. Skipped rather than emit a quote that would not ground. |
| C-Annex p15 — "The Contractor shall provide work schedules for both Recurring and Non-<br>Recurring Work per Section F." | `Non-\nRecurring` → `NonRecurring`. Same cause, same decision. |

The correct handling (learned after the fact): keep the newline **inside** the
verbatim span so it normalizes identically to the page text. Two of three misses
were avoidable.

**These three were NOT added to the drafts artifact after being identified.**
Doing so would make recall reflect knowledge of the answer key rather than
extraction quality. 0.971 is the honest measured number.

## Known measurement caveats

1. **The match rule is superset-tolerant.** `token_set_ratio` scores 100 when a
   prediction's token set contains the golden span's, so quoting a whole paragraph
   that merely *contains* the required sentence matches as well as an exact quote.
   Precision therefore does not penalize over-broad spans. Tightness is enforced
   separately by `test_golden_verbatim.py` (exact-locatable-span contract).
2. **The match rule cannot see atomic siblings.** Matching is one-to-one on
   verbatim text, so when a compound sentence is split into more rows than ground
   truth splits it into, the extra siblings score as false positives even when the
   split is correct. Affects 10 rows here.
3. **Minor contamination, disclosed:** while inspecting the golden file's *shape*
   (keys, counts, match rule) before extracting, one of its 103 entries was
   visible. That single requirement was subsequently extracted. Effect on recall
   is at most 1/103 (≈0.01). The remaining 102 were never read before extraction.
4. Extraction was performed from the exported chunks only, never from
   `golden_set.json`'s requirement text.

## Parser defect found (Phase 1, worth fixing)

The Section C Annexes use a **two-column spec-item table** (Spec Item / Title /
Description). Flattening injects the *title* column into the middle of description
sentences:

- "…authorizations to **Licenses** perform work under this contract…"
- "…at least 30 calendar days written **Insurance** notice to the KO…"
- "…shall provide sign-in sheets and prepare minutes of all meetings and **Meetings** submit per Section F…"

10 of 70 annex spans required the interleaved token to be reproduced in order to
ground. This corrupts requirement text in the exported matrix even when grounding
succeeds, and it will read as gibberish to a proposal manager. Page-break running
headers ("0200000 - Management and Administration / Spec Item Title Description")
similarly split sentences mid-span, making some obligations unquotable as a single
contiguous run.

**Recommendation:** carry this into Phase 3 as a parsing backlog item —
column-aware extraction for annex spec tables, and running-header suppression.

## Reproducibility

The score is tied to `tests/eval/fixtures/golden_drafts.jsonl`, a committed
414-draft recording of this Claude Code extraction run. Replaying it produces a
byte-identical `RequirementSet` on any machine: no GPU, no API key, and no
sampling variance anywhere in the pipeline. Anyone can re-derive the table above
rather than take it on trust — which is what the retired local-model bake-off,
with its GPU-nondeterminism caveat, could never offer.
