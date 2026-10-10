"""Server administration for the shared server (W-004), run by the Entra admin from a developer's machine.

The shared server is safe only if no login role can reach a database it was not granted. By default every
database grants CONNECT to PUBLIC, so the first step on each database is to revoke that. Before revoking, see
who would lose access: a role that today connects only through PUBLIC would be locked out.

PostgreSQL 15 and later already deny CREATE on schema ``public`` to PUBLIC, so only CONNECT needs revoking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .connect import Database

# For each login role: can it connect now, and would it still if PUBLIC lost CONNECT? A role keeps access if
# it owns the database or is a superuser (both reported as is_owner), or holds CONNECT directly or through a
# role it inherits from (pg_has_role USAGE). ACL grantee 0 is PUBLIC.
CONNECT_PATHS_SQL = """
SELECT r.rolname,
       r.rolinherit,
       has_database_privilege(r.oid, d.oid, 'CONNECT') AS can_connect,
       d.datdba = r.oid OR r.rolsuper AS is_owner,
       EXISTS (
           SELECT 1
           FROM aclexplode(COALESCE(d.datacl, acldefault('d', d.datdba))) a
           WHERE a.privilege_type = 'CONNECT'
             AND a.grantee <> 0
             AND pg_has_role(r.oid, a.grantee, 'USAGE')
       ) AS connect_without_public,
       EXISTS (
           SELECT 1
           FROM aclexplode(COALESCE(d.datacl, acldefault('d', d.datdba))) a
           WHERE a.privilege_type = 'CONNECT' AND a.grantee = 0
       ) AS public_has_connect
FROM pg_roles r
CROSS JOIN pg_database d
WHERE d.datname = %s
  AND r.rolcanlogin
ORDER BY r.rolname
"""


@dataclass(frozen=True)
class ConnectPath:
    role: str
    inherits: bool
    can_connect: bool
    is_owner: bool
    without_public: bool
    public_has_connect: bool

    @property
    def would_lose_access(self) -> bool:
        """True if revoking CONNECT from PUBLIC would lock this role out."""
        return self.can_connect and not (self.is_owner or self.without_public)


def connect_paths(db: Database, dbname: str) -> list[ConnectPath]:
    return [ConnectPath(*row) for row in db.run(CONNECT_PATHS_SQL, (dbname,))]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def revoke_public_connect_sql(dbname: str) -> str:
    return f"REVOKE CONNECT ON DATABASE {quote_ident(dbname)} FROM PUBLIC"


OWNER, INGEST, REVIEWER = "whales_owner", "whales_ingest", "whales_reviewer"
IDENTITY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,127}$")


def add_identity_statements(identity: str, group: str, dbname: str) -> list[str]:
    """Register a managed identity as a Postgres login role, put it in one group, and let it connect to one
    database (W-039, W-042). Run in the ``postgres`` database by the Entra admin. Idempotent.

    ``owner``: SET only, never inherited, so the admin job acts as owner only by saying so. ``ingest``:
    inherited, because the collector simply works as ingest. CONNECT goes to the login role, never the group.
    """
    if not IDENTITY_NAME.match(identity):
        raise ValueError(f"not a managed-identity name: {identity!r}")
    q = quote_ident
    statements = [
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{identity}') "
        f"THEN PERFORM pgaadauth_create_principal('{identity}', false, false); END IF; END $$"
    ]
    if group == "owner":
        statements.append(f"GRANT {OWNER} TO {q(identity)} WITH INHERIT FALSE, SET TRUE")
    elif group == "ingest":
        statements.append(f"GRANT {INGEST} TO {q(identity)} WITH INHERIT TRUE, SET TRUE")
    else:
        raise ValueError(f"group must be owner or ingest, not {group!r}")
    statements.append(f"GRANT CONNECT ON DATABASE {q(dbname)} TO {q(identity)}")
    return statements


def bootstrap_statements(admin_role: str, dbname: str) -> list[str]:
    """The group roles (cluster-wide, so created here and not in a migration) and their database rights
    (W-039). Idempotent.

    On PostgreSQL 16 and later, a CREATEROLE admin who creates a role is granted it WITH ADMIN only, so the
    admin must grant itself SET to use ``SET ROLE``. INHERIT FALSE on owner and ingest means an ordinary
    session never acts as either without saying so; reviewer is inherited, because the admin reviews."""
    q = quote_ident
    statements = [
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
        f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$"
        for role in (OWNER, INGEST, REVIEWER)
    ]
    statements += [
        f"GRANT {OWNER} TO {q(admin_role)} WITH INHERIT FALSE, SET TRUE",
        f"GRANT {INGEST} TO {q(admin_role)} WITH INHERIT FALSE, SET TRUE",
        f"GRANT {REVIEWER} TO {q(admin_role)} WITH INHERIT TRUE, SET TRUE",
        f"GRANT CREATE ON DATABASE {q(dbname)} TO {OWNER}",
        f"REVOKE TEMPORARY ON DATABASE {q(dbname)} FROM PUBLIC",
    ]
    return statements
