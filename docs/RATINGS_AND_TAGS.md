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

Tags are loose: a manager can carry several in each facet, except Kind, which takes exactly one. But they come from a controlled list, for the same
reason as topics (W-018). They supersede the single "cohort" in W-026.

| Facet | Tags |
|---|---|
| **Style** | value, deep value, quality, growth, special situations |
| **Kind** | manager, listed vehicle, independent writer, economist or strategist |
| **Strategy** | long only, long/short, market neutral, activist, event driven, macro, credit and distressed, multi-strategy, crossover (public and private) |
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

## 4. First-pass tag proposal (2026-10-08, for the owner to correct)

Proposed by the agent from general knowledge of each firm, **not** from evidence in their letters: W-038 asks for
evidence, so each tag must be confirmed or corrected before use. "?" marks a tag the agent is unsure of. "13F
lines" is measured (the 2026 Q2 cover page, from `docs/MANAGER_SURVEY.md`): a rough guide to concentration,
since a top-10 weight has not yet been computed. Correct a tag by editing the table or saying it in chat.

### Watchlist

| Manager | Kind | Style | Strategy | Asset focus | Geography | 13F lines | Notes |
|---|---|---|---|---|---|---|---|
| Tiger Global | manager | growth | long/short, crossover | equities | global | 46 | Large private book; the 13F shows the public slice only |
| Coatue | manager | growth | long/short, crossover | equities | global | 211 | Private book too |
| Altimeter | manager | growth | long only?, crossover | equities | US | 20 | Long-biased; private book too |
| Atreides | manager | growth | long/short?, crossover | equities | US | 49 | Private book too |
| Whale Rock | manager | growth | long/short | equities | US | 35 | Technology-focused |
| Light Street | manager | growth | long/short | equities | global | 28 | Technology-focused |
| Dragoneer | manager | growth | long only, crossover | equities | US | 12 | Mostly private |
| Durable | manager | growth, quality | long only, crossover | equities | US | 36 | Private book too |
| Situational Awareness | manager | growth | long/short? | equities | US | 26 | AI-thematic; large put lines |
| Lone Pine | manager | growth, quality | long/short | equities | global | 34 | |
| Viking Global | manager | growth? | long/short | equities | global | 90 | Diversified fundamental book |
| D1 | manager | growth | long/short, crossover | equities | global | 55 | Private book too |
| Maverick | manager | growth? | long/short | equities | global | 179 | |
| Duquesne | manager | growth? | macro | multi-asset | global | 95 | Equity book only in the 13F |
| Appaloosa | manager | deep value, special situations | event driven, credit and distressed | multi-asset | US | 27 | Distressed roots; now equity-heavy |
| Third Point | manager | special situations | event driven, activist, long/short | multi-asset | global | 43 | |
| Berkshire Hathaway | listed vehicle | quality, value | long only | equities | US | 89 | Mostly operating businesses |
| Pershing Square | manager | quality | activist, long only | equities | US | 15 | Concentrated; uses hedges |
| Baupost | manager | value, deep value | event driven, credit and distressed | multi-asset | global | 23 | Often holds a lot of cash |
| Greenlight (DME) | manager | value | long/short | equities | US | 95 | Also holds gold and macro positions |
| TCI | manager | quality | activist, long only | equities | global | 11 | Concentrated; much of it in Europe |
| Akre | manager | quality | long only | equities | US | 20 | |
| Himalaya | manager | value, quality | long only | equities | Asia, US | 8 | |
| Fundsmith | manager | quality | long only | equities | global | 41 + 27 | Two filers |
| Elliott | manager | special situations | activist, event driven, credit and distressed, multi-strategy | multi-asset | global | 29 | |
| Starboard | manager | value | activist | equities | US | 22 | |
| ValueAct | manager | value, quality | activist | equities | US | 18 | |
| Trian | manager | value, quality | activist | equities | US | 9 | |
| JANA | manager | value | activist, event driven | equities | US | 10 | |
| Oaktree | manager | deep value | credit and distressed | credit | global | 145 | The 13F shows a small slice |
| Southeastern (Longleaf) | manager | value | long only | equities | global | 81 | Engages with managements, short of formal activism |
| Whitebox | manager | special situations? | multi-strategy, credit and distressed | multi-asset | US | 667 | Out of 13F tracking (W-010); Redleaf's writing only |

### Added by the owner

| Manager | Kind | Style | Strategy | Asset focus | Geography | 13F | Notes |
|---|---|---|---|---|---|---|---|
| PM Capital | manager | value, deep value | long only? long/short? | equities | global | No | Contrarian; some funds can short |
| Praetorian (Kupperman) | manager | special situations, deep value? | event driven, long/short? | natural resources, equities | global | No (13D and 13G only) | Thematic inflection trades |
| Laughing Water (Sweeney) | manager | value, special situations | long only? | equities | US | No | Small caps |
| Stone Sentinel | manager | ? | ? | ? | ? | Not checked | Too little known; tag from its letters |

### Topic writers

| Writer, firm | Kind | Style | Strategy | Asset focus | Geography | Notes |
|---|---|---|---|---|---|---|
| Sløk, Apollo | economist or strategist | (n/a) | credit and distressed, multi-strategy | multi-asset | global | An economist writing for the firm; the firm's 13F is not a public-equity book |
| Hussman | manager | value | long/short? | multi-asset | US | Hedged funds; valuation-driven |
| Lyn Alden | independent writer | (n/a) | macro | multi-asset | global | Independent writer, not a manager |
| Smead | manager | value | long only | equities | US | |
| GMO | manager | value, quality | macro, multi-strategy | multi-asset | global | Asset allocation |
| Crescat | manager | (n/a) | macro, long/short | natural resources, multi-asset | global | |
| Hoisington | manager | (n/a) | macro | credit | US | Treasuries |
| Fairfax (Watsa) | listed vehicle | value, deep value | macro? | multi-asset | global | Insurance float; macro hedges |
| Brookfield (Flatt) | manager | quality | long only | multi-asset | global | Real assets (no separate tag) |
| Goehring & Rozencwajg | manager | deep value | long only | natural resources | global | |
| Horizon Kinetics | manager | value, deep value | long only | equities, natural resources | global | Hard assets |
| Kopernik | manager | deep value | long only | equities, natural resources | global, emerging markets | |
| Sprott | manager | (n/a) | long only | natural resources | global | Precious metals and uranium |
| U.S. Global Investors | manager | (n/a) | long only | natural resources | global | |
| Bridgewater | manager | (n/a) | macro | multi-asset | global | |
| FPA (Romick) | manager | value | long only | multi-asset | global | Flexible, contrarian |
| Incrementum | manager | (n/a) | macro | natural resources | Europe | Gold |
| Semper Augustus | manager | quality, value | long only | equities | US | |
| Oakmark | manager | value | long only | equities | US, Europe | International team |
| ARK | manager | growth | long only | equities | global | |
| Baillie Gifford | manager | growth | long only | equities | global | |

### Tag-list changes decided 2026-10-08

The owner accepted **crossover** (a strategy tag) and the **Kind** facet, and rejected "real assets", so
Brookfield stays "multi-asset". Crossover is applied above to Tiger, Coatue, D1, Dragoneer, Altimeter, Atreides
and Durable. Kind is "manager" except Berkshire and Fairfax (listed vehicles), Sløk (economist or strategist)
and Lyn Alden (independent writer).

## For the owner

1. Rubric settled 2026-10-08: two judged dimensions, two counted ones, a 1-5 scale and no overall score.
2. Correct the first-pass tags in section 4, especially those marked "?". (List additions decided:
   crossover and Kind accepted, real assets rejected.)
3. Calibration: the owner gives quick verdicts on 10 rated letters (about right, too high, too low).
