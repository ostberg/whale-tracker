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
