"""Plain numbered SQL migrations (W-022, W-039).

Files live in ``src/whales/db/migrations/`` as ``NNNN_name.sql``. Each is applied in one transaction, as the
owner role (``SET LOCAL ROLE whales_owner``), by an admin; never by the ingest job. Applied files are
recorded in ``raw.schema_migration`` with a checksum, and an applied file that has since been edited is
refused: write a new migration instead.

Checksums are taken over the text with line endings normalised to ``\\n``, because git rewrites line endings
on Windows checkouts and the same migration must check out identical on every machine.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .connect import Database

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
OWNER_ROLE = "whales_owner"
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    """A migration set that must not be applied as it stands."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return checksum(self.sql)


def checksum(sql: str) -> str:
    return hashlib.sha256(sql.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Every migration file in version order. Gaps, duplicates and badly named .sql files are refused."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        m = _NAME.match(path.name)
        if not m:
            raise MigrationError(f"badly named migration file: {path.name} (want NNNN_name.sql)")
        found.append(Migration(int(m.group(1)), m.group(2), path.read_text(encoding="utf-8")))
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise MigrationError(
            f"migration versions must run 1, 2, 3... without gaps or repeats; found {versions}"
        )
    return found


def pending(available: list[Migration], applied: dict[int, str]) -> list[Migration]:
    """The migrations still to apply. ``applied`` maps version to recorded checksum. An applied migration
    whose file has changed, or a recorded version with no file, stops everything."""
    by_version = {m.version: m for m in available}
    for version, recorded in sorted(applied.items()):
        m = by_version.get(version)
        if m is None:
            raise MigrationError(f"migration {version} is recorded in the database but has no file")
        if m.checksum != recorded:
            raise MigrationError(
                f"migration {version:04d}_{m.name} was edited after it was applied; write a new migration"
            )
    return [m for m in available if m.version not in applied]


SCHEMAS = ["meta", "raw", "core", "letters", "api"]

# Anything in our schemas not owned by whales_owner: the schemas themselves, relations (tables, views,
# indexes, sequences), functions and types (domains included).
NOT_OWNED_SQL = """
SELECT nspname FROM pg_namespace
 WHERE nspname = ANY(%(s)s) AND nspowner <> %(o)s::regrole
UNION ALL
SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = ANY(%(s)s) AND c.relowner <> %(o)s::regrole
UNION ALL
SELECT n.nspname || '.' || p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = ANY(%(s)s) AND p.proowner <> %(o)s::regrole
UNION ALL
SELECT n.nspname || '.' || t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
 WHERE n.nspname = ANY(%(s)s) AND t.typowner <> %(o)s::regrole
"""


def applied_versions(db: Database) -> dict[int, str]:
    exists = db.run("SELECT to_regclass('meta.schema_migration') IS NOT NULL")[0][0]
    if not exists:
        return {}
    return {v: c for v, c in db.run("SELECT version, checksum FROM meta.schema_migration ORDER BY version")}


def apply(db: Database, migration: Migration) -> None:
    """One migration, in one transaction, as the owner role, recorded in the same transaction. If anything
    in our schemas ends up owned by another role, the whole migration is rolled back."""
    conn = db.connection()
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {OWNER_ROLE}")
        conn.execute(migration.sql)
        stray = [r[0] for r in conn.execute(NOT_OWNED_SQL, {"s": SCHEMAS, "o": OWNER_ROLE}).fetchall()]
        if stray:
            raise MigrationError(f"objects not owned by {OWNER_ROLE}: {stray}")
        conn.execute(
            "INSERT INTO meta.schema_migration (version, name, checksum) VALUES (%s, %s, %s)",
            (migration.version, migration.name, migration.checksum),
        )
