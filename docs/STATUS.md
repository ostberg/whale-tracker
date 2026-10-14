# Status board

What is done, in progress, outstanding or blocked, and on whom. Read this first, then DECISIONS.md.

*Last updated 2026-10-14: predictions redesigned as linked claims (W-048; migration 0002 written, not
applied) with the trust profile's baselines, basis and confidence (W-050, W-051); clippings route confirmed (W-049);
collectors built for SEC, websites and the inbox; compliance position recorded (W-043). Azure sign-in is
blocked, so nothing has run in Azure yet and the database is behind the config.*

## Phases

Re-planned 2026-10-08 after the owner made letters the primary product (W-027). Target dates are the agent's
proposals, not commitments.

| # | Phase | Target | Gate | Status |
|---|---|---|---|---|
| 1 | Setup: git repo and private remote, `whales_dev` database, blocking decisions, letter-source inventory, compliance ruling on source tiers (W-029, W-030) | 2026-10-23 | Migrations run against the Azure server; compliance has ruled on tiers 1 to 3 | Gate met 2026-10-09: migration 0001 applied to `whales_dev` and verified live. Compliance position recorded 2026-10-13 (W-043). Still open: the GitHub remote |
| 2 | Letters pilot, run by hand: fetch and store tier-1 and tier-2 letters for about ten managers, two years back, including activist letters filed as 13D exhibits (W-031); extract company mentions, topic stances and predictions, each with its quote, and rate each letter, through the in-tenant model seam | November 2026 | The owner finds the extraction useful on 20 letters; every stance carries its quote and link (W-019); ratings checked with quick verdicts on 10 letters (W-036) | In progress: collectors built (SEC, websites, inbox); 2,210 website documents and 78 inbox PDFs listed or identified. `config/` synced to `whales_dev` (57 managers, 54 filers, 261 tag proposals, 44 sources, all inactive). Predictions redesigned as linked claims (W-048): migration 0002 written and unit-tested, applied by the next admin job. The compliance ruling is in (W-043); still needs Azure (IT) and a Foundry model endpoint |
| 3 | Thin 13F layer (W-028): SEC bulk-data backfill, current quarters from the filing XML, filer map (W-024), unit detection (W-025), check against WhaleWisdom; 13G stakes (W-031); topic exposure and the said-versus-owned view | Nov to Dec 2026 (Q3 13Fs due Monday 2026-11-16) | Every filing reconciles; sampled positions match WhaleWisdom | Not started |
| 4 | Azure job and weekly digest: letters weekly, 13F after each deadline | December 2026 | A week of clean unattended runs | Pulled forward (W-042, 2026-10-10): jobs and identities defined in `infra/`; the digest is still to build |
| 5 | Firm-side consumers, in the Tamale repo: Research Assistant source and "Why Now" prompts, Tamale publisher, alerts | January 2027 | Owner approves the Tamale note format on five companies | Not started |
| 6 | Broaden: tier-3 sources if licensed, forward performance from first mentions and initiations (W-007; needs a price source) | Q1 2027 | Ten events checked by hand | Not started |
| 7 | Letter search in the Research Assistant; restricted tier only if cleared | After phase 5 | | Not started |

Phase 2 decides whether the letters signal is worth the rest. Do not start phase 4 or later until the owner
finds the pilot useful.

## Decisions waiting on the owner

Blocking phase 1 or 2:

- [ ] **Azure sign-in blocked (IT investigating, 2026-10-13).** Azure CLI sign-in fails with AADSTS53003
      (Conditional Access refuses token issuance) on the owner's laptop, and the owner's other desktop could
      not get through either. Until IT clears it, nothing that touches Azure or the database can run: the
      deploy (W-042), registering the job identities, and the first SEC collection. Trace and correlation IDs:
      HANDOFF.md, 2026-10-10 entry. Once cleared, the deploy is one short session (HANDOFF "Next").

- [x] **W-004, where the database lives:** the existing `pg-tocqv-context`, under four hardening conditions
      (owner, 2026-10-08). The steps below are phase-1 work and need the owner, as the server's only Entra
      admin, to run them or approve them:
      - [x] done 2026-10-08: `REVOKE CONNECT ON DATABASE context FROM PUBLIC` added to Tamale's
            `scripts/context_db_roles.py` (Tamale commit `1006a46`, not pushed) and applied live.
            Verified: the Research Assistant and weekly-job identities still connect through
            `context_writer`;
      - [x] `whales_dev` created (UTF8, en_US.utf8) and CONNECT revoked from PUBLIC on 2026-10-08, so the
            Tamale identities can no longer connect to it. `whales` follows when production is needed;
      - [x] checked 2026-10-08: `azure.extensions` is empty, so pgvector is not allowed. Adding `VECTOR`
            changes a parameter on the shared server; it is needed in phase 2 (letter search, Uniqueness), not
            phase 1. The server is `rg-research-automation`, B1ms, PostgreSQL 17, Central US, Ready, with
            databases `context`, `postgres`, `azure_sys` and `azure_maintenance`;
      - [x] a temporary firewall rule for the development machine was used and removed the same day
            (`whales-dev-temp-20261008`). Add one for each working session; remove it afterwards.
- [x] **How the ingest job runs in Azure:** W-042 (2026-10-10). `rg-whale-tracker`, Central US, the Tamale
      subscription, own registry, environment and identities. Still open: whether to report to the Tamale
      fleet ledger (W-021).
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
- [x] **Compliance ruling on letter sources:** W-043 (owner, 2026-10-13). Internal use only; no
      republication, external quotation or monetization. 29 tier-1 sources activated; Fundsmith, Sprott and
      Third Point's Malibu site stay off (explicit AI or data-mining bans). Still open: whether the CCO has
      signed off, for the record; the view on PDFs whose flags forbid text extraction (W-030).
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
- [ ] **A model deployment for this project (W-052).** The seam and the predictions runner are built and
      wait for: a chat-model deployment on `tocqv-research-ai` (the firm's in-tenant Azure AI resource,
      already approved for research content in the Tamale repo) or another in-tenant resource added to
      `whales.llm.APPROVED_MODEL_HOSTS` by commit; the role Cognitive Services OpenAI User on that resource
      for `id-whales-ingest` and for the owner's own account (laptop checks); then `WHALES_MODEL_DEPLOYMENT`
      in `infra/azure.toml` and `.env`. `whales model check` proves the connection. Also open: the pilot on
      the owner's 78 inbox PDFs needs either the inbox-to-blob upload (W-044) or an extension of W-045 to
      full text on a laptop, since `--apply` runs only in Azure.
- [ ] **Manual collection (W-033, W-034).** The owner chose a Teams digest and acts on reminders for now; a
      junior analyst or intern takes over later through the `letters_reviewer` role. Still open:
      - which team and channel;
      - who owns the Teams Workflows flow (ideally a service account rather than a person, so it survives staff
        changes; check that the firm's Power Automate policies allow an HTTP-triggered flow);
      - [x] the intake: `Whale Tracker Inbox` beside the project folder (W-044, created 2026-10-13), uploaded
        to the Blob container `letters-inbox` by the loader once Azure is reachable. The owner's starting
        library of tier-1 PDFs goes there.
- [ ] **The contact email** to declare in the SEC User-Agent header. Proposed by the owner:
      `research@tocqueville.com`, used for the one-off survey on 2026-10-08. SEC does not verify or register the
      address. It is how SEC reaches someone before or after blocking a client, so it must be a real, monitored
      mailbox. Owner to confirm it exists and who reads it. The value lives in configuration, not code.

Later:

- [ ] **Tag ratification (W-038).** The list is settled and the first-pass proposals (261, 14 uncertain) are
      in `config/managers.toml` and the database. Correct tags by editing that file, then ratify; a
      ratification command is not built yet.
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
- [x] **Clippings route (W-049).** Owner, 2026-10-13: a good approach, another input, not built yet, plan
      for flexibility. The folder and file format are defined (`docs/PREDICTIONS.md`, section 6; the inbox
      README), so files can be dropped now; the loader route follows the model seam. Still open: X's terms
      for model extraction on hand-clipped posts.
- [ ] **Topic-to-beneficiary edges.** The owner's financial-graph project links companies to topics with a
      stance (benefits, at risk, linked). Here that becomes a `stance` column on `core.topic_security` in
      phase 3, so "topic or technology → eventual beneficiary" chains can be followed. Not yet designed.
- [x] **Trust profile (W-050, W-051).** Layers 1 and 2 built 2026-10-14: baselines in `config/trust.toml`
      (read at query time only), basis and confidence on every claim, `letters.author_trust` with the
      confident-miss flag; all in migration 0002, not yet applied. Layer 3 fills as calls resolve. Optional
      later: a `trust` tag facet for the owner's own view.
- [ ] **Alert delivery.** Reminders and the digest go to Teams (W-034). Still open: whether event alerts (new
      letter from a watched manager, a 13D on a held name) use the same channel. Holdings-based alerts stay
      firm-side (W-012).
- [ ] **Tamale:** the entry type for machine-generated whale notes. Account: fleet jobs already write as
      `tocquevilleapi` ("Research Automation", D-036). No entry type is agreed: the Tamale repo's
      `docs/NOTE_TYPE_CATALOG.md` is an unapproved draft. Needed before phase 5.
- [x] **EDGAR client:** nothing exists in the Tamale repo to share, so build one here (W-023, proposed).
- [ ] **Compliance, remaining:** fetching public letters and LP-received letters are settled (W-043, W-014).
      Still open: retention of generated notes and alerts, and PDF permission flags (W-030).

## Answered on 2026-10-08 by reading the Tamale repo

- The "research assistant chatbot" is the Research Assistant in the Tamale repo (`tamale.research_assistant`),
  deployed on Azure Container Apps and in pilot with the owner only.
- The Postgres server "started for something else" is `pg-tocqv-context` (the context layer, D-150).
- The Tamale repo already has an automation fleet, a provider-agnostic model seam, hash-pinned locks and CI
  gates; reuse the patterns here.
- Second session, after reading the Tamale plans in full: the fleet's shared identity and file share must not
  be reused (W-020); ledger reporting goes through D-052 (W-021); tooling is copied (W-022); the EDGAR client is
  built here (W-023). Details are in AGENTS.md under "From the Tamale repo".
