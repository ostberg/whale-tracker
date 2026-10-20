"""The reminder calendar (W-033, W-055): what each manual source owes, when it is due, and the two
collection rounds a quarter that ask for it.

``whales expected refresh`` creates one ``letters.expected`` row per manual source and period that has
ended (quarterly, semiannual, annual or monthly; irregular sources have no calendar), with a due window
from the source's own past publication lag, or a default when it has no history. It then marks an
expectation loaded when a document for that period exists, from any route, so a letter the automatic
route or the inbox already caught is never asked for. Nobody is asked one letter at a time: the weekly
digest carries one checklist in round 1 (about week 6 after quarter-end) and one for the leftovers in
round 2 (about week 10). Deeper reports wait for a round to close (``ready_for_deep_dive``).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import Config
from .db.connect import Database

CALENDAR = {"quarterly": 3, "semiannual": 6, "annual": 12, "monthly": 1}  # months per period
DEFAULT_WINDOW = {"quarterly": (21, 75), "semiannual": (21, 75), "annual": (30, 90), "monthly": (7, 30)}
EXPECTED_KIND = {
    "quarterly": "quarterly_letter",
    "semiannual": "quarterly_letter",
    "annual": "annual_letter",
    "monthly": "commentary",
}
HISTORY_DAYS = 400  # periods older than this are not expected retroactively
ROUND_1 = 42  # days after quarter-end
ROUND_2 = 70
ROUND_SPAN = 7  # the digest shows a round for this many days
READY_SHARE = 0.8  # a deep dive may run once this share of the quarter's expected letters is loaded


@dataclass(frozen=True)
class Expectation:
    id: int
    source: str
    source_name: str
    manager_name: str
    cadence: str
    period_end: date
    due_from: date
    due_to: date
    status: str
    reminders: int


@dataclass(frozen=True)
class Round:
    number: int
    quarter_end: date
    opened_on: date
    items: list[Expectation] = field(default_factory=list)


# --- the calendar ---------------------------------------------------------------------------------------


def month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def period_ends(cadence: str, since: date, until: date) -> list[date]:
    """The period ends of a cadence that fall in (since, until]. Irregular sources have none."""
    months = CALENDAR.get(cadence)
    if not months:
        return []
    out = []
    year, month = since.year, since.month
    while True:
        end = month_end(year, month)
        if end > until:
            break
        if end > since and month % months == 0:
            out.append(end)
        year, month = (year + (month == 12), month % 12 + 1)
    return out


def due_window(cadence: str, period_end: date, lags: list[int]) -> tuple[date, date]:
    """When the letter is due: from the source's past lags (median, with a fortnight before and three weeks
    after), else the cadence's default."""
    if lags:
        lag = int(statistics.median(lags))
        start, stop = max(7, lag - 14), lag + 21
    else:
        start, stop = DEFAULT_WINDOW[cadence]
    return period_end + timedelta(days=start), period_end + timedelta(days=stop)


def plan(
    cfg: Config, today: date, existing: set[tuple[str, date]], lags: dict[str, list[int]]
) -> list[tuple[str, date, date, date]]:
    """(source slug, period end, due from, due to) for every expectation not yet in the database: active
    manual sources with a calendar cadence, periods ended within HISTORY_DAYS."""
    out = []
    since = today - timedelta(days=HISTORY_DAYS)
    for s in cfg.sources:
        if not (s.active and s.mode == "manual" and s.cadence in CALENDAR):
            continue
        for end in period_ends(s.cadence, since, today):
            if (s.slug, end) in existing:
                continue
            due_from, due_to = due_window(s.cadence, end, lags.get(s.slug, []))
            out.append((s.slug, end, due_from, due_to))
    return out


# --- rounds and the deep-dive gate -----------------------------------------------------------------------


def last_quarter_end(today: date) -> date:
    q = (today.month - 1) // 3  # quarters already ended this year
    if q == 0:
        return date(today.year - 1, 12, 31)
    return month_end(today.year, 3 * q)


def current_round(today: date) -> Round | None:
    """Round 1 opens ROUND_1 days after the last quarter-end, round 2 ROUND_2 days after; each is shown for
    ROUND_SPAN days. Outside those windows there is no round."""
    q = last_quarter_end(today)
    for number, offset in ((1, ROUND_1), (2, ROUND_2)):
        opened = q + timedelta(days=offset)
        if opened <= today < opened + timedelta(days=ROUND_SPAN):
            return Round(number, q, opened)
    return None


def ready_for_deep_dive(today: date, quarter_end: date, loaded: int, awaiting: int) -> bool:
    """W-055: after round 2 has closed, or once READY_SHARE of the quarter's expected letters are loaded;
    never before round 1 opens."""
    if today < quarter_end + timedelta(days=ROUND_1):
        return False
    if today >= quarter_end + timedelta(days=ROUND_2 + ROUND_SPAN):
        return True
    total = loaded + awaiting
    return total > 0 and loaded / total >= READY_SHARE


def render_round(rnd: Round) -> str:
    q = rnd.quarter_end
    label = f"Q{(q.month - 1) // 3 + 1} {q.year}"
    if not rnd.items:
        return f"Collection round {rnd.number} for {label}: nothing outstanding."
    lines = [f"Collection round {rnd.number} for {label}: {len(rnd.items)} letters to drop in the inbox"]
    for e in rnd.items:
        period = (
            e.period_end.isoformat() if e.cadence == "monthly" else f"period to {e.period_end.isoformat()}"
        )
        asked = f", asked {e.reminders} time(s) before" if e.reminders else ""
        lines.append(
            f"   - {e.manager_name}: {e.source_name}, {period} (expected by {e.due_to.isoformat()}{asked})"
        )
    return "\n".join(lines)


# --- the database ---------------------------------------------------------------------------------------

EXPECTED_SQL = (
    "SELECT e.id, s.slug, s.name, m.name, s.cadence, e.period_end, e.due_from, e.due_to, e.status, "
    "e.reminders FROM letters.expected e JOIN letters.source s ON s.id = e.source_id "
    "JOIN core.manager m ON m.id = s.manager_id"
)
LAGS_SQL = (
    "SELECT s.slug, d.published_on - d.period_end FROM letters.document d "
    "JOIN letters.document_file f ON f.document_id = d.id JOIN letters.source s ON s.id = f.source_id "
    "WHERE d.period_end IS NOT NULL AND d.published_on_basis <> 'first_seen' "
    "AND d.published_on > d.period_end"
)
INSERT_SQL = (
    "INSERT INTO letters.expected (source_id, period_end, due_from, due_to) "
    "VALUES ((SELECT id FROM letters.source WHERE slug = %s), %s, %s, %s)"
)
# A document for the period from the same source, or from any of the manager's sources when its kind is the
# one the cadence expects: the automatic route and the inbox satisfy a manual expectation too.
MARK_LOADED_SQL = """
UPDATE letters.expected e SET status = 'loaded', document_id = d.id
FROM letters.source s, letters.document d
WHERE e.source_id = s.id AND e.status = 'awaiting' AND d.period_end = e.period_end
  AND (EXISTS (SELECT 1 FROM letters.document_file f WHERE f.document_id = d.id AND f.source_id = s.id)
       OR (d.manager_id = s.manager_id AND d.kind = CASE s.cadence
               WHEN 'annual' THEN 'annual_letter' WHEN 'monthly' THEN 'commentary'
               ELSE 'quarterly_letter' END))
"""
ROUND_ITEMS_SQL = (
    EXPECTED_SQL + " WHERE e.status = 'awaiting' AND e.due_from <= %s AND e.period_end <= %s "
    "ORDER BY e.period_end, m.name, s.name"
)
QUARTER_COUNTS_SQL = (
    "SELECT count(*) FILTER (WHERE status = 'loaded'), count(*) FILTER (WHERE status = 'awaiting') "
    "FROM letters.expected WHERE period_end > %s AND period_end <= %s"
)


def expectations(db: Database, where: str = "", params: tuple = ()) -> list[Expectation]:
    return [Expectation(*r) for r in db.run(EXPECTED_SQL + where, params)]


def refresh(db: Database, cfg: Config, today: date, *, apply: bool) -> tuple[list[tuple], int]:
    """Plan the missing expectations and, with apply, insert them and mark the loaded ones. Returns the
    plan and how many were marked loaded (0 on a dry run)."""
    existing = {(e.source, e.period_end) for e in expectations(db)}
    lags: dict[str, list[int]] = {}
    for slug, lag in db.run(LAGS_SQL):
        lags.setdefault(slug, []).append(int(lag))
    todo = plan(cfg, today, existing, lags)
    if not apply:
        return todo, 0
    conn = db.connection()
    with conn.transaction():
        for slug, end, due_from, due_to in todo:
            conn.execute(INSERT_SQL, (slug, end, due_from, due_to))
        loaded = conn.execute(MARK_LOADED_SQL).rowcount
    return todo, loaded


def round_for(db: Database, today: date) -> Round | None:
    rnd = current_round(today)
    if rnd is None:
        return None
    rows = db.run(ROUND_ITEMS_SQL, (today, rnd.quarter_end))
    return Round(rnd.number, rnd.quarter_end, rnd.opened_on, [Expectation(*r) for r in rows])


def mark_reminded(db: Database, rnd: Round) -> None:
    if rnd.items:
        db.run(
            "UPDATE letters.expected SET reminders = reminders + 1, last_reminded_at = now() "
            "WHERE id = ANY(%s)",
            ([e.id for e in rnd.items],),
        )


def quarter_ready(db: Database, today: date, quarter_end: date) -> bool:
    prev = quarter_end - timedelta(days=92)
    loaded, awaiting = db.run(QUARTER_COUNTS_SQL, (prev, quarter_end))[0]
    return ready_for_deep_dive(today, quarter_end, int(loaded), int(awaiting))
