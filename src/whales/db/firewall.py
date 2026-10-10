"""A temporary firewall opening for this machine, for the rare admin step run from a laptop (W-042).

Routine work runs in Azure, inside the server's "Azure services" rule, and needs no opening. The few one-off
steps that need the Entra admin's own rights (creating roles, registering identities) run from a laptop:
``whales --open-firewall ...`` adds a rule for this machine's public address for the length of one command
and always removes it afterwards, even if the command fails. ``whales db close-firewall`` removes any
temporary rule left behind (for example after a crash).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

PREFIXES = ("whales-temp-", "whales-dev-temp-")


class FirewallError(RuntimeError):
    pass


def public_ip(fetch=urllib.request.urlopen) -> str:
    with fetch("https://api.ipify.org", timeout=15) as r:
        ip = r.read().decode("ascii", "replace").strip()
    try:
        if ipaddress.ip_address(ip).version != 4:
            raise ValueError
    except ValueError as e:
        raise FirewallError(f"unexpected public-address answer: {ip[:60]!r}") from e
    return ip


def _server_and_group() -> tuple[str, str]:
    host = os.environ.get("WHALES_DB_HOST", "")
    group = os.environ.get("WHALES_DB_RESOURCE_GROUP", "")
    if not host or not group:
        raise FirewallError("WHALES_DB_HOST and WHALES_DB_RESOURCE_GROUP must be set (see .env.example)")
    return host.split(".", 1)[0], group


def _az(*args: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["az", "postgres", "flexible-server", "firewall-rule", *args, "--only-show-errors"],
        capture_output=True,
        text=True,
        shell=(os.name == "nt"),
    )
    if proc.returncode != 0:
        raise FirewallError(f"az firewall-rule {args[0]} failed: {proc.stderr.strip()[:400]}")
    return proc


def rule_name(now: float | None = None) -> str:
    host = re.sub(r"[^a-z0-9-]", "-", socket.gethostname().lower())[:30]
    return f"whales-temp-{host}-{int(now or time.time())}"


@contextmanager
def opening() -> Iterator[str]:
    server, group = _server_and_group()
    ip = public_ip()
    name = rule_name()
    _az(
        "create",
        "-g",
        group,
        "--server-name",
        server,
        "--name",
        name,
        "--start-ip-address",
        ip,
        "--end-ip-address",
        ip,
    )
    print(f"(firewall opened for {ip} as {name})")
    try:
        yield ip
    finally:
        _az("delete", "-g", group, "--server-name", server, "--name", name, "--yes")
        print(f"(firewall rule {name} removed)")


def close_leftovers() -> list[str]:
    """Delete every temporary rule this project creates; return their names."""
    server, group = _server_and_group()
    out = _az("list", "-g", group, "--server-name", server, "--query", "[].name", "-o", "tsv").stdout
    names = [n.strip() for n in out.splitlines() if n.strip().startswith(PREFIXES)]
    for n in names:
        _az("delete", "-g", group, "--server-name", server, "--name", n, "--yes")
    return names
