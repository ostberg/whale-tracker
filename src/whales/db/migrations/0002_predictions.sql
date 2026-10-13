-- 0002_predictions: predictions as structured, linked claims (W-048). Design: docs/PREDICTIONS.md.
-- Replaces the W-037 prediction tables of 0001. They are empty (no extraction has run), so they are dropped
-- rather than altered; the first statement refuses to run if that is no longer true.
-- Applied by `whales db migrate` as whales_owner, in one transaction. Never edit once applied: write 0003.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM letters.prediction) THEN
        RAISE EXCEPTION 'letters.prediction holds rows; migration 0002 expects the W-037 tables to be empty';
    END IF;
END
$$;

DROP TABLE letters.prediction_score;
DROP TABLE letters.prediction;

-- A hand-clipped tweet, article or note (W-049) is a document like any other.
ALTER TABLE letters.document DROP CONSTRAINT document_kind_check;
ALTER TABLE letters.document ADD CONSTRAINT document_kind_check CHECK (kind IN ('annual_letter',
    'quarterly_letter', 'memo', 'commentary', 'activist_letter', 'presentation', 'essay', 'filing_exhibit',
    'clipping', 'other'));

-- One testable claim. `role` separates what the writer asserts from a premise the writer only supposes
-- ("if capex rises 30%..."); premises never count in a track record. `ordinal` is the model's own numbering
-- within the run, which the links use before ids exist. What each column may hold: docs/PREDICTIONS.md.
CREATE TABLE letters.prediction (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id   bigint NOT NULL,
    task                text NOT NULL DEFAULT 'predictions',
    ordinal             smallint NOT NULL,
    role                text NOT NULL DEFAULT 'asserted',
    subject             text NOT NULL,
    metric              text NOT NULL,
    security_id         bigint REFERENCES core.security (id),
    topic_id            bigint REFERENCES core.topic (id),
    comparator          text NOT NULL,
    threshold           numeric,
    unit                text,
    relative_to         text,
    window_from         date,
    window_to           date,
    timing              text NOT NULL DEFAULT 'any_time',
    horizon_text        text,
    confidence_wording  text,
    claim               text NOT NULL,
    quote               text NOT NULL,
    page                integer,
    CONSTRAINT prediction_run_fkey FOREIGN KEY (extraction_run_id, task)
        REFERENCES letters.extraction_run (id, task),
    CONSTRAINT prediction_run_ordinal_key UNIQUE (extraction_run_id, ordinal),
    CONSTRAINT prediction_id_run_key UNIQUE (id, extraction_run_id),
    CONSTRAINT prediction_id_role_key UNIQUE (id, role),
    CONSTRAINT prediction_task_check CHECK (task = 'predictions'),
    CONSTRAINT prediction_ordinal_check CHECK (ordinal > 0),
    CONSTRAINT prediction_role_check CHECK (role IN ('asserted', 'premise')),
    CONSTRAINT prediction_subject_check CHECK (length(subject) BETWEEN 1 AND 200),
    CONSTRAINT prediction_metric_check CHECK (metric IN ('price', 'valuation_multiple', 'revenue', 'earnings',
        'margin', 'capex', 'capital_return', 'volume', 'interest_rate', 'credit_spread', 'inflation', 'gdp',
        'employment', 'fx', 'commodity_price', 'event', 'other')),
    CONSTRAINT prediction_comparator_check CHECK (comparator IN ('up', 'down', 'above', 'below', 'at_least',
        'at_most', 'happens', 'does_not_happen')),
    CONSTRAINT prediction_threshold_check
        CHECK ((comparator IN ('above', 'below', 'at_least', 'at_most')) = (threshold IS NOT NULL)),
    CONSTRAINT prediction_window_check
        CHECK (window_from IS NULL OR window_to IS NULL OR window_to >= window_from),
    CONSTRAINT prediction_timing_check CHECK (timing IN ('any_time', 'at_end')),
    CONSTRAINT prediction_at_end_check CHECK (timing = 'any_time' OR window_to IS NOT NULL),
    CONSTRAINT prediction_quote_check CHECK (length(quote) BETWEEN 1 AND 400),
    CONSTRAINT prediction_page_check CHECK (page IS NULL OR page > 0)
);
CREATE INDEX prediction_run_idx ON letters.prediction (extraction_run_id);
CREATE INDEX prediction_security_id_idx ON letters.prediction (security_id);
CREATE INDEX prediction_topic_id_idx ON letters.prediction (topic_id);
CREATE INDEX prediction_window_to_idx ON letters.prediction (window_to);

-- How claims in one run depend on each other. `premise_of`: `from` is a premise (not asserted) that `to` is
-- conditional on; if the premise fails, `to` is void. `causes`: the writer says asserted `from` brings about
-- asserted `to`. The composite keys keep both ends in one run and make the roles match the kind.
CREATE TABLE letters.prediction_link (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_run_id  bigint NOT NULL,
    from_id            bigint NOT NULL,
    from_role          text NOT NULL,
    to_id              bigint NOT NULL,
    kind               text NOT NULL,
    CONSTRAINT prediction_link_from_fkey FOREIGN KEY (from_id, extraction_run_id)
        REFERENCES letters.prediction (id, extraction_run_id),
    CONSTRAINT prediction_link_from_role_fkey FOREIGN KEY (from_id, from_role)
        REFERENCES letters.prediction (id, role),
    CONSTRAINT prediction_link_to_fkey FOREIGN KEY (to_id, extraction_run_id)
        REFERENCES letters.prediction (id, extraction_run_id),
    CONSTRAINT prediction_link_key UNIQUE (from_id, to_id, kind),
    CONSTRAINT prediction_link_kind_check CHECK (kind IN ('premise_of', 'causes')),
    CONSTRAINT prediction_link_role_check CHECK ((kind = 'premise_of' AND from_role = 'premise')
        OR (kind = 'causes' AND from_role = 'asserted')),
    CONSTRAINT prediction_link_self_check CHECK (from_id <> to_id)
);
CREATE INDEX prediction_link_from_id_idx ON letters.prediction_link (from_id);
CREATE INDEX prediction_link_to_id_idx ON letters.prediction_link (to_id);
CREATE INDEX prediction_link_run_idx ON letters.prediction_link (extraction_run_id);

-- A proposed outcome, written by the job: from a data series, a price, a filing, or a model's reading of
-- later evidence. The evidence is always stated. A person confirms or overrides it in prediction_score.
CREATE TABLE letters.prediction_check (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prediction_id     bigint NOT NULL REFERENCES letters.prediction (id),
    run_id            bigint NOT NULL REFERENCES raw.run_log (id),
    method            text NOT NULL,
    source            text NOT NULL,
    observed          text NOT NULL,
    as_of             date NOT NULL,
    proposed_outcome  text NOT NULL,
    reason            text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL DEFAULT session_user,
    CONSTRAINT prediction_check_id_prediction_key UNIQUE (id, prediction_id),
    CONSTRAINT prediction_check_method_check CHECK (method IN ('data', 'price', 'filing', 'model')),
    CONSTRAINT prediction_check_outcome_check
        CHECK (proposed_outcome IN ('right', 'wrong', 'partly_right', 'unresolvable'))
);
CREATE INDEX prediction_check_prediction_id_idx ON letters.prediction_check (prediction_id);
CREATE INDEX prediction_check_run_id_idx ON letters.prediction_check (run_id);

-- A person's verdict: insert-only, stamped by the database. `check_id` names the proposal it confirms or
-- overrides, if any; the composite key makes that a proposal for the same prediction.
CREATE TABLE letters.prediction_score (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prediction_id  bigint NOT NULL REFERENCES letters.prediction (id),
    check_id       bigint,
    outcome        text NOT NULL,
    note           text,
    reviewed_by    text NOT NULL DEFAULT session_user,
    reviewed_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT prediction_score_check_fkey FOREIGN KEY (check_id, prediction_id)
        REFERENCES letters.prediction_check (id, prediction_id),
    CONSTRAINT prediction_score_outcome_check
        CHECK (outcome IN ('right', 'wrong', 'partly_right', 'unresolvable'))
);
CREATE INDEX prediction_score_prediction_id_idx ON letters.prediction_score (prediction_id);
CREATE INDEX prediction_score_check_id_idx ON letters.prediction_score (check_id);

-- Where each claim stands. Derived, never stored: scored (a person decided), void (a premise was scored
-- wrong), proposed (a check awaits a verdict), open (the window has not closed, or there is none),
-- awaiting_premise (due, but a premise is unscored), due. A claim with no window is never scored by guesswork.
CREATE VIEW letters.prediction_state AS
WITH latest_score AS (
    SELECT DISTINCT ON (prediction_id) prediction_id, outcome, reviewed_by, reviewed_at
    FROM letters.prediction_score ORDER BY prediction_id, id DESC
), latest_check AS (
    SELECT DISTINCT ON (prediction_id) prediction_id, proposed_outcome, method, observed, as_of
    FROM letters.prediction_check ORDER BY prediction_id, id DESC
), premises AS (
    SELECT l.to_id AS prediction_id,
           bool_or(s.outcome = 'wrong') AS any_failed,
           bool_or(s.outcome IS NULL) AS any_unscored
    FROM letters.prediction_link l
    LEFT JOIN latest_score s ON s.prediction_id = l.from_id
    WHERE l.kind = 'premise_of'
    GROUP BY l.to_id
)
SELECT p.id, p.extraction_run_id, p.ordinal, p.role, p.subject, p.metric, p.comparator, p.threshold, p.unit,
       p.window_from, p.window_to, p.timing, p.claim,
       s.outcome, s.reviewed_by, s.reviewed_at,
       c.proposed_outcome, c.method AS check_method, c.observed AS check_observed, c.as_of AS check_as_of,
       CASE
           WHEN s.outcome IS NOT NULL THEN 'scored'
           WHEN coalesce(pr.any_failed, false) THEN 'void'
           WHEN c.proposed_outcome IS NOT NULL THEN 'proposed'
           WHEN p.window_to IS NULL OR p.window_to >= current_date THEN 'open'
           WHEN coalesce(pr.any_unscored, false) THEN 'awaiting_premise'
           ELSE 'due'
       END AS state
FROM letters.prediction p
LEFT JOIN latest_score s ON s.prediction_id = p.id
LEFT JOIN latest_check c ON c.prediction_id = p.id
LEFT JOIN premises pr ON pr.prediction_id = p.id;

-- Each writer's record on asserted claims, from the latest successful predictions run per document.
CREATE VIEW letters.track_record AS
WITH latest_run AS (
    SELECT DISTINCT ON (document_id) id, document_id
    FROM letters.extraction_run WHERE task = 'predictions' AND status = 'ok'
    ORDER BY document_id, id DESC
)
SELECT m.slug AS manager, m.name AS manager_name,
       count(*) FILTER (WHERE st.state = 'scored' AND st.outcome = 'right') AS right_calls,
       count(*) FILTER (WHERE st.state = 'scored' AND st.outcome = 'partly_right') AS partly_right_calls,
       count(*) FILTER (WHERE st.state = 'scored' AND st.outcome = 'wrong') AS wrong_calls,
       count(*) FILTER (WHERE st.state = 'scored' AND st.outcome = 'unresolvable') AS unresolvable_calls,
       count(*) FILTER (WHERE st.state = 'void') AS void_calls,
       count(*) FILTER (WHERE st.state IN ('open', 'due', 'proposed', 'awaiting_premise')) AS open_calls,
       count(*) FILTER (WHERE st.window_to IS NOT NULL) AS dated_calls
FROM letters.prediction_state st
JOIN latest_run r ON r.id = st.extraction_run_id
JOIN letters.document d ON d.id = r.document_id
JOIN core.manager m ON m.id = d.manager_id
WHERE st.role = 'asserted'
GROUP BY m.slug, m.name;

-- Grants (W-039): the job writes claims, links and proposals; a person writes verdicts. No DELETE, no UPDATE.
GRANT INSERT ON letters.prediction, letters.prediction_link, letters.prediction_check TO whales_ingest;
GRANT INSERT (prediction_id, check_id, outcome, note) ON letters.prediction_score TO whales_reviewer;
