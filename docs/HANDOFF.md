# Handoff journal

Dated entries, newest first: what changed, what is verified, what is next.

## 2026-10-20: Azure cleared; deployed, migrated, synced, loaded; first jobs started

**Owner direction.** "Azure sign in looks ok." And: "Tamale tie in? Request list of topics from Tamale to
see if any matches."

**What changed.**
- Deployed (W-042): `rg-whale-tracker`, `log-whale-tracker`, registry `tocqvwhalesacr`, identities
  `id-whales-ingest` and `id-whales-admin` (AcrPull), environment `cae-whale-tracker`, image
  `whale-tracker:26d2c4d`, jobs `job-whales-collect-sec` (daily 11:00 UTC), `job-whales-collect-web`
  (Mondays 10:00 UTC) and `job-whales-admin` (manual). Two deploy fixes on the way: the az CLI refuses a
  job argument list containing `--apply`, so a job's arguments travel as one string and
  `infra/entrypoint.sh` splits them; and the Windows az CLI cannot print the image build log (console
  encoding; its Python runs isolated, so UTF-8 settings do not reach it), so the build runs with
  `--no-logs`.
- Both identities registered as Postgres logins (`db add-identity`, from the laptop with the temporary
  firewall rule).
- Migration 0002 applied to `whales_dev`; `config sync --apply` wrote 79 inserts and 46 updates (the
  W-043 activations, new managers and sources, 52 trust baselines, five Tamale topic ids); `inbox load
  --apply` recorded all 78 PDFs; `pytest -m live`: 26 passed, which verifies 0002's views, grants and the
  trust flag against the server.
- Tamale topic twins (W-018): the live Tamale list (259 Topic entities) was read through the Tamale repo's
  own client, from that repo, nothing copied here but five ids: housing, lumber, AI (umbrella), edge
  compute, gold. No Tamale topic for interest rates in general (only Rising Rates), US Treasuries,
  inflation, European macro or oil.
- First executions of both collection jobs started by hand at 16:32 UTC.

**Process note.** The agent's sandboxed shells died mid-session (every command returned exit 107 at once,
nothing ran); the rest went through the app's terminal tool in the owner's own PowerShell, from scripts in
the scratchpad. One `--open-firewall` call hit an Azure gateway timeout while another rule was being
removed; `whales db close-firewall` sweeps any leftover.

**Verified.** Deploy exit 0; migration, sync, inbox load and live tests as above. First executions:
- `collect sec` ran as `id-whales-ingest`, 329 SEC requests, 131 documents collected (Elliott 99,
  Starboard 12, Greenlight Re 7, Trian 5, Third Point 5, JANA 2, PSUS 1) and one source failed on a
  transient network error (`pershing-square-edgar`: "Cannot assign requested address"), which marked the
  run failed. Fixed in code: both clients now retry a dropped connection (EDGAR twice, websites once).
- `collect web` was still running an hour in, with 180 documents recorded (Oaktree 110, Southeastern 59,
  Elliott 9, Starboard 1, Laughing Water 20 ...). Its `fetch_attempt` rows show three problems:
  (1) about 30 older Oaktree memos (2002 to 2015) are AES-encrypted with an empty password and pypdf
  needs the `cryptography` package to open them: a dependency decision for the owner (`pypdf[crypto]`);
  (2) one Oaktree URL contains "déjà", which urllib cannot send unencoded: fixed, URLs are now
  percent-encoded; (3) `praetorian-letters` fails in the container on the site's certificate chain
  ("unable to get local issuer certificate", fine from a Windows laptop) and `pm-capital-insights`
  gets HTTP 404 for its sitemap from Azure although the laptop dry run listed 430 items: both to check,
  and a candidate for manual collection if they persist.

**Evening: the weekly digest (W-054).** The owner set the end use: chatbot for pull, proactive reports that
are "high value or short enough to warrant a quick read", above all themes several writers raise at the same
time; weekly, at most four items, the subject line says when there is nothing, and themes must be allowed six
months to emerge, so later documents are analysed against earlier ones too. Built: migration 0003 (schema
`reports`: `digest`, `digest_item`, the view `theme_mention`), `src/whales/reports/digest.py` (convergence,
disagreement, calls due, confident misses; a 26-week window by publication date recomputed every issue; the
memory so a theme returns only once grown), `whales digest`, `docs/REPORTS.md`, unit tests on constructed
rows. The SQL has no extraction output to read yet; the first real issue follows the model deployment, and
the Teams post follows the flow URL.

**Later the same day.** The owner approved `cryptography` (W-053): `pypdf[crypto]` in `pyproject.toml`,
locks regenerated with `scripts\lock_deps.ps1` (versions held), a test that an AES-256 PDF with an empty
password is read, image rebuilt. The next website run picks the Oaktree memos up.

**Next.**
1. Check Praetorian's certificate chain and PM Capital's sitemap from the container; switch either to
   manual if a site change is the cause.
2. A model deployment and the Cognitive Services OpenAI User role (W-052); then `whales model check` and
   the first `extract predictions --apply` in Azure.
3. How the inbox PDFs reach the runner in Azure (the blob upload, W-044) or on a laptop (a W-045
   extension).

## 2026-10-14 (evening): the model seam and the predictions runner; GitHub remote

**Owner direction.** "Model seam + predictions runner" chosen as the next build while Azure is blocked;
the private repository `github.com/ostberg/whale-tracker` created and its URL handed over.

**What changed.**
- `src/whales/llm.py` (W-052): `FoundryProvider`, an OpenAI-compatible chat call to the firm's in-tenant
  endpoint with an Entra token (no key), an in-code host allowlist with default deny, JSON-only replies,
  the `max_completion_tokens` quirk learned once, a token refresh on 401, retries on 429 and 5xx, the
  empty-reply retry, and usage totals. `whales model check` makes one small call.
- `src/whales/extract.py` (W-048): candidates (machine-readable copies with no successful predictions
  run), the system prompt (the rules, canonical subjects, topic slugs and the contract; the letter is
  data, not instructions), one retry with the contract's problems, text from inbox files or re-fetched by
  URL (PDFs with page markers, HTML, text), and the run: one `extraction_run` per document in its own
  transaction, failures recorded per document, stale running runs swept. `whales extract predictions`
  lists candidates; `--apply` runs only in Azure.
- `.env.example` and `infra/azure.toml`: `WHALES_MODEL_ENDPOINT` and `WHALES_MODEL_DEPLOYMENT` (the
  deployment name is still to come).
- Decision W-052; AGENTS, STATUS and PREDICTIONS.md updated.
- Tests: the seam against a fake endpoint; the runner against a fake model and a fake database.

**Verified.** Unit tests and ruff pass. Nothing has reached a real endpoint: `whales model check` is the
first thing to run once a deployment and the role assignment exist.

**Next.**
1. Owner: a deployment on `tocqv-research-ai` (or another in-tenant resource, added to the allowlist by
   commit) and the Cognitive Services OpenAI User role for `id-whales-ingest` and the owner's account.
2. Owner: how the inbox PDFs reach the runner: the blob upload (W-044) or a W-045 extension to full text
   on a laptop for the pilot.
3. Then: mentions, topics and ratings prompts on the same runner; the digest.

## 2026-10-14 (later): trust baselines, and "earned but quickly lost"

**Owner direction.** "Your baseline views seem fine, as long as it doesn't impact functionality or analysis
if we have to change them later. Trust is earned but can be quickly lost." Decision W-051.

**What changed.**
- `config/trust.toml`: the baselines, one rule per source type, expanded by `whales config check` to every
  (document kind, author kind) pair; a pair covered twice or not at all is refused. `whales config sync`
  writes them to `core.trust_baseline` (new in migration 0002), which views read at query time, so a change
  touches nothing stored.
- Migration 0002: `confidence` (high, medium, low) on `letters.prediction`; the view `letters.author_trust`
  (one row per writer and medium: baseline, basis counts, the earned record, confident misses, `trust_flag`);
  `letters.track_record` now sums it per writer.
- `src/whales/predictions.py`: `confidence` in the contract and the insert.
- Docs: PREDICTIONS.md section 7, DECISIONS W-050 and W-051, SCHEMA, STATUS, AGENTS.
- Tests: config coverage and overlap checks, the baselines in the sync plan, the contract field, and the
  live flag check.

**Verified.** Unit tests and ruff pass. The SQL is still unverified against a server. For the first Azure
session: run `db migrate --apply` before `config sync --apply`, since the sync now reads
`core.trust_baseline`.

**Next.** Unchanged: deploy, apply 0002, sync, live tests; then the model seam.

## 2026-10-14: trust profile, layer 2 (the basis of each claim)

**Owner direction.** "Some sort of trust score (and/or more context/evaluation if something is pure
opinion, well researched thesis, observable facts, etc) even roughly by source type." From the three-layer
proposal the owner chose "basis now, baselines next" (W-050). The owner asked whether "prior" meant
priority; it is the statistics word for a starting assumption, so the docs now say "baseline".

**What changed.**
- Migration 0002 (still unapplied, so edited in place): `basis` (data, reasoning, assertion) and
  `basis_note` on `letters.prediction`, `letters.mention` and `letters.topic_mention`; the migration refuses
  to run if the mention tables hold rows (they are empty). `prediction_state` shows the basis;
  `track_record` counts data-backed, reasoned and asserted calls.
- `src/whales/predictions.py`: `basis` required and `basis_note` optional in the contract and the insert.
- `docs/PREDICTIONS.md`, section 7: the trust profile (baseline by source type, basis, earned trust, the
  owner's optional tag) with the baselines table for the owner to correct. Decision W-050. SCHEMA, STATUS,
  AGENTS and RATINGS_AND_TAGS updated.
- Tests: fixtures carry a basis; three new refusals; the live track-record check covers the basis counts.

**Verified.** Unit tests and ruff pass. The SQL is still unverified against a server (Azure blocked).

**Next.** Once the owner corrects the baselines: `config/trust.toml` with its sync, and the
`letters.author_trust` view. Then as before: deploy, apply 0002, the model seam.

## 2026-10-13 (night): predictions as linked claims (migration 0002, not applied)

**Owner direction.** The owner's earlier document/idea/tweet parser produced a predictions table with
dependencies ("Brent < $100, 12/31/2026, dependency: Iran peace"); the owner asked for the design and the
migration, was first undecided on clippings ("don't want to get caught going down a rabbit hole") and then
confirmed the route (W-049: "seems like a good approach, another input, not built quite yet, but plan for
flexibility"), and noted that "not everything will be deterministic; this is where LLMs will really help". The earlier parser lives on the
owner's personal desktop. The financial-graph archive (`../financial-graph.zip`) was read for ideas only
(`docs/PREDICTIONS.md`, section 8); it holds a `.env` with API keys and third-party research PDFs, and
nothing from it was copied into this repo.

**What changed.**
- `src/whales/db/migrations/0002_predictions.sql`: `letters.prediction` rebuilt as one testable claim per
  row (role, subject, metric, comparator, threshold, window, timing), plus `prediction_link` (premise_of,
  causes), `prediction_check` (the job's proposed outcome with evidence), `prediction_score` (a person's
  verdict), and the views `prediction_state` and `track_record`. The clipping media (tweet, article,
  transcript, note) added to the document kinds. The migration refuses to run if the old table holds rows
  (it is empty: no extraction has run).
- `src/whales/predictions.py`: the JSON contract the model must return, `parse` (every problem reported at
  once; unknown topics dropped and noted; links checked for roles and cycles), `store`, `refuse_if_scored`.
- `docs/PREDICTIONS.md`: the design, the two examples parsed, the resolution flow, the clippings route
  (W-049, not built), what was taken from financial-graph and what was not.
- `Whale Tracker Inbox/clippings/` created and the inbox README extended with the clipping file format, so
  the owner can start clipping before the loader route exists.
- Decisions W-048 and W-049. SCHEMA.md, STATUS.md, AGENTS.md and RATINGS_AND_TAGS.md updated.
- Tests: 36 new unit tests (162 in all); live tests for the new grants and the state view, for
  `pytest -m live` once the migration is applied.

**Verified.** Unit tests and ruff pass. The SQL has not run against a server (Azure sign-in blocked): the
first `db migrate --apply` from the admin job is the real check, followed by `pytest -m live`.

**Next.**
1. When IT clears Azure: deploy, `db migrate --apply` (0002), `config sync --apply`, then the live tests.
2. The model seam and a Foundry endpoint, then the predictions prompt (contract in `predictions.CONTRACT`,
   rules in `docs/PREDICTIONS.md`, section 2).
3. The clippings route in the inbox loader (W-049, confirmed): the folder and file header are defined in
   `docs/PREDICTIONS.md`, section 6, and in the inbox README.
4. Open for the owner: the canonical subject list; X's terms for model use on hand-clipped posts; whether
   `data` and `price` checks may auto-score after a grace period (today a person always confirms).

## 2026-10-13 (evening): website collector; 17 sites automatic, 5 manual

**Owner direction.** "Go ahead with the website collectors."

**What changed.**
- `src/whales/sources/web.py`, a polite fetcher:
  - declared User-Agent;
  - robots.txt per host (4xx means no rules, unreadable means stop) and Crawl-delay;
  - at least 2 seconds per host;
  - only the source's hosts, re-checked after redirects;
  - size cap.
- Its rules list documents from index pages (with paging that stops when a page is empty or missing), a
  sitemap or a feed, with options to follow one hop, rewrite links and read `javascript:` links.
- `src/whales/collect_web.py`: a dry run, offline without a database, and recording as `whales_ingest`.
  Recording reads PDFs, so it runs only in Azure.
- Config: `web` rules for 17 sources. Berkshire, Lyn Alden, Coatue and FPA were switched to manual (bot walls,
  Drive, browser-only terms). Bonsai is manual and not machine-read: robots.txt blocks AI crawlers (W-047).
  Alluvial's URL was corrected to `/partnership-info/`.
- `infra/azure.toml` has a new weekly job, `job-whales-collect-web` (Mondays 10:00 UTC).
- Decisions W-046 and W-047. 126 unit tests.

**Verified.** The live dry run (index pages only, 94 requests, no errors) lists 2,210 documents across the
17 sites, matching the agents' counts site by site (LETTER_SOURCES.md, "Website collection").

**Process note.** One research agent breached the no-download instruction once: about 300 KB of the 2026
In Gold We Trust PDF, fetched to test a download URL and deleted unread.

**Next.**
1. Deploy once IT clears the Azure sign-in, then run `collect web --apply` in Azure. The first run will
   fetch about 2,200 documents politely, which takes a while.
2. One-off backfills, if wanted: Hussman 1999 to 2017, Smead quarterly newsletters.
3. The owner to confirm W-047.

## 2026-10-13 (later): pypdf and the inbox loader; the owner's 78-PDF library identified

**Owner direction.**
- "Go ahead with pypdf and build the loader."
- He has a starting library of PDFs, from public websites and shared by managers, now in the inbox (W-044).
- He allowed the inbox scan to read PDFs on the laptop (W-045).
- He shared his email exchange with GreenWood's COO, now saved in the inbox's permissions folder.

**What changed.**
- pypdf 6.19.0 (pinned in the locks; the days-old 6.20.x avoided).
- `src/whales/inbox.py`:
  - scans the inbox by route and identifies the manager by slug folder or by name or alias;
  - infers the period from file name, then title, then first page, covering `Q1'24`, `1H 2024`, `YE'25`,
    `Year End 2016`, and annual or semi-annual letters with no year;
  - takes the publication date from a date in the file name, a stated date or the PDF date, only when
    plausible, and never treats an "as of" date as one;
  - reads permission flags.
- `src/whales/inbox_load.py`: records each file once by sha256 under the manager's source, as
  `whales_ingest`.
- Commands: `whales inbox scan` and `whales inbox load`.
- Config:
  - managers Alluvial, Bonsai and GreenWood, with aliases;
  - sources `alluvial-writings` and `bonsai-letters` (auto, cleared);
  - `greenwood-letters` (off: terms exclude data mining);
  - `greenwood-shared` (recorded, not machine-read);
  - `greenwood-edgar` (13D, auto).
- W-045 recorded; AGENTS security rule amended. 115 unit tests.

**Verified.**
- `whales inbox scan` identifies all 78 PDFs: Laughing Water 20, Praetorian 16, Bonsai 15, Alluvial 14,
  GreenWood 13.
- None is unreadable or forbids text extraction, and every file maps to a source.
- Some publication dates are inferred, not stated: Laughing Water's 2016 and 2017 letters fall back to the
  period end.

**Next.**
1. `whales inbox load --apply` once Azure is reachable.
2. The owner may ask GreenWood for explicit consent (a draft reply is in the chat, not sent).
3. Auto collectors for the 22 cleared website sources.

## 2026-10-13: compliance position recorded (W-043); Azure sign-in with IT

**Owner direction.**
- Compliance: "we are good if we only use the sources for internal purposes and we don't re-publish or
  quote externally. We do not publish our own research. And we will not be selling or monetizing the
  content in any way." Recorded as W-043.
- Azure CLI sign-in is blocked by Conditional Access on both of the owner's machines; IT is looking at it.

**What changed.**
- `config/letter_sources.toml`: the 29 tier-1 sources without an explicit AI or data-mining ban are now
  active, approved under W-043. 41 of 44 sources are active.
- Fundsmith, Sprott and Third Point's Malibu site stay inactive until the publisher consents.
- AGENTS.md has a new standing rule: everything this project produces stays inside the firm.
- STATUS, LETTER_SOURCES and DECISIONS updated.

- The owner has a starting library of tier-1 PDFs (from public websites, and shared by managers). It goes in
  `../Whale Tracker Inbox` (W-044; folder and README created), never in git: `*.pdf` and `*.msg` are now
  gitignored, except test fixtures.

**Not done.**
- The database is not synced, because the Azure block also stops database access. The next sync (from the
  admin job once deployed) writes the activations.
- No tier-1 collector exists yet: only the SEC collector is built. Activation matters once auto collectors
  and the manual reminder calendar exist.
- Before automating each tier-1 source, re-read its terms page. The agents' paraphrases were not all
  re-checked (LETTER_SOURCES.md).

## 2026-10-10: SEC collector built; runs move into Azure

**Owner direction.**
- "Go ahead with the SEC collector first."
- The SEC sources were activated with the owner as approver (his go-ahead), since they need no terms ruling.
- On the laptop sign-in and firewall friction, "temporary firewall sounds like an absolute nightmare": he
  chose to move runs into Azure now (W-042).

**What changed.**
- `whales collect sec`:
  - `src/whales/sources/edgar.py` (SEC client) and `sec_letters.py` (presets `activist`, `ncsr`,
    `earnings_8k`; boilerplate deny-list; PDF flags);
  - `src/whales/collect.py` runs as `whales_ingest` and writes run_log and fetch_attempt rows;
  - 12 SEC sources with `edgar` rules and `edgar_since = 2024-10-01`.
- Azure: `Dockerfile`, `.dockerignore`, `infra/azure.toml`, `infra/deploy.py` (idempotent; dry run by
  default; builds from `git archive HEAD`).
- New commands: `whales db add-identity`, `whales db close-firewall`, `whales status`, and the global
  `--open-firewall`. Migrations, config sync and status now run as `whales_owner` for the whole session.
- Decisions W-041 and W-042. 84 unit tests.

**Verified.**
- An EDGAR-only preview found 180 documents since 2024-10-01 across 8 of the 12 sources:
  - Elliott 100;
  - Pershing Square 45;
  - Starboard 13;
  - Greenlight Re 7;
  - Trian 5;
  - Third Point 5;
  - JANA 4;
  - PSUS 1.

  ValueAct, TCI, Appaloosa and Praetorian have no exhibits in the window.
- Two parser fixes came from real pages: inline-XBRL links (`/ix?doc=`) hid the PSUS report, and
  boilerplate labels sometimes sit in the type column.
- Nothing has been written to the database yet. On 2026-10-10 the firm's Conditional Access policy
  blocked the Azure CLI token refresh (AADSTS53003), which needs an interactive `az login` by the owner.

**Blocked on the laptop (as of 2026-10-13).**
- On the owner's main laptop (hybrid-joined, device healthy), Azure CLI sign-in fails with AADSTS53003:
  Conditional Access refuses token issuance. Trace ID `78a2635f-13fe-44cf-8da6-0eb0c85f3100`, correlation ID
  `9a1e9739-aff6-4097-843e-7f4e7a5ddc5a`, 2026-10-10 14:25:43 UTC; IT can look it up in Entra sign-in logs.
- Plan: deploy from the owner's other desktop. It had no Azure CLI on 2026-10-13. Check that
  portal.azure.com signs in there first; if it does, install the CLI (`winget install -e --id
  Microsoft.AzureCLI`), confirm Python 3.13 and git, and run the steps below in Claude Code on that desktop.
- The venv does not travel (AGENTS.md, Environment); `.env` comes with OneDrive.

**Next (needs the owner's `az login` once).**
1. `python infra/deploy.py --apply`.
2. Register the identities, from the laptop:
   - `whales --open-firewall db add-identity id-whales-admin --group owner whales_dev --apply`;
   - the same for `id-whales-ingest --group ingest`.
3. Run the admin job with `config sync --apply`, then start `job-whales-collect-sec`, then the admin job
   with `status`. Check the logs.

## 2026-10-09 (later): config files and `whales config sync`

**Owner direction.** "Go ahead with config files and config sync."

**What changed.**
- `config/tags.toml` (23 tags) and `config/topics.toml` (10 topics; lumber under housing, edge compute under
  AI).
- `config/managers.toml`: 57 managers and writers, 54 filers with the verified successions, 261 tag proposals
  (14 marked uncertain), and one excluded filing (the Situational Awareness duplicate).
- `config/letter_sources.toml`: 44 sources (20 tier-1 auto, 12 tier-1 manual, 12 tier-2 SEC), every one
  inactive. Fundsmith, Third Point/Malibu and Sprott have `use_allowed = false`.
- `src/whales/config.py`: loads with `tomllib` and validates, reporting every problem at once.
- `src/whales/db/sync.py`: plans, then applies as `whales_owner` in one transaction. Never deletes.
- Commands `whales config check` and `whales config sync`.
- Tests: 43 unit, 19 live. W-040 recorded; AGENTS.md layout and commands updated.

**Verified.**
- The writers' 17 CIKs were checked against EDGAR (2026-10-09); all match and file current 13Fs.
  Praetorian, PSUS and Greenlight Re file no 13F, as expected.
- The first sync wrote 449 rows to `whales_dev`; the second reported nothing to do.
- Spot checks: the Greenlight hand-over (filer 1079114 to 2023 Q4, DME 1489933 from 2024 Q1) and the
  restricted sources' flags are correct.
- The temporary firewall rule `whales-dev-temp-20261009b` was removed.

**Next.**
1. A command to ratify, reject and correct tags (insert-only `core.tag_decision`).
2. The first auto source collector, once compliance approves a source. A tier-2 SEC source (PSUS N-CSRS or a
   13D exhibit) needs no ruling on terms and is a natural first.
3. The model seam and the Foundry endpoint.

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
