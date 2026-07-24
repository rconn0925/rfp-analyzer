# Golden Set Review Note — N4008526R0033

**Package:** N4008526R0033 — MCAS Beaufort and Laurel Bay Base Operation Support
(DoD / Navy / NAVFAC). **Corpus:** `tests/corpus/primary-ucf` (7 PDFs, 290 pp,
gitignored). **Built:** 2026-07-24. **Final size:** 103 ground-truth requirements
(57 pass-A + 46 pass-B), 90 unique verbatim spans, 8 atomic-split groups.

This note records how the golden set was built, what the adversarial pass found,
what is and isn't covered, and the honest caveat about an agent-built baseline —
so Ross (or anyone) can spot-check it later. This is **non-blocking**, like the
Phase 1 HUMAN-UAT.

---

## How it was built (two-pass, autonomous)

Per the locked decision (CONTEXT.md), the human review checkpoint is replaced by
**two independent agent passes**:

- **Pass A — draft.** Read the *cleaned, page-referenced* section text from the
  Phase 1 document map (`artifacts/primary-ucf/document_map.json`, produced by
  `run_pipeline` over the primary corpus — the same map the extractor will consume).
  Hand-shredded the requirement-bearing sections into ground-truth requirements,
  each carrying `file_id`, `page`, `verbatim_text` (a **real contiguous span copied
  from the source page**), `atomic_obligation` (single-duty rewrite), `binding_keyword`,
  and `req_type`. Compound obligations were split into atomic siblings sharing one
  verbatim span, linked by `parent_id` (splitting rule documented in `schema.md`).
  Pass A produced 57 entries.

- **Pass B — adversarial validation + reconciliation.** An independent, deliberately
  skeptical second look at the source text:
  1. **Verbatim/page verification** — every `verbatim_text` was string-matched
     (after NFKC + de-hyphenation + whitespace-collapse normalization) against its
     cited page. See "Findings" for the defects this caught and fixed.
  2. **Miss hunt** — ran a deterministic `shall/must/shall not` keyword sweep over
     exactly the pages pass A drew from, then flagged every binding sentence *not*
     covered by a pass-A verbatim span. Each flag was triaged (genuine obligation vs.
     government-action vs. near-duplicate vs. sweep artifact) and genuine misses were
     added as pass-B entries.
  3. **Over-/under-split review** — checked atomic groups against the splitting rule;
     kept coordinated enumerations/verb phrases split and left conditionals/temporal
     qualifiers intact (e.g. *"until time of award, during performance and through
     final payment"* remains one row).

The build/validation scripts are ephemeral (run against the gitignored corpus); the
**committed** gate is `check_golden.py` + `tests/eval/test_golden_verbatim.py`, which
re-verify every verbatim on demand and skip cleanly where the corpus is absent (CI).

---

## Adversarial-pass findings (concrete)

**Verbatim/page defects fixed (4, all table-layout traps).** The PWS annex pages use
a three-column *Spec Item / Title / Description* layout whose title-column words are
interleaved into the extracted prose stream. Pass A initially quoted spans that read
cleanly to a human but are **not contiguous** in the parsed text:

| Defect | Fix |
|--------|-----|
| Permits obligation spanned a page break (p10→p11) *and* the title word "Licenses" split the stream | Re-paged to p10; split into two distinct (still real, contiguous) p10 spans |
| Certificate-of-Insurance span broken by the interleaved title "Insurance" | Trimmed the span to end at "…30 calendar days written" (still carries the `shall`) |
| "the Contractor shall furnish all labor…" — title "Furnished Items" sits between "shall" and "furnish", making the span unquotable | Replaced with a clean, contiguous `shall not` obligation on the same page (GFI-breakdown responsibility) |
| Several pass-B annex spans (safeguard-info, procure/maintain-insurance, submit-COI) | Authored as trimmed contiguous spans to dodge the same interleave |

**Misses found and reconciled (46 added).** The sweep found **154** binding
sweep-hits on the covered pages. Pass A covered the high-signal Section L submittal
instructions, Section M factor submittal requirements, and a first cut of the PWS
SOW obligations. Pass B added **46** genuine contractor/offeror obligations that
pass A had omitted — chiefly additional Section M factor requirements (phase-in,
workforce, safety, corporate-experience constraints) and a large batch of PWS SOW
obligations from Annex 0200000 (permits, insurance, GFI/GFP handling, safeguarding
CUI, work control, invoicing). Section coverage grew L 18→24, M 15→24, C 4→5,
C-Annex-SOW 20→50.

**Deliberately excluded (not misses).** Of the sweep hits left uncovered, a large
share are correctly *not* ground-truth offeror/contractor obligations:
- **Government / board / CO actions** — e.g. *"Proposals from unsuccessful offerors …
  shall be destroyed by the Contracting Officer"*, *"The evaluation report must
  document …"*, *"The Government shall provide the Contractor …"*, *"The facilitator
  must be acceptable to both …"*. These bind the Government or describe process, not
  the offeror.
- **Near-duplicates** of a covered entry (the same obligation repeated on a later
  page, e.g. the FAR 15.107 submission sentence on both p49 and p50).
- **Sentence-segmentation artifacts** — bare lead-ins (*"The Offeror shall submit the
  following information."*), bullet fragments, and rows where the table title column
  still contaminates the swept sentence.

---

## Coverage scope (what was and was not shredded)

**In scope / covered (representative, page-anchored):**
- **Section L — Instructions** (Solicitation pp. 49–51): proposal content,
  submission, registrations (SAM/SPRS/FAPIIS/VETS-4212/CMMC), responsibility data.
- **Section M — Evaluation** (Solicitation pp. 58–70, sampled): Factor 1 Management
  Approach, Factor 2 Corporate Experience, Factor 3 Safety, Factor 4 Past Performance
  submittal requirements and page/format limits.
- **Section C** (Solicitation p. 10): reporting, GPC, ECMRA labor-hour reporting.
- **PWS SOW — Section C Annexes**, Annex 0200000 Management & Administration
  (pp. 9–16): partnering, permits/licenses, insurance, GFP/GFI, safeguarding CUI,
  contractor-furnished items, management, work control/scheduling, invoicing,
  deliverables. This exercises the **EXTR-04** "requirements outside L/M" path.

**Explicitly NOT exhaustively covered (known, quantified limitation):**
- **FAR/DFARS clause full-text** in Section L (Solicitation pp. 52–57) is out of
  scope for v1 — these are incorporated clauses, not solicitation-authored offeror
  instructions.
- The golden set is a **representative baseline, not an exhaustive shred**. After
  pass B, **65** binding sweep-hits remain uncovered on the covered pages. Roughly a
  third are the correctly-excluded non-obligations above; the remainder are genuine
  but lower-priority PWS mechanics — concentrated in Annex 0200000 spec items
  2.6.5–2.6.8 (deliverable-website mechanics, service-interruption/utility-outage and
  excavation-request procedures on pp. 15–16) — deliberately left out of the v1
  baseline. They are honest gaps, not hidden ones.
- The 161-page Section C Annexes and 18-page Section F Annex are sampled, not fully
  shredded; the base-solicitation Sections D–K and the SF30 amendments are not in the
  golden set (amendment handling is INTK-03, scored separately).

**Locatability:** 103 / 103 verbatims (100%) are exact substrings of their cited page
after normalization — **zero fuzzy exceptions**. Every span is a real contiguous run
of source characters; none required fuzzy tolerance to locate.

---

## Honest caveat (threat T-02-08) and its mitigation

**An agent built this baseline, and the same class of agent builds the extractor —
so they can share blind spots.** A requirement that is genuinely hard for an LLM to
recognize (buried in a table, phrased without a standard binding keyword, split
awkwardly across a page break) may be missed by *both* the golden-set author and the
extractor. If so, recall measured against this golden set would look better than the
true recall, because the yardstick omits the same thing the extractor omits. The
two-pass adversarial process narrows this gap but does not eliminate it — both passes
are still the same kind of reader.

**Independent mitigations already in place:**
1. **EXTR-05 deterministic keyword sweep** — a pure-Python, model-independent
   `shall/must/will/should` pass over the cleaned page text. It is *not* an LLM, so it
   catches keyword-bearing obligations both agents might overlook, and it surfaces
   them as "missed candidates" at eval time. This is the primary cross-check.
2. **EXTR-02 computed grounding** — every extracted (and every golden) verbatim must
   string-match a real page; fabricated obligations cannot pass, so the failure mode
   is *omission*, never invention.
3. **The committed locatability test** — `test_golden_verbatim.py` prevents silent
   drift: if a page's text changes or a span was mis-transcribed, the check fails.

Residual risk after all three: **shared omission of non-keyword or table-mangled
obligations.** This is documented, not silent, and is the main thing a human
spot-check should probe.

---

## How Ross can spot-check this later (non-blocking)

1. Open `golden_set.json` alongside the source PDFs in `tests/corpus/primary-ucf`.
   Jump to any entry's `page` in `Solicitation - N4008526R0033.pdf` (or the Annexes
   PDF) and confirm the `verbatim_text` is really there and really binding.
2. **Recall probe:** pick a covered page (e.g. Section L p50, or Annex p11) and read
   it top-to-bottom, listing every offeror/contractor "shall/must". Compare with the
   golden entries for that page — anything you find that's missing is a real miss to
   add (especially non-keyword obligations the sweep can't catch).
3. **Precision probe:** skim the `atomic_obligation` values and confirm none invert or
   distort the source meaning, and that atomic splits didn't fabricate obligations.
4. Re-run the machine gate any time: `uv run python tests/eval/golden/check_golden.py`
   (or `uv run python -m pytest tests/eval/test_golden_verbatim.py`).

Findings from a spot-check feed straight back into `golden_set.json` (add/adjust
entries, re-run the check) — the baseline is meant to improve over time.
