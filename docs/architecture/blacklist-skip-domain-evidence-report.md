# Blacklist/Skip Domain Evidence Report Artifact

Purpose: provide one self-contained Korean HTML reference that lists the 31
effective Blacklist hosts and 21 Skip entries, and makes the evidence type of
each displayed URL explicit.

Implemented output: `output/reports/blacklist-skip-domain-evidence-ko.html`.

Inputs: `pipeline_config.json`, the current filter-policy behaviour, and
read-only records from `data/company_data.db`. The report does not query or
modify a database when opened.

Rules:

- Show exactly 31 Blacklist hosts and 21 Skip entries. `topcv.vn` appears in
  both configured lists, but the report explains that Blacklist has priority.
- A manual Blacklist sample prefers scraped URLs with no contact. When those
  are unavailable, it may show a real database URL only when its provenance is
  visible and it is not described as no-contact scrape evidence.
- `dauthau.info` has no URL in the Firecrawl search/filter/scrape chain in the
  audited databases. Its 20 displayed samples are deterministic, distinct
  `extracted_contacts.source_url` values where `source_type` is
  `gemini_grounding` and `scraped_page_id` is null. Each carries the Korean
  label `Gemini Grounding 출처 URL · Firecrawl 스크레이프 증거 아님`.
- Do not claim that manual configuration was caused by historical failures;
  audit data does not retain per-host author, date, or business reason.

Verification completed on 2026-08-05:

- Static content checks confirm 31 Blacklist rows, six manual hosts with 20
  displayed samples each, 21 Skip entries, and 577 total displayed URL samples.
- The three low-volume auto-Blacklist hosts remain truthful: `ceginfo.hu` has
  15 samples and `zenithlongevity.eu` / `zenithtrademark.com` have one each.
- `bash scripts/check-doc-sync.sh` and `git diff --check` pass after the
  report and documentation update.
- Chromium render review passed at 1440×1100 desktop and 390×844 mobile. The
  mobile table intentionally scrolls inside its table container to preserve
  all five columns. Landscape-A4 PDF rendering produced four populated pages.

The artifact is static evidence material, not application runtime code. No
application test is applicable; visual review covers the rendered document.
