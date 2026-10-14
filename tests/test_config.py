import re
from datetime import date

import pytest

from whales import config

TAGS = '[style]\nvalue = "v"\n[strategy]\nactivist = "a"\n'
TOPICS = '[[topic]]\nslug = "gold"\nname = "Gold"\ndescription = "d"\n'
MANAGERS = """tags_proposed_by = "test"
tags_valid_from = 2026-10-08
[[manager]]
slug = "m1"
name = "M1"
kind = "manager"
style = ["value?"]
  [[manager.filer]]
  cik = 1
  edgar_name = "M1 LLC"
  first_quarter = 2024-03-31
"""
SOURCE = """[[source]]
slug = "s1"
manager = "m1"
name = "S1"
url = "https://x.test"
tier = 1
mode = "auto"
cadence = "quarterly"
access_restricted = false
storage_allowed = false
use_allowed = true
permission_basis = "test"
"""
TRUST = (
    "[[baseline]]\ndocument_kinds = ["
    + ", ".join(f'"{k}"' for k in config.DOCUMENT_KINDS)
    + ']\nlevel = "medium"\nreason = "test"\n'
)


def _write(tmp_path, tags=TAGS, topics=TOPICS, managers=MANAGERS, sources=SOURCE, trust=TRUST):
    for name, text in (
        ("tags.toml", tags),
        ("topics.toml", topics),
        ("managers.toml", managers),
        ("letter_sources.toml", sources),
        ("trust.toml", trust),
    ):
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_real_config_is_valid():
    cfg = config.load()
    assert cfg.managers and cfg.sources and cfg.tags and cfg.topics
    # nothing is active before the compliance ruling, and the loader would refuse an unapproved active source
    assert all(s.approved_by for s in cfg.sources if s.active)


def test_minimal_config_loads(tmp_path):
    cfg = config.load(_write(tmp_path))
    m = cfg.managers[0]
    assert m.tags == (config.TagProposal("style", "value", True),)
    assert m.filers[0].first_quarter == date(2024, 3, 31)
    assert cfg.tags_valid_from == date(2026, 10, 8)


@pytest.mark.parametrize(
    ("managers", "sources", "expected"),
    [
        (MANAGERS.replace('["value?"]', '["growth"]'), SOURCE, "not in tags.toml"),
        (MANAGERS.replace("2024-03-31", "2024-03-30"), SOURCE, "quarter-end"),
        (MANAGERS, SOURCE + "active = true\n", "needs approved_by"),
        (MANAGERS, SOURCE.replace("access_restricted = false", "access_restricted = true"), "must be manual"),
        (MANAGERS, SOURCE.replace("tier = 1", "tier = 4"), "tier must be 1, 2 or 3"),
        (MANAGERS, SOURCE.replace('manager = "m1"', 'manager = "nobody"'), "not in managers.toml"),
        (MANAGERS.replace('kind = "manager"', 'kind = "fund"'), SOURCE, "kind must be"),
    ],
)
def test_invalid_config_is_refused(tmp_path, managers, sources, expected):
    with pytest.raises(config.ConfigError) as e:
        config.load(_write(tmp_path, managers=managers, sources=sources))
    assert any(expected in p for p in e.value.problems), e.value.problems


def test_sec_sources_need_an_edgar_rule(tmp_path):
    sec = SOURCE.replace("tier = 1", "tier = 2")
    with pytest.raises(config.ConfigError, match="needs an edgar rule"):
        config.load(_write(tmp_path, sources=sec))
    ruled = "edgar_since = 2024-10-01\n" + sec + 'edgar = { preset = "activist", ciks = [1] }\n'
    assert config.load(_write(tmp_path, sources=ruled)).sources[0].edgar == config.EdgarRule("activist", (1,))
    bad = "edgar_since = 2024-10-01\n" + sec + 'edgar = { preset = "nope", ciks = [] }\n'
    with pytest.raises(config.ConfigError, match="preset must be one of"):
        config.load(_write(tmp_path, sources=bad))


def test_topic_parent_must_come_first(tmp_path):
    topics = TOPICS + '[[topic]]\nslug = "a"\nname = "A"\ndescription = "d"\nparent = "z"\n'
    with pytest.raises(config.ConfigError, match="defined earlier"):
        config.load(_write(tmp_path, topics=topics))


def test_duplicate_cik_is_refused(tmp_path):
    managers = MANAGERS + '[[manager]]\nslug = "m2"\nname = "M2"\nkind = "manager"\n'
    managers += '  [[manager.filer]]\n  cik = 1\n  edgar_name = "dup"\n'
    with pytest.raises(config.ConfigError, match="appears twice"):
        config.load(_write(tmp_path, managers=managers))


def test_all_problems_reported_together(tmp_path):
    bad = SOURCE.replace("tier = 1", "tier = 9").replace('mode = "auto"', 'mode = "robot"')
    with pytest.raises(config.ConfigError) as e:
        config.load(_write(tmp_path, sources=bad))
    assert len(e.value.problems) >= 2


@pytest.mark.parametrize(
    ("trust", "expected"),
    [
        ('[[baseline]]\ndocument_kinds = ["tweet"]\nlevel = "low"\nreason = "r"\n', "no baseline for"),
        (TRUST + '[[baseline]]\ndocument_kinds = ["tweet"]\nlevel = "low"\nreason = "r"\n', "covered twice"),
        (TRUST.replace('"medium"', '"maybe"'), "level must be one of"),
        (TRUST.replace('"note"', '"podcast"'), "document_kinds must be"),
        (
            TRUST.replace("[[baseline]]\n", '[[baseline]]\nmanager_kinds = ["robot"]\n'),
            "manager_kinds must be",
        ),
        ("", "at least one"),
    ],
)
def test_trust_baselines_must_cover_every_pair_once(tmp_path, trust, expected):
    with pytest.raises(config.ConfigError) as info:
        config.load(_write(tmp_path, trust=trust))
    assert any(expected in p for p in info.value.problems), info.value.problems


def test_trust_baselines_expand_to_every_pair():
    cfg = config.load()
    by_pair = {(b.document_kind, b.manager_kind): b.level for b in cfg.baselines}
    assert len(by_pair) == len(config.DOCUMENT_KINDS) * len(config.KINDS) == len(cfg.baselines)
    assert by_pair[("quarterly_letter", "manager")] == "high"
    assert by_pair[("quarterly_letter", "independent_writer")] == "medium"
    assert by_pair[("tweet", "manager")] == "low"
    assert by_pair[("note", "independent_writer")] == "none"


def test_document_kinds_and_levels_match_migration_0002():
    from whales.db import migrate

    sql = next(m.sql for m in migrate.discover() if m.version == 2)
    kinds = re.search(r"document_kind_check CHECK \(kind IN \((.*?)\)\)", sql, re.S).group(1)
    assert set(re.findall(r"'([a-z_]+)'", kinds)) == set(config.DOCUMENT_KINDS)
    for level in config.LEVELS:
        assert f"'{level}'" in sql


def test_is_quarter_end():
    assert config.is_quarter_end(date(2026, 6, 30)) and config.is_quarter_end(date(2026, 12, 31))
    assert not config.is_quarter_end(date(2026, 6, 29)) and not config.is_quarter_end(date(2026, 5, 31))
