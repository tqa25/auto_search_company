import pytest
import os
import tempfile
from src.database import DatabaseManager
from src.result_aggregator import ResultAggregator

@pytest.fixture
def db():
    # Use a temp directory for tests
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    db_manager = DatabaseManager(db_path)
    db_manager.init_db()
    
    # Insert mock data
    db_manager.insert_company("Company A", tax_code="123")
    db_manager.insert_company("Company B", tax_code="456")
    db_manager.insert_company("Company C", tax_code="789")
    
    db_manager.execute_query(
        "INSERT INTO extracted_contacts (company_id, source_type, address, phone) VALUES (?, ?, ?, ?)",
        (1, "masothue", "123 Street A", "0123")
    )
    db_manager.execute_query(
        "INSERT INTO extracted_contacts (company_id, source_type, email, confidence_score) VALUES (?, ?, ?, ?)",
        (1, "website", "a@test.com", 0.9)
    )
    db_manager.execute_query(
        "INSERT INTO extracted_contacts (company_id, source_type, address, confidence_score) VALUES (?, ?, ?, ?)",
        (2, "topcv", "456 Street B", 0.5)
    )
    # Company C has no derived data

    return db_manager

def test_aggregate_company(db):
    aggregator = ResultAggregator(db)
    
    res_a = aggregator.aggregate_company(1)
    assert res_a["company_name"] == "Company A"
    assert res_a["tax_code"] == "123"
    assert res_a["has_data"] is True
    assert res_a["total_sources"] == 2
    assert len(res_a["sources"]) == 2
    assert res_a["sources"][0]["source_type"] == "masothue"
    
    res_c = aggregator.aggregate_company(3)
    assert res_c["has_data"] is False
    assert res_c["total_sources"] == 0

def test_aggregate_all(db):
    aggregator = ResultAggregator(db)
    results = aggregator.aggregate_all()
    
    assert len(results) == 3
    assert sum(1 for r in results if r["has_data"]) == 2

def test_generate_summary_stats(db):
    aggregator = ResultAggregator(db)
    results = aggregator.aggregate_all()
    stats = aggregator.generate_summary_stats(results)
    
    assert stats["total_companies"] == 3
    assert stats["companies_with_data"] == 2
    assert stats["companies_no_data"] == 1
    assert stats["avg_sources_per_company"] == 1.0  # 3 sources total / 3 companies
    assert stats["avg_confidence"] == 0.7  # (0.9 + 0.5) / 2
