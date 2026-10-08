# Letter sources

The register of candidate letter sources, their tier (W-029) and what is known about the right to fetch, store
and machine-read them. Evidence, not configuration: approved sources go into `config/letter_sources.yaml` after
the compliance ruling.

Columns: **robots** is whether robots.txt allows the path for generic agents. **Terms** covers automated access,
storage and AI use. **PDF flags** says whether the PDF permits text extraction (W-030).

## Sources the owner named on 2026-10-08

Checked by the agent the same day.

| Source | Tier | What it is | Access | Robots | Terms | PDF flags | Verdict |
|---|---|---|---|---|---|---|---|
| [Fundsmith documents](https://www.fundsmith.co.uk/documents/), e.g. the 2026 Fundsmith Equity Fund semi-annual letter | 1 | Owner's letters (annual, semi-annual) and fund documents | Open | Not yet checked (inventory agent) | Not yet checked (inventory agent) | Not encrypted | Likely clean; pending terms |
| [Oaktree memos](https://www.oaktreecapital.com/insights/memos) | 1 | Howard Marks memos | Open | Not yet checked (inventory agent) | Not yet checked (inventory agent) | Not checked | Likely clean; pending terms |
| [Pershing Square Holdings June 2026 interim report](https://assets.pershingsquareholdings.com/wp-content/uploads/2026/08/13002306/Pershing-Square-Holdings-Ltd.-June-2026-Interim.pdf) | 1 | Listed vehicle's interim report, 59 pages: letter plus financial statements | Open; HTTP 200 with the declared User-Agent | Main site allows all but `/wp-admin/`; the `assets.` host answers 403 for robots.txt, which RFC 9309 treats as no restriction | Not yet checked (inventory agent) | Not encrypted | Likely clean. Extract only the letter section |
| q4cdn.com `Q2-2026-Shareholder-Letter.pdf` ([link](https://s29.q4cdn.com/628966176/files/doc_financials/2026/q2/Q2-2026-Shareholder-Letter.pdf)) | 1 | A public company's own shareholder letter on its investor-relations host; issuer not yet identified | Open | Not checked | Not checked | Not encrypted | Owner to name the company |
| [PM Capital insights](https://www.pmcapital.com.au/insights) | 1 | Single-company theses by named PMs, the PM's annual report, quarterly fund updates. About 450 items, paged with `?topic=All&page=N` (zero-based), roughly 1.4 a month | Open | Allowed (Drupal defaults only) | [Regal Partners terms](https://regalpartners.com/terms-of-use/): copying or **storing** needs prior written consent; nothing on bots or AI | Not checked | Eligible to read; storing raw files needs consent (W-032). No US 13F filer |
| [PM Capital Global Opportunities Fund (ASX: PGF) reports](https://www.pmcapital.com.au/pgf/reports) | 1 | Weekly NAV (net tangible assets) since 2015, monthly updates since 2014, quarterly updates since 2015; all PDF | Open | Allowed | As above | Not checked | As above. The NAV reports are numbers, not letters: low value |
| [Hedge Fund Alpha: Greenlight Q2 2026](https://hedgefundalpha.com/wp-content/uploads/2026/08/Greenlight_Capital_Q2_2026_Letter.pdf) | 3 | Greenlight's letter to partners, re-hosted | Open PDF on a subscription site ($399 a year) | Allowed; declares `ai-input=yes, ai-train=no` | No public terms page found; "All Rights Reserved" | **Encrypted; copying and text extraction NOT allowed** | Needs a licence and a compliance ruling (W-029, W-030) |
| [Hedge Fund Alpha: Stone Sentinel Q3 2026](https://hedgefundalpha.com/investor-letters/stone-sentinel-capital-q3-2026/) | 3 | Letter to partners as full HTML; index at `/investor-letters/` | Open, posted 2026-10-08 | Allowed | As above | n/a (HTML) | Needs a licence and a compliance ruling |
| [Buy Side Digest: Greenlight](https://www.buysidedigest.com/funds/greenlight-capital) | 3 | Letter summaries, topic tags and scored fields open; full letters for paid members | Partly paywalled; site says accredited and professional investors only | Allowed | [Terms](https://www.buysidedigest.com/terms) forbid bots and scraping without written permission, internal business use, and any AI use including embeddings | n/a | Only through its [institutional feed](https://www.buysidedigest.com/institutional) (daily S3, JSON and CSV, source links to the manager, ticker and stance taxonomy) |

## Inventory of the watchlist and additional writers

Pending: two research agents were started on 2026-10-08, one for the watchlist managers and one for further
public writers on the topic list.
