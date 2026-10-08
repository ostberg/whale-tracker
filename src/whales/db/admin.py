"""Server administration for the shared server (W-004), run by the Entra admin from a developer's machine.

The shared server is safe only if no login role can reach a database it was not granted. By default every
database grants CONNECT to PUBLIC, so the first step on each database is to revoke that. Before revoking, see
who would lose access: a role that today connects only through PUBLIC would be locked out.

PostgreSQL 15 and later already deny CREATE on schema ``public`` to PUBLIC, so only CONNECT needs revoking.
"""

from __future__ import annotations

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
