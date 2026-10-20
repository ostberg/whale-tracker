"""Deploy Whale Tracker to Azure (W-042): resource group, logs, registry, identities, image, environment and
jobs.

    python infra/deploy.py              # report what exists and what would be created; changes nothing
    python infra/deploy.py --apply      # create what is missing, build the image from HEAD, set the jobs

Idempotent: existing resources are left alone, except the jobs, which are updated to the new image and
settings on every apply. Needs `az login`. The image is built from `git archive HEAD`, so uncommitted changes
to tracked files are refused: commit first. Settings: infra/azure.toml. No secrets are stored anywhere; the
Log Analytics key is read from Azure at deploy time and passed straight to the environment.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class DeployError(RuntimeError):
    pass


def load_settings(path: Path = REPO / "infra" / "azure.toml") -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


class Az:
    def __init__(self, subscription: str):
        self.subscription = subscription

    def run(self, *args: str, check: bool = True) -> dict | list | str | None:
        """Run an az command and return its JSON output. With check=False, a failure returns None."""
        cmd = ["az", *args, "--subscription", self.subscription, "-o", "json", "--only-show-errors"]
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=(os.name == "nt"))
        if proc.returncode != 0:
            if check:
                raise DeployError(f"az {' '.join(args[:3])} failed: {proc.stderr.strip()[:600]}")
            return None
        out = proc.stdout.strip()
        return json.loads(out) if out else None


def job_command(settings: dict, job: dict, image: str, ids: dict, update: bool) -> list[str]:
    """The az arguments that create (or update) one job. Pure, for testing."""
    rg, env_name = settings["resource_group"], settings["environment"]
    identity = ids[job["identity"]]
    env_vars = {
        "WHALES_DB_HOST": settings["database"]["host"],
        "WHALES_DB_NAME": settings["database"]["name"],
        "WHALES_DB_USER": settings["identities"][job["identity"]],
        "AZURE_CLIENT_ID": identity["clientId"],
        **settings.get("env", {}),
    }
    pairs = [f"{k}={v}" for k, v in env_vars.items()]
    if update:
        cmd = ["containerapp", "job", "update", "-n", job["name"], "-g", rg, "--image", image]
        cmd += [
            "--replica-timeout",
            str(job["timeout_seconds"]),
            "--set-env-vars",
            *pairs,
            "--args",
            " ".join(job["args"]),  # one string: az refuses a list element starting with "--"
        ]
        if job.get("cron"):
            cmd += ["--cron-expression", job["cron"]]
        return cmd
    cmd = ["containerapp", "job", "create", "-n", job["name"], "-g", rg, "--environment", env_name]
    if job.get("cron"):
        cmd += ["--trigger-type", "Schedule", "--cron-expression", job["cron"]]
    else:
        cmd += ["--trigger-type", "Manual"]
    cmd += [
        "--image",
        image,
        "--registry-server",
        f"{settings['registry']}.azurecr.io",
        "--registry-identity",
        identity["id"],
        "--mi-user-assigned",
        identity["id"],
        "--cpu",
        "0.5",
        "--memory",
        "1Gi",
        "--replica-timeout",
        str(job["timeout_seconds"]),
        "--replica-retry-limit",
        "0",
        "--parallelism",
        "1",
        "--replica-completion-count",
        "1",
        "--env-vars",
        *pairs,
        "--args",
        " ".join(job["args"]),  # one string, split by infra/entrypoint.sh inside the container
    ]
    return cmd


def head_sha() -> str:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True
    )
    if dirty.stdout.strip():
        raise DeployError(
            "tracked files have uncommitted changes; commit first (the image is built from HEAD)"
        )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


def build_context(sha: str) -> Path:
    """HEAD as a clean directory: only committed files, so no .env or venv can reach the image."""
    archive = subprocess.run(["git", "archive", "--format=tar", sha], capture_output=True, check=True).stdout
    out = Path(tempfile.mkdtemp(prefix="whales-build-"))
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(out, filter="data")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    s = load_settings()
    az = Az(s["subscription"])
    rg, loc, reg = s["resource_group"], s["location"], s["registry"]

    def step(label: str, exists, create) -> None:
        if exists is not None:
            print(f"   ok       {label}")
            return
        print(f"   {'create' if args.apply else 'missing'}  {label}")
        if args.apply:
            create()

    step(
        f"resource group {rg}",
        az.run("group", "show", "-n", rg, check=False),
        lambda: az.run("group", "create", "-n", rg, "-l", loc),
    )
    law_show = ("monitor", "log-analytics", "workspace", "show", "-g", rg, "-n", s["log_workspace"])
    step(
        f"log workspace {s['log_workspace']}",
        az.run(*law_show, check=False),
        lambda: az.run(
            "monitor", "log-analytics", "workspace", "create", "-g", rg, "-n", s["log_workspace"], "-l", loc
        ),
    )
    step(
        f"registry {reg}",
        az.run("acr", "show", "-n", reg, check=False),
        lambda: az.run(
            "acr", "create", "-g", rg, "-n", reg, "-l", loc, "--sku", "Basic", "--admin-enabled", "false"
        ),
    )
    ids: dict[str, dict] = {}
    for key, name in s["identities"].items():
        step(
            f"identity {name}",
            az.run("identity", "show", "-g", rg, "-n", name, check=False),
            lambda name=name: az.run("identity", "create", "-g", rg, "-n", name, "-l", loc),
        )
        ids[key] = az.run("identity", "show", "-g", rg, "-n", name, check=False) or {}

    acr = az.run("acr", "show", "-n", reg, check=False)
    if not args.apply and (acr is None or not all(ids.values())):
        print("(dry run: later steps depend on resources that do not exist yet; add --apply)")
        return 0
    for key, ident in ids.items():
        have = az.run(
            "role",
            "assignment",
            "list",
            "--assignee",
            ident["principalId"],
            "--scope",
            acr["id"],
            "--role",
            "AcrPull",
            check=False,
        )
        step(
            f"AcrPull for {s['identities'][key]}",
            have or None,
            lambda ident=ident: az.run(
                "role",
                "assignment",
                "create",
                "--assignee-object-id",
                ident["principalId"],
                "--assignee-principal-type",
                "ServicePrincipal",
                "--role",
                "AcrPull",
                "--scope",
                acr["id"],
            ),
        )

    sha = head_sha()
    image = f"{reg}.azurecr.io/{s['image']}:{sha}"
    tags = az.run("acr", "repository", "show-tags", "-n", reg, "--repository", s["image"], check=False) or []

    def build() -> None:
        context = build_context(sha)
        print(f"            building {image} from {context} (a few minutes)")
        # --no-logs: the build log carries non-ASCII characters that the Windows az CLI cannot print to a
        # pipe (its Python runs isolated, so PYTHONIOENCODING does not reach it). It still waits for the
        # build to finish; a failed build still fails here. Logs: `az acr task logs -r <registry>`.
        az.run(
            "acr",
            "build",
            "-r",
            reg,
            "-t",
            f"{s['image']}:{sha}",
            "--build-arg",
            f"GIT_SHA={sha}",
            "--no-logs",
            str(context),
        )

    step(f"image {image}", sha if sha in tags else None, build)

    def create_env() -> None:
        law = az.run(*law_show)
        key = az.run(
            "monitor", "log-analytics", "workspace", "get-shared-keys", "-g", rg, "-n", s["log_workspace"]
        )
        az.run(
            "containerapp",
            "env",
            "create",
            "-g",
            rg,
            "-n",
            s["environment"],
            "-l",
            loc,
            "--logs-workspace-id",
            law["customerId"],
            "--logs-workspace-key",
            key["primarySharedKey"],
        )

    step(
        f"environment {s['environment']}",
        az.run("containerapp", "env", "show", "-g", rg, "-n", s["environment"], check=False),
        create_env,
    )

    for job in s["job"]:
        exists = az.run("containerapp", "job", "show", "-g", rg, "-n", job["name"], check=False)
        print(f"   {'update' if exists else 'create'}   job {job['name']} -> {image}")
        if not args.apply:
            continue
        for attempt in range(4):  # a fresh AcrPull grant can take a minute to reach the registry
            try:
                az.run(*job_command(s, job, image, ids, update=bool(exists)))
                break
            except DeployError:
                if attempt == 3:
                    raise
                time.sleep(30)
    if not args.apply:
        print("(dry run: nothing changed; add --apply)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DeployError as e:
        print(f"deploy failed: {e}", file=sys.stderr)
        sys.exit(1)
