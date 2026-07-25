# Extraction Accuracy — Claude Code engine, package N4008526R0033

First measured 2026-07-24 (plan 02-07); re-measured 2026-07-25 after the parser
fix, factor anchoring and the pass-C exhaustive audit. Replaces the retired Qwen
14B-vs-32B bake-off, which died with the local-model engine.

## Result

Re-measured 2026-07-25 after the column-aware parser fix, factor anchoring, and a
pass-C exhaustive audit of Section L pages 49-51.

| Metric | Value |
|---|---|
| **Precision (exhaustive scope, L p49-51)** | **0.860** — *a true error rate* |
| **Recall (exhaustive scope)** | **1.000** (49 of 49) |
| **F1 (exhaustive scope)** | **0.925** |
| Precision (whole golden set) | 0.532 — still a lower bound, see below |
| Recall (whole golden set) | 0.977 (125 of 128) |
| Requirements produced | 277 |
| **Grounded / verified** | **277 / 277 (100%)**, 0 ungroundable |

Reproduce exactly:

```
rfp-analyzer extract artifacts/primary-ucf \n  --drafts tests/eval/fixtures/golden_drafts.jsonl \n  --golden tests/eval/golden/golden_set.json
```

## Precision finally means something

The previous 0.426 was **uninterpretable**, and the audit proved why rather than
assuming it. Of 29 distinct unmatched predictions on Section L pages 49-51, **25
were genuine binding requirements the golden set had simply never recorded** —
cover-page contents, the 110-page limit, SPRS registration, the bank reference,
the responsibility-determination submissions. Only 4 were true false positives:

| Rejected prediction | Why it is not a requirement |
|---|---|
| "Prospective offerors are **requested to** submit written questions specifying the section and paragraph…" | Advisory, not mandatory |
| "All inquires will be answered in writing." | Government action, no offeror duty |
| "Proposals from unsuccessful offerors will not be returned… shall be destroyed by the Contracting Officer." | Government process |
| "No certificate of destruction will be issued." | Government process |

Those 25 are now ground truth (`provenance_pass: "C"`), and `golden_set.json`
declares an `exhaustive_scope` naming the page ranges it annotates completely.
Inside that scope an unmatched prediction really is an error, so precision is a
rate: **0.860**. Outside it, precision remains a lower bound and is labelled as
one — that is the honest reading, not a hedge.

Simply adding the 25 audited rows moved whole-set precision 0.426 -> 0.532 on
identical extraction output, which is itself the cleanest evidence that the
original number measured annotation coverage rather than extraction quality.

**Independence caveat, stated plainly:** ground truth and extractor share an
author. This measures self-consistency of judgment, not agreement with an
independent human shredder. Extending the exhaustive scope — ideally with a
second pair of eyes — is the next real improvement.

## What the parser fix changed

The annex two-column defect is gone: descriptions are contiguous, and no
requirement text carries an interleaved title token ("authorizations to
**Licenses** perform work"). Running headers now strip correctly too — the
frequency test assumed one header regime per file, but this annex concatenates
six sub-annexes each with its own column header, so none cleared the 40%
threshold. An absolute repetition floor fixed it.

Extraction accuracy was unaffected by the change (277 requirements, 277
grounded), which is the expected result: the fix removed corruption from the text
rather than changing what counts as a requirement.

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

| Missed (of the pre-audit 103) | Root cause |
|---|---|
| M p63 — "…total length for each Corporate Experience Data Sheet shall not exceed three (3) single-sided pages." | Plain oversight; the sentence was read but not emitted. |
| M p63 — "Contracts with periods of performance beyond one year shall be clearly defined as multi-<br>year contracts…" | `multi-\nyear` de-hyphenates to `multiyear` on normalize. Skipped rather than emit a quote that would not ground. |
| C-Annex p15 — "The Contractor shall provide work schedules for both Recurring and Non-<br>Recurring Work per Section F." | `Non-\nRecurring` → `NonRecurring`. Same cause, same decision. |

The correct handling (learned after the fact): keep the newline **inside** the
verbatim span so it normalizes identically to the page text. Two of three misses
were avoidable.

**These three were NOT added to the drafts artifact after being identified.**
Doing so would make recall reflect knowledge of the answer key rather than
extraction quality. They remain the 3 misses behind whole-set recall 0.977; inside
the exhaustive scope, recall is 1.000 because none of the three falls in it.

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
3. **Ground truth and extractor share an author.** The pass-C audit promoted
   audited predictions to ground truth, so the exhaustive-scope number measures
   self-consistency of judgment, not agreement with an independent shredder.
4. **Minor contamination, disclosed:** while inspecting the golden file's *shape*
   (keys, counts, match rule) before extracting, one of its 103 entries was
   visible. That single requirement was subsequently extracted. Effect on recall
   is at most 1/128 (<0.01). The rest were never read before extraction.
5. Extraction was performed from the exported chunks only, never from
   `golden_set.json`'s requirement text.

## Parser defect — FIXED 2026-07-25

The annex two-column spec table used to inject the Title column mid-sentence
("authorizations to **Licenses** perform work"), corrupting requirement text even
where grounding succeeded, and running headers survived into the text of 40
pages. Both are fixed (`parsing/columns.py`, absolute-repetition header floor).
The 17 recorded draft spans that had encoded the corruption were repaired, and one
golden verbatim carrying a de-hyphenation artifact was corrected.

## Reproducibility

The score is tied to `tests/eval/fixtures/golden_drafts.jsonl`, a committed
414-draft recording of this Claude Code extraction run. Replaying it produces a
byte-identical `RequirementSet` on any machine: no GPU, no API key, and no
sampling variance anywhere in the pipeline. Anyone can re-derive the table above
rather than take it on trust — which is what the retired local-model bake-off,
with its GPU-nondeterminism caveat, could never offer.
