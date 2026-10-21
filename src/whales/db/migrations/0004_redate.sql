-- 0004_redate: a document's date can be corrected from its source, and the extraction runs made under the
-- wrong date are marked superseded. Applied by `whales db migrate` as whales_owner, in one transaction.
-- Never edit once applied: write 0005.
--
-- Why (2026-10-21): the first Azure extraction run dated every Oaktree memo on the day it was collected
-- (published_on_basis 'first_seen'), because the memo's date sits in a <time> tag past the first 400
-- characters of visible text. Claims took their window_from from that date. `whales redate` fetches such
-- documents again, takes the date their markup or file states, and marks their successful predictions runs
-- superseded so the next extraction run redoes them; every view reads status = 'ok' only, so superseded
-- claims drop out of sight without a DELETE (W-039: ingest never deletes).

ALTER TABLE letters.extraction_run DROP CONSTRAINT extraction_run_status_check;
ALTER TABLE letters.extraction_run
    ADD CONSTRAINT extraction_run_status_check CHECK (status IN ('running', 'ok', 'failed', 'superseded'));

-- The collector's own derived columns (SCHEMA.md: "working columns"); never the permission columns.
GRANT UPDATE (title, kind, period_end, published_on, published_on_basis) ON letters.document TO whales_ingest;
