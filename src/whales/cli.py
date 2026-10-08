"""The ``whales`` command: every scheduled job and one-off command goes through here (AGENTS.md).

    whales db connect-paths <database>               who can connect, and who would lose access (read-only)
    whales db revoke-public-connect <database>       show the statement; add --apply to run it

Admin commands connect to the ``postgres`` database as the Entra admin (``az login``), so they need
``WHALES_DB_HOST`` and a firewall rule for this machine.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .db import admin
from .db.connect import Database, DbSettings


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
    return ap


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
