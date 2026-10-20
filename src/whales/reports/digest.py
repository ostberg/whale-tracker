"""The weekly digest (W-054): ``whales digest``.

One Teams post a week, at most four items, and a subject line that says when there is nothing to report.
Three kinds of item: convergence (several writers on one theme within a rolling window, counted by
publication date, so a letter loaded late still joins the cluster it belongs to), disagreement (credible
writers on opposite sides of a theme) and calls due (claims whose window closed, with the proposed outcome,
plus any confident miss). Themes are the controlled topics and the model's candidate themes, grouped by
label. ``reports.digest_item`` remembers what was reported, so a theme returns only once it has grown.
Design and scoring: docs/REPORTS.md.
"""

from __future__ import annotations

import json
import platform
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .. import expected
from ..collect import _git_sha
from ..db.connect import Database

WINDOW_WEEKS = 26
MIN_WRITERS = 3  # a theme is convergence from this many distinct writers
GROWTH = 2  # a reported theme returns once it has this many more writers
MAX_ITEMS = 4
CREDIBLE = ("high", "medium")  # source-type baselines that count in a disagreement
QUOTE_CHARS = 140


@dataclass(frozen=True)
class ThemeRow:
    theme: str
    label: str
    manager: str
    manager_name: str
    baseline: str | None
    stance: str | None
    first_mention: bool
    published_on: date
    quote: str
    title: str


@dataclass(frozen=True)
class CallRow:
    prediction_id: int
    state: str
    outcome: str | None
    proposed_outcome: str | None
    observed: str | None
    subject: str
    claim: str
    window_to: date | None
    confidence: str
    reviewed_on: date | None
    manager: str
    manager_name: str


@dataclass
class Item:
    kind: str
    key: str
    headline: str
    detail_line: str
    score: float
    writers: int = 0
    detail: dict = field(default_factory=dict)


@dataclass
class Digest:
    issued_on: date
    subject: str
    body: str
    items: list[Item]
    dropped: int = 0
    collection: expected.Round | None = None  # the quarter's collection round, when one is open (W-055)


# --- reading -------------------------------------------------------------------------------------------

THEME_SQL = (
    "SELECT theme, label, manager, manager_name, baseline, stance, first_mention, published_on, quote, title "
    "FROM reports.theme_mention WHERE published_on >= %s ORDER BY published_on, document_id"
)
REPORTED_SQL = "SELECT kind, key, max(writers) FROM reports.digest_item GROUP BY kind, key"
CALLS_SQL = (
    "SELECT st.id, st.state, st.outcome, st.proposed_outcome, st.check_observed, st.subject, st.claim, "
    "st.window_to, st.confidence, st.reviewed_at::date, m.slug, m.name "
    "FROM letters.prediction_state st "
    "JOIN letters.extraction_run r ON r.id = st.extraction_run_id "
    "JOIN letters.document d ON d.id = r.document_id "
    "JOIN core.manager m ON m.id = d.manager_id "
    "WHERE st.role = 'asserted' AND (st.state IN ('due', 'proposed') "
    "OR (st.state = 'scored' AND st.outcome = 'wrong' AND st.confidence = 'high' AND st.reviewed_at >= %s)) "
    "ORDER BY st.window_to, st.id"
)


def theme_rows(db: Database, since: date) -> list[ThemeRow]:
    return [ThemeRow(*r) for r in db.run(THEME_SQL, (since,))]


def call_rows(db: Database, misses_since: date) -> list[CallRow]:
    return [CallRow(*r) for r in db.run(CALLS_SQL, (misses_since,))]


def reported(db: Database) -> dict[tuple[str, str], int]:
    """What earlier issues reported: (kind, key) to the writer count at the time."""
    return {(kind, key): int(writers) for kind, key, writers in db.run(REPORTED_SQL)}


# --- the items ----------------------------------------------------------------------------------------


def _short_quote(rows: list[ThemeRow]) -> tuple[str, str]:
    """The shortest quote that is not trivial, and who said it."""
    best = min((r for r in rows if len(r.quote) >= 20), key=lambda r: len(r.quote), default=rows[0])
    quote = best.quote if len(best.quote) <= QUOTE_CHARS else best.quote[: QUOTE_CHARS - 1].rstrip() + "…"
    return quote, best.manager_name


def _stance_text(rows: list[ThemeRow]) -> str:
    counts = Counter(r.stance for r in rows if r.stance)
    if not counts:
        return "stance not judged"
    order = ("positive", "negative", "mixed", "neutral")
    return ", ".join(f"{counts[s]} {s}" for s in order if counts.get(s))


def convergence(rows: list[ThemeRow], already: dict[tuple[str, str], int], weeks: int) -> list[Item]:
    """Themes raised by MIN_WRITERS or more distinct writers in the window; a theme reported before comes
    back only with GROWTH more writers."""
    by_theme: dict[str, list[ThemeRow]] = defaultdict(list)
    for r in rows:
        by_theme[r.theme].append(r)
    items = []
    for theme, rs in by_theme.items():
        writers = {r.manager for r in rs}
        n = len(writers)
        if n < MIN_WRITERS:
            continue
        before = already.get(("convergence", theme))
        if before is not None and n < before + GROWTH:
            continue
        firsts = {r.manager for r in rs if r.first_mention}
        credible = {r.manager for r in rs if r.baseline in CREDIBLE}
        names = sorted({r.manager_name for r in rs})
        quote, who = _short_quote(rs)
        headline = f"Convergence: {rs[0].label}, {n} writers in {weeks} weeks"
        if firsts:
            headline += f", {len(firsts)} for the first time"
        headline += f"; {_stance_text(rs)}"
        if before is not None:
            headline += f" (up from {before})"
        detail_line = f'{", ".join(names)}. "{quote}" ({who})'
        items.append(
            Item(
                "convergence",
                theme,
                headline,
                detail_line,
                2 * n + len(firsts) + len(credible),
                n,
                {"writers": sorted(writers), "first": sorted(firsts), "label": rs[0].label},
            )
        )
    return items


def disagreement(rows: list[ThemeRow], already: dict[tuple[str, str], int]) -> list[Item]:
    """Themes with credible writers on both sides within the window."""
    by_theme: dict[str, list[ThemeRow]] = defaultdict(list)
    for r in rows:
        if r.stance in ("positive", "negative") and r.baseline in CREDIBLE:
            by_theme[r.theme].append(r)
    items = []
    for theme, rs in by_theme.items():
        pos = {r.manager: r for r in rs if r.stance == "positive"}
        neg = {r.manager: r for r in rs if r.stance == "negative"}
        if not pos or not neg:
            continue
        n = len(set(pos) | set(neg))
        before = already.get(("disagreement", theme))
        if before is not None and n < before + GROWTH:
            continue
        pos_quote, pos_who = _short_quote(list(pos.values()))
        neg_quote, neg_who = _short_quote(list(neg.values()))
        headline = f"Disagreement: {rs[0].label}, {len(pos)} positive, {len(neg)} negative"
        detail_line = (
            f"For: {', '.join(sorted(r.manager_name for r in pos.values()))}. "
            f"Against: {', '.join(sorted(r.manager_name for r in neg.values()))}. "
            f'"{pos_quote}" ({pos_who}); "{neg_quote}" ({neg_who})'
        )
        items.append(
            Item(
                "disagreement",
                theme,
                headline,
                detail_line,
                3 * min(len(pos), len(neg)) + n,
                n,
                {"positive": sorted(pos), "negative": sorted(neg), "label": rs[0].label},
            )
        )
    return items


def calls(rows: list[CallRow], today: date) -> list[Item]:
    """One item for the week's calls due, and one per confident miss."""
    due = [r for r in rows if r.state in ("due", "proposed")]
    items = []
    if due:
        proposed = [r for r in due if r.proposed_outcome]
        shown = []
        for r in due[:3]:
            line = f"{r.manager_name}: {r.claim}"
            if r.proposed_outcome:
                line += f" (proposed: {r.proposed_outcome}, {r.observed})"
            shown.append(line)
        if len(due) > 3:
            shown.append(f"and {len(due) - 3} more")
        headline = f"Calls due: {len(due)} for a verdict"
        if proposed:
            headline += f", {len(proposed)} with a proposed outcome"
        items.append(
            Item(
                "calls_due",
                f"week:{today.isoformat()}",
                headline,
                "; ".join(shown),
                2 + len(due) + 2 * len(proposed),
                0,
                {"predictions": [r.prediction_id for r in due]},
            )
        )
    for r in rows:
        if r.state == "scored" and r.outcome == "wrong" and r.confidence == "high":
            items.append(
                Item(
                    "confident_miss",
                    str(r.prediction_id),
                    f"Confident miss: {r.manager_name} on {r.subject}",
                    f"{r.claim} (scored wrong on {r.reviewed_on})",
                    5,
                    1,
                    {"prediction": r.prediction_id},
                )
            )
    return items


# --- the issue ----------------------------------------------------------------------------------------


def choose(items: list[Item], already: dict[tuple[str, str], int], today: date) -> tuple[list[Item], int]:
    """Rank, drop what was reported before (for the kinds that never repeat), cap at MAX_ITEMS."""
    fresh = [
        i for i in items if not (i.kind in ("calls_due", "confident_miss") and (i.kind, i.key) in already)
    ]
    fresh.sort(key=lambda i: (-i.score, i.kind, i.key))
    return fresh[:MAX_ITEMS], max(0, len(fresh) - MAX_ITEMS)


def subject(today: date, items: list[Item], collection: expected.Round | None = None) -> str:
    base = f"Whale Tracker, week of {today.isoformat()}: "
    text = "nothing to report" if not items else (f"{len(items)} items" if len(items) > 1 else "1 item")
    if collection is not None and collection.items:
        text += f"; collection round {collection.number}, {len(collection.items)} letters"
    return base + text


def render(items: list[Item], collection: expected.Round | None = None) -> str:
    if not items:
        body = (
            "Nothing cleared the bar this week: no theme reached three writers, no credible disagreement, "
            "no call due."
        )
    else:
        lines = []
        for n, item in enumerate(items, start=1):
            lines.append(f"{n}. {item.headline}")
            lines.append(f"   {item.detail_line}")
        body = "\n".join(lines)
    if collection is not None:
        body += "\n\n" + expected.render_round(collection)
    return body


def build(db: Database, today: date, *, weeks: int = WINDOW_WEEKS) -> Digest:
    since = today - timedelta(weeks=weeks)
    already = reported(db)
    rows = theme_rows(db, since)
    items = convergence(rows, already, weeks) + disagreement(rows, already)
    items += calls(call_rows(db, today - timedelta(days=7)), today)
    chosen, dropped = choose(items, already, today)
    collection = expected.round_for(db, today)
    return Digest(
        today, subject(today, chosen, collection), render(chosen, collection), chosen, dropped, collection
    )


def record(db: Database, digest: Digest) -> int:
    """Store the issue and its items as whales_ingest; one issue per day (the database refuses a second)."""
    conn = db.connection()
    with conn.transaction():
        run_id = conn.execute(
            "INSERT INTO raw.run_log (command, git_sha, host, status, finished_at) "
            "VALUES ('digest', %s, %s, 'ok', now()) RETURNING id",
            (_git_sha(), platform.node()),
        ).fetchone()[0]
        digest_id = conn.execute(
            "INSERT INTO reports.digest (issued_on, subject, body, items, run_id) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (digest.issued_on, digest.subject, digest.body, len(digest.items), run_id),
        ).fetchone()[0]
        for item in digest.items:
            conn.execute(
                "INSERT INTO reports.digest_item (digest_id, kind, key, writers, score, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (digest_id, item.kind, item.key, item.writers, item.score, json.dumps(item.detail)),
            )
    if digest.collection is not None:
        expected.mark_reminded(db, digest.collection)
    return digest_id
