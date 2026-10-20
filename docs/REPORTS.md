# Proactive reports (W-054)

The owner's rule (2026-10-20): the chatbot is for pull; reports are push, and a report must be "high value or
short enough to warrant a quick read". The one that matters most: "similar themes investors and industry
experts are thinking about at the same time."

## 1. The weekly digest

One Teams post a week (W-034), **at most four items**, two lines each with links to the quotes. When nothing
clears the bar, the post still goes out and its subject line says so: `Whale Tracker, week of 2026-11-02:
nothing to report`. Silence is a result, not a failure.

Three kinds of item compete for the four slots, ranked by a score:

| Kind | What qualifies | Score |
|---|---|---|
| **Convergence** | A theme that three or more distinct writers raised within the window, counted by *publication* date. Shown with how many raised it for the first time in their own history, the stance split, the writers and the shortest quote | 2 per writer, plus 1 per first mention, plus 1 per writer whose source-type baseline is high or medium |
| **Disagreement** | A theme with credible writers (baseline high or medium) on both sides, positive and negative, within the window. Shown with each side's names and one quote per side | 3 per writer on the smaller side, plus 1 per writer |
| **Calls due** | Claims whose window closed (state due or proposed, W-048), with the proposed outcome and evidence where the job produced one. One item for the week, listing up to three; the rest are a count. This item is also the only place a person's input is asked for: one click per verdict | 2, plus 1 per call, plus 2 per proposal waiting for a verdict |
| **Confident miss** | A claim scored wrong in the last week that the writer had put at high confidence (W-051): the writer, the claim, the quote | 5 |

Themes are the controlled topics (`core.topic`) **and** the model's candidate themes (`letters.topic_candidate`),
grouped by their normalised label. The candidates are where "what are they all suddenly thinking about" lives,
since the controlled list is short by design; a candidate that keeps clustering is promoted to a topic by a
person (one click in a later version; editing `config/topics.toml` today).

## 2. Looking backwards, and forwards

Letters cluster at quarter-ends and themes take months to emerge, so (the owner, 2026-10-20) a document is
never analysed only against what came before it. Every week the digest recomputes every theme over a
rolling window of **26 weeks by publication date** (`WINDOW_WEEKS`), whatever order the documents arrived in.
A letter published in May and loaded in October joins May's cluster, and the cluster surfaces the week it
first reaches three writers.

To keep that from repeating itself, `reports.digest_item` remembers what each issue reported and with how many
writers. A theme comes back only when it has grown by at least two writers since it was last reported
(`GROWTH`); a confident miss or a week's calls-due item is never repeated. Rerunning the digest for a day
already issued is refused by the database (one issue per day).

"First mention" is a writer's own history: the first time that writer's documents carry the theme, over all
time, not within the window.

## 3. Industry experts

The clippings route (W-049) feeds the same extraction, so an expert's transcript or article raises the same
theme keys as a manager's letter and counts in the same cluster, with the source-type baseline shown
beside the name (a transcript starts medium-low; a tweet low). Nothing in the digest is specific to letters.

## 4. What exists and what waits

Built 2026-10-20 (`src/whales/reports/digest.py`, `whales digest`): the theme view
`reports.theme_mention`, the item builders, ranking, the cap, the subject line, the rendering, and the memory
tables `reports.digest` and `reports.digest_item` (migration 0003). The dry run prints the issue; `--apply`
records it. Verified by unit tests on constructed rows; the SQL runs against the live schema but no extraction
output exists yet, so the first real issue comes after the model deployment (W-052).

Waiting: the Teams Workflows flow (channel and flow owner, STATUS.md) for the actual post; promotion of a
candidate theme with one click; a monthly theme radar (mentions by theme by quarter, who moved first) once
there are two quarters of extraction output; said-versus-owned items in phase 3.

## 5. Holdings watch (firm side, phase 5)

The owner (2026-10-20): compare the company names the firm owns with what the writers say, "not useful for
new idea generation but definitely for continued due diligence, particularly if it goes against our
thesis". This is the highest-value short report, and it cannot be produced here: this database holds public
data only and never sees the firm's holdings (W-002). It is built in the Tamale repo as a firm-side consumer
reading the `api` views (W-005):

- `api.letter_mentions`: every company mention with stance, basis, quote, page, the writer and the writer's
  trust profile (the first `api` view, to be created with phase 5; `api.predictions` alongside it for claims
  about a company).
- A Tamale-side job joins them to APX holdings through the issuer rollup (D-137, so ADRs and share classes
  match) and posts its own section, short by construction: owned names a writer wrote about this week,
  negative and mixed stances first, confident claims against a name, and the writer's record on it.
- "Against our thesis": where the context layer holds the firm's stance on a name, the comparison is direct;
  where it does not, a negative view on a name the firm is long is the default flag.
- The holdings list never travels the other way: not into this database, and not into any model call made
  from here (D-127 for OpenFIGI applies in spirit to everything).

## 6. Manual letters: collection rounds, and when deep dives run (W-055)

The owner (2026-10-20): manual requests must be optimised "to minimise the task occurrence", and a
quarterly or monthly deeper report must not run "right before we add a bunch of documents".

- **Collection rounds, not reminders.** Manual sources (W-033) are never asked for one at a time. Twice a
  quarter the weekly digest carries one checklist below its items: round 1 at about week 6 after quarter-end
  (when most quarterly letters are out) lists every expected letter not yet loaded, in one line each; round 2
  at about week 10 lists the leftovers. Monthly and irregular sources fold into whichever round is next.
  A letter the automatic route caught drops off the list; one marked "not published" or "skipped" stops
  asking (`letters.expected.status`). The checklist does not count against the four-item cap.
- **Deep dives wait for the round to close.** The quarterly theme radar, and any monthly deeper report, runs
  only when the quarter's round 2 has closed, or when at least 80% of that quarter's expected letters are
  loaded, whichever comes first, and never before round 1. Letters that arrive later still enter the weekly
  digest's rolling window and the next radar; they do not trigger a rerun.
- Built with the reminder calendar (`letters.expected` is populated from each source's cadence and past
  publication lag); the digest then renders the round from it. Not built yet.

## 7. Example issue

```
Whale Tracker, week of 2026-11-09: 3 items

1. Convergence: Copper supply, 5 writers in 26 weeks, 3 for the first time; 4 positive, 1 negative
   Kopernik, Goehring & Rozencwajg, Crescat, Oaktree, Hoisington. "The copper deficit is now a 2027 story" (Crescat)
2. Disagreement: Private credit, 2 positive, 2 negative
   For: Apollo, Brookfield. Against: Oaktree, Howard Marks memo. "Something's gotta give" (Oaktree)
3. Calls due: 4 calls due for a verdict, 2 with a proposed outcome
   Greenlight: Brent below $100 by year-end (proposed: right, 92.1 USD/bbl on 2026-11-03); Smead: ...
```
