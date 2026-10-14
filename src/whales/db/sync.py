"""Write ``config/`` to the database: ``whales config sync`` (W-040).

Config is the source of truth for tags, topics, managers, filers, tag proposals, letter sources and trust
baselines. The sync
inserts what is new and updates what changed, as whales_owner, in one transaction. It never deletes: a
manager or source missing from config is deactivated, and anything else the database holds that config does
not is reported, not removed. People's decisions (tag ratification and the rest) are never touched here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..config import Config
from .connect import Database
from .migrate import OWNER_ROLE


@dataclass(frozen=True)
class Change:
    action: str  # insert, update, deactivate, note
    what: str
    sql: str | None = None
    params: tuple = ()


@dataclass
class Current:
    """What the database holds now, keyed by natural key."""

    tags: dict[tuple[str, str], str] = field(default_factory=dict)
    topics: dict[str, tuple] = field(default_factory=dict)
    managers: dict[str, tuple] = field(default_factory=dict)
    filers: dict[int, tuple] = field(default_factory=dict)
    proposals: set[tuple[str, str, str, date]] = field(default_factory=set)
    sources: dict[str, tuple] = field(default_factory=dict)
    baselines: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)


def read_current(db: Database) -> Current:
    c = Current()
    c.tags = {(f, t): d for f, t, d in db.run("SELECT facet, tag, description FROM core.tag")}
    c.baselines = {
        (dk, mk): (level, reason)
        for dk, mk, level, reason in db.run(
            "SELECT document_kind, manager_kind, level, reason FROM core.trust_baseline"
        )
    }
    c.topics = {
        r[0]: tuple(r[1:])
        for r in db.run(
            "SELECT t.slug, t.name, p.slug, t.description, t.aliases, t.tamale_topic_id "
            "FROM core.topic t LEFT JOIN core.topic p ON p.id = t.parent_id"
        )
    }
    c.managers = {
        r[0]: tuple(r[1:]) for r in db.run("SELECT slug, name, kind, active, notes FROM core.manager")
    }
    c.filers = {
        r[0]: tuple(r[1:])
        for r in db.run(
            "SELECT f.cik, m.slug, f.edgar_name, f.first_quarter, f.last_quarter, f.note "
            "FROM core.filer f JOIN core.manager m ON m.id = f.manager_id"
        )
    }
    c.proposals = set(
        db.run(
            "SELECT m.slug, t.facet, t.tag, mt.valid_from FROM core.manager_tag mt "
            "JOIN core.manager m ON m.id = mt.manager_id JOIN core.tag t ON t.id = mt.tag_id"
        )
    )
    c.sources = {
        r[0]: tuple(r[1:])
        for r in db.run(
            "SELECT s.slug, m.slug, s.name, s.url, s.tier, s.mode, s.cadence, s.access_restricted, "
            "s.storage_allowed, s.use_allowed, s.permission_basis, s.terms_url, s.approved_by, "
            "s.approved_at::date, s.active FROM letters.source s JOIN core.manager m ON m.id = s.manager_id"
        )
    }
    return c


MANAGER_ID = "(SELECT id FROM core.manager WHERE slug = %s)"
TOPIC_ID = "(SELECT id FROM core.topic WHERE slug = %s)"


def plan(config: Config, current: Current) -> list[Change]:
    """Every change needed to make the database match config, in an order that satisfies foreign keys."""
    changes: list[Change] = []
    changes += _plan_tags(config, current)
    changes += _plan_baselines(config, current)
    changes += _plan_topics(config, current)
    changes += _plan_managers(config, current)
    changes += _plan_filers(config, current)
    changes += _plan_proposals(config, current)
    changes += _plan_sources(config, current)
    excluded = sum(len(m.excluded_filings) for m in config.managers)
    if excluded:
        changes.append(
            Change("note", f"{excluded} excluded filing(s) in config, stored from phase 3 (W-024)")
        )
    return changes


def _plan_tags(config: Config, current: Current) -> list[Change]:
    out = []
    for t in config.tags:
        key = (t.facet, t.tag)
        if key not in current.tags:
            out.append(
                Change(
                    "insert",
                    f"tag {t.facet}.{t.tag}",
                    "INSERT INTO core.tag (facet, tag, description) VALUES (%s, %s, %s)",
                    (t.facet, t.tag, t.description),
                )
            )
        elif current.tags[key] != t.description:
            out.append(
                Change(
                    "update",
                    f"tag {t.facet}.{t.tag}",
                    "UPDATE core.tag SET description = %s WHERE facet = %s AND tag = %s",
                    (t.description, t.facet, t.tag),
                )
            )
    known = {(t.facet, t.tag) for t in config.tags}
    out += [
        Change("note", f"tag {f}.{t} is in the database but not in config")
        for f, t in current.tags
        if (f, t) not in known
    ]
    return out


def _plan_baselines(config: Config, current: Current) -> list[Change]:
    """Trust baselines (W-050) are read only at query time (W-051), so an update here changes nothing
    stored."""
    out = []
    for b in config.baselines:
        key = (b.document_kind, b.manager_kind)
        what = f"trust baseline {b.document_kind} for {b.manager_kind}"
        if key not in current.baselines:
            out.append(
                Change(
                    "insert",
                    what,
                    "INSERT INTO core.trust_baseline (document_kind, manager_kind, level, reason) "
                    "VALUES (%s, %s, %s, %s)",
                    (b.document_kind, b.manager_kind, b.level, b.reason),
                )
            )
        elif current.baselines[key] != (b.level, b.reason):
            out.append(
                Change(
                    "update",
                    what,
                    "UPDATE core.trust_baseline SET level = %s, reason = %s "
                    "WHERE document_kind = %s AND manager_kind = %s",
                    (b.level, b.reason, b.document_kind, b.manager_kind),
                )
            )
    known = {(b.document_kind, b.manager_kind) for b in config.baselines}
    out += [
        Change("note", f"trust baseline {dk} for {mk} is in the database but not in config")
        for dk, mk in sorted(current.baselines)
        if (dk, mk) not in known
    ]
    return out


def _plan_topics(config: Config, current: Current) -> list[Change]:
    out = []
    for t in config.topics:
        want = (t.name, t.parent, t.description, list(t.aliases), t.tamale_topic_id)
        have = current.topics.get(t.slug)
        if have is None:
            out.append(
                Change(
                    "insert",
                    f"topic {t.slug}",
                    "INSERT INTO core.topic (slug, name, parent_id, description, aliases, tamale_topic_id) "
                    f"VALUES (%s, %s, {TOPIC_ID}, %s, %s, %s)",
                    (t.slug, t.name, t.parent, t.description, list(t.aliases), t.tamale_topic_id),
                )
            )
        elif tuple(have[:2]) + (have[2], list(have[3] or []), have[4]) != want:
            out.append(
                Change(
                    "update",
                    f"topic {t.slug}",
                    f"UPDATE core.topic SET name = %s, parent_id = {TOPIC_ID}, description = %s, "
                    "aliases = %s, tamale_topic_id = %s WHERE slug = %s",
                    (t.name, t.parent, t.description, list(t.aliases), t.tamale_topic_id, t.slug),
                )
            )
    known = {t.slug for t in config.topics}
    out += [
        Change("note", f"topic {s} is in the database but not in config")
        for s in current.topics
        if s not in known
    ]
    return out


def _plan_managers(config: Config, current: Current) -> list[Change]:
    out = []
    for m in config.managers:
        want = (m.name, m.kind, m.active, m.notes)
        have = current.managers.get(m.slug)
        if have is None:
            out.append(
                Change(
                    "insert",
                    f"manager {m.slug}",
                    "INSERT INTO core.manager (slug, name, kind, active, notes) VALUES (%s, %s, %s, %s, %s)",
                    (m.slug, *want),
                )
            )
        elif tuple(have) != want:
            out.append(
                Change(
                    "update",
                    f"manager {m.slug}",
                    "UPDATE core.manager SET name = %s, kind = %s, active = %s, notes = %s WHERE slug = %s",
                    (*want, m.slug),
                )
            )
    known = {m.slug for m in config.managers}
    for slug, have in current.managers.items():
        if slug not in known and have[2]:
            out.append(
                Change(
                    "deactivate",
                    f"manager {slug} (no longer in config)",
                    "UPDATE core.manager SET active = false WHERE slug = %s",
                    (slug,),
                )
            )
    return out


def _plan_filers(config: Config, current: Current) -> list[Change]:
    out = []
    for m in config.managers:
        for f in m.filers:
            want = (m.slug, f.edgar_name, f.first_quarter, f.last_quarter, f.note)
            have = current.filers.get(f.cik)
            if have is None:
                out.append(
                    Change(
                        "insert",
                        f"filer {f.cik} ({m.slug})",
                        "INSERT INTO core.filer (cik, manager_id, edgar_name, first_quarter, last_quarter, "
                        f"note) VALUES (%s, {MANAGER_ID}, %s, %s, %s, %s)",
                        (f.cik, *want),
                    )
                )
            elif tuple(have) != want:
                out.append(
                    Change(
                        "update",
                        f"filer {f.cik} ({m.slug})",
                        f"UPDATE core.filer SET manager_id = {MANAGER_ID}, edgar_name = %s, "
                        "first_quarter = %s, last_quarter = %s, note = %s WHERE cik = %s",
                        (*want, f.cik),
                    )
                )
    known = {f.cik for m in config.managers for f in m.filers}
    out += [
        Change("note", f"filer {c} is in the database but not in config")
        for c in current.filers
        if c not in known
    ]
    return out


def _plan_proposals(config: Config, current: Current) -> list[Change]:
    out = []
    wanted = set()
    for m in config.managers:
        for p in m.tags:
            key = (m.slug, p.facet, p.tag, config.tags_valid_from)
            wanted.add(key)
            if key in current.proposals:
                continue
            evidence = "first-pass proposal; marked uncertain" if p.uncertain else "first-pass proposal"
            out.append(
                Change(
                    "insert",
                    f"tag proposal {m.slug}: {p.facet}.{p.tag}{'?' if p.uncertain else ''}",
                    "INSERT INTO core.manager_tag (manager_id, tag_id, valid_from, proposed_by, evidence) "
                    f"VALUES ({MANAGER_ID}, (SELECT id FROM core.tag WHERE facet = %s AND tag = %s), "
                    "%s, %s, %s)",
                    (m.slug, p.facet, p.tag, config.tags_valid_from, config.tags_proposed_by, evidence),
                )
            )
    out += [
        Change("note", f"tag proposal {s}: {f}.{t} (from {d}) is in the database but not in config")
        for s, f, t, d in sorted(current.proposals)
        if (s, f, t, d) not in wanted
    ]
    return out


def _plan_sources(config: Config, current: Current) -> list[Change]:
    out = []
    columns = (
        "name, url, tier, mode, cadence, access_restricted, storage_allowed, use_allowed, permission_basis, "
        "terms_url, approved_by, approved_at, active"
    )
    for s in config.sources:
        rest = (
            s.name,
            s.url,
            s.tier,
            s.mode,
            s.cadence,
            s.access_restricted,
            s.storage_allowed,
            s.use_allowed,
            s.permission_basis,
            s.terms_url,
            s.approved_by,
            s.approved_at,
            s.active,
        )
        have = current.sources.get(s.slug)
        if have is None:
            out.append(
                Change(
                    "insert",
                    f"source {s.slug}",
                    f"INSERT INTO letters.source (slug, manager_id, {columns}) "
                    f"VALUES (%s, {MANAGER_ID}, {', '.join(['%s'] * len(rest))})",
                    (s.slug, s.manager, *rest),
                )
            )
        elif tuple(have) != (s.manager, *rest):
            sets = ", ".join(f"{c.strip()} = %s" for c in columns.split(","))
            out.append(
                Change(
                    "update",
                    f"source {s.slug}",
                    f"UPDATE letters.source SET manager_id = {MANAGER_ID}, {sets} WHERE slug = %s",
                    (s.manager, *rest, s.slug),
                )
            )
    known = {s.slug for s in config.sources}
    for slug, have in current.sources.items():
        if slug not in known and have[-1]:
            out.append(
                Change(
                    "deactivate",
                    f"source {slug} (no longer in config)",
                    "UPDATE letters.source SET active = false WHERE slug = %s",
                    (slug,),
                )
            )
    return out


def apply(db: Database, changes: list[Change]) -> int:
    """Run every change with SQL, as whales_owner, in one transaction. Returns how many ran."""
    work = [c for c in changes if c.sql]
    if not work:
        return 0
    conn = db.connection()
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {OWNER_ROLE}")
        for c in work:
            conn.execute(c.sql, c.params)
    return len(work)
