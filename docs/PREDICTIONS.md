# Predictions as linked claims (W-048)

What a writer predicts, captured so that it can be checked later and turned into a track record. Decision
W-048 replaces the record shape of W-037; migration `0002_predictions.sql` holds the tables; the code is
`src/whales/predictions.py`. Written 2026-10-13 from the owner's earlier document/idea/tweet parser, whose
output looked like "Brent oil < $100, 12/31/2026, dependency: Iran peace".

Not everything here is deterministic, and that is deliberate. Rules do what rules can (vocabularies, dates,
links, the state of each claim); a model does the reading (turning prose into claims, and later reading
evidence to propose an outcome); a person gives one-click verdicts. The owner's words: "not everything will
be deterministic; this is where LLMs will really help".

## 1. The owner's two examples, parsed

*"Iran will hold out until after the midterm elections and then broker a peace deal which will cause brent oil
prices to drop to below $100 by the end of the year."* (a letter dated 2026-10-01)

| k | role | subject | metric | test | window | links |
|---|---|---|---|---|---|---|
| 1 | asserted | US-Iran peace deal | event | happens | 2026-11-04 to 2026-12-31, any time | |
| 2 | asserted | Brent crude | commodity_price | below 100 USD/bbl | by 2026-12-31, any time | caused by 1 |

*"If MSFT capex rises by over 30% next year, investors will punish the shares and cause the multiple to
compress to 18x."*

| k | role | subject | metric | test | window | links |
|---|---|---|---|---|---|---|
| 1 | **premise** | MSFT capex growth | capex | above 30 % y/y | 2027, judged at the end | |
| 2 | asserted | MSFT share price | price | down | during 2027 | premise 1 |
| 3 | asserted | MSFT forward P/E | valuation_multiple | at most 18x | during 2027 | premise 1; caused by 2 |

If Microsoft's capex grows 20%, claim 1 is scored wrong and claims 2 and 3 become **void**: the writer never
asserted them unconditionally, so they count neither for nor against. If capex grows 40% and the shares rise,
claim 2 is wrong. If the multiple does compress but capex did not jump, claim 3 is right for the wrong reason,
which the `causes` link lets a reader see. The same shapes are the unit tests in `tests/test_predictions.py`.

## 2. One claim per row

A claim is one testable thing. A sentence with two tests becomes two rows. Each row holds:

| Field | Holds | Vocabulary |
|---|---|---|
| `role` | what the writer asserts, or a premise the writer only supposes ("if capex rises...") | asserted, premise |
| `subject` | a short canonical name of what is measured | free text, at most 200 characters; the prompt carries a list of standard names (Brent crude, WTI crude, gold, US 10-year Treasury yield, Fed funds rate, US CPI, S&P 500, US dollar index...) so the same thing is spelled the same way |
| `metric` | the kind of quantity, which also decides how the claim is checked (section 4) | price, valuation_multiple, revenue, earnings, margin, capex, capital_return, volume, interest_rate, credit_spread, inflation, gdp, employment, fx, commodity_price, event, other |
| `security_id`, `topic_id` | joins to `core.security` (by ticker) and `core.topic` (by slug), each optional | a ticker not in `core.security` leaves the claim unlinked and is noted, never guessed; a topic not in the list is dropped to null and noted |
| `comparator`, `threshold`, `unit` | the test | up, down, above, below, at_least, at_most, happens, does_not_happen; a threshold is required for above, below, at_least and at_most and forbidden otherwise |
| `relative_to` | the benchmark of a relative call ("will outperform the S&P 500") | free text, optional |
| `window_from`, `window_to`, `timing` | when the test applies. `any_time`: met if true at any point in the window ("below $100 by year-end"). `at_end`: judged at `window_to` ("capex growth for 2027") | dates; `window_to` null means the writer gave no deadline |
| `horizon_text`, `confidence_wording` | the writer's own words ("by the end of the year"; "will", "we expect", "could") | free text |
| `confidence` | how firmly the writer puts it, judged from the wording: `high` (will, we expect), `medium` (likely, should), `low` (could, might). Used for calibration and for confident misses (W-051, section 7) | high, medium, low |
| `basis`, `basis_note` | what the writer shows for the claim (W-050, section 7): `data` cites specific numbers or observable facts; `reasoning` argues a mechanism without hard numbers; `assertion` states a view with nothing shown. The note says what was shown ("cites Q2 capex of $24bn and the FY guide") | counted per writer in the track record, never turned into a judged score |
| `claim`, `quote`, `page` | one plain sentence; the exact words, at most 400 characters (W-015, W-019); the page | |

Rules for the model, which the prompt will carry:

- Only the writer's own calls. Consensus, "the market expects", and calls the writer attributes to others are
  not extracted. (A letter that disputes a consensus call yields the writer's own call.)
- No deadline, no guess: `window_to` is null. "Next year" and "by year-end" are read from the letter's date,
  which is reading, not guessing. A claim whose `window_to` is before the letter's date is refused.
- A condition becomes a premise row linked to the claims that depend on it, never free text. A premise that
  nothing depends on is refused.
- Canonical subjects from the list where one fits; otherwise the shortest unambiguous name.

Why no table of observables: a canonical subject plus a metric code groups the same thing across writers well
enough for a digest ("who else called Brent below $100"), and the model does fuzzy matching better than a
register would. If grouping by name proves insufficient, a `core.observable` table can be added later; nothing
in the rows would change.

## 3. Links: premises and causes

`letters.prediction_link` ties claims of one letter together:

- **premise_of**: the from-claim is a premise (role `premise`); the to-claim is conditional on it. A premise
  scored **wrong** makes its dependants **void**. A premise scored right or partly right leaves them live. A
  premise scored unresolvable leaves them live too, flagged in the digest, because the writer's call still
  stands on its own words.
- **causes**: both ends are asserted; the writer says the first brings about the second. This is the writer's
  story, so "right outcome, wrong reason" can be seen later. It never changes scoring.

Links stay within one letter and one extraction run; composite keys enforce that, and that the from-claim's
role matches the kind. Chains may be any length ("peace deal → Brent < $100 → airline margins up"); a cycle is
refused. Links across letters ("as we said last quarter") are not modelled: the track record view shows a
writer's repeated calls side by side instead.

## 4. From open to scored: who decides what

The state of a claim is derived by the view `letters.prediction_state`, never stored:

| State | Means |
|---|---|
| open | the window has not closed, or there is no deadline (such a claim is never scored by guesswork) |
| due | the window has closed and nobody has looked |
| awaiting_premise | due, but a premise is still unscored |
| proposed | the job has proposed an outcome with evidence; a person has not yet decided |
| void | a premise was scored wrong |
| scored | a person decided: right, wrong, partly_right or unresolvable |

Who does what:

1. **The job proposes.** When a claim is due, the job writes a `letters.prediction_check` with the method,
   the source, what was observed and when, and a proposed outcome. The method follows the metric
   (`predictions.CHECK_METHOD`): `data` for public series (commodity prices, rates, inflation, GDP,
   employment, FX: FRED and similar, free), `price` for securities (phase 6, once a price source exists),
   `filing` for a company's own numbers (revenue, earnings, margin, capex, capital return), `model` for
   everything that needs judgement (events, multiples, volumes, "other"). For `model`, the model reads later
   evidence it is given (a later letter by the same writer, a filing, a news item in a clipping) and proposes
   an outcome with its reason. None of these checkers is built yet; the table and the view are.
2. **A person confirms.** The Teams digest (W-034) lists due and proposed claims with the evidence; one click
   inserts a `letters.prediction_score` as `whales_reviewer`, optionally naming the check it confirms or
   overrides. "Unresolvable" is a fine answer. There are no scoring sheets, and a claim with no deadline
   never asks for a verdict (the owner's standing preference for a light workload).
3. **Nothing is re-extracted after a verdict.** `predictions.refuse_if_scored` stops a re-run on a document
   that has any scored claim, so scores never point at superseded rows (W-039).

`letters.track_record` counts each writer's asserted claims from the latest successful predictions run per
document: right, partly right, wrong, unresolvable, void and open, plus how many carried a deadline (the
"Predictions" count of the rating, W-036). Premises are excluded. Consumers will see this through an `api`
view in phase 5, by manager slug.

Open policy question for the owner: whether `data` and `price` checks may count as scored after a grace
period with no verdict. Today a person always confirms.

## 5. The extraction contract

The model receives the letter's text, its date, the topic slugs and the canonical subject list, and returns
JSON in this shape (`predictions.CONTRACT`; `PROMPT_VERSION = predictions-v2`):

```
{"predictions": [
  {"k": 1, "role": "asserted | premise",
   "subject": "...", "metric": "...", "ticker": "MSFT or null", "topic": "slug or null",
   "comparator": "...", "threshold": 100 or null, "unit": "USD/bbl or null", "relative_to": null,
   "window_from": "YYYY-MM-DD or null", "window_to": "YYYY-MM-DD or null", "timing": "any_time | at_end",
   "horizon_text": "...", "confidence_wording": "...", "confidence": "high | medium | low",
   "basis": "data | reasoning | assertion", "basis_note": "what the writer shows, or null",
   "claim": "one plain sentence", "quote": "the writer's words, at most 400 characters", "page": 3,
   "premises": [2], "caused_by": [3]}
]}
```

`predictions.parse` checks every field against the vocabularies above, the dates against the letter's date,
and the links (existence, roles, self-reference, cycles). It reports every problem at once and nothing is
stored unless all of it is valid; an unknown topic is the one soft case (dropped and noted). `predictions.store`
writes the claims and links in the caller's transaction and returns each `k`'s row id. The model has no
tools and sees only text (AGENTS.md, security requirements); instructions inside a letter never change the
contract.

The runner is `src/whales/extract.py` (`whales extract predictions`). It takes the text of each copy that may
be machine-read (inbox files, or re-fetched by URL; PDFs carry `[page N]` markers so the model can cite
pages), sends the system prompt in `extract.SYSTEM_TEMPLATE` with the canonical subjects, the topic slugs and
the contract, and stores a checked reply under one `letters.extraction_run` with the deployment asked for,
the model that answered, token usage, the text's hash and whether it was truncated (150,000 characters). A
reply that fails the contract goes back once with the problems; if the second reply still fails, the claims
that break the contract are dropped, each with a note saying why, and the rest is stored (`parse(...,
salvage=True)`). The first Azure run (2026-10-21) lost eight letters to one or two claims each: a threshold
that was a phrase ("above GDP growth"), a null confidence, "at_end" with no deadline, a link to the wrong
role. Those are now rules in the prompt (`predictions-v2`), and the salvage keeps the letter when the model
still slips. Only a reply with no usable shape fails the document. Model calls go through
`src/whales/llm.py` only (W-052): an in-tenant endpoint on an approved host, an Entra token, JSON replies.

## 6. Where claims come from

**Letters** (now): every `letters.document` that may be machine-read gets a predictions run alongside
mentions, topics and the rating.

**Clippings** (W-049; direction confirmed by the owner on 2026-10-13, loader not yet built): a third inbox
route beside `public-websites` and `shared-by-manager`. The folder exists and files can be dropped now; the
loader picks them up once it is built.

```
Whale Tracker Inbox/clippings/<author-slug>/anything.txt | .md | .pdf
```

- A text or Markdown file may start with a header, one item per line, then a blank line, then the text:

  ```
  kind: tweet | article | transcript | note
  url: https://...
  date: 2026-10-13
  title: ...
  note: reading guidance for the model
  ```

  Every line is optional. `kind` names the medium and becomes `letters.document.kind`; without it the loader
  takes `tweet` from an X or Twitter URL, else `note`. `date` is the publication date; without it the loader
  uses the file's own date and records that basis, as it does for PDFs. The note is the owner's reading
  guidance ("skeptical of the demand claim; focus on the capex comment"), passed to the model as context, as
  the financial-graph project did with its context notes; it guides, never overrides the contract.
- The author is a `core.manager` in `config/managers.toml` (usually kind `independent_writer` or
  `economist_or_strategist`) with one source `<slug>-clippings` in `config/letter_sources.toml`; `whales
  inbox scan` prints the TOML to paste for an author it does not know. Config stays the one home for authors
  and sources (W-040).
- Its claims join the author's track record like a letter's, and the kind lets the record be split by medium
  later ("his tweets against his letters").
- Collection is by hand only. X's terms forbid automated collection, so a tweet is copied by a person; whether
  model extraction on a hand-clipped post sits within the internal-use position (W-043) is for the owner to
  confirm. A clipped article by a third party is a tier-3 source and carries that source's terms.
- **Built for later inputs** (the owner: "plan for flexibility"). The route is medium-agnostic: anything
  someone else reduces to a text file (a podcast transcript, an email saved as text, an interview) enters the
  same way, under the same author and source, and gets the same extraction. A new medium is one more `kind`
  code (a constraint re-add, convention 5 in SCHEMA.md) and at most a file reader; the claims model, the
  contract and the track record do not change. This project still does no transcription, mail reading or
  scraping of its own.

**Out of scope, on purpose** (the owner: "don't want to get caught going down a rabbit hole and never
finishing"): a browser extension, automated collection from X or any feed, podcasts and audio, email
ingestion, chart extraction, and a graph user interface. Each is a project of its own; none is needed for the
track record.

## 7. Trust profile (W-050)

The owner asked (2026-10-14) for "some sort of trust score (and/or more context/evaluation if something is
pure opinion, well researched thesis, observable facts, etc), even roughly by source type". Trust is three
things here, shown side by side like the rating (W-036: no overall score), because a single number would be
the source-type baseline in disguise until resolved calls accumulate.

| Layer | What | Who decides | Standing |
|---|---|---|---|
| 1. Baseline, by source type | the trust a source type starts with before any of its claims has been checked: a rough level from `document.kind` and `manager.kind` (table below), which layers 2 and 3 then move | the owner, in `config/trust.toml` | built: `core.trust_baseline`, joined at read time by `letters.author_trust` |
| 2. Basis of each claim | `data`, `reasoning` or `assertion` with a one-line note, on every prediction, company mention and topic mention; counted per writer ("60% of calls data-backed") | the model, beside the quote it must already give | built: columns in 0002, a contract field, counts in `letters.track_record` |
| 3. Earned | the track record (hit rate by subject and horizon); calibration (do "will" calls land more often than "could" calls, from `confidence_wording`); skin in the game (`says_owned` on mentions, and the said-versus-owned join of W-017 in phase 3) | computed | the track record is built; the rest once calls resolve |
| 4. The owner's view (optional) | a dated tag facet `trust` (trusted, watch, skeptical) with evidence, ratified like any tag (W-038) | the owner | proposed |

The layer-1 baselines, accepted by the owner on 2026-10-14 and held in `config/trust.toml` (one rule per row
here, plus `other` at medium-low until someone sets the document's kind):

| Source type (document kind, author kind) | Baseline | Why |
|---|---|---|
| A manager's own letter, memo or presentation | high | money and reputation at stake; signed and dated; checkable against the 13F |
| Activist letter, 13D exhibit | medium | facts usually checkable, framing partisan by design |
| Strategist or economist commentary (Apollo, GMO, Hoisington) | medium | researched, but sells a view and holds no position |
| Independent writer (Lyn Alden) | medium | researched, no fiduciary stake |
| Transcript (interview, podcast) | medium-low | spoken, unedited, led by the host |
| Third-party article | medium-low | second-hand; the reporter's framing |
| Tweet or thread | low | fast and unedited, unless it links data |
| The owner's own note | not scored | |

Two rules the owner set on 2026-10-14 (W-051):

- **Baselines never touch stored data.** They live in `core.trust_baseline`, loaded from `config/trust.toml`
  by `whales config sync`, and are joined only at query time by `letters.author_trust`. Changing a level
  changes the next query and nothing else: no row is re-extracted, re-scored or rewritten, and the history of
  claims and verdicts is untouched. `whales config check` refuses a (document kind, author kind) pair that is
  covered twice or not at all, so a new document kind cannot slip through without a level.
- **Trust is earned but quickly lost.** Each claim carries the writer's `confidence` (high, medium, low,
  judged from the wording). `letters.author_trust` counts confident misses (confidence high, scored wrong)
  separately and raises `trust_flag = recent_confident_miss` for any writer with one in the last year,
  whatever the long-run hit rate. Building a record takes many dated, scored calls; losing it takes one
  confident miss. No decay formula is applied until there is data to fit one; the counts are shown as they
  are.

`letters.author_trust` has one row per writer and medium (a manager's letters and the same manager's tweets
are separate rows with separate baselines): the baseline and its reason; calls and dated calls; data-backed,
reasoned and asserted counts; right, partly right, wrong, unresolvable, void and open; confident misses,
recent confident misses, the last miss date and the flag. `letters.track_record` sums it per writer. A judged
"Evidence" score per letter stays out (the owner dropped it in W-036); the basis counts carry the same
information without a scoring sheet.

## 8. What was taken from the owner's financial-graph project

The archive `AI Projects/financial-graph.zip` (a personal FastAPI, SQLAlchemy and React project run on Cloud
Run, with a Chrome clipper extension) was read for ideas on 2026-10-13. Nothing from it was copied into this
repo. The archive holds a `.env` with API keys, a SQLite database and third-party research PDFs; it stays
where it is.

Taken:
- predictions as rows with the raw deadline text and a machine date, a status lifecycle, and a confirm step
  before a row counts (its `PENDING / TRUE / FALSE / MIXED / EXPIRED` became open, right, wrong, partly right,
  unresolvable; `EXPIRED` became "due", which asks for a verdict instead of expiring);
- reading-guidance notes at clip time, passed to the model as context;
- the Chrome extension's lesson that tweets have to be captured by a person, not an API.

New here: premises and void outcomes; causal links; proposed outcomes with evidence; timing (any time versus
at the end); the metric vocabulary that decides how a claim is checked.

Noted for later, not built:
- its company-to-topic edges with a stance (benefits, at risk, linked) are the "topic or technology → eventual
  beneficiary" chains the owner described. Here that becomes a `stance` column on `core.topic_security` in
  phase 3, with the reason and the source letter, so the chain can be followed from a letter's topic view to
  the names that benefit;
- its "historical precedent" passage tag ("when X happened in 1998, Y followed") pairs well with predictions
  and could become a third extraction task.

Not taken, and why: the stack (three model vendors through API keys, PyMuPDF, SQLAlchemy, Cloud Run, a
SQLite development mode) conflicts with the in-tenant model rule, the small hash-pinned dependency set and the
Azure-only runtime (W-002, W-022, W-042); its delete endpoints and in-place edits conflict with the insert-only
decision rule (W-039).

## 9. For the owner

1. W-049 (clippings) confirmed on 2026-10-13 as direction, build later. Still open: X's terms for model
   use on hand-clipped posts.
2. Confirm the canonical subject list before the prompt is written (section 2).
3. Decide whether `data` and `price` checks may auto-score after a grace period (section 4).
4. Migration 0002 is applied by the admin job once IT clears Azure; `pytest -m live` then exercises the state
   view on the MSFT example.
5. Baselines accepted on 2026-10-14 and held in `config/trust.toml`; edit that file to change one.
6. A chat-model deployment on an approved in-tenant resource, and the Cognitive Services OpenAI User role
   for `id-whales-ingest` and your own account; then `whales model check`.
