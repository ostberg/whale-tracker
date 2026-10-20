-- 0003_reports: the weekly digest's memory and its theme view (W-054). Design: docs/REPORTS.md.
-- Applied by `whales db migrate` as whales_owner, in one transaction. Never edit once applied: write 0004.

CREATE SCHEMA reports;

-- One issue per day at most. The body is what was posted, or would have been; `sent` flips when the Teams
-- flow exists and the post succeeded.
CREATE TABLE reports.digest (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issued_on   date NOT NULL,
    subject     text NOT NULL,
    body        text NOT NULL,
    items       smallint NOT NULL,
    sent        boolean NOT NULL DEFAULT false,
    run_id      bigint REFERENCES raw.run_log (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT digest_issued_on_key UNIQUE (issued_on),
    CONSTRAINT digest_items_check CHECK (items >= 0)
);
CREATE INDEX digest_run_id_idx ON reports.digest (run_id);

-- What each issue reported, so a theme returns only once it has grown (docs/REPORTS.md, section 2).
CREATE TABLE reports.digest_item (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    digest_id  bigint NOT NULL REFERENCES reports.digest (id),
    kind       text NOT NULL,
    key        text NOT NULL,
    writers    smallint NOT NULL DEFAULT 0,
    score      numeric NOT NULL,
    detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT digest_item_kind_check
        CHECK (kind IN ('convergence', 'disagreement', 'calls_due', 'confident_miss')),
    CONSTRAINT digest_item_writers_check CHECK (writers >= 0)
);
CREATE INDEX digest_item_digest_id_idx ON reports.digest_item (digest_id);
CREATE INDEX digest_item_kind_key_idx ON reports.digest_item (kind, key);

-- Every theme mention, from the latest successful topics run per document: the controlled topics and the
-- model's candidate themes under one key, with the writer, the publication date, the source-type baseline
-- and whether this is the writer's first mention of the theme ever.
CREATE VIEW reports.theme_mention AS
WITH latest_run AS (
    SELECT DISTINCT ON (document_id) id, document_id
    FROM letters.extraction_run WHERE task = 'topics' AND status = 'ok'
    ORDER BY document_id, id DESC
), mentions AS (
    SELECT r.document_id, 'topic:' || t.slug AS theme, t.name AS label, tm.stance, tm.quote
    FROM letters.topic_mention tm
    JOIN latest_run r ON r.id = tm.extraction_run_id
    JOIN core.topic t ON t.id = tm.topic_id
    UNION ALL
    SELECT r.document_id, 'candidate:' || btrim(regexp_replace(lower(c.label), '[^a-z0-9]+', ' ', 'g')),
           c.label, NULL, c.quote
    FROM letters.topic_candidate c
    JOIN latest_run r ON r.id = c.extraction_run_id
), placed AS (
    SELECT m.theme, m.label, m.stance, m.quote, d.id AS document_id, d.title, d.published_on,
           d.kind AS document_kind, d.manager_id
    FROM mentions m
    JOIN letters.document d ON d.id = m.document_id
)
SELECT p.theme, p.label, p.stance, p.quote, p.document_id, p.title, p.published_on, p.document_kind,
       mg.slug AS manager, mg.name AS manager_name, mg.kind AS manager_kind, b.level AS baseline,
       NOT EXISTS (SELECT 1 FROM placed q
                   WHERE q.theme = p.theme AND q.manager_id = p.manager_id
                     AND (q.published_on < p.published_on
                          OR (q.published_on = p.published_on AND q.document_id < p.document_id))) AS first_mention
FROM placed p
JOIN core.manager mg ON mg.id = p.manager_id
LEFT JOIN core.trust_baseline b ON b.document_kind = p.document_kind AND b.manager_kind = mg.kind;

-- Grants (W-039): the job writes issues and items and flips `sent`; the reviewer reads.
GRANT USAGE ON SCHEMA reports TO whales_ingest, whales_reviewer;
GRANT SELECT ON ALL TABLES IN SCHEMA reports TO whales_ingest, whales_reviewer;
GRANT INSERT ON reports.digest, reports.digest_item TO whales_ingest;
GRANT UPDATE (sent) ON reports.digest TO whales_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA reports GRANT SELECT ON TABLES TO whales_ingest, whales_reviewer;
