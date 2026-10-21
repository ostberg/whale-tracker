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
        ["Praetorian Capital Fund", "Q3 2026 Investor Letter", "October 5, 2026", "Dear Partners,"]
    )
    (box / "public-websites" / "letter.pdf").write_bytes(pdf)
    f = _scan(cfg, box)["letter.pdf"]
    assert (f.manager, f.manager_basis) == ("praetorian", "text")
    assert f.period_end == date(2026, 9, 30) and f.kind == "quarterly_letter"
    assert (f.published_on, f.published_basis) == (date(2026, 10, 5), "stated")
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
        ("Laughing+Water+Capital+Q1'24+Letter", date(2024, 3, 31), "quarterly_letter"),
        ("LWC+H1+2026+Letter", date(2026, 6, 30), "quarterly_letter"),
        ("Laughing+Water+Capital+YE'25", date(2025, 12, 31), "annual_letter"),
        ("LWC+Year+End+2016+Letter", date(2016, 12, 31), "annual_letter"),
        ("Bonsai+Partners+1H+2024+Letter", date(2024, 6, 30), "quarterly_letter"),
        ("Bonsai+Partners+2H+2025+Investor+Letter+Final", date(2025, 12, 31), "annual_letter"),
        ("2023.08.04-1H-2023-Letter-v3", date(2023, 6, 30), "quarterly_letter"),
        ("A note on markets, up 10% in 2025 annual returns", None, "other"),
        ("A note on markets", None, "other"),
    ],
)
def test_infer_period(text, expected, kind):
    assert inbox.infer_period(text) == (expected, kind)


def test_earliest_phrase_wins():
    # the letter's own label comes first; a comparison later in the text must not override it
    assert inbox.infer_period("Q1 2024 letter. Compared with Q1 2023, results improved")[0] == date(
        2024, 3, 31
    )


@pytest.mark.parametrize(
    ("name", "published", "expected"),
    [
        ("2024.02.03-Annual-Letter_v7", date(2024, 2, 3), date(2023, 12, 31)),
        ("2025.08.08-Semi-Annual-Letter-vF", date(2025, 8, 8), date(2025, 6, 30)),
        ("2026.08.13-Sem-Annual-Letter-v4", date(2026, 8, 13), date(2026, 6, 30)),
    ],
)
def test_annual_letters_without_a_year(name, published, expected):
    assert inbox.date_in_name(name) == published
    assert inbox.period_without_year(name, published)[0] == expected


def test_implausible_dates_are_not_used():
    period = date(2016, 12, 31)
    assert not inbox.plausible(date(2022, 11, 18), period)  # the file's creation date, years later
    assert inbox.plausible(date(2017, 1, 20), period)
    assert not inbox.plausible(date(2099, 1, 1), None)  # never in the future


def test_infer_published_both_orders():
    assert inbox.infer_published("Dated 15 October 2026.") == date(2026, 10, 15)
    assert inbox.infer_published("no date here") is None


def test_infer_published_ordinals_and_numeric_dates():
    """The owner (2026-10-21): letters nearly always carry a date, written out or numeric."""
    assert inbox.infer_published("October 10th, 2026") == date(2026, 10, 10)
    assert inbox.infer_published("the 3rd of March, 2025") == date(2025, 3, 3)
    assert inbox.infer_published("Sept. 1, 2026") == date(2026, 9, 1)
    assert inbox.infer_published("as of 10/15/2026") is None  # numeric only when asked
    assert inbox.infer_published("as of 10/15/2026", numeric=True) == date(2026, 10, 15)
    assert inbox.infer_published("as of 3/31/26", numeric=True) == date(2026, 3, 31)
    assert inbox.infer_published("ratio 13/45/26", numeric=True) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2018-Shareholders-Letter", date(2018, 12, 31)),
        ("2016-Final-Shareholders-letter", date(2016, 12, 31)),
        ("Performance 12/31/25 - 3/31/26", date(2026, 3, 31)),
        ("Performance 12/31/25 through 03/31/2026", date(2026, 3, 31)),
        ("as of 6/30/26", date(2026, 6, 30)),
        ("as of 6/15/26", None),  # not a quarter end: not a period
    ],
)
def test_infer_period_from_bare_years_and_numeric_ranges(text, expected):
    assert inbox.infer_period(text)[0] == expected


def test_signature_date_and_no_future_period(tmp_path):
    f = inbox.InboxFile(None, "public", "2018-Shareholders-Letter.pdf", "x", 1)
    f.head = "FAIRFAX FINANCIAL HOLDINGS LIMITED To Our Shareholders: an excellent year in 2018"
    f.tail = "see you at our shareholders' meeting in April.\nMarch 8, 2019\nV. Prem Watsa"
    inbox.date_and_kind(f, date(2026, 10, 20))
    assert (f.period_end, f.kind) == (date(2018, 12, 31), "annual_letter")
    assert (f.published_on, f.published_basis) == (date(2019, 3, 8), "stated")
    g = inbox.InboxFile(None, "public", "Targets.pdf", "x", 1)
    g.head = "Our FY2027 targets. Annual letter 2027 preview"  # a period in the future is not a period
    inbox.date_and_kind(g, date(2026, 10, 20))
    assert (g.period_end, g.published_on, g.published_basis) == (None, date(2026, 10, 20), "first_seen")
    # Trian's Solventum release: a target year in the headline, the date in the file name and the dateline
    h = inbox.InboxFile(None, "public", "2025-01-08-SOLV-Shareholder-Letter-Release.pdf", "x", 1)
    h.head = (
        "Trian Issues Open Letter to Solventum Shareholders " + "x" * 420 + " Worth $140 by Year-End 2027"
    )
    h.head += " NEW YORK, Jan. 8, 2025 - Trian Fund Management"
    inbox.date_and_kind(h, date(2026, 10, 20))
    assert (h.period_end, h.published_on, h.published_basis) == (None, date(2025, 1, 8), "stated")
    h.rel = "SOLV-Shareholder-Letter-Release.pdf"  # without the file-name date, the dateline is read
    inbox.date_and_kind(h, date(2026, 10, 20))
    assert (h.published_on, h.published_basis) == (date(2025, 1, 8), "stated")


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


def test_as_of_date_is_not_a_publication_date(cfg, box):
    pdf = make_pdf(
        ["Bonsai Partners", "1H 2024 Letter", "Performance as of June 30, 2024"], title="1H 2024 Letter"
    )
    (box / "public-websites" / "b.pdf").write_bytes(pdf)
    f = _scan(cfg, box)["b.pdf"]
    assert f.manager == "bonsai" and f.period_end == date(2024, 6, 30)
    assert f.published_basis != "stated"
