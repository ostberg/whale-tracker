"""The ``whales`` command: every scheduled job and one-off command goes through here (AGENTS.md).

    whales db connect-paths <database>               who can connect, and who would lose access (read-only)
    whales db revoke-public-connect <database>       show the statement; add --apply to run it
    whales db bootstrap-roles <database>             the whales_ group roles and database rights; --apply
    whales db migrate                                pending migrations on WHALES_DB_NAME; --apply
    whales config check                              validate config/ (no database)
    whales config sync                               config/ into WHALES_DB_NAME; --apply
    whales collect sec [--source SLUG]               new SEC letters (tier 2) since edgar_since; --apply
    whales collect web [--source SLUG] [--offline]   new letters from managers' websites; --apply (Azure only)
    whales db add-identity <name> --group G <db>     register a managed identity (owner or ingest); --apply
    whales db close-firewall                         remove any temporary firewall rule left behind
    whales status                                    counts and the latest runs (read-only)
    whales inbox scan                                letters in the inbox and who each is from (no database)
    whales inbox load                                record new inbox letters as whales_ingest; --apply
    whales extract predictions                       claims from machine-readable documents; --apply (Azure)
    whales model check                               one small call to the configured model endpoint
    whales digest [--today D] [--weeks N]            the weekly digest, at most four items; --apply records it
    whales expected refresh | list | skip            the reminder calendar for manual sources; --apply
    whales weekly                                    the Monday job: calendar refresh then digest; --apply

Routine runs happen in Azure as Container Apps jobs (W-042). From a laptop, the few admin steps that need the
Entra admin's own rights run with ``whales --open-firewall ...``, which opens this machine's address for that
one command and always closes it again. Every command shows what it would do unless given --apply.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import collect, collect_web, config, expected, extract, inbox, inbox_load, llm
from .db import admin, firewall, migrate, sync
from .db.connect import Database, DbSettings
from .reports import digest
from .sources.edgar import EdgarClient
from .sources.web import WebClient


def load_env_file(path: Path = Path(".env")) -> None:
    """Read KEY=VALUE lines from a local .env into the environment, never overriding what is already set.
    Local convenience only; in Azure the job's settings come from the platform."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _admin_db() -> Database:
    return Database(DbSettings.from_env("postgres"))


def cmd_connect_paths(args: argparse.Namespace) -> int:
    with _admin_db() as db:
        paths = admin.connect_paths(db, args.database)
    if not paths:
        print(f"no such database, or no login roles: {args.database}")
        return 1
    print(f"database {args.database}: PUBLIC has CONNECT = {paths[0].public_has_connect}")
    print(f"{'role':<48} {'inherits':<8} {'connects':<8} {'owner':<6} {'own grant':<9} would lose")
    for p in paths:
        print(
            f"{p.role:<48} {p.inherits!s:<8} {p.can_connect!s:<8} {p.is_owner!s:<6} "
            f"{p.without_public!s:<9} {'YES' if p.would_lose_access else ''}"
        )
    losers = [p.role for p in paths if p.would_lose_access]
    print(f"\nwould lose access if PUBLIC loses CONNECT: {losers or 'nobody'}")
    return 0


def cmd_revoke_public_connect(args: argparse.Namespace) -> int:
    sql = admin.revoke_public_connect_sql(args.database)
    print(sql)
    if not args.apply:
        print("(dry run: nothing changed; add --apply)")
        return 0
    with _admin_db() as db:
        losers = [p.role for p in admin.connect_paths(db, args.database) if p.would_lose_access]
        if losers and not args.force:
            print(f"refused: these roles would lose access: {losers}. Grant them CONNECT first, or --force.")
            return 2
        db.run(sql)
        after = admin.connect_paths(db, args.database)
    print(f"done: PUBLIC has CONNECT = {after[0].public_has_connect if after else 'unknown'}")
    return 0


def cmd_bootstrap_roles(args: argparse.Namespace) -> int:
    settings = DbSettings.from_env("postgres")
    statements = admin.bootstrap_statements(settings.user, args.database)
    for s in statements:
        print(s)
    if not args.apply:
        print("(dry run: nothing changed; add --apply)")
        return 0
    with Database(settings) as db:
        for s in statements:
            db.run(s)
        roles = db.run("SELECT rolname FROM pg_roles WHERE rolname LIKE 'whales\\_%' ORDER BY 1")
    print(f"done: roles {[r[0] for r in roles]}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    available = migrate.discover()
    with Database(DbSettings.from_env(), role=migrate.OWNER_ROLE) as db:
        todo = migrate.pending(available, migrate.applied_versions(db))
        print(f"database {db.settings.dbname}: {len(available) - len(todo)} applied, {len(todo)} pending")
        for m in todo:
            print(f"   pending {m.version:04d}_{m.name}")
        if not todo or not args.apply:
            if todo:
                print("(dry run: nothing changed; add --apply)")
            return 0
        for m in todo:
            migrate.apply(db, m)
            print(f"   applied {m.version:04d}_{m.name}")
    return 0


def cmd_config_check(args: argparse.Namespace) -> int:
    cfg = config.load()
    print(
        f"config ok: {len(cfg.tags)} tags, {len(cfg.topics)} topics, {len(cfg.managers)} managers "
        f"({sum(len(m.filers) for m in cfg.managers)} filers, "
        f"{sum(len(m.tags) for m in cfg.managers)} tag proposals), {len(cfg.sources)} letter sources "
        f"({sum(s.active for s in cfg.sources)} active), {len(cfg.baselines)} trust baselines"
    )
    return 0


def cmd_config_sync(args: argparse.Namespace) -> int:
    cfg = config.load()
    with Database(DbSettings.from_env(), role=migrate.OWNER_ROLE) as db:
        changes = sync.plan(cfg, sync.read_current(db))
        counts: dict[str, int] = {}
        for c in changes:
            counts[c.action] = counts.get(c.action, 0) + 1
            if args.verbose or c.action in ("update", "deactivate", "note"):
                print(f"   {c.action:<10} {c.what}")
        print(
            f"database {db.settings.dbname}: "
            + (", ".join(f"{n} {a}" for a, n in sorted(counts.items())) or "in step")
        )
        if not args.apply:
            if any(c.sql for c in changes):
                print("(dry run: nothing changed; add --apply)")
            return 0
        print(f"applied {sync.apply(db, changes)} change(s)")
    return 0


def cmd_collect_web(args: argparse.Namespace) -> int:
    cfg = config.load()
    sources = collect_web.web_sources(cfg, args.source)
    client = WebClient(collect_web.user_agent())
    if args.offline:
        results = collect_web.survey(None, client, sources)
    else:
        with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
            if args.apply:
                results = collect_web.collect(db, client, cfg, sources, limit=args.limit)
            else:
                results = collect_web.survey(db, client, sources)
    print(f"{client.requests} requests")
    for r in results:
        line = f"   {r.slug:<30} found {r.found:<4} new {len(r.new):<4}"
        if args.apply:
            line += f" collected {r.collected:<4} duplicates {r.duplicates}"
        print(line + (f"  ERROR {r.error}" if r.error else ""))
        if args.verbose:
            for c in r.new[:50]:
                print(f"        {c.url}  {c.text[:80]}")
    if not args.apply:
        print("(dry run: nothing fetched beyond index pages, nothing written; add --apply in Azure)")
    return 1 if any(r.error for r in results) else 0


def cmd_collect_sec(args: argparse.Namespace) -> int:
    cfg = config.load()
    sources = collect.sec_sources(cfg, args.source)
    client = EdgarClient()
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        if args.apply:
            results = collect.collect(db, client, cfg, sources, limit=args.limit)
        else:
            results = collect.survey(db, client, cfg, sources)
    print(f"since {cfg.edgar_since}; {client.requests} SEC requests")
    for r in results:
        line = f"   {r.slug:<26} found {r.found:<4} new {len(r.new):<4}"
        if args.apply:
            line += f" collected {r.collected:<4} duplicates {r.duplicates}"
        print(line + (f"  ERROR {r.error}" if r.error else ""))
        if args.verbose:
            for c in r.new:
                print(f"        {c.filing.filed} {c.filing.accession} {c.title}")
    if not args.apply:
        print("(dry run: nothing fetched or written; add --apply)")
    return 1 if any(r.error for r in results) else 0


def cmd_add_identity(args: argparse.Namespace) -> int:
    statements = admin.add_identity_statements(args.name, args.group, args.database)
    for s in statements:
        print(s)
    if not args.apply:
        print("(dry run: nothing changed; add --apply)")
        return 0
    with _admin_db() as db:
        for s in statements:
            db.run(s)
    print(f"done: {args.name} is in whales_{args.group} and may connect to {args.database}")
    return 0


def cmd_close_firewall(args: argparse.Namespace) -> int:
    removed = firewall.close_leftovers()
    print(f"removed {removed or 'nothing'}")
    return 0


STATUS_SQL = {
    "managers (active)": "SELECT count(*) FILTER (WHERE active) FROM core.manager",
    "filers": "SELECT count(*) FROM core.filer",
    "sources (active / all)": "SELECT count(*) FILTER (WHERE active) || ' / ' || count(*) "
    "FROM letters.source",
    "documents": "SELECT count(*) FROM letters.document",
    "document copies": "SELECT count(*) FROM letters.document_file",
    "tag proposals / decisions": "SELECT (SELECT count(*) FROM core.manager_tag) || ' / ' || "
    "(SELECT count(*) FROM core.tag_decision)",
}


def cmd_status(args: argparse.Namespace) -> int:
    with Database(DbSettings.from_env(), role=migrate.OWNER_ROLE) as db:
        print(f"database {db.settings.dbname}, migrations {sorted(migrate.applied_versions(db))}")
        for label, sql in STATUS_SQL.items():
            print(f"   {label:<28} {db.run(sql)[0][0]}")
        print("   latest runs:")
        for row in db.run(
            "SELECT id, command, status, started_at::timestamp(0), started_by, detail::text FROM raw.run_log "
            "ORDER BY id DESC LIMIT 5"
        ):
            print(f"      #{row[0]} {row[1]} {row[2]} {row[3]} by {row[4]}  {row[5][:300]}")
        print("   documents by source:")
        for slug, n, last in db.run(
            "SELECT s.slug, count(f.id), max(f.fetched_at)::date FROM letters.source s "
            "LEFT JOIN letters.document_file f ON f.source_id = s.id WHERE s.active "
            "GROUP BY s.slug ORDER BY 2 DESC"
        ):
            print(f"      {slug:<28} {n:>5}  last {last}")
    return 0


def _print_scan(files: list[inbox.InboxFile], cfg: config.Config, verbose: bool) -> None:
    for f in files:
        if verbose or not f.manager or f.error:
            who = f"{f.manager} ({f.manager_basis})" if f.manager else f"?  {', '.join(f.candidates) or '-'}"
            flags = " ENCRYPTED" if f.encrypted else ""
            flags += " NO-EXTRACT" if f.extract_allowed is False else ""
            flags += f"  ERROR {f.error}" if f.error else ""
            print(
                f"   {f.route:<6} {who:<34} {str(f.period_end or '-'):<10} {f.kind:<16} "
                f"{f.published_on} ({f.published_basis}) {f.pages or '?':>3}p  {f.rel}{flags}"
            )
    by_manager: dict[str, int] = {}
    for f in files:
        if f.manager:
            by_manager[f.manager] = by_manager.get(f.manager, 0) + 1
    unresolved = [f for f in files if not f.manager]
    print(
        f"{len(files)} PDFs: {len(files) - len(unresolved)} identified, {len(unresolved)} unresolved, "
        f"{sum(1 for f in files if f.error)} unreadable, "
        f"{sum(1 for f in files if f.extract_allowed is False)} forbid text extraction"
    )
    print(
        "   by manager: "
        + ", ".join(f"{m} {n}" for m, n in sorted(by_manager.items(), key=lambda kv: -kv[1]))
    )
    missing = sorted({(f.manager, f.route) for f in files if f.manager and inbox.source_for(cfg, f) is None})
    if missing:
        print("   no source in config yet for: " + ", ".join(f"{m} ({r})" for m, r in missing))
    if unresolved:
        print(
            "   unresolved: move each into a subfolder named after its manager's slug "
            r"(e.g. public-websites\greenwood\), or add an alias in config/managers.toml"
        )


def cmd_inbox_scan(args: argparse.Namespace) -> int:
    cfg = config.load()
    root = inbox.inbox_dir()
    print(f"inbox {root}")
    _print_scan(inbox.scan(cfg, root), cfg, args.verbose)
    return 0


def cmd_inbox_load(args: argparse.Namespace) -> int:
    cfg = config.load()
    files = inbox.scan(cfg)
    if not args.apply:
        _print_scan(files, cfg, args.verbose)
        print("(dry run: nothing recorded; add --apply)")
        return 0
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        r = inbox_load.load(db, cfg, files)
    print(
        f"recorded {len(r.recorded)}, already held {len(r.known)}, unresolved {len(r.unresolved)}, "
        f"no source {len(r.no_source)}, unreadable {len(r.unreadable)}"
    )
    return 0


def cmd_redate(args: argparse.Namespace) -> int:
    cfg = config.load()
    client = WebClient(collect_web.user_agent())
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        results = collect_web.redate(
            db, client, cfg, manager=args.manager, apply=args.apply, limit=args.limit
        )
    print(f"{len(results)} document(s) dated the day they were first seen")
    for r in results:
        line = f"   {r.manager:<24} {r.old} {r.title[:60]}"
        if r.new:
            line += f"  -> {r.new} ({r.basis}), {r.runs_superseded} run(s) superseded"
        if r.error:
            line += f"  ERROR {r.error}"
        print(line)
    if not args.apply:
        print("(dry run: nothing fetched, nothing written; add --apply in Azure)")
    return 1 if any(r.error for r in results) else 0


def cmd_extract_predictions(args: argparse.Namespace) -> int:
    cfg = config.load()
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        cands = extract.candidates(db, document_id=args.document, manager=args.manager, limit=args.limit)
        fetcher = extract.Fetcher(inbox.inbox_dir(), WebClient(collect_web.user_agent()), EdgarClient())
        provider = llm.FoundryProvider(llm.ModelSettings.from_env()) if args.apply else None
        results = extract.run(db, provider, cfg, fetcher, cands, apply=args.apply, log=print)
    print(f"{len(cands)} document(s) without a successful predictions run")
    for r in results:
        c = r.candidate
        line = f"   {r.status:<8} {c.manager:<24} {c.published_on} {c.title[:60]}"
        if r.status == "ok":
            line += f"  claims {r.claims} links {r.links} attempts {r.attempts}"
        if r.reason:
            line += f"  ({r.reason})"
        print(line)
        if args.verbose:
            for n in r.notes:
                print(f"        {n}")
    if provider is not None:
        print(f"model {provider.host} {provider.model}: {provider.totals}")
    if not args.apply:
        print("(dry run: no model called, nothing written; add --apply in Azure)")
    return 1 if any(r.status == "failed" for r in results) else 0


def cmd_digest(args: argparse.Namespace) -> int:
    from datetime import date

    today = date.fromisoformat(args.today) if args.today else date.today()
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        issue = digest.build(db, today, weeks=args.weeks)
        print(issue.subject)
        print()
        print(issue.body)
        if issue.dropped:
            print(f"\n({issue.dropped} more item(s) below the cut)")
        if args.apply:
            digest_id = digest.record(db, issue)
            print(f"\nrecorded as reports.digest #{digest_id}")
        else:
            print("\n(dry run: not recorded; add --apply)")
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    """The Monday job (W-054, W-055): refresh the reminder calendar, then build and record the digest. Safe
    to run twice in a day: a second digest for the same day is refused by the database and reported."""
    from datetime import date

    import psycopg

    cfg = config.load()
    today = date.fromisoformat(args.today) if args.today else date.today()
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        todo, loaded = expected.refresh(db, cfg, today, apply=args.apply)
        print(f"calendar: {len(todo)} new expectation(s), {loaded} marked loaded")
        issue = digest.build(db, today)
        print(issue.subject)
        print()
        print(issue.body)
        if not args.apply:
            print("\n(dry run: nothing written; add --apply)")
            return 0
        try:
            digest_id = digest.record(db, issue)
        except psycopg.errors.UniqueViolation:
            print(f"\ndigest for {today} already recorded; nothing more to do")
            return 0
        print(f"\nrecorded as reports.digest #{digest_id} (Teams post: not yet, no flow URL; W-034)")
    return 0


def cmd_expected_refresh(args: argparse.Namespace) -> int:
    from datetime import date

    cfg = config.load()
    today = date.fromisoformat(args.today) if args.today else date.today()
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        todo, loaded = expected.refresh(db, cfg, today, apply=args.apply)
        for slug, end, due_from, due_to in todo:
            print(f"   expect   {slug:<34} period to {end}  due {due_from} to {due_to}")
        if args.apply:
            print(f"inserted {len(todo)} expectation(s); marked {loaded} loaded")
        else:
            print(f"{len(todo)} expectation(s) to insert (dry run: nothing written; add --apply)")
    return 0


def cmd_expected_skip(args: argparse.Namespace) -> int:
    """Write off awaiting periods that ended before a date: the owner decides how far back to collect."""
    from datetime import date

    before = date.fromisoformat(args.before)
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        rows = expected.expectations(
            db, " WHERE e.status = 'awaiting' AND e.period_end < %s ORDER BY e.period_end, s.slug", (before,)
        )
        for e in rows:
            print(f"   skip     {e.source:<34} period to {e.period_end}")
        if args.apply and rows:
            db.run(
                "UPDATE letters.expected SET status = 'skipped' WHERE id = ANY(%s)", ([e.id for e in rows],)
            )
        print(f"{len(rows)} expectation(s) {'skipped' if args.apply else 'to skip (dry run; add --apply)'}")
    return 0


def cmd_expected_list(args: argparse.Namespace) -> int:
    with Database(DbSettings.from_env(), role=collect.INGEST_ROLE) as db:
        rows = expected.expectations(db, " ORDER BY e.status, e.period_end, s.slug")
    for e in rows:
        print(
            f"   {e.status:<18} {e.source:<34} period to {e.period_end}  due by {e.due_to}  "
            f"asked {e.reminders}x"
        )
    print(f"{len(rows)} expectation(s)")
    return 0


def cmd_model_check(args: argparse.Namespace) -> int:
    provider = llm.FoundryProvider(llm.ModelSettings.from_env())
    started = time.monotonic()
    reply = provider.complete_json("Answer with one JSON object.", 'Reply with {"ok": true}.', max_tokens=50)
    print(
        f"{provider.host} deployment {provider.model}: answered as {provider.last_model!r} in "
        f"{time.monotonic() - started:.1f}s, usage {provider.last_usage}, reply {reply}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="whales", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--open-firewall",
        action="store_true",
        help="from a laptop: open this machine's address on the database firewall for this one command",
    )
    sub = ap.add_subparsers(dest="group", required=True)
    db = sub.add_parser("db", help="database administration").add_subparsers(dest="command", required=True)

    p = db.add_parser("connect-paths", help="who can connect to a database, and who would lose access")
    p.add_argument("database")
    p.set_defaults(func=cmd_connect_paths)

    p = db.add_parser("revoke-public-connect", help="revoke CONNECT on a database from PUBLIC")
    p.add_argument("database")
    p.add_argument("--apply", action="store_true", help="run it (default: show only)")
    p.add_argument("--force", action="store_true", help="run it even if some role would lose access")
    p.set_defaults(func=cmd_revoke_public_connect)

    p = db.add_parser("bootstrap-roles", help="create the whales_ group roles and grant database rights")
    p.add_argument("database")
    p.add_argument("--apply", action="store_true", help="run it (default: show only)")
    p.set_defaults(func=cmd_bootstrap_roles)

    p = db.add_parser("add-identity", help="register a managed identity as a login role in one group")
    p.add_argument("name")
    p.add_argument("--group", required=True, choices=["owner", "ingest"])
    p.add_argument("database")
    p.add_argument("--apply", action="store_true", help="run it (default: show only)")
    p.set_defaults(func=cmd_add_identity)

    p = db.add_parser("close-firewall", help="remove temporary firewall rules left behind")
    p.set_defaults(func=cmd_close_firewall)

    p = db.add_parser("migrate", help="apply pending migrations to WHALES_DB_NAME as whales_owner")
    p.add_argument("--apply", action="store_true", help="apply them (default: list only)")
    p.set_defaults(func=cmd_migrate)

    cfg = sub.add_parser("config", help="the config/ files").add_subparsers(dest="command", required=True)
    p = cfg.add_parser("check", help="validate config/ without touching the database")
    p.set_defaults(func=cmd_config_check)
    p = cfg.add_parser("sync", help="write config/ to WHALES_DB_NAME as whales_owner")
    p.add_argument("--apply", action="store_true", help="apply the changes (default: list only)")
    p.add_argument(
        "-v", "--verbose", action="store_true", help="list inserts too, not only updates and notes"
    )
    p.set_defaults(func=cmd_config_sync)

    col = sub.add_parser("collect", help="collect letters").add_subparsers(dest="command", required=True)
    p = col.add_parser("sec", help="tier-2 letters from SEC EDGAR, as whales_ingest")
    p.add_argument("--source", action="append", help="only this source slug (repeatable)")
    p.add_argument("--apply", action="store_true", help="fetch and record (default: list only)")
    p.add_argument("--limit", type=int, help="at most this many new documents per source")
    p.add_argument("-v", "--verbose", action="store_true", help="list each new document")
    p.set_defaults(func=cmd_collect_sec)
    p = col.add_parser("web", help="letters from managers' own websites, as whales_ingest")
    p.add_argument("--source", action="append", help="only this source slug (repeatable)")
    p.add_argument("--apply", action="store_true", help="fetch and record (Azure only; default: list only)")
    p.add_argument(
        "--offline", action="store_true", help="list without a database (all documents shown as new)"
    )
    p.add_argument("--limit", type=int, help="at most this many new documents per source")
    p.add_argument("-v", "--verbose", action="store_true", help="list each new document")
    p.set_defaults(func=cmd_collect_web)

    p = sub.add_parser(
        "redate", help="take the stated date of documents dated the day they were first seen (migration 0004)"
    )
    p.add_argument("--manager", help="only this manager slug")
    p.add_argument("--limit", type=int, help="at most this many documents")
    p.add_argument(
        "--apply", action="store_true", help="fetch and update (Azure, as the ingest job; default: list only)"
    )
    p.set_defaults(func=cmd_redate)

    ext = sub.add_parser("extract", help="model extraction runs (W-048)").add_subparsers(
        dest="command", required=True
    )
    p = ext.add_parser("predictions", help="claims from documents that may be machine-read, as whales_ingest")
    p.add_argument(
        "--apply", action="store_true", help="call the model and record (Azure only; default: list)"
    )
    p.add_argument("--limit", type=int, help="at most this many documents")
    p.add_argument("--document", type=int, help="one document id")
    p.add_argument("--manager", help="only this manager slug")
    p.add_argument("-v", "--verbose", action="store_true", help="list each run's notes")
    p.set_defaults(func=cmd_extract_predictions)

    mdl = sub.add_parser("model", help="the model endpoint (W-052)").add_subparsers(
        dest="command", required=True
    )
    p = mdl.add_parser("check", help="one small call to the configured endpoint; prints what answered")
    p.set_defaults(func=cmd_model_check)

    p = sub.add_parser("weekly", help="the Monday job: calendar refresh, then the digest (job-whales-weekly)")
    p.add_argument("--apply", action="store_true", help="write (default: print only)")
    p.add_argument("--today", help="as of this date, YYYY-MM-DD (default: today)")
    p.set_defaults(func=cmd_weekly)

    p = sub.add_parser("digest", help="the weekly digest (W-054), as whales_ingest")
    p.add_argument("--apply", action="store_true", help="record the issue (default: print only)")
    p.add_argument("--today", help="issue date, YYYY-MM-DD (default: today)")
    p.add_argument("--weeks", type=int, default=digest.WINDOW_WEEKS, help="the look-back window in weeks")
    p.set_defaults(func=cmd_digest)

    exp = sub.add_parser(
        "expected", help="the reminder calendar for manual sources (W-033, W-055)"
    ).add_subparsers(dest="command", required=True)
    p = exp.add_parser("refresh", help="expect ended periods and mark the loaded ones, as whales_ingest")
    p.add_argument("--apply", action="store_true", help="write (default: list only)")
    p.add_argument("--today", help="as of this date, YYYY-MM-DD (default: today)")
    p.set_defaults(func=cmd_expected_refresh)
    p = exp.add_parser("list", help="every expectation and its status")
    p.set_defaults(func=cmd_expected_list)
    p = exp.add_parser("skip", help="write off awaiting periods that ended before a date")
    p.add_argument("--before", required=True, help="YYYY-MM-DD: periods ending before this are skipped")
    p.add_argument("--apply", action="store_true", help="write (default: list only)")
    p.set_defaults(func=cmd_expected_skip)

    p = sub.add_parser("status", help="counts and the latest runs (read-only)")
    p.set_defaults(func=cmd_status)

    inb = sub.add_parser("inbox", help="letters people collected (W-044)").add_subparsers(
        dest="command", required=True
    )
    p = inb.add_parser("scan", help="list the inbox and identify each letter (no database)")
    p.add_argument("-v", "--verbose", action="store_true", help="list every file, not only the unclear ones")
    p.set_defaults(func=cmd_inbox_scan)
    p = inb.add_parser("load", help="record new inbox letters as whales_ingest")
    p.add_argument("--apply", action="store_true", help="record them (default: show what would happen)")
    p.add_argument("-v", "--verbose", action="store_true", help="list every file")
    p.set_defaults(func=cmd_inbox_load)
    return ap


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    args = build_parser().parse_args(argv)
    if args.open_firewall:
        with firewall.opening():
            return args.func(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
