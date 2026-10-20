# Database schema

How database `whales` (development `whales_dev`) is built, and why (decision W-039). Columns, constraints and
grants live in the migration files, `src/whales/db/migrations/NNNN_*.sql`. They are the source of truth;
this file keeps the conventions and the reasoning. Migration 0001 (applied to `whales_dev` on 2026-10-09)
covers phase 2, the letters pilot. The 13F tables come with phase 3.

An independent review on 2026-10-09 checked the first draft against Azure's managed Postgres and the
decisions. Its fixes are folded in below.

## Conventions

1. **Ownership.** A NOLOGIN role `whales_owner` owns every schema, table, function and type. Migrations run
   as the Entra admin, who switches to it (`SET LOCAL ROLE whales_owner`). The runner rolls back any migration
   that leaves an object owned by anyone else. Nothing belongs to a person's account.
2. **Roles** are NOLOGIN groups. Login identities are made members; CONNECT is granted per database to login
   roles, never to groups, so a developer added to a group for `whales_dev` gets nothing in `whales`.

   | Role | Can | Cannot |
   |---|---|---|
   | `whales_owner` | Everything, by owning it | Be used without an explicit `SET ROLE`: the admin holds it with INHERIT FALSE |
   | `whales_ingest` | Read `raw`, `core` and `letters`. Insert collected data and model output. Update only working columns (run status, reminder counters, security mapping fields) | See `meta`; change config tables (managers, sources, tags, topics); change any permission or review column; delete anything |
   | `whales_reviewer` | Read `core` and `letters`. Add decisions: tag ratification, topic-candidate approval, prediction scores, rating verdicts. Set an expected letter's status | Choose the `reviewed_by` name (the database stamps it); change model output; delete anything |
   | `whales_reader` | (created with the first `api` view, W-005) | |

   Roles are server-wide, so they are created by `whales db bootstrap-roles <database>`, not by a migration.
   On PostgreSQL 16 and later, an admin who creates a role holds it only WITH ADMIN, so the bootstrap grants
   the admin SET explicitly. Never grant `pg_read_all_data` or `pg_write_all_data`: they reach the whole
   shared server.
3. **Migrations.** Numbered SQL files, each applied in one transaction by `whales db migrate --apply`. They are
   recorded in `meta.schema_migration` with a checksum taken over normalised line endings, and an
   applied file that has been edited is refused. `meta` is invisible to the ingest job.
4. **Keys.** Each table has a surrogate `id` (identity) plus a UNIQUE natural key: CIK, slug, content hash,
   source and period. **Surrogate ids are internal:** they change if the database is rebuilt from blobs, so
   `api` views and Tamale notes expose natural keys (slug, sha256, accession), never `id`.
5. **Fixed vocabularies** are snake_case codes in named CHECK constraints (`not_yet_published`,
   `listed_vehicle`), never enum types; a later migration can drop and re-add a constraint by name.
   Vocabularies that people edit (tags, topics) are tables, loaded from `config/` by an admin.
6. **Time.** Business dates are `date`; system moments are `timestamptz` (UTC). A quarter is its last day, in
   the domain `core.quarter_end`.
7. **A letter versus its copies.** `letters.document` is the work; `letters.document_file` is each copy or
   version. Rule: each new copy creates its own document, and a person merges duplicates by pointing the copy
   at the surviving document. HTML pages are deduplicated on `text_sha256` (normalised text), because their
   markup changes weekly.
8. **Permissions are a snapshot per copy.** A trigger copies tier, use and storage permissions from the
   source when a copy is inserted, overwriting whatever the job supplied. `machine_read_ok` is true only if use
   is allowed and the PDF does not forbid text extraction. A composite foreign key then makes the database
   itself refuse an extraction run on a copy that may not be machine-read (W-030, W-032, W-035).
9. **Provenance.** Every model output belongs to a `letters.extraction_run` with a `task`: mentions, topics,
   predictions or rating. Composite keys stop a row from claiming a run of another task. Re-runs add rows and
   never overwrite. "Current" means the latest successful run per document and task, so re-running ratings
   does not hide mentions.
10. **People's decisions are insert-only rows** (`core.tag_decision`, `letters.candidate_decision`,
    `letters.prediction_score`, `letters.rating_verdict`). The database stamps who and when. A prediction's
    state (open, due, awaiting premise, proposed, void, scored) is derived in `letters.prediction_state` from
    its window, its links and the latest verdict, never stored. The job may propose an outcome with its
    evidence (`letters.prediction_check`); only a person's verdict scores. Code refuses to re-extract a
    document's predictions once any of them is scored, so scores never point at superseded rows.
11. **No DELETE** for any non-owner role. A failed run's partial output stays, and views filter on
    `status = 'ok'`.
12. **Quotes** are required on mentions, topic mentions, predictions and ratings (W-019), and are at most 400
    characters (W-015).
13. **The `public` schema stays empty.** TEMPORARY on the database is revoked from PUBLIC.

## What migration 0001 created

| Schema | Tables |
|---|---|
| `meta` | `schema_migration` |
| `raw` | `run_log` |
| `core` | `manager` (slug, kind), `tag`, `manager_tag` (proposals, dated), `tag_decision`, `filer` (CIK, quarter range), `security` (unique `composite_figi`, and `cusip` when present), `topic` (with `tamale_topic_id`) |
| `letters` | `source` (tier 1 to 3, mode, cadence, permissions), `document`, `document_file`, `fetch_attempt` (every fetch, so the digest can name stale sources), `expected` (the reminder calendar; status changes are stamped), `extraction_run`, `mention`, `topic_mention`, `topic_candidate`, `candidate_decision`, `prediction`, `prediction_score`, `rating`, `rating_verdict` |
| `api` | (empty until the first consumer, W-005) |

Every foreign key column is indexed.

## What migration 0002 changes (written 2026-10-13, not yet applied)

Predictions as linked claims (W-048; design and worked examples in `docs/PREDICTIONS.md`). The W-037 tables
of 0001 were empty, so the migration drops and recreates them rather than altering them, and refuses to run
if `letters.prediction` holds rows.

| Object | Holds |
|---|---|
| `core.trust_baseline` | the trust a source type starts with, by document kind and author kind, from `config/trust.toml` (W-050); read only at query time (W-051) |
| `letters.prediction` | one testable claim: role (asserted or premise), subject, metric, security or topic, comparator, threshold and unit, window and timing, confidence (code and wording), basis and basis note (W-050), claim, quote, page. `ordinal` is the model's own numbering within the run |
| `letters.mention`, `letters.topic_mention` | gain `basis` (data, reasoning, assertion) and `basis_note` (W-050); the migration refuses to run if either table holds rows |
| `letters.prediction_link` | `premise_of` and `causes` links between claims of one run. Composite keys keep both ends in the run and make the from-claim's role match the kind |
| `letters.prediction_check` | the job's proposed outcome, with method (data, price, filing, model), source, what was observed and when |
| `letters.prediction_score` | a person's verdict, optionally confirming or overriding one check of the same prediction |
| `letters.prediction_state` (view) | each claim's derived state |
| `letters.author_trust` (view) | per writer and medium: baseline, basis counts, the earned record over asserted claims from the latest successful predictions run per document, confident misses and `trust_flag` (W-051) |
| `letters.track_record` (view) | `letters.author_trust` summed per writer |

It also adds the clipping media `tweet`, `article`, `transcript` and `note` to `letters.document.kind` (W-049). Grants: the job inserts claims, links and checks;
the reviewer inserts verdicts without choosing `reviewed_by`. The SQL is unit-checked (named constraints, no
DELETE, vocabularies matching `whales.predictions`) but has not run against a server, because Azure sign-in is
blocked. `pytest -m live` carries a test of the state view for when it has.

## What migration 0003 adds (written 2026-10-20)

The weekly digest's memory (W-054; `docs/REPORTS.md`): schema `reports` with `digest` (one issue per day:
subject, body, item count, sent flag, run) and `digest_item` (kind, key, writers, score, detail), so a theme
is reported again only once it has grown; and the view `reports.theme_mention`, every theme mention from the
latest successful topics run per document, controlled topics and candidate themes under one key, with the
writer, publication date, source-type baseline and whether it is the writer's first mention ever. The job
inserts issues and items and may flip `sent`; the reviewer reads.

## Verified on 2026-10-09

Run with `pytest -m live`, against `whales_dev`:
- the migration is current;
- every object is owned by `whales_owner`;
- PUBLIC cannot connect;
- the admin holds owner and ingest with SET only, and reviewer with inherit;
- eleven privilege checks pass, covering ingest and reviewer;
- no role can delete;
- a forged permission snapshot is overwritten, and an extraction run on a forbidden copy is refused.

Writing tests run in transactions that roll back; the tables were empty afterwards.

## Later

- **Phase 3:** `raw.filing`, `core.holding`, `core.position_quarter`, `core.event`, `core.topic_security`.
  They get their own design pass; W-024 and W-025 already fix the filer ranges and the value-unit detection.
- **Full text and embeddings** (`letters.document_text`): in a later migration, once pgvector is allow-listed
  on the shared server. Text is stored only where the copy's `storage_allowed` is true (W-032).
- **The ingest identity:** create it with `pgaadauth_create_principal_with_oid`, make it a member of
  `whales_ingest`, and grant CONNECT on `whales` only. This is phase 4, with the Azure job.
- **`whales config sync`** (built 2026-10-09, W-040) loads managers, filers, tag proposals, sources, tags and
  topics from `config/` as `whales_owner`. Ingest only reads these tables.
