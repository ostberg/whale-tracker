"""The website collector (W-046) against a fake web: robots, hosts, paging, parsing and the Azure guard."""

from datetime import date

import pytest

from test_inbox import make_pdf
from whales import collect_web, config
from whales.sources import web

UA = "Tocqueville Asset Management test@example.com"


class _Response:
    def __init__(self, status, body, ctype, url):
        self.status, self._body, self._url = status, body, url
        self.headers = type("H", (), {"get_content_type": lambda _self: ctype})()

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_web(pages: dict):
    """An opener serving ``pages``: url -> body, or (status, body, content type, final url)."""
    seen = []

    def opener(request, timeout):
        url = request.full_url
        seen.append(url)
        value = pages.get(url, (404, b"", "text/plain", url))
        if isinstance(value, (bytes, str)):
            value = (200, value.encode() if isinstance(value, str) else value, "text/html", url)
        status, body, ctype, final = value
        if status >= 400:
            import urllib.error

            raise urllib.error.HTTPError(url, status, "x", {}, None)
        return _Response(status, body, ctype, final)

    return opener, seen


ROBOTS_OPEN = "User-agent: *\nDisallow: /private/\n"


def client(pages):
    opener, seen = fake_web(pages)
    return web.WebClient(UA, opener=opener, min_gap=0), seen


def test_robots_disallow_is_respected():
    c, _ = client({"https://m.test/robots.txt": ROBOTS_OPEN})
    with pytest.raises(web.WebError, match="robots.txt disallows"):
        c.get("https://m.test/private/letter.pdf", {"m.test"})


def test_missing_robots_means_no_rules_but_unreadable_means_stop():
    c, _ = client({"https://m.test/a.pdf": (200, b"%PDF-1.4", "application/pdf", "https://m.test/a.pdf")})
    assert c.get("https://m.test/a.pdf", {"m.test"})[1] == "application/pdf"
    c2, _ = client({"https://n.test/robots.txt": (503, b"", "text/plain", "https://n.test/robots.txt")})
    with pytest.raises(web.WebError, match="unreadable"):
        c2.get("https://n.test/a.pdf", {"n.test"})


def test_other_hosts_and_redirects_are_refused():
    c, _ = client(
        {
            "https://m.test/robots.txt": ROBOTS_OPEN,
            "https://m.test/go": (200, b"x", "text/html", "https://evil.test/x"),
        }
    )
    with pytest.raises(web.WebError, match="not allowed"):
        c.get("https://other.test/x", {"m.test"})
    with pytest.raises(web.WebError, match="redirected"):
        c.get("https://m.test/go", {"m.test"})
    with pytest.raises(web.WebError, match="scheme"):
        c.get("ftp://m.test/x", {"m.test"})


def test_dropped_connection_is_retried_once():
    import urllib.error

    calls = []

    def flaky(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise urllib.error.URLError("Cannot assign requested address")  # seen in the Azure job
        return _Response(200, b"ok", "text/plain", request.full_url)

    c = web.WebClient(UA, opener=flaky, min_gap=0, retry_wait=0)
    assert c._raw("https://m.test/a")[1] == b"ok" and len(calls) == 2

    def down(request, timeout):
        calls.append(request.full_url)
        raise urllib.error.URLError("down")

    calls.clear()
    c = web.WebClient(UA, opener=down, min_gap=0, retry_wait=0)
    with pytest.raises(web.WebError, match="could not reach"):
        c._raw("https://m.test/a")
    assert len(calls) == 2


def test_non_ascii_urls_are_percent_encoded_once():
    opener, seen = fake_web({"https://m.test/memos/d%C3%A9j%C3%A0-vu%20all.pdf": b"%PDF-"})
    c = web.WebClient(UA, opener=opener, min_gap=0)
    assert c._raw("https://m.test/memos/déjà-vu all.pdf")[0] == 200
    assert c._raw("https://m.test/memos/d%C3%A9j%C3%A0-vu%20all.pdf")[0] == 200  # already encoded: unchanged
    assert seen == ["https://m.test/memos/d%C3%A9j%C3%A0-vu%20all.pdf"] * 2
    assert web.quote_url("https://m.test/a?x=1&y=2#f") == "https://m.test/a?x=1&y=2#f"


def test_links_rule_with_paging_stops_when_nothing_new():
    page = '<a href="/l/{0}.pdf">Q{0} letter</a> <a href="/about">About</a> <a href="https://x.test/l/9.pdf">x</a>'
    pages = {
        "https://m.test/robots.txt": ROBOTS_OPEN,
        "https://m.test/letters?page=0": page.format(1) + page.format(2),
        "https://m.test/letters?page=1": page.format(3),
        "https://m.test/letters?page=2": page.format(3),
    }
    c, seen = client(pages)
    rule = web.WebRule(
        "links",
        ("https://m.test/letters?page=0",),
        r"/l/\d+\.pdf$",
        pages="https://m.test/letters?page={n}",
        max_pages=10,
    )
    found = web.candidates(c, rule)
    assert [x.url for x in found] == [
        "https://m.test/l/1.pdf",
        "https://m.test/l/2.pdf",
        "https://m.test/l/3.pdf",
    ]
    assert found[0].text == "Q1 letter"
    assert "https://m.test/letters?page=3" not in seen  # page 2 added nothing, so paging stopped


def test_feed_and_sitemap_parsing():
    feed = (
        "<rss><channel><item><title><![CDATA[Market Comment: Rates]]></title>"
        "<link>https://m.test/comment/rates/</link></item></channel></rss>"
    )
    assert web.feed_links(feed) == [
        web.WebCandidate("https://m.test/comment/rates/", "Market Comment: Rates")
    ]
    sitemap = (
        "<urlset><url><loc>https://m.test/memo/a</loc></url><url><loc> https://m.test/x </loc></url></urlset>"
    )
    assert web.sitemap_locations(sitemap) == ["https://m.test/memo/a", "https://m.test/x"]


def test_describe_html_and_pdf():
    page = (
        b"<html><head><title>Q2 2026 Letter to Partners</title><script>x=1</script></head>"
        b"<body>July 20, 2026 Dear partners</body></html>"
    )
    f = collect_web.describe(
        web.WebCandidate("https://m.test/q2", "Q2 letter"), page, "text/html", date(2026, 10, 1)
    )
    assert f.title == "Q2 2026 Letter to Partners" and f.period_end == date(2026, 6, 30)
    assert (f.published_on, f.published_basis) == (date(2026, 7, 20), "stated") and "x=1" not in f.head
    pdf = make_pdf(["Alluvial Capital Management", "Q1 2026 Letter to Partners", "April 20, 2026"])
    g = collect_web.describe(
        web.WebCandidate("https://m.test/q1.pdf", ""), pdf, "application/pdf", date(2026, 10, 1)
    )
    assert g.period_end == date(2026, 3, 31) and g.published_on == date(2026, 4, 20) and g.pages == 1


def test_describe_reads_the_page_markup_date_and_ignores_generic_link_text():
    """Oaktree memos were all dated the day they were collected (first Azure run, 2026-10-21): the memo's
    date sits in a <time> tag past the first 400 characters of visible text. Trian's PDF was titled
    'READ MORE' after its link."""
    nav = b"<nav>" + b"Insights Memos About Careers Contact " * 30 + b"</nav>"
    page = (
        b"<html><head><title>Sea Change</title></head><body>"
        + nav
        + b'<time class="embedded-date" datetime=">2022-12-13T08:00:00.0000000Z" pubdate>Dec 13, 2022</time>'
        b"<p>December 13, 2022</p><p>Memo text</p></body></html>"
    )
    f = collect_web.describe(
        web.WebCandidate("https://m.test/memo/sea-change", ""), page, "text/html", date(2026, 10, 20)
    )
    assert (f.published_on, f.published_basis) == (date(2022, 12, 13), "stated")
    assert collect_web.page_date(
        '<meta property="article:published_time" content="2025-02-03T10:00:00Z">'
    ) == date(2025, 2, 3)
    assert collect_web.page_date('"datePublished":"2024-05-06"') == date(2024, 5, 6)
    assert collect_web.page_date("<p>no markup date</p>") is None
    pdf = make_pdf(["Letter to the board", "April 20, 2026"])
    g = collect_web.describe(
        web.WebCandidate("https://m.test/wp-content/uploads/2026/04/Trian-Letter.pdf", "READ MORE"),
        pdf,
        "application/pdf",
        date(2026, 10, 1),
    )
    assert g.title == "Trian-Letter.pdf"


def test_recording_refuses_to_run_outside_azure(monkeypatch):
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    with pytest.raises(collect_web.NotInAzure):
        collect_web.collect(None, None, None, [])


def test_web_rules_in_config_are_checked(tmp_path):
    from test_config import MANAGERS, SOURCE, TAGS, TOPICS, _write

    good = SOURCE + 'web = { method = "links", index = ["https://x.test/letters"], match = "\\\\.pdf$" }\n'
    cfg = config.load(_write(tmp_path, tags=TAGS, topics=TOPICS, managers=MANAGERS, sources=good))
    assert cfg.sources[0].web.allowed_hosts() == {"x.test"}
    bad = SOURCE + 'web = { method = "crawl", index = ["http://x.test"], match = "(" }\n'
    with pytest.raises(config.ConfigError) as e:
        config.load(_write(tmp_path, tags=TAGS, topics=TOPICS, managers=MANAGERS, sources=bad))
    text = " ".join(e.value.problems)
    assert "method must be" in text and "https URLs" in text and "not a valid regex" in text


def test_javascript_links_yield_their_url():
    page = (
        "<a href=\"javascript:openPDF('Old memo','https://m.test/docs/memos/old.pdf?sfvrsn=2')\">Old memo</a>"
        '<a href="javascript:void(0)">menu</a>'
    )
    links = web.page_links(page, "https://m.test/memos")
    assert [link.url for link in links] == ["https://m.test/docs/memos/old.pdf?sfvrsn=2"]


def test_follow_reads_one_hop_and_paging_starts_where_told():
    sitemap = "<urlset><url><loc>https://m.test/campaign-a/</loc></url><url><loc>https://m.test/contact/</loc></url></urlset>"
    pages = {
        "https://m.test/robots.txt": ROBOTS_OPEN,
        "https://m.test/page-sitemap.xml": sitemap,
        "https://m.test/campaign-a/": '<a href="/up/letter.pdf">L</a> <a href="/up/JA-letter.pdf">JA</a>',
    }
    c, seen = client(pages)
    rule = web.WebRule(
        "sitemap",
        ("https://m.test/page-sitemap.xml",),
        r"/up/[^/]+\.pdf$",
        exclude=r"/JA-",
        follow=r"^https://m\.test/(?!contact/)[a-z-]+/$",
    )
    assert [x.url for x in web.candidates(c, rule)] == ["https://m.test/up/letter.pdf"]
    assert "https://m.test/contact/" not in seen
    paged = web.WebRule(
        "links", ("https://m.test/l/",), "x", pages="https://m.test/l/page/{n}/", first=2, max_pages=3
    )
    assert web.index_urls(paged)[1:] == [
        "https://m.test/l/page/2/",
        "https://m.test/l/page/3/",
        "https://m.test/l/page/4/",
    ]


def test_a_missing_page_ends_paging_quietly():
    pages = {"https://m.test/robots.txt": ROBOTS_OPEN, "https://m.test/l/": '<a href="/d/1.pdf">1</a>'}
    c, _ = client(pages)
    rule = web.WebRule(
        "links",
        ("https://m.test/l/",),
        r"/d/\d+\.pdf$",
        pages="https://m.test/l/page/{n}/",
        first=2,
        max_pages=5,
    )
    assert [x.url for x in web.candidates(c, rule)] == ["https://m.test/d/1.pdf"]


class _RedateDb:
    """Answers the redate query with the given rows; records every statement of the connection."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def run(self, sql, params=()):
        assert sql.startswith("\nSELECT DISTINCT ON (d.id)") and params == (None, None)
        return self.rows

    def connection(self):
        return self

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

        class _R:
            rowcount = 17

        return _R()

    def transaction(self):
        import contextlib

        return contextlib.nullcontext()


class _RedateClient:
    def __init__(self, pages):
        self.pages, self.got = pages, []

    def get(self, url, allowed_hosts):
        self.got.append((url, allowed_hosts))
        return self.pages[url], "text/html"


def test_redate_takes_the_stated_date_and_supersedes_the_runs(tmp_path, monkeypatch):
    from test_config import MANAGERS, SOURCE, TAGS, TOPICS, _write

    good = SOURCE + 'web = { method = "links", index = ["https://x.test/letters"], match = "memo" }\n'
    cfg = config.load(_write(tmp_path, tags=TAGS, topics=TOPICS, managers=MANAGERS, sources=good))
    rows = [
        (1, "m1", "Sea Change", date(2026, 10, 20), None, "https://x.test/memo/sea-change", "s1"),
        (2, "m1", "No date", date(2026, 10, 20), None, "https://x.test/memo/no-date", "s1"),
        (3, "m1", "Other source", date(2026, 10, 20), None, "https://x.test/memo/x", "s9"),
    ]
    pages = {
        "https://x.test/memo/sea-change": b'<html><body><time datetime="2022-12-13T08:00:00Z">x</time>'
        b"</body></html>",
        "https://x.test/memo/no-date": b"<html><body>nothing</body></html>",
    }
    db, client = _RedateDb(rows), _RedateClient(pages)
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    dry = collect_web.redate(db, client, cfg)
    assert [r.document_id for r in dry] == [1, 2, 3] and client.got == [] and db.calls == []
    with pytest.raises(collect_web.NotInAzure):
        collect_web.redate(db, client, cfg, apply=True)
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://169.254.169.254/x")
    out = collect_web.redate(db, client, cfg, apply=True)
    assert (out[0].new, out[0].basis, out[0].runs_superseded) == (date(2022, 12, 13), "stated", 17)
    assert out[1].new is None and out[1].error is None  # nothing better found: left alone
    assert out[2].new is None and "no web rule" in out[2].error
    assert client.got == [
        ("https://x.test/memo/sea-change", {"x.test"}),
        ("https://x.test/memo/no-date", {"x.test"}),
    ]
    update, supersede = db.calls
    assert update[0].startswith("UPDATE letters.document SET published_on") and update[1] == (
        date(2022, 12, 13),
        "stated",
        None,
        1,
    )
    assert supersede[0].startswith("UPDATE letters.extraction_run SET status = 'superseded'") and supersede[
        1
    ] == (1,)
