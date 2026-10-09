"""Static guards on the migration files and the role bootstrap (W-004, W-039)."""

import re

from whales.db import admin, migrate


def _all_sql() -> str:
    """Every migration, with -- comments removed (SQL bodies here contain no '--' inside strings)."""
    text = "\n".join(m.sql for m in migrate.discover())
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def test_shipped_migrations_are_discoverable():
    found = migrate.discover()
    assert found[0].version == 1 and found[0].name == "foundation"


def test_no_delete_grants_and_no_server_wide_roles():
    sql = _all_sql().upper()
    assert not re.search(r"GRANT[^;]*\bDELETE\b", sql)
    assert "PG_READ_ALL_DATA" not in sql and "PG_WRITE_ALL_DATA" not in sql
    assert not re.search(r"\bTO\s+PUBLIC\b", sql)


def test_ingest_never_touches_meta():
    sql = _all_sql()
    for grant in re.findall(r"GRANT[^;]*TO whales_ingest", sql):
        assert "meta" not in grant


def test_reviewer_cannot_supply_reviewed_by():
    sql = _all_sql()
    for grant in re.findall(r"GRANT INSERT \(([^)]*)\)[^;]*TO whales_reviewer", sql):
        assert "reviewed_by" not in grant


def test_every_check_constraint_is_named():
    # an unnamed CHECK gets a generated name, which a later migration cannot reliably drop
    sql = _all_sql()
    for m in re.finditer(r"\bCHECK\s*\(", sql):
        before = sql[: m.start()].rstrip()
        assert re.search(r"CONSTRAINT\s+\w+$", before), (
            f"unnamed CHECK near: {sql[m.start() : m.start() + 60]}"
        )


def test_bootstrap_grants_set_without_inheriting_owner():
    stmts = admin.bootstrap_statements("me@firm.com", "whales_dev")
    assert 'GRANT whales_owner TO "me@firm.com" WITH INHERIT FALSE, SET TRUE' in stmts
    assert 'GRANT CREATE ON DATABASE "whales_dev" TO whales_owner' in stmts
    assert sum("CREATE ROLE" in s for s in stmts) == 3
