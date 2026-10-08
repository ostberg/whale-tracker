# Handoff journal

Dated entries, newest first: what changed, what is verified, what is next.

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
