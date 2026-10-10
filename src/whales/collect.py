"""Collect tier-2 letters from SEC EDGAR: ``whales collect sec`` (W-031, W-041).

For every active source with an ``edgar`` rule, list the wanted documents filed since ``edgar_since``, skip
those already collected, fetch the rest and record each as a ``letters.document`` with one
``letters.document_file``. The database trigger fills in the permission snapshot. Raw files are not kept yet
(W-041): an SEC document can always be fetched again by its accession number.

Runs as ``whales_ingest``, the job's role, so a run from a developer's machine has exactly the job's rights.
Every run writes one ``raw.run_log`` row, and every source gets a ``letters.fetch_attempt`` row.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from dataclasses import dataclass, field

import psycopg

from .config import Config, Source
from .db.connect import Database
from .sources.edgar import EdgarClient
from .sources.sec_letters import Candidate, candidates, pdf_flags

INGEST_ROLE = "whales_ingest"
# Only a fund report's report date is the period a letter covers; for 13D and 8-K it is an event date.
PERIOD_PRESETS = {"ncsr"}


@dataclass
class SourceResult:
    slug: str
    found: int = 0
    new: list[Candidate] = field(default_factory=list)
    collected: int = 0
    duplicates: int = 0
    error: str | None = None


def sec_sources(cfg: Config, slugs: list[str] | None = None) -> list[Source]:
    chosen = [s for s in cfg.sources if s.edgar and s.active]
    if slugs:
        unknown = set(slugs) - {s.slug for s in chosen}
        if unknown:
            raise ValueError(f"not active SEC sources: {sorted(unknown)}")
        chosen = [s for s in chosen if s.slug in slugs]
    return chosen


def _git_sha() -> str | None:
    if os.environ.get("GIT_SHA"):
        return os.environ["GIT_SHA"]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or None
    except OSError:
        return None


def survey(db: Database, client: EdgarClient, cfg: Config, sources: list[Source]) -> list[SourceResult]:
    """What each source has on EDGAR since ``edgar_since``, and which documents are not yet collected."""
    results = []
    for s in sources:
        r = SourceResult(s.slug)
        try:
            known = {
                u
                for (u,) in db.run(
                    "SELECT f.url FROM letters.document_file f JOIN letters.source s ON s.id = f.source_id "
                    "WHERE s.slug = %s",
                    (s.slug,),
                )
            }
            found = candidates(client, s.edgar.preset, list(s.edgar.ciks), cfg.edgar_since)
            r.found = len(found)
            r.new = [c for c in found if c.document.url not in known]
        except Exception as e:  # noqa: BLE001 - one source failing must not stop the others; it is recorded
            r.error = f"{type(e).__name__}: {e}"
        results.append(r)
    return results


def collect(
    db: Database, client: EdgarClient, cfg: Config, sources: list[Source], *, limit: int | None = None
) -> list[SourceResult]:
    """Survey, then fetch and record every new document. One run_log row; one or more fetch_attempt rows per
    source."""
    conn = db.connection()
    run_id = conn.execute(
        "INSERT INTO raw.run_log (command, git_sha, host) VALUES (%s, %s, %s) RETURNING id",
        ("collect sec", _git_sha(), platform.node()),
    ).fetchone()[0]
    results = survey(db, client, cfg, sources)
    preset = {s.slug: s.edgar.preset for s in sources}
    for r in results:
        source_id = conn.execute("SELECT id FROM letters.source WHERE slug = %s", (r.slug,)).fetchone()[0]
        if r.error:
            _attempt(conn, source_id, run_id, "failed", error=r.error[:2000])
            continue
        keeps_period = preset[r.slug] in PERIOD_PRESETS
        for c in r.new[:limit] if limit else r.new:
            try:
                file_id = _record(conn, client, source_id, c, c.filing.period if keeps_period else None)
            except Exception as e:  # noqa: BLE001 - recorded per document; the run goes on
                error = f"{c.document.url}: {type(e).__name__}: {e}"
                _attempt(conn, source_id, run_id, "failed", error=error[:2000])
                r.error = r.error or error
                continue
            if file_id is None:
                r.duplicates += 1
                continue
            r.collected += 1
            _attempt(conn, source_id, run_id, "new", document_file_id=file_id)
        if not r.collected and not r.error:
            _attempt(conn, source_id, run_id, "unchanged")
    status = "failed" if any(r.error for r in results) else "ok"
    detail = {
        r.slug: {"found": r.found, "new": len(r.new), "collected": r.collected, "duplicates": r.duplicates}
        | ({"error": r.error} if r.error else {})
        for r in results
    }
    detail["_sec_requests"] = client.requests
    conn.execute(
        "UPDATE raw.run_log SET status = %s, finished_at = now(), detail = %s WHERE id = %s",
        (status, json.dumps(detail), run_id),
    )
    return results


def _attempt(conn, source_id: int, run_id: int, outcome: str, *, document_file_id=None, error=None) -> None:
    conn.execute(
        "INSERT INTO letters.fetch_attempt (source_id, run_id, outcome, document_file_id, error) "
        "VALUES (%s, %s, %s, %s, %s)",
        (source_id, run_id, outcome, document_file_id, error),
    )


def _record(conn, client: EdgarClient, source_id: int, c: Candidate, period) -> int | None:
    """Fetch one document and record it. None if the same bytes are already held for this source."""
    body, content_type = client.get(c.document.url)
    sha = hashlib.sha256(body).hexdigest()
    encrypted, permissions, extract_ok = (None, None, None)
    if content_type == "application/pdf" or body[:5] == b"%PDF-":
        encrypted, permissions, extract_ok = pdf_flags(body)
    try:
        with conn.transaction():
            document_id = conn.execute(
                "INSERT INTO letters.document (manager_id, title, kind, period_end, published_on, "
                "published_on_basis) VALUES ((SELECT manager_id FROM letters.source WHERE id = %s), %s, "
                "'filing_exhibit', %s, %s, 'stated') RETURNING id",
                (source_id, c.title[:500], period, c.filing.filed),
            ).fetchone()[0]
            return conn.execute(
                "INSERT INTO letters.document_file (document_id, source_id, url, accession, sha256, "
                "content_type, byte_size, collected, raw_kept, pdf_encrypted, pdf_permissions, "
                "pdf_extract_allowed) VALUES (%s, %s, %s, %s, %s, %s, %s, 'auto', false, %s, %s, %s) "
                "RETURNING id",
                (
                    document_id,
                    source_id,
                    c.document.url,
                    c.filing.accession,
                    sha,
                    content_type or "application/octet-stream",
                    len(body),
                    encrypted,
                    permissions,
                    extract_ok,
                ),
            ).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        return None
