import pytest

from whales.db import migrate


def _write(tmp_path, name, sql="SELECT 1;"):
    (tmp_path / name).write_text(sql, encoding="utf-8")


def test_discover_orders_and_names(tmp_path):
    _write(tmp_path, "0002_second.sql")
    _write(tmp_path, "0001_first.sql")
    found = migrate.discover(tmp_path)
    assert [(m.version, m.name) for m in found] == [(1, "first"), (2, "second")]


@pytest.mark.parametrize("names", [["0001_a.sql", "0003_c.sql"], ["0002_b.sql"]])
def test_discover_refuses_gaps(tmp_path, names):
    for n in names:
        _write(tmp_path, n)
    with pytest.raises(migrate.MigrationError, match="without gaps"):
        migrate.discover(tmp_path)


def test_discover_refuses_bad_names(tmp_path):
    _write(tmp_path, "1_First.sql")
    with pytest.raises(migrate.MigrationError, match="badly named"):
        migrate.discover(tmp_path)


def test_checksum_ignores_windows_line_endings():
    assert migrate.checksum("a;\r\nb;\r\n") == migrate.checksum("a;\nb;\n")


def test_pending_skips_applied():
    a = migrate.Migration(1, "a", "SELECT 1;")
    b = migrate.Migration(2, "b", "SELECT 2;")
    assert migrate.pending([a, b], {1: a.checksum}) == [b]


def test_pending_refuses_edited_migration():
    a = migrate.Migration(1, "a", "SELECT 1;")
    with pytest.raises(migrate.MigrationError, match="edited after it was applied"):
        migrate.pending([a], {1: "not-the-same"})


def test_pending_refuses_recorded_version_without_file():
    with pytest.raises(migrate.MigrationError, match="has no file"):
        migrate.pending([], {1: "x"})
