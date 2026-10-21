"""Collect letters from managers' own websites: ``whales collect web`` (W-046).

For every active automatic tier-1 source with a ``web`` rule: list its documents (index pages, sitemap or
feed), skip those already collected, fetch the rest, describe each (title, period, kind, publication date;
PDF permission flags) and record it as a ``letters.document`` with one ``letters.document_file``. The database
trigger fills in the permission snapshot. Raw files are not kept yet (W-041).

``--offline`` lists without a database. Recording reads PDFs, so it runs only inside the Azure job (the
laptop exception W-045 covers the inbox alone). One ``raw.run_log`` row per run; a ``letters.fetch_attempt``
row per source.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import platform
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath

import psycopg

from .collect import _attempt, _git_sha
from .config import Config, Source
from .db.connect import Database
from .inbox import InboxFile, date_and_kind, read_pdf
from .sources.web import WebCandidate, WebClient, WebError, candidates


class NotInAzure(RuntimeError):
    """Recording reads PDFs, which is allowed only inside the job container."""


def user_agent() -> str:
    ua = (os.environ.get("WHALES_USER_AGENT") or os.environ.get("SEC_USER_AGENT") or "").strip()
    if "@" not in ua or " " not in ua:
        raise WebError("WHALES_USER_AGENT (or SEC_USER_AGENT) must name the organisation and a contact email")
    return ua


def in_azure() -> bool:
    return bool(os.environ.get("IDENTITY_ENDPOINT"))


@dataclass
class WebResult:
    slug: str
    found: int = 0
    new: list[WebCandidate] = field(default_factory=list)
    collected: int = 0
    duplicates: int = 0
    error: str | None = None


def web_sources(cfg: Config, slugs: list[str] | None = None) -> list[Source]:
    chosen = [s for s in cfg.sources if s.web and s.active and s.mode == "auto" and s.tier == 1]
    if slugs:
        unknown = set(slugs) - {s.slug for s in chosen}
        if unknown:
            raise ValueError(f"not active web sources: {sorted(unknown)}")
        chosen = [s for s in chosen if s.slug in slugs]
    return chosen


def survey(db: Database | None, client: WebClient, sources: list[Source]) -> list[WebResult]:
    """What each source lists now, and which documents are not yet collected (all of them, offline)."""
    results = []
    for s in sources:
        r = WebResult(s.slug)
        try:
            known: set[str] = set()
            if db is not None:
                known = {
                    u
                    for (u,) in db.run(
                        "SELECT f.url FROM letters.document_file f "
                        "JOIN letters.source s ON s.id = f.source_id WHERE s.slug = %s",
                        (s.slug,),
                    )
                }
            found = candidates(client, s.web)
            r.found = len(found)
            r.new = [c for c in found if c.url not in known]
        except Exception as e:  # noqa: BLE001 - one source failing must not stop the others; it is recorded
            r.error = f"{type(e).__name__}: {e}"
        results.append(r)
    return results


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", page, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


GENERIC_LINK_TEXT = re.compile(r"^(read more|download|view|open|pdf|click here|link|more)\W*$", re.I)


def page_date(page: str) -> date | None:
    """The publication date a page states in its markup: a ``<time datetime>``, an ``article:published_time``
    meta tag or a ``datePublished`` field. The first Azure run (2026-10-21) dated every Oaktree memo on the
    day it was collected because the memo's date sits past the first 400 characters of visible text."""
    for pattern in (
        r"<time\b[^>]*\bdatetime=[\"'][^\"'\d]*(\d{4}-\d{2}-\d{2})",
        r"<meta\b[^>]*\barticle:published_time[^>]*\bcontent=[\"'][^\"'\d]*(\d{4}-\d{2}-\d{2})",
        r"\"datePublished\"\s*:\s*\"[^\"\d]*(\d{4}-\d{2}-\d{2})",
    ):
        m = re.search(pattern, page, re.I)
        if m:
            try:
                return date.fromisoformat(m[1])
            except ValueError:
                continue
    return None


def describe(c: WebCandidate, body: bytes, content_type: str, today: date) -> InboxFile:
    """Title, period, kind and publication date of one fetched document, with the inbox's rules."""
    name = PurePosixPath(urllib.parse.urlsplit(c.url).path).name or "document"
    f = InboxFile(None, "public", name, hashlib.sha256(body).hexdigest(), len(body))
    stated = None
    if content_type == "application/pdf" or body[:5] == b"%PDF-":
        read_pdf(f, body)
    else:
        page = body.decode("utf-8", "replace")
        title = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        f.title = visible_text(title.group(1))[:300] if title else None
        f.head = visible_text(page)[:4000]
        stated = page_date(page)
    link_text = c.text if c.text and not GENERIC_LINK_TEXT.match(c.text) else None
    f.title = f.title or link_text or name  # a "READ MORE" link is no title; the file name says more
    date_and_kind(f, today, stated)
    return f


def collect(
    db: Database, client: WebClient, cfg: Config, sources: list[Source], *, limit: int | None = None
) -> list[WebResult]:
    if not in_azure():
        raise NotInAzure("recording reads PDFs; run it in the Azure job (W-045 covers the inbox only)")
    conn = db.connection()
    run_id = conn.execute(
        "INSERT INTO raw.run_log (command, git_sha, host) VALUES (%s, %s, %s) RETURNING id",
        ("collect web", _git_sha(), platform.node()),
    ).fetchone()[0]
    results = survey(db, client, sources)
    rules = {s.slug: s.web for s in sources}
    today = date.today()
    for r in results:
        source_id = conn.execute("SELECT id FROM letters.source WHERE slug = %s", (r.slug,)).fetchone()[0]
        if r.error:
            _attempt(conn, source_id, run_id, "failed", error=r.error[:2000])
            continue
        for c in r.new[:limit] if limit else r.new:
            try:
                body, ctype = client.get(c.url, rules[r.slug].allowed_hosts())
                file_id = _record(conn, source_id, c, body, ctype, today)
            except Exception as e:  # noqa: BLE001 - recorded per document; the run goes on
                error = f"{c.url}: {type(e).__name__}: {e}"
                _attempt(
                    conn,
                    source_id,
                    run_id,
                    "blocked" if isinstance(e, WebError) else "failed",
                    error=error[:2000],
                )
                r.error = r.error or error
                continue
            if file_id is None:
                r.duplicates += 1
                continue
            r.collected += 1
            _attempt(conn, source_id, run_id, "new", document_file_id=file_id)
        if not r.collected and not r.error:
            _attempt(conn, source_id, run_id, "unchanged")
    detail = {r.slug: {"found": r.found, "new": len(r.new), "collected": r.collected} for r in results}
    detail["_requests"] = client.requests
    conn.execute(
        "UPDATE raw.run_log SET status = %s, finished_at = now(), detail = %s WHERE id = %s",
        ("failed" if any(r.error for r in results) else "ok", json.dumps(detail), run_id),
    )
    return results


REDATE_SQL = """
SELECT DISTINCT ON (d.id) d.id, m.slug, d.title, d.published_on, d.period_end, f.url, s.slug
FROM letters.document d
JOIN letters.document_file f ON f.document_id = d.id
JOIN letters.source s ON s.id = f.source_id
JOIN core.manager m ON m.id = d.manager_id
WHERE d.published_on_basis = 'first_seen' AND f.url LIKE 'http%%'
  AND (%s::text IS NULL OR m.slug = %s)
ORDER BY d.id, f.id DESC
"""
SUPERSEDE_SQL = (
    "UPDATE letters.extraction_run SET status = 'superseded', "
    'detail = detail || \'{"superseded": "document redated"}\'::jsonb '
    "WHERE document_id = %s AND task = 'predictions' AND status = 'ok'"
)


@dataclass
class RedateResult:
    document_id: int
    manager: str
    title: str
    old: date
    new: date | None = None
    basis: str | None = None
    runs_superseded: int = 0
    error: str | None = None


def redate(
    db: Database,
    client: WebClient,
    cfg: Config,
    *,
    manager: str | None = None,
    apply: bool = False,
    limit: int | None = None,
) -> list[RedateResult]:
    """Documents dated the day they were first seen: fetch each again and take the date its page markup or
    file states (migration 0004). A redated document's successful predictions runs are marked superseded,
    so the next extraction run redoes them with the right window. Dry run: list them, fetch nothing."""
    rows = db.run(REDATE_SQL, (manager, manager))
    rows = rows[:limit] if limit else rows
    results = [RedateResult(r[0], r[1], r[2], r[3]) for r in rows]
    if not apply:
        return results
    if not in_azure():
        raise NotInAzure("redating reads PDFs; run it in Azure as the ingest job (W-045 covers the inbox)")
    rules = {s.slug: s.web for s in cfg.sources if s.web}
    conn = db.connection()
    today = date.today()
    for r, row in zip(results, rows, strict=True):
        _id, _m, _t, _old, period_end, url, source_slug = row
        rule = rules.get(source_slug)
        try:
            if rule is None:
                raise WebError(f"source {source_slug} has no web rule")
            body, ctype = client.get(url, rule.allowed_hosts())
            f = describe(WebCandidate(url, ""), body, ctype, today)
        except Exception as e:  # noqa: BLE001 - recorded per document; the run goes on
            r.error = f"{type(e).__name__}: {e}"[:500]
            continue
        if f.published_basis == "first_seen" or f.published_on == r.old:
            continue  # nothing better found
        with conn.transaction():
            conn.execute(
                "UPDATE letters.document SET published_on = %s, published_on_basis = %s, "
                "period_end = COALESCE(period_end, %s) WHERE id = %s",
                (f.published_on, f.published_basis, f.period_end, r.document_id),
            )
            r.runs_superseded = conn.execute(SUPERSEDE_SQL, (r.document_id,)).rowcount
        r.new, r.basis = f.published_on, f.published_basis
    return results


def _record(conn, source_id: int, c: WebCandidate, body: bytes, ctype: str, today: date) -> int | None:
    f = describe(c, body, ctype, today)
    is_pdf = ctype == "application/pdf" or body[:5] == b"%PDF-"
    # HTML pages change markup; their visible text is the stable fingerprint (W-039)
    text_sha = None if is_pdf else hashlib.sha256(f.head.encode("utf-8")).hexdigest()
    try:
        with conn.transaction():
            document_id = conn.execute(
                "INSERT INTO letters.document (manager_id, title, kind, period_end, published_on, "
                "published_on_basis) VALUES ((SELECT manager_id FROM letters.source WHERE id = %s), "
                "%s, %s, %s, %s, %s) RETURNING id",
                (source_id, f.title[:500], f.kind, f.period_end, f.published_on, f.published_basis),
            ).fetchone()[0]
            return conn.execute(
                "INSERT INTO letters.document_file (document_id, source_id, url, sha256, text_sha256, "
                "content_type, byte_size, collected, raw_kept, pdf_encrypted, pdf_permissions, "
                "pdf_extract_allowed) VALUES (%s, %s, %s, %s, %s, %s, %s, 'auto', false, %s, %s, %s) "
                "RETURNING id",
                (
                    document_id,
                    source_id,
                    c.url,
                    f.sha256,
                    text_sha,
                    ctype or "application/octet-stream",
                    f.size,
                    f.encrypted if is_pdf else None,
                    f.pdf_permissions,
                    f.extract_allowed if is_pdf else None,
                ),
            ).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        return None
