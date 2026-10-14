-- 0002_predictions: predictions as structured, linked claims (W-048). Design: docs/PREDICTIONS.md.
-- Replaces the W-037 prediction tables of 0001. They are empty (no extraction has run), so they are dropped
-- rather than altered; the first statement refuses to run if that is no longer true.
-- Applied by `whales db migrate` as whales_owner, in one transaction. Never edit once applied: write 0003.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM letters.prediction) THEN
        RAISE EXCEPTION 'letters.prediction holds rows; migration 0002 expects the W-037 tables to be empty';
    END IF;
    IF EXISTS (SELECT 1 FROM letters.mention) OR EXISTS (SELECT 1 FROM letters.topic_mention) THEN
        RAISE EXCEPTION 'letters.mention or letters.topic_mention holds rows; 0002 adds NOT NULL basis columns';
    END IF;
END
$$;

DROP TABLE letters.prediction_score;
DROP TABLE letters.prediction;

-- Clippings (W-049): a tweet, an article, a transcript or a note is a document like any other. Kinds name
-- the medium, so a writer's record can later be split by it; a new medium is one more code here.
ALTER TABLE letters.document DROP CONSTRAINT document_kind_check;
ALTER TABLE letters.document ADD CONSTRAINT document_kind_check CHECK (kind IN ('annual_letter',
    'quarterly_letter', 'memo', 'commentary', 'activist_letter', 'presentation', 'essay', 'filing_exhibit',
    'tweet', 'article', 'transcript', 'note', 'other'));

-- Trust profile, layer 2 (W-050): the basis of every model-extracted claim or stance, judged by the model
-- with a one-line note. data: cites specific numbers or observable facts; reasoning: argues a mechanism;
-- assertion: stated as a view with nothing shown. Counted per writer, never judged into a score.
ALTER TABLE letters.mention
    ADD COLUMN basis text NOT NULL,
    ADD COLUMN basis_note text,
    ADD CONSTRAINT mention_basis_check CHECK (basis IN ('data', 'reasoning', 'assertion')),
    ADD CONSTRAINT mention_basis_note_check CHECK (basis_note IS NULL OR length(basis_note) BETWEEN 1 AND 300);
ALTER TABLE letters.topic_mention
    ADD COLUMN basis text NOT NULL,
    ADD COLUMN basis_note text,
    ADD CONSTRAINT topic_mention_basis_check CHECK (basis IN ('data', 'reasoning', 'assertion')),
    ADD CONSTRAINT topic_mention_basis_note_check
        CHECK (basis_note IS NULL OR length(basis_note) BETWEEN 1 AND 300);

-- Trust profile, layer 1 (W-050): the trust a source type starts with, by document kind and author kind.
-- Loaded from config/trust.toml by `whales config sync`; read only by views at query time (W-051), so a
-- change here touches nothing stored.
CREATE TABLE core.trust_baseline (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_kind  text NOT NULL,
    manager_kind   text NOT NULL,
    level          text NOT NULL,
    reason         text NOT NULL,
    CONSTRAINT trust_baseline_key UNIQUE (document_kind, manager_kind),
    CONSTRAINT trust_baseline_document_kind_check CHECK (document_kind IN ('annual_letter', 'quarterly_letter',
        'memo', 'commentary', 'activist_letter', 'presentation', 'essay', 'filing_exhibit', 'tweet', 'article',
        'transcript', 'note', 'other')),
    CONSTRAINT trust_baseline_manager_kind_check
        CHECK (manager_kind IN ('manager', 'listed_vehicle', 'independent_writer', 'economist_or_strategist')),
    CONSTRAINT trust_baseline_level_check CHECK (level IN ('high', 'medium', 'medium_low', 'low', 'none'))
);

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
    confidence          text NOT NULL,
    basis               text NOT NULL,
    basis_note          text,
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
    CONSTRAINT prediction_confidence_check CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT prediction_basis_check CHECK (basis IN ('data', 'reasoning', 'assertion')),
    CONSTRAINT prediction_basis_note_check
        CHECK (basis_note IS NULL OR length(basis_note) BETWEEN 1 AND 300),
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
       p.window_from, p.window_to, p.timing, p.confidence, p.basis, p.claim,
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

-- The trust profile per writer and medium (W-050): the baseline (layer 1), basis counts (layer 2) and the
-- earned record (layer 3) side by side, never combined into one number. Asserted claims only, from the
-- latest successful predictions run per document. Trust is earned but quickly lost (W-051): a confident miss
-- (confidence high, scored wrong) within the last year raises trust_flag whatever the long-run hit rate.
CREATE VIEW letters.author_trust AS
WITH latest_run AS (
    SELECT DISTINCT ON (document_id) id, document_id
    FROM letters.extraction_run WHERE task = 'predictions' AND status = 'ok'
    ORDER BY document_id, id DESC
), claims AS (
    SELECT m.slug AS manager, m.name AS manager_name, m.kind AS manager_kind, d.kind AS document_kind,
           st.state, st.outcome, st.reviewed_at, st.confidence, st.basis, st.window_to
    FROM letters.prediction_state st
    JOIN latest_run r ON r.id = st.extraction_run_id
    JOIN letters.document d ON d.id = r.document_id
    JOIN core.manager m ON m.id = d.manager_id
    WHERE st.role = 'asserted'
), counted AS (
    SELECT c.manager, c.manager_name, c.manager_kind, c.document_kind,
           count(*) AS calls,
           count(*) FILTER (WHERE c.window_to IS NOT NULL) AS dated_calls,
           count(*) FILTER (WHERE c.basis = 'data') AS data_backed_calls,
           count(*) FILTER (WHERE c.basis = 'reasoning') AS reasoned_calls,
           count(*) FILTER (WHERE c.basis = 'assertion') AS asserted_calls,
           count(*) FILTER (WHERE c.state = 'scored' AND c.outcome = 'right') AS right_calls,
           count(*) FILTER (WHERE c.state = 'scored' AND c.outcome = 'partly_right') AS partly_right_calls,
           count(*) FILTER (WHERE c.state = 'scored' AND c.outcome = 'wrong') AS wrong_calls,
           count(*) FILTER (WHERE c.state = 'scored' AND c.outcome = 'unresolvable') AS unresolvable_calls,
           count(*) FILTER (WHERE c.state = 'void') AS void_calls,
           count(*) FILTER (WHERE c.state IN ('open', 'due', 'proposed', 'awaiting_premise')) AS open_calls,
           count(*) FILTER (WHERE c.state = 'scored' AND c.outcome = 'wrong' AND c.confidence = 'high')
               AS confident_misses,
           count(*) FILTER (WHERE c.state = 'scored' AND c.outcome = 'wrong' AND c.confidence = 'high'
                            AND c.reviewed_at >= now() - interval '1 year') AS recent_confident_misses,
           max(c.reviewed_at) FILTER (WHERE c.state = 'scored' AND c.outcome = 'wrong') AS last_miss_at
    FROM claims c
    GROUP BY c.manager, c.manager_name, c.manager_kind, c.document_kind
)
SELECT n.manager, n.manager_name, n.manager_kind, n.document_kind,
       b.level AS baseline, b.reason AS baseline_reason,
       n.calls, n.dated_calls, n.data_backed_calls, n.reasoned_calls, n.asserted_calls,
       n.right_calls, n.partly_right_calls, n.wrong_calls, n.unresolvable_calls, n.void_calls, n.open_calls,
       n.confident_misses, n.recent_confident_misses, n.last_miss_at,
       CASE WHEN n.recent_confident_misses > 0 THEN 'recent_confident_miss' END AS trust_flag
FROM counted n
LEFT JOIN core.trust_baseline b ON b.document_kind = n.document_kind AND b.manager_kind = n.manager_kind;

-- Each writer's record across media: author_trust summed. The baseline is per medium, so it is not here;
-- the flag carries over.
CREATE VIEW letters.track_record AS
SELECT manager, manager_name,
       sum(calls)::bigint AS calls,
       sum(dated_calls)::bigint AS dated_calls,
       sum(data_backed_calls)::bigint AS data_backed_calls,
       sum(reasoned_calls)::bigint AS reasoned_calls,
       sum(asserted_calls)::bigint AS asserted_calls,
       sum(right_calls)::bigint AS right_calls,
       sum(partly_right_calls)::bigint AS partly_right_calls,
       sum(wrong_calls)::bigint AS wrong_calls,
       sum(unresolvable_calls)::bigint AS unresolvable_calls,
       sum(void_calls)::bigint AS void_calls,
       sum(open_calls)::bigint AS open_calls,
       sum(confident_misses)::bigint AS confident_misses,
       sum(recent_confident_misses)::bigint AS recent_confident_misses,
       max(last_miss_at) AS last_miss_at,
       CASE WHEN sum(recent_confident_misses) > 0 THEN 'recent_confident_miss' END AS trust_flag
FROM letters.author_trust
GROUP BY manager, manager_name;

-- Grants (W-039): the job writes claims, links and proposals; a person writes verdicts. No DELETE, no UPDATE.
GRANT INSERT ON letters.prediction, letters.prediction_link, letters.prediction_check TO whales_ingest;
GRANT INSERT (prediction_id, check_id, outcome, note) ON letters.prediction_score TO whales_reviewer;
