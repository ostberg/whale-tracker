# Letter sources

The register of candidate letter sources: each one's tier (W-029) and what is known about the right to fetch,
store and machine-read it. This is evidence, not configuration: approved sources go into
`config/letter_sources.toml`, inactive until the compliance ruling. Everything here was checked on 2026-10-08 unless
marked (I) for inferred.

## Three kinds of restriction, and what fixes each (W-035)

| Kind | Examples | What fixes it |
|---|---|---|
| **Access**: bots, scraping, crawling, gates | Bot bans in the terms (Apollo, Sprott, Malibu Life); accept-terms gates (Pershing Square Holdings); detail forms (Laughing Water) | `manual` collection: a person downloads and the reminder calendar prompts them (W-033) |
| **Storage**: copying or storing | Regal Partners (PM Capital): storing needs prior written consent | Keep extracts, short quotes and the link, not the file (W-032) |
| **Use**: automated text analysis or AI | Fundsmith: no "automated analytical technique aimed at analysing text" without express written consent; Ruffer: no text and data mining or AI; Buy Side Digest: no AI use, embeddings included | **Only the publisher's written consent, or a licence.** Downloading by hand does not help, because the restriction is on what we do with the text |

Nearly every site also limits use to "personal, non-commercial". **Settled 2026-10-13 (W-043):** the firm
uses sources for internal research only, with no republication, external quotation or monetization, which
clears those clauses. It does not lift explicit AI or text-analysis bans, bot bans or aggregator terms.

## The owner's priority managers: where their own words can come from

| Manager | Best route | Mode | Notes |
|---|---|---|---|
| Greenlight | Partner letters only through an aggregator, under licence (Hedge Fund Alpha) | Licence | Greenlight's own site bans systematic retrieval for a database; partner letters sit behind its login. Greenlight Re's quarterly 8-K on EDGAR carries short commentary on the Greenlight-managed portfolio (tier 2, auto) |
| Third Point | Quarterly letters at Malibu Life Holdings (formerly Third Point Investors Ltd), malibulifeinsurance.com/resources/ | Manual | Terms ban bots, crawlers and data mining. 13D exhibits on EDGAR are auto |
| Oaktree | Howard Marks memos, oaktreecapital.com/insights/memos | Auto | No clause on automated access; personal downloads allowed; no republication. Pending ruling |
| Pershing Square | (1) Pershing Square USA's (PSUS) semi-annual N-CSRS on EDGAR, which contains the manager's letter (tier 2); (2) Pershing Square Inc.'s (NYSE: PS) quarterly letter from 2Q26; (3) Pershing Square Holdings' reports | Auto, auto, manual | PSH has an accept-terms gate and terms banning spidering. PS Inc. has no terms page, but bot protection answered 403 to curl |
| Fundsmith | Owner's letters at fundsmith.co.uk/documents/ | **Consent needed** | Use restriction (see above). Ask Fundsmith for written consent. Smithson has the same notice |
| Longleaf (Southeastern) | Fund commentaries, southeasternasset.com/mutual-fund-commentaries/ | Auto | Personal use only, no commercial distribution. Pending ruling |
| Elliott | elliottletters.com campaign letters; DFAN14A and 13D exhibits on EDGAR | Auto | Copyright reserved; nothing on automated access. elliottdocs.com is gated |
| Starboard | starboardvalue.com/presentations/ (board letters and decks); EDGAR | Auto | No terms page; robots crawl-delay 10 |
| JANA | 13D exhibits on EDGAR only | Auto | Its own site has no letters |
| "Value Investor" | Unresolved | | Owner to say what this means |

## Sources the owner named

| Source | Tier | What it is | Access | Robots | Terms | PDF flags | Verdict |
|---|---|---|---|---|---|---|---|
| [Fundsmith documents](https://www.fundsmith.co.uk/documents/), e.g. the 2026 Fundsmith Equity Fund semi-annual letter | 1 | Owner's annual letters since 2010, semi-annual since about 2020 | Open; bot protection on some fetchers | Allowed | [Legal notice](https://www.fundsmith.co.uk/legal-notice/): no systematic or automated data collection, and no automated text analysis to generate information or train AI, without express written consent (re-read directly 2026-10-08) | Not encrypted | **Consent needed** (use restriction) |
| [Oaktree memos](https://www.oaktreecapital.com/insights/memos) | 1 | Howard Marks memos since 1990; HTML from about 2020, PDF before | Open | Memo paths allowed | No republication without consent; personal downloads allowed; nothing on automated access | Not checked | Auto, pending ruling |
| [Pershing Square Holdings June 2026 interim report](https://assets.pershingsquareholdings.com/wp-content/uploads/2026/08/13002306/Pershing-Square-Holdings-Ltd.-June-2026-Interim.pdf) | 1 | Listed vehicle's interim report, 59 pages: letter plus financial statements | **The materials page has an accept-terms gate**, though the file itself answers HTTP 200 | Main site allows all but `/wp-admin/`; the `assets.` host answers 403 for robots.txt | Terms ban spidering and scraping | Not encrypted | **Manual**; extract only the letter section. PSUS on EDGAR is the auto route |
| q4cdn.com `Q2-2026-Shareholder-Letter.pdf` ([link](https://s29.q4cdn.com/628966176/files/doc_financials/2026/q2/Q2-2026-Shareholder-Letter.pdf)) | 1 | A public company's own shareholder letter on its investor-relations host; issuer not yet identified | Open | Not checked | Not checked | Not encrypted | Owner to name the company |
| [PM Capital insights](https://www.pmcapital.com.au/insights) | 1 | Single-company theses by named PMs, the PM's annual report, quarterly fund updates. About 450 items, paged with `?topic=All&page=N` (zero-based), roughly 1.4 a month | Open | Allowed (Drupal defaults only) | [Regal Partners terms](https://regalpartners.com/terms-of-use/): copying or **storing** needs prior written consent; nothing on bots or AI | Not checked | Auto without storing the raw file (W-032). No US 13F filer |
| [PM Capital Global Opportunities Fund (ASX: PGF) reports](https://www.pmcapital.com.au/pgf/reports) | 1 | Weekly NAV (net tangible assets) since 2015, monthly updates since 2014, quarterly updates since 2015; all PDF | Open | Allowed | As above | Not checked | As above. The NAV reports are numbers, not letters: low value |
| [Praetorian Capital investor letters](https://pracap.com/investor-letters/) (Harris Kupperman) | 1 | Quarterly investor letters, the pitch deck and monthly tear sheets: 26 PDFs, openly linked and hosted on go.pracap.com. The "accredited investor" wording only concerns subscribing to updates | Open | Allowed except `/bullpen` | No terms page, only a privacy policy and an offering disclaimer | Not checked | **Auto**, pending ruling. 13F-HR stopped in 2023; Praetorian Capital Management (CIK 1337851) files many 13D and 13G (W-031) |
| [Laughing Water Capital letters](https://www.laughingwatercapital.com/letters) (Matt Sweeney) | 1 | Letters from 2016 to H1 2026 (year-end, quarterly, half-year), plus presentations and transcripts | The owner met a details form; the page source also links the PDFs directly | Squarespace defaults; letter files allowed | No terms or legal pages found | Not checked | **Manual** (W-033): the publisher gates with a form, so a person downloads. No 13F; one PX14A6G exempt solicitation on EDGAR (tier 2) |
| [Hedge Fund Alpha: Greenlight Q2 2026](https://hedgefundalpha.com/wp-content/uploads/2026/08/Greenlight_Capital_Q2_2026_Letter.pdf) | 3 | Greenlight's letter to partners, re-hosted | Open PDF on a subscription site ($399 a year); many write-ups need a login | Allowed, except site search; declares `ai-input=yes, ai-train=no` | [Legal disclaimer](https://hedgefundalpha.com/legal-disclaimer-valuewalk/): no robots or spiders, no copying without written consent; the letters page also bans scraping, bulk redistribution and AI training. **Sells a data-licensing product** | **Encrypted; copying and text extraction NOT allowed** | Licence (W-029, W-030) |
| [Hedge Fund Alpha: Stone Sentinel Q3 2026](https://hedgefundalpha.com/investor-letters/stone-sentinel-capital-q3-2026/) | 3 | Letter to partners as full HTML | Open, posted 2026-10-08 | Allowed | As above | n/a (HTML) | Licence |
| [Buy Side Digest: Greenlight](https://www.buysidedigest.com/funds/greenlight-capital) | 3 | Letter summaries, topic tags and scored fields open; full letters for paid members | Partly paywalled; site says accredited and professional investors only | Allowed | [Terms](https://www.buysidedigest.com/terms) forbid bots and scraping without written permission, internal business use, and any AI use including embeddings | n/a | Only through its [institutional feed](https://www.buysidedigest.com/institutional) (daily S3, JSON and CSV, source links to the manager, ticker and stance taxonomy) |

## From the owner's starting library (2026-10-13)

78 PDFs in `../Whale Tracker Inbox` (W-044), all identified by `whales inbox scan`:
- 64 from public websites: Laughing Water 20, Praetorian 16, Bonsai 15, Alluvial 14;
- 13 shared by GreenWood (6 annual or semi-annual letters, 7 research reports).

| Source | Tier | Terms (checked 2026-10-13) | Verdict |
|---|---|---|---|
| [Alluvial writings](https://alluvialcapital.com/writings/) (Dave Waters) | 1 | robots.txt allows all but `/wp-admin/`; no terms page, only an "as is" disclaimer | Auto; cleared for internal use (W-043). No 13F; CIK 1958911 files 13G |
| [Bonsai letters](https://bonsaipartners.com/letters-and-materials) (Andrew Rosenblum) | 1 | [Terms](https://bonsaipartners.com/terms-of-use): "solely for internal, personal, non-commercial purposes"; no copying or redistribution; nothing on bots or AI | Auto; cleared for internal use (W-043) |
| [GreenWood investor letters](https://www.gwinvestors.com/investor-letters/) (Steven Wood) | 1 | Accredited-investor sign-up; [terms](https://www.gwinvestors.com/terms-conditions-use/) exclude "data mining, robots or similar data gathering" and adding content to another database. (`greenwoodinvestors.com` is an unrelated parked domain) | **Off** until GreenWood consents (W-035) |
| GreenWood, shared with the owner | 1 | As above. Josh Pesses (COO) welcomed the connection on 2026-10-13, knowing the purpose (email in the inbox's permissions folder), but that is not explicit consent | Recorded; **not machine-read** until GreenWood agrees |
| GreenWood 13D exhibits (CIK 2096490) | 2 | Public SEC filing | Auto (W-031) |

## Additional writers on the topic list

From a research agent's survey on 2026-10-08. The agent opened every index page except Semper Augustus. These
facts are agent-reported and not re-checked here; terms in particular need re-reading before any approval.
Ordered by usefulness for the topic list.

Topic codes: R rates, T Treasuries, EU European macro, H housing, AI, Au gold, I inflation, O oil, L lumber.

| # | Writer, firm | Index | Kind, frequency, since | Topics | 13F CIK | Terms (robots allows unless noted) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Torsten Sløk, Apollo | apollo.com/insights-news/insights/daily-spark | Daily Spark, daily, HTML | R T I H EU AI O Au | 1449434 (book not public equity) | Bans bots used to scrape; personal use; apolloacademy.com disallows `*.pdf` | Bot ban: permission or manual load |
| 2 | John Hussman, Hussman Strategic Advisors | hussmanfunds.com/comment/ | Monthly comment since 2000, HTML | R T I AI Au | 1179475 | No terms page found, only a copyright notice | Promising; ask for the reprint policy |
| 3 | Lyn Alden | lynalden.com/newsletter-archives/ | Newsletter every ~2 months since 2018, HTML | T R I Au O EU AI | None | Copying needs permission; short credited excerpts allowed; nothing on bots | Personal use; ruling |
| 4 | Bill Smead, Smead Capital | smeadcap.com/missives/ | Missives 1 to 2 a month, HTML | O H R T I EU AI | 1427008 | Personal, non-commercial; no bot clause | Ruling. Strong said-versus-owned fit |
| 5 | Grantham and Inker, GMO | gmo.com/americas/research-library/ | Quarterly letter and insights, HTML and PDF | AI R I EU O H | 1352662 | Print or download with notices kept; no commercial reproduction; no bot clause | Ruling |
| 6 | Kevin Smith and Tavi Costa, Crescat | crescat.net/investment-process/investor-letters/ | About monthly since 2023, HTML | Au I R T O | None | Bans bots harvesting a large portion | Bot ban |
| 7 | Lacy Hunt, Hoisington | hoisington.com/economic_overview.html | Quarterly, only since Q3 2024, PDF | R T I H | None | No terms found; no robots.txt | Promising; ask |
| 8 | Prem Watsa, Fairfax | fairfax.ca/investors/ | Annual letter since 1985, PDF | R T I EU | 915191 | Personal, non-commercial; no bot clause | Ruling |
| 9 | Bruce Flatt, Brookfield | bam.brookfield.com/reports-sec-filings/letters-shareholders | Quarterly since Q4 2022 | R H AI O EU | 1001085 | Bans scraping, bots and spiders; Cloudflare | Bot ban |
| 10 | Goehring & Rozencwajg | gorozen.com/research/commentaries | Quarterly since 2017 | O Au I | 1863154 | No terms found; full text needs a form | Gated; manual only |
| 11 | Murray Stahl, Horizon Kinetics | horizonkinetics.com/insights/library/ | Quarterly since 2015, PDF | I O Au R | 1056823 | Bans bots and "intelligent agents" | Bot ban |
| 12 | David Iben, Kopernik | kopernikglobal.com/news-views/ | Several a year since 2013 | Au I O L | 1599814 | Personal or informational; no commercial reproduction | Ruling. Only lumber angle (June 2026 timber paper) |
| 13 | Sprott | sprott.com/insights/ | 2 to 4 a month since 2018, HTML | Au I R | 1512920 | Bans scraping and data mining | Bot ban |
| 14 | Frank Holmes, U.S. Global Investors | usfunds.com/investor-library/ | Weekly, HTML | Au O AI I | 754811 | Personal, non-commercial; no bot clause | Ruling |
| 15 | Bridgewater | bridgewater.com/research-and-insights | About monthly, HTML | AI I Au EU R | 1350694 | "Agree" click-through; bans robots | Bot ban |
| 16 | Steven Romick, FPA | fpa.com/insights/ | Quarterly, HTML | R I AI | 1377581 | Personal viewing only; crawl-delay 10 | Ruling |
| 17 | Incrementum, *In Gold We Trust* | ingoldwetrust.report/archiv/ | Annual since 2007, PDF | Au I R T | Not a US filer | Private, non-commercial copies only | Ruling |
| 18 | Chris Bloomstran, Semper Augustus | semperaugustus.com | Annual letter, PDF | R I O AI | 1115373 | Unverified (Cloudflare) | Unverified |
| 19 | Nygren and Coniaris, Oakmark | oakmark.com/news-insights/ | Quarterly, HTML | EU AI R | 813917 | Bans bots and "intelligent agents" | Bot ban |
| 20 | Cathie Wood, ARK Invest | ark-invest.com/articles | Articles and letters, HTML | AI | 1697748 | Terms unverified (403); robots disallows `/wp-content/` (the PDFs) | PDFs off limits |
| 21 | Baillie Gifford | bailliegifford.com/en/uk/individual-investors/insights/ | 737 items, 49 tagged AI | AI | 1088875 | Personal use; no reproduction; no bot clause | Ruling |

**Excluded: Ruffer** (CIK 1426859). Its disclaimer forbids text and data mining and any use for AI training,
fine-tuning or retrieval; its robots.txt blocks AI crawlers by name; its site excludes US persons.

**What the survey shows.**
- Terms are the binding constraint, not robots.txt. Eight sources ban bots in their terms even where
  robots.txt allows the path. Almost every other one limits use to personal, non-commercial.
- So for most tier-1 sources an automated collector needs written permission from the publisher, or a
  compliance view that a person loading letters by hand (`whales ingest-file`) for internal research is
  acceptable. A licensed feed (Buy Side Digest's institutional product) moves that burden to the vendor.
- Nobody writes regularly on edge compute or lumber. The nearest proxies are ARK and Baillie Gifford for AI
  infrastructure, and Kopernik, Smead (homebuilders) and Goehring & Rozencwajg for lumber.
- Not verified, so left out: First Eagle and Troy (investor gates), WisdomTree (403), VanEck (redirect loop).
- PIMCO's outlooks are strong on rates, but it files only 13F-NT, so there are no holdings to compare.

## The watchlist managers

From a research agent's inventory on 2026-10-08. The agent opened each index page and fetched robots.txt with
curl, and accepted no gate or banner. Terms are paraphrased. "Eligible" means open, allowed by robots.txt and
with nothing on automated access in the terms, pending the compliance ruling.

| Manager | Source | Kind and span | Robots | Terms | Verdict |
|---|---|---|---|---|---|
| Berkshire | berkshirehathaway.com/letters/letters.html | Annual letter: Buffett 1977 to 2024, Abel from 2025; HTML to 2003, then PDF | No robots.txt | No reproduction or distribution without written permission; nothing on automated access | Eligible |
| Coatue | coatue.com/east-meets-west and blog posts | East Meets West decks 2023 to 2025 and occasional decks; PDFs on Google Drive | Allowed | One personal copy; no republication | Eligible |
| Situational Awareness | situational-awareness.ai | One essay (June 2024), not a fund letter | Allowed | None found | Eligible |
| Greenlight Re | EDGAR 8-K, CIK 1385613 | Quarterly results with short commentary on the Greenlight-managed portfolio | Allowed | Public filing | Eligible (tier 2) |
| Greenlight | greenlightcapital.com | Sohn and Robin Hood presentations; partner letters behind a login | No robots.txt | Bans systematic retrieval to build a database | Restricted |
| Akre | akrefund.com (now the Akre Focus ETF) | Occasional letters (HTML and PDF), quarterly commentary behind a mailing-list sign-up | **Disallows `*.pdf` and `/wp-content/uploads/`**; akre.com's robots.txt is malformed and reads as block-all | Personal, non-commercial | HTML letters eligible; the rest restricted |
| Himalaya (Li Lu) | himcap.com/publications | Essays and speeches 2010 to 2024, PDF | Empty file | No copying without permission; nothing on automated access | Eligible |
| Third Point | malibulifeinsurance.com/resources/ | Quarterly letters Q1 2024 to Q2 2026, monthly reports | Allowed | Bans bots, crawlers and data mining | Manual |
| TCI | tcifund.com/CorporateEngagements/... | Campaign letters (Alphabet, Aena, Airbus, Cellnex) since 2022 | No robots.txt | "Private circulation"; reproduction needs consent | Restricted; ask |
| Trian | trianpartners.com/press-releases/ | Open letters and decks since 2022 | Allowed | Personal use only | Eligible |
| Altimeter | Medium (Meta open letter, 2022) (I) | One-off | AI bots disallowed | Bot challenge | Unverified |
| Smithson | smithson.co.uk | Chairman letters and reports since 2020 | Allowed | Same notice as Fundsmith | Consent needed |

**No public source found:** Tiger Global, Baupost and Whale Rock (logins only); Atreides, Dragoneer, Light Street,
Durable, Viking and Maverick (company pages only); D1 (parked domain); Lone Pine (podcasts only); Duquesne and
Appaloosa (no website); ValueAct and JANA (no letters on site). For these the only public "say" is SEC
filings: 13D exhibits and proxy materials. Appaloosa filed a 13D on Whirlpool on 2026-03-03 after a public
letter to its board (the letter is known only from news coverage (I)).

## Activist letters on EDGAR

Each example was found with EDGAR full-text search and opened:

| Activist | Example |
|---|---|
| Pershing Square | [13D/A Ex. 99.22, Ackman to the Howard Hughes board, 2025-01-13](https://www.sec.gov/Archives/edgar/data/1981792/000093041325000067/c111204_ex99-22.htm) |
| Third Point | [13D/A Ex. 3, Loeb to the Bath & Body Works board, 2023-02-22](https://www.sec.gov/Archives/edgar/data/701985/000089914023000443/b022223d.htm) |
| Elliott | [DFAN14A, letter to Phillips 66 shareholders, 2025-04-03](https://www.sec.gov/Archives/edgar/data/1534701/000092189525000976/dfan14a10168303_04032025.htm) |
| Starboard | [DFAN14A, TripAdvisor board letter, 2026-02-17](https://www.sec.gov/Archives/edgar/data/1526520/000092189526000436/dfan14a06297373_02172026.htm) |
| ValueAct | [13D/A Ex. 2, Ubben to the MSCI board, 2015](https://www.sec.gov/Archives/edgar/data/1408198/000141881215000005/msci13d0301515.txt) (no later example) |
| Trian | [13D/A Ex. 7, Peltz and General Catalyst to the Janus Henderson board, 2025-10-26](https://www.sec.gov/Archives/edgar/data/1274173/000119312525250770/ck0001345471-ex7.htm) |
| JANA | [13D/A Ex. 99.5, open letter to Lamb Weston shareholders, 2025-06-03](https://www.sec.gov/Archives/edgar/data/1679273/000090266425002636/p25-1336exhibit99_5.htm) |
| TCI | [13D/A Ex. 2, letter to the Canadian National board, 2021-08-31](https://www.sec.gov/Archives/edgar/data/16868/000090266421004084/p21-2054sc13da.htm) |

**EDGAR covers only part of what activists write.** A letter reaches EDGAR only with a 13D (a stake of 5% or
more in a US-registered company) or a proxy solicitation (DFAN14A). Letters about smaller stakes or non-US
companies appear only on the activist's own site:
- Starboard's 2026 letters to LW, DT, KMX, KNF, FLS and RIOT are not on EDGAR.
- TCI's Alphabet and Airbus letters, and Elliott's Northern Star and Daikin letters, appear only on their own
  sites.

Both routes are needed: watch EDGAR for 13D exhibits and DFAN14A, and the activists' own sites for the rest.

**Other aggregators.** ValueWalk answered 403 to curl; its letters appear to have moved to Hedge Fund Alpha (I).
Scribd disallows `/document_downloads/`, and downloads need a login (I), so it is excluded.

**SEC access.** EDGAR's `/Archives` refused a request whose User-Agent named the firm but gave no email ("Undeclared
Automated Tool"). The job's User-Agent must carry a real contact email.
