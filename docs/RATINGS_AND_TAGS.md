# Letter ratings and manager tags (draft for the owner to edit)

The owner's idea of 2026-10-08: a model-provided rating on each ingested letter, and loose tags to classify
the managers. Decisions W-036 to W-038. When built, the rubric and the tag list move into `config/`, and this
file keeps only the reasoning.

Both are model extraction, so the use restrictions in W-035 apply: no rating, prediction extraction or
embedding for a source whose terms forbid automated text analysis.

## 1. Letter rating (W-036, simplified 2026-10-08)

The owner asked for this to stay simple: scoring many letters by hand on five dimensions is too much. So the
model judges only two things, two more are counted, and the person's part is a quick verdict.

**Judged by the model**, each a whole number from 1 to 5 against these anchors, with a one-sentence reason and
a short supporting quote (W-019, W-015):

| Dimension | Asks | 1 | 3 | 5 |
|---|---|---|---|---|
| **Insight** | Does it argue something the reader probably hasn't heard, and say where it parts from consensus? | Restates consensus or the news | One or two original angles | A clearly different, well-argued view |
| **Clarity** | Is it well written: structured, concise, readable? | Hard to follow, padded | Adequate | A pleasure to read; no wasted words |

**Counted, not judged:**
- **Predictions:** the number of explicit calls with a stated horizon, taken from the prediction records (W-037).
- **Uniqueness:** how far the letter's content sits from the other letters of the same quarter, measured with
  text embeddings. A model cannot know what everyone else wrote; this can.

Every rating records the model, the prompt version and the date, so it can be re-run and compared.

**The person's part.**
- **Calibration once:** the owner (later the `letters_reviewer`) sees 10 rated letters while reading them anyway,
  and marks each rating "about right", "too high" or "too low". The prompt is tuned until most are "about right".
  There are no scoring sheets.
- **After that:** a thumbs up or down on any rating in the digest or the Research Assistant. Disagreements feed
  the next prompt revision, and the 10 are re-run before any change of model.

**Not scored:** Evidence and Candor (dropped for simplicity). "Relevant to us" is computed on the firm side,
because it needs APX and Tamale data this project never holds (W-012).

**No overall score.** Insight, Clarity, Predictions and Uniqueness are shown side by side, and any one can be
used for sorting (the owner chose this).

## 2. Predictions as records (W-037)

Each explicit call in a letter becomes its own row. These rows give the Predictions count and, over time, a track record.
Each row holds:
- the call, paraphrased, with a short quote and page reference;
- the subject: a security (must match `core.security`) or a topic (must match `core.topic`);
- the direction (up, down, above or below a level, happens or does not happen);
- the horizon or date, if stated, and any condition;
- the confidence wording as written ("we expect", "could", "will").

Each call starts as **open**. When its horizon passes it becomes right, wrong, partly right or unresolvable.
Scoring is done by a person at first; price-based calls are scored automatically once a price source exists
(phase 6). Calls with no horizon stay open and are reported as such, never scored by guesswork.

Over time this gives each writer a hit rate by subject and horizon. That is the most useful thing the letters
can produce, and it ties into W-007 (forward performance from first mentions).

## 3. Manager tags (W-038)

Tags are loose: a manager can carry several in each facet. But they come from a controlled list, for the same
reason as topics (W-018). They supersede the single "cohort" in W-026.

| Facet | Tags |
|---|---|
| **Style** | value, deep value, quality, growth, special situations |
| **Strategy** | long only, long/short, market neutral, activist, event driven, macro, credit and distressed, multi-strategy |
| **Asset focus** (optional) | equities, credit, natural resources, multi-asset |
| **Geography** (optional) | US, global, Europe, Asia, emerging markets |

Rules:
- **People ratify.** The model may propose tags, each with evidence from the manager's letters or
  self-description. A person accepts them before they apply, matching the ratify-before-tagging rule.
- **Tags are dated.** Each has a from and a to date, because managers drift (Third Point's listed vehicle
  became a reinsurer). A change in style is itself worth reporting.
- **Measured facts sit beside tags, not in them.** Concentration (top-10 weight), turnover, and put and call
  usage come from the 13F and are shown next to the tags. The 13F cannot show short positions, so
  long/short and market neutral must come from what the manager says, never from holdings.
- **Overlap reports filter by tag** (for example "activist", or "value and long only") rather than by fixed
  cohorts.

## For the owner

1. Rubric settled 2026-10-08: two judged dimensions, two counted ones, a 1-5 scale and no overall score.
2. Edit the tag list.
3. Calibration: the owner gives quick verdicts on 10 rated letters (about right, too high, too low).
4. Optionally ask the agent for a first-pass tag proposal for the watchlist and the topic writers, to correct
   by hand.
