# Test Corpus Manifest

Three real federal solicitation packages downloaded from SAM.gov (2026-07-23) per D-01/D-02.
Binaries are **local-only** (gitignored); this manifest and `manifest.json` are the only tracked
files under `tests/corpus/`. To reconstruct the corpus, download the files from the notice URLs
below and verify against the sha256 checksums.

All packages are public SAM.gov contract-opportunity data. Downloads used SAM.gov's public
keyless attachment endpoints (`/api/prod/opps/v3/opportunities/resources/files/{id}/download`).

---

## 1. primary-ucf — PRIMARY (clean full-UCF, Phase 2 golden set)

- **SAM.gov notice:** https://sam.gov/opp/e333dd6c76ca4f4d9b52bed3ea8f305e/view
- **Solicitation number:** N4008526R0033
- **Notice type:** Solicitation (RFP)
- **Agency:** DoD / Department of the Navy / NAVFAC
- **Title:** MCAS Beaufort and Laurel Bay Base Operation Support (services)
- **Role:** `primary` — expected classification `partial_ucf`
  (initially hypothesized `full_ucf`; page-1 inspection during plan 01-06 verified the base
  solicitation is an SF1449 — "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND
  COMMERCIAL SERVICES" — carrying a complete UCF A–M section structure. Per the Open
  Question 1 rule, a commercial-form signal alongside UCF letter sections classifies
  `partial_ucf` with a "verify package format" warning — the honest answer for this hybrid.)
- **Selection rationale:** Rare current DoD services RFP with real attachments hosted on SAM.gov
  (most current DoD notices are PIEE-link-only). Full UCF structure with verified extractable
  "SECTION L" and "SECTION M" headings in the base solicitation; **two** SF30 amendments (both
  contain "AMENDMENT OF SOLICITATION" marker text); Section C/F annex attachments; 290 pages
  total — inside the 100–300 page target. The notice carries ~27 additional J-series exhibits
  that were deliberately not downloaded to stay inside the page budget. This package becomes
  Phase 2's hand-shredded golden set.

| File | sha256 | Size (bytes) | Pages |
|------|--------|--------------|-------|
| Cover Letter.pdf | 8f401c9c9bf556dd8c2c8d78d22b5ac534d6854a08abb7d77b31fb09b72d8f54 | 105,765 | 2 |
| N4008526R0033 Section C Annexes.pdf | d360f634d987f8b5b0d8e8ff094f66a69f40ee8f6f9a024d5da8e290808b7675 | 1,323,790 | 161 |
| N4008526R0033 SECTION F ANNEX.pdf | f4524e75003b1b49318ee2bdd331e020723646682c77815d8317becf5240f18d | 339,565 | 18 |
| Solicitation - N4008526R0033.pdf | 475828d11085d63340939fba10fd94f881f0de717d9d10a32f40c9dd523a21de | 2,034,006 | 70 |
| Solicitation Amendment N4008526R00330001 SF 30.pdf | 0ae96ace946cb1a3cc2f958bc64a218e17b4f214da66db7f7b2308ec5b9704bb | 590,607 | 5 |
| Solicitation Amendment N4008526R00330002 SF 30.pdf | 406c911e7d3777e1bb25e5a83bcb8bc1a3925125cb3ce197b9b1ae9d30569fe0 | 639,115 | 17 |
| Solicitation N4008526R0033 Amendment 0002.pdf | 5aa82301df5e2d8859f09e97acee118eabb5c7485a8bf33acf20e7ba386eb551 | 252,123 | 17 |

**Package total:** 7 files, 290 pages.

---

## 2. hostile-scanned — HOSTILE (scanned/image-only pages)

- **SAM.gov notice:** https://sam.gov/opp/1d4a11931e894dcabb313e0aa9d1a44a/view
- **Solicitation number:** W9127N26BA016
- **Notice type:** Solicitation (construction IFB, SF1442-based, 2 modifications)
- **Agency:** DoD / Department of the Army / USACE Portland District
- **Title:** Miller-Rice Islands Pile Dike System Repairs
- **Role:** `hostile` — expected classification `unknown` (SF1442 construction package:
  no UCF Section L/M structure, not FAR Part 12 commercial — the honest degradation case)
- **Selection rationale:** The Project Manual (Specifications) contains verified image-only
  scanned pages: pages 2–3 return empty `extract_text()` while carrying 36 raster images each.
  The Planset adds a second hostility mode — CID-garbage text extraction ("(cid:0)(cid:2)…",
  broken font maps). Found after probing ~14 candidate scanned-SF30 files across 3 search
  pools (all DHA/VA/IHS SF30 amendments tested had clean text layers). Exercises the scanned
  and gibberish page-quality gates plus honest package classification.

| File | sha256 | Size (bytes) | Pages |
|------|--------|--------------|-------|
| Bid Abstract - W9127N26BA016_KO APPROVED 20260723.pdf | 1b2b805f691cb69367d76b5d966273098a8610c75108622be1573db53af409f6 | 341,195 | 2 |
| W9127N26BA016 Miller-Rice Islands Pile Dike System Repairs_Planset.pdf | ce68a44be4280b66d7dd20d1d53facff6dcb95b7d6d73a8edd3a0c28f3d98c46 | 6,347,247 | 36 |
| W9127N26BA016 Miller-Rice Islands Pile Dike System Repairs_Specifications.pdf | 749cd9a6424c092f3456d9a9bc7549a0eddf1a8f0d08e7d19a7cef41ee6a3b80 | 13,001,662 | 370 |

**Package total:** 3 files, 408 pages.

---

## 3. non-ucf-part12 — NON-UCF (FAR Part 12 combined synopsis/solicitation)

- **SAM.gov notice:** https://sam.gov/opp/98e9dffa4ce54668b93210d9e7c80709/view
- **Solicitation number:** FA441826Q0079
- **Notice type:** Combined Synopsis/Solicitation (search JSON type code `k`)
- **Agency:** DoD / Department of the Air Force / Air Mobility Command (JB Charleston)
- **Title:** FY26 841st Dock Fender Repair
- **Role:** `non_ucf` — expected classification `non_ucf_commercial`
- **Selection rationale:** Exact FAR 12.603 honest-degradation specimen: SF1449-based
  ("STANDARD FORM 1449" marker verified on the solicitation document), Combined
  Synopsis/Solicitation notice type confirmed from the SAM.gov search JSON. Small
  (35 pages), fully text-extractable, with SOW and wage-determination attachments.

| File | sha256 | Size (bytes) | Pages |
|------|--------|--------------|-------|
| Attachment 01. Statement of Work.pdf | d4f7dc5549ba33ddf9fe05dc89b9a90a027892ea81b5f3c20f79a514624562d6 | 556,550 | 4 |
| Attachment 02. JB CHS Form 111 Contractor Access Worksheet.pdf | 0226fffa8ffbcd7b907ab6f3fdc1e061d0bfa3a6851b6ad6766c73e7c2e1ee85 | 415,493 | 1 |
| Attachment 03. SCA Wage Determinations 15-4427.pdf | 8f29b17c0c5117c7012739f409ccc2a3ff0449237619bdc4e828dbd95c6e0d8e | 70,837 | 15 |
| Solicitation - FA441826Q0079.pdf | 05f06a998d5071c4e677bd3fb501138b0d32238cfffde9b528e3f4ff59171d3c | 508,104 | 15 |

**Package total:** 4 files, 35 pages.
