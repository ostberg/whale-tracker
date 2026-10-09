# Database schema

The design of database `whales` (development `whales_dev`), decision W-039. AGENTS.md "Data model" lists
the tables; this file fixes the conventions and the columns. Migration `0001` creates what phase 2 (the
letters pilot) needs. The 13F tables come with phase 3 and are only sketched here.

## Conventions (decide once)

1. **Ownership.** A NOLOGIN role `whales_owner` owns every schema, table, view and sequence. Migrations run
   as an admin who switches to it (`SET ROLE whales_owner`), so no object belongs to a person's account.
   Default privileges are set for `whales_owner`, so new tables get the right grants automatically.
2. **Roles.** All of them are NOLOGIN groups; login identities are made members.

   | Role | Gets | Members |
   |---|---|---|
   | `whales_owner` | Owns everything; runs DDL | The Entra admin, for migrations only |
   | `whales_ingest` | USAGE on `raw`, `core`, `letters`; SELECT, INSERT, UPDATE on their tables (DELETE only where noted); sequences. No DDL, so the internet-facing job cannot change the schema | The ingest job's identity; a developer while testing |
   | `whales_reader` | USAGE on `api`; SELECT on its views | `id-research-assistant` (later), firm-side jobs |
   | `whales_reviewer` | `whales_reader`, plus UPDATE on the review columns (overrides, verdicts, ratification, prediction scoring) | Whoever acts as `letters_reviewer` (W-034) |

   Every role name starts `whales_`; nothing is shared with Tamale (W-004).
3. **Migrations.** Plain numbered SQL files in `src/whales/db/migrations/` (`0001_foundation.sql`, ...), each in
   one transaction. They are recorded in `raw.schema_migration` with a checksum: an edited, already-applied
   file is refused. They are applied by an admin command, never by the ingest job.
4. **Keys.** Every table has a surrogate `id bigint GENERATED ALWAYS AS IDENTITY` primary key, plus a UNIQUE
   constraint on its natural key (CIK, accession, content hash, source and period). Foreign keys reference `id`.
5. **Fixed vocabularies** are `text` columns with CHECK constraints, not Postgres enum types: enums are
   awkward to change. Vocabularies that people edit (tags, topics) are tables loaded from `config/`, and
   foreign keys enforce them.
6. **Time.** Business dates are `date`: quarter end, period covered, publication date, horizon. System
   moments are `timestamptz` in UTC: fetched, created, reviewed. A quarter is stored as its end date, and a
   CHECK constraint makes sure it is one.
7. **Provenance.** Each row derived by a model references `letters.extraction_run` (model, prompt version,
   input file, time), and through it `raw.run_log`. Rows are never overwritten by a re-run: a new run adds new
   rows, and views choose the latest successful run. People's verdicts live in their own columns or tables,
   so a re-run never erases them.
8. **No silent deletes** of collected or derived data. Corrections are new rows or versions. DELETE is granted
   only on working tables (for example a failed run's partial rows).
9. **Quotes stay short** (W-015): CHECK constraint `length(quote) <= 400`.
10. **The `public` schema stays empty.**

## Phase 2 tables (migration 0001)

### `raw`

| Table | Columns (beyond `id`, `created_at`) | Notes |
|---|---|---|
| `raw.schema_migration` | `version int UNIQUE`, `name`, `checksum`, `applied_at`, `applied_by` | |
| `raw.run_log` | `command`, `started_at`, `finished_at`, `status` (running, ok, failed), `detail jsonb`, `git_sha`, `host` | One row per CLI run |

### `core`

| Table | Columns | Notes |
|---|---|---|
| `core.manager` | `name UNIQUE`, `kind` (manager, listed vehicle, independent writer, economist or strategist), `active`, `notes` | A manager or writer. Kind is a column because each has exactly one (W-038) |
| `core.tag` | `facet` (style, strategy, asset focus, geography), `tag`, `description`; UNIQUE (`facet`, `tag`) | The controlled list, loaded from `config/tags.yaml` |
| `core.manager_tag` | `manager_id`, `tag_id`, `valid_from date`, `valid_to date NULL`, `proposed_by`, `evidence`, `ratified_by NULL`, `ratified_at NULL` | Applies only once ratified |
| `core.filer` | `cik bigint UNIQUE`, `manager_id`, `edgar_name`, `first_quarter date`, `last_quarter date NULL`, `note` | W-024. Created now, because the survey already holds this data and 13D/G (W-031) needs it |
| `core.security` | `figi UNIQUE NULL`, `composite_figi`, `share_class_figi`, `cusip NULL`, `ticker`, `exch_code`, `name`, `security_type`, `mapped_at`, `mapping_source` | The security master. In phase 2 it is filled from OpenFIGI for tickers named in letters (public data only, D-127); in phase 3 from 13F CUSIPs as well |
| `core.topic` | `slug UNIQUE`, `name`, `parent_id NULL`, `description`, `aliases text[]`, `tamale_topic_id NULL` | W-018, recommended option (a): a short list owned here, each topic carrying the id of its Tamale twin |

### `letters`

| Table | Columns | Notes |
|---|---|---|
| `letters.source` | `manager_id`, `name`, `url`, `tier` (1 to 4), `mode` (auto, manual), `cadence` (annual, semiannual, quarterly, monthly, irregular), `access_restricted bool`, `storage_allowed bool`, `use_allowed bool`, `permission_basis text`, `terms_url`, `approved_by`, `approved_at`, `active` | W-029, W-033, W-035. Loaded from `config/letter_sources.yaml`. `use_allowed = false` blocks model extraction |
| `letters.expected` | `source_id`, `period_end date`, `due_from date`, `due_to date`, `status` (awaiting, loaded, not yet published, skipped), `assignee_role` (default `letters_reviewer`), `reminders int`, `last_reminded_at`, `document_id NULL`; UNIQUE (`source_id`, `period_end`) | W-033 reminder calendar |
| `letters.document` | `manager_id`, `title`, `kind` (annual letter, quarterly letter, memo, commentary, activist letter, presentation, essay, filing exhibit, other), `period_end date NULL`, `published_on date NULL`, `language` | The letter as a work, whatever copy it came from |
| `letters.document_file` | `document_id`, `source_id`, `tier`, `url`, `sha256`, `content_type`, `byte_size`, `fetched_at`, `collected` (auto, manual), `collected_by NULL`, `raw_kept bool`, `blob_path NULL`, `pdf_encrypted NULL`, `pdf_extract_allowed NULL`, `use_allowed bool`, `permission_basis`; UNIQUE (`source_id`, `sha256`); CHECK `raw_kept = (blob_path IS NOT NULL)` | **One row per copy or version.** Permissions are copied from the source when fetched, so a later change to a source does not silently re-license old copies (W-030, W-032) |
| `letters.document_text` | `document_file_id UNIQUE`, `text`, `extracted_at`, `extractor`, `pages int` | Only where `storage_allowed`. Otherwise text is held in memory during extraction and not stored (W-032) |
| `letters.extraction_run` | `document_file_id`, `run_id`, `model`, `prompt_version`, `started_at`, `finished_at`, `status`, `dropped_mentions int` | Provenance for every model output. Refused in code when the copy's `use_allowed` is false (W-035) |
| `letters.mention` | `extraction_run_id`, `document_id`, `security_id`, `stance` (positive, negative, mixed, neutral), `says_owned bool NULL`, `summary`, `quote`, `page NULL` | A ticker that doesn't match `core.security` is dropped and counted (AGENTS.md) |
| `letters.topic_mention` | `extraction_run_id`, `document_id`, `topic_id`, `stance`, `summary`, `quote`, `page NULL` | |
| `letters.topic_candidate` | `extraction_run_id`, `label`, `quote`, `status` (pending, approved, rejected), `reviewed_by`, `reviewed_at` | W-018 |
| `letters.prediction` | `extraction_run_id`, `document_id`, `security_id NULL`, `topic_id NULL` (CHECK exactly one is set), `direction`, `horizon_date NULL`, `horizon_text`, `condition`, `confidence_wording`, `quote`, `page NULL`, `status` (open, right, wrong, partly right, unresolvable; default open), `scored_by`, `scored_at`, `score_note` | W-037 |
| `letters.rating` | `extraction_run_id`, `document_id`, `dimension` (insight, clarity), `score smallint` 1 to 5, `reason`, `quote`; UNIQUE (`extraction_run_id`, `dimension`) | W-036. Predictions and Uniqueness are counted in views, not stored |
| `letters.rating_verdict` | `rating_id`, `verdict` (about right, too high, too low), `by`, `at` | The owner's quick verdicts (W-036) |

Views in `letters` (internal, not the `api` contract) pick the latest successful run per document:
`letters.current_mention`, `letters.current_rating`, and so on.

## Later

- **Phase 3:** `raw.filing`, `core.holding`, `core.position_quarter`, `core.event`, `core.topic_security`.
  These follow AGENTS.md and W-024 and W-025, and get their own design pass then.
- **Embeddings:** needs pgvector allow-listed on the shared server (STATUS.md). Phase 2, migration 0002 or
  later.
- **`api` views:** created when the first consumer exists (W-005); none in 0001.
- **`restricted` schema:** only if compliance ever clears LP letters (W-014).
