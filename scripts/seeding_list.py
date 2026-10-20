"""Write docs/SEEDING_LIST.md: the historical letters worth collecting by hand for every manual source,
from the project's history start to the automation cutoff (W-055), minus what the database already holds.

    .venv\\Scripts\\python.exe scripts\\seeding_list.py

Runs from the repo with its venv and opens the firewall for the read (laptop, as the signed-in admin).
Rerun after a batch has been loaded: held periods drop off the list.
"""

from datetime import date
from pathlib import Path

from whales import config, expected
from whales.cli import load_env_file
from whales.db import firewall
from whales.db.connect import Database, DbSettings

START = date(2024, 9, 30)  # periods ending after this; the project's history starts in October 2024
CUTOFF = date(2026, 6, 30)  # the automation asks for anything after this (W-055 rounds)
OUT = Path("docs/SEEDING_LIST.md")


def main() -> None:
    load_env_file()
    cfg = config.load()
    managers = {m.slug: m for m in cfg.managers}
    with firewall.opening(), Database(DbSettings.from_env(), role="whales_ingest") as db:
        held = set(
            db.run(
                "SELECT s.slug, d.period_end FROM letters.document d "
                "JOIN letters.document_file f ON f.document_id = d.id "
                "JOIN letters.source s ON s.id = f.source_id WHERE d.period_end IS NOT NULL"
            )
        )
        held_by_manager = set(
            db.run(
                "SELECT m.slug, d.period_end FROM letters.document d "
                "JOIN core.manager m ON m.id = d.manager_id WHERE d.period_end IS NOT NULL"
            )
        )
        counts = dict(
            db.run(
                "SELECT s.slug, count(*) FROM letters.document_file f "
                "JOIN letters.source s ON s.id = f.source_id GROUP BY s.slug"
            )
        )

    lines = [
        "# Seeding list: historical letters to collect by hand",
        "",
        f"Generated {date.today().isoformat()} by `scripts/seeding_list.py` from `config/letter_sources.toml`"
        " and the database. The",
        f"automation asks only for periods ending after {CUTOFF.isoformat()} (W-055); everything older on"
        " this list is a",
        "one-off back-collection, a good intern task (the owner, 2026-10-20). Periods the database already"
        " holds are",
        "left out; rerun the script after a batch has been loaded to get the remainder.",
        "",
        "How to drop a file: put it in `Whale Tracker Inbox\\public-websites\\<manager-slug>\\` (any file"
        " name), or in",
        "`shared-by-manager\\<manager-slug>\\` if the manager sent it. The loader works out the period from"
        " the",
        "file; a period in the file name (`Q3 2025`, `2025 annual letter`) helps. Internal use only (W-043):"
        " nothing",
        "collected here is quoted or sent outside the firm.",
        "",
        "Sources marked (not machine-read) are listed too: worth holding, but not analysed until the"
        " publisher",
        "consents (W-035).",
        "",
    ]
    manual = [s for s in cfg.sources if s.active and s.mode == "manual"]
    total = 0
    for s in sorted(manual, key=lambda s: (managers[s.manager].name, s.name)):
        m = managers[s.manager]
        shared = s.slug.endswith("-shared")
        periods = expected.period_ends(s.cadence, START, CUTOFF)
        missing = [p for p in periods if (s.slug, p) not in held and (m.slug, p) not in held_by_manager]
        note = (
            "" if s.use_allowed else " (not machine-read: terms ban AI analysis until the publisher consents)"
        )
        folder = f"shared-by-manager\\{m.slug}\\" if shared else f"public-websites\\{m.slug}\\"
        lines.append(f"## {m.name}: {s.name}{note}")
        lines.append("")
        where = s.url + (
            " (sent by the manager; the agreement is on file in `permissions\\`)" if shared else ""
        )
        lines.append(f"- Where: {where}")
        lines.append(f"- Cadence: {s.cadence}; drop in `{folder}`")
        lines.append(f"- Already held: {counts.get(s.slug, 0)} file(s) from this source")
        if shared:
            lines.append("- Collect: nothing to fetch; whatever the manager sends goes in the shared folder")
        elif s.cadence == "irregular":
            lines.append("- Collect: whatever the site lists back to October 2024 (no fixed calendar)")
        elif missing:
            total += len(missing)
            label = "months" if s.cadence == "monthly" else "periods"
            lines.append(f"- Collect ({len(missing)} {label}): " + ", ".join(p.isoformat() for p in missing))
        else:
            lines.append("- Collect: nothing, every period is already held")
        lines.append("")
    lines.append(f"Total dated items to collect: {total}.")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(manual)} sources and {total} dated items")


if __name__ == "__main__":
    main()
