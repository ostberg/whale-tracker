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
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
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
        x
        for x in (Path(f.rel).stem.replace("_", " ").replace("-", " "), f.title or "", f.author or "", f.head)
        if x
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
_YEAR = r"(20[0-4]\d)"


def _qend(q: int, year: int) -> date:
    month, day = _QUARTER_END[q]
    return date(year, month, day)


def infer_period(text: str) -> tuple[date | None, str]:
    """(period end, kind) from phrases such as 'Q3 2026', '3Q26', 'second quarter 2026', 'H1 2026',
    'year-end 2025' or 'annual letter 2025'."""
    t = text.lower()
    patterns = [
        (rf"\bq([1-4])[\s'-]*{_YEAR}\b", lambda m: _qend(int(m[1]), int(m[2])), "quarterly_letter"),
        (rf"\b{_YEAR}[\s-]*q([1-4])\b", lambda m: _qend(int(m[2]), int(m[1])), "quarterly_letter"),
        (r"\b([1-4])q[\s'-]*(\d{2})\b", lambda m: _qend(int(m[1]), 2000 + int(m[2])), "quarterly_letter"),
        (
            rf"\b(first|second|third|fourth|1st|2nd|3rd|4th) quarter(?: of)?,? {_YEAR}\b",
            lambda m: _qend(_ORDINAL[m[1]], int(m[2])),
            "quarterly_letter",
        ),
        (
            rf"\b(?:h1|first half|half[- ]year|semi[- ]annual|interim)(?: of)?,? {_YEAR}\b",
            lambda m: date(int(m[1]), 6, 30),
            "quarterly_letter",
        ),
        (rf"\b(?:h2|second half)(?: of)?,? {_YEAR}\b", lambda m: date(int(m[1]), 12, 31), "quarterly_letter"),
        (
            rf"\b(?:year[- ]end|annual(?: letter| report)?|full[- ]year)(?: of)?,? {_YEAR}\b",
            lambda m: date(int(m[1]), 12, 31),
            "annual_letter",
        ),
        (rf"\b{_YEAR} (?:year[- ]end|annual)\b", lambda m: date(int(m[1]), 12, 31), "annual_letter"),
    ]
    for pattern, to_date, kind in patterns:
        m = re.search(pattern, t)
        if m:
            try:
                return to_date(m), kind
            except ValueError:
                continue
    return None, "other"


def infer_published(text: str) -> date | None:
    """The first full date written out on the page, e.g. 'October 15, 2026' or '15 October 2026'."""
    names = "|".join(_MONTHS)
    for m in re.finditer(
        rf"\b({names})\s+(\d{{1,2}}),?\s+{_YEAR}\b|\b(\d{{1,2}})\s+({names}),?\s+{_YEAR}\b", text, re.I
    ):
        month, day, year = (m[1], m[2], m[3]) if m[1] else (m[5], m[4], m[6])
        try:
            return date(int(year), _MONTHS[month.lower()], int(day))
        except ValueError:
            continue
    return None


def infer_kind(f: InboxFile, period_kind: str) -> str:
    name = f"{f.rel} {f.title or ''}".lower()
    if re.search(r"presentation|deck|slides", name):
        return "presentation"
    if re.search(r"\bmemo\b", name):
        return "memo"
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
            text = " ".join(
                x for x in (Path(f.rel).stem.replace("_", " "), f.title or "", f.head[:HEADER_CHARS]) if x
            )
            f.period_end, period_kind = infer_period(text)
            f.kind = infer_kind(f, period_kind)
            stated = infer_published(f.head[:HEADER_CHARS])
            if stated:
                f.published_on, f.published_basis = stated, "stated"
            elif f.created:
                f.published_on, f.published_basis = f.created, "inferred"
            else:
                f.published_on = datetime.fromtimestamp(path.stat().st_mtime).date()
            out.append(f)
    return out
