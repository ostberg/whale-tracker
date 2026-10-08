# Handoff journal

Dated entries, newest first: what changed, what is verified, what is next.

## 2026-10-08 (second session): git, Tamale read, manager survey

**What changed.**
- Local git repository created on `main` and the planning docs committed. No remote yet: `gh` is not installed,
  so the owner creates the empty private `whale-tracker` repository on github.com.
- The Tamale repo's `OPS_AUTOMATION_PLAN.md`, `CONTEXT_LAYER_PLAN.md`, `DECISIONS.md`, deploy scripts and CI
  were read in full (by a sub-agent; findings carry file references). Results are in AGENTS.md under "From the
  Tamale repo" and in new decisions W-020 to W-023.
- All candidate managers were surveyed on EDGAR, giving `docs/MANAGER_SURVEY.md` and new decisions W-024 to
  W-026. The data model gained `core.filer`.

**Owner answers this session.**
- Git: local repository plus a private GitHub remote.
- SEC contact: "possibly `research@tocqueville.com`". The owner asked whether access is needed to prove it is
  real. Answer: SEC verifies nothing, but the mailbox must exist and be read.
- W-004 deferred until the Tamale read; the recommendation is now its own server.
- Managers: verify all, plus Whitebox (Andy Redleaf), Oaktree and Longleaf. First-pass priorities: Greenlight,
  Third Point, Oaktree, Pershing Square, Fundsmith, Longleaf, Elliott, Starboard, Jana, "Value Investor".

**Verified (live EDGAR requests, 2026-10-08).**
- Every candidate's current 13F filer CIK, its latest cover-page totals and its successions.
- Baupost and Duquesne still report values in thousands.
- The two Situational Awareness entities filed identical 2026 Q1 reports.
- The EDGAR full-text and entity search endpoints work with a declared User-Agent.

**Not verified.**
- Pre-2024 filer history for most managers (see the survey's method).
- Whether the table-scoped ledger role in W-021 works.
- Whether `research@tocqueville.com` exists.

**Tamale-side gap noticed, not acted on.** Tamale's `scripts/context_db_roles.py` grants CONNECT on database
`context` to `context_writer` but never revokes it from PUBLIC. By Postgres default, any login role on
`pg-tocqv-context` can therefore connect to `context`, unless someone revoked it by hand (the live server was
not checked). This belongs to the Tamale repo; it matters whatever W-004 decides.

**Next.**
1. Owner: create the empty private GitHub repository; decide W-004, "Value Investor", W-026 and the topic
   source of truth (W-018); confirm the SEC mailbox.
2. Agent: add `origin` and push; scaffold `pyproject.toml`, the pip-tools locks, Ruff, pytest and the package
   skeleton (W-022).
3. First migration (`raw.filing`, `core.manager`, `core.filer`, `core.security`, `core.holding`) once the
   database exists.
4. `sources/edgar.py` and `parse/form13f.py` against saved real filings. Test fixtures should include:
   - one filing from before 2023;
   - one amendment;
   - a post-2023 filing in thousands (Baupost, accession `0001061768-26-000010`);
   - the duplicate Situational Awareness pair (`0002045724-26-000008` and `0002038540-26-000004`, both filed 2026-05-18);
   - a filing with put lines.

## 2026-10-08: planning session; project folder created

**What happened.** The owner asked for a long-running Azure process that pulls shareholder letters and 13F
reports from investment "whales", summarizes them and correlates companies held by several of them, with a
long-lived database. Over the session the scope grew to include forward performance tracking per event (the
owner's idea), use as a further source for the Research Assistant (the owner's idea), alerts, and summaries
stored in Tamale. A build plan was written and this folder was created with `AGENTS.md`, `CLAUDE.md`,
`docs/STATUS.md`, `docs/DECISIONS.md` and this journal. No code exists.

**Companion document.** "Whale Tracker: Build Plan", a doc in the owner's Claude account
(https://claude.ai/code/artifact/24ab302f-15cb-4ccb-8370-f7e95c739285), is the readable version of the plan
with an architecture diagram and cited sources. It is private to the owner. This repo is authoritative: where
the two differ, the repo wins.

**Verified on 2026-10-08** (pages opened): SEC EDGAR API and fair-access limits, the Form 13F FAQ (deadline,
long-only, dollar values from 2023-01-03, summary-page totals), the SEC 13F bulk data sets, OpenFIGI mapping and
limits, Azure Container Apps scheduled jobs, Entra sign-in for Azure Postgres. See AGENTS.md "Domain facts".

**Not verified.** The candidate manager list is from memory. Nothing was tested against EDGAR. The Tamale repo
was read only in part (`AGENTS.md`, `docs/DATA_STORE.md`, the top of `docs/DATA_SOURCES.md` and
`docs/STATUS.md`); its `docs/DECISIONS.md`, `docs/OPS_AUTOMATION_PLAN.md` and `docs/CONTEXT_LAYER_PLAN.md` were
not read, so the fleet and context-layer details here are thin.

**Legal note recorded for the owner (not legal advice).** Being an LP does not make a letter free to use: the
fund's confidentiality terms usually limit use to monitoring that investment. Feeding LP letters into an
idea-generation system, or trading on them, raises contract, fiduciary and misappropriation questions. Hence
W-014.

**Added later the same day: topic analysis (W-017 to W-019).** The owner asked for a topic analyzer covering
interest rates, US Treasuries, European macro, housing, AI, edge compute, gold, inflation, lumber, oil and
similar. Design: a controlled topic list; a holdings lens (13F positions mapped to topic baskets, available
from phase 3) and a letters lens (topic mentions with stance, quote and link, phase 6). Limits recorded in
AGENTS.md: 13F does not show bonds, futures or physical commodities, so macro topics are visible mainly in
what managers write. The Tamale context layer plans its own topic tags; the two should share one vocabulary.

**Next.**

1. Owner answers the blocking decisions in STATUS.md.
2. From a Windows terminal or Claude Code on the machine: `git init`, first commit, private remote.
3. Read the Tamale repo's `docs/OPS_AUTOMATION_PLAN.md` (fleet, identities, deploy scripts) and
   `docs/CONTEXT_LAYER_PLAN.md` before designing the Azure job and the database roles.
4. Scaffold `pyproject.toml`, Ruff, pytest and the package skeleton.
5. First migration (`raw.filing`, `core.manager`, `core.security`, `core.holding`) against `whales_dev`.
6. Build `sources/edgar.py` and `parse/form13f.py` against saved real filings, including one filing from before
   2023 and one amendment.
