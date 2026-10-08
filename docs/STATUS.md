# Status board

What is done, in progress, outstanding or blocked, and on whom. Read this first, then DECISIONS.md.

*Last updated 2026-10-08 (second session): local git repository created; Tamale repo plans read in full;
candidate managers surveyed on EDGAR. Nothing built.*

## Phases

Target dates were proposed by the planning agent and are not commitments.

| # | Phase | Target | Gate | Status |
|---|---|---|---|---|
| 1 | Setup: git repo and private remote, `whales_dev` database, manager list, blocking decisions | 2026-10-16 | Migrations run against the Azure server | In progress: local repo and first commit done; remote, database and decisions outstanding |
| 2 | 13F core: fetch, parse, CUSIP mapping, five-year backfill, event detection, run by hand | 2026-10-30 | Every filing reconciles to its summary-page totals; the overlap report against the coverage list reads sensibly | Not started |
| 3 | Azure job, quarterly digest, first live cycle (Q3 filings due Monday 2026-11-16). Includes topic exposure from holdings: `topics.yaml`, `core.topic_security`, `api.topic_exposure` | 2026-11-20 | A week of clean unattended runs; the owner has reviewed the securities mapped to each topic | Not started |
| 4 | Performance tracking: prices, forward returns, scorecards | December 2026 | Ten events checked by hand | Not started; needs a price source |
| 5 | Firm-side consumers, in the Tamale repo: Research Assistant source and "Why Now" prompts, Tamale publisher, alerts | Dec 2026 to Jan 2027 | Owner approves the Tamale note format on five companies | Not started |
| 6 | Letters and 13D/G, including topic mentions, topic trend and the said-versus-owned comparison | Q1 2027 | Compliance sign-off on the source list; topic tags spot-checked on 20 letters | Not started |
| 7 | Letter search in the Research Assistant; restricted tier only if cleared | After phase 6 | | Not started |

Phase 2 decides whether the signal is worth the rest. Do not start later phases until the owner finds the
overlap report useful.

## Decisions waiting on the owner

Blocking phase 1 or 2:

- [ ] **W-004, where the database lives.** The owner deferred this until the Tamale repo was read; it now has
      been. Recommended: its own small server. Sharing `pg-tocqv-context` would mean changing Tamale's server
      first (revoking CONNECT on `context` from PUBLIC) and sharing its public endpoint, sole admin, restores
      and B1ms capacity with an internet-facing job. Its own server could also sit in East US beside the job.
- [ ] **How the ingest job runs in Azure.** Settled in outline by W-020 and W-021 (own image, identity and
      environment; ledger rows through D-052; no immediate failure email). Still open: subscription, resource
      group and region, and whether to report to the fleet ledger at all (that needs a row and a role
      assignment made from the Tamale side).
- [ ] **Git remote.** The owner confirmed a private `whale-tracker` repository beside `tamale-tocqueville`. The
      local repository and first commit exist. `gh` is not installed, so the owner creates the empty private
      repository on github.com (no README, licence or .gitignore); the agent then adds `origin` and pushes.
- [ ] **The watchlist.** All 29 candidates plus the owner's additions (Oaktree, Southeastern/Longleaf,
      Whitebox) were verified on EDGAR on 2026-10-08: see `docs/MANAGER_SURVEY.md`. Each is a current 13F
      filer. Greenlight now files as DME Capital Management, and Pershing Square and Jana changed CIKs.
      Owner's first-pass priorities: Greenlight, Third Point, Oaktree, Pershing Square, Fundsmith, Longleaf,
      Elliott, Starboard, Jana and "Value Investor". **Open:** (1) what "Value Investor" means (no such 13F
      filer; ValueAct?); (2) W-026, ingest all 30 tagged by cohort rather than a first 20; (3) leave Whitebox's
      13F out and treat Andy Redleaf's writing as a letters source.
- [ ] **The contact email** to declare in the SEC User-Agent header. Proposed by the owner:
      `research@tocqueville.com`, used for the one-off survey on 2026-10-08. SEC does not verify or register the
      address. It is how SEC reaches someone before or after blocking a client, so it must be a real, monitored
      mailbox. Owner to confirm it exists and who reads it. The value lives in configuration, not code.

Later:

- [ ] **Topic list and its source of truth (W-018).** The starting list is interest rates, US Treasuries,
      European macro, housing, AI, edge compute, gold, inflation, lumber and oil. Tamale already has about 250
      Topic entities, applied unevenly. The Tamale code reads them live and keeps no copy (D-026, D-109), but
      this project cannot read Tamale (W-002). Options: (a) a short list owned here, each topic carrying the id
      of its matching Tamale Topic, kept in step by a firm-side check; (b) a firm-side job exports the
      ratified Tamale topics into a file this project reads; (c) separate lists. Recommended: (a), since the
      macro topics here are a small curated set and the Tamale list has not been cleaned up. Needed before
      phase 3.
- [ ] **Pull a letters pilot forward?** The say-side of topic analysis depends on letters, which are phase 6.
      A small pilot of openly published, macro-heavy writers could run earlier if compliance clears the
      sources.
- [ ] **Price source** for forward returns. APX closes are not split-adjusted (D-118) and the FactSet feed has
      stopped, so neither works as-is.
- [ ] **Alert delivery.** Reuse the Tamale fleet's alerting, a Teams channel, email, or a mix. The fleet's
      email goes through a Graph secret this project must not hold (W-021). A firm-side job reading the `api`
      views can send the alerts, or this project needs its own narrowly scoped sender.
- [ ] **Tamale:** the entry type for machine-generated whale notes. Account: fleet jobs already write as
      `tocquevilleapi` ("Research Automation", D-036). No entry type is agreed: the Tamale repo's
      `docs/NOTE_TYPE_CATALOG.md` is an unapproved draft. Needed before phase 5.
- [x] **EDGAR client:** nothing exists in the Tamale repo to share, so build one here (W-023, proposed).
- [ ] **Compliance sign-off:** fetching public letters, the position on LP-received letters, retention of
      generated notes and alerts.

## Answered on 2026-10-08 by reading the Tamale repo

- The "research assistant chatbot" is the Research Assistant in the Tamale repo (`tamale.research_assistant`),
  deployed on Azure Container Apps and in pilot with the owner only.
- The Postgres server "started for something else" is `pg-tocqv-context` (the context layer, D-150).
- The Tamale repo already has an automation fleet, a provider-agnostic model seam, hash-pinned locks and CI
  gates; reuse the patterns here.
- Second session, after reading the Tamale plans in full: the fleet's shared identity and file share must not
  be reused (W-020); ledger reporting goes through D-052 (W-021); tooling is copied (W-022); the EDGAR client is
  built here (W-023). Details are in AGENTS.md under "From the Tamale repo".
