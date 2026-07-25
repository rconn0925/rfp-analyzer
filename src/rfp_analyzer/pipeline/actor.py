"""Who owes the duty: the offeror, or the Government?

The signal that makes L<->M cross-mapping work. Typing a requirement by the
section it sits in is wrong in practice, because FAR solicitations routinely put
*submittal instructions* inside Section M under headings like "(i) Solicitation
Submittal Requirements" — and N4008526R0033 does exactly that, delegating
Section L's content to M wholesale. Bucketing by section then files real offeror
duties on the evaluation side, and cross-mapping reports them as "scored but
never instructed" gaps that do not exist.

Actor is the durable distinction the section label only approximates:

- **offeror** — a duty the bidder must discharge. Belongs on the L side however
  it is filed. "The Offeror shall submit a narrative response…"
- **government** — an action the Government takes to evaluate or administer.
  Belongs on the M side. "The Government will evaluate the feasibility of…"

Deterministic regex over the verbatim span: no engine, no judgment, so the
classification is reproducible and reviewable. Government patterns are checked
first because they are the more distinctive voice; anything with an offeror duty
and no Government subject falls to ``offeror``; the rest is ``other`` (a
statement of fact, definition, or page-limit note that obliges nobody).
"""

from __future__ import annotations

import re
from typing import Literal

Actor = Literal["offeror", "government", "other"]

_GOVERNMENT = re.compile(
    r"\b("
    r"the Government (?:will|shall|may|reserves|intends|is seeking|considers)"
    r"|the Government's inability"
    r"|the (?:evaluation )?board will"
    r"|the Contracting Officer (?:will|shall|may) (?:evaluate|consider|determine)"
    r"|award will be made"
    r"|will (?:be )?(?:evaluated|considered|assigned|rated)"
    r"|(?:may|shall|will) be (?:rated|considered|evaluated|assigned|deemed)"
    r"|will not be (?:considered|evaluated|eligible)"
    r"|is evaluated"
    r"|the evaluation (?:report|will|focuses)"
    r"|a deficiency will be assigned"
    r"|shall be evaluated"
    r")",
    re.IGNORECASE,
)

_OFFEROR = re.compile(
    r"\b("
    r"(?:the )?(?:offeror|offerors|contractor|contractors|bidder)s?'?\s+"
    r"(?:is|are|shall|must|will|should|may|personnel)"
    r"|(?:offeror|contractor)s? (?:shall|must|will|should)"
    r"|your (?:narrative|proposal|schedule|summary|plan)"
    r"|the proposal shall"
    r"|shall be submitted"
    r"|must be submitted"
    r"|shall submit"
    r"|must submit"
    r"|shall provide"
    r"|shall include"
    r"|shall be provided"
    r"|shall not be submitted"
    r"|^(?:submit|provide|include|describe|ensure|state|complete|obtain|maintain)\b"
    r")",
    re.IGNORECASE,
)


def classify_actor(text: str) -> Actor:
    """Return who the obligation in ``text`` falls on.

    When both voices appear, the one in the MAIN clause wins, approximated by
    whichever matches earliest. Solicitation sentences lead with the duty and
    trail the consequence, so "All questions must be submitted at least 10 days
    before proposals are due, **or the Government may not respond**" is an
    offeror duty with a Government consequence attached — not an evaluation
    criterion. A blanket "Government wins" rule mistyped exactly these rows and
    pushed real instructions onto the M side of the cross-map.
    """
    gov = _GOVERNMENT.search(text)
    off = _OFFEROR.search(text)
    if gov and off:
        return "government" if gov.start() < off.start() else "offeror"
    if gov:
        return "government"
    if off:
        return "offeror"
    return "other"
