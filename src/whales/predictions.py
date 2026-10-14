"""Predictions as structured, linked claims (W-048): the contract between the extraction model and the
database, and the code that stores what the model returns.

The model receives a letter's text and returns JSON in the shape of ``CONTRACT``. ``parse`` checks every
field against the controlled vocabularies, the dates against the letter's publication date, and the links
between claims; it reports every problem at once and nothing is stored unless all of it is valid. ``store``
writes one run's claims and links. Design and worked examples: docs/PREDICTIONS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

PROMPT_VERSION = "predictions-v1"

ROLES = ("asserted", "premise")
METRICS = (
    "price",
    "valuation_multiple",
    "revenue",
    "earnings",
    "margin",
    "capex",
    "capital_return",
    "volume",
    "interest_rate",
    "credit_spread",
    "inflation",
    "gdp",
    "employment",
    "fx",
    "commodity_price",
    "event",
    "other",
)
COMPARATORS = ("up", "down", "above", "below", "at_least", "at_most", "happens", "does_not_happen")
NEEDS_THRESHOLD = ("above", "below", "at_least", "at_most")
TIMINGS = ("any_time", "at_end")
LINK_KINDS = ("premise_of", "causes")
BASES = ("data", "reasoning", "assertion")  # W-050: what the writer shows for the claim
QUOTE_MAX = 400
SUBJECT_MAX = 200
BASIS_NOTE_MAX = 300

# How a claim about each metric is checked when its window closes. `data`: a public series (FRED and the
# like); `price`: the price source (phase 6); `filing`: the company's own reports; `model`: a model reads
# later evidence and proposes an outcome, which a person confirms. None of this is built yet.
CHECK_METHOD = {
    "price": "price",
    "valuation_multiple": "model",
    "revenue": "filing",
    "earnings": "filing",
    "margin": "filing",
    "capex": "filing",
    "capital_return": "filing",
    "volume": "model",
    "interest_rate": "data",
    "credit_spread": "data",
    "inflation": "data",
    "gdp": "data",
    "employment": "data",
    "fx": "data",
    "commodity_price": "data",
    "event": "model",
    "other": "model",
}

# The JSON the model must return. Every claim is one testable thing; a sentence with two tests becomes two
# claims. `k` numbers the claims within the document; `premises` and `caused_by` refer to other claims by `k`.
CONTRACT = """{
  "predictions": [
    {
      "k": 1,
      "role": "asserted | premise",
      "subject": "short canonical name of what is measured, e.g. 'Brent crude', 'MSFT forward P/E'",
      "metric": "price | valuation_multiple | revenue | earnings | margin | capex | capital_return | volume
                 | interest_rate | credit_spread | inflation | gdp | employment | fx | commodity_price
                 | event | other",
      "ticker": "listed ticker the claim is about, or null",
      "topic": "topic slug from the given list, or null",
      "comparator": "up | down | above | below | at_least | at_most | happens | does_not_happen",
      "threshold": "number, required for above/below/at_least/at_most, else null",
      "unit": "unit of the threshold, e.g. 'USD/bbl', 'x', '% y/y', 'pp', or null",
      "relative_to": "benchmark when the call is relative, e.g. 'S&P 500', else null",
      "window_from": "YYYY-MM-DD or null: the call applies from this date",
      "window_to": "YYYY-MM-DD or null: the deadline; null when the writer gives none (never guess)",
      "timing": "any_time (met if true at any point in the window) | at_end (judged at window_to)",
      "horizon_text": "the writer's own words for the timing, or null",
      "confidence_wording": "the writer's own words, e.g. 'will', 'we expect', 'could', or null",
      "basis": "data (cites specific numbers or observable facts) | reasoning (argues a mechanism)
                | assertion (stated as a view, nothing shown)",
      "basis_note": "one line on what the writer shows, e.g. 'cites Q2 capex and the FY guide', or null",
      "claim": "one plain sentence restating the call",
      "quote": "the writer's exact words, at most 400 characters",
      "page": "page number or null",
      "premises": [2],
      "caused_by": [3]
    }
  ]
}"""


class ContractError(ValueError):
    """The model's output does not meet the contract. ``problems`` lists everything wrong."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Claim:
    k: int
    role: str
    subject: str
    metric: str
    ticker: str | None
    topic: str | None
    comparator: str
    threshold: Decimal | None
    unit: str | None
    relative_to: str | None
    window_from: date | None
    window_to: date | None
    timing: str
    horizon_text: str | None
    confidence_wording: str | None
    basis: str
    basis_note: str | None
    claim: str
    quote: str
    page: int | None


@dataclass(frozen=True)
class Link:
    from_k: int
    to_k: int
    kind: str


@dataclass
class Extraction:
    claims: list[Claim] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # soft problems: something was dropped, nothing refused

    def claim(self, k: int) -> Claim:
        return next(c for c in self.claims if c.k == k)


# --- parsing ------------------------------------------------------------------------------------------


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _text(item: dict, key: str, problems: list[str], where: str, *, required: bool, limit: int) -> str | None:
    v = item.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            problems.append(f"{where}: {key} is required")
        return None
    if not isinstance(v, str):
        problems.append(f"{where}: {key} must be text")
        return None
    v = " ".join(v.split())
    if len(v) > limit:
        problems.append(f"{where}: {key} is longer than {limit} characters")
    return v


def _date(item: dict, key: str, problems: list[str], where: str) -> date | None:
    v = item.get(key)
    if v is None:
        return None
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        problems.append(f"{where}: {key} must be YYYY-MM-DD, got {v!r}")
        return None


def _code(item: dict, key: str, allowed: tuple[str, ...], problems: list[str], where: str) -> str | None:
    v = item.get(key)
    if v not in allowed:
        problems.append(f"{where}: {key} must be one of {allowed}, got {v!r}")
        return None
    return v


def _refs(item: dict, key: str, problems: list[str], where: str) -> list[int]:
    v = item.get(key) or []
    if not isinstance(v, list) or not all(_is_int(x) for x in v):
        problems.append(f"{where}: {key} must be a list of claim numbers")
        return []
    return v


def parse(payload: Any, published_on: date, topics: set[str] | frozenset[str] = frozenset()) -> Extraction:
    """Check the model's JSON against the contract. ``topics`` are the slugs the model was allowed to use; an
    unknown one is dropped to None and noted. Anything else wrong raises ContractError with every problem."""
    items = payload.get("predictions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ContractError(["payload must be an object with a 'predictions' list"])
    problems: list[str] = []
    out = Extraction()
    seen: set[int] = set()
    pending_links: list[tuple[int, int, str, str]] = []
    for i, item in enumerate(items):
        where = f"predictions[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object")
            continue
        k = item.get("k")
        if not _is_int(k) or k < 1:
            problems.append(f"{where}: k must be a positive integer")
            continue
        if k in seen:
            problems.append(f"{where}: k {k} is used twice")
            continue
        seen.add(k)
        where = f"claim {k}"
        role = _code(item, "role", ROLES, problems, where)
        metric = _code(item, "metric", METRICS, problems, where)
        comparator = _code(item, "comparator", COMPARATORS, problems, where)
        timing = _code(item, "timing", TIMINGS, problems, where)
        basis = _code(item, "basis", BASES, problems, where)
        basis_note = _text(item, "basis_note", problems, where, required=False, limit=BASIS_NOTE_MAX)
        subject = _text(item, "subject", problems, where, required=True, limit=SUBJECT_MAX)
        claim = _text(item, "claim", problems, where, required=True, limit=1000)
        quote = _text(item, "quote", problems, where, required=True, limit=QUOTE_MAX)
        ticker = _text(item, "ticker", problems, where, required=False, limit=20)
        topic = _text(item, "topic", problems, where, required=False, limit=100)
        unit = _text(item, "unit", problems, where, required=False, limit=40)
        relative_to = _text(item, "relative_to", problems, where, required=False, limit=100)
        horizon_text = _text(item, "horizon_text", problems, where, required=False, limit=200)
        confidence = _text(item, "confidence_wording", problems, where, required=False, limit=100)
        window_from = _date(item, "window_from", problems, where)
        window_to = _date(item, "window_to", problems, where)
        threshold: Decimal | None = None
        raw = item.get("threshold")
        if raw is not None:
            try:
                threshold = Decimal(str(raw))
            except InvalidOperation:
                problems.append(f"{where}: threshold must be a number, got {raw!r}")
        if comparator is not None and (comparator in NEEDS_THRESHOLD) != (threshold is not None):
            problems.append(f"{where}: threshold is required for {NEEDS_THRESHOLD} and not allowed otherwise")
        if window_from and window_to and window_to < window_from:
            problems.append(f"{where}: window_to is before window_from")
        if window_to and window_to < published_on:
            problems.append(f"{where}: window_to {window_to} is before the letter's date {published_on}")
        if timing == "at_end" and window_to is None:
            problems.append(f"{where}: timing at_end needs a window_to")
        page = item.get("page")
        if page is not None and (not _is_int(page) or page < 1):
            problems.append(f"{where}: page must be a positive integer or null")
            page = None
        if topic is not None and topic not in topics:
            out.notes.append(f"{where}: topic {topic!r} is not in the list; dropped")
            topic = None
        for ref in _refs(item, "premises", problems, where):
            pending_links.append((ref, k, "premise_of", where))
        for ref in _refs(item, "caused_by", problems, where):
            pending_links.append((ref, k, "causes", where))
        if problems:
            continue
        out.claims.append(
            Claim(
                k=k,
                role=role,
                subject=subject,
                metric=metric,
                ticker=ticker.upper() if ticker else None,
                topic=topic,
                comparator=comparator,
                threshold=threshold,
                unit=unit,
                relative_to=relative_to,
                window_from=window_from,
                window_to=window_to,
                timing=timing,
                horizon_text=horizon_text,
                confidence_wording=confidence,
                basis=basis,
                basis_note=basis_note,
                claim=claim,
                quote=quote,
                page=page,
            )
        )
    if problems:
        raise ContractError(problems)
    by_k = {c.k: c for c in out.claims}
    for from_k, to_k, kind, where in pending_links:
        if from_k not in by_k:
            problems.append(f"{where}: refers to claim {from_k}, which does not exist")
            continue
        if from_k == to_k:
            problems.append(f"{where}: refers to itself")
            continue
        want = "premise" if kind == "premise_of" else "asserted"
        if by_k[from_k].role != want:
            problems.append(f"{where}: claim {from_k} is {by_k[from_k].role}, but a {kind} link needs {want}")
            continue
        link = Link(from_k, to_k, kind)
        if link not in out.links:
            out.links.append(link)
    for c in out.claims:
        if c.role == "premise" and not any(link.from_k == c.k for link in out.links):
            problems.append(f"claim {c.k}: a premise must be the premise of some other claim")
    problems.extend(_cycles(out.links))
    if problems:
        raise ContractError(problems)
    return out


def _cycles(links: list[Link]) -> list[str]:
    """A claim cannot depend on itself through any chain of links."""
    following: dict[int, list[int]] = {}
    for link in links:
        following.setdefault(link.from_k, []).append(link.to_k)
    problems = []
    for start in sorted(following):
        stack, seen = list(following[start]), set()
        while stack:
            node = stack.pop()
            if node == start:
                problems.append(f"claim {start}: depends on itself through the links")
                break
            if node not in seen:
                seen.add(node)
                stack.extend(following.get(node, []))
    return problems


# --- storing ------------------------------------------------------------------------------------------

INSERT_CLAIM = (
    "INSERT INTO letters.prediction (extraction_run_id, ordinal, role, subject, metric, security_id, "
    "topic_id, comparator, threshold, unit, relative_to, window_from, window_to, timing, horizon_text, "
    "confidence_wording, basis, basis_note, claim, quote, page) VALUES (%s, %s, %s, %s, %s, "
    "(SELECT id FROM core.security WHERE ticker = %s ORDER BY id LIMIT 1), "
    "(SELECT id FROM core.topic WHERE slug = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "RETURNING id, security_id"
)
INSERT_LINK = (
    "INSERT INTO letters.prediction_link (extraction_run_id, from_id, from_role, to_id, kind) "
    "VALUES (%s, %s, %s, %s, %s)"
)
SCORED_SQL = (
    "SELECT count(*) FROM letters.prediction_score s JOIN letters.prediction p ON p.id = s.prediction_id "
    "JOIN letters.extraction_run r ON r.id = p.extraction_run_id WHERE r.document_id = %s"
)


def claim_params(run_id: int, c: Claim) -> tuple:
    """The parameters of INSERT_CLAIM, in column order."""
    return (
        run_id,
        c.k,
        c.role,
        c.subject,
        c.metric,
        c.ticker,
        c.topic,
        c.comparator,
        c.threshold,
        c.unit,
        c.relative_to,
        c.window_from,
        c.window_to,
        c.timing,
        c.horizon_text,
        c.confidence_wording,
        c.basis,
        c.basis_note,
        c.claim,
        c.quote,
        c.page,
    )


def refuse_if_scored(conn, document_id: int) -> None:
    """A document whose predictions carry a score is never re-extracted (W-039), so scores never point at
    superseded rows."""
    n = conn.execute(SCORED_SQL, (document_id,)).fetchone()[0]
    if n:
        raise RuntimeError(f"document {document_id} has {n} scored prediction(s); re-extraction refused")


def store(conn, run_id: int, extraction: Extraction) -> dict[int, int]:
    """Write one run's claims and links inside the caller's transaction. Returns the prediction id of each
    ``k``. A ticker with no row in core.security leaves security_id empty and is noted; never a guessed
    match."""
    ids: dict[int, int] = {}
    for c in extraction.claims:
        row_id, security_id = conn.execute(INSERT_CLAIM, claim_params(run_id, c)).fetchone()
        ids[c.k] = row_id
        if c.ticker and security_id is None:
            extraction.notes.append(f"claim {c.k}: ticker {c.ticker} is not in core.security; left unlinked")
    for link in extraction.links:
        from_role = extraction.claim(link.from_k).role
        conn.execute(INSERT_LINK, (run_id, ids[link.from_k], from_role, ids[link.to_k], link.kind))
    return ids
