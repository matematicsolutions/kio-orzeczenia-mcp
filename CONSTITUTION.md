# Constitution kio-orzeczenia-mcp

Version: 0.1.0 (2026-05-20)
Status: Draft POC

This document defines the 4 non-negotiable governance principles for the MCP connector to the case law of the Krajowa Izba Odwolawcza (KIO) (National Appeals Chamber) at the Urzad Zamowien Publicznych (UZP) (Public Procurement Office).

---

## Art. 1. Public data only

`kio-orzeczenia-mcp` consumes exclusively the publicly available KIO case law database made available at `https://orzeczenia.uzp.gov.pl`. These are official rulings of the Krajowa Izba Odwolawcza (National Appeals Chamber) published by UZP - case law made publicly available under the Act of 6 September 2001 on access to public information (Dz.U. 2001 no. 112 item 1198, as amended) and the Act of 11 September 2019 - Public Procurement Law.

KIO rulings are not a source of law within the meaning of art. 87 of the Constitution of the Republic of Poland - they are rulings applying the law that widely serve law-firm practice as reference material.

The connector:
- does NOT circumvent any protections (no CAPTCHA-solving, no fake-CSRF)
- does NOT de-anonymize the parties to a proceeding beyond what UZP publishes
- does NOT store the full text of rulings in the audit log (only signatures and metadata)
- does NOT modify the source data

If UZP changes its terms or Terms of Service and prohibits programmatic access - the connector is suspended. Decision of Wieslaw Mazur as Administrator.

## Art. 2. Rate limit 1 req/s mandatory

The default rate limit is **1 request per second** for the entire server (global lock, not per-tool). The value is chosen conservatively - without knowing the actual capacity of UZP infrastructure, we pick a lower threshold than for larger institutional portals (e.g. api.sejm.gov.pl, which does not publish an official rate limit but handles noticeably higher load).

- Configurable via the env `KIO_MCP_RATE_LIMIT` (float, requests per second), but no higher than **2.0** (arbitrary POC decision, to be validated - see `DISCOVERY.md` section "Open questions")
- If `KIO_MCP_RATE_LIMIT > 2.0` -> hard error at startup
- User-Agent mandatory: `matematic-kio-mcp/{version} (+https://matematic.co; kontakt@matematic.co)`
- Retry-After respected unconditionally
- Exponential backoff on 429/503

Goal: not to overload UZP infrastructure and to identify ourselves clearly (kontakt@matematic.co).

## Art. 3. Audit log mandatory

Every call to each of the 5 tools writes an entry to `~/.matematic/audit/kio-orzeczenia-mcp.jsonl`:

- `ts` (ISO 8601 UTC)
- `tool` (tool name, e.g. `kio_search`)
- `params_hash` (SHA-256 of the parameters - no raw data)
- `result_summary` (e.g. `{"items": 12, "total": 154}`)
- `source_urls` (list of full URLs of the endpoints hit)
- `latency_ms`
- `cache_hit` (bool)

**What we do NOT log:**
- The full text of rulings (`reasoning`, `content_text`) - only signatures
- Personal data of the parties to a proceeding (even though it is public, the audit log is our internal artifact)

The audit log serves operator accountability - every call to the connector leaves a trace allowing verification of what was fetched and when. The decision to invoke a specific provision (e.g. art. 12 of Regulation (EU) 2024/1689 - AI Act, on record-keeping for high-risk AI systems) rests with the entity deploying the connector and requires a separate legal assessment for that entity. The connector itself is not a high-risk AI system within the meaning of the AI Act.

## Art. 4. Citations mandatory

Every `Orzeczenie` and `OrzeczenieSummary` returned by the connector MUST contain:

- `signature` in the canonical format `"KIO {nr}/{rok}"` (e.g. `"KIO 2924/21"`)
- `human_readable_citation` in the format `"Wyrok KIO z {YYYY-MM-DD}, sygn. KIO {nr}/{rok}"`
- `source_url` - the full URL to `orzeczenia.uzp.gov.pl` (openable by a human)
- `retrieved_at` (ISO 8601 UTC)

Goal: every ruling returned by the connector contains a complete set of metadata allowing direct verification in the UZP database - signature, link to the original, retrieval date.

---

## Constitution changes

Changes to this document require:
1. An entry in `DISCOVERY.md` with justification
2. A SEMVER bump of the constitution (MAJOR for changes to Art. 1-4, MINOR for clarifications, PATCH for typos)
3. Acceptance by the Administrator (Wieslaw Mazur)

---

Constitution based on the spec-driven pattern (cherry-pick github/spec-kit, MIT).
