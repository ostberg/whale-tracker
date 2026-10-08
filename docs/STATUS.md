# Status board

What is done, in progress, outstanding or blocked, and on whom. Read this first, then DECISIONS.md.

*Last updated 2026-10-08 (second session): letters made the primary product (W-027), phases re-planned;
local git repository created; Tamale repo plans read in full; candidate managers surveyed on EDGAR. Nothing
built.*

## Phases

Re-planned 2026-10-08 after the owner made letters the primary product (W-027). Target dates are the agent's
proposals, not commitments.

| # | Phase | Target | Gate | Status |
|---|---|---|---|---|
| 1 | Setup: git repo and private remote, `whales_dev` database, blocking decisions, letter-source inventory, compliance ruling on source tiers (W-029, W-030) | 2026-10-23 | Migrations run against the Azure server; compliance has ruled on tiers 1 to 3 | In progress: local repo done; source inventory running |
| 2 | Letters pilot, run by hand: fetch and store tier-1 and tier-2 letters for about ten managers, two years back, including activist letters filed as 13D exhibits (W-031); extract company mentions, topic stances and predictions, each with its quote, and rate each letter, through the in-tenant model seam | November 2026 | The owner finds the extraction useful on 20 letters; every stance carries its quote and link (W-019); ratings checked with quick verdicts on 10 letters (W-036) | Not started; needs a Foundry model endpoint for this project |
| 3 | Thin 13F layer (W-028): SEC bulk-data backfill, current quarters from the filing XML, filer map (W-024), unit detection (W-025), check against WhaleWisdom; 13G stakes (W-031); topic exposure and the said-versus-owned view | Nov to Dec 2026 (Q3 13Fs due Monday 2026-11-16) | Every filing reconciles; sampled positions match WhaleWisdom | Not started |
| 4 | Azure job and weekly digest: letters weekly, 13F after each deadline | December 2026 | A week of clean unattended runs | Not started |
| 5 | Firm-side consumers, in the Tamale repo: Research Assistant source and "Why Now" prompts, Tamale publisher, alerts | January 2027 | Owner approves the Tamale note format on five companies | Not started |
| 6 | Broaden: tier-3 sources if licensed, forward performance from first mentions and initiations (W-007; needs a price source) | Q1 2027 | Ten events checked by hand | Not started |
| 7 | Letter search in the Research Assistant; restricted tier only if cleared | After phase 5 | | Not started |

Phase 2 decides whether the letters signal is worth the rest. Do not start phase 4 or later until the owner
finds the pilot useful.

## Decisions waiting on the owner

Blocking phase 1 or 2:

- [x] **W-004, where the database lives:** the existing `pg-tocqv-context`, under four hardening conditions
      (owner, 2026-10-08). The steps below are phase-1 work and need the owner, as the server's only Entra
      admin, to run them or approve them:
      - [ ] in the Tamale repo, add `REVOKE CONNECT ON DATABASE context FROM PUBLIC` to
            `scripts/context_db_roles.py` and apply it;
      - [ ] create `whales_dev` (and later `whales`) and revoke CONNECT from PUBLIC on each;
      - [ ] check whether `vector` (pgvector) is in the server's `azure.extensions` allow-list; letter
            search and the Uniqueness score need it;
      - [ ] add a temporary firewall rule for the development machine, the same practice as the context
            layer.
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
- [ ] **Compliance ruling on letter sources** (W-029 tiers, W-030 PDF permission flags). This is the phase 1
      gate now that letters come first. The owner takes it to the CCO; the agent can draft a one-page brief.
- [ ] **Buy or build the letters collection.** Two aggregators carry the letters the owner cares about:
      - **Buy Side Digest** sells an institutional feed: a daily S3 delivery in JSON and CSV, links verified back
        to each manager's own source, and a normalised ticker and stance taxonomy. No price shown; contact
        info@buysidedigest.com. Its standard terms forbid automated access and any AI use, including
        embeddings, so only a licence works.
      - **Hedge Fund Alpha** has full letter text openly visible. Its legal disclaimer bans robots, copying and
        AI training, and it sells a data-licensing product.
      Recommended: the owner asks Buy Side Digest for an institutional trial and Hedge Fund Alpha for a licence,
      while the tier-1 and tier-2 pilot is built here. Any licence must allow in-tenant AI processing and
      storage. Outreach is the owner's to make.
- [ ] **Consent requests to publishers (W-035).** Fundsmith (and Smithson) forbid automated text analysis
      without express written consent, so neither manual nor automatic collection is enough. A short request,
      on firm letterhead after the compliance ruling, could also go to TCI ("private circulation"),
      Greenlight, and the topic writers whose terms ban bots (Apollo, Brookfield, Horizon Kinetics, Sprott,
      Oakmark). The owner decides whom to ask; the agent can draft the letter.
- [ ] **WhaleWisdom for the 13F check (W-028):** does the firm have, or want, a subscription? Without one, the
      API covers the last 8 quarters, excluding the current one.
- [ ] **A Foundry model endpoint for this project.** Letter extraction is now phase 2. The endpoint must be
      in-tenant and reached through the provider-agnostic seam.
- [ ] **Manual collection (W-033, W-034).** The owner chose a Teams digest and acts on reminders for now; a
      junior analyst or intern takes over later through the `letters_reviewer` role. Still open:
      - which team and channel;
      - who owns the Teams Workflows flow (ideally a service account rather than a person, so it survives staff
        changes; check that the firm's Power Automate policies allow an HTTP-triggered flow);
      - the intake location. Proposed: a Blob container `letters-inbox`, uploaded to with Storage Explorer or
        the portal; never a laptop or OneDrive folder.
- [ ] **The contact email** to declare in the SEC User-Agent header. Proposed by the owner:
      `research@tocqueville.com`, used for the one-off survey on 2026-10-08. SEC does not verify or register the
      address. It is how SEC reaches someone before or after blocking a client, so it must be a real, monitored
      mailbox. Owner to confirm it exists and who reads it. The value lives in configuration, not code.

Later:

- [ ] **Tag list (W-038).** The rubric is settled (W-036, simplified). The owner edits the tag list in
      `docs/RATINGS_AND_TAGS.md`, or asks for a first-pass proposal to correct.
- [ ] **Topic list and its source of truth (W-018).** The starting list is interest rates, US Treasuries,
      European macro, housing, AI, edge compute, gold, inflation, lumber and oil. Tamale already has about 250
      Topic entities, applied unevenly. The Tamale code reads them live and keeps no copy (D-026, D-109), but
      this project cannot read Tamale (W-002). Options: (a) a short list owned here, each topic carrying the id
      of its matching Tamale Topic, kept in step by a firm-side check; (b) a firm-side job exports the
      ratified Tamale topics into a file this project reads; (c) separate lists. Recommended: (a), since the
      macro topics here are a small curated set and the Tamale list has not been cleaned up. Needed before
      phase 3.
- [x] **Pull a letters pilot forward?** Yes, and further: letters are now the product (W-027, 2026-10-08).
- [ ] **Price source** for forward returns. APX closes are not split-adjusted (D-118) and the FactSet feed has
      stopped, so neither works as-is.
- [ ] **Alert delivery.** Reminders and the digest go to Teams (W-034). Still open: whether event alerts (new
      letter from a watched manager, a 13D on a held name) use the same channel. Holdings-based alerts stay
      firm-side (W-012).
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
