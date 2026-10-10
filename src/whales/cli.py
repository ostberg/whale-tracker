"""The ``whales`` command: every scheduled job and one-off command goes through here (AGENTS.md).

    whales db connect-paths <database>               who can connect, and who would lose access (read-only)
    whales db revoke-public-connect <database>       show the statement; add --apply to run it
    whales db bootstrap-roles <database>             the whales_ group roles and database rights; --apply
    whales db migrate                                pending migrations on WHALES_DB_NAME; --apply
    whales config check                              validate config/ (no database)
    whales config sync                               config/ into WHALES_DB_NAME; --apply
    whales collect sec [--source SLUG]               new SEC letters (tier 2) since edgar_since; --apply

Admin commands run as the Entra admin (``az login``), so they need ``WHALES_DB_HOST`` and a temporary
firewall rule for this machine. Every command shows what it would do unless given --apply.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import collect, config
from .db import admin, migrate, sync
from .db.connect import Database, DbSettings
from .sources.edgar import EdgarClient


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
    with Database(DbSettings.from_env()) as db:
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
        f"({sum(s.active for s in cfg.sources)} active)"
    )
    return 0


def cmd_config_sync(args: argparse.Namespace) -> int:
    cfg = config.load()
    with Database(DbSettings.from_env()) as db:
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="whales", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
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
    return ap


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
