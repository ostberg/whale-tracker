"""Live checks against WHALES_DB_NAME (W-004, W-039). Run with: pytest -m live

Needs `az login` as the Entra admin, WHALES_DB_HOST and WHALES_DB_NAME in .env, and a firewall rule for this
machine. Everything that writes runs inside a transaction that is rolled back.
"""

import os
from datetime import date

import psycopg
import pytest

from whales import config, predictions
from whales.cli import load_env_file
from whales.db import admin, migrate, sync
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
        (ING, "table", "letters.prediction_link", "INSERT", True),
        (ING, "table", "letters.prediction_check", "INSERT", True),
        (ING, "table", "letters.prediction_score", "INSERT", False),
        (ING, "table", "letters.prediction", "UPDATE", False),
        (REV, "column", "letters.prediction_score.check_id", "INSERT", True),
        (REV, "column", "letters.prediction_score.reviewed_by", "INSERT", False),
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


def test_config_is_in_sync(db):
    changes = sync.plan(config.load(), sync.read_current(db))
    assert [c.what for c in changes if c.sql] == []


def test_synced_sources_are_inactive_until_approved(db):
    rows = db.run(
        "SELECT slug FROM letters.source WHERE active AND (approved_by IS NULL OR approved_at IS NULL)"
    )
    assert rows == []


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


MSFT_LETTER = {
    "predictions": [
        {
            "k": 1,
            "role": "premise",
            "subject": "MSFT capex growth",
            "metric": "capex",
            "ticker": "MSFT",
            "comparator": "above",
            "threshold": 30,
            "unit": "% y/y",
            "window_from": "2026-01-01",
            "window_to": "2026-06-30",
            "timing": "at_end",
            "confidence": "medium",
            "basis": "data",
            "claim": "Capex grows over 30%.",
            "quote": "If capex rises by over 30%",
        },
        {
            "k": 2,
            "role": "asserted",
            "subject": "MSFT share price",
            "metric": "price",
            "ticker": "MSFT",
            "comparator": "down",
            "window_to": "2026-06-30",
            "timing": "any_time",
            "confidence": "high",
            "basis": "reasoning",
            "claim": "Shares fall.",
            "quote": "investors will punish the shares",
            "premises": [1],
        },
        {
            "k": 3,
            "role": "asserted",
            "subject": "MSFT forward P/E",
            "metric": "valuation_multiple",
            "comparator": "at_most",
            "threshold": 18,
            "unit": "x",
            "window_to": "2030-12-31",
            "timing": "any_time",
            "confidence": "high",
            "basis": "reasoning",
            "claim": "The multiple compresses to 18x.",
            "quote": "compress to 18x",
            "premises": [1],
            "caused_by": [2],
        },
        {
            "k": 4,
            "role": "asserted",
            "subject": "Brent crude",
            "metric": "commodity_price",
            "topic": "oil",
            "comparator": "below",
            "threshold": 100,
            "unit": "USD/bbl",
            "window_to": "2030-12-31",
            "timing": "any_time",
            "confidence": "high",
            "basis": "assertion",
            "claim": "Brent trades below $100.",
            "quote": "below $100 by the end of the year",
        },
    ]
}


def test_prediction_states_follow_premises_and_verdicts(db):
    """W-048, on a letter dated 2026-01-01. Claim 1 is a premise of 2 (window closed) and 3 (window open).
    While the premise is unscored, 2 awaits it. The premise scored wrong voids 2 and 3. A check on 4 makes
    it proposed; a verdict makes it scored. The track record counts asserted claims only. Rolled back."""
    x = predictions.parse(MSFT_LETTER, date(2026, 1, 1), {"oil"})
    conn = db.connection()
    with _rollback(conn) as cur:
        cur.execute("SET LOCAL ROLE whales_owner")
        manager_id = cur.execute(
            "INSERT INTO core.manager (slug, name, kind) VALUES ('zz-test', 'Test', 'manager') RETURNING id"
        ).fetchone()[0]
        source_id = cur.execute(
            "INSERT INTO letters.source (slug, manager_id, name, url, tier, mode, cadence, "
            "access_restricted, storage_allowed, use_allowed, permission_basis) VALUES ('zz-test', %s, "
            "'Test', 'https://x.test', 1, 'manual', 'quarterly', false, true, true, 'test') RETURNING id",
            (manager_id,),
        ).fetchone()[0]
        cur.execute("SET LOCAL ROLE whales_ingest")
        document_id = cur.execute(
            "INSERT INTO letters.document (manager_id, title, kind, published_on, published_on_basis) "
            "VALUES (%s, 'Test letter', 'quarterly_letter', '2026-01-01', 'stated') RETURNING id",
            (manager_id,),
        ).fetchone()[0]
        file_id = cur.execute(
            "INSERT INTO letters.document_file (document_id, source_id, url, sha256, content_type, "
            "byte_size, collected, raw_kept) VALUES (%s, %s, 'https://x.test/b.pdf', repeat('b', 64), "
            "'application/pdf', 10, 'manual', false) RETURNING id",
            (document_id, source_id),
        ).fetchone()[0]
        run_id = cur.execute("INSERT INTO raw.run_log (command) VALUES ('test') RETURNING id").fetchone()[0]
        extraction_id = cur.execute(
            "INSERT INTO letters.extraction_run (document_file_id, document_id, task, run_id, model, "
            "prompt_version, status) VALUES (%s, %s, 'predictions', %s, 'test', %s, 'ok') RETURNING id",
            (file_id, document_id, run_id, predictions.PROMPT_VERSION),
        ).fetchone()[0]
        ids = predictions.store(cur, extraction_id, x)

        def states():
            return dict(
                cur.execute(
                    "SELECT ordinal, state FROM letters.prediction_state WHERE extraction_run_id = %s",
                    (extraction_id,),
                ).fetchall()
            )

        assert states() == {1: "due", 2: "awaiting_premise", 3: "open", 4: "open"}
        cur.execute("SET LOCAL ROLE whales_reviewer")
        cur.execute(
            "INSERT INTO letters.prediction_score (prediction_id, outcome) VALUES (%s, 'wrong')", (ids[1],)
        )
        assert states() == {1: "scored", 2: "void", 3: "void", 4: "open"}
        cur.execute("SET LOCAL ROLE whales_ingest")
        check_id = cur.execute(
            "INSERT INTO letters.prediction_check (prediction_id, run_id, method, source, observed, as_of, "
            "proposed_outcome) VALUES (%s, %s, 'data', 'test series', '92.1 USD/bbl', '2026-10-01', 'right') "
            "RETURNING id",
            (ids[4], run_id),
        ).fetchone()[0]
        assert states()[4] == "proposed"
        cur.execute("SET LOCAL ROLE whales_reviewer")
        cur.execute(
            "INSERT INTO letters.prediction_score (prediction_id, check_id, outcome) "
            "VALUES (%s, %s, 'right')",
            (ids[4], check_id),
        )
        assert states()[4] == "scored"
        record = cur.execute(
            "SELECT right_calls, wrong_calls, void_calls, open_calls, dated_calls, data_backed_calls, "
            "reasoned_calls, asserted_calls, confident_misses, trust_flag FROM letters.track_record "
            "WHERE manager = 'zz-test'"
        ).fetchone()
        assert record == (1, 0, 2, 0, 3, 0, 2, 1, 0, None)
        # Trust is earned but quickly lost (W-051): one confident miss raises the flag at once.
        cur.execute(
            "INSERT INTO letters.prediction_score (prediction_id, outcome) VALUES (%s, 'wrong')", (ids[2],)
        )
        wrong, void, flag, baseline = cur.execute(
            "SELECT t.wrong_calls, t.void_calls, t.trust_flag, a.baseline FROM letters.track_record t "
            "JOIN letters.author_trust a ON a.manager = t.manager WHERE t.manager = 'zz-test'"
        ).fetchone()
        assert (wrong, void, flag) == (1, 1, "recent_confident_miss")
        assert baseline == "high"  # a quarterly letter by a manager, from config/trust.toml


def test_extraction_candidates_query_runs(db):
    """The candidates SQL against the real schema (its first Azure run failed on an ambiguous column)."""
    from whales import extract

    found = extract.candidates(db, limit=3)
    assert isinstance(found, list) and len(found) <= 3
    for c in found:
        assert isinstance(c.file_id, int) and isinstance(c.document_id, int) and c.published_on


def test_an_expectation_is_marked_loaded_by_a_document_from_any_of_the_managers_sources(db):
    """W-055: a manual source's expectation is satisfied by the automatic route's copy of the same letter."""
    from whales import expected

    conn = db.connection()
    with _rollback(conn) as cur:
        cur.execute("SET LOCAL ROLE whales_owner")
        manager_id = cur.execute(
            "INSERT INTO core.manager (slug, name, kind) VALUES ('zz-test', 'Test', 'manager') RETURNING id"
        ).fetchone()[0]
        manual, auto = (
            cur.execute(
                "INSERT INTO letters.source (slug, manager_id, name, url, tier, mode, cadence, "
                "access_restricted, storage_allowed, use_allowed, permission_basis) VALUES (%s, %s, 'T', "
                "'https://x.test', 1, %s, 'quarterly', false, true, true, 'test') RETURNING id",
                (slug, manager_id, mode),
            ).fetchone()[0]
            for slug, mode in (("zz-manual", "manual"), ("zz-auto", "auto"))
        )
        cur.execute("SET LOCAL ROLE whales_ingest")
        cur.execute(
            "INSERT INTO letters.expected (source_id, period_end, due_from, due_to) "
            "VALUES (%s, '2026-09-30', '2026-10-21', '2026-12-14')",
            (manual,),
        )
        document_id = cur.execute(
            "INSERT INTO letters.document (manager_id, title, kind, period_end, published_on, "
            "published_on_basis) VALUES (%s, 'Q3 letter', 'quarterly_letter', '2026-09-30', '2026-11-02', "
            "'stated') RETURNING id",
            (manager_id,),
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO letters.document_file (document_id, source_id, url, sha256, content_type, "
            "byte_size, collected, raw_kept) VALUES (%s, %s, 'https://x.test/q3.pdf', repeat('c', 64), "
            "'application/pdf', 10, 'auto', false)",
            (document_id, auto),
        )
        assert cur.execute(expected.MARK_LOADED_SQL).rowcount == 1
        status, doc = cur.execute(
            "SELECT status, document_id FROM letters.expected WHERE source_id = %s", (manual,)
        ).fetchone()
        assert (status, doc) == ("loaded", document_id)


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
