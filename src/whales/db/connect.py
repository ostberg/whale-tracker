"""Postgres connections signed in with Microsoft Entra tokens (W-004).

Inside Azure, the Container Apps identity endpoint issues a token for the job's user-assigned identity. On a
developer's machine, ``az account get-access-token`` issues one for whoever ran ``az login``. The token goes
in the password slot and lasts about an hour, so a failed statement reconnects once with a fresh token.

The pattern is copied from the Tamale repo's ``tamale.context.backends``; the module is not shared, because
the two projects stay separate (W-002). No Azure SDK: plain HTTP and the az CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

PG_TOKEN_RESOURCE = "https://ossrdbms-aad.database.windows.net"  # the Entra audience for Azure PostgreSQL


class TokenError(RuntimeError):
    """No Entra token could be obtained."""


class SettingsError(RuntimeError):
    """The database settings are incomplete."""


def token_from_container_identity(
    client_id: str,
    *,
    resource: str = PG_TOKEN_RESOURCE,
    opener: Callable = urllib.request.urlopen,
    timeout: int = 10,
) -> str:
    """A token from the Container Apps identity endpoint (``IDENTITY_ENDPOINT`` and ``IDENTITY_HEADER``).
    ``client_id`` picks the user-assigned identity; the job has no system-assigned one."""
    endpoint = os.environ.get("IDENTITY_ENDPOINT", "")
    header = os.environ.get("IDENTITY_HEADER", "")
    if not (endpoint and header):
        raise TokenError("IDENTITY_ENDPOINT or IDENTITY_HEADER not set: not inside a Container Apps job?")
    query = urllib.parse.urlencode(
        {"api-version": "2019-08-01", "resource": resource, "client_id": client_id}
    )
    request = urllib.request.Request(f"{endpoint}?{query}", headers={"X-IDENTITY-HEADER": header})
    try:
        with opener(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as e:
        raise TokenError(f"identity endpoint failed: {e}") from e
    token = body.get("access_token")
    if not token:
        raise TokenError("identity endpoint returned no access_token")
    return token


def _az(args: list[str], run: Callable) -> subprocess.CompletedProcess:
    exe = os.environ.get("AZ_CLI", "az")
    # az is az.cmd on Windows, which only a shell can start
    return run([exe, *args], capture_output=True, text=True, shell=(os.name == "nt"))


def token_from_az_cli(*, resource: str = PG_TOKEN_RESOURCE, run: Callable = subprocess.run) -> str:
    """A token from the developer's own ``az login``: the local path, never the job's."""
    proc = _az(
        ["account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"], run
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise TokenError(f"az account get-access-token failed: {(proc.stderr or '').strip()[:200]}")
    return proc.stdout.strip()


def default_token_source() -> Callable[[], str]:
    """The container identity inside Azure, the az CLI anywhere else."""
    if os.environ.get("IDENTITY_ENDPOINT"):
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        if not client_id:
            raise TokenError("AZURE_CLIENT_ID not set: the identity's client id must be passed to the job")
        return lambda: token_from_container_identity(client_id)
    return lambda: token_from_az_cli()


def signed_in_user(run: Callable = subprocess.run) -> str:
    """The developer's Entra sign-in name, which is also their Postgres role name."""
    proc = _az(["ad", "signed-in-user", "show", "--query", "userPrincipalName", "-o", "tsv"], run)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SettingsError("WHALES_DB_USER not set and `az ad signed-in-user show` failed")
    return proc.stdout.strip()


@dataclass(frozen=True)
class DbSettings:
    host: str
    dbname: str
    user: str
    port: int = 5432

    @classmethod
    def from_env(cls, dbname: str | None = None, *, run: Callable = subprocess.run) -> DbSettings:
        """``WHALES_DB_HOST`` and ``WHALES_DB_NAME`` (or ``dbname``) are required. ``WHALES_DB_USER`` defaults
        to the signed-in developer locally; in Azure it must name the job's identity."""
        host = os.environ.get("WHALES_DB_HOST", "").strip()
        name = (dbname or os.environ.get("WHALES_DB_NAME", "")).strip()
        if not host or not name:
            raise SettingsError("WHALES_DB_HOST and WHALES_DB_NAME must be set (see .env.example)")
        user = os.environ.get("WHALES_DB_USER", "").strip() or signed_in_user(run)
        return cls(host=host, dbname=name, user=user, port=int(os.environ.get("WHALES_DB_PORT", "5432")))


class Database:
    """One autocommit connection, opened on first use and reopened once if a statement fails."""

    def __init__(
        self, settings: DbSettings, token_source: Callable[[], str] | None = None, *, role: str | None = None
    ):
        """``role``: a group role to act as for the whole session (``SET ROLE``), e.g. ``whales_ingest``, so a
        developer's run is held to exactly the job's privileges."""
        self.settings = settings
        self._token_source = token_source or default_token_source()
        self._role = role
        self._conn = None

    def _connect(self):
        import psycopg

        s = self.settings
        self._conn = psycopg.connect(
            host=s.host,
            port=s.port,
            dbname=s.dbname,
            user=s.user,
            password=self._token_source(),
            sslmode="require",
            autocommit=True,
            connect_timeout=20,
        )
        if self._role:
            from .admin import quote_ident

            self._conn.execute(f"SET ROLE {quote_ident(self._role)}")
        return self._conn

    def connection(self):
        """The underlying psycopg connection, for work that needs an explicit transaction (migrations)."""
        return self._conn or self._connect()

    def run(self, sql: str, params: tuple = ()) -> list[tuple]:
        for attempt in (1, 2):
            conn = self._conn or self._connect()
            try:
                with conn.cursor() as cur:
                    # None, not (): with an empty tuple psycopg still parses '%' in the SQL as a placeholder
                    cur.execute(sql, params or None)
                    return cur.fetchall() if cur.description else []
            except Exception:  # noqa: BLE001 - an expired token or a dropped connection: once more, fresh
                self.close()
                if attempt == 2:
                    raise
        return []

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
