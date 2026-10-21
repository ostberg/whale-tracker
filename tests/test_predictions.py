"""The prediction contract (W-048) on the owner's two examples, and what it refuses."""

import copy
from datetime import date
from decimal import Decimal

import pytest

from whales import predictions
from whales.db import migrate

PUBLISHED = date(2026, 10, 1)
TOPICS = {"oil", "ai", "interest-rates"}

# "Iran will hold out until after the midterm elections and then broker a peace deal which will cause brent
# oil prices to drop to below $100 by the end of the year."
IRAN = {
    "predictions": [
        {
            "k": 1,
            "role": "asserted",
            "subject": "US-Iran peace deal",
            "metric": "event",
            "ticker": None,
            "topic": None,
            "comparator": "happens",
            "threshold": None,
            "unit": None,
            "relative_to": None,
            "window_from": "2026-11-04",
            "window_to": "2026-12-31",
            "timing": "any_time",
            "horizon_text": "after the midterm elections, by the end of the year",
            "confidence_wording": "will",
            "confidence": "high",
            "basis": "assertion",
            "basis_note": None,
            "claim": "Iran brokers a peace deal after the November 2026 midterm elections.",
            "quote": "Iran will hold out until after the midterm elections and then broker a peace deal",
            "page": 2,
            "premises": [],
            "caused_by": [],
        },
        {
            "k": 2,
            "role": "asserted",
            "subject": "Brent crude",
            "metric": "commodity_price",
            "ticker": None,
            "topic": "oil",
            "comparator": "below",
            "threshold": 100,
            "unit": "USD/bbl",
            "relative_to": None,
            "window_from": None,
            "window_to": "2026-12-31",
            "timing": "any_time",
            "horizon_text": "by the end of the year",
            "confidence_wording": "will",
            "confidence": "high",
            "basis": "reasoning",
            "basis_note": "rests on the peace-deal call; no supply or demand numbers shown",
            "claim": "Brent crude trades below $100 a barrel before the end of 2026.",
            "quote": "cause brent oil prices to drop to below $100 by the end of the year",
            "page": 2,
            "premises": [],
            "caused_by": [1],
        },
    ]
}

# "If MSFT capex rises by over 30% next year, investors will punish the shares and cause the multiple to
# compress to 18x."
MSFT = {
    "predictions": [
        {
            "k": 1,
            "role": "premise",
            "subject": "MSFT capex growth",
            "metric": "capex",
            "ticker": "MSFT",
            "topic": "ai",
            "comparator": "above",
            "threshold": 30,
            "unit": "% y/y",
            "relative_to": None,
            "window_from": "2027-01-01",
            "window_to": "2027-12-31",
            "timing": "at_end",
            "horizon_text": "next year",
            "confidence_wording": None,
            "confidence": "medium",
            "basis": "assertion",
            "basis_note": None,
            "claim": "Microsoft's capital spending grows more than 30% in 2027.",
            "quote": "If MSFT capex rises by over 30% next year",
            "page": None,
            "premises": [],
            "caused_by": [],
        },
        {
            "k": 2,
            "role": "asserted",
            "subject": "MSFT share price",
            "metric": "price",
            "ticker": "MSFT",
            "topic": None,
            "comparator": "down",
            "threshold": None,
            "unit": None,
            "relative_to": None,
            "window_from": "2027-01-01",
            "window_to": "2027-12-31",
            "timing": "any_time",
            "horizon_text": "next year",
            "confidence_wording": "will",
            "confidence": "high",
            "basis": "reasoning",
            "basis_note": "argues that investors punish capex growth; no numbers shown",
            "claim": "Microsoft shares fall.",
            "quote": "investors will punish the shares",
            "page": None,
            "premises": [1],
            "caused_by": [],
        },
        {
            "k": 3,
            "role": "asserted",
            "subject": "MSFT forward P/E",
            "metric": "valuation_multiple",
            "ticker": "MSFT",
            "topic": None,
            "comparator": "at_most",
            "threshold": 18,
            "unit": "x",
            "relative_to": None,
            "window_from": "2027-01-01",
            "window_to": "2027-12-31",
            "timing": "any_time",
            "horizon_text": "next year",
            "confidence_wording": "will",
            "confidence": "high",
            "basis": "reasoning",
            "basis_note": None,
            "claim": "Microsoft's earnings multiple compresses to 18 times or less.",
            "quote": "cause the multiple to compress to 18x",
            "page": None,
            "premises": [1],
            "caused_by": [2],
        },
    ]
}


def test_iran_example_parses_to_two_claims_and_one_causal_link():
    x = predictions.parse(IRAN, PUBLISHED, TOPICS)
    assert [c.k for c in x.claims] == [1, 2]
    deal, brent = x.claims
    assert (deal.metric, deal.comparator, deal.window_from, deal.window_to) == (
        "event",
        "happens",
        date(2026, 11, 4),
        date(2026, 12, 31),
    )
    assert (brent.subject, brent.comparator, brent.threshold, brent.unit) == (
        "Brent crude",
        "below",
        Decimal("100"),
        "USD/bbl",
    )
    assert brent.topic == "oil" and brent.window_to == date(2026, 12, 31)
    assert (deal.basis, deal.basis_note, deal.confidence) == ("assertion", None, "high")
    assert brent.basis == "reasoning" and brent.basis_note.startswith("rests on the peace-deal call")
    assert x.links == [predictions.Link(1, 2, "causes")]
    assert x.notes == []


def test_msft_example_parses_to_a_premise_and_two_conditional_claims():
    x = predictions.parse(MSFT, PUBLISHED, TOPICS)
    assert [(c.k, c.role) for c in x.claims] == [(1, "premise"), (2, "asserted"), (3, "asserted")]
    assert x.claim(1).timing == "at_end" and x.claim(1).ticker == "MSFT"
    assert x.claim(3).threshold == Decimal("18") and x.claim(3).comparator == "at_most"
    assert set(x.links) == {
        predictions.Link(1, 2, "premise_of"),
        predictions.Link(1, 3, "premise_of"),
        predictions.Link(2, 3, "causes"),
    }


def test_unknown_topic_is_dropped_and_noted_not_refused():
    x = predictions.parse(IRAN, PUBLISHED, topics={"ai"})
    assert x.claim(2).topic is None
    assert x.notes == ["claim 2: topic 'oil' is not in the list; dropped"]


def test_ticker_is_upper_cased_and_text_is_normalised():
    payload = copy.deepcopy(MSFT)
    payload["predictions"][0]["ticker"] = "msft"
    payload["predictions"][0]["subject"] = "  MSFT   capex\ngrowth "
    x = predictions.parse(payload, PUBLISHED, TOPICS)
    assert x.claim(1).ticker == "MSFT" and x.claim(1).subject == "MSFT capex growth"


def _broken(example, which, **changes):
    payload = copy.deepcopy(example)
    item = next(p for p in payload["predictions"] if p["k"] == which)
    item.update(changes)
    return payload


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (_broken(IRAN, 2, threshold=None), "threshold is required"),
        (_broken(IRAN, 1, threshold=5), "not allowed otherwise"),
        (_broken(IRAN, 2, comparator="crashes"), "comparator must be one of"),
        (_broken(IRAN, 2, metric="oil"), "metric must be one of"),
        (_broken(IRAN, 2, role="guess"), "role must be one of"),
        (_broken(IRAN, 2, basis="vibes"), "basis must be one of"),
        (_broken(IRAN, 2, confidence="sure"), "confidence must be one of"),
        (_broken(IRAN, 2, basis=None), "basis must be one of"),
        (_broken(IRAN, 2, basis_note="x" * 301), "basis_note is longer than 300"),
        (_broken(IRAN, 2, threshold="a hundred"), "threshold must be a number"),
        (_broken(IRAN, 2, window_to="2026-09-30"), "before the letter's date"),
        (_broken(IRAN, 1, window_from="2027-01-01"), "window_to is before window_from"),
        (_broken(IRAN, 2, window_to="year-end"), "must be YYYY-MM-DD"),
        (_broken(IRAN, 2, window_to=None, timing="at_end"), "at_end needs a window_to"),
        (_broken(IRAN, 2, quote=""), "quote is required"),
        (_broken(IRAN, 2, subject=7), "subject must be text"),
        (_broken(IRAN, 2, page=0), "page must be a positive integer"),
        (_broken(IRAN, 2, k=1), "k 1 is used twice"),
        (_broken(IRAN, 2, k="2"), "k must be a positive integer"),
        (_broken(IRAN, 2, caused_by="1"), "must be a list of claim numbers"),
        (_broken(IRAN, 2, caused_by=[9]), "claim 9, which does not exist"),
        (_broken(IRAN, 2, caused_by=[2]), "refers to itself"),
        (_broken(IRAN, 2, premises=[1]), "claim 1 is asserted, but a premise_of link needs premise"),
        (_broken(MSFT, 2, caused_by=[1]), "claim 1 is premise, but a causes link needs asserted"),
    ],
)
def test_contract_refusals(payload, expected):
    with pytest.raises(predictions.ContractError) as info:
        predictions.parse(payload, PUBLISHED, TOPICS)
    assert any(expected in p for p in info.value.problems), info.value.problems


def test_an_over_long_quote_is_cut_not_refused():
    """The first Azure run lost a whole letter to one 400+ character quote (2026-10-21)."""
    x = predictions.parse(_broken(IRAN, 2, quote="word " * 120), PUBLISHED, TOPICS)
    assert len(x.claim(2).quote) == predictions.QUOTE_MAX and x.claim(2).quote.endswith("…")
    assert x.notes == ["claim 2: quote cut to 400 characters"]


def test_salvage_drops_the_bad_claim_and_its_links_not_the_letter():
    """Eight of 25 letters in the first Azure run failed on one or two claims each (2026-10-21)."""
    payload = _broken(MSFT, 2, comparator="crashes", confidence=None)
    x = predictions.parse(payload, PUBLISHED, TOPICS, salvage=True)
    assert [c.k for c in x.claims] == [1, 3]
    assert x.links == [predictions.Link(1, 3, "premise_of")]
    assert x.notes == [
        "claim 2: dropped (comparator must be one of ('up', 'down', 'above', 'below', 'at_least', "
        "'at_most', 'happens', 'does_not_happen'), got 'crashes'; confidence must be one of "
        "('high', 'medium', 'low'), got None)",
        "claim 3: causes link from claim 2 dropped (refers to claim 2, which was dropped)",
    ]


def test_salvage_drops_a_bad_link_and_then_an_unused_premise():
    payload = _broken(MSFT, 2, premises=[])
    payload = _broken(payload, 3, premises=[1], caused_by=[1])  # a causes link from a premise
    x = predictions.parse(payload, PUBLISHED, TOPICS, salvage=True)
    assert [c.k for c in x.claims] == [1, 2, 3] and len(x.links) == 1  # the premise_of link stays
    assert x.notes == [
        "claim 3: causes link from claim 1 dropped (claim 1 is premise, but a causes link needs asserted)"
    ]
    payload = _broken(payload, 3, premises=[])
    x = predictions.parse(payload, PUBLISHED, TOPICS, salvage=True)
    assert [c.k for c in x.claims] == [2, 3] and x.links == []
    assert x.notes[-1] == "claim 1: dropped (a premise must be the premise of some other claim)"


def test_salvage_breaks_a_cycle_and_still_refuses_an_unusable_payload():
    x = predictions.parse(_broken(IRAN, 1, caused_by=[2]), PUBLISHED, TOPICS, salvage=True)
    assert [c.k for c in x.claims] == [1, 2] and x.links == []
    assert all("depends on itself through the links" in n for n in x.notes) and len(x.notes) == 2
    x = predictions.parse({"predictions": [7, {"k": 0}]}, PUBLISHED, TOPICS, salvage=True)
    assert x.claims == [] and x.notes == [
        "predictions[0]: dropped (must be an object)",
        "predictions[1]: dropped (k must be a positive integer)",
    ]
    with pytest.raises(predictions.ContractError, match="'predictions' list"):
        predictions.parse({"claims": []}, PUBLISHED, TOPICS, salvage=True)


def test_an_unused_premise_is_refused():
    payload = _broken(MSFT, 2, premises=[])
    payload = _broken(payload, 3, premises=[])
    with pytest.raises(predictions.ContractError, match="a premise must be the premise of some other claim"):
        predictions.parse(payload, PUBLISHED, TOPICS)


def test_cycles_are_refused():
    payload = _broken(IRAN, 1, caused_by=[2])
    with pytest.raises(predictions.ContractError, match="depends on itself"):
        predictions.parse(payload, PUBLISHED, TOPICS)


def test_every_problem_is_reported_at_once():
    payload = _broken(IRAN, 2, comparator="crashes", quote="", page=-1)
    with pytest.raises(predictions.ContractError) as info:
        predictions.parse(payload, PUBLISHED, TOPICS)
    assert len(info.value.problems) >= 3


@pytest.mark.parametrize("payload", [None, [], {"predictions": "none"}, {"claims": []}])
def test_payload_shape_is_checked(payload):
    with pytest.raises(predictions.ContractError, match="'predictions' list"):
        predictions.parse(payload, PUBLISHED, TOPICS)


def test_vocabularies_match_migration_0002():
    sql = next(m.sql for m in migrate.discover() if m.version == 2)
    vocabularies = (
        predictions.METRICS
        + predictions.COMPARATORS
        + predictions.TIMINGS
        + predictions.ROLES
        + predictions.BASES
        + predictions.CONFIDENCES
    )
    for code in vocabularies:
        assert f"'{code}'" in sql, code
    assert set(predictions.CHECK_METHOD) == set(predictions.METRICS)
    assert set(predictions.CHECK_METHOD.values()) <= {"data", "price", "filing", "model"}


class _FakeConn:
    """Records SQL; hands out ids; knows the MSFT ticker only."""

    def __init__(self):
        self.calls = []
        self.next_id = 100

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith("INSERT INTO letters.prediction ("):
            self.next_id += 1
            ticker = params[5]
            return _Row((self.next_id, 7 if ticker == "MSFT" else None))
        return _Row(None)


class _Row:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


def test_store_writes_claims_then_links_by_id():
    x = predictions.parse(MSFT, PUBLISHED, TOPICS)
    conn = _FakeConn()
    ids = predictions.store(conn, run_id=42, extraction=x)
    assert ids == {1: 101, 2: 102, 3: 103}
    links = [p for sql, p in conn.calls if sql.startswith("INSERT INTO letters.prediction_link")]
    assert (42, 101, "premise", 102, "premise_of") in links
    assert (42, 102, "asserted", 103, "causes") in links
    assert len(links) == 3
    assert x.notes == []


def test_store_notes_an_unknown_ticker_instead_of_guessing():
    payload = _broken(MSFT, 2, ticker="MSFTX")
    x = predictions.parse(payload, PUBLISHED, TOPICS)
    conn = _FakeConn()
    predictions.store(conn, run_id=1, extraction=x)
    assert x.notes == ["claim 2: ticker MSFTX is not in core.security; left unlinked"]


def test_claim_params_order_matches_insert_columns():
    x = predictions.parse(IRAN, PUBLISHED, TOPICS)
    params = predictions.claim_params(9, x.claim(2))
    assert params[:5] == (9, 2, "asserted", "Brent crude", "commodity_price")
    assert params[5:7] == (None, "oil")
    assert predictions.INSERT_CLAIM.count("%s") == len(params)
