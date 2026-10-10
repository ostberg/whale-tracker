"""A small SEC EDGAR client (W-023): submissions per CIK and filing index pages.

SEC fair access: a User-Agent naming the organisation and a monitored contact email is required, and at most
10 requests a second are allowed. This client stays at about 4 a second and refuses to run without
``SEC_USER_AGENT``. Responses are untrusted input: index pages are read with narrow regular expressions, never
an HTML or XML parser that could fetch anything.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

SEC = "https://www.sec.gov"
DATA = "https://data.sec.gov"


class EdgarError(RuntimeError):
    """EDGAR refused or failed a request."""


@dataclass(frozen=True)
class Filing:
    cik: int
    accession: str
    form: str
    filed: date
    period: date | None
    items: tuple[str, ...]
    primary_document: str


@dataclass(frozen=True)
class IndexDocument:
    seq: str
    description: str
    name: str
    type: str
    size: int | None
    url: str


@dataclass(frozen=True)
class FilingIndex:
    filed_by: tuple[str, ...]
    subject: tuple[str, ...]
    documents: tuple[IndexDocument, ...]


def user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in ua or " " not in ua:
        raise EdgarError(
            "SEC_USER_AGENT must name the organisation and a monitored contact email (AGENTS.md)"
        )
    return ua


def _date(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


class EdgarClient:
    def __init__(
        self, ua: str | None = None, *, pause: float = 0.25, opener: Callable = urllib.request.urlopen
    ):
        self.ua = ua or user_agent()
        self.pause = pause
        self._opener = opener
        self._last = 0.0
        self.requests = 0

    def get(self, url: str) -> tuple[bytes, str]:
        """Body and content type. Retries twice on 429 and 5xx; anything else fails loudly."""
        if not url.startswith((SEC, DATA)):
            raise EdgarError(f"refusing a non-SEC URL: {url}")
        for attempt in range(3):
            wait = self.pause - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(
                url, headers={"User-Agent": self.ua, "Accept-Encoding": "identity"}
            )
            try:
                with self._opener(request, timeout=60) as response:
                    self._last = time.monotonic()
                    self.requests += 1
                    content_type = response.headers.get_content_type() if response.headers else ""
                    return response.read(), content_type
            except urllib.error.HTTPError as e:
                self._last = time.monotonic()
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise EdgarError(f"HTTP {e.code} for {url}") from e
        raise EdgarError(f"gave up on {url}")

    def get_json(self, url: str) -> dict:
        return json.loads(self.get(url)[0])

    def filings(self, cik: int, since: date) -> list[Filing]:
        """Every filing by ``cik`` on or after ``since``, newest first, paging into older files as needed."""
        sub = self.get_json(f"{DATA}/submissions/CIK{cik:010d}.json")
        blocks = [sub["filings"]["recent"]]
        for f in sub["filings"].get("files", []):
            if f.get("filingTo", "9999") >= since.isoformat():
                blocks.append(self.get_json(f"{DATA}/submissions/{f['name']}"))
        out = []
        for b in blocks:
            for form, filed, period, acc, items, doc in zip(
                b["form"],
                b["filingDate"],
                b["reportDate"],
                b["accessionNumber"],
                b.get("items", [""] * len(b["form"])),
                b["primaryDocument"],
                strict=True,
            ):
                filed_on = date.fromisoformat(filed)
                if filed_on >= since:
                    its = tuple(i.strip() for i in (items or "").split(",") if i.strip())
                    out.append(Filing(cik, acc, form, filed_on, _date(period), its, doc))
        return sorted(out, key=lambda f: (f.filed, f.accession), reverse=True)

    def filing_index(self, cik: int, accession: str) -> FilingIndex:
        url = f"{SEC}/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.htm"
        return parse_index(self.get(url)[0].decode("utf-8", "replace"))


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_index(page: str) -> FilingIndex:
    """The filer and subject companies and the document table of an EDGAR ``-index.htm`` page."""
    filed_by, subject = [], []
    for m in re.finditer(r'<span class="companyName">(.*?)</span>', page, re.S):
        name = _text(m.group(1))
        role = re.search(r"\((Filed by|Subject|Filer|Reporting)\)", name)
        clean = re.sub(r"\s*\((Filed by|Subject|Filer|Reporting)\).*$", "", name).strip()
        if role and role.group(1) == "Subject":
            subject.append(clean)
        else:
            filed_by.append(clean)
    table = re.search(r'<table class="tableFile".*?</table>', page, re.S)
    docs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0) if table else "", re.S)[1:]:
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        # inline-XBRL documents link through the viewer: /ix?doc=/Archives/...; keep the direct path
        href = re.search(r'href="(?:/ix\?doc=)?(/Archives/[^"]+)"', row)
        if len(cells) < 5 or not href:
            continue
        seq, description, name, doc_type, size = cells[:5]
        name = re.sub(r"\s+iXBRL$", "", name)  # the viewer's tag, not part of the file name
        docs.append(
            IndexDocument(
                seq=seq,
                description=description,
                name=name,
                type=doc_type,
                size=int(size) if size.isdigit() else None,
                url=SEC + href.group(1),
            )
        )
    return FilingIndex(tuple(filed_by), tuple(subject), tuple(docs))
