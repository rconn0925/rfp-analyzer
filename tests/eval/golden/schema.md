# Golden Set Schema — `golden_set.json`

Ground-truth requirements for the primary package **N4008526R0033** (MCAS Beaufort
and Laurel Bay Base Operation Support). This is the measurement baseline the Phase 2
extraction bake-off scores recall/precision against. Built by a two-pass agent
process (draft + adversarial validation) — see `review-note.md`.

The entry shape deliberately mirrors the Phase 2 `Requirement` contract
(`src/rfp_analyzer/pipeline/models.py`) so the eval matcher (02-07) compares
like-for-like: same `file_id`, same `page`, and a `verbatim_text` that grounds.

## Top-level object

| Field | Type | Description |
|-------|------|-------------|
| `package` | string | Solicitation number (`N4008526R0033`). |
| `solicitation_title` | string | Human title. |
| `source_corpus` | string | Corpus dir under `tests/corpus/` (`primary-ucf`). |
| `built` | string (date) | Build date. |
| `build_method` | string | Two-pass provenance pointer. |
| `granularity` | string | The atomic-granularity contract in one line. |
| `verbatim_contract` | string | The locatability guarantee every `verbatim_text` upholds. |
| `match_rule` | object | How a predicted requirement is judged to match a golden one (for the eval matcher). |
| `counts` | object | Summary counts (`total`, `by_section`, `unique_verbatim_spans`, `atomic_split_groups`). |
| `requirements` | array | The ground-truth entries (below). |

## Requirement entry

| Field | Type | Description |
|-------|------|-------------|
| `requirement_id` | string | Stable content-derived key `GOLD-<sha256[:10]>` of `(file_id \| normalized verbatim \| atomic_ord)`. Stable across re-emits; not order-based. |
| `section` | string | `L` \| `M` \| `C` \| `C-Annex-SOW` \| `other` — readability label. |
| `file_id` | string | The Phase 1 `ParsedFile.file_id` this requirement was read from. |
| `filename` | string | Source PDF filename (mirror of the map). |
| `page` | integer | 1-indexed source page the `verbatim_text` is locatable on. |
| `verbatim_text` | string | **A real contiguous span copied from the cited page.** This is what grounds — it must be a substring of the page's parsed text after NFKC + de-hyphenation + whitespace-collapse normalization. Never paraphrased. May be trimmed to avoid table-column interleaving (see review-note.md). |
| `atomic_obligation` | string | The single-duty rewrite of the obligation (display/analysis text). **Not** required to verbatim-match — it is the atomic-granularity view. |
| `binding_keyword` | string | `shall` \| `must` \| `will` \| `should` \| `shall not` \| `none`. The obligation's binding force. |
| `req_type` | string | `instruction` (Section L) \| `evaluation` (Section M) \| `sow_pws` (Section C / PWS annex) \| `special_requirements` \| `clause` \| `attachment` \| `other`. Mirrors `RequirementDraft.type_guess`. |
| `parent_id` | string \| null | For atomic siblings split from one compound source statement: the `requirement_id` of the first sibling (which carries `parent_id: null`). Standalone requirements are `null`. |
| `provenance_pass` | string | `A` = drafted in the first (draft) pass; `B` = added during the adversarial reconciliation pass (a pass-A miss). Recorded for audit; the eval matcher ignores it. |

## Two-field design (why `verbatim_text` ≠ `atomic_obligation`)

The locked decisions require **atomic** granularity *and* **string-match-verified**
grounding. A compound sentence — e.g. *"Offeror shall insert its company name … in
Block #17A, acknowledge all amendments in Block #28 … signature in Block #30B …"* —
becomes several atomic rows. All siblings share **one** real `verbatim_text` span
(so grounding still passes), while each carries its own `atomic_obligation`. The
`parent_id` links siblings back to the source statement.

**Splitting rule (applied in the draft):** split on (a) coordinated noun-phrase
enumerations under one verb, (b) coordinated verb phrases sharing a subject, and
(c) lettered/numbered sub-lists. Do **not** split conditional clauses or temporal
qualifiers (e.g. *"until time of award, during performance and through final
payment"* stays one row).

**Interleave exception:** where a source page's three-column PWS table layout
interleaves a title-column word into the prose stream (breaking contiguity), the
affected atomic rows carry distinct — but still real and contiguous — spans instead
of one shared span. These cases are enumerated in `review-note.md`.

## Locatability check

`check_golden.py` (and `tests/eval/test_golden_verbatim.py`) load this file plus the
primary package's document map and assert every `verbatim_text` normalizes to a
substring of its cited page. The check skips when the gitignored corpus/artifact is
absent (CI). The golden set is only committed after this passes.
