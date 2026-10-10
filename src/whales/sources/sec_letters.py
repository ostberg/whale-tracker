"""Which documents in which SEC filings count as letters (tier 2, W-029, W-031).

A source's ``edgar`` rule in ``config/letter_sources.toml`` names a preset and the filer CIKs to watch. A
preset maps each form to the document types to take: ``EX-99*`` is a prefix match, anything else exact.
Boilerplate exhibits (joint filing agreements, powers of attorney) are skipped by their description.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .edgar import EdgarClient, Filing, IndexDocument

ACTIVIST_13D = ["EX-99*"]
PRESETS: dict[str, dict] = {
    # Activists: letters to boards and shareholders, filed as 13D exhibits or as proxy materials (DFAN14A).
    "activist": {
        "forms": {
            "SC 13D": ACTIVIST_13D,
            "SC 13D/A": ACTIVIST_13D,
            "SCHEDULE 13D": ACTIVIST_13D,
            "SCHEDULE 13D/A": ACTIVIST_13D,
            "DFAN14A": ["DFAN14A", "EX-99*"],
        },
        "items": None,
    },
    # A registered fund's shareholder report, which carries the manager's letter.
    "ncsr": {"forms": {"N-CSR": ["N-CSR"], "N-CSRS": ["N-CSRS"]}, "items": None},
    # A listed company's earnings release (8-K item 2.02, exhibit 99.1).
    "earnings_8k": {"forms": {"8-K": ["EX-99.1"]}, "items": {"2.02"}},
}

# Exhibits that are legal or trading boilerplate, never letters. A deny-list, because letters often carry
# only a generic description ("EX-99.1"); what slips through is classified later, from the text.
SKIP_DESCRIPTIONS = re.compile(
    r"joint filing|powers? of attorney|trading data|\bschedul|\btransactions?\b|agreement|confirmation|"
    r"holders? r(igh)?ts|term sheet|commitment|certificat|\bcert\b|indenture|warrant|promissory|"
    r"subscription|registration rights|merger|\bform of\b|consent|lock-?up|indemnif|nominee",
    re.I,
)
SKIP_TYPES = {"GRAPHIC", "XML", "ZIP", "EX-101.INS", "JSON"}


@dataclass(frozen=True)
class Candidate:
    """One document to collect."""

    filing: Filing
    document: IndexDocument
    subject: str | None
    filed_by: str | None

    @property
    def title(self) -> str:
        about = f" on {self.subject}" if self.subject else ""
        label = self.document.description or self.document.type
        return f"{self.filing.form}{about}: {label} ({self.document.name})"


def type_matches(doc_type: str, patterns: list[str]) -> bool:
    return any(doc_type.startswith(p[:-1]) if p.endswith("*") else doc_type == p for p in patterns)


def wanted_forms(preset: str) -> set[str]:
    return set(PRESETS[preset]["forms"])


def filing_wanted(preset: str, filing: Filing) -> bool:
    rule = PRESETS[preset]
    if filing.form not in rule["forms"]:
        return False
    return rule["items"] is None or bool(rule["items"] & set(filing.items))


def documents_wanted(preset: str, filing: Filing, docs: tuple[IndexDocument, ...]) -> list[IndexDocument]:
    patterns = PRESETS[preset]["forms"][filing.form]
    out = []
    for d in docs:
        if d.type in SKIP_TYPES or d.name.endswith((".txt", ".jpg", ".gif", ".png")):
            continue
        # some filers put the label in the type column, so both are checked
        if SKIP_DESCRIPTIONS.search(d.description) or SKIP_DESCRIPTIONS.search(d.type):
            continue
        if type_matches(d.type, patterns):
            out.append(d)
    return out


def candidates(client: EdgarClient, preset: str, ciks: list[int], since: date) -> list[Candidate]:
    """Every wanted document filed by any of ``ciks`` on or after ``since``. One index fetch per filing."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for cik in ciks:
        for filing in client.filings(cik, since):
            if filing.accession in seen or not filing_wanted(preset, filing):
                continue
            seen.add(filing.accession)
            index = client.filing_index(cik, filing.accession)
            for doc in documents_wanted(preset, filing, index.documents):
                out.append(
                    Candidate(
                        filing,
                        doc,
                        index.subject[0] if index.subject else None,
                        index.filed_by[0] if index.filed_by else None,
                    )
                )
    return out


def pdf_flags(body: bytes) -> tuple[bool, int | None, bool | None]:
    """(encrypted, permissions value, text extraction allowed) from a PDF's standard security handler, read
    without decrypting anything. Bit 5 of the permissions value allows copying and extracting text."""
    m = re.search(rb"/Filter\s*/Standard", body)
    if not m:
        return False, None, True
    p = re.search(rb"/P\s+(-?\d+)", body[max(0, m.start() - 400) : m.end() + 400])
    if not p:
        return True, None, None
    value = int(p.group(1))
    return True, value, bool((value & 0xFFFFFFFF) >> 4 & 1)
