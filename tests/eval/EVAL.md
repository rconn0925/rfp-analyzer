# Extraction Accuracy — Claude Code engine, package N4008526R0033

First measured 2026-07-24 (plan 02-07); re-measured 2026-07-25 after the parser
fix, factor anchoring and the pass-C exhaustive audit. Replaces the retired Qwen
14B-vs-32B bake-off, which died with the local-model engine.

## Result

Re-measured 2026-07-25 after the column-aware parser fix, factor anchoring, and a
pass-C exhaustive audit of Sections L and M (16 pages).

| Metric | Value |
|---|---|
| **Precision (exhaustive scope)** | **0.950** — *a true error rate* |
| **Recall (exhaustive scope)** | **0.864** |
| **F1 (exhaustive scope)** | **0.905** |
| Precision (whole golden set) | 0.714 — still a lower bound outside the scope |
| Recall (whole golden set) | 0.895 (187 of 209) |
| Requirements produced | 277 |
| **Grounded / verified** | **277 / 277 (100%)**, 0 ungroundable |

Exhaustive scope: solicitation pages 49–51 (Section L) and 58–70 (Section M) —
16 pages, 154 ground-truth rows. Reproduce with:

```
rfp-analyzer extract artifacts/primary-ucf   --drafts tests/eval/fixtures/golden_drafts.jsonl   --golden tests/eval/golden/golden_set.json
```

## Precision means something now

The original 0.426 was uninterpretable. The audit proved why instead of assuming
it: every prediction inside the scope was judged against one standard — *does it
obligate the offeror, or state a measure the proposal is judged by?* The
overwhelming majority were genuine requirements the golden set had never
recorded. Exactly **7 were not**, and they are the whole of the false-positive
count:

| Rejected prediction | Why it is not a requirement |
|---|---|
| "Prospective offerors are **requested to** submit written questions…" | Advisory, not mandatory |
| "All inquires will be answered in writing." | Government action, no offeror duty |
| "Proposals from unsuccessful offerors will not be returned… shall be destroyed…" (2 atomic rows) | Government process |
| "No certificate of destruction will be issued." | Government process |
| "…Evaluation of Options will not obligate the Government to exercise the option(s)." | Legal disclaimer |
| "The Offeror **may** include performance recognition documents…" | Permissive option |

## The exhaustiveness claim was wrong once, and fixing it cost recall

Declaring pages 58–70 exhaustive was **false**. Page 62 carried 3,804 characters
of real Factor 1 "Basis of Evaluation" content and had **zero predictions and zero
golden rows** — so it silently contributed nothing to either side of the ratio,
and recall read 0.985 when the page had never been looked at.

Page 62 was then shredded independently by reading it (pass D, 19 rows). Those
rows are the ONLY ground truth in this set not derived from extraction output,
which also makes them the only part with genuine provenance independence.

Recall fell **0.985 → 0.864** as a result. That drop is the measurement getting
*more* honest, not the extractor getting worse: 19 real requirements were being
excluded from the denominator because nobody had recorded them. It is also a
concrete coverage finding — the Factor 1 evaluation sub-criteria on page 62 are
a genuine extraction gap.

The other misses are the known PDF line-wrap hyphenation cases (see below).

**Atomic siblings are in ground truth too.** When a compound sentence is split
into several single-duty rows, the golden set now carries the same siblings, so
the one-to-one match rule is not penalised for splitting correctly. Promoting
deduplicated verbatims only (the first attempt) understated precision at 0.757;
this is a measurement artifact worth naming, not a quality change.

Progression on identical extraction output, which is the cleanest evidence that
the early numbers measured annotation coverage rather than extraction quality:
**0.426 → 0.532 → 0.757 → 0.950**.

**Independence caveat, stated plainly:** ground truth and extractor share an
author. Inside the exhaustive scope this measures *self-consistency of judgment*,
not agreement with an independent human shredder. A second reader is the single
biggest remaining improvement to this eval, and no amount of further self-audit
substitutes for it.

**Verify emptiness, never assume it.** A page with no golden rows and no
predictions looks identical to a page with nothing on it. Any future scope
extension must confirm each declared page was actually read.

**Not yet exhaustive:** the SOW annex (pages 9–16 of the annex file, 50 golden
rows) is still sample-annotated, so predictions there remain outside the scope
and precision over them stays a lower bound.

## What the parser fix changed

The annex two-column defect is gone: descriptions are contiguous, and no
requirement text carries an interleaved title token ("authorizations to
**Licenses** perform work"). Running headers strip correctly too — the frequency
test assumed one header regime per file, but this annex concatenates six
sub-annexes each with its own column header, so none cleared the 40% threshold.
An absolute repetition floor fixed it.

Extraction accuracy was unaffected (277 requirements, 277 grounded): the fix
removed corruption from the text rather than changing what counts as a
requirement.

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
