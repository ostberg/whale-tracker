from whales import config
from whales.db import sync


def _mirror(cfg: config.Config) -> sync.Current:
    """What the database would hold after a perfect sync of cfg."""
    c = sync.Current()
    c.tags = {(t.facet, t.tag): t.description for t in cfg.tags}
    c.topics = {
        t.slug: (t.name, t.parent, t.description, list(t.aliases), t.tamale_topic_id) for t in cfg.topics
    }
    c.managers = {m.slug: (m.name, m.kind, m.active, m.notes) for m in cfg.managers}
    c.filers = {
        f.cik: (m.slug, f.edgar_name, f.first_quarter, f.last_quarter, f.note)
        for m in cfg.managers
        for f in m.filers
    }
    c.proposals = {(m.slug, p.facet, p.tag, cfg.tags_valid_from) for m in cfg.managers for p in m.tags}
    c.sources = {
        s.slug: (
            s.manager,
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
        for s in cfg.sources
    }
    c.baselines = {(b.document_kind, b.manager_kind): (b.level, b.reason) for b in cfg.baselines}
    return c


def test_empty_database_gets_everything_in_dependency_order():
    cfg = config.load()
    changes = sync.plan(cfg, sync.Current())
    inserts = [c.what.split(" ")[0] for c in changes if c.action == "insert"]
    first = {kind: inserts.index(kind) for kind in ("tag", "topic", "manager", "filer", "source")}
    assert first["tag"] < first["manager"] < first["filer"] < first["source"]
    proposals = [i for i, c in enumerate(changes) if c.what.startswith("tag proposal")]
    assert proposals and min(proposals) > max(
        i for i, c in enumerate(changes) if c.what.startswith("manager ")
    )
    assert inserts.count("manager") == len(cfg.managers)
    assert all(c.sql for c in changes if c.action == "insert")


def test_database_in_step_needs_no_writes():
    cfg = config.load()
    changes = sync.plan(cfg, _mirror(cfg))
    assert [c for c in changes if c.sql] == []


def test_changed_manager_is_updated_and_missing_one_deactivated():
    cfg = config.load()
    current = _mirror(cfg)
    slug = cfg.managers[0].slug
    current.managers[slug] = ("Old name", *current.managers[slug][1:])
    current.managers["gone"] = ("Gone", "manager", True, None)
    changes = sync.plan(cfg, current)
    assert any(c.action == "update" and c.what == f"manager {slug}" for c in changes)
    assert any(c.action == "deactivate" and c.what.startswith("manager gone") for c in changes)
    assert not any(c.sql and "DELETE" in c.sql.upper() for c in changes)


def test_extra_rows_are_reported_not_removed():
    cfg = config.load()
    current = _mirror(cfg)
    current.tags[("style", "momentum")] = "x"
    current.filers[999] = ("someone", "X", None, None, None)
    notes = [c.what for c in sync.plan(cfg, current) if c.action == "note"]
    assert any("style.momentum" in n for n in notes) and any("filer 999" in n for n in notes)


def test_changed_baseline_is_one_update_and_nothing_else():
    """W-051: a baseline change touches the baseline table only; nothing stored elsewhere depends on it."""
    cfg = config.load()
    current = _mirror(cfg)
    b = cfg.baselines[0]
    current.baselines[(b.document_kind, b.manager_kind)] = ("none", b.reason)
    changes = [c for c in sync.plan(cfg, current) if c.sql]
    assert len(changes) == 1 and changes[0].action == "update"
    assert "core.trust_baseline" in changes[0].sql and "DELETE" not in changes[0].sql.upper()
