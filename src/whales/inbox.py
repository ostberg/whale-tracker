"""The letter inbox (W-044): find, identify and record letters that people collected.

    whales inbox scan              what is in the inbox and who each letter is from (no database)
    whales inbox load --apply      record new letters as whales_ingest (needs the database)

The inbox is a folder outside the repository (``WHALES_INBOX_DIR``, default ``../Whale Tracker Inbox``) with
one subfolder per route: ``public-websites`` (downloaded from a manager's own site) and ``shared-by-manager``
(sent by the manager, permission kept in ``shared-by-manager/permissions``). No naming rules: the manager is
taken from a subfolder named after a manager slug, else from the earliest match of a manager's name or alias
in the file name, PDF metadata or first page. Anything unclear is listed, not guessed.

PDFs are untrusted input. pypdf is pure Python, never renders, never runs scripts, and every file is read
with a cap on pages; a file that cannot be read is reported and skipped.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import Config, Manager
from .sources.sec_letters import pdf_flags

ROUTES = {"public-websites": "public", "shared-by-manager": "shared"}
SKIP_DIRS = {"permissions"}
HEAD_PAGES = 2  # pages read to identify a letter
HEAD_CHARS = 4000
HEADER_CHARS = 800  # a manager's own name normally appears this early


def inbox_dir() -> Path:
    override = os.environ.get("WHALES_INBOX_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "Whale Tracker Inbox"


@dataclass
class InboxFile:
    path: Path
    route: str
    rel: str
    sha256: str
    size: int
    pages: int | None = None
    encrypted: bool = False
    pdf_permissions: int | None = None
    extract_allowed: bool | None = None
    title: str | None = None
    author: str | None = None
    created: date | None = None
    head: str = ""
    manager: str | None = None
    manager_basis: str = ""
    candidates: list[str] = field(default_factory=list)
    period_end: date | None = None
    published_on: date | None = None
    published_basis: str = "first_seen"
    kind: str = "other"
    error: str | None = None


# --- identifying the manager -------------------------------------------------------------------------


def aliases(m: Manager) -> list[str]:
    """Names a manager goes by: its config name, the name without a parenthesised part, the parenthesised part
    (often a person), and any explicit aliases."""
    out = {m.name}
    base = re.sub(r"\s*\(.*?\)\s*", " ", m.name).strip()
    out.add(base)
    out.update(p.strip() for p in re.findall(r"\(([^)]+)\)", m.name))
    out.update(m.aliases)
    return sorted((a for a in out if len(a) >= 4), key=len, reverse=True)


def identify(f: InboxFile, managers: tuple[Manager, ...]) -> None:
    """Set ``f.manager`` from a folder named after a manager slug, else from the earliest name match in the
    file name, metadata or first page. Leaves it None, with the contenders in ``f.candidates``, when
    unsure."""
    slugs = {m.slug for m in managers}
    for part in Path(f.rel).parts[:-1]:
        if part.lower() in slugs:
            f.manager, f.manager_basis = part.lower(), "folder"
            return
    haystack = " \n ".join(
        x for x in (re.sub(r"[_+\-.]+", " ", Path(f.rel).stem), f.title or "", f.author or "", f.head) if x
    )
    first: dict[str, int] = {}
    for m in managers:
        for a in aliases(m):
            hit = re.search(r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", haystack, re.I)
            if hit and (m.slug not in first or hit.start() < first[m.slug]):
                first[m.slug] = hit.start()
    ranked = sorted(first.items(), key=lambda kv: kv[1])
    f.candidates = [slug for slug, _ in ranked[:4]]
    if not ranked:
        return
    best, pos = ranked[0]
    meta_len = len(Path(f.rel).stem) + len(f.title or "") + len(f.author or "") + 12
    if pos > meta_len + HEADER_CHARS:
        return  # the name only appears deep in the text: probably a mention, not the author
    if len(ranked) > 1 and ranked[1][1] - pos < 40:
        return  # two managers named side by side: ask
    f.manager, f.manager_basis = best, "text"


# --- dates and kind -----------------------------------------------------------------------------------

_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
_ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_YEAR = r"(20[0-4]\d)(?!\d)"


def _qend(q: int, year: int) -> date:
    month, day = _QUARTER_END[q]
    return date(year, month, day)


def normalise(text: str) -> str:
    """Lower case; '+', '_', '-' and '.' as spaces (file names often use them); "Q1'24" as "Q1 2024"."""
    t = re.sub(r"[_+\-.]+", " ", text.lower())
    return re.sub(r"'\s?(\d{2})(?!\d)", r" 20\1", t)


_PERIOD_PATTERNS = [
    (rf"\bq([1-4])\s*{_YEAR}", lambda m: _qend(int(m[1]), int(m[2])), "quarterly_letter"),
    (r"\b(20[0-4]\d)\s*q([1-4])\b", lambda m: _qend(int(m[2]), int(m[1])), "quarterly_letter"),
    (
        r"\b([1-4])q\s*(20[0-4]\d|\d{2})(?!\d)",
        lambda m: _qend(int(m[1]), int(m[2][-2:]) + 2000),
        "quarterly_letter",
    ),
    (
        rf"\b(first|second|third|fourth|1st|2nd|3rd|4th) quarter(?: of)?,?\s*{_YEAR}",
        lambda m: _qend(_ORDINAL[m[1]], int(m[2])),
        "quarterly_letter",
    ),
    (rf"\b(?:h1|1h|first half)(?: of)?,?\s*{_YEAR}", lambda m: date(int(m[1]), 6, 30), "quarterly_letter"),
    (rf"\b(?:h2|2h|second half)(?: of)?,?\s*{_YEAR}", lambda m: date(int(m[1]), 12, 31), "annual_letter"),
    (
        rf"\b(?:half year|semi ?annual|sem annual|interim)(?: letter| report)?(?: of)?,?\s*{_YEAR}",
        lambda m: date(int(m[1]), 6, 30),
        "quarterly_letter",
    ),
    (
        rf"\b(?:ye|year ?end|full year|annual)(?: letter| report| review)?(?: of)?,?\s*{_YEAR}",
        lambda m: date(int(m[1]), 12, 31),
        "annual_letter",
    ),
    (
        r"\b(20[0-4]\d)\s*(?:ye|year ?end|annual (?:letter|report|review))\b",
        lambda m: date(int(m[1]), 12, 31),
        "annual_letter",
    ),
]


def infer_period(text: str) -> tuple[date | None, str]:
    """(period end, kind) from the EARLIEST period phrase in ``text``: 'Q3 2026', "Q1'24", '3Q26',
    'second quarter 2026', '1H 2024', 'H2 2025', 'YE 2025', 'Year End 2016', 'semi-annual 2026',
    'annual letter 2025'."""
    t = normalise(text)
    best: tuple[int, date, str] | None = None
    for pattern, to_date, kind in _PERIOD_PATTERNS:
        for m in re.finditer(pattern, t):
            try:
                d = to_date(m)
            except ValueError:
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), d, kind)
            break
    return (best[1], best[2]) if best else (None, "other")


def period_without_year(text: str, published: date | None) -> tuple[date | None, str]:
    """'Annual Letter' or 'Semi-Annual Letter' with no year: the period from the publication date."""
    if published is None:
        return None, "other"
    t = normalise(text)
    if re.search(r"\b(?:semi ?annual|sem annual|half year|interim)\b", t):
        if published.month >= 7:
            return date(published.year, 6, 30), "quarterly_letter"
        return date(published.year - 1, 12, 31), "annual_letter"
    if re.search(r"\bannual\b", t) and published.month <= 6:
        return date(published.year - 1, 12, 31), "annual_letter"
    return None, "other"


def date_in_name(name: str) -> date | None:
    """A date at the front of a file name, e.g. '2024.02.03-Annual-Letter'."""
    m = re.match(r"(20[0-4]\d)[.\-_ ](\d{2})[.\-_ ](\d{2})(?!\d)", name)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def infer_published(text: str) -> date | None:
    """The first full date written out, e.g. 'October 15, 2026' or '15 October 2026'."""
    names = "|".join(_MONTHS)
    for m in re.finditer(
        rf"\b({names})\s+(\d{{1,2}}),?\s+{_YEAR}|\b(\d{{1,2}})\s+({names}),?\s+{_YEAR}", text, re.I
    ):
        month, day, year = (m[1], m[2], m[3]) if m[1] else (m[5], m[4], m[6])
        try:
            return date(int(year), _MONTHS[month.lower()], int(day))
        except ValueError:
            continue
    return None


def plausible(d: date | None, period_end: date | None, today: date | None = None) -> bool:
    """A publication date must not be in the future and, when the period is known, must fall between a few
    days before the period end and 200 days after it."""
    if d is None or d > (today or date.today()):
        return False
    return period_end is None or (period_end - timedelta(days=5)) <= d <= (period_end + timedelta(days=200))


def infer_kind(f: InboxFile, period_kind: str) -> str:
    name = normalise(f"{f.rel} {f.title or ''}")
    if re.search(r"presentation|\bdeck\b|slides", name):
        return "presentation"
    if re.search(r"\bmemo\b", name):
        return "memo"
    if re.search(r"research (?:report|update)|\bfp\b", name):
        return "commentary"
    return period_kind


# --- reading files ------------------------------------------------------------------------------------


def _pdf_date(value) -> date | None:
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})", str(value or ""))
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def read_pdf(f: InboxFile, body: bytes) -> None:
    """Fill metadata, permission flags and the first pages' text. Never decrypts: an encrypted file that
    needs a key we do not hold is reported."""
    from io import BytesIO

    from pypdf import PdfReader

    f.encrypted, f.pdf_permissions, f.extract_allowed = pdf_flags(body)
    reader = PdfReader(BytesIO(body))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                f.error = "encrypted with a password"
                return
        except Exception as e:  # noqa: BLE001 - e.g. AES without the optional crypto extra
            f.error = f"encrypted; cannot read without an extra library ({type(e).__name__})"
            return
    f.pages = len(reader.pages)
    meta = reader.metadata or {}
    f.title = (meta.get("/Title") or None) and str(meta.get("/Title")).strip()[:300]
    f.author = (meta.get("/Author") or None) and str(meta.get("/Author")).strip()[:200]
    f.created = _pdf_date(meta.get("/CreationDate"))
    if f.extract_allowed is False:
        return  # W-030: the publisher forbids text extraction; identify from name and metadata only
    parts = []
    for page in reader.pages[:HEAD_PAGES]:
        parts.append(page.extract_text() or "")
    f.head = re.sub(r"[ \t]+", " ", "\n".join(parts))[:HEAD_CHARS]


def date_and_kind(f: InboxFile, first_seen: date) -> None:
    """Period from the file name first, then the title, then the first page; publication date from a date in
    the file name, a date written near the top, or the PDF's creation date, each only if plausible for the
    period; failing those, the period end itself (a lower bound), then the file's own date."""
    name = Path(f.rel).stem
    period, kind = None, "other"
    for text in (name, f.title or "", f.head[:HEADER_CHARS]):
        period, kind = infer_period(text)
        if period:
            break
    stated = date_in_name(name) or infer_published(f.head[:400])
    if period is None:
        period, kind = period_without_year(f"{name} {f.title or ''}", stated or f.created)
    f.period_end = period
    f.kind = infer_kind(f, kind)
    if stated is not None and stated == period:
        stated = None  # 'as of June 30' is the period, not the day the letter came out
    if plausible(stated, period):
        f.published_on, f.published_basis = stated, "stated"
    elif plausible(f.created, period):
        f.published_on, f.published_basis = f.created, "inferred"
    elif period is not None:
        f.published_on, f.published_basis = period, "inferred"
    else:
        f.published_on = first_seen
        f.published_basis = "first_seen"


def source_for(cfg: Config, f: InboxFile) -> str | None:
    """The letters.source a file belongs to. Shared by the manager: ``<manager>-shared``, which carries the
    manager's permission. From a public website: the manager's own tier-1 source (manual preferred, as a
    person collected it). None when config has no such source yet."""
    if not f.manager:
        return None
    own = [s for s in cfg.sources if s.manager == f.manager and s.tier == 1]
    if f.route == "shared":
        return next((s.slug for s in own if s.slug == f"{f.manager}-shared"), None)
    own = [s for s in own if not s.slug.endswith("-shared")]
    own.sort(key=lambda s: (s.mode != "manual", s.slug))
    return own[0].slug if own else None


def scan(cfg: Config, root: Path | None = None) -> list[InboxFile]:
    """Every PDF in the inbox, identified as far as the evidence allows. Reads nothing outside ``root``."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # malformed-but-readable PDFs are common; not news
    root = root or inbox_dir()
    out: list[InboxFile] = []
    for route_dir, route in ROUTES.items():
        base = root / route_dir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            if any(p.lower() in SKIP_DIRS for p in path.relative_to(base).parts[:-1]):
                continue
            body = path.read_bytes()
            f = InboxFile(
                path, route, path.relative_to(base).as_posix(), hashlib.sha256(body).hexdigest(), len(body)
            )
            try:
                read_pdf(f, body)
            except Exception as e:  # noqa: BLE001 - a malformed PDF is reported, never fatal
                f.error = f"unreadable: {type(e).__name__}: {str(e)[:200]}"
            identify(f, cfg.managers)
            date_and_kind(f, datetime.fromtimestamp(path.stat().st_mtime).date())
            out.append(f)
    return out
