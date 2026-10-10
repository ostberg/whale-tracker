"""The configuration files in ``config/``: tags, topics, managers and letter sources (W-040).

TOML, read with the standard library's ``tomllib``, so configuration adds no dependency. ``load()`` validates
everything and reports every problem at once; ``whales config sync`` writes the result to the database.
The vocabularies here mirror the CHECK constraints in migration 0001; the database enforces them again.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

KINDS = ("manager", "listed_vehicle", "independent_writer", "economist_or_strategist")
FACETS = ("style", "strategy", "asset_focus", "geography")
MODES = ("auto", "manual")
CADENCES = ("annual", "semiannual", "quarterly", "monthly", "irregular")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TAG = re.compile(r"^[a-z0-9][a-z0-9_]*$")
ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")


class ConfigError(ValueError):
    """The configuration is invalid; ``problems`` lists every issue found."""

    def __init__(self, problems: list[str]):
        super().__init__("invalid configuration:\n  " + "\n  ".join(problems))
        self.problems = problems


def config_dir() -> Path:
    """``WHALES_CONFIG_DIR`` if set (the job image), else ``config/`` at the repository root."""
    override = os.environ.get("WHALES_CONFIG_DIR")
    return Path(override) if override else Path(__file__).resolve().parents[2] / "config"


def is_quarter_end(d: date) -> bool:
    nxt = d + timedelta(days=1)
    return nxt.day == 1 and nxt.month in (1, 4, 7, 10)


@dataclass(frozen=True)
class Tag:
    facet: str
    tag: str
    description: str


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    description: str
    parent: str | None = None
    aliases: tuple[str, ...] = ()
    tamale_topic_id: str | None = None


@dataclass(frozen=True)
class TagProposal:
    facet: str
    tag: str
    uncertain: bool


@dataclass(frozen=True)
class Filer:
    cik: int
    edgar_name: str
    first_quarter: date | None = None
    last_quarter: date | None = None
    note: str | None = None


@dataclass(frozen=True)
class ExcludedFiling:
    accession: str
    reason: str


@dataclass(frozen=True)
class Manager:
    slug: str
    name: str
    kind: str
    active: bool
    notes: str | None
    tags: tuple[TagProposal, ...]
    filers: tuple[Filer, ...]
    excluded_filings: tuple[ExcludedFiling, ...]


@dataclass(frozen=True)
class Source:
    slug: str
    manager: str
    name: str
    url: str
    tier: int
    mode: str
    cadence: str
    access_restricted: bool
    storage_allowed: bool
    use_allowed: bool
    permission_basis: str
    terms_url: str | None
    approved_by: str | None
    approved_at: date | None
    active: bool
    edgar: EdgarRule | None = None


@dataclass(frozen=True)
class EdgarRule:
    """How a tier-2 source finds its documents: a preset from ``whales.sources.sec_letters`` and the filer
    CIKs to watch. Not stored in the database; the collector reads it from config."""

    preset: str
    ciks: tuple[int, ...]


@dataclass(frozen=True)
class Config:
    tags: tuple[Tag, ...]
    topics: tuple[Topic, ...]
    managers: tuple[Manager, ...]
    sources: tuple[Source, ...]
    tags_proposed_by: str
    tags_valid_from: date
    edgar_since: date | None = None


def _read(directory: Path, name: str) -> dict:
    with (directory / name).open("rb") as f:
        return tomllib.load(f)


def load(directory: Path | None = None) -> Config:
    """Read and validate all four files. Raises ConfigError listing every problem."""
    d = directory or config_dir()
    problems: list[str] = []
    tags = _tags(_read(d, "tags.toml"), problems)
    topics = _topics(_read(d, "topics.toml"), problems)
    raw_managers = _read(d, "managers.toml")
    managers = _managers(raw_managers, {(t.facet, t.tag) for t in tags}, problems)
    raw_sources = _read(d, "letter_sources.toml")
    sources = _sources(raw_sources, {m.slug for m in managers}, problems)
    proposed_by = raw_managers.get("tags_proposed_by", "")
    valid_from = raw_managers.get("tags_valid_from")
    if not proposed_by or not isinstance(valid_from, date):
        problems.append("managers.toml: tags_proposed_by and tags_valid_from (a date) are required")
    edgar_since = raw_sources.get("edgar_since")
    if any(s.edgar for s in sources) and not isinstance(edgar_since, date):
        problems.append(
            "letter_sources.toml: edgar_since (a date) is required when any source has an edgar rule"
        )
    if problems:
        raise ConfigError(problems)
    return Config(tags, topics, managers, sources, proposed_by, valid_from, edgar_since)


def _tags(raw: dict, problems: list[str]) -> tuple[Tag, ...]:
    out, seen = [], set()
    for facet, entries in raw.items():
        if facet not in FACETS:
            problems.append(f"tags.toml: unknown facet [{facet}]")
            continue
        for tag, description in entries.items():
            if not TAG.match(tag):
                problems.append(f"tags.toml: bad tag code {facet}.{tag}")
            if (facet, tag) in seen:
                problems.append(f"tags.toml: duplicate {facet}.{tag}")
            seen.add((facet, tag))
            out.append(Tag(facet, tag, str(description)))
    return tuple(out)


def _topics(raw: dict, problems: list[str]) -> tuple[Topic, ...]:
    out: list[Topic] = []
    seen: set[str] = set()
    for t in raw.get("topic", []):
        slug = t.get("slug", "")
        if not SLUG.match(slug):
            problems.append(f"topics.toml: bad slug {slug!r}")
        if slug in seen:
            problems.append(f"topics.toml: duplicate slug {slug}")
        parent = t.get("parent")
        if parent and parent not in seen:
            problems.append(f"topics.toml: {slug}: parent {parent!r} must be defined earlier in the file")
        seen.add(slug)
        if not t.get("name") or not t.get("description"):
            problems.append(f"topics.toml: {slug}: name and description are required")
        out.append(
            Topic(
                slug,
                t.get("name", ""),
                t.get("description", ""),
                parent,
                tuple(t.get("aliases", [])),
                t.get("tamale_topic_id"),
            )
        )
    return tuple(out)


def _managers(raw: dict, known_tags: set[tuple[str, str]], problems: list[str]) -> tuple[Manager, ...]:
    out: list[Manager] = []
    slugs: set[str] = set()
    ciks: set[int] = set()
    for m in raw.get("manager", []):
        slug = m.get("slug", "")
        where = f"managers.toml: {slug or '?'}"
        if not SLUG.match(slug):
            problems.append(f"{where}: bad slug")
        if slug in slugs:
            problems.append(f"{where}: duplicate slug")
        slugs.add(slug)
        if m.get("kind") not in KINDS:
            problems.append(f"{where}: kind must be one of {KINDS}")
        if not m.get("name"):
            problems.append(f"{where}: name is required")
        proposals = []
        for facet in FACETS:
            for code in m.get(facet, []):
                tag = code.rstrip("?")
                if (facet, tag) not in known_tags:
                    problems.append(f"{where}: {facet} tag {tag!r} is not in tags.toml")
                proposals.append(TagProposal(facet, tag, code.endswith("?")))
        filers = []
        for f in m.get("filer", []):
            cik = f.get("cik")
            if not isinstance(cik, int) or cik <= 0:
                problems.append(f"{where}: filer cik must be a positive integer")
                continue
            if cik in ciks:
                problems.append(f"{where}: CIK {cik} appears twice")
            ciks.add(cik)
            first, last = f.get("first_quarter"), f.get("last_quarter")
            for label, q in (("first_quarter", first), ("last_quarter", last)):
                if q is not None and not (isinstance(q, date) and is_quarter_end(q)):
                    problems.append(f"{where}: CIK {cik} {label} must be a quarter-end date")
            if first and last and last < first:
                problems.append(f"{where}: CIK {cik} last_quarter is before first_quarter")
            if not f.get("edgar_name"):
                problems.append(f"{where}: CIK {cik} edgar_name is required")
            filers.append(Filer(cik, f.get("edgar_name", ""), first, last, f.get("note")))
        excluded = []
        for x in m.get("excluded_filing", []):
            if not ACCESSION.match(x.get("accession", "")) or not x.get("reason"):
                problems.append(f"{where}: excluded_filing needs a valid accession and a reason")
            excluded.append(ExcludedFiling(x.get("accession", ""), x.get("reason", "")))
        out.append(
            Manager(
                slug,
                m.get("name", ""),
                m.get("kind", ""),
                bool(m.get("active", True)),
                m.get("notes"),
                tuple(proposals),
                tuple(filers),
                tuple(excluded),
            )
        )
    return tuple(out)


def _sources(raw: dict, managers: set[str], problems: list[str]) -> tuple[Source, ...]:
    out: list[Source] = []
    seen: set[str] = set()
    required = ("access_restricted", "storage_allowed", "use_allowed")
    for s in raw.get("source", []):
        slug = s.get("slug", "")
        where = f"letter_sources.toml: {slug or '?'}"
        if not SLUG.match(slug):
            problems.append(f"{where}: bad slug")
        if slug in seen:
            problems.append(f"{where}: duplicate slug")
        seen.add(slug)
        if s.get("manager") not in managers:
            problems.append(f"{where}: manager {s.get('manager')!r} is not in managers.toml")
        if s.get("tier") not in (1, 2, 3):
            problems.append(f"{where}: tier must be 1, 2 or 3 (tier 4 never lives here, W-014)")
        if s.get("mode") not in MODES:
            problems.append(f"{where}: mode must be one of {MODES}")
        if s.get("cadence") not in CADENCES:
            problems.append(f"{where}: cadence must be one of {CADENCES}")
        for key in required:
            if not isinstance(s.get(key), bool):
                problems.append(f"{where}: {key} must be true or false")
        if s.get("access_restricted") and s.get("mode") != "manual":
            problems.append(f"{where}: an access-restricted source must be manual (W-033)")
        if not s.get("url") or not s.get("permission_basis") or not s.get("name"):
            problems.append(f"{where}: name, url and permission_basis are required")
        active = bool(s.get("active", False))
        approved_by, approved_at = s.get("approved_by"), s.get("approved_at")
        if approved_at is not None and not isinstance(approved_at, date):
            problems.append(f"{where}: approved_at must be a date")
        if active and not (approved_by and approved_at):
            problems.append(
                f"{where}: an active source needs approved_by and approved_at (compliance ruling)"
            )
        edgar = _edgar_rule(s.get("edgar"), s.get("tier"), where, problems)
        out.append(
            Source(
                slug,
                s.get("manager", ""),
                s.get("name", ""),
                s.get("url", ""),
                s.get("tier", 0),
                s.get("mode", ""),
                s.get("cadence", ""),
                bool(s.get("access_restricted")),
                bool(s.get("storage_allowed")),
                bool(s.get("use_allowed")),
                s.get("permission_basis", ""),
                s.get("terms_url"),
                approved_by,
                approved_at,
                active,
                edgar,
            )
        )
    return tuple(out)


def _edgar_rule(raw: dict | None, tier: int | None, where: str, problems: list[str]) -> EdgarRule | None:
    from .sources.sec_letters import PRESETS

    if raw is None:
        if tier == 2:
            problems.append(f"{where}: a tier-2 (SEC) source needs an edgar rule")
        return None
    if tier != 2:
        problems.append(f"{where}: only tier-2 (SEC) sources take an edgar rule")
    preset, ciks = raw.get("preset"), raw.get("ciks", [])
    if preset not in PRESETS:
        problems.append(f"{where}: edgar preset must be one of {sorted(PRESETS)}")
    if not ciks or not all(isinstance(c, int) and c > 0 for c in ciks):
        problems.append(f"{where}: edgar ciks must be a non-empty list of positive integers")
    return EdgarRule(str(preset), tuple(ciks))
