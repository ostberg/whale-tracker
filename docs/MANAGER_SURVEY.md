# Manager survey, 2026-10-08

The candidate managers checked against EDGAR, so the owner can choose the watchlist from facts. This is
evidence, not configuration: the watchlist itself goes in `config/managers.yaml` once the owner has chosen.

## Method

- One-off, read-only requests to EDGAR's full-text search, its entity search, `data.sec.gov/submissions` and
  each latest 13F-HR's cover page. About 3 requests per second, with User-Agent
  `Tocqueville Asset Management research@tocqueville.com`.
- For every candidate: each entity whose name matched and that filed any 13F form since 2024-01-01, and the
  cover-page totals of its latest 13F-HR.
- Full history back to 2021 Q2 checked only for Pershing Square (both filers), Situational Awareness (both),
  Jana (both), Fundsmith (both), Elliott, Appaloosa, Greenlight and DME. The others' pre-2024 filer history is
  not yet checked; the backfill must confirm it.
- "Reported value" is the cover page's `tableValueTotal`. It includes the underlying value of put and call
  lines, so it is neither assets under management nor net long exposure.

Unless noted, the latest 13F-HR is for the quarter ending 2026-06-30, filed 2026-08-14 (Baupost filed
2026-08-13, Trian 2026-08-12). ★ marks the owner's first-pass priorities.

## Results

Cohorts are the agent's proposal, for comparing like with like in overlap reports.

### Technology and growth

| Manager | Filer CIK | Lines | Reported value | Notes |
|---|---|---|---|---|
| Tiger Global | 1167483 Tiger Global Management LLC | 46 | $23.98bn | |
| Coatue | 1135730 Coatue Management LLC | 211 | $48.63bn | 27 other included managers; two affiliates file notices only |
| Altimeter | 1541617 Altimeter Capital Management, LP | 20 | $9.83bn | |
| Atreides | 1777813 Atreides Management, LP | 49 | $14.34bn | |
| Whale Rock | 1387322 Whale Rock Capital Management LLC | 35 | $12.46bn | |
| Light Street | 1569049 Light Street Capital Management, LLC | 28 | $0.90bn | Small |
| Dragoneer | 1602189 Dragoneer Investment Group, LLC | 12 | $2.83bn | |
| Durable | 1798849 Durable Capital Partners LP | 36 | $10.28bn | |
| Lone Pine | 1061165 Lone Pine Capital LLC | 34 | $16.36bn | |
| Viking Global | 1103804 Viking Global Investors LP | 90 | $35.08bn | |
| D1 | 1747057 D1 Capital Partners L.P. | 55 | $34.78bn | |
| Maverick | 934639 Maverick Capital Ltd | 179 | $11.32bn | |
| Situational Awareness | 2045724 Situational Awareness LP | 26 | $20.24bn | First 13F for 2024 Q4. A second entity, 2038540 Situational Awareness Partners LP, filed a report identical to it for 2026 Q1 (see findings). Large put lines |

### Value and quality

| Manager | Filer CIK | Lines | Reported value | Notes |
|---|---|---|---|---|
| Berkshire Hathaway | 1067983 Berkshire Hathaway Inc | 89 | $299.25bn | 14 other included managers; subsidiaries file notices only |
| Baupost | 1061768 Baupost Group LLC/MA | 23 | 5,415,853 as filed, about $5.4bn | **Values in thousands**, not dollars |
| Akre | 1112520 Akre Capital Management LLC | 20 | $5.12bn | |
| Himalaya | 1709323 Himalaya Capital Management LLC | 8 | $3.70bn | |
| ★ Fundsmith | 1569205 Fundsmith LLP and 1868537 Fundsmith Investment Services Ltd | 41 and 27 | $13.65bn and $4.52bn | Two filers, both with full history since 2021 Q2; different books, not duplicates |
| ★ Southeastern (Longleaf) | 807985 Southeastern Asset Management Inc/TN | 81 | $1.92bn | 2 other included managers |
| TCI | 1647251 TCI Fund Management Ltd | 11 | $52.77bn | |
| ★ Greenlight | 1079114 Greenlight Capital Inc to 2023 Q4; 1489933 DME Capital Management, LP from 2024 Q1 | 95 | $3.91bn | Filer changed (see findings) |

### Activist

| Manager | Filer CIK | Lines | Reported value | Notes |
|---|---|---|---|---|
| ★ Pershing Square | 1336528 Pershing Square Capital Management, L.P. to 2026 Q1; 2026053 Pershing Square Inc. (formerly Pershing Square HoldCo, L.P.) from 2025 Q2 | 15 | $19.47bn | Filer changed (see findings). 6 other included managers |
| ★ Third Point | 1040273 Third Point LLC | 43 | $4.68bn | |
| ★ Elliott | 1791786 Elliott Investment Management L.P. | 29 | $22.67bn | Full history since 2021 Q2; Elliott Associates files notices only |
| ★ Starboard | 1517137 Starboard Value LP | 22 | $4.52bn | 5 other included managers |
| ValueAct | 1418814 ValueAct Holdings, L.P. | 18 | $5.63bn | Combination report |
| Trian | 1345471 Trian Fund Management, L.P. | 9 | $4.23bn | |
| ★ Jana | 1159159 JANA Partners LLC to 2023 Q2; 1998597 JANA Partners Management, LP from 2023 Q3 | 10 | $1.90bn | Filer changed (see findings) |

### Macro, opportunistic and credit

| Manager | Filer CIK | Lines | Reported value | Notes |
|---|---|---|---|---|
| Duquesne | 1536411 Duquesne Family Office LLC | 95 | 5,210,860 as filed, about $5.2bn | **Values in thousands**, not dollars |
| Appaloosa | 1656456 Appaloosa LP | 27 | $7.73bn | Full history since 2021 Q2 |
| ★ Oaktree | 949509 Oaktree Capital Management LP | 145 | $7.21bn | Combination report. Mostly a credit manager, so the 13F shows a small slice; Howard Marks's public memos are the richer source (letters phase) |

### Not recommended for 13F tracking

| Manager | Filer CIK | Lines | Reported value | Notes |
|---|---|---|---|---|
| Whitebox | 1257391 Whitebox Advisors LLC | 667 | $7.65bn | Multi-strategy and credit-arbitrage book with frequent amendments (26 13F filings since 2024): the W-010 profile. Andy Redleaf has left, so the 13F no longer reflects his views. His public writing is a candidate letters source for phase 6 |

### Unresolved

- ★ **"Value Investor"** from the owner's first-pass list: no manager of that name files a 13F. Possibly
  ValueAct (already a candidate), or something else; owner to say.

## Findings that change the design

1. **Some filers still report values in thousands.** The SEC switched 13F values to dollars for filings from
   2023-01-03, but Baupost and Duquesne still report in thousands in their 2026 Q2 filings. Baupost lists
   1,371,931 Alphabet shares at 484,744, which is $0.35 a share in dollars and $353 in thousands. The filing
   still reconciles to its own summary page, so reconciliation alone does not catch it. Units must be detected
   for each filing (W-025).
2. **A manager is not one CIK.** Successions (Greenlight to DME in 2024 Q1, JANA Partners LLC to JANA Partners
   Management in 2023 Q3, Pershing Square Capital Management to Pershing Square Inc. in 2026 Q2) and parallel
   filers (Fundsmith) are common. In each succession the old CIK switches to 13F-NT, a notice that another
   manager reports its holdings, in the quarter the new CIK starts full reports. Watching only the original
   CIK would show a full exit followed by silence (W-024).
3. **Overlapping filers are usually separate books, but not always.** From 2025 Q2 to 2026 Q1 Pershing Square
   Inc. reported only its own 9.0m Howard Hughes shares beside Pershing Square Capital Management's full report,
   so the two add up. But the two Situational Awareness entities filed identical 2026 Q1 reports (42 lines,
   $13,676,657,577 each), so adding them would double the position. The ingest must detect identical filings
   from one manager's filers and stop (W-024).
4. **Option lines can be large.** Situational Awareness's 2026 Q1 report holds puts on AMD (about $969m of
   underlying) and ASML (about $494m) beside small long positions in the same names. Treating them as long
   would invert the signal. This confirms the existing rule to flag put and call lines.
