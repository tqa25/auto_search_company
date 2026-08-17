"""Where to restart a company whose pipeline run was interrupted.

`companies.status` cannot be trusted after a crash: a worker that dies mid-scrape
leaves the row saying `scraping` forever, with no process behind it. These
helpers ignore the status column and read the actual rows the run produced, then
infer the cheapest safe restart point — notably resuming at `ai_extract_pending`
when scraped pages already exist, which avoids paying Firecrawl to scrape them
again.

This module is deliberately dependency-free: `src/pipeline_worker.py` and
`dashboard/app.py` both need this policy, and importing the worker from the
dashboard would drag `Pipeline` into the dashboard's import graph. Anything with
a `fetch_one` method works as `db`.

Both call sites used to carry byte-identical copies of this logic, which meant
the worker and the dashboard could silently disagree about how to recover the
same company. Keep it here; do not re-inline it.
"""

from __future__ import annotations


_EMPTY_COUNTS = {
    "gemini_results": 0,
    "search_results": 0,
    "filtered_links": 0,
    "scrape_candidates": 0,
    "scraped_pages": 0,
    "scraped_success": 0,
    "contacts": 0,
    "contact_addresses": 0,
}


def company_data_counts(db, company_id: int) -> dict:
    """Count the rows each pipeline step would have produced for one company."""
    row = db.fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM gemini_quick_results WHERE company_id = ?) AS gemini_results,
            (SELECT COUNT(*) FROM search_results WHERE company_id = ?) AS search_results,
            (SELECT COUNT(*) FROM filtered_links WHERE company_id = ?) AS filtered_links,
            (SELECT COUNT(*) FROM filtered_links WHERE company_id = ? AND should_scrape = 1) AS scrape_candidates,
            (SELECT COUNT(*) FROM scraped_pages WHERE company_id = ?) AS scraped_pages,
            (SELECT COUNT(*) FROM scraped_pages WHERE company_id = ? AND scrape_status = 'success') AS scraped_success,
            (SELECT COUNT(*) FROM extracted_contacts WHERE company_id = ?) AS contacts,
            (SELECT COUNT(*) FROM extracted_contacts WHERE company_id = ? AND address IS NOT NULL AND TRIM(address) != '') AS contact_addresses
        """,
        (company_id,) * 8,
    )
    return row or dict(_EMPTY_COUNTS)


def suggest_resume_status(company: dict, counts: dict) -> tuple[str, str]:
    """Return (status_to_resume_from, reason) for an interrupted company.

    Ordered most-progress-first, so the cheapest restart point wins.
    """
    status = company.get("status")
    if status == "extracting" or counts.get("contacts", 0) > 0:
        return "ai_extract_pending", "has_extracted_contacts_or_extracting"
    if counts.get("scraped_success", 0) > 0:
        if status == "scraping" and counts.get("filtered_links", 0) > counts.get("scraped_success", 0):
            return "searched", "partial_scrape_can_resume_without_deep_search"
        return "ai_extract_pending", "has_successful_scraped_pages"
    if counts.get("scraped_pages", 0) > 0 and counts.get("filtered_links", 0) > 0:
        return "searched", "partial_scraped_pages_with_filtered_links"
    if counts.get("filtered_links", 0) > 0:
        return "searched", "has_filtered_links"
    if counts.get("search_results", 0) > 0:
        return "searched", "has_search_results"
    if counts.get("gemini_results", 0) > 0:
        return "gemini_quick_done", "has_gemini_quick_results"
    return "pending", "no_intermediate_data"
