# Decisions

Settled decisions and why, newest ids last. Ids are `W-nnn`; `D-nnn` refers to the Tamale repo's register.
"Proposed" means the planning agent recommended it on 2026-10-08 and the owner has not yet confirmed it.
"Owner" means the owner asked for it. Don't relitigate a confirmed decision; if one looks wrong, say so and ask.

| Id | Decision | Why | Standing |
|---|---|---|---|
| W-001 | A scheduled pipeline, not an always-on agent | Cheaper and auditable; a model is used only to read letters and write summaries | Proposed |
| W-002 | Public data only, in its own project and repo; firm-side consumers are built in the Tamale repo | The ingest job fetches untrusted content from the internet, so it must not sit beside Tamale or APX credentials | Proposed |
| W-003 | Postgres is the system of record; Tamale is an output | Tamale is a notes system, not a query engine; overlap and change questions need SQL | Proposed (owner suggested storing in Tamale; summaries still go there) |
| W-004 | Database `whales` on the existing server `pg-tocqv-context`, with the ingest identity limited to CONNECT on `whales` | Avoids a second server. Counted only as a switching cost (D-151): that server also holds the confidential `context` database, so a separate small server is the cleaner isolation | **OPEN: owner to choose** (see STATUS.md) |
| W-005 | Consumers read only the `api` views | Internal tables can change without breaking the Research Assistant | Proposed |
| W-006 | 13F first; letters and 13D/G later | 13Fs are structured, free and enough to test whether the signal is useful | Proposed |
| W-007 | Track forward performance from each event: first mention or initiation, adds, full exits | A rough check of whether following a manager or a signal is worth anything | Owner |
| W-008 | Two clocks per event: quarter-end and filing date | Quarter-end approximates the manager's result; the filing date is what a follower could capture | Proposed |
| W-009 | An "add" needs a threshold (20% share increase, split-adjusted, to start) | Share counts move for trivial reasons | Proposed |
| W-010 | Leave out multi-strategy and quant shops (Citadel, Millennium, Point72, Renaissance) | Thousands of positions and high turnover swamp the overlap signal | Proposed |
| W-011 | Whale data is a further source for the Research Assistant, through its front door and fixed query specs, not free-form SQL | Matches that project's spec-driven query model (D-001); easier to cite and to stamp with `as_of` | Owner asked for the source; the mechanism is proposed |
| W-012 | Joins to APX holdings happen in the Research Assistant, never here | APX positions are firm-confidential; this database is public data | Proposed |
| W-013 | Tamale notes: coverage and held names only, one "Whale activity" note per company per quarter, updated in place, labelled as delayed public data, written by a service account, dry run first | Keeps Tamale from being flooded and keeps machine output identifiable | Proposed |
| W-014 | LP-received letters are excluded by default | Confidentiality terms, fiduciary and misappropriation risk; needs fund-by-fund compliance clearance | Proposed |
| W-015 | For letters, store summaries, short quotes and a link, not full text for redistribution | Copyright | Proposed |
| W-016 | Project docs follow the Tamale repo's convention: `AGENTS.md` authoritative, `CLAUDE.md` imports it, `docs/STATUS.md`, `DECISIONS.md`, `HANDOFF.md` | One convention across the owner's projects; platform-neutral for any agent | Proposed |
| W-017 | Topic analysis with two lenses: what managers say (letters) and what they own (13F holdings mapped to topic baskets) | The owner asked for a topic analyzer. Letters carry the views; holdings show whether positioning matches, and the holdings lens works before any letters are ingested | Owner asked for topics; the two-lens design is proposed |
| W-018 | A controlled topic list in `config/topics.yaml`; the model may only tag topics on the list, and new ones wait in a candidate queue for a person to approve | Free tagging produces dozens of near-duplicates ("rates", "Fed policy", "yields") and trends that cannot be compared across quarters; matches the context layer's ratify-before-tagging rule | Proposed |
| W-019 | Every topic stance shown to a user carries the quote and a link to the source | Stance classification is a judgment call by a model; the reader must be able to check it | Proposed |
