# Executive Blacklist/Skip Report Artifact

Purpose: provide one self-contained Korean HTML report for management about
the observed Blacklist/Skip analysis and the simulated Firecrawl scrape credits
avoided by those rules.

Implemented output: `output/reports/blacklist-skip-executive-report.html`.

Inputs: the verified audit figures for 22/05/2026–14/07/2026, including the
search denominator, blocked URL counts, replayed Top-10 candidates, successful
scrape count, paid scrape-credit count, boundary ties, and skip-policy bypass.

Output: a static HTML file that opens without a server or external network
resources. It must make the distinction between observed counts and simulated
credit savings visible.

Must not: query or modify databases, make API calls, embed secrets, present
boundary ties as definite credits, or claim a causal result outside the stated
data period.

Invariant: `8,977` is shown only as the simulated number of candidates that
definitely enter the replayed Top 10 (`Top 10 확정 진입`), not as a directly
billed or settled total. The Korean UI must use `블랙리스트`, `스킵 도메인`,
`스크레이프 성공 URL`, and `절감 가능 크레딧`; the comparison with scraped URLs
must name its denominator.

Verification completed on 2026-08-05:

- Desktop browser review: passed; the executive hierarchy, the `8.977` hero
  number, and the comparison against `70.651` successful scrape URLs were
  legible with no clipping.
- Mobile browser review: passed; the report reflows into a single-column view
  and the comparison table remains legible without horizontal overflow.
- Print review: passed; the landscape A4 output contains three populated
  pages and no blank trailing page.
- `bash scripts/check-doc-sync.sh`: passed after the final documentation
  update.

Korean localization completed on 2026-08-05:

- All user-facing text, including document metadata, table labels, aria labels,
  responsive table labels, caveats, methodology, and footer, is Korean.
- Korean number formatting uses commas for thousands and dots for decimals;
  values remain unchanged.
- The UI explicitly says that `8,977` is a historical replay simulation and
  candidate credits, not an invoice or settled saving. It excludes `6,134`
  tied-boundary URLs and retains `73` historical skip-bypass credits as a
  separate caveat.
- Korean desktop and mobile renders passed visual review. The final A4
  landscape PDF has three pages; its print-style preview was also reviewed.

The report is a standalone static artifact, so no application test is needed.
