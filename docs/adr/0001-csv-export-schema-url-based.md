---
status: accepted
---
# CSV Export Format: One Row Per URL

We decided to structure the CSV export to have one row per search result URL, rather than one row per Company.

This means Company information (like Name and Tax Code) will be duplicated across multiple rows if that company has multiple URLs. For data extracted via Gemini Quick Search (which returns one set of contact data for the entire company but references multiple grounding URLs), we duplicate that contact data across all referenced grounding URLs and mark it with a `Data Scope` of `Company-Level`. Data from deep scrapes is marked as `URL-Level`.

This decision trades off strict normalization (1 row per contact) for maximum transparency (every URL scanned is explicitly listed with its outcome). A future reader might be surprised why the exact same phone number appears 5 times for the same company; this is a deliberate trade-off to keep the mapping to source URLs 1:1, allowing the user to trace all sources that verify that contact information. Additionally, we retain all technical columns (tokens, duration, error messages) for debugging purposes, but position them at the end of the row so business users can focus on the core contact data first.
