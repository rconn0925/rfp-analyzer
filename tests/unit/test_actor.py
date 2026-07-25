"""Actor classification — the signal that makes L<->M cross-mapping meaningful."""

from __future__ import annotations

import pytest

from rfp_analyzer.pipeline.actor import classify_actor


@pytest.mark.parametrize(
    "text",
    [
        "The Offeror shall submit a narrative response demonstrating its approach.",
        "The Contractor shall pay all costs associated with the partnering effort.",
        "Your narrative for this Factor shall be no more than 25 single-sided pages.",
        "All required proposal documents shall be submitted in accordance with FAR 15.107.",
        "Submit five (5) previous complete calendar years' worth of data.",
        "Offerors shall not incorporate by reference into their proposal PPQs or CPARS.",
    ],
)
def test_offeror_duties(text):
    assert classify_actor(text) == "offeror"


@pytest.mark.parametrize(
    "text",
    [
        "The Government will evaluate price based on the total price.",
        "The Government reserves the right to contact references for verification.",
        "Award will be made to the responsible Offeror whose offer conforms.",
        "Contracts submitted in excess of the maximum will not be considered.",
        "The Management Approach factor shall be evaluated based upon the following criteria.",
        "A Deficiency will be assigned to any Offeror that does not meet the minimum.",
    ],
)
def test_government_actions(text):
    assert classify_actor(text) == "government"


def test_main_clause_wins_over_trailing_consequence():
    """The bug this rule exists to fix: a duty with a Government consequence
    attached is still a duty, and typing it as evaluation pushed real
    instructions onto the M side of the cross-map."""
    text = (
        "All questions must be submitted at least 10 days before proposals are due, "
        "or the Government may not respond."
    )
    assert classify_actor(text) == "offeror"


def test_government_main_clause_still_wins_when_it_leads():
    """"The Government will evaluate the narrative the Offeror shall submit" is an
    evaluation criterion that merely references the duty."""
    text = (
        "The Government will evaluate the feasibility of the workforce management "
        "narrative the Offeror shall submit."
    )
    assert classify_actor(text) == "government"


@pytest.mark.parametrize(
    "text",
    [
        "Definitions and Acronyms are listed in J-0200000-01.",
        "The Government observes the following holidays: New Year's Day.",
        "",
    ],
)
def test_obligation_free_text_is_other(text):
    assert classify_actor(text) == "other"


def test_is_deterministic():
    text = "The Offeror shall submit one (1) copy via PIEE."
    assert classify_actor(text) == classify_actor(text)
