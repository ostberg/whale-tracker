# Status board

What is done, in progress, outstanding or blocked, and on whom. Read this first, then DECISIONS.md.

*Last updated 2026-10-08: planning complete (topic analysis added the same day); nothing built; folder
created; not yet a git repository.*

## Phases

Target dates were proposed by the planning agent and are not commitments.

| # | Phase | Target | Gate | Status |
|---|---|---|---|---|
| 1 | Setup: git repo and private remote, `whales_dev` database, manager list, blocking decisions | 2026-10-16 | Migrations run against the Azure server | Not started |
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

- [ ] **W-004, where the database lives.** `whales` as a second database on `pg-tocqv-context`, or its own
      small server. The existing server holds the confidential context layer; the ingest job is the only
      internet-facing part of this project.
- [ ] **How the ingest job runs in Azure.** Recommended: its own image, its own Container Apps job and its own
      managed identity (no access to the Tamale Key Vault secrets). Open: whether it also reports to the Tamale
      automation fleet's ledger, watchdog and alerts, and which subscription, resource group and region it
      uses (the Research Assistant is in East US; the Postgres server is in Central US).
- [ ] **Git remote.** Assumed: a private `whale-tracker` repository beside `tamale-tocqueville` under the same
      GitHub account. Confirm.
- [ ] **The first 20 or so managers.** Candidates discussed, listed from memory and each to be verified as a
      current 13F filer: Tiger Global, Coatue, Altimeter, Atreides, Whale Rock, Light Street, Dragoneer,
      Durable, Situational Awareness, Lone Pine, Viking Global, D1, Maverick, Duquesne, Appaloosa, Third Point,
      Berkshire Hathaway, Pershing Square, Baupost, Greenlight, TCI, Akre, Himalaya, Fundsmith, Elliott,
      Starboard, ValueAct, Trian, Jana.
- [ ] **The contact email** to declare in the SEC User-Agent header.

Later:

- [ ] **Topic list.** The starting list (interest rates, US Treasuries, European macro, housing, AI, edge
      compute, gold, inflation, lumber, oil) and whether it is shared with Tamale's Topic entities and the
      context layer's topic tags (recommended: one vocabulary).
- [ ] **Pull a letters pilot forward?** The say-side of topic analysis depends on letters, which are phase 6.
      A small pilot of openly published, macro-heavy writers could run earlier if compliance clears the
      sources.
- [ ] **Price source** for forward returns. APX closes are not split-adjusted (D-118) and the FactSet feed has
      stopped, so neither works as-is.
- [ ] **Alert delivery.** Reuse the Tamale fleet's alerting, a Teams channel, email, or a mix.
- [ ] **Tamale:** the entry type and service account for machine-generated whale notes (check the Tamale repo's
      `docs/NOTE_TYPE_CATALOG.md` first).
- [ ] **EDGAR client:** share one with the Tamale repo's planned EDGAR resolver, or keep them separate.
- [ ] **Compliance sign-off:** fetching public letters, the position on LP-received letters, retention of
      generated notes and alerts.

## Answered on 2026-10-08 by reading the Tamale repo

- The "research assistant chatbot" is the Research Assistant in the Tamale repo (`tamale.research_assistant`),
  deployed on Azure Container Apps and in pilot with the owner only.
- The Postgres server "started for something else" is `pg-tocqv-context` (the context layer, D-150).
- The Tamale repo already has an automation fleet, a provider-agnostic model seam, hash-pinned locks and CI
  gates; reuse the patterns here.
