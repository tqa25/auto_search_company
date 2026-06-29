from __future__ import annotations

import os
from typing import Any


_NON_BLOCKING_SCRAPE_STATUSES = {"success", "timeout", "skipped", "unsupported"}
_TOP_N = max(1, int(os.getenv("TOP_N", "10") or "10"))


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


def _top_scrape_candidate_rows(db, company_id: int) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT
            fl.id AS filtered_link_id,
            fl.url,
            fl.source_type,
            fl.relevance_score,
            latest.scrape_status AS latest_scrape_status,
            latest.error_message AS latest_error_message,
            latest.credits_used AS latest_credits_used,
            latest.created_at AS latest_created_at
        FROM (
            SELECT *
            FROM filtered_links
            WHERE company_id = ?
              AND should_scrape = 1
            ORDER BY relevance_score DESC, id
            LIMIT ?
        ) fl
        LEFT JOIN (
            SELECT sp.filtered_link_id, sp.scrape_status, sp.error_message, sp.credits_used, sp.created_at
            FROM scraped_pages sp
            INNER JOIN (
                SELECT filtered_link_id, MAX(id) AS max_id
                FROM scraped_pages
                WHERE company_id = ?
                GROUP BY filtered_link_id
            ) last_sp ON last_sp.max_id = sp.id
        ) latest ON latest.filtered_link_id = fl.id
        ORDER BY fl.relevance_score DESC, fl.id
        """,
        (company_id, _TOP_N, company_id),
    )


def _classify_scrape_result(status: str | None, error_message: str | None) -> str:
    if not status:
        return "missing"

    status_norm = str(status).strip().lower()
    error_norm = (error_message or "").strip().lower()

    if status_norm in _NON_BLOCKING_SCRAPE_STATUSES:
        return "terminal"

    unsupported_markers = (
        "unsupported",
        "not support",
        "not supported",
        "cannot scrape",
        "can't scrape",
        "khong ho tro",
        "không hỗ trợ",
    )
    if any(marker in error_norm for marker in unsupported_markers):
        return "terminal"

    return "blocking"


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

    scrape_candidates = _top_scrape_candidate_rows(db, company_id)
    scrape_missing = 0
    scrape_blocking = 0
    scrape_terminal = 0
    for row in scrape_candidates:
        classification = _classify_scrape_result(row.get("latest_scrape_status"), row.get("latest_error_message"))
        if classification == "missing":
            scrape_missing += 1
        elif classification == "blocking":
            scrape_blocking += 1
        else:
            scrape_terminal += 1

    data_counts = {
        "gemini_results": counts.get("gemini_results", 0) or 0,
        "search_results": counts.get("search_results", 0) or 0,
        "filtered_links": counts.get("filtered_links", 0) or 0,
        "scrape_candidates": len(scrape_candidates),
        "scraped_success": scrape_terminal,
        "scraped_missing": scrape_missing,
        "scraped_failed": scrape_blocking,
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
        if scrape_missing:
            result.update({
                "completion_reason": "scrape_missing",
                "resume_status": "searched",
                "checkpoint": "scrape",
                "current_step": "Scrape",
            })
            return result
        if scrape_blocking:
            result.update({
                "completion_reason": "scrape_failed",
                "resume_status": "searched",
                "checkpoint": "scrape",
                "current_step": "Scrape",
            })
            return result
        if data_counts["contacts"] > 0:
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
