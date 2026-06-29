from __future__ import annotations

from typing import Any


def _latest_activity(db, company_id: int) -> dict[str, Any]:
    row = db.fetch_one(
        """
        SELECT step, status, error_message
        FROM pipeline_logs
        WHERE company_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (company_id,),
    )
    return row or {"step": None, "status": None, "error_message": None}


def _scrape_candidate_rows(db, company_id: int) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT
            fl.id AS filtered_link_id,
            fl.url,
            (
                SELECT sp.scrape_status
                FROM scraped_pages sp
                WHERE sp.filtered_link_id = fl.id
                ORDER BY sp.id DESC
                LIMIT 1
            ) AS latest_scrape_status
        FROM filtered_links fl
        WHERE fl.company_id = ?
          AND fl.should_scrape = 1
        ORDER BY fl.id
        """,
        (company_id,),
    )


def audit_company_completion(db, company_id: int, company: dict | None = None) -> dict[str, Any]:
    company = company or db.get_company(company_id) or {}
    latest = _latest_activity(db, company_id)
    latest_step = latest.get("step")
    latest_status = latest.get("status")

    counts = db.fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM gemini_quick_results WHERE company_id = ?) AS gemini_results,
            (SELECT COUNT(*) FROM search_results WHERE company_id = ?) AS search_results,
            (SELECT COUNT(*) FROM filtered_links WHERE company_id = ?) AS filtered_links,
            (SELECT COUNT(*) FROM extracted_contacts WHERE company_id = ?) AS contacts,
            (SELECT COUNT(*) FROM pipeline_logs WHERE company_id = ? AND step = 'AI_EXT') AS ai_extract_logs
        """,
        (company_id, company_id, company_id, company_id, company_id),
    ) or {}

    scrape_candidates = _scrape_candidate_rows(db, company_id)
    missing_scrapes = sum(1 for row in scrape_candidates if not row.get("latest_scrape_status"))
    failed_scrapes = sum(
        1 for row in scrape_candidates
        if row.get("latest_scrape_status") and row.get("latest_scrape_status") != "success"
    )
    successful_scrapes = sum(1 for row in scrape_candidates if row.get("latest_scrape_status") == "success")

    data_counts = {
        "gemini_results": counts.get("gemini_results", 0) or 0,
        "search_results": counts.get("search_results", 0) or 0,
        "filtered_links": counts.get("filtered_links", 0) or 0,
        "scrape_candidates": len(scrape_candidates),
        "scraped_success": successful_scrapes,
        "scraped_missing": missing_scrapes,
        "scraped_failed": failed_scrapes,
        "contacts": counts.get("contacts", 0) or 0,
        "ai_extract_logs": counts.get("ai_extract_logs", 0) or 0,
    }

    result = {
        "completion_status": "incomplete",
        "completion_reason": "no_intermediate_data",
        "resume_status": "pending",
        "checkpoint": "pipeline_init",
        "current_step": "Waiting",
        "last_activity_step": latest_step,
        "last_activity_status": latest_status,
        "last_error": latest.get("error_message"),
        "data_counts": data_counts,
    }

    if scrape_candidates:
        if missing_scrapes:
            result.update({
                "completion_reason": "scrape_missing",
                "resume_status": "searched",
                "checkpoint": "scrape",
                "current_step": "Scrape",
            })
            return result
        if failed_scrapes:
            result.update({
                "completion_reason": "scrape_failed",
                "resume_status": "searched",
                "checkpoint": "scrape",
                "current_step": "Scrape",
            })
            return result
        if data_counts["ai_extract_logs"] > 0 or data_counts["contacts"] > 0:
            result.update({
                "completion_status": "strict_done",
                "completion_reason": "strict_done",
                "resume_status": "done",
                "checkpoint": "done",
                "current_step": "Done",
            })
            return result
        result.update({
            "completion_reason": "ai_extract_incomplete",
            "resume_status": "ai_extract_pending",
            "checkpoint": "ai_extract",
            "current_step": "AI Extract",
        })
        return result

    if data_counts["search_results"] > 0 or data_counts["filtered_links"] > 0 or latest_step == "firecrawl_search":
        result.update({
            "completion_reason": "firecrawl_search_incomplete",
            "resume_status": "gemini_quick_done",
            "checkpoint": "deep_search",
            "current_step": "Deep Search",
        })
        return result

    if data_counts["gemini_results"] > 0:
        result.update({
            "completion_reason": "firecrawl_search_incomplete",
            "resume_status": "gemini_quick_done",
            "checkpoint": "deep_search",
            "current_step": "Deep Search",
        })
        return result

    if latest_step == "scrape":
        result.update({
            "completion_reason": "scrape_missing",
            "resume_status": "searched",
            "checkpoint": "scrape",
            "current_step": "Scrape",
        })
        return result

    return result
