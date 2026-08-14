# Work Item: Korean Blacklist/Skip Domain Evidence HTML

Owner: Codex
Status: completed
Created: 2026-08-05 +07

## Scope

- Add a static Korean evidence report at `output/reports/blacklist-skip-domain-evidence-ko.html`.
- Use only `pipeline_config.json`, filter logic, and verified records in `data/company_data.db`.
- Add sample URLs without displaying contact PII or inventing causal evidence.
- Update the matching architecture documentation, implementation status, and this work item.
- Do not change application code, runtime configuration, or database contents.

## Acceptance criteria

- The Korean document contains exactly two primary tables: 31 effective Blacklist hosts and 21 Skip entries.
- Each Blacklist host has a deterministic sample URL list in an HTML disclosure; manual hosts prioritize scraped pages with no extracted contact before non-scrape historical URLs.
- Every sample labels its evidence category accurately; URLs are real and clickable.
- `dauthau.info` shows exactly 20 real, distinct Gemini Grounding source URLs
  when no Firecrawl URL exists, each labelled as non-Firecrawl evidence.
- The document explains the Blacklist-first precedence for `topcv.vn`, the auto-blacklist threshold, and the absence of a current whitelist.
- Desktop, mobile, and printable output are reviewed; static integrity checks and `bash scripts/check-doc-sync.sh` pass.

## Evidence

- The report uses 20 deterministic, distinct `extracted_contacts.source_url`
  values for `dauthau.info`, restricted to `source_type = gemini_grounding`
  and `scraped_page_id IS NULL`. Every displayed value was checked against the
  database and labelled in Korean as `Gemini Grounding 출처 URL · Firecrawl
  스크레이프 증거 아님`. They are context-only URLs, not evidence that
  Firecrawl scraped the page or that a scrape produced no contact.
- Static check passed: 31 Blacklist rows; 21 Skip rows; all six manual hosts
  show 20 samples; `dauthau.info` shows 20 distinct grounded URLs; total
  Blacklist URL samples are 577; low-volume automatic hosts remain 15/1/1 for
  `ceginfo.hu`, `zenithlongevity.eu`, and `zenithtrademark.com`.
- Render review passed: Chromium desktop 1440×1100 and mobile 390×844. The
  mobile table uses its intended internal horizontal scroll. Landscape-A4 PDF
  rendered to four populated pages; page 1 was visually reviewed.
- `bash scripts/check-doc-sync.sh` → `doc-sync check passed (read-only).`
- `git diff --check` → passed with no output.
- Application tests: not run (not applicable; this is a standalone static
  HTML artifact and no application code changed).

## File scope

- `output/reports/blacklist-skip-domain-evidence-ko.html` (new; Git-ignored through `output/`)
- `docs/architecture/INDEX.md`
- `docs/architecture/blacklist-skip-domain-evidence-report.md` (new)
- `docs/implementation/STATUS.md`
- `docs/implementation/work-items/2026-08-05-blacklist-skip-domain-evidence-ko.md`
