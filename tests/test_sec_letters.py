"""The SEC collector's parsing and rules, against index pages saved from EDGAR (tests/fixtures/edgar)."""

from datetime import date
from pathlib import Path

import pytest

from whales.sources import edgar, sec_letters

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _index(name: str) -> edgar.FilingIndex:
    return edgar.parse_index((FIXTURES / name).read_text(encoding="utf-8"))


def _filing(form: str, items: tuple[str, ...] = ()) -> edgar.Filing:
    return edgar.Filing(1, "0000000000-26-000001", form, date(2026, 1, 2), None, items, "x.htm")


def test_parse_dfan14a_index():
    idx = _index("DFAN14A_0000921895-25-001599-index.htm")
    assert idx.filed_by == ("Elliott Investment Management L.P.",)
    assert idx.subject == ("Phillips 66",)
    types = [(d.seq, d.type, d.name) for d in idx.documents]
    assert ("2", "DFAN14A", "ex991dfan14a10168303_052025.pdf") in types
    pdf = next(d for d in idx.documents if d.name.endswith(".pdf"))
    assert pdf.description == "EXHIBIT 99.1" and pdf.size == 1573278
    assert pdf.url.startswith("https://www.sec.gov/Archives/edgar/data/")


def test_dfan14a_takes_letter_and_exhibit_not_images():
    idx = _index("DFAN14A_0000921895-25-001599-index.htm")
    wanted = sec_letters.documents_wanted("activist", _filing("DFAN14A"), idx.documents)
    assert sorted(d.name for d in wanted) == [
        "dfan14a10168303_05202025.htm",
        "ex991dfan14a10168303_052025.pdf",
    ]


def test_13d_amendment_without_exhibits_yields_nothing():
    idx = _index("SCHEDULE_13D-A_0000921895-26-002741-index.htm")
    assert idx.subject == ("Qorvo, Inc.",)
    assert sec_letters.documents_wanted("activist", _filing("SCHEDULE 13D/A"), idx.documents) == []


@pytest.mark.parametrize(
    "description",
    [
        "SCHEDULE 1",
        "SCHEDULE B",
        "TRANSACTIONS IN THE SHARES OF THE ISSUER SINCE THE FILING",
        "VOTING AGREEMENT",
        "AGREEMENT, DATED MARCH 22, 2026",
        "EX-99.5 HOLDERS RTS",
        "EX-99.CERT",
        "FORM OF INDEMNIFICATION LETTER",
        "SCHEDULA A",
        "AMENDMENT TO CONFIRMATION",
    ],
)
def test_boilerplate_descriptions_are_skipped(description):
    assert sec_letters.SKIP_DESCRIPTIONS.search(description)


@pytest.mark.parametrize(
    "description", ["", "EX-99.1", "EXHIBIT 99.1", "LETTER TO SHAREHOLDERS", "PRESS RELEASE"]
)
def test_letter_descriptions_are_kept(description):
    assert not sec_letters.SKIP_DESCRIPTIONS.search(description)


def test_inline_xbrl_documents_are_found():
    row = (
        '<table class="tableFile"><tr><th>h</th></tr><tr><td scope="row">1</td><td scope="row"></td>'
        '<td scope="row"><a href="/ix?doc=/Archives/edgar/data/2002660/000119312526360100/d87027dncsrs.htm">'
        'd87027dncsrs.htm</a> iXBRL</td><td scope="row">N-CSRS</td><td scope="row">900000</td></tr></table>'
    )
    (doc,) = edgar.parse_index(row).documents
    assert doc.name == "d87027dncsrs.htm"
    assert doc.type == "N-CSRS"
    assert doc.url == "https://www.sec.gov/Archives/edgar/data/2002660/000119312526360100/d87027dncsrs.htm"


def test_13d_exhibit_kept_but_boilerplate_skipped():
    docs = (
        edgar.IndexDocument(
            "2", "LETTER TO THE BOARD", "ex99-1.htm", "EX-99.1", 100, "https://www.sec.gov/a"
        ),
        edgar.IndexDocument(
            "3", "JOINT FILING AGREEMENT", "ex99-2.htm", "EX-99.2", 100, "https://www.sec.gov/b"
        ),
        edgar.IndexDocument("4", "POWER OF ATTORNEY", "ex24.htm", "EX-24", 100, "https://www.sec.gov/c"),
    )
    wanted = sec_letters.documents_wanted("activist", _filing("SC 13D/A"), docs)
    assert [d.name for d in wanted] == ["ex99-1.htm"]


@pytest.mark.parametrize(
    ("preset", "form", "items", "expected"),
    [
        ("earnings_8k", "8-K", ("2.02", "9.01"), True),
        ("earnings_8k", "8-K", ("5.07", "9.01"), False),
        ("activist", "SCHEDULE 13D/A", (), True),
        ("activist", "SCHEDULE 13G", (), False),
        ("ncsr", "N-CSRS", (), True),
        ("ncsr", "N-PX", (), False),
    ],
)
def test_filing_wanted(preset, form, items, expected):
    assert sec_letters.filing_wanted(preset, _filing(form, items)) is expected


def test_type_matching_is_exact_unless_starred():
    assert sec_letters.type_matches("EX-99.1", ["EX-99*"])
    assert not sec_letters.type_matches("N-CSRS", ["N-CSR"])
    assert sec_letters.type_matches("N-CSRS", ["N-CSRS"])


def test_pdf_flags():
    assert sec_letters.pdf_flags(b"%PDF-1.7 plain") == (False, None, True)
    locked = b"%PDF-1.7 << /Filter /Standard /V 5 /R 6 /P -1052 >>"
    assert sec_letters.pdf_flags(locked) == (True, -1052, False)
    open_ = b"%PDF-1.7 << /Filter /Standard /V 2 /P -4 >>"
    assert sec_letters.pdf_flags(open_) == (True, -4, True)


def test_client_refuses_other_hosts():
    client = edgar.EdgarClient("Test Org test@example.com")
    with pytest.raises(edgar.EdgarError, match="non-SEC"):
        client.get("https://example.com/x")


def test_user_agent_must_carry_an_email(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Tocqueville")
    with pytest.raises(edgar.EdgarError, match="contact email"):
        edgar.user_agent()


def test_label_in_type_column_is_also_checked():
    docs = (edgar.IndexDocument("5", "", "ex99-5.htm", "EX-99.5 HOLDERS RTS", 10, "https://www.sec.gov/x"),)
    assert sec_letters.documents_wanted("activist", _filing("SCHEDULE 13D/A"), docs) == []
