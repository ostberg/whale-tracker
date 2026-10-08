# Letter ratings and manager tags (draft for the owner to edit)

The owner's idea of 2026-10-08: a model-provided rating on each ingested letter, and loose tags to classify
the managers. Decisions W-036 to W-038. When built, the rubric and the tag list move into `config/`, and this
file keeps only the reasoning.

Both are model extraction, so the use restrictions in W-035 apply: no rating, prediction extraction or
embedding for a source whose terms forbid automated text analysis.

## 1. Letter rating (W-036)

Each dimension is scored as a whole number from 1 to 5, using the anchors below. Each score carries a
one-sentence reason and a short supporting quote (W-019); quotes are kept short (W-015). Every rating records
the model, the prompt version and the date, so ratings can be compared over time and re-run. A person can
override any score, and the override wins.

| Dimension | Asks | 1 | 3 | 5 |
|---|---|---|---|---|
| **Insight** | Does it argue something the reader probably hasn't heard? | Restates consensus or the news | One or two original angles | A clearly different, well-argued view |
| **Predictions** | Does it make explicit calls that can be checked? | None, or only vague hedges | Some calls, but loose about direction or timing | Several calls, each with a subject, direction and horizon |
| **Evidence** | Are claims backed by data, filings or unit economics? | Assertion only | Mixed | Claims consistently backed by specifics |
| **Candor** | Does it discuss mistakes, losses and changes of mind? | Only wins | Mentions setbacks briefly | Examines mistakes and what was learned |
| **Clarity** | Is it well written: structured, concise, readable? | Hard to follow, padded | Adequate | A pleasure to read; no wasted words |

Notes:
- **No single overall score by default.** The profile tells you more than an average, and "well written but
  no calls" is a different letter from "badly written but precise". If one number is wanted for sorting, the
  owner sets the weights in config.
- **Uniqueness is measured, not judged.** A model cannot know what every other manager wrote this quarter. A
  computed score adds that: how far a letter's content sits from the other letters of the same quarter,
  using text embeddings. It sits beside Insight; it does not replace it.
- **"Relevant to us" is computed on the firm side.** Whether a letter touches the firm's holdings or coverage
  needs APX and Tamale data, which this project never holds (W-012). The Research Assistant joins on that.
- **Calibration.** Before ratings are shown to anyone:
  - The owner, or the analyst who will use the ratings, rates 20 letters blind. The prompt is tuned until
    the model is within one point on most of them.
  - Five letters are re-checked each quarter.
  - The 20 are re-run before any change of model.
  - Model ratings tend to drift upwards and bunch at 4. The anchors and this check are the defence.

## 2. Predictions as records (W-037)

Each explicit call in a letter becomes its own row, which turns the Predictions score into a track record.
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

1. Edit the rubric: add, drop or rename dimensions, and change the anchors.
2. Edit the tag list.
3. Say who rates the calibration set of 20.
4. Optionally ask the agent for a first-pass tag proposal for the watchlist and the topic writers, to correct
   by hand.
