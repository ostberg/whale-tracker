"""The inbox loader (W-044) against small synthetic PDFs: no third-party letters in the repository."""

from datetime import date

import pytest

from whales import config, inbox, inbox_load


def make_pdf(lines: list[str], title: str | None = None, author: str | None = None) -> bytes:
    """A minimal one-page PDF with the given text lines and optional metadata."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({esc(t)}) Tj 0 -16 Td" for t in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    info = ""
    if title or author:
        info = (
            "<< "
            + (f"/Title ({esc(title)}) " if title else "")
            + (f"/Author ({esc(author)}) " if author else "")
        )
        info += "/CreationDate (D:20261001000000) >>"
        objects.append(info)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    trailer = (
        f"<< /Size {len(objects) + 1} /Root 1 0 R" + (f" /Info {len(objects)} 0 R" if info else "") + " >>"
    )
    out += f"trailer\n{trailer}\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def box(tmp_path):
    for d in ("public-websites", "shared-by-manager/permissions"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture(scope="module")
def cfg():
    return config.load()


def _scan(cfg, box):
    return {f.rel: f for f in inbox.scan(cfg, box)}


def test_letterhead_identifies_manager_period_and_date(cfg, box):
    pdf = make_pdf(
        ["Praetorian Capital Fund", "Q3 2026 Investor Letter", "October 15, 2026", "Dear Partners,"]
    )
    (box / "public-websites" / "letter.pdf").write_bytes(pdf)
    f = _scan(cfg, box)["letter.pdf"]
    assert (f.manager, f.manager_basis) == ("praetorian", "text")
    assert f.period_end == date(2026, 9, 30) and f.kind == "quarterly_letter"
    assert (f.published_on, f.published_basis) == (date(2026, 10, 15), "stated")
    assert f.pages == 1 and not f.encrypted and f.extract_allowed is True


def test_folder_named_after_manager_wins(cfg, box):
    (box / "public-websites" / "oaktree").mkdir()
    pdf = make_pdf(["A memo about the market", "Praetorian Capital is mentioned here"])
    (box / "public-websites" / "oaktree" / "x.pdf").write_bytes(pdf)
    f = _scan(cfg, box)["oaktree/x.pdf"]
    assert (f.manager, f.manager_basis) == ("oaktree", "folder")


def test_name_deep_in_the_text_is_not_trusted(cfg, box):
    filler = ["We discuss interest rates and the economy at length."] * 30
    (box / "public-websites" / "y.pdf").write_bytes(
        make_pdf([*filler, "As Oaktree Capital Management wrote"])
    )
    f = _scan(cfg, box)["y.pdf"]
    assert f.manager is None and "oaktree" in f.candidates


def test_two_managers_side_by_side_are_not_guessed(cfg, box):
    (box / "public-websites" / "z.pdf").write_bytes(
        make_pdf(["Starboard Value and Elliott Investment Management"])
    )
    assert _scan(cfg, box)["z.pdf"].manager is None


def test_metadata_and_shared_route(cfg, box):
    pdf = make_pdf(["Dear Partners"], title="Laughing Water Capital H1 2026 Letter", author="Matt Sweeney")
    (box / "shared-by-manager" / "lw.pdf").write_bytes(pdf)
    f = _scan(cfg, box)["lw.pdf"]
    assert f.route == "shared" and f.manager == "laughing-water"
    assert f.period_end == date(2026, 6, 30)
    assert (f.published_on, f.published_basis) == (date(2026, 10, 1), "inferred")


def test_permissions_folder_is_ignored_and_junk_is_reported(cfg, box):
    (box / "shared-by-manager" / "permissions" / "email.pdf").write_bytes(make_pdf(["Praetorian Capital"]))
    (box / "public-websites" / "broken.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
    files = _scan(cfg, box)
    assert "permissions/email.pdf" not in files
    assert files["broken.pdf"].error


@pytest.mark.parametrize(
    ("text", "expected", "kind"),
    [
        ("2026 Q1 Investor Letter", date(2026, 3, 31), "quarterly_letter"),
        ("Q2 2026 letter", date(2026, 6, 30), "quarterly_letter"),
        ("3Q26 update", date(2026, 9, 30), "quarterly_letter"),
        ("Second Quarter 2025 Commentary", date(2025, 6, 30), "quarterly_letter"),
        ("Year-End 2025 Letter", date(2025, 12, 31), "annual_letter"),
        ("2025 Annual Letter", date(2025, 12, 31), "annual_letter"),
        ("Semi-Annual 2026", date(2026, 6, 30), "quarterly_letter"),
        ("A note on markets", None, "other"),
    ],
)
def test_infer_period(text, expected, kind):
    assert inbox.infer_period(text) == (expected, kind)


def test_infer_published_both_orders():
    assert inbox.infer_published("Dated 15 October 2026.") == date(2026, 10, 15)
    assert inbox.infer_published("no date here") is None


def test_sources_by_route(cfg):
    pub = inbox.InboxFile(
        path=None, route="public", rel="a.pdf", sha256="x", size=1, manager="laughing-water"
    )
    assert inbox.source_for(cfg, pub) == "laughing-water-letters"
    shared = inbox.InboxFile(
        path=None, route="shared", rel="a.pdf", sha256="x", size=1, manager="laughing-water"
    )
    assert inbox.source_for(cfg, shared) is None  # needs a laughing-water-shared source in config first


def test_load_plan_sorts_files(cfg):
    def f(name, manager, sha, error=None):
        return inbox.InboxFile(
            path=None, route="public", rel=name, sha256=sha, size=1, manager=manager, error=error
        )

    files = [
        f("a", "praetorian", "h1"),
        f("b", "praetorian", "h2"),
        f("c", None, "h3"),
        f("d", "stone-sentinel", "h4"),
    ]
    result, todo = inbox_load.plan(cfg, files, known_hashes={"h2"})
    assert [(x.rel, s) for x, s in todo] == [("a", "praetorian-letters")]
    assert [x.rel for x in result.known] == ["b"]
    assert [x.rel for x in result.unresolved] == ["c"]
    assert [x.rel for x in result.no_source] == ["d"]
