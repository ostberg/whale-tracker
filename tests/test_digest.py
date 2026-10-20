"""The weekly digest (W-054) on constructed rows: clusters, growth, disagreement, calls, cap, subject."""

from datetime import date

from whales.db import migrate
from whales.reports import digest

TODAY = date(2026, 11, 9)


def row(
    theme, manager, stance="positive", first=False, baseline="high", published=date(2026, 9, 30), quote=None
):
    return digest.ThemeRow(
        theme=theme,
        label=theme.split(":", 1)[1].title(),
        manager=manager,
        manager_name=manager.title(),
        baseline=baseline,
        stance=stance,
        first_mention=first,
        published_on=published,
        quote=quote or f"{manager} says something about {theme} worth quoting",
        title="Q3 letter",
    )


COPPER = [
    row("candidate:copper supply", "kopernik", first=True),
    row("candidate:copper supply", "crescat", first=True, quote="The copper deficit is now a 2027 story"),
    row("candidate:copper supply", "oaktree", stance="negative", published=date(2026, 5, 2)),
    row("candidate:copper supply", "kopernik", published=date(2026, 6, 30)),  # the same writer twice
]


def test_three_writers_make_a_convergence_item_with_first_mentions_and_stances():
    items = digest.convergence(COPPER, {}, 26)
    assert len(items) == 1
    item = items[0]
    assert item.kind == "convergence" and item.key == "candidate:copper supply" and item.writers == 3
    assert item.headline == (
        "Convergence: Copper Supply, 3 writers in 26 weeks, 2 for the first time; 3 positive, 1 negative"
    )
    assert "Crescat, Kopernik, Oaktree" in item.detail_line
    assert '"The copper deficit is now a 2027 story" (Crescat)' in item.detail_line
    assert item.score == 2 * 3 + 2 + 3


def test_two_writers_are_not_convergence():
    assert digest.convergence(COPPER[:2], {}, 26) == []


def test_a_reported_theme_returns_only_once_it_has_grown():
    assert digest.convergence(COPPER, {("convergence", "candidate:copper supply"): 3}, 26) == []
    assert digest.convergence(COPPER, {("convergence", "candidate:copper supply"): 2}, 26) == []
    grown = COPPER + [row("candidate:copper supply", "gmo"), row("candidate:copper supply", "smead")]
    items = digest.convergence(grown, {("convergence", "candidate:copper supply"): 3}, 26)
    assert len(items) == 1 and items[0].writers == 5 and "(up from 3)" in items[0].headline


def test_late_letters_join_the_cluster_whatever_their_arrival_order():
    """A May letter loaded in October counts by its publication date: the rows carry dates, not load order."""
    shuffled = [COPPER[3], COPPER[1], COPPER[2], COPPER[0]]
    assert digest.convergence(shuffled, {}, 26)[0].writers == 3


def test_disagreement_needs_credible_writers_on_both_sides():
    rows = [
        row("topic:private-credit", "apollo", "positive"),
        row("topic:private-credit", "brookfield", "positive", baseline="medium"),
        row("topic:private-credit", "oaktree", "negative"),
        row("topic:private-credit", "a-tweeter", "negative", baseline="low"),  # does not count
    ]
    items = digest.disagreement(rows, {})
    assert len(items) == 1
    assert items[0].headline == "Disagreement: Private-Credit, 2 positive, 1 negative"
    assert items[0].detail_line.startswith("For: Apollo, Brookfield. Against: Oaktree. ")
    assert items[0].score == 3 * 1 + 3 and items[0].writers == 3
    assert digest.disagreement(rows[:2], {}) == []
    assert digest.disagreement(rows, {("disagreement", "topic:private-credit"): 3}) == []


def _call(pid, state, proposed=None, outcome=None, confidence="high", reviewed=None):
    return digest.CallRow(
        pid,
        state,
        outcome,
        proposed,
        "92.1 USD/bbl on 2026-11-03" if proposed else None,
        "Brent crude",
        f"Claim {pid}",
        date(2026, 10, 31),
        confidence,
        reviewed,
        "greenlight",
        "Greenlight",
    )


def test_calls_due_is_one_item_and_each_confident_miss_its_own():
    rows = [
        _call(1, "due"),
        _call(2, "proposed", proposed="right"),
        _call(3, "due"),
        _call(4, "due"),
        _call(5, "scored", outcome="wrong", reviewed=date(2026, 11, 5)),
    ]
    items = digest.calls(rows, TODAY)
    assert [i.kind for i in items] == ["calls_due", "confident_miss"]
    due = items[0]
    assert due.headline == "Calls due: 4 for a verdict, 1 with a proposed outcome"
    assert "Greenlight: Claim 2 (proposed: right, 92.1 USD/bbl on 2026-11-03)" in due.detail_line
    assert due.detail_line.endswith("; and 1 more") and due.key == "week:2026-11-09"
    assert due.score == 2 + 4 + 2
    miss = items[1]
    assert (
        miss.headline == "Confident miss: Greenlight on Brent crude" and miss.key == "5" and miss.score == 5
    )


def test_choose_caps_at_four_and_never_repeats_a_miss_or_a_week():
    items = [digest.Item("convergence", f"t{i}", f"h{i}", "d", score=i) for i in range(6)]
    items += [
        digest.Item("confident_miss", "9", "miss", "d", score=5),
        digest.Item("calls_due", "week:x", "c", "d", 3),
    ]
    chosen, dropped = digest.choose(items, {("confident_miss", "9"): 1, ("calls_due", "week:x"): 0}, TODAY)
    assert [i.key for i in chosen] == ["t5", "t4", "t3", "t2"] and dropped == 2


def test_subject_says_when_there_is_nothing():
    assert digest.subject(TODAY, []) == "Whale Tracker, week of 2026-11-09: nothing to report"
    one = [digest.Item("convergence", "t", "h", "d", 1)]
    assert digest.subject(TODAY, one).endswith(": 1 item")
    assert digest.subject(TODAY, one * 3).endswith(": 3 items")
    assert digest.render([]).startswith("Nothing cleared the bar")


def test_render_is_two_lines_per_item():
    items = [
        digest.Item("convergence", "t", "Convergence: X", "A, B, C.", 1),
        digest.Item("calls_due", "w", "Calls due: 1", "x", 1),
    ]
    body = digest.render(items)
    assert body.splitlines() == ["1. Convergence: X", "   A, B, C.", "2. Calls due: 1", "   x"]


def test_migration_0003_matches_the_item_kinds():
    sql = next(m.sql for m in migrate.discover() if m.version == 3)
    for kind in ("convergence", "disagreement", "calls_due", "confident_miss"):
        assert f"'{kind}'" in sql
    assert "reports" in migrate.SCHEMAS
