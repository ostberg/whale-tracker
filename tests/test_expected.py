"""The reminder calendar (W-033, W-055): periods, due windows, the plan, the rounds and the deep-dive gate."""

from datetime import date

from whales import config, expected

TODAY = date(2026, 11, 12)


def test_period_ends_follow_the_cadence():
    assert expected.period_ends("quarterly", date(2026, 1, 1), date(2026, 10, 20)) == [
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2026, 9, 30),
    ]
    assert expected.period_ends("semiannual", date(2025, 12, 31), date(2026, 12, 31)) == [
        date(2026, 6, 30),
        date(2026, 12, 31),
    ]
    assert expected.period_ends("annual", date(2024, 6, 1), date(2026, 3, 1)) == [
        date(2024, 12, 31),
        date(2025, 12, 31),
    ]
    assert expected.period_ends("monthly", date(2026, 1, 31), date(2026, 3, 31)) == [
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]
    assert expected.period_ends("irregular", date(2020, 1, 1), date(2026, 1, 1)) == []


def test_due_window_uses_the_sources_own_lag_else_the_default():
    q = date(2026, 9, 30)
    assert expected.due_window("quarterly", q, []) == (date(2026, 10, 21), date(2026, 12, 14))
    assert expected.due_window("annual", date(2025, 12, 31), []) == (date(2026, 1, 30), date(2026, 3, 31))
    # past lags of 40, 50 and 45 days: median 45, window 31 to 66 days after the period end
    assert expected.due_window("quarterly", q, [40, 50, 45]) == (date(2026, 10, 31), date(2026, 12, 5))
    # a very short lag still waits a week
    assert expected.due_window("monthly", q, [3]) == (date(2026, 10, 7), date(2026, 10, 24))


def _source(slug, cadence, mode="manual", active=True):
    return config.Source(
        slug,
        "m1",
        slug,
        "https://x.test",
        1,
        mode,
        cadence,
        False,
        False,
        True,
        "test",
        None,
        "o",
        TODAY,
        active,
    )


def _cfg(*sources):
    return config.Config((), (), (), tuple(sources), "t", TODAY)


def test_plan_covers_manual_calendar_sources_only_and_skips_what_exists():
    cfg = _cfg(
        _source("q", "quarterly"),
        _source("a", "annual"),
        _source("auto", "quarterly", mode="auto"),
        _source("irr", "irregular"),
        _source("off", "quarterly", active=False),
    )
    todo = expected.plan(cfg, TODAY, {("q", date(2026, 9, 30))}, {"a": [60]})
    assert [(s, e) for s, e, _, _ in todo] == [
        ("q", date(2025, 12, 31)),
        ("q", date(2026, 3, 31)),
        ("q", date(2026, 6, 30)),
        ("a", date(2025, 12, 31)),
    ]
    annual = next(t for t in todo if t[0] == "a")
    assert annual[2:] == (date(2026, 2, 15), date(2026, 3, 22))


def test_rounds_open_six_and_ten_weeks_after_the_quarter_for_a_week():
    assert expected.last_quarter_end(date(2026, 11, 12)) == date(2026, 9, 30)
    assert expected.last_quarter_end(date(2026, 2, 1)) == date(2025, 12, 31)
    r1 = expected.current_round(date(2026, 11, 11))
    assert (r1.number, r1.quarter_end, r1.opened_on) == (1, date(2026, 9, 30), date(2026, 11, 11))
    assert expected.current_round(date(2026, 11, 17)).number == 1
    assert expected.current_round(date(2026, 11, 18)) is None
    assert expected.current_round(date(2026, 12, 9)).number == 2
    assert expected.current_round(date(2026, 12, 16)) is None
    assert expected.current_round(date(2026, 10, 20)) is None


def test_deep_dive_waits_for_the_round_to_close_or_most_letters_to_arrive():
    q = date(2026, 9, 30)
    assert not expected.ready_for_deep_dive(date(2026, 11, 1), q, loaded=10, awaiting=0)  # before round 1
    assert not expected.ready_for_deep_dive(date(2026, 11, 20), q, loaded=5, awaiting=5)
    assert expected.ready_for_deep_dive(date(2026, 11, 20), q, loaded=8, awaiting=2)  # 80 per cent in
    assert expected.ready_for_deep_dive(date(2026, 12, 16), q, loaded=1, awaiting=9)  # round 2 closed
    assert not expected.ready_for_deep_dive(date(2026, 11, 20), q, loaded=0, awaiting=0)


def test_round_renders_one_line_per_letter():
    e = expected.Expectation(
        1,
        "ps",
        "Pershing Square letters",
        "Pershing Square",
        "quarterly",
        date(2026, 9, 30),
        date(2026, 10, 21),
        date(2026, 12, 14),
        "awaiting",
        1,
    )
    rnd = expected.Round(2, date(2026, 9, 30), date(2026, 12, 9), [e])
    text = expected.render_round(rnd)
    assert text.splitlines() == [
        "Collection round 2 for Q3 2026: 1 letters to drop in the inbox",
        "   - Pershing Square: Pershing Square letters, period to 2026-09-30 "
        "(expected by 2026-12-14, asked 1 time(s) before)",
    ]
    assert expected.render_round(expected.Round(1, date(2026, 9, 30), date(2026, 11, 11))).endswith(
        "nothing outstanding."
    )
