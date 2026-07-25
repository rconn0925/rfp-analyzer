"""Analysis stage: an extracted RequirementSet becomes a judged compliance matrix.

Three steps, deliberately ordered cheapest-and-most-certain first:

- ``crossmap.py`` — deterministic L<->M<->C gap and orphan detection (ANLZ-01).
  No engine involved: gaps are found by comparing what was extracted, so the
  finding is reproducible and never hallucinated.
- ``outline.py`` — the proposal outline derived from Section L's own structure,
  and every requirement mapped to a node (ANLZ-02). Also deterministic.
- ``judge.py`` — graded compliance against a capabilities profile (ANLZ-04). The
  only step needing judgment, so the only one that goes through the Claude Code
  replay seam.

Keeping the first two engine-free means a matrix has real analytical value even
when no judgment has been run, and it keeps the expensive step small.
"""
