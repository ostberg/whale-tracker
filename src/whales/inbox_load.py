"""Record inbox letters in the database: ``whales inbox load --apply`` (W-044).

Runs as ``whales_ingest``. Each file becomes one ``letters.document`` with one ``letters.document_file``,
recorded once by content hash. The copy's ``url`` is ``inbox:<route folder>/<path>``, so it can always be
found again; the raw file is not stored in the database or Blob yet (W-041, W-044). The permission snapshot
comes from the source, set by the database trigger.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field

import psycopg

from .config import Config
from .db.connect import Database
from .inbox import ROUTES, InboxFile, source_for

ROUTE_DIR = {v: k for k, v in ROUTES.items()}


@dataclass
class LoadResult:
    recorded: list[InboxFile] = field(default_factory=list)
    known: list[InboxFile] = field(default_factory=list)
    unresolved: list[InboxFile] = field(default_factory=list)
    no_source: list[InboxFile] = field(default_factory=list)
    unreadable: list[InboxFile] = field(default_factory=list)


def plan(cfg: Config, files: list[InboxFile], known_hashes: set[str]) -> tuple[LoadResult, list[tuple]]:
    """Sort files into what to record and why the rest is left. Pure, for testing."""
    r = LoadResult()
    todo = []
    for f in files:
        if f.error and not f.manager:
            r.unreadable.append(f)
        elif f.sha256 in known_hashes:
            r.known.append(f)
        elif not f.manager:
            r.unresolved.append(f)
        else:
            source = source_for(cfg, f)
            if source is None:
                r.no_source.append(f)
            else:
                todo.append((f, source))
    return r, todo


def load(db: Database, cfg: Config, files: list[InboxFile]) -> LoadResult:
    conn = db.connection()
    known = {h for (h,) in db.run("SELECT sha256 FROM letters.document_file")}
    result, todo = plan(cfg, files, known)
    run_id = conn.execute(
        "INSERT INTO raw.run_log (command, host) VALUES ('inbox load', %s) RETURNING id", (platform.node(),)
    ).fetchone()[0]
    for f, source in todo:
        try:
            with conn.transaction():
                document_id = conn.execute(
                    "INSERT INTO letters.document (manager_id, title, kind, period_end, published_on, "
                    "published_on_basis) VALUES ((SELECT manager_id FROM letters.source WHERE slug = %s), "
                    "%s, %s, %s, %s, %s) RETURNING id",
                    (
                        source,
                        (f.title or f.path.stem)[:500],
                        f.kind,
                        f.period_end,
                        f.published_on,
                        f.published_basis,
                    ),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO letters.document_file (document_id, source_id, url, sha256, content_type, "
                    "byte_size, collected, raw_kept, pdf_encrypted, pdf_permissions, pdf_extract_allowed) "
                    "VALUES (%s, (SELECT id FROM letters.source WHERE slug = %s), %s, %s, 'application/pdf', "
                    "%s, 'manual', false, %s, %s, %s)",
                    (
                        document_id,
                        source,
                        f"inbox:{ROUTE_DIR[f.route]}/{f.rel}",
                        f.sha256,
                        f.size,
                        f.encrypted,
                        f.pdf_permissions,
                        f.extract_allowed,
                    ),
                )
            result.recorded.append(f)
        except psycopg.errors.UniqueViolation:
            result.known.append(f)
    conn.execute(
        "UPDATE raw.run_log SET status = 'ok', finished_at = now(), detail = %s WHERE id = %s",
        (
            json.dumps(
                {
                    "recorded": len(result.recorded),
                    "known": len(result.known),
                    "unresolved": len(result.unresolved),
                    "no_source": len(result.no_source),
                    "unreadable": len(result.unreadable),
                }
            ),
            run_id,
        ),
    )
    return result
