import io
import json
import subprocess

import pytest

from whales.db import admin, connect


def _done(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_az_cli_token_returns_stripped_token():
    assert connect.token_from_az_cli(run=lambda *a, **k: _done(stdout="tok\n")) == "tok"


def test_az_cli_token_failure_raises():
    with pytest.raises(connect.TokenError, match="get-access-token failed"):
        connect.token_from_az_cli(run=lambda *a, **k: _done(returncode=1, stderr="not logged in"))


def test_container_identity_sends_header_and_client_id(monkeypatch):
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://identity.local/msi/token")
    monkeypatch.setenv("IDENTITY_HEADER", "secret-header")
    seen = {}

    def opener(request, timeout):
        seen["url"], seen["header"] = request.full_url, request.get_header("X-identity-header")
        return io.BytesIO(json.dumps({"access_token": "abc"}).encode())

    assert connect.token_from_container_identity("client-1", opener=opener) == "abc"
    assert "client_id=client-1" in seen["url"]
    assert "resource=https%3A%2F%2Fossrdbms-aad.database.windows.net" in seen["url"]
    assert seen["header"] == "secret-header"


def test_container_identity_without_env_raises(monkeypatch):
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    monkeypatch.delenv("IDENTITY_HEADER", raising=False)
    with pytest.raises(connect.TokenError, match="not inside a Container Apps job"):
        connect.token_from_container_identity("client-1")


def test_default_token_source_in_container_needs_client_id(monkeypatch):
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://identity.local")
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    with pytest.raises(connect.TokenError, match="AZURE_CLIENT_ID"):
        connect.default_token_source()


def test_settings_require_host_and_name(monkeypatch):
    monkeypatch.delenv("WHALES_DB_HOST", raising=False)
    with pytest.raises(connect.SettingsError):
        connect.DbSettings.from_env("postgres")


def test_settings_default_user_is_signed_in_developer(monkeypatch):
    monkeypatch.setenv("WHALES_DB_HOST", "db.example")
    monkeypatch.delenv("WHALES_DB_USER", raising=False)
    s = connect.DbSettings.from_env("whales_dev", run=lambda *a, **k: _done(stdout="me@firm.com\n"))
    assert (s.host, s.dbname, s.user, s.port) == ("db.example", "whales_dev", "me@firm.com", 5432)


def test_revoke_statement_quotes_the_name():
    assert admin.revoke_public_connect_sql('we"ird') == 'REVOKE CONNECT ON DATABASE "we""ird" FROM PUBLIC'


@pytest.mark.parametrize(
    ("can_connect", "is_owner", "without_public", "loses"),
    [
        (True, False, False, True),  # connects only through PUBLIC
        (True, True, False, False),  # owner
        (True, False, True, False),  # own grant or an inherited group's grant
        (False, False, False, False),  # cannot connect today anyway
    ],
)
def test_would_lose_access(can_connect, is_owner, without_public, loses):
    p = admin.ConnectPath("r", True, can_connect, is_owner, without_public, True)
    assert p.would_lose_access is loses
