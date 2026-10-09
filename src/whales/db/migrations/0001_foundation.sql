-- 0001_foundation: schemas, conventions and the phase-2 (letters pilot) tables. Design: docs/SCHEMA.md (W-039).
-- Applied by `whales db migrate` as whales_owner, in one transaction. Roles come from `whales db bootstrap-roles`.
-- Never edit this file once applied anywhere: write 0002.

CREATE SCHEMA meta;     -- migration ledger and nothing else; the ingest job has no access
CREATE SCHEMA raw;
CREATE SCHEMA core;
CREATE SCHEMA letters;
CREATE SCHEMA api;      -- consumer views (W-005); empty until the first consumer exists

CREATE TABLE meta.schema_migration (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version     integer NOT NULL,
    name        text NOT NULL,
    checksum    text NOT NULL,
    applied_by  text NOT NULL DEFAULT session_user,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT schema_migration_version_key UNIQUE (version)
);

-- ---------------------------------------------------------------------------------------------------------
-- raw
-- ---------------------------------------------------------------------------------------------------------

CREATE TABLE raw.run_log (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    command      text NOT NULL,
    status       text NOT NULL DEFAULT 'running',
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    detail       jsonb NOT NULL DEFAULT '{}'::jsonb,
    git_sha      text,
    host         text,
    started_by   text NOT NULL DEFAULT session_user,
    CONSTRAINT run_log_status_check CHECK (status IN ('running', 'ok', 'failed'))
);

-- ---------------------------------------------------------------------------------------------------------
-- core
-- ---------------------------------------------------------------------------------------------------------

-- A quarter is stored as its last day.
CREATE DOMAIN core.quarter_end AS date
    CONSTRAINT quarter_end_check
    CHECK (extract(day FROM VALUE + 1) = 1 AND extract(month FROM VALUE + 1) IN (1, 4, 7, 10));

CREATE TABLE core.manager (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug        text NOT NULL,
    name        text NOT NULL,
    kind        text NOT NULL,
    active      boolean NOT NULL DEFAULT true,
    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT manager_slug_key UNIQUE (slug),
    CONSTRAINT manager_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    CONSTRAINT manager_kind_check
        CHECK (kind IN ('manager', 'listed_vehicle', 'independent_writer', 'economist_or_strategist'))
);

CREATE TABLE core.tag (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facet        text NOT NULL,
    tag          text NOT NULL,
    description  text,
    CONSTRAINT tag_facet_tag_key UNIQUE (facet, tag),
    CONSTRAINT tag_facet_check CHECK (facet IN ('style', 'strategy', 'asset_focus', 'geography')),
    CONSTRAINT tag_tag_check CHECK (tag ~ '^[a-z0-9][a-z0-9_]*$')
);

-- A proposed tag (W-038). It applies only once a decision in core.tag_decision ratifies it.
CREATE TABLE core.manager_tag (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manager_id   bigint NOT NULL REFERENCES core.manager (id),
    tag_id       bigint NOT NULL REFERENCES core.tag (id),
    valid_from   date NOT NULL,
    valid_to     date,
    proposed_by  text NOT NULL DEFAULT session_user,
    evidence     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT manager_tag_key UNIQUE (manager_id, tag_id, valid_from),
    CONSTRAINT manager_tag_valid_check CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX manager_tag_tag_id_idx ON core.manager_tag (tag_id);

-- People's decisions are insert-only rows; reviewed_by is stamped by the database, never supplied.
CREATE TABLE core.tag_decision (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manager_tag_id  bigint NOT NULL REFERENCES core.manager_tag (id),
    decision        text NOT NULL,
    note            text,
    reviewed_by     text NOT NULL DEFAULT session_user,
    reviewed_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tag_decision_decision_check CHECK (decision IN ('ratified', 'rejected'))
);
CREATE INDEX tag_decision_manager_tag_id_idx ON core.tag_decision (manager_tag_id);

-- One SEC filer CIK and the quarters it counts for (W-024). NULL first_quarter: from the start.
CREATE TABLE core.filer (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cik            bigint NOT NULL,
    manager_id     bigint NOT NULL REFERENCES core.manager (id),
    edgar_name     text NOT NULL,
    first_quarter  core.quarter_end,
    last_quarter   core.quarter_end,
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT filer_cik_key UNIQUE (cik),
    CONSTRAINT filer_cik_check CHECK (cik > 0),
    CONSTRAINT filer_quarters_check
        CHECK (first_quarter IS NULL OR last_quarter IS NULL OR last_quarter >= first_quarter)
);
CREATE INDEX filer_manager_id_idx ON core.filer (manager_id);

-- The security master. composite_figi is the stable key: OpenFIGI returns one figi per exchange.
CREATE TABLE core.security (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    composite_figi    text,
    share_class_figi  text,
    figi              text,
    cusip             text,
    ticker            text,
    exch_code         text,
    name              text NOT NULL,
    security_type     text,
    mapping_source    text NOT NULL,
    mapped_at         timestamptz NOT NULL DEFAULT now(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT security_composite_figi_key UNIQUE (composite_figi),
    CONSTRAINT security_identity_check CHECK (composite_figi IS NOT NULL OR cusip IS NOT NULL),
    CONSTRAINT security_cusip_check CHECK (cusip IS NULL OR cusip ~ '^[0-9A-Z]{9}$'),
    CONSTRAINT security_mapping_source_check CHECK (mapping_source IN ('openfigi', 'manual'))
);
CREATE UNIQUE INDEX security_cusip_key ON core.security (cusip) WHERE cusip IS NOT NULL;
CREATE INDEX security_ticker_idx ON core.security (ticker);

-- The controlled topic list (W-018). tamale_topic_id links a topic to its Tamale twin, when the owner
-- settles the source of truth.
CREATE TABLE core.topic (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug             text NOT NULL,
    name             text NOT NULL,
    parent_id        bigint REFERENCES core.topic (id),
    description      text,
    aliases          text[] NOT NULL DEFAULT '{}',
    tamale_topic_id  text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT topic_slug_key UNIQUE (slug),
    CONSTRAINT topic_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$')
);
CREATE INDEX topic_parent_id_idx ON core.topic (parent_id);

-- ---------------------------------------------------------------------------------------------------------
-- letters
-- ---------------------------------------------------------------------------------------------------------

-- Stamps who changed a row's status, and when. Whoever runs the UPDATE cannot choose those values.
CREATE FUNCTION letters.stamp_status() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        NEW.status_by := session_user;
        NEW.status_at := now();
    END IF;
    RETURN NEW;
END
$$;

-- One approved source (W-029, W-033, W-035). Tier 4 (LP-received) never lives here: it would go in a separate
-- `restricted` schema, and only if compliance clears it (W-014).
CREATE TABLE letters.source (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug               text NOT NULL,
    manager_id         bigint NOT NULL REFERENCES core.manager (id),
    name               text NOT NULL,
    url                text NOT NULL,
    tier               smallint NOT NULL,
    mode               text NOT NULL,
    cadence            text NOT NULL,
    access_restricted  boolean NOT NULL,
    storage_allowed    boolean NOT NULL,
    use_allowed        boolean NOT NULL,
    permission_basis   text NOT NULL,
    terms_url          text,
    approved_by        text,
    approved_at        timestamptz,
    active             boolean NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT source_slug_key UNIQUE (slug),
    CONSTRAINT source_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    CONSTRAINT source_tier_check CHECK (tier BETWEEN 1 AND 3),
    CONSTRAINT source_mode_check CHECK (mode IN ('auto', 'manual')),
    CONSTRAINT source_cadence_check
        CHECK (cadence IN ('annual', 'semiannual', 'quarterly', 'monthly', 'irregular')),
    CONSTRAINT source_access_mode_check CHECK (NOT access_restricted OR mode = 'manual')
);
CREATE INDEX source_manager_id_idx ON letters.source (manager_id);

-- A letter as a work. Rule: each new copy creates its own document; a person merges duplicates by pointing
-- letters.document_file.document_id at the surviving document.
CREATE TABLE letters.document (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manager_id          bigint NOT NULL REFERENCES core.manager (id),
    title               text NOT NULL,
    kind                text NOT NULL,
    period_end          date,
    published_on        date NOT NULL,
    published_on_basis  text NOT NULL,
    language            text NOT NULL DEFAULT 'en',
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_kind_check CHECK (kind IN ('annual_letter', 'quarterly_letter', 'memo', 'commentary',
        'activist_letter', 'presentation', 'essay', 'filing_exhibit', 'other')),
    CONSTRAINT document_published_on_basis_check CHECK (published_on_basis IN ('stated', 'inferred', 'first_seen'))
);
CREATE INDEX document_manager_published_idx ON letters.document (manager_id, published_on);

-- One copy or version of a document. Its permissions are a snapshot of the source's at insert time, copied by
-- letters.snapshot_permissions(), so neither the job nor a later change to the source can re-license it.
CREATE TABLE letters.document_file (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id          bigint NOT NULL REFERENCES letters.document (id),
    source_id            bigint NOT NULL REFERENCES letters.source (id),
    tier                 smallint NOT NULL,
    url                  text,
    accession            text,
    sha256               text NOT NULL,
    text_sha256          text,
    content_type         text NOT NULL,
    byte_size            bigint NOT NULL,
    fetched_at           timestamptz NOT NULL DEFAULT now(),
    collected            text NOT NULL,
    collected_by         text NOT NULL DEFAULT session_user,
    use_allowed          boolean NOT NULL,
    storage_allowed      boolean NOT NULL,
    permission_basis     text NOT NULL,
    raw_kept             boolean NOT NULL,
    blob_path            text,
    pdf_encrypted        boolean,
    pdf_permissions      integer,
    pdf_extract_allowed  boolean,
    machine_read_ok      boolean NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_file_source_sha256_key UNIQUE (source_id, sha256),
    CONSTRAINT document_file_id_document_key UNIQUE (id, document_id),
    CONSTRAINT document_file_id_machine_read_key UNIQUE (id, machine_read_ok),
    CONSTRAINT document_file_tier_check CHECK (tier BETWEEN 1 AND 3),
    CONSTRAINT document_file_sha256_check CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT document_file_text_sha256_check CHECK (text_sha256 IS NULL OR text_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT document_file_accession_check CHECK (accession IS NULL OR accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
    CONSTRAINT document_file_byte_size_check CHECK (byte_size > 0),
    CONSTRAINT document_file_collected_check CHECK (collected IN ('auto', 'manual')),
    CONSTRAINT document_file_locator_check CHECK (url IS NOT NULL OR accession IS NOT NULL OR collected = 'manual'),
    CONSTRAINT document_file_blob_check CHECK (raw_kept = (blob_path IS NOT NULL)),
    CONSTRAINT document_file_storage_check CHECK (storage_allowed OR NOT raw_kept),
    CONSTRAINT document_file_machine_read_check
        CHECK (machine_read_ok = (use_allowed AND coalesce(pdf_extract_allowed, true)))
);
CREATE INDEX document_file_document_id_idx ON letters.document_file (document_id);
CREATE INDEX document_file_accession_idx ON letters.document_file (accession) WHERE accession IS NOT NULL;
CREATE INDEX document_file_text_sha256_idx ON letters.document_file (text_sha256) WHERE text_sha256 IS NOT NULL;

CREATE FUNCTION letters.snapshot_permissions() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    s letters.source%ROWTYPE;
BEGIN
    SELECT * INTO STRICT s FROM letters.source WHERE id = NEW.source_id;
    NEW.tier := s.tier;
    NEW.use_allowed := s.use_allowed;
    NEW.storage_allowed := s.storage_allowed;
    NEW.permission_basis := s.permission_basis;
    NEW.machine_read_ok := s.use_allowed AND coalesce(NEW.pdf_extract_allowed, true);
    RETURN NEW;
END
$$;
CREATE TRIGGER document_file_snapshot_permissions
    BEFORE INSERT ON letters.document_file
    FOR EACH ROW EXECUTE FUNCTION letters.snapshot_permissions();

-- Every fetch of an auto source, including "nothing new", so the digest can name failing or stale sources.
CREATE TABLE letters.fetch_attempt (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         bigint NOT NULL REFERENCES letters.source (id),
    run_id            bigint REFERENCES raw.run_log (id),
    attempted_at      timestamptz NOT NULL DEFAULT now(),
    outcome           text NOT NULL,
    http_status       integer,
    document_file_id  bigint REFERENCES letters.document_file (id),
    error             text,
    CONSTRAINT fetch_attempt_outcome_check CHECK (outcome IN ('new', 'unchanged', 'failed', 'blocked'))
);
CREATE INDEX fetch_attempt_source_at_idx ON letters.fetch_attempt (source_id, attempted_at DESC);
CREATE INDEX fetch_attempt_run_id_idx ON letters.fetch_attempt (run_id);
CREATE INDEX fetch_attempt_document_file_id_idx ON letters.fetch_attempt (document_file_id);

-- The reminder calendar (W-033, W-034). Who receives reminders is the letters_reviewer role in config.
CREATE TABLE letters.expected (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         bigint NOT NULL REFERENCES letters.source (id),
    period_end        date NOT NULL,
    due_from          date NOT NULL,
    due_to            date NOT NULL,
    status            text NOT NULL DEFAULT 'awaiting',
    status_by         text,
    status_at         timestamptz,
    reminders         integer NOT NULL DEFAULT 0,
    last_reminded_at  timestamptz,
    document_id       bigint REFERENCES letters.document (id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT expected_source_period_key UNIQUE (source_id, period_end),
    CONSTRAINT expected_due_check CHECK (due_to >= due_from),
    CONSTRAINT expected_status_check CHECK (status IN ('awaiting', 'loaded', 'not_yet_published', 'skipped')),
    CONSTRAINT expected_loaded_check CHECK (status <> 'loaded' OR document_id IS NOT NULL),
    CONSTRAINT expected_reminders_check CHECK (reminders >= 0)
);
CREATE INDEX expected_status_due_idx ON letters.expected (status, due_from);
CREATE INDEX expected_document_id_idx ON letters.expected (document_id);
CREATE TRIGGER expected_stamp_status
    BEFORE UPDATE ON letters.expected
    FOR EACH ROW EXECUTE FUNCTION letters.stamp_status();

-- Provenance for every model output. The composite keys make the database refuse a run on a copy that may
-- not be machine-read (W-030, W-035), or one whose document does not match the copy.
CREATE TABLE letters.extraction_run (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_file_id  bigint NOT NULL,
    document_id       bigint NOT NULL,
    machine_read_ok   boolean NOT NULL DEFAULT true,
    task              text NOT NULL,
    run_id            bigint NOT NULL REFERENCES raw.run_log (id),
    model             text NOT NULL,
    prompt_version    text NOT NULL,
    status            text NOT NULL DEFAULT 'running',
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    dropped_mentions  integer NOT NULL DEFAULT 0,
    detail            jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT extraction_run_id_task_key UNIQUE (id, task),
    CONSTRAINT extraction_run_file_document_fkey FOREIGN KEY (document_file_id, document_id)
        REFERENCES letters.document_file (id, document_id),
    CONSTRAINT extraction_run_machine_read_fkey FOREIGN KEY (document_file_id, machine_read_ok)
        REFERENCES letters.document_file (id, machine_read_ok),
    CONSTRAINT extraction_run_machine_read_check CHECK (machine_read_ok),
    CONSTRAINT extraction_run_task_check CHECK (task IN ('mentions', 'topics', 'predictions', 'rating')),
    CONSTRAINT extraction_run_status_check CHECK (status IN ('running', 'ok', 'failed')),
    CONSTRAINT extraction_run_dropped_check CHECK (dropped_mentions >= 0)
);
CREATE INDEX extraction_run_document_task_idx ON letters.extraction_run (document_id, task, status);
CREATE INDEX extraction_run_document_file_id_idx ON letters.extraction_run (document_file_id);
CREATE INDEX extraction_run_run_id_idx ON letters.extraction_run (run_id);

-- Model outputs. Each row's `task` must match its run's task, enforced by the composite foreign key.
CREATE TABLE letters.mention (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id  bigint NOT NULL,
    task               text NOT NULL DEFAULT 'mentions',
    security_id        bigint NOT NULL REFERENCES core.security (id),
    stance             text NOT NULL,
    says_owned         boolean,
    summary            text NOT NULL,
    quote              text NOT NULL,
    page               integer,
    CONSTRAINT mention_run_fkey FOREIGN KEY (extraction_run_id, task)
        REFERENCES letters.extraction_run (id, task),
    CONSTRAINT mention_run_security_key UNIQUE (extraction_run_id, security_id),
    CONSTRAINT mention_task_check CHECK (task = 'mentions'),
    CONSTRAINT mention_stance_check CHECK (stance IN ('positive', 'negative', 'mixed', 'neutral')),
    CONSTRAINT mention_quote_check CHECK (length(quote) BETWEEN 1 AND 400),
    CONSTRAINT mention_page_check CHECK (page IS NULL OR page > 0)
);
CREATE INDEX mention_security_id_idx ON letters.mention (security_id);

CREATE TABLE letters.topic_mention (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id  bigint NOT NULL,
    task               text NOT NULL DEFAULT 'topics',
    topic_id           bigint NOT NULL REFERENCES core.topic (id),
    stance             text NOT NULL,
    summary            text NOT NULL,
    quote              text NOT NULL,
    page               integer,
    CONSTRAINT topic_mention_run_fkey FOREIGN KEY (extraction_run_id, task)
        REFERENCES letters.extraction_run (id, task),
    CONSTRAINT topic_mention_run_topic_key UNIQUE (extraction_run_id, topic_id),
    CONSTRAINT topic_mention_task_check CHECK (task = 'topics'),
    CONSTRAINT topic_mention_stance_check CHECK (stance IN ('positive', 'negative', 'mixed', 'neutral')),
    CONSTRAINT topic_mention_quote_check CHECK (length(quote) BETWEEN 1 AND 400),
    CONSTRAINT topic_mention_page_check CHECK (page IS NULL OR page > 0)
);
CREATE INDEX topic_mention_topic_id_idx ON letters.topic_mention (topic_id);

CREATE TABLE letters.topic_candidate (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id  bigint NOT NULL,
    task               text NOT NULL DEFAULT 'topics',
    label              text NOT NULL,
    quote              text NOT NULL,
    CONSTRAINT topic_candidate_run_fkey FOREIGN KEY (extraction_run_id, task)
        REFERENCES letters.extraction_run (id, task),
    CONSTRAINT topic_candidate_task_check CHECK (task = 'topics'),
    CONSTRAINT topic_candidate_quote_check CHECK (length(quote) BETWEEN 1 AND 400)
);
CREATE INDEX topic_candidate_run_idx ON letters.topic_candidate (extraction_run_id);

CREATE TABLE letters.candidate_decision (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id       bigint NOT NULL REFERENCES letters.topic_candidate (id),
    decision           text NOT NULL,
    resolved_topic_id  bigint REFERENCES core.topic (id),
    note               text,
    reviewed_by        text NOT NULL DEFAULT session_user,
    reviewed_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT candidate_decision_decision_check CHECK (decision IN ('approved', 'rejected')),
    CONSTRAINT candidate_decision_resolved_check
        CHECK (decision = 'rejected' OR resolved_topic_id IS NOT NULL)
);
CREATE INDEX candidate_decision_candidate_id_idx ON letters.candidate_decision (candidate_id);
CREATE INDEX candidate_decision_resolved_topic_id_idx ON letters.candidate_decision (resolved_topic_id);

-- An explicit call (W-037). Open until a prediction_score row resolves it. Code refuses to re-extract a
-- document's predictions once any of them is scored.
CREATE TABLE letters.prediction (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id   bigint NOT NULL,
    task                text NOT NULL DEFAULT 'predictions',
    security_id         bigint REFERENCES core.security (id),
    topic_id            bigint REFERENCES core.topic (id),
    direction           text NOT NULL,
    level               numeric,
    horizon_date        date,
    horizon_text        text,
    condition           text,
    confidence_wording  text,
    claim               text NOT NULL,
    quote               text NOT NULL,
    page                integer,
    CONSTRAINT prediction_run_fkey FOREIGN KEY (extraction_run_id, task)
        REFERENCES letters.extraction_run (id, task),
    CONSTRAINT prediction_task_check CHECK (task = 'predictions'),
    CONSTRAINT prediction_subject_check CHECK (num_nonnulls(security_id, topic_id) = 1),
    CONSTRAINT prediction_direction_check
        CHECK (direction IN ('up', 'down', 'above', 'below', 'happens', 'does_not_happen')),
    CONSTRAINT prediction_level_check CHECK ((direction IN ('above', 'below')) = (level IS NOT NULL)),
    CONSTRAINT prediction_quote_check CHECK (length(quote) BETWEEN 1 AND 400),
    CONSTRAINT prediction_page_check CHECK (page IS NULL OR page > 0)
);
CREATE INDEX prediction_run_idx ON letters.prediction (extraction_run_id);
CREATE INDEX prediction_security_id_idx ON letters.prediction (security_id);
CREATE INDEX prediction_topic_id_idx ON letters.prediction (topic_id);
CREATE INDEX prediction_horizon_date_idx ON letters.prediction (horizon_date);

CREATE TABLE letters.prediction_score (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prediction_id  bigint NOT NULL REFERENCES letters.prediction (id),
    outcome        text NOT NULL,
    note           text,
    reviewed_by    text NOT NULL DEFAULT session_user,
    reviewed_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT prediction_score_outcome_check
        CHECK (outcome IN ('right', 'wrong', 'partly_right', 'unresolvable'))
);
CREATE INDEX prediction_score_prediction_id_idx ON letters.prediction_score (prediction_id);

-- W-036: Insight and Clarity, 1 to 5. Predictions and Uniqueness are counted in views, not stored here.
CREATE TABLE letters.rating (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id  bigint NOT NULL,
    task               text NOT NULL DEFAULT 'rating',
    dimension          text NOT NULL,
    score              smallint NOT NULL,
    reason             text NOT NULL,
    quote              text NOT NULL,
    CONSTRAINT rating_run_fkey FOREIGN KEY (extraction_run_id, task)
        REFERENCES letters.extraction_run (id, task),
    CONSTRAINT rating_run_dimension_key UNIQUE (extraction_run_id, dimension),
    CONSTRAINT rating_task_check CHECK (task = 'rating'),
    CONSTRAINT rating_dimension_check CHECK (dimension IN ('insight', 'clarity')),
    CONSTRAINT rating_score_check CHECK (score BETWEEN 1 AND 5),
    CONSTRAINT rating_quote_check CHECK (length(quote) BETWEEN 1 AND 400)
);

-- The owner's quick verdicts (W-036): thumbs up is about_right; thumbs down is disagree, or too_high/too_low.
CREATE TABLE letters.rating_verdict (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rating_id    bigint NOT NULL REFERENCES letters.rating (id),
    verdict      text NOT NULL,
    note         text,
    reviewed_by  text NOT NULL DEFAULT session_user,
    reviewed_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT rating_verdict_verdict_check CHECK (verdict IN ('about_right', 'too_high', 'too_low', 'disagree'))
);
CREATE INDEX rating_verdict_rating_id_idx ON letters.rating_verdict (rating_id);

-- ---------------------------------------------------------------------------------------------------------
-- Grants (W-039). No DELETE anywhere; no access to meta. Column lists limit what each role may change.
-- ---------------------------------------------------------------------------------------------------------

GRANT USAGE ON SCHEMA raw, core, letters TO whales_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, core, letters TO whales_ingest;
GRANT INSERT ON raw.run_log, core.security, core.manager_tag, letters.document, letters.document_file,
    letters.fetch_attempt, letters.expected, letters.extraction_run, letters.mention, letters.topic_mention,
    letters.topic_candidate, letters.prediction, letters.rating TO whales_ingest;
GRANT UPDATE (status, finished_at, detail) ON raw.run_log TO whales_ingest;
GRANT UPDATE (status, finished_at, dropped_mentions, detail) ON letters.extraction_run TO whales_ingest;
GRANT UPDATE (status, reminders, last_reminded_at, document_id) ON letters.expected TO whales_ingest;
GRANT UPDATE (composite_figi, share_class_figi, figi, ticker, exch_code, name, security_type, mapping_source,
    mapped_at) ON core.security TO whales_ingest;

GRANT USAGE ON SCHEMA core, letters TO whales_reviewer;
GRANT SELECT ON ALL TABLES IN SCHEMA core, letters TO whales_reviewer;
GRANT INSERT (manager_tag_id, decision, note) ON core.tag_decision TO whales_reviewer;
GRANT INSERT (candidate_id, decision, resolved_topic_id, note) ON letters.candidate_decision TO whales_reviewer;
GRANT INSERT (prediction_id, outcome, note) ON letters.prediction_score TO whales_reviewer;
GRANT INSERT (rating_id, verdict, note) ON letters.rating_verdict TO whales_reviewer;
GRANT UPDATE (status) ON letters.expected TO whales_reviewer;

-- Future tables are readable by default; every write grant is given explicitly, migration by migration.
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, core, letters GRANT SELECT ON TABLES TO whales_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, letters GRANT SELECT ON TABLES TO whales_reviewer;
