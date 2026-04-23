import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ResultAggregator:
    """Aggregates extracted contact data for reporting."""
    
    def __init__(self, db):
        self.db = db

    def aggregate_company(self, company_id: int) -> dict:
        """Aggregates all extracted contacts for a given company."""
        company = self.db.get_company(company_id)
        if not company:
            return {}

        extracted_contacts = self.db.get_extracted_contacts_for_company(company_id)
        
        sources = []
        for contact in extracted_contacts:
            sources.append({
                "source_type": contact.get("source_type"),
                "source_url": contact.get("source_url"),
                "address": contact.get("address"),
                "phone": contact.get("phone"),
                "email": contact.get("email"),
                "website": contact.get("website"),
                "fax": contact.get("fax"),
                "representative": contact.get("representative"),
                "confidence": contact.get("confidence_score")
            })
            
        return {
            "company_name": company.get("original_name"),
            "tax_code": company.get("tax_code"),
            "sources": sources,
            "has_data": len(sources) > 0,
            "total_sources": len(sources),
            "collection_date": datetime.now().strftime("%Y-%m-%d")
        }

    def aggregate_all(self, company_ids: List[int] = None) -> List[Dict]:
        """Aggregates extracted contacts for multiple or all companies."""
        if not company_ids:
            companies = self.db.get_all_companies()
            company_ids = [c["id"] for c in companies]
            
        results = []
        for cid in company_ids:
            results.append(self.aggregate_company(cid))
        return results

    def generate_summary_stats(self, aggregated_data: List[Dict]) -> Dict:
        """Generates summary statistics from aggregated data."""
        total_companies = len(aggregated_data)
        companies_with_data = sum(1 for c in aggregated_data if c.get("has_data"))
        companies_no_data = total_companies - companies_with_data
        coverage_rate = (companies_with_data / total_companies * 100) if total_companies > 0 else 0
        
        total_sources = 0
        total_confidence = 0
        confidence_count = 0
        
        field_counts = {
            "address": 0, "phone": 0, "email": 0,
            "website": 0, "fax": 0, "representative": 0
        }
        source_distribution = {}
        
        for company in aggregated_data:
            has_address = False
            has_phone = False
            has_email = False
            has_website = False
            has_fax = False
            has_representative = False
            
            total_sources += company.get("total_sources", 0)
            
            for source in company.get("sources", []):
                source_type = source.get("source_type") or "unknown"
                source_distribution[source_type] = source_distribution.get(source_type, 0) + 1
                
                if source.get("address"): has_address = True
                if source.get("phone"): has_phone = True
                if source.get("email"): has_email = True
                if source.get("website"): has_website = True
                if source.get("fax"): has_fax = True
                if source.get("representative"): has_representative = True
                
                conf = source.get("confidence")
                if conf is not None:
                    total_confidence += conf
                    confidence_count += 1
            
            if has_address: field_counts["address"] += 1
            if has_phone: field_counts["phone"] += 1
            if has_email: field_counts["email"] += 1
            if has_website: field_counts["website"] += 1
            if has_fax: field_counts["fax"] += 1
            if has_representative: field_counts["representative"] += 1
            
        field_coverage = {k: (v / total_companies * 100) if total_companies > 0 else 0 for k, v in field_counts.items()}
        
        total_sources_all = sum(source_distribution.values())
        source_dist_pct = {k: (v / total_sources_all * 100) if total_sources_all > 0 else 0 for k, v in source_distribution.items()}
        
        avg_sources_per_company = (total_sources / total_companies) if total_companies > 0 else 0
        avg_confidence = (total_confidence / confidence_count) if confidence_count > 0 else 0
        
        return {
            "total_companies": total_companies,
            "companies_with_data": companies_with_data,
            "companies_no_data": companies_no_data,
            "coverage_rate": coverage_rate,
            "field_coverage": field_coverage,
            "source_distribution": source_dist_pct,
            "avg_sources_per_company": avg_sources_per_company,
            "avg_confidence": avg_confidence
        }
