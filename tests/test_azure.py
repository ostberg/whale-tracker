"""The Azure move (W-042): identity grants, the firewall helper and the deploy commands, without Azure."""

import importlib.util
import io
from pathlib import Path

import pytest

from whales.db import admin, firewall

REPO = Path(__file__).resolve().parents[1]


def _deploy():
    spec = importlib.util.spec_from_file_location("deploy", REPO / "infra" / "deploy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_owner_identity_sets_but_never_inherits():
    stmts = admin.add_identity_statements("id-whales-admin", "owner", "whales_dev")
    assert "pgaadauth_create_principal('id-whales-admin', false, false)" in stmts[0]
    assert 'GRANT whales_owner TO "id-whales-admin" WITH INHERIT FALSE, SET TRUE' in stmts
    assert 'GRANT CONNECT ON DATABASE "whales_dev" TO "id-whales-admin"' in stmts


def test_ingest_identity_inherits_ingest_only():
    stmts = admin.add_identity_statements("id-whales-ingest", "ingest", "whales_dev")
    assert 'GRANT whales_ingest TO "id-whales-ingest" WITH INHERIT TRUE, SET TRUE' in stmts
    assert not any("whales_owner" in s for s in stmts)


@pytest.mark.parametrize("name", ["x'; DROP ROLE y; --", "a b", ""])
def test_identity_names_are_checked(name):
    with pytest.raises(ValueError):
        admin.add_identity_statements(name, "ingest", "whales_dev")


def test_public_ip_must_be_ipv4():
    assert firewall.public_ip(lambda *a, **k: io.BytesIO(b"173.70.88.249\n")) == "173.70.88.249"
    with pytest.raises(firewall.FirewallError):
        firewall.public_ip(lambda *a, **k: io.BytesIO(b"<html>blocked</html>"))


def test_rule_names_are_recognised_for_cleanup():
    assert firewall.rule_name(1_800_000_000).startswith(firewall.PREFIXES)


def test_collect_job_runs_as_ingest_with_no_admin_rights():
    deploy = _deploy()
    s = deploy.load_settings()
    ids = {
        "ingest": {"id": "/ids/ingest", "clientId": "c-ingest"},
        "admin": {"id": "/ids/admin", "clientId": "c-admin"},
    }
    collect_job = next(j for j in s["job"] if j["name"] == "job-whales-collect-sec")
    cmd = deploy.job_command(s, collect_job, "reg.azurecr.io/whale-tracker:abc", ids, update=False)
    assert cmd[cmd.index("--mi-user-assigned") + 1] == "/ids/ingest"
    assert "WHALES_DB_USER=id-whales-ingest" in cmd and "AZURE_CLIENT_ID=c-ingest" in cmd
    assert cmd[cmd.index("--trigger-type") + 1] == "Schedule"
    assert cmd[-3:] == ["collect", "sec", "--apply"]
    assert not any("admin" in part for part in cmd)


def test_admin_job_is_manual_and_uses_our_registry():
    deploy = _deploy()
    s = deploy.load_settings()
    ids = {
        "ingest": {"id": "/ids/ingest", "clientId": "c-ingest"},
        "admin": {"id": "/ids/admin", "clientId": "c-admin"},
    }
    admin_job = next(j for j in s["job"] if j["name"] == "job-whales-admin")
    cmd = deploy.job_command(s, admin_job, "img", ids, update=False)
    assert cmd[cmd.index("--trigger-type") + 1] == "Manual"
    assert cmd[cmd.index("--registry-server") + 1] == f"{s['registry']}.azurecr.io"
    update = deploy.job_command(s, admin_job, "img2", ids, update=True)
    assert update[:3] == ["containerapp", "job", "update"] and "img2" in update
