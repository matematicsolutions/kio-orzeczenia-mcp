# Sources ledger - Poland / KIO + regulator decisions (PL)

Machine-diffable record of every Legal Data Hunter (`worldwidelaw/legal-sources`) source we have
checked for this repo's scope, and what we did about it. Machine-read by
`eu-legal-mcp/gap_scan.py`.

This repo is single-source by constitution (CONSTITUTION.md Art. 1): orzeczenia.uzp.gov.pl only.
Besides the shipped row, this ledger is the fleet's tracking point for Polish REGULATOR decision
sources (quasi-judicial bodies) not yet assigned to a repo - todo rows below.

| LDH id | LDH name | LDH status @ check | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|---|
| PL/KIO | Krajowa Izba Odwolawcza (orzeczenia.uzp.gov.pl) | complete | shipped | `kio_search`, `kio_get_orzeczenie`, `kio_recent`, `kio_by_pzp_article`, `kio_get_pdf_url` | primary source of this repo, HTML over public UZP portal, rate limit 1 req/s per constitution. |
| PL/UODO | UODO decisions (uodo.gov.pl) | complete | todo | - | MACHINE BACKEND CONFIRMED live 2026-07-08 at the dedicated portal `orzeczenia.uodo.gov.pl` (react-router SSR + JSON layers, keyless): search GET `/search.data?dcr=rodo&q=...&page=N` (turbo-stream; `itemsCount` 579 docs @ check), snippets GET `/api/documents/public/items/{urn}/snippet.html?query=...&column=content_pl`, full text GET `/document/{urn}/content` (SSR HTML, e.g. urn:ndoc:gov:pl:uodo:2023:dkn_5131_34) or `/content.data`. Suggestions `/webapi/suggest?q=`. Small corpus, PATRON-critical. BUILT 2026-07-08 as local repo `uodo-orzeczenia-mcp` v0.2.0 (5 tools; full query-param map reverse-engineered from the portal bundle and verified live: `q` fulltext, `rn` signature exact=1, `dtps`/`dtpe` publication dates, `s` status final=485/nonfinal=91/repealed=3 of 579; page size fixed 10). NOT yet published - README governance gate requires notifying UODO (kancelaria@uodo.gov.pl) + 14-day wait before the repo goes public; row flips to `shipped` after that. |
| PL/KNF | KNF decisions | complete | todo | - | not probed this round; LDH `complete` via dane.gov.pl channel. |
| PL/UKE | UKE decisions | complete | todo | - | not probed this round. |
| PL/URE | URE decisions | complete | todo | - | not probed this round. |
| PL/UOKIK | UOKiK decisions | complete | todo | - | not probed this round; decyzje.uokik.gov.pl portal known from prior scouting. |

The `LDH status @ check` column records what LDH said WHEN WE CHECKED (2026-07-08 manifest pull).

## Status vocabulary

- `shipped` - live in this repo, has at least one MCP tool, tested and published.
- `rejected` - scouted, deliberately NOT built; `Notes` gives the reason (LDH taxonomy:
  `bot_protection`, `captcha_required`, `geo_restricted`, `duplicate`, `no_full_text_access`,
  `needs_separate_subscription`, `unreliable_exact_match`).
- `todo` - LDH has it as `complete`, we have not evaluated it yet (or, as with PL/UODO, probed
  and confirmed feasible but not yet built).

## Not on this list

Anything NOT in this table has simply not been checked yet against this scope's LDH sources.
Fleet map for Poland: `mcp-saos`, `mcp-nsa` (CBOSA - LDH block reversed live 2026-07-08),
`mcp-eureka` (KIS/MF tax interpretations, shipped 2026-07-08), `sejm-eli-mcp` / `mcp-isap`
(legislation), `mcp-krs`.
