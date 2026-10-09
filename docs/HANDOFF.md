# Handoff journal

Dated entries, newest first: what changed, what is verified, what is next.

## 2026-10-09: schema designed, reviewed and applied (migration 0001); phase 1 gate met

**Owner direction.**
- "Is it worth making sure the schema is set right?" Yes: the agent drafted `docs/SCHEMA.md` and an
  independent agent reviewed it.
- "Go ahead with migration 0001 after the review."

**The review's main findings, all fixed.**
- On PG16+, an admin who creates a role gets only ADMIN on it. Fix: an explicit `GRANT ... WITH SET TRUE`,
  in a separate `bootstrap-roles` command, because roles are server-wide.
- The ingest grant was too broad: it could have flipped permission columns and forged approvals. Ingest now
  gets reads, inserts and named working columns only, and permission snapshots are set by a trigger.
- Reviewer rows could have been signed as someone else. Decisions are now insert-only tables, and the
  database stamps `reviewed_by`.

**What changed.**
- `src/whales/db/migrate.py`: numbered SQL, one transaction each, run as `whales_owner`, with checksums,
  refusal of edited files, and a rollback if anything is mis-owned.
- `src/whales/db/migrations/0001_foundation.sql`: schemas `meta`, `raw`, `core`, `letters` and `api`, with
  22 tables. Applied to `whales_dev`.
- New commands: `whales db bootstrap-roles` and `whales db migrate`.
- Roles `whales_owner`, `whales_ingest` and `whales_reviewer` were created on the server. The admin holds
  owner and ingest with SET only, and reviewer with inherit.
- TEMPORARY on `whales_dev` was revoked from PUBLIC.
- Tests: 26 unit tests, including static guards on the SQL, and 17 live tests (`pytest -m live`).
- `docs/SCHEMA.md` was rewritten to match the build. W-039 is final; W-038 is amended (kind is a column).

**Verified (live, 2026-10-09).**
- Every object is owned by `whales_owner`; PUBLIC cannot connect; no role can delete.
- Ingest cannot see `meta` or change permissions.
- A forged copy permission is overwritten, and an extraction run on a forbidden copy is refused.
- All 22 tables were empty after the rolled-back tests.
- The temporary firewall rule `whales-dev-temp-20261009` was removed.

**Next.**
1. The GitHub remote (owner).
2. `config/` files and `whales config sync`: managers, filers, tags, topics and sources from the registers.
3. The first auto source collector (Oaktree memos or Praetorian), pending the compliance ruling.
4. The model seam and the Foundry endpoint.

## 2026-10-08 (second session, end): database set up and hardened; package scaffolded

**Owner decisions.**
- W-004: share `pg-tocqv-context` under four hardening conditions, rather than paying for a server.
- Ratings simplified to two judged and two counted signals (W-036).
- Tag list: crossover and Kind accepted, real assets rejected (W-038).
- Approved: create `whales_dev`, edit the Tamale role script, scaffold the package.

**What changed.**
- `whales_dev` created on `pg-tocqv-context` (UTF8).
- Tamale's `scripts/context_db_roles.py` now revokes CONNECT on `context` from PUBLIC (Tamale commit
  `1006a46`, local only, not pushed; another session has uncommitted work in that tree).
- The same revoke applied live on `context` and `whales_dev`.
- Package scaffold:
  - `pyproject.toml`;
  - `scripts/lock_deps.ps1`;
  - `requirements-runtime.lock` (psycopg[binary] 3.3.6, tzdata) and `requirements-dev.lock`, both
    hash-pinned and first generated with the Tamale venv's pinned pip-tools;
  - `src/whales/db/connect.py`: Entra tokens from the container identity endpoint or `az`, no Azure SDK;
  - `src/whales/db/admin.py` and `src/whales/cli.py`: the `whales db connect-paths` and
    `revoke-public-connect` commands;
  - 12 unit tests; `.env.example`.

**Verified.**
- Before the revoke, PUBLIC had CONNECT on `context`, and the Research Assistant and weekly-job identities
  could connect to `whales_dev`.
- After it, `context` is reachable only by its owner (Peter), `azuresu`, and `context_writer` members
  (`id-research-assistant`, `id-weekly-job`); `whales_dev` only by Peter and `azuresu`. Azure's
  `replication` role lost database CONNECT on both; physical replication does not need it and there is no
  replica or HA.
- Ruff check and format pass; pytest 12 passed.
- The temporary firewall rule was removed. Only the "Azure services" rule remains.
- pgvector is not allow-listed on the server (`azure.extensions` empty). That is needed in phase 2.

**Not done.**
- The GitHub remote: the owner signs in or creates the repository.
- Pushing the Tamale commit, which is the owner's call or the Tamale session's.
- The first migration (schemas `raw`, `core`, `letters`, `api` and the migrations table).
- The ingest identity and its role.

**Next.**
1. Add the remote and push.
2. First migration against `whales_dev`; that meets the phase 1 gate "migrations run against the Azure
   server".
3. Owner: the compliance brief, outreach, the Teams channel and the "?" tags.

## 2026-10-08 (second session, later): letters become the product

**What changed.**
- The owner said the real value is in shareholder letters; 13F tracking is a commodity (WhaleWisdom), useful
  at most as a verifier. Recorded as W-027 (supersedes W-006), with W-028 to W-035.
- Phases re-planned in STATUS.md: the letters pilot is now phase 2 and the thin 13F layer phase 3.
- New register `docs/LETTER_SOURCES.md`. It covers the owner's example links, the 30 watchlist managers,
  activist letters on EDGAR, three aggregators and 21 further topic writers.

**Owner direction this session.**
- Letters first; WhaleWisdom at least as a verifier.
- Pull 13G too (W-031).
- If a source can't be scraped, send an automated reminder to check (W-033).
- Reminders go to a Teams digest, acted on by the owner for now and later by an intern or junior analyst
  (W-034).
- The owner sent example sources: Greenlight and Stone Sentinel on Hedge Fund Alpha, Buy Side Digest,
  Fundsmith, Oaktree, Pershing Square Holdings, a q4cdn shareholder letter, PM Capital, Praetorian and
  Laughing Water.

**Verified (pages, terms and robots.txt opened 2026-10-08).**
- The Greenlight PDF on Hedge Fund Alpha forbids text extraction (permissions value -1052).
- Fundsmith's legal notice forbids automated text analysis without written consent (re-read directly).
- Buy Side Digest's terms forbid bots and any AI use, but it sells an institutional S3 feed.
- Hedge Fund Alpha's terms ban robots and copying, and it sells data licensing.
- Regal Partners (PM Capital) requires consent to store its content.
- Praetorian's letters are open, with no terms page.
- Teams Office 365 connectors were retired in May 2026; Workflows webhooks replace them.

**Main finding.** Website terms, not robots.txt, bind us, and they come in three kinds (W-035). Access
restrictions are solved by manual collection with reminders. Storage restrictions are solved by keeping
extracts only. Use restrictions (no automated text analysis or AI) are solved only by consent or a licence.
Most of the owner's priority managers have an auto route (Oaktree, Longleaf, Elliott, Starboard, Pershing
Square through PSUS's N-CSRS on EDGAR, JANA through 13D exhibits). Third Point is manual. Fundsmith needs
consent. Greenlight's partner letters come only through an aggregator licence.

**Not verified.**
- The agents' paraphrases of most terms pages; re-read each before approving a source.
- The q4cdn issuer.
- What "Value Investor" means.
- The 13D/G deadlines, taken from law-firm summaries rather than the rule text.

**Next.**
1. Owner:
   - take the source-tier question to the CCO (the agent can draft the brief);
   - decide on outreach to Buy Side Digest (trial), Hedge Fund Alpha (licence) and Fundsmith (consent);
   - name the Teams channel and the flow owner;
   - confirm the intake container;
   - create the GitHub repository.
2. Agent: push to the remote once it exists, then scaffold the package (W-022).

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
