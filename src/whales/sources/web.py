"""A polite fetcher for managers' own websites, and the rules that find their letters (W-046).

Politeness and safety, for every request:
- the declared User-Agent (organisation and contact email, as for SEC);
- robots.txt checked first, per host, read with that User-Agent. A robots.txt that answers 4xx means no
  restrictions (RFC 9309); one that cannot be read at all means stop;
- at least ``MIN_GAP`` seconds between requests to the same host, or the site's Crawl-delay if longer;
- only http(s), only hosts the source allows (the index page's host and any listed in config), checked again
  after redirects, so a stray link to another domain is never followed;
- a size cap on every response.

Pages and feeds are untrusted input: links are read with narrow regular expressions, never an HTML or XML
parser that could fetch anything.
"""

from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass

MIN_GAP = 2.0
MAX_BYTES = 60 * 1024 * 1024


class WebError(RuntimeError):
    """A fetch that was refused (robots, host, scheme, size) or failed."""


@dataclass(frozen=True)
class WebRule:
    """How to list one source's documents. ``method``: links (index pages), sitemap or feed."""

    method: str
    index: tuple[str, ...]
    match: str
    text: str | None = None
    exclude: str | None = None
    pages: str | None = None
    max_pages: int = 1
    hosts: tuple[str, ...] = ()

    def allowed_hosts(self) -> set[str]:
        return {urllib.parse.urlsplit(u).hostname or "" for u in self.index} | set(self.hosts)


@dataclass(frozen=True)
class WebCandidate:
    url: str
    text: str


class WebClient:
    def __init__(
        self, user_agent: str, *, opener: Callable = urllib.request.urlopen, min_gap: float = MIN_GAP
    ):
        self.ua = user_agent
        self._opener = opener
        self._min_gap = min_gap
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests = 0

    def _raw(self, url: str) -> tuple[int, bytes, str, str]:
        request = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "identity"})
        try:
            with self._opener(request, timeout=60) as r:
                body = r.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise WebError(f"larger than {MAX_BYTES} bytes: {url}")
                ctype = r.headers.get_content_type() if r.headers else ""
                return getattr(r, "status", 200), body, ctype, r.geturl() if hasattr(r, "geturl") else url
        except urllib.error.HTTPError as e:
            return e.code, b"", "", url
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise WebError(f"could not reach {url}: {e}") from e

    def robots(self, scheme: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        """The host's robots rules; None means 'no rules' (robots.txt answered 4xx)."""
        key = f"{scheme}://{host}"
        if key not in self._robots:
            self._pause(host, None)
            status, body, _, _ = self._raw(f"{key}/robots.txt")
            self.requests += 1
            if 400 <= status < 500:
                self._robots[key] = None
            elif status != 200:
                raise WebError(f"robots.txt for {host} unreadable (HTTP {status}); not fetching")
            else:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.decode("utf-8", "replace").splitlines())
                self._robots[key] = rp
        return self._robots[key]

    def _pause(self, host: str, rp: urllib.robotparser.RobotFileParser | None) -> None:
        delay = self._min_gap
        if rp is not None:
            delay = max(delay, float(rp.crawl_delay(self.ua) or 0))
        wait = delay - (time.monotonic() - self._last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def get(self, url: str, allowed_hosts: set[str]) -> tuple[bytes, str]:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise WebError(f"refusing scheme {parts.scheme!r}: {url}")
        host = parts.hostname or ""
        if host not in allowed_hosts:
            raise WebError(f"host {host} is not allowed for this source: {url}")
        rp = self.robots(parts.scheme, host)
        if rp is not None and not rp.can_fetch(self.ua, url):
            raise WebError(f"robots.txt disallows {url}")
        self._pause(host, rp)
        status, body, ctype, final = self._raw(url)
        self.requests += 1
        if (urllib.parse.urlsplit(final).hostname or "") not in allowed_hosts:
            raise WebError(f"redirected off the allowed hosts: {url} -> {final}")
        if status != 200:
            raise WebError(f"HTTP {status} for {url}")
        return body, ctype


# --- reading index pages, sitemaps and feeds -----------------------------------------------------------

_A = re.compile(r"<a\b[^>]*?\bhref\s*=\s*(?:\"([^\"]*)\"|'([^']*)')[^>]*>(.*?)</a>", re.I | re.S)


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def page_links(page: str, base: str) -> list[WebCandidate]:
    out = []
    for m in _A.finditer(page):
        href = html.unescape(m.group(1) or m.group(2) or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        out.append(WebCandidate(urllib.parse.urljoin(base, href).split("#", 1)[0], _clean(m.group(3))[:300]))
    return out


def sitemap_locations(xml: str) -> list[str]:
    return [html.unescape(u).strip() for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.I)]


def feed_links(xml: str) -> list[WebCandidate]:
    out = []
    for item in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", xml, re.I | re.S):
        title_match = re.search(r"<title[^>]*>(.*?)</title>", item, re.S | re.I)
        raw_title = title_match.group(1) if title_match else ""
        title = _clean(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw_title, flags=re.S))
        links = re.findall(r"<link>\s*([^<\s]+)\s*</link>", item, re.I)
        links += re.findall(r"<link\b[^>]*\bhref=\"([^\"]+)\"", item, re.I)
        links += re.findall(r"<enclosure\b[^>]*\burl=\"([^\"]+)\"", item, re.I)
        out += [WebCandidate(html.unescape(u).strip(), title[:300]) for u in links]
    return out


def _wanted(rule: WebRule, c: WebCandidate) -> bool:
    if (urllib.parse.urlsplit(c.url).hostname or "") not in rule.allowed_hosts():
        return False
    if not re.search(rule.match, c.url):
        return False
    if rule.text and not re.search(rule.text, c.text, re.I):
        return False
    return not (rule.exclude and re.search(rule.exclude, c.url))


def index_urls(rule: WebRule) -> list[str]:
    urls = list(rule.index)
    if rule.pages:
        urls += [rule.pages.format(n=n) for n in range(rule.max_pages)]
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def candidates(client: WebClient, rule: WebRule) -> list[WebCandidate]:
    """Every wanted document URL, first occurrence kept, in page order. Stops paging at the first page that
    adds nothing new."""
    hosts = rule.allowed_hosts()
    found: dict[str, WebCandidate] = {}
    for url in index_urls(rule):
        body, _ = client.get(url, hosts)
        text = body.decode("utf-8", "replace")
        if rule.method == "links":
            items = page_links(text, url)
        elif rule.method == "feed":
            items = feed_links(text)
        else:  # sitemap, one level of sitemap index followed
            locs = sitemap_locations(text)
            if "<sitemapindex" in text[:2000].lower():
                nested = []
                for sub in locs:
                    if (urllib.parse.urlsplit(sub).hostname or "") in hosts:
                        nested += sitemap_locations(client.get(sub, hosts)[0].decode("utf-8", "replace"))
                locs = nested
            items = [WebCandidate(u, "") for u in locs]
        before = len(found)
        for c in items:
            if _wanted(rule, c) and c.url not in found:
                found[c.url] = c
            elif c.url in found and not found[c.url].text and c.text:
                found[c.url] = c
        if rule.pages and url not in rule.index and len(found) == before:
            break
    return list(found.values())
