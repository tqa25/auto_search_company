# V2 Implementation Specification

> **Audience: AI coding agents.** For the human/management narrative see `docs/v2-modular-refactor-plan.md` (Vietnamese).
> **Section numbers match the Vietnamese document exactly.** Section 3.7 here == Section 3.7 there.
> **Precedence, business behaviour:** the approved Vietnamese plan governs intended business behaviour; executable code, migrations, and tests describe current behaviour. A disagreement is an incomplete defect—flag it and resolve it under §21.4 instead of silently treating either side as correct.
> **Precedence, process:** repo-root `AGENTS.md` governs *how* work is done — branching, tests, documentation duty, definition of done. Where this plan and `AGENTS.md` disagree on process, **`AGENTS.md` wins** and this plan is the stale side (§0.2).
> Last updated: 2026-08-17. Sync rules: §21.5. Changelog: §24.

## 0. Agent operating rules

Read this section before any task.

1. **Do not rewrite V1.** V2 is an incremental modification of the existing codebase **in this repository, on a working branch** (`AGENTS.md` §5) — *not* a copy into a separate `version2` directory. New code goes in `src/v2/`. Old code is deleted only after the replacement has tests and has run against real data. See §0.2.
2. **After every stage the app must run a full company end to end.** No stage may leave the system non-functional.
3. **Never call a paid API in a unit test.** Use fixtures, or V1 `replay mode` (re-runs the pipeline over stored evidence with no paid calls).
4. **One file, one job.** Target ≤200 lines. A file may call a paid API **or** write to the database, never both.
5. **A module that makes business decisions must not call an API.** A module that calls an API must not make business decisions.
6. **Read `docs/architecture/MAP.md` and `docs/implementation/STATUS.md` at session start** (`AGENTS.md` §1), then use `docs/architecture/INDEX.md` to find the file you need and open only that. Do not scan directories. See §21.
7. **Every rejecting decision must record a machine-readable `reason`.** Applies to `rejected`, `skipped`, `deferred`, `cancelled_by_policy`. See §20.
8. **Preserve URL traceability.** Every stored contact must be attributable to exactly one URL that produced it.
9. Schema changes require a forward migration plus a test against both a fresh database and the existing schema shape.
10. When a change makes a documented fact false, update the doc in the same change.

### 0.1 Numeric constants — single source of truth

Never hardcode these. Read from policy. Values below are defaults.

| Constant | Default | Section |
|---|---|---|
| `EARLY_STOP_SCORE` | 35 | §3.4 |
| `EARLY_STOP_TARGET_URLS` | 10 | §3.4 |
| `QUERY_FIELD_EVIDENCE_WEIGHT` | 0.25 | §3.3 |
| `UNCONFIRMED_FIELD_WEIGHT` | 0.5 | §3.8 |
| `RETRY_MAX_ATTEMPTS` | 3 | §11 |
| `RETRY_BASE_DELAY_S` | 2 | §11 |
| `RETRY_MAX_DELAY_S` | 60 | §11 |
| `FIRECRAWL_WAIT_FOR_MS` | 0 | §12.1 |
| `DELAY_SECONDS` | 0 | §12.1 |
| `STALE_WORKER_HEARTBEAT_MIN` | 15 | §14 |
| `LOG_RETENTION_DAYS` | 30 | §20.4 |
| `ALLOW_NAME_ONLY_QUERY` | false | §3.8 |
| `NAME_ONLY_SCORE_THRESHOLD` | 60 | §3.8 |

Every section referenced in this table exists in this document. If you add a
constant, add its section too — a pointer to a section that only exists in the
Vietnamese file is a defect (§21.5).

### 0.2 Repository reality — read before following any process instruction here

This plan was written on 2026-07-29 against a "copy V1 into a `version2`
directory" model. **That model is obsolete.** Reality as of 2026-08-17:

| The plan assumed | What is actually true |
|---|---|
| Copy the code to `<V2_ROOT>`, keep V1 read-only, build a second venv | One repository, one venv. V2 work happens on a working branch cut from the current branch (`AGENTS.md` §5) and merges back only on explicit user confirmation |
| The agent creates `AGENTS.md`, `INDEX.md`, `STATUS.md`, `check-doc-sync.sh` (§21.6 self-bootstrap) | All of them already exist, plus `docs/architecture/MAP.md`, `docs/architecture/symbols.md`, `scripts/gen-symbols.sh`, and a `PreToolUse` hook that blocks `git commit` when the gate fails. Do not recreate them; §21.6 is now repair-only |
| `STATUS.md` is a cumulative 8-section session journal | `AGENTS.md` §9: STATUS.md is a handoff note — **replaced, not appended**, kept under ~40 lines. Finished work goes to git history and `docs/implementation/work-items/` |
| "Never copy docs from V1" | V1 *is* this repository. The rule survives only as: never import docs or code from backup checkouts or other repos |
| A separate V2 architecture doc set under `docs/architecture/<module>.md` | `MAP.md` + `INDEX.md` are the authoritative pair. New per-module contracts are added *alongside* them and indexed in `INDEX.md`, they do not replace them |

Consequence for anyone executing this plan: **process comes from `AGENTS.md`;
business intent comes from this document and the Vietnamese plan.** Sections 21.1,
21.5 and 21.6 below have been rewritten to match. If you find another process
instruction here that contradicts `AGENTS.md`, `AGENTS.md` wins and the
contradiction is a defect to fix in this file.

## 1. What V2 is

V2 splits company-level processing into small independently retryable units, cuts paid-call cost, and stops producing wrong-company data. It is built by modifying V1, not replacing it.

### 1.1 Already present in V1 — reuse, do not rebuild

| Capability | V1 location |
|---|---|
| Atomic job claiming | `BEGIN IMMEDIATE` in `src/database.py` |
| Worker heartbeat, stale recovery | `src/pipeline_worker.py`, `pipeline_workers` table |
| Durable checkpoint that avoids re-paying for scrape | company status `ai_extract_pending` |
| Stop request at safe boundary | `src/company_run.py` |
| Typed error taxonomy | `src/errors.py` — `RetryableError`, `SkippableError`, `CriticalError` |
| URL scoring, blacklist domains, per-domain dedup | `src/filter_module.py` |
| Business status gate | `src/business_status.py`, `src/company_run.py:231` |
| Identity enrichment via grounded search | `src/gemini_quick_search.py` |
| Company matching / scoring | `src/company_matcher.py` |
| Replay mode, force refresh | `src/company_run.py` |
| WAL, 10s busy timeout, per-thread connections | `src/database.py` |

## 2. Confirmed V1 defects to fix

Line numbers re-verified against the working tree on **2026-08-17**. All four
defects are still present; no Stage 1 work has landed and `src/v2/` does not exist.

| # | Defect | Evidence (verified 2026-08-17) | Fix |
|---|---|---|---|
| 2.1 | Wrong-company and publisher-footer contacts | 315 scrapes into news domains; 57 contact rows with phone (measured 2026-07-29, not re-measured) | Province-bound queries (§5.4) + context slicing (§7.6) + tax-code veto (§3.7) |
| 2.2 | Retry stops at 2 attempts | `src/company_run.py:59` `max_retries = 2`; repro `attempts=2 result=failed: max_retries` | Central retry policy (§11) |
| 2.3 | Cache hit inserts duplicate rows | `src/search_module.py:214-216` — `_save_results()` runs unconditionally after `_search_with_dedup()`, whatever `cache_hit` says. `search_results` has only `idx_search_results_company_id`; no uniqueness anywhere | Remove post-cache-hit save + UNIQUE index (§10) |
| 2.4 | Fixed 3s wait on every page | `src/scrape_module.py:230,452` `waitFor: 3000`; `DELAY_SECONDS` default `3.0` at `src/config.py:178` and `pipeline_config.json:96` | `wait_for_ms: 0` **after the measurement gate**, per-domain selector only (§12.1) |
| 2.5 | Dead multi-page AI helper still in the tree | `src/ai_extractor.py:285` `_batch_short_pages`, called from nowhere | Delete it (§17.4b) |

**Duplicate-row counts are historical and must be re-measured, not quoted.**
The 85,336 groups / 89,070 excess rows figure was measured on 2026-07-29 against
an unnamed database file. Two databases exist today, and they disagree:

| Database | Rows in `search_results` | Duplicate groups | Excess rows |
|---|---:|---:|---:|
| `data/company_data_1013_companies.db` (measured 2026-08-17) | 193,588 | 19,069 | 19,946 (10.3%) |
| `data/company_data.db` (1.98 GB, mtime 2026-07-17) | not measured | not measured | not measured |

Any migration must name its target database file explicitly and re-run the audit
against that file. Never hardcode a historical count into a script or an
acceptance criterion.

## 3. Operating rules

### 3.1 Cost gates before any paid step — ordered

Evaluate in this order. Stop at the first gate that rejects.

```
1. Is the company legally dissolved?          → if yes, scrape 0 URLs, finalize (§3.6)
2. Is there a fresh cache entry for this URL? → if yes, reuse
3. Is this the top-scoring URL for its domain? → if no, reject `duplicate_domain` (§3.1)
4. Does the URL meet score + evidence rules?   → if no, reject or defer (§3.3)
5. Does a CONFIRMED tax code conflict?         → if yes, reject (§3.7)
6. Does policy allow cheap GET on this domain? → optional preflight (§7.4)
7. Does HTML/metadata contain a blacklist hit? → skip that URL only
8. Has this tier already met its stop rule?    → if yes, cancel remaining units
```

Gates 1 and 3 are the largest cost savers. Both exist in V1. Do not drop them.

### 3.2 Every significant decision lives in Source Policy

`Source Policy` is the rule file that says which domains are preferred, how many
points they add, when to scrape and when to stop (§6).

Each run stores a versioned **snapshot** of the policy plus the input as they were
at run start, so any stored result can be explained by the exact rules that
produced it. Changing the policy never deletes older results — they are marked
`stale`, meaning "produced under previous rules, may need recomputation".

### 3.3 Query-derived fields score less and cannot self-confirm

A field used to build the query is **not discarded** — it is down-weighted and cannot alone admit a URL.

| Evidence class | Weight | Can alone make `accepted` |
|---|---|---|
| Field NOT used in the query (e.g. tax code, legal representative) | 1.0 | Yes |
| Field used in the query (e.g. name, province) | `QUERY_FIELD_EVIDENCE_WEIGHT` = 0.25 | **No** |
| No identity evidence | 0 | No |

Admission rule:

```
accepted   requires: total_score >= EARLY_STOP_SCORE
                AND at least one evidence item not used in the query
deferred   when:     total_score >= EARLY_STOP_SCORE
                AND all evidence came from query-derived fields
rejected   when:     total_score < threshold, or a CONFIRMED conflict exists
```

Score-threshold-passing URLs with only query-derived evidence go to `deferred`, never `rejected`.

### 3.4 V1 rules stay until something explicitly replaces them

The default stop rule is unchanged from V1:

```
keep issuing queries until EARLY_STOP_TARGET_URLS (10) quality URLs exist
a quality URL scores at least EARLY_STOP_SCORE (35)
once the target is met, stop planning queries and begin the scrape phase
```

Both numbers live in policy and change without touching code
(V1 today: `EARLY_STOP_COUNT=10`, `EARLY_STOP_SCORE=35` in `src/config.py`,
overridable from `pipeline_config.json`).

Also unchanged unless a new business requirement *and* a replacement test exist:
the business status gate, `replay_mode`, and `force_refresh`. Export keeps the
ability to trace every contact back to its Search Result URL, and URL-level
findings stay distinguishable from company-level aggregates.

### 3.5 Identity enrichment is step 1 and is mandatory

`identity/enricher.py` calls grounded search to fill missing `tax_code`, `vietnamese_name`, `province`, `legal_representative`.

**Do not remove this step.** §5.4's fallback ("no province → query by tax code") requires a tax code, and this is the step that supplies it. 1,252 of 8,701 companies have no address at all.

- Output contacts are **company-level**, tied to their citation URLs, not to a scraped page.
- Citation URLs are excluded from later search results so the same page is not paid for twice.
- Failure is non-blocking: continue with the original input profile.
- Enforce a daily usage counter.

### 3.6 Business status gate

`identity/status_gate.py` reads a legal-source page for the company's registration status **before** the main scrape phase.

```
suspended | dissolved | tax-code-closed | awaiting-bankruptcy
  → company terminal `done`, stop_reason = business_status_inactive, 0 further URLs scraped

"not operating at registered address"
  → NOT a stop condition. Continue normally.

status unreadable
  → continue. No conclusion means no block.
```

This is a deliberate exception to §3.1's ordering: it spends one scrape to potentially save ten.

### 3.7 Tax code as veto — three outcomes, never two

#### Checksum

VN tax codes are self-validating. 10 digits; the 10th is a check digit over the first 9. 13-digit form is a 10-digit base plus a 3-digit branch suffix — validate the first 10.

```
weights = [31, 29, 23, 19, 17, 13, 7, 5, 3]
total   = sum(digit[i] * weights[i] for i in 0..8)
check   = (10 - total % 11) % 10
valid   = (check == digit[9])
```

Verified against production data: **99.9%** of 7,448 real tax codes pass; only **9.9%** of 5,687 real 10-digit phone numbers falsely pass. Worked example `0100112437`: total 102, 102 % 11 = 3, 10 − 3 = 7, matches digit 10.

#### Confidence ladder

| Step | Check | Effect |
|---|---|---|
| 1 | Shape: 10 digits, or 13 as `NNNNNNNNNN-NNN` | Filter |
| 2 | Checksum passes | Eliminates ~90% of phones |
| 3 | Label within N chars before: `MST`, `Mã số thuế`, `Mã số doanh nghiệp`, `Tax code`, `MSDN` | Strong |
| 4 | Label within N chars before: `Điện thoại`, `Hotline`, `Tel`, `Fax`, `Zalo` | It is a phone — reject as tax code |
| 5 | Tax code present in the URL path (tax-lookup sites) | Strongest. V1: `src/ai_extractor.py:30` |

#### Return type — three outcomes

`identity/taxcode.py` returns one of:

| Outcome | Condition | Caller behaviour |
|---|---|---|
| `match` | Confident tax code, equals target | Add points |
| `mismatch` | Confident tax code, differs from target | **Reject URL** |
| `unknown` | Cannot confirm the string is a tax code | **No effect.** Score on other evidence |

**`unknown` must never reject a URL.** A two-outcome design silently discards correct pages: target `3701234567`, page contains `0912345678` (a phone) → guessed as tax code → mismatch → good URL destroyed with no visible cause.

Asymmetric thresholds:

```
to ADD POINTS : steps 1 + 2 suffice.       Cost of error = one missed URL.
to REJECT     : steps 2 + 3, or step 5.    Rejection is destructive and invisible.
```

Additional constraint from §3.8: **`mismatch` may only reject when the target tax code is `confirmed`.**

#### Safety brake — veto rejects all

Even a `confirmed` target tax code may be wrong because of user input or an earlier incorrect promotion.

If one or more URLs were `accepted` or met the evidence threshold **before the tax-code check**, and tax-code veto alone would reject every such URL:

```
do not finalize those URLs as rejected
set URL state = held_for_review
halt automatic processing for the company
set reason = tax_code_veto_rejects_all
send the company to Deferred Review
```

Review must show the target code and provenance, competing codes, affected URLs, names/addresses on those pages, and the evidence that promoted the target code.

Do not trigger merely because the final URL count is zero. If no URL was plausible before veto, zero survivors is normal.

#### Unknown-format learning loop

On every `unknown`, log `domain`, the candidate string, and the failing step. Operators review periodically and promote confirmed site formats to per-domain policy rules.

### 3.8 Enriched data is `unconfirmed` and cannot veto

Enrichment fills identity fields, but verifying enrichment requires those same fields. The loop cannot be fully broken, so V2 tracks confidence and restricts authority instead.

#### Field provenance

Every identity field carries `source` and `confidence`.

| `source` | `confidence` |
|---|---|
| `user_input` | `confirmed` |
| `quick_search` | `unconfirmed` |
| `scraped` | `unconfirmed` until cross-confirmed |

#### Authority table — the critical rule

| Operation | `confirmed` | `unconfirmed` |
|---|---|---|
| Build a query | Allowed | Allowed |
| Contribute score | Full weight | × `UNCONFIRMED_FIELD_WEIGHT` = 0.5 |
| **Reject a URL (veto)** | **Allowed** | **Never** |

Rationale: one wrong enrichment result used as a veto rejects *every* correct URL for that company, with no visible cause.

#### Validating the enrichment result

Score the returned profile against the original input row using the existing import matcher (`src/company_matcher.py`): exact tax code = 100 and auto-match; name/province/address/domain/phone contribute weighted evidence; tax-code inequality scores 0; auto-match needs ≥85 and a 15-point lead.

**Anchor rule: enrichment may only fill empty fields. It must never overwrite or contradict a `user_input` field.**

```
input:  MINH AN, Bình Dương          returned: MINH AN, Bình Dương, MST 3701234567
        → accept, mark unconfirmed

input:  MINH AN, Bình Dương          returned: MINH AN, Hà Nội, MST 0101234567
        → province contradicts user_input
        → reject, reason = quick_search_conflict, keep original input
```

#### Ambiguity

Count distinct companies across the grounded citations.

```
citations → 1 company   : accept, unconfirmed
citations → ≥2 companies : do not accept
                           company → review queue, reason = identity_ambiguous
```

Never auto-select among same-named companies.

#### Promotion to `confirmed`

Promotion grants veto authority. Every supporting observation must retain provenance and pass all conditions:

1. At least two supporting pages from different domains and different `source_family` values; **or** one `authoritative_registry` page.
2. A page discovered through a query containing the candidate field cannot confirm that same field. A tax-code-query result cannot vote to promote that tax code.
3. The company name on every supporting page matches the target under the name rule below.
4. Normalize case, whitespace and punctuation, then compare evidence-window tokens. Similarity at or above policy `promotion_evidence_similarity_threshold` (default `0.85`) counts as one source because the sites may have copied each other.
5. No rival value also passes conditions 1–4. Competing qualifying tax codes produce `identity_ambiguous`, never an automatic winner.

A `source_family` groups domains likely to belong to one network or repeat one source. Different domains in one family count once.

Persist for every promotion: field/value, supporting URLs/domains/families, query IDs and query fields, evidence windows, name-match relation and score, policy version, and timestamp. If a stronger source later conflicts, demote to `unconfirmed`, mark affected results `stale`, and send the company to review.

#### A 90% similar name is not automatically the same company

Normalize case, whitespace, punctuation, Vietnamese accents, and legal-form variants before calculating similarity.

`name_similarity >= promotion_name_probable_threshold` (default `0.90`) means `probable`, not confirmed. A containing name with distinguishing tokens may identify another company: `MINH AN`, `MINH AN PHÁT`, `MINH AN GROUP`, and `ĐẦU TƯ MINH AN` are not automatically equal.

For a `probable` name to support promotion, require at least one additional strong independent field: specific address, representative, official domain, or confirmed tax code; and no strong conflict. A conflicting tax code overrides name similarity.

Store both the numeric score and relation such as `exact`, `legal_form_variant`, `target_contained_with_suffix`, `probable`, or `conflict`.

#### Name-only input — required behaviour

| Enrichment result | Action |
|---|---|
| name + province + tax code, single company | Fill both, mark `unconfirmed`, proceed |
| tax code but no province | Run tax-code-only query (province not required) |
| province but no tax code | Run name+province query; URLs need independent evidence to be `accepted` |
| multiple same-named companies | Halt company, `identity_ambiguous`, review queue |
| nothing returned | Halt company, `dependency_missing: province, tax_code`, needs-input list |

**The app does not run a name-only broad query.** It halts and reports. Optional override:

```yaml
allow_name_only_query: false
name_only_score_threshold: 60
name_only_max_queries: 1
```

## 4. Company input fields

| Field | Required | Use |
|---|---|---|
| `company_name` | Yes | Identity; query when policy selects it |
| `vietnamese_name` | No | Query placeholder |
| `tax_code` | No | Query, or evidence if not used in that query |
| `province` | No, but required for the default name query | Narrows search by locality |
| `legal_representative` | No | Query, or independent evidence |
| `blacklist_phone` + user label | No | URL and contact filtering; labels are opaque |
| user-added columns | No | Available as placeholders if policy allows |

### 4.2 Address has exactly one structured level: `province`

Only province / centrally-governed city is structured. Ward, district and street are **never** mandatory conditions and never auto-reject a URL — ward names are unstable after mergers, historical and current records disagree, and industrial-park companies often lack a street.

The full address string is retained for display and export. Operators may supply an alias table (`TP.HCM`, `HCM`, `Thành phố Hồ Chí Minh` → `Hồ Chí Minh`). If province cannot be determined, do not guess from street or industrial-park name — route the row to the needs-check list.

Measured: a naive matcher resolves province for 85.3% of 8,701 companies; 1,252 rows (14.4%) have no address at all; 85.6% have a tax code.

## 5. Query templates

Placeholders are substituted per company. Each template declares `required_fields`; a missing required field produces `skipped / reason: missing required field <name>` **with no API call** (§17.1).

```yaml
query_templates:
  - name: contact_by_vietnamese_name
    template: '"{{vietnamese_name}}" "{{province}}" ({{contact_keywords}})'
    required_fields: [vietnamese_name, province]
```

### 5.4 Name queries require province

```
name-bearing query        → MUST include {{province}}
tax-code-only query       → province not required
neither province nor tax code → no broad query; see §3.8 name-only table
```

### 5.5 Pre-flight validation

Before the first query executes, render all templates for the batch and report counts plus invalid placeholders. An unknown placeholder such as `{{provine}}` is a hard configuration error. Zero API calls before this passes.

## 6. Source policy

Per-domain / per-tier configurable: tier membership, priority, score bonus, minimum score, cheap-GET permission, scrape mode, wait selector, max workers, max attempts, cost cap.

```yaml
source_families:
  - name: yellowpages_network
    domains: [yellowpages.vn, yellowpages.com.vn, trangvangvietnam.com]

promotion_name_probable_threshold: 0.90
promotion_evidence_similarity_threshold: 0.85

tiers:
  - name: authoritative_registry
    priority: 0
    scrape_mode: scrape_all_planned
    require_tax_code_match: true
    one_url_per_domain: true
  - name: tax_directory
    priority: 1
    scrape_mode: scrape_all_planned
    require_tax_code_match: true
    one_url_per_domain: true
  - name: business_directory
    priority: 2
    scrape_mode: scrape_all_planned
    one_url_per_domain: true
  - name: job_portal
    priority: 3
    scrape_mode: stop_on_first_valid_phone
    one_url_per_domain: true
  - name: facebook
    priority: 4
    scrape_mode: stop_on_first_valid_phone
    one_url_per_domain: true
```

- `scrape_all_planned` — open every selected URL in the tier.
- `stop_on_first_valid_phone` — stop opening new URLs once a valid phone is found. Soft stop: in-flight URLs finish and persist.
- `one_url_per_domain: true` — default on for all tiers. Rejected siblings are retained with `reason = duplicate_domain`, never deleted, so export can still trace them.
- `authoritative_registry` and `tax_directory` are not equivalent. Only an official registry or a source explicitly configured as authoritative may support promotion alone. An aggregator such as Masothue remains a `tax_directory` and needs cross-confirmation.
- `require_tax_code_match: true` — authoritative and tax-directory tiers. Page tax code must equal target before a phone is accepted. This contact-acceptance rule does not make a directory self-confirming.

Adding a domain must require only a policy edit, never a code change.

## 7. Worked example and slicing

### 7.6 Context slicing

Find anchors (tax code, legal name, legal representative) in the returned markdown; keep surrounding windows; drop the rest. Example: 25,000 chars → 1,800 chars.

**Required fallback when no anchor is found** — the plan must not leave this undefined: keep main content up to a policy char limit and mark the extraction `low_confidence`. Never send the whole page.

Slicing reduces AI tokens and footer contamination. It does not refund scrape credits, so §3.1 gates run first.

## 8. Full pipeline order

| # | Step | Paid |
|---:|---|---|
| 1 | Read and normalize input | No |
| 2 | Snapshot run configuration | No |
| 3 | **Identity enrichment (grounded quick search)** | Yes |
| 4 | Plan queries | No |
| 5 | Check search cache | No |
| 6 | Search until enough quality URLs | Yes |
| 7 | Score URLs, dedup by domain, check tax code | No |
| 8 | User reviews deferred | No |
| 9 | **Business status gate** | Yes |
| 10 | Cheap GET + metadata fallback | Very cheap |
| 11 | Plan scrapes by tier | No |
| 12 | Scrape with per-domain wait | Yes |
| 13 | Slice context and extract | Yes |
| 14 | Blacklist match and aggregate | No |
| 15 | Close tier or open next tier | No |
| 16 | Compute status card | No |

Steps 3 and 9 exist in V1 and were omitted from the earlier plan draft. Do not drop them again.

## 9. Module layout

### 9.1 Rules

≤200 lines per file. Paid I/O and persistence never in the same file. Business decisions never in a file that calls an API. Every module takes inputs and returns outputs; no reading global config.

### 9.2 Tree

```
src/v2/
  policy/     loader.py  snapshot.py
  input/      normalizer.py  province.py  blacklist.py
  identity/   taxcode.py  enricher.py  status_gate.py
  query/      template.py  validator.py  planner.py
  search/     adapter.py  cache.py
  scoring/    scorer.py  evidence.py  domain_dedupe.py  classifier.py
  scrape/     planner.py  preflight.py  adapter.py
  extract/    slicer.py  extractor.py  verifier.py  blacklist_match.py  aggregator.py
  work/       unit.py  store.py  log.py
  runtime/    retry.py  resources.py  worker.py[LATER]  supervisor.py[LATER]
  service/    application.py
```

### 9.3 Module contracts

| Module | File | In | Out | Must not |
|---|---|---|---|---|
| Input Normalizer | `input/normalizer.py` | User file | Company Input Profile | Call any API |
| Province Resolver | `input/province.py` | Full address | Province + alias resolution | Infer from street/industrial-park name |
| Blacklist Loader | `input/blacklist.py` | User numbers + labels | Normalized blacklist | Reinterpret user labels |
| Policy Registry | `policy/loader.py` | Policy file | Validated policy | Apply defaults silently |
| Policy Snapshot | `policy/snapshot.py` | Policy + input | Versioned snapshot | Mutate after run start |
| Identity Enricher | `identity/enricher.py` | Company Profile | Enriched profile, all `unconfirmed` | Overwrite `user_input` fields |
| Tax Code Validator | `identity/taxcode.py` | Digit string + context | `match` / `mismatch` / `unknown` | Call any API; return a boolean |
| Business Status Gate | `identity/status_gate.py` | Legal-source page | Status classification | Treat unreadable as inactive |
| Query Template | `query/template.py` | Template + profile | Query text + fields used | Emit query with unfilled placeholder |
| Query Validator | `query/validator.py` | Templates | Error list | Allow an unknown placeholder through |
| Query Planner | `query/planner.py` | Profile + policy | Query work units | Call the search API |
| Search Adapter | `search/adapter.py` | Query work unit | Search results | Write to the database |
| Search Cache | `search/cache.py` | Fingerprint | hit / miss | **Insert any row on hit** |
| Candidate Scorer | `scoring/scorer.py` | URL + profile + policy | Score + breakdown | Hardcode any weight |
| Evidence Finder | `scoring/evidence.py` | URL + fields used in query | Independent evidence | Count query-derived fields at full weight |
| Domain Deduper | `scoring/domain_dedupe.py` | Scored URL list | One URL per domain + reasons | Delete rejected siblings |
| Candidate Classifier | `scoring/classifier.py` | Score + evidence | accepted / deferred / rejected | Reject for missing independent evidence alone |
| Cheap Preflight | `scrape/preflight.py` | URL + blacklist | pass / skip / unknown | Exceed per-domain rate limit |
| Scrape Planner | `scrape/planner.py` | URLs + tier policy | Scrape work units | Ignore tier stop mode |
| Scrape Adapter | `scrape/adapter.py` | Scrape work unit | Page content | Write to the database |
| Context Slicer | `extract/slicer.py` | Markdown + anchors | Context slice | Send whole page when no anchor found |
| Contact Extractor | `extract/extractor.py` | Context slice | Contact observation | **Cover more than one page per AI call** |
| Contact Verifier | `extract/verifier.py` | Contact + evidence text | pass / fail | Accept a value absent from the text |
| Blacklist Matcher | `extract/blacklist_match.py` | Contact + blacklist | Contact decision | Invent or alter a label |
| Contact Aggregator | `extract/aggregator.py` | Contact decisions | Company result | Merge URL-level into company-level scope |
| Work Store | `work/store.py` | Work unit | Status + claim | Claim outside a transaction |
| Work Log | `work/log.py` | Every change | History | Be used to compute current status |
| Retry Executor | `runtime/retry.py` | One API call | Attempts | Retry a 4xx |
| Resource Controller | `runtime/resources.py` | Credit, rate, budget | Resource state | Exceed a configured cost cap |
| Application Service | `service/application.py` | User request | Command or report | Duplicate logic in a UI layer |

### 9.3b Concurrency is deferred

**Do not build a new worker pool or supervisor in the first pass.** V1's mechanism works: atomic claiming, heartbeat, stale reclaim, safe-boundary stop.

| Concern | First pass | Later |
|---|---|---|
| Work queue | V1 `pipeline_jobs` | Fine-grained work units |
| Claiming, heartbeat | V1 unchanged | Same mechanism, finer granularity |
| Pause / resume / drain / shutdown | V1 unchanged | Extract to `runtime/supervisor.py` |
| Worker count | As today | Policy-driven |

**All new `src/v2/` business modules must be concurrency-agnostic** — inputs in, outputs out — so switching workers later requires no business-module change.

### 9.4 Status lives on the row

Current status is stored on the work-unit row. `Work Log` is for history and explanation only — **not** the source of truth for status. Do not fold an event stream to compute status.

Claiming reuses V1's proven pattern:

```sql
UPDATE work_units SET owner = :worker, claimed_at = :now
WHERE id = :id AND status = 'pending'
```

## 10. Duplicate prevention

Excess rows are duplicates **within a single company**, not across companies.
Counts must be re-measured per database at migration time (§2).

Three changes:

1. On cache hit: return the cached result, emit a `cache_reused` event with cost 0, and **do not call the save function**.
2. Normalize the URL at **one** boundary before it reaches the database, on every insert path.
3. Add a UNIQUE constraint over `(company_id, search_query, <normalized url>)` on `search_results`.

A cleanup script must remove existing duplicates before the constraint can be added (Stage 1 §5.5).

### 10.1 The constraint must be over the normalized URL, not the raw one

An index on the raw `url` column does **not** enforce the identity this plan
defines. Two rows whose normalized forms are equal but whose stored strings
differ (`http://X.vn/a/` vs `https://x.vn/a?utm_source=…`) both survive it, and
the duplicate bug returns through the back door for every row written before
normalization existed.

Pick one and state it in the migration:

- **Preferred** — add a `normalized_url` column, populate it for the whole table
  using the same production function (`src/utils.py::normalize_url`), and build
  the UNIQUE index on `(company_id, search_query, normalized_url)`. A generated
  column is acceptable only if the normalization is expressible in SQL, which
  `normalize_url` currently is not — so populate it in Python.
- **Acceptable** — rewrite `url` in place to its normalized form for **every**
  row, not only the rows in duplicate groups, then index `(company_id,
  search_query, url)`. Loses the original string; only choose this if nothing
  needs the raw URL.

Whichever is chosen, the post-migration audit must prove that re-normalizing the
whole table produces zero new duplicate groups. Normalizing only the rows being
deduplicated is the failure mode this section exists to prevent.

### 10.2 Downstream effects that must be checked in the same change

Collapsing duplicate `search_results` rows changes ids that other tables point at.

- `filtered_links.search_result_id` is repointed to the canonical row. But
  `filtered_links` **itself** accumulates duplicate URLs on every run
  (`MAP.md` §9, trap 4) — this plan does not deduplicate it, and must not be read
  as having done so.
- `src/completion_audit.py` deliberately joins scrape candidates to results **by
  `url`, not by `filtered_link_id`**, precisely because of that accumulation.
  Verify after migration that strict completion still reaches `done` for a sample
  of already-`done` companies. A regression here does not lose data — it re-queues
  companies forever, which is worse because it silently spends money.
- Export and the dashboard must still resolve every contact back to one search
  result (§0 rule 8).

**Rejected design — one shared search artifact referenced by many companies.** Measured: only 164 of 21,041 distinct queries (0.8%) are used by more than one company; 2.1% of rows. It targets 2.1% while the real bug is 8.5%, and it adds two risks: per-company per-URL decisions have nowhere to live (requiring a third table identical in shape to today's), and SQLite foreign-key enforcement is not enabled per connection, so deleting an artifact orphans many companies' evidence.

## 11. Retry policy

```yaml
retry:
  max_attempts: 3          # total calls, not extra retries
  base_delay_seconds: 2
  max_delay_seconds: 60
  honor_retry_after: true
  jitter: true
```

`max_attempts: 3` = one initial call plus up to two retries.

| Status | Meaning | Retry |
|---|---|---|
| `2xx` | Success | — |
| `400` | Malformed request | **No** |
| `401` | Bad/expired API key | **No** |
| `402` | Out of credit | **No** — set resources `credit_exhausted`, abort batch |
| `408` | Request timeout | Yes |
| `429` | Rate limited | Yes — wait exactly `Retry-After`, and reduce concurrency |
| `500` `502` `503` `504` | Server-side failure | Yes |
| connection timeout | No response | Yes |

Rule of thumb: **4xx is the caller's fault and will not fix itself; 5xx is the provider's and may.**

All three V1 root causes must be fixed together: the outer loop cap, unclassified 5xx, and lower layers that swallow transient errors and return empty success-shaped results. **A module must not catch a network error and return an empty list.**

Every attempt is logged. Retry re-runs only the failed API operation, never the whole company. A shutdown signal must interrupt backoff sleep.

### 11.1 Complete inventory of today's retry and throttle owners

Six places currently decide what happens after a failed or throttled call. The
retry executor replaces the first five; the sixth stays but must be kept out of
the retry path. **Missing one of these produces nested retries — three "attempts"
becoming nine HTTP requests.** Verified 2026-08-17:

| Owner | What it does today | After Stage 1 |
|---|---|---|
| `src/connection_pool.py:75-78` | `urllib3` `Retry(total=max_retries, status_forcelist=[500, 502, 504])` — **503 is not in the list** | Status-based retry disabled; keeps pooling and timeouts only |
| `src/search_module.py:606-679` | Own loop, `max_retries=3`, fixed 60s wait on 429 | Delegates to the executor |
| `src/scrape_module.py:235,462` | Two own loops, `max_retries = 3` | Delegates to the executor |
| `src/ai_extractor.py:371-545` | Own loop, `max_retries = 3`, special 60s path for Gemini 503, then returns `{"status": "failed", "reason": "max_retries"}` | Delegates to the executor; must stop converting failure into a success-shaped dict |
| `src/company_run.py:59` | Whole-company retry, `max_retries = 2` | Removed as a retry layer (§11.2) |
| `src/rate_limiter.py` (`AdaptiveRateLimiter`) | **Throttling, not retry**: 429 doubles the delay, 403/503 jump to max delay plus a 5-minute cooldown | Kept. It shapes the delay *before* a call; it must never also decide whether to repeat one |

Note the disagreement this table exposes: a 503 is retried by `ai_extractor`
after 60s, ignored by `connection_pool`'s forcelist, and treated as a 5-minute
cooldown by `rate_limiter`. Unifying these three is the actual work of §11.

### 11.2 When an operation exhausts its attempts, the company status must be defined

Removing the whole-company retry leaves a question this plan previously did not
answer: what status does the company get? Leaving it implicit is dangerous
because `src/completion_audit.py` rewinds companies that are not strictly
complete, so a wrong choice re-queues a company forever.

Required mapping, expressed against V1's `Pipeline.STATUS_FLOW` (`MAP.md` §3):

| Operation that exhausted | Company outcome |
|---|---|
| Search or scrape operation | `failed` — resumes from the start of that step. Scraped rows already persisted are kept and reused |
| AI extraction | **Preserve `ai_extract_pending`.** Scraping is paid for and saved; never rewind past this checkpoint |
| `CriticalError` (401, 402, DB invariant) | Preserve the current checkpoint, abort the batch — V1 behaviour, unchanged |

Every one of these transitions needs a test asserting the resulting
`companies.status`, not merely the raised exception type.

## 12. Scrape throughput controls

```yaml
firecrawl:
  wait_for_ms: 0
  only_main_content: true
  max_age_ms: policy_controlled
  max_concurrency: policy_controlled
```

**12.1 `wait_for_ms`** — extra wait *added after* Firecrawl's own readiness wait. V1's 3,000 ms costs ~60s per 20-URL company (~16h per 1,000 companies). Target default 0; per-domain selector waits only for genuinely JS-dependent sites. Same for `DELAY_SECONDS`, the sleep between sequential URLs.

**"For no benefit" is a hypothesis, not a measurement.** This is the one change
in Stage 1 that can silently *reduce* data quality: a JS-heavy page that used the
3 seconds to finish rendering will now return a shorter body, and the loss shows
up as a missing phone number three steps later, not as an error. Checking "no
`sleep` was called" does not detect it.

**Measurement gate — required before the default changes:**

1. Pick ≥50 URLs already in `scraped_pages`, spread across the domain families
   actually seen in production (registry, tax directory, business directory, job
   portal, Facebook), deliberately including the JS-heaviest ones.
2. Scrape each twice into a scratch database: once at `wait_for_ms: 3000`, once at `0`.
3. Compare per URL: HTTP outcome, markdown length, and the count of fields
   `src/ai_extractor.py` can extract from it.
4. Ship default 0 only if no domain family loses content. Any family that does
   gets a per-domain wait or selector policy entry — and that entry, not the
   global default, is the fix.
5. Record the comparison table as the acceptance evidence for this work item.

This gate spends Firecrawl credits and therefore needs explicit user approval
before it runs (§0 rule 3 forbids paid calls in tests; this is a measured
experiment, not a test).

**12.2 `only_main_content`** — drops header/menu/footer. Typical 25,000 → 8,000 chars. Fewer AI tokens and less publisher-footer contamination. First defence layer; slicing (§7.6) is the second.

**12.3 `max_age_ms`** — max acceptable age of Firecrawl's stored page copy.

| Source kind | Setting | Reason |
|---|---|---|
| Business directory | 7–30 days | Phones rarely change |
| Job portal | 1–3 days | Postings churn |
| Legal source for status gate | 0 | Needs current status |

**12.4 `max_concurrency`** — adaptive, not fixed. On `429`: honour `Retry-After`, halve concurrency; after a run of successes, increase gradually.

```
8 concurrent → 429 (retry-after 30) → wait 30s → drop to 4
→ 20 consecutive successes → 5 → 6 → on 429 drop again
```

**12.5 Cheap GET limits** — preflight requests originate from the operator's own IP, not Firecrawl's. Sites can block that IP. Separate, much stricter limits:

```yaml
cheap_get:
  max_concurrent_per_domain: 1
  min_delay_between_requests_ms: 1000
```

## 13. Deferred review screen — LATER (§22)

For URLs that may be correct but lack enough evidence for the app to spend money unilaterally. Each row shows: company + province; URL, domain, tier; search title and description; the query that produced it; which fields that query used; evidence found; total score and breakdown; defer reason; GET/metadata result if checked; estimated scrape cost.

Actions, single or bulk: `Scrape`, `Skip`, `Keep deferred`. Decisions persist; resume does not re-ask about a decided URL.

**An unreviewed queue blocks only its own company or tier at that checkpoint. All other companies keep running.**

## 14. Stop, pause, resume

| Command | Behaviour |
|---|---|
| Pause scheduling | Issue no new work; in-flight reaches a safe point |
| Resume | Workers take pending units again |
| Drain and shutdown | Stop intake, let in-flight persist, then exit |
| Emergency shutdown | Stop now; terminate after the safety window |

Lease + heartbeat: a dead worker's heartbeat stops, the lease expires, and the unit returns to `pending`. `Runtime Supervisor` verifies real processes, PIDs, heartbeats and leases — a status column changing is not proof of a stop. First pass uses V1's mechanism (§9.3b).

## 15. Status card

Status is read from stored work-unit state, not recomputed from history. Six independent axes: execution, coverage, contact, resources, stop reason, freshness. `completed` means all planned units reached a terminal state — it does **not** mean a contact was found. `cancelled_by_policy` is a valid terminal state.

## 16. Incremental roadmap

Each stage must end with the app running a full company. Verify with V1 replay mode on a fixed 30-company sample.

| Stage | Work | Acceptance |
|---|---|---|
| 0 | Pick 30-company sample (same-name/different-province, news domain, timeout, cache hit, blacklist, dissolved company, missing province). Record V1 results | V1 baseline exists |
| 1 | Three cheap fixes: `waitFor`/`DELAY_SECONDS` → 0; cache-hit save removed + dedupe + UNIQUE index; minimal retry executor with `max_attempts` + 5xx classification | No fixed wait; cache hit adds no rows; `503,503,200` succeeds on attempt 3 |
| 2 | Non-API modules: `input/`, `policy/`, `identity/taxcode.py`. Flow unchanged | Unit-testable in isolation; tax code returns 3 outcomes |
| 3 | `query/` + province coverage measurement + pre-flight preview | Name queries always carry province; bad placeholder caught before any API call |
| 4 | `scoring/` — keep V1 weights, add domain dedup and tax-code veto | Same input → same decision; one URL per domain |
| 5 | `extract/slicer.py`, `extract/verifier.py` | No publisher-footer contacts; every contact present in stored evidence text |
| 6 | Extend Stage 1's `runtime/retry.py`, add `runtime/resources.py`, cost/rate budgets, and remove leftover legacy retry code | 402 no retry; 429 honours `Retry-After`; shutdown interrupts backoff |
| 7 | `work/` — company job → fine-grained units, **on V1's existing claiming/heartbeat** | Kill and restart re-runs only unfinished units |
| 8 | **LATER** `runtime/worker.py`, `runtime/supervisor.py` — only if throughput proves insufficient (§9.3b) | Concurrent workers never double-claim; stop kills real processes |
| 9 | Move domains, tiers, scores, query templates into versioned policy | New domain needs no code change |
| 10 | Deferred review API + screen | Review blocks no other company |
| 11 | CLI, API, dashboard all call `service/application.py` | Three interfaces, identical results and controls |
| 12 | V1/V2 parallel run, separate databases. **Doubles paid API spend for the sample** — get an explicit budget and user approval first; it is not covered by any earlier estimate | Cost, accuracy, duration report |
| 13 | Cut over; V1 read-only | Documented rollback and resume-from-checkpoint |

Stage 0 is a prerequisite for Stage 1, not an optional warm-up: Stage 1's replay
gate compares against the Stage 0 baseline, and without it "no regression" cannot
be asserted. As of 2026-08-17 no Stage 0 baseline exists in
`docs/implementation/work-items/`.

### 16.1 Safe stopping points

This plan is 13 stages long and the operator's verification time is the binding
constraint (§22). The realistic risk is not failure — it is stopping halfway and
leaving `src/` and `src/v2/` each holding half of one decision.

A stage boundary is a **safe stop** only if the system at that point has no
duplicated business logic. Stopping anywhere else means finishing the current
stage or reverting it.

| After stage | Safe stop? | State if you stop here |
|---|---|---|
| 1 | **Yes — the recommended stop** | Pure V1 with four defects fixed. No `src/v2/` business logic to keep in sync |
| 2–3 | Yes | New modules exist but the old path still owns the decision; delete `src/v2/` to revert |
| 4 | **No** | Scoring exists in two places. Either the old scorer is gone or the new one is unused — never both live |
| 5 | Yes | Slicing/verification are additive in front of extraction |
| 6 | **No** | Retry ownership must be single. Half-migrated retry is worse than V1's |
| 7 | **No** | Work units and company jobs cannot both own status |
| 9, 11 | Yes | Policy/interface consolidation is complete or not started |

Before starting a stage marked **No**, decide whether there is capacity to finish
it. Recording that decision in `STATUS.md` is part of starting the stage.

Stage 1 stands alone: if the project stops there, the system is already better than V1.

Detailed execution order, commits, migration, rollback, and test gates: `docs/v2-stage1-critical-fixes-implementation-plan.md`.

## 17. Mandatory tests

No test may call a paid API.

### 17.1 Query and identity

1. Two same-named companies in different provinces produce different queries.
2. A name query missing province is blocked **before the API call** — not filtered afterwards.
3. A tax-code-only query runs without province.
4. An invalid placeholder is reported **before the first query executes**.
5. A query-derived field earns reduced points and cannot alone make a URL `accepted`.
6. Ward, street and industrial-park names are never mandatory conditions.
7. An enrichment-derived (`unconfirmed`) field never rejects a URL.
8. Multiple same-named companies from enrichment → review queue, `identity_ambiguous`.

### 17.1b Tax code

1. Real tax code `0100112437` passes the checksum.
2. Phone `0912345678` is not accepted as a tax code without an `MST`-class label.
3. An unconfirmable digit string returns `unknown`, and `unknown` does not reject the URL.
4. A tax-lookup URL whose path tax code differs from target rejects immediately.
5. A matching tax code adds points only if it was not the query's primary field.
6. The 13-digit `...-001` form is parsed correctly.
7. A page discovered through a tax-code query cannot promote that same tax code.
8. Two domains in one `source_family` count as one promotion source.
9. Near-identical evidence windows count as one promotion source.
10. A name with ≥90% similarity but a distinguishing token such as `PHÁT` or `GROUP` cannot promote alone.
11. Two tax codes that both qualify produce `identity_ambiguous`, not an automatic winner.
12. If tax-code veto alone removes every previously plausible URL, URLs become `held_for_review` and company reason is `tax_code_veto_rejects_all`.
13. If no URL was plausible before veto, the all-rejected brake does not trigger.

### 17.1c Enrichment and status

1. A company with neither province nor tax code is enriched before query planning.
2. Enrichment failure is non-blocking; the run continues on original input.
3. Enrichment contacts are stored at company level, not URL level.
4. URLs cited by enrichment are not searched or scraped again.
5. A dissolved company finishes with 0 URLs scraped.
6. "Not operating at registered address" runs normally.
7. Unreadable status does not block the company.

### 17.1d Domain dedup

1. Ten URLs on one domain open exactly one — the highest scoring.
2. The nine rejected are retained with `reason = duplicate_domain`.
3. Export can still trace domain-deduped URLs.

### 17.2 Publisher pages and slicing

1. A publisher's footer contact is never stored as the company's contact.
2. A tax code past character 15,000 is still found.
3. Every stored contact appears in its stored evidence text.
4. A page with a publish date keeps that exact date.
5. A page without a publish date does not get the scrape date substituted.
6. No anchor found → defined fallback applies and the result is marked `low_confidence`.

### 17.3 Retry

1. `503, 503, 200` → exactly 3 attempts, succeeds.
2. `timeout, timeout, 200` → exactly 3 attempts, succeeds.
3. `402` → 0 retries, resources become `credit_exhausted`.
4. `401` → 0 retries, reports an API-key error.
5. `400` → 0 retries.
6. `429` → waits exactly `Retry-After`, no guessing.
7. Shutdown interrupts backoff sleep; no waiting the full 60s to exit.
8. Retry creates no duplicate rows.
9. Exhausting a **search or scrape** operation leaves `companies.status = 'failed'` (§11.2).
10. Exhausting **AI extraction** leaves `companies.status = 'ai_extract_pending'` — the paid scrape checkpoint survives (§11.2).
11. No operation produces more HTTP requests than `max_attempts`, with `connection_pool`'s own status retry disabled (§11.1).
12. A Gemini 503 is handled by exactly one owner; `AdaptiveRateLimiter` shapes the delay but never repeats the call.

Tests 1 and 2 target the current V1 defect directly. Tests 9–12 exist because
removing the whole-company retry is only safe if the resulting status is defined.

### 17.4 Cache and workers

1. 100 cache hits on one query add zero rows to `search_results`.
2. Re-inserting the same `(company_id, search_query, normalized url)` is refused by the database.
3. Two URLs that differ only in scheme, `www.`, trailing slash or `utm_*` are one row, not two (§10.1).
4. Re-normalizing every row after migration produces zero new duplicate groups (§10.1).
5. No `filtered_links` row points at a deleted search result, and strict completion still returns `done` for a company that was `done` before migration (§10.2).
6. Two workers saving one result → exactly one accepted, both receive the canonical id.
7. A worker dying mid-unit returns the unit to `pending` after lease expiry.
8. Resume does not re-run completed units.

### 17.4b One AI call == one URL

**Regression lock for a defect that already happened.**

A helper batched 2–3 short pages into a single Gemini call and wrote the returned result to *every* page in the batch — so URL 1's phone was attributed to URLs 2 and 3 of the same company. The database then showed three URLs with contacts when only one had them, silently breaking source traceability.

Current state: fixed — the loop calls one page at a time (`src/ai_extractor.py:577`, with an explicit comment at line 581). **But the dead helper `_batch_short_pages` still exists at `src/ai_extractor.py:285` and is called from nowhere.** An agent told to "reduce AI cost" will find it and rewire it.

Required:

1. **Delete `_batch_short_pages` in V2.**
2. Add these tests:
   - One AI call maps to exactly one `scraped_page_id`.
   - Three URLs of one company where only URL 1 has a phone → after extraction only URL 1 has a contact; URLs 2 and 3 are empty.
   - Every stored phone appears in the markdown of the page it is attributed to.
   - No function groups multiple pages into one AI call.
   - Company-level enrichment contacts are not stored as URL-level contacts.

Invariant: **a contact must always be traceable to exactly one URL that produced it.** To reduce AI cost, shorten per-page input via §7.6 slicing — never merge pages.

### 17.5 Speed and control

1. Static pages incur no `sleep(3)` or `waitFor: 3000`.
2. Only domains with a selector policy receive a wait action.
3. On 429, concurrency decreases per policy.
4. Drain-and-shutdown leaves no worker process.
5. Emergency shutdown issues no new API call after the safety window.

## 18. V1 vs V2 comparison metrics

Same sample, separate databases. Report: on-target URL rate; contacts with correct-company evidence text; footer/publisher contacts rejected; search calls per company; scrape credits per company; AI tokens per valid contact; median duration; p95 duration; double-run work units; cache-caused duplicate rows; resume-without-rework rate; shutdown-to-zero-workers time.

V2 replaces V1 only when it is no worse at finding needed contacts, clearly reduces wrong-company URLs and wrong-source contacts, reduces average search/scrape/AI cost, and passes every mandatory test.

## 19. Out of scope for the first pass

No user-facing choice between Gemini and OpenRouter — build one AI gateway so a provider can be added later without touching the pipeline. No automatic classification of phone numbers into wrong/invalid/same; the app reads user-supplied labels, normalizes, and compares.

**Reuse V1 `replay mode`** as the primary test harness for §17 and §18 — it re-runs the full flow over stored evidence with no paid calls. Keep `force refresh` for targeted re-collection.

## 20. Live decision log

Purpose: diagnose a wrong result **without reading code**.

V1's `pipeline_logs` records what ran but not *why* a decision was made. When a correct URL is rejected, the current log does not say at which step or for what reason.

### 20.2 Schema

| Column | Example |
|---|---|
| `time` | `2026-07-28 14:32:07` (Asia/Ho_Chi_Minh) |
| `company_id` | `4821` |
| `work_unit_id` | `wu_4821_scrape_7` |
| `module` | `scoring/domain_dedupe.py` |
| `action` | `dedupe_domain` |
| `decision` | `rejected` |
| `reason` | `duplicate_domain: yellowpages.vn already kept at score 62` |
| `target` | the URL or entity affected |
| `cost` | `0` |
| `duration_ms` | `4` |

**`reason` is mandatory for every `rejected`, `skipped`, `deferred`, `cancelled_by_policy`.**

### 20.3 Reading a trace

```
14:32:01  identity/enricher      quick_search    success    tax_code=3701234567 (unconfirmed)
14:32:03  query/planner          plan_query      created    "MINH AN" "Bình Dương" (contact)
14:32:05  search/cache           cache_lookup    hit        saved 1 search credit
14:32:06  scoring/scorer         score_url       62         yellowpages.vn/minh-an
14:32:06  scoring/domain_dedupe  dedupe_domain   rejected   duplicate_domain: kept score 62
14:32:07  identity/status_gate   status_check    inactive   dissolved → halt company
```

### 20.4 Requirements

1. Stream live over V1's existing `/ws/logs`.
2. Index `company_id` and `work_unit_id`; the screen must stay fast as the table grows.
3. Retain detail `LOG_RETENTION_DAYS` = 30, roll aggregates into a summary table before deleting. Without rotation this table outgrows the real data.

## 21. Architecture record for agents

### 21.1 The document set — already built, do not rebuild

Every file this section once asked an agent to create now exists. Their current
roles are fixed by `AGENTS.md`, not by this plan:

| File | Purpose | Owner of its rules |
|---|---|---|
| `AGENTS.md` (repo root) | Hard process rules: session bootstrap, branch per code change, docs in the same commit, definition of done | `AGENTS.md` itself |
| `docs/architecture/MAP.md` | How the system works now. Read first, every session | `AGENTS.md` §1, §7, §10 |
| `docs/architecture/INDEX.md` | "To change X, read file Y, verify with test Z" | `AGENTS.md` §2, §7 |
| `docs/architecture/symbols.md` | Generated symbol → `file:line` table (`scripts/gen-symbols.sh`) | `AGENTS.md` §7 |
| `docs/architecture/<module>.md` | One module contract, max one page — added per module as V2 modules appear, and indexed in `INDEX.md` | this plan, §21.3 |
| `docs/implementation/STATUS.md` | Handoff note: what is in flight, what was decided, the single next action, what is blocked | **`AGENTS.md` §9** |
| `docs/implementation/work-items/` | One file per work item: owner, file scope, acceptance criteria, evidence | this plan, §21.6 |
| `scripts/check-doc-sync.sh` + `.claude/hooks/precommit-doc-sync.sh` | Enforced gate; blocks `git commit` when documentation did not move with code | `AGENTS.md` §8 |

Two rules from the original plan survive and still matter:

- `AGENTS.md` holds stable instructions only. Mutable progress goes to
  `STATUS.md`, so a temporary note can never be mistaken for a permanent rule.
- `MAP.md` and `INDEX.md` are authoritative. When any other document — including
  this plan — contradicts them, the code decides and the loser gets fixed.

**`STATUS.md` format is governed by `AGENTS.md` §9, not by this plan:** replace its
contents rather than appending, keep it under ~40 lines, and let git history and
`work-items/` hold everything finished. The 8-heading session-journal template
that earlier versions of §21.6 prescribed is withdrawn — it produced exactly the
scrollback that `AGENTS.md` §9 exists to prevent.

### 21.2 Routing table

The main token saver. Do not scan `src/`.

The live routing table is **`docs/architecture/INDEX.md`** — it covers today's V1
modules and is kept current by `AGENTS.md` §7. Do not maintain a competing copy
here.

New V2 modules get a row in `INDEX.md` as they are created, in the same commit
that creates them. Planned rows, for reference only:

```
| To change                          | Read                            | Test                    |
|------------------------------------|---------------------------------|-------------------------|
| Tax code recognition               | src/v2/identity/taxcode.py      | tests/test_taxcode.py   |
| A domain's score                   | policy/sources.yaml             | tests/test_scorer.py    |
| Query formulas                     | policy/queries.yaml             | tests/test_query.py     |
| One URL per domain                 | src/v2/scoring/domain_dedupe.py | tests/test_dedupe.py    |
| Trimming content before the AI call| src/v2/extract/slicer.py        | tests/test_slicer.py    |
| API retry rules                    | src/v2/runtime/retry.py         | tests/test_retry.py     |
```

### 21.3 Module contract format

```
# scoring/domain_dedupe.py
Purpose:   Keep only the highest-scoring URL per domain.
Input:     list of URLs with: url, domain, score
Output:    same list plus: keep (bool), reason
Must not:  call an API, write to the database, read global config
Invariants:
  - Rejected URLs are still returned, with reason = "duplicate_domain".
  - On a score tie, keep the higher source_priority.
Test: tests/test_dedupe.py
```

The Input / Output / Must not triple is the most important part — it bounds the module without reading surrounding code.

### 21.4 Maintenance

Code change that falsifies a documented line updates the doc in the same change. Docs carry contracts and invariants, never copied code.

**A code/doc disagreement is an incomplete defect; do not silently assume either side is correct.**

| Question | Authority |
|---|---|
| What does the current app actually do? | Executable code, migrations, tests |
| What should the business do? | Approved Vietnamese plan and approved user decisions |
| What interface did a module promise? | Module contract and tests |
| Was the difference intentional? | Approved changelog, ADR, or issue |

Example: if the plan forbids an `unconfirmed` veto but code allows one, code accurately describes current behaviour but that behaviour is a bug. Fix code and add a regression test; do not edit the plan to legitimize the bug.

#### Definition of Done

The change is incomplete until every applicable row is updated in the same change:

This table extends `AGENTS.md` §7; it does not replace it. Where both apply, do both.

| Changed | Required companion |
|---|---|
| `src/v2/<area>/<module>.py` | Corresponding `docs/architecture/` contract and related test |
| New file under `src/v2/` | New row in `docs/architecture/INDEX.md` |
| A pipeline step, a `companies.status` value, a table, an entry point | `docs/architecture/MAP.md`, affected section only (`AGENTS.md` §7) |
| A public class or function added, moved, or renamed | re-run `./scripts/gen-symbols.sh` |
| Policy key | `docs/architecture/policy.md` and policy test |
| Table, column, or index | `docs/architecture/schema.md`, migration, and test. Note: schema changes go in `src/database.py::init_db`, **not** `src/migrations.py`, whose registry is empty (`MAP.md` §5) |
| Business rule or numeric threshold | Both plans, §24 changelogs, and regression test |
| End or hand off an implementation session | `docs/implementation/STATUS.md`, rewritten per `AGENTS.md` §9 |

`scripts/check-doc-sync.sh` exists and is wired to `.claude/hooks/precommit-doc-sync.sh`,
which blocks `git commit` when the gate fails. It fails open, so a block always
means the gate genuinely failed. Do not disable it; fix the documentation
(`AGENTS.md` §8).

Passing the gate is necessary, not sufficient — it cannot tell whether what you
wrote is true. Do not keep the only checker in `.git/hooks/pre-commit`:
`.git/hooks` is not committed and other checkouts do not receive it.

#### Graphify usage

Read `INDEX.md` and module contracts per task. Use Graphify only when the index is insufficient, for onboarding/large refactors, or at milestone boundaries; do not rebuild it after every small edit.

Every graph build/read must include only project paths such as `src/`, `dashboard/`, `scripts/`, `tests/`, and exclude `graphify/`, `version1-lasted/`, dependencies and vendor code. Without filtering, an agent may learn the tool or V1 architecture instead of V2.

### 21.5 Two-document sync rules

| Version | File | Audience | Status |
|---|---|---|---|
| Vietnamese | `docs/v2-modular-refactor-plan.md` | Humans, management | Authoritative for business intent |
| English | `docs/v2-modular-refactor-plan.en.md` | AI agents | Condensed normative spec |
| Korean | `docs/v2-modular-refactor-plan.ko.md` | Reference translation | **Not synchronized. Do not treat as current** |

The English version is a condensed normative spec, not a sentence-by-sentence translation.

1. Identical section numbering. §3.7 here == §3.7 there. A cross-reference in one file must resolve in that same file (§0.1).
2. A business-decision change edits **both** the Vietnamese and English files in the same change.
3. Every numeric constant is defined once (§0.1) and repeated verbatim in the other document.
4. **On conflict, the Vietnamese version wins** — it is the one the user approves.
5. Both documents end with a changelog table listing date and sections touched.
6. The Korean file is a point-in-time translation. Either re-derive it from the Vietnamese file when the business decisions settle, or delete it — a third copy that silently drifts is worse than no copy.

**Open sync debt (2026-08-17):** the corrections in this revision — §0.2, §2, §3.2,
§3.4, §10.1, §10.2, §11.1, §11.2, §12.1, §16.1, §21 — were applied to this file
and to `docs/v2-stage1-critical-fixes-implementation-plan.md` only. The
Vietnamese and Korean plans still carry the superseded text. Reconcile the
Vietnamese file before the next business-decision change to it.

### 21.6 Cross-agent and cross-session implementation handoff

Goal: a new agent or chat session can continue immediately without guessing what was done, while still verifying actual repository state before trusting the handoff.

#### Bootstrap is repair-only

The bootstrap set is complete (§21.1). An agent's job is no longer to create it —
only to notice if something has gone missing and restore it. `scripts/check-doc-sync.sh`
already fails when a required path is absent, so this check is automatic.

If a required file *is* missing:

1. Never overwrite an existing file. Preserve its content and add only the missing sections.
2. Use exact repository paths; never copy docs from backup checkouts, Graphify output, or another repository (`AGENTS.md` §3).
3. The Vietnamese V2 plan governs business intent. Do not invent modules, states, or decisions without evidence.
4. Restore `INDEX.md` rows only from mappings verified against the repository. Mark uncertain entries `unverified`.
5. Rebuild `STATUS.md` from `git status`, the code as it actually is, and tests actually run. Never infer `completed` from a plan.
6. Note the repair in `STATUS.md` with the verification command used.

For read-only explanation, review, or diagnosis: report the gap, change nothing.

#### Implementation status file

Format and length are governed by **`AGENTS.md` §9**: a handoff note, contents
replaced rather than appended, under ~40 lines, answering only what is in flight,
what was just decided, the single next executable action, and what is blocked.
`scripts/check-doc-sync.sh` enforces the `## Current handoff` and `## Verification`
headings.

`Next action` must be executable — "write failing test 7 in `tests/test_taxcode.py`",
never "continue stage 2".

Anything finished belongs in git history and in
`docs/implementation/work-items/<work-item-id>.md`, which is where per-item
owner, file scope, acceptance criteria, and evidence live. That is the file to
grow; `STATUS.md` stays short.

#### Session-start protocol

Follows `AGENTS.md` §1: read `docs/architecture/MAP.md`, then
`docs/implementation/STATUS.md`. Then, for a code-changing task:

1. Run `git status`. Uncommitted changes that are not yours mean stop and ask (`AGENTS.md` §5).
2. Verify STATUS against reality — the code, git, and the tests it claims were run.
3. If STATUS disagrees with reality, repair STATUS before relying on it.
4. Start from `Next action`; do not redo work recorded as verified without contrary evidence.
5. Cut the working branch before the first edit.

#### During work and before ending

Do not edit status after every code line. Update at meaningful checkpoints: a
work item changes state, a test group changes state, a decision is made, a
blocker appears, or the session ends.

Before ending or handoff, `STATUS.md` must show the behaviour that changed, the
commands run with their exact results (`not run` when verification was skipped,
and why), remaining failures and blockers, and one concrete next action. The
detail behind each of those goes in the work-item file.

Never mark work complete merely because code was edited (`AGENTS.md` §8).
Acceptance criteria must pass and evidence must exist. An interrupted session
stays in progress; never guess the outcome.

#### Parallel agents

Do not let several agents freely edit one status paragraph. Use:

```text
docs/implementation/STATUS.md
docs/implementation/work-items/<work-item-id>.md
```

Each work item has one owner at a time, explicit file scope, acceptance criteria, evidence, and state:

```text
pending → in_progress → completed
                    ↘ blocked
```

An agent edits only its owned work-item file. `STATUS.md` aggregates and links to work items; the coordinating agent/human updates the aggregate to avoid conflicts.

#### Stale-status protection

`STATUS.md` is a handoff aid, not final evidence. Verify important claims through code, Git, and tests. If it says “tests pass” without a command/result, or code changed after its timestamp, treat the claim as unverified.

## 22. Priority and effort

Context: the operator has basic IT knowledge, an AI agent writes the code, and the operator verifies results manually. **Verification, not code generation, is the bottleneck.**

| Level | Meaning |
|---|---|
| **MUST** | Without it V2 is not better than V1, or it produces wrong data |
| **SHOULD** | Clear cost or error reduction, but deferrable |
| **LATER** | Safely omitted from the first pass |

| Work | Level | AI sessions | Operator verification |
|---|---|---|---|
| Remove `waitFor: 3000` / `DELAY_SECONDS` | **MUST** | 1 | 1h |
| Cache-hit fix + dedupe 89,070 rows + UNIQUE index | **MUST** | 1 | 3h |
| Retry: `max_attempts`, 4xx/5xx classification | **MUST** | 1–2 | 3h |
| Tax code module (checksum, 3 outcomes) | **MUST** | 1 | 2h |
| Keep enrichment + `unconfirmed` marking | **MUST** | 1–2 | 4h |
| Keep business status gate | **MUST** | 1 | 3h |
| Domain dedup | **MUST** | 1 | 3h |
| Live log with `reason` | **MUST** | 1–2 | 2h |
| `AGENTS.md` + `INDEX.md` + module contracts + `STATUS.md` | **MUST** | 1 | 1h |
| Province-required queries + pre-flight preview | **MUST** | 2 | 5h |
| "One AI call == one URL" regression lock | **MUST** | 1 | 1h |
| Three-class evidence scoring (§3.3) | **SHOULD** | 1–2 | 5h |
| Context slicing | **SHOULD** | 2 | 6h |
| Move policy into config files | **SHOULD** | 2 | 4h |
| Fine-grained work units | **SHOULD** | 3–4 | 8h |
| Cheap GET preflight | **LATER** | 2 | 6h |
| Deferred review screen | **LATER** | 3 | 6h |
| New worker pool + supervisor | **LATER** | 4 | 10h |
| Unify three interfaces | **LATER** | 3 | 5h |

| Group | AI sessions | Verification | Calendar at 2–3h/day |
|---|---|---|---|
| **MUST** | 12–15 | ~28h | **2–3 weeks** |
| **SHOULD** | 8–10 | ~23h | +2–3 weeks |
| **LATER** | 12 | ~27h | +3–4 weeks |

Calendar exceeds the sum of the two columns because of rework, waiting on real batch runs, and result review.

### 22.4 Order under deadline pressure

```
Day 0      Stage 0 baseline: 30-company sample + recorded V1 results
           (Stage 1's replay gate has nothing to compare against without it)
Day 1      Live log with reason column               (makes every later check faster)
Day 2–4    Three cheap fixes                         (best result per hour spent)
Day 5–9    Four V1 behaviours: enrichment, status gate, domain dedup, tax code
```

The bootstrap day from the original ordering is gone — `AGENTS.md`, `INDEX.md`,
`MAP.md` and `STATUS.md` already exist (§0.2). Day 0 and Day 1 produce nothing
visible but shorten everything after them.

The `AGENTS.md` + `INDEX.md` + `STATUS.md` row in the table above is likewise
already delivered; what remains of it is one module contract per new V2 module,
written in the same commit as the module.

## 23. API references

- [Firecrawl Batch Scrape API](https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape)
- [Firecrawl Advanced Scraping Guide](https://docs.firecrawl.dev/advanced-scraping-guide)
- [Firecrawl API errors](https://docs.firecrawl.dev/api-reference/introduction)

## 24. Changelog

Edit together with §24 of the Vietnamese document. Rules: §21.5.

| Date | Sections | Change |
|---|---|---|
| 2026-07-28 | all | First English spec, derived from the Vietnamese plan at the same date. Covers: incremental-modification direction, restored enrichment / status gate / tax-code veto / domain dedup, dropped shared-artifact design, ~30 small modules, deferred concurrency, three-class evidence scoring, `unconfirmed` field authority, live decision log, agent architecture record, priority and effort table. |
| 2026-07-29 | 3.7, 3.8, 6, 17.1b, 21, 24 | Tightened promotion against query self-confirmation, same-family/copied sources, weak name-only matches, rival fields, and missing provenance. Added `tax_code_veto_rejects_all`, authoritative-registry versus tax-directory classes, regression tests, Definition of Done, versioned doc-sync gate, authority rules, and scoped Graphify usage. Added `docs/implementation/STATUS.md`, session start/end protocols, evidence-based handoff, stale-status protection, and per-owner work items for parallel agents. |
| 2026-07-29 | 16, 24 | Added `docs/v2-stage1-critical-fixes-implementation-plan.md`: detailed fixed-wait, cache/dedup migration, and retry execution plan with baseline, red tests, commit order, backup/rollback, gates, and Definition of Done. Clarified that Stage 1 creates the minimal retry executor and Stage 6 extends resource control. |
| 2026-07-29 | 21, 24 | Added self-bootstrap protocol: before code editing, agents create/repair missing bootstrap parts without overwriting or inventing progress, verify through Git/tests, and create the current work item. Read-only tasks report absence without mutating. Added minimal root `AGENTS.md` for automatic discovery. |
| 2026-08-17 | 0, 0.1, 0.2, 2, 3.2, 3.4, 10, 11, 12.1, 16, 17.3, 17.4, 21, 22.4, 24 | Reconciled the plan with the repository as it actually is. Replaced the "copy V1 into a `version2` directory" model with branch-based work in this repo (§0.2); `AGENTS.md` now governs process and wins any process conflict. §21.1/21.2/21.6 rewritten: the bootstrap document set already exists, so bootstrap is repair-only, the routing table is `INDEX.md` itself, and the 8-heading `STATUS.md` template is withdrawn in favour of `AGENTS.md` §9. Re-verified all defect evidence against the working tree and added defect 2.5 (dead `_batch_short_pages`); duplicate-row counts marked historical with a fresh measurement and a requirement to name the target database. Added §10.1 (the UNIQUE constraint must cover the normalized URL, and the whole table must be normalized, not only duplicate groups) and §10.2 (`filtered_links` and strict-completion fallout). Added §11.1 (complete inventory of six retry/throttle owners, including the previously unmentioned `src/rate_limiter.py` and the 503 gap in `connection_pool`) and §11.2 (company status when an operation exhausts its attempts). §12.1 now requires a measured A/B gate before `wait_for_ms` defaults to 0. Added §16.1 safe stopping points, Stage 0 as a Stage 1 prerequisite, and a budget warning on Stage 12's double API spend. Added tests 17.3.9–12 and 17.4.2–5. Added §3.2 and §3.4 so §0.1's constant pointers resolve; added `DELAY_SECONDS` to §0.1. Recorded open sync debt against the Vietnamese and Korean plans (§21.5). |
