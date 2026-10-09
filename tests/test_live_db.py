"""Live checks against WHALES_DB_NAME (W-004, W-039). Run with: pytest -m live

Needs `az login` as the Entra admin, WHALES_DB_HOST and WHALES_DB_NAME in .env, and a firewall rule for this
machine. Everything that writes runs inside a transaction that is rolled back.
"""

import os

import psycopg
import pytest

from whales.cli import load_env_file
from whales.db import admin, migrate
from whales.db.connect import Database, DbSettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def db():
    load_env_file()
    if not os.environ.get("WHALES_DB_HOST"):
        pytest.skip("WHALES_DB_HOST not set")
    database = Database(DbSettings.from_env())
    yield database
    database.close()


def _one(db, sql, params=()):
    return db.run(sql, params)[0][0]


def test_migrations_are_current(db):
    assert migrate.pending(migrate.discover(), migrate.applied_versions(db)) == []


def test_everything_is_owned_by_whales_owner(db):
    assert db.run(migrate.NOT_OWNED_SQL, {"s": migrate.SCHEMAS, "o": migrate.OWNER_ROLE}) == []


def test_public_cannot_connect(db):
    paths = admin.connect_paths(db, db.settings.dbname)
    assert paths and not paths[0].public_has_connect


def test_admin_memberships(db):
    rows = db.run(
        "SELECT r.rolname, m.inherit_option, m.set_option FROM pg_auth_members m "
        "JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles u ON u.oid = m.member "
        "WHERE u.rolname = current_user AND m.set_option "
        "AND r.rolname IN ('whales_owner', 'whales_ingest', 'whales_reviewer')"
    )
    got = {name: inherit for name, inherit, _set in rows}
    assert got.get("whales_owner") is False and got.get("whales_ingest") is False
    assert got.get("whales_reviewer") is True


ING, REV = "whales_ingest", "whales_reviewer"


@pytest.mark.parametrize(
    ("role", "kind", "target", "privilege", "expected"),
    [
        (ING, "schema", "meta", "USAGE", False),
        (ING, "table", "letters.source", "UPDATE", False),
        (ING, "table", "core.manager", "INSERT", False),
        (ING, "column", "letters.document_file.use_allowed", "UPDATE", False),
        (ING, "column", "letters.expected.status_by", "UPDATE", False),
        (ING, "table", "letters.mention", "INSERT", True),
        (ING, "table", "letters.rating_verdict", "INSERT", False),
        (REV, "column", "letters.rating_verdict.verdict", "INSERT", True),
        (REV, "column", "letters.rating_verdict.reviewed_by", "INSERT", False),
        (REV, "table", "letters.mention", "UPDATE", False),
        (REV, "schema", "raw", "USAGE", False),
    ],
)
def test_role_privileges(db, role, kind, target, privilege, expected):
    if kind == "column":
        table, column = target.rsplit(".", 1)
        sql, params = "SELECT has_column_privilege(%s, %s, %s, %s)", (role, table, column, privilege)
    else:
        sql, params = f"SELECT has_{kind}_privilege(%s, %s, %s)", (role, target, privilege)
    assert _one(db, sql, params) is expected


def test_no_role_can_delete(db):
    rows = db.run(
        "SELECT table_schema || '.' || table_name, grantee FROM information_schema.role_table_grants "
        "WHERE privilege_type = 'DELETE' AND grantee IN ('whales_ingest', 'whales_reviewer')"
    )
    assert rows == []


def test_ingest_cannot_forge_permissions_or_extract_a_forbidden_copy(db):
    """As owner: a manager and a source that forbids model use. As ingest: a copy claiming use is allowed.
    The trigger must overwrite the claim, and an extraction run on that copy must be refused."""
    conn = db.connection()
    with _rollback(conn) as cur:
        cur.execute("SET LOCAL ROLE whales_owner")
        manager_id = cur.execute(
            "INSERT INTO core.manager (slug, name, kind) VALUES ('zz-test', 'Test', 'manager') RETURNING id"
        ).fetchone()[0]
        source_id = cur.execute(
            "INSERT INTO letters.source (slug, manager_id, name, url, tier, mode, cadence, "
            "access_restricted, storage_allowed, use_allowed, permission_basis) VALUES ('zz-test', %s, "
            "'Test', 'https://x.test', 1, 'auto', 'quarterly', false, false, false, 'test: use forbidden') "
            "RETURNING id",
            (manager_id,),
        ).fetchone()[0]
        cur.execute("SET LOCAL ROLE whales_ingest")
        document_id = cur.execute(
            "INSERT INTO letters.document (manager_id, title, kind, published_on, published_on_basis) "
            "VALUES (%s, 'Test letter', 'memo', '2026-10-01', 'stated') RETURNING id",
            (manager_id,),
        ).fetchone()[0]
        file_id, use_allowed, machine_read_ok = cur.execute(
            "INSERT INTO letters.document_file (document_id, source_id, tier, url, sha256, content_type, "
            "byte_size, collected, use_allowed, storage_allowed, permission_basis, raw_kept, "
            "machine_read_ok) VALUES "
            "(%s, %s, 3, 'https://x.test/a.pdf', repeat('a', 64), 'application/pdf', 10, 'auto', true, true, "
            "'forged', false, true) RETURNING id, use_allowed, machine_read_ok",
            (document_id, source_id),
        ).fetchone()
        assert (use_allowed, machine_read_ok) == (False, False)
        run_id = cur.execute("INSERT INTO raw.run_log (command) VALUES ('test') RETURNING id").fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
            cur.execute(
                "INSERT INTO letters.extraction_run (document_file_id, document_id, task, run_id, model, "
                "prompt_version) VALUES (%s, %s, 'mentions', %s, 'test', 'v0')",
                (file_id, document_id, run_id),
            )


class _rollback:
    """A transaction that always rolls back, yielding a cursor."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.tx = self.conn.transaction(force_rollback=True)
        self.tx.__enter__()
        self.cur = self.conn.cursor()
        return self.cur

    def __exit__(self, *exc):
        self.cur.close()
        return self.tx.__exit__(*exc)
