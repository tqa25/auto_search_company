import os
import sys
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.config import Config
from src.reparse_module import ReparseModule

reparse_router = APIRouter(prefix="/api/reparse", tags=["reparse"])

# Helper functions to get instances
def _db() -> DatabaseManager:
    db_path = os.path.join(_PROJECT_ROOT, os.getenv("DB_PATH", "data/company_data.db"))
    return DatabaseManager(db_path)

def _cfg() -> Config:
    return Config()

def _reparse_module() -> ReparseModule:
    db = _db()
    cfg = _cfg()
    logger = PipelineLogger(db, log_dir=os.path.join(_PROJECT_ROOT, "output", "logs"))
    return ReparseModule(db, logger, cfg)

# Request Models
class UnlockRequest(BaseModel):
    link_ids: List[int]

class ScrapeRequest(BaseModel):
    link_ids: List[int]
    
class ExtractRequest(BaseModel):
    page_ids: List[int]

class AutoReparseRequest(BaseModel):
    min_score: Optional[float] = 0.3
    max_urls: Optional[int] = 5

# Endpoints

@reparse_router.get("/{company_id}/unscrapped")
def get_unscrapped(company_id: int):
    rm = _reparse_module()
    urls = rm.get_unscrapped_urls(company_id)
    return {"company_id": company_id, "urls": urls}

@reparse_router.get("/{company_id}/phones")
def get_existing_phones(company_id: int):
    rm = _reparse_module()
    phones = rm.get_existing_phones(company_id)
    return {"company_id": company_id, "existing_phones": list(phones)}

@reparse_router.post("/{company_id}/unlock")
def unlock_urls(company_id: int, request: UnlockRequest):
    rm = _reparse_module()
    count = rm.unlock_urls(company_id, request.link_ids)
    return {"company_id": company_id, "unlocked_count": count}

@reparse_router.post("/{company_id}/scrape")
def scrape_urls(company_id: int, request: ScrapeRequest):
    rm = _reparse_module()
    # Note: in a real async environment this might be long-running, 
    # but we follow the sync pattern established in app.py runner.
    results = rm.scrape_unlocked(company_id, request.link_ids)
    new_pages = rm.get_newly_scraped_pages(company_id, request.link_ids)
    return {
        "company_id": company_id, 
        "scrape_results": results,
        "new_pages": new_pages
    }

@reparse_router.post("/{company_id}/extract")
def extract_pages(company_id: int, request: ExtractRequest):
    rm = _reparse_module()
    existing_phones = rm.get_existing_phones(company_id)
    results = rm.reextract(company_id, request.page_ids, existing_phones)
    
    new_phones = []
    for res in results:
        if res.get("status") == "success" and res.get("new_phones_found"):
            new_phones.extend(res["new_phones_found"])
            
    return {
        "company_id": company_id,
        "extract_results": results,
        "new_phones": list(set(new_phones))
    }

@reparse_router.post("/{company_id}/auto")
def auto_reparse(company_id: int, request: AutoReparseRequest):
    rm = _reparse_module()
    result = rm.run_reparse(company_id, request.min_score, request.max_urls)
    return result
