#!/usr/bin/env python3
"""
Integration Test — Phase 1 (GĐ1)
Agent 1D: Tests 3 modules working together:
  - src/database.py (DatabaseManager)
  - src/excel_handler.py (ExcelReader + ExcelWriter)
  - src/logger.py (PipelineLogger)

Run: python tests/test_integration_phase1.py
"""

import os
import sys
import time
import datetime
import traceback

# Ensure project root is on sys.path so 'src' package is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.database import DatabaseManager
from src.excel_handler import ExcelReader, ExcelWriter
from src.logger import PipelineLogger

# ── Configuration ────────────────────────────────────────────────────────────
TEST_DB_PATH = os.path.join(PROJECT_ROOT, "data", "integration_test.db")
EXCEL_INPUT_PATH = os.path.join(PROJECT_ROOT, "PIC 수집 시도_글투실_20260409.xlsx")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
EXCEL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "integration_test_output.xlsx")
CSV_LOG_PATH = os.path.join(OUTPUT_DIR, "integration_test_log.csv")
SUMMARY_EXCEL_PATH = os.path.join(OUTPUT_DIR, "integration_test_summary.xlsx")

# ── Fake data for simulating pipeline ────────────────────────────────────────
FAKE_SOURCES = [
    {
        "source": "masothue",
        "address": "123 Nguyễn Huệ, Quận 1, TP.HCM",
        "phone": "028-1234-5678",
        "email": "info@company.com",
        "website": "https://company.com",
        "fax": "028-1234-5679",
        "rep": "Nguyễn Văn A",
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
    },
    {
        "source": "topcv",
        "address": "456 Lê Lợi, Quận 3, TP.HCM",
        "phone": "0901-234-567",
        "email": "hr@company.com",
        "website": "",
        "fax": "",
        "rep": "",
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
    },
]


def _separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _step(num: int, msg: str):
    print(f"\n  [{num}] {msg}")


def main():
    passed = 0
    failed = 0
    errors = []

    print("\n" + "=" * 60)
    print("  GĐ1 INTEGRATION TEST — Agent 1D")
    print(f"  Started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Step 0: Cleanup previous test DB if exists ───────────────────────────
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        print(f"\n  [CLEANUP] Removed old test DB: {TEST_DB_PATH}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1: Create new DB (DatabaseManager.init_db) ──────────────────────
    _separator("STEP 1: Tạo database mới")
    try:
        db = DatabaseManager(db_path=TEST_DB_PATH)
        db.init_db()
        assert os.path.exists(TEST_DB_PATH), "DB file was not created!"

        # Verify all 6 tables exist
        tables = db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        # Exclude sqlite_sequence (auto-created by SQLite for AUTOINCREMENT)
        table_names = sorted([t["name"] for t in tables if t["name"] != "sqlite_sequence"])
        expected_tables = sorted([
            "companies", "search_results", "filtered_links",
            "scraped_pages", "extracted_contacts", "pipeline_logs"
        ])
        assert table_names == expected_tables, (
            f"Tables mismatch!\n  Expected: {expected_tables}\n  Got:      {table_names}"
        )

        # Verify index on pipeline_logs
        indexes = db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pipeline_logs'"
        )
        index_names = [i["name"] for i in indexes]
        assert any("company_step" in name for name in index_names), (
            f"Missing index on pipeline_logs(company_id, step)! Found: {index_names}"
        )

        print(f"  ✅ DB created: {TEST_DB_PATH}")
        print(f"  ✅ 6 tables verified: {table_names}")
        print(f"  ✅ Index verified: {index_names}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 1: {e}")
        failed += 1
        # Cannot continue without DB
        print("\n❌ GĐ1 INTEGRATION TEST: FAILED (DB creation error, aborting)")
        sys.exit(1)

    # ── Step 2: Read real Excel file ─────────────────────────────────────────
    _separator("STEP 2: Đọc file Excel thật")
    companies_list = []
    try:
        reader = ExcelReader()
        companies_list = reader.read_company_list(EXCEL_INPUT_PATH)
        assert len(companies_list) > 0, "No companies read from Excel!"

        tax_count = sum(1 for c in companies_list if c.get("tax_code"))
        print(f"  ✅ Đọc được {len(companies_list)} công ty, {tax_count} công ty có MST")
        
        # Show first 5 for visual verification
        print(f"\n  First 5 companies:")
        for i, c in enumerate(companies_list[:5], 1):
            print(f"    {i}. {c['name']} | MST: {c.get('tax_code', '—')}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 2: {e}")
        failed += 1

    # ── Step 3: Insert all companies into DB ─────────────────────────────────
    _separator("STEP 3: Insert công ty vào database")
    try:
        inserted = 0
        for comp in companies_list:
            db.insert_company(
                original_name=comp["name"],
                tax_code=comp.get("tax_code"),
            )
            inserted += 1

        # Verify count in DB
        row = db.fetch_one("SELECT COUNT(*) as cnt FROM companies")
        db_count = row["cnt"]
        assert db_count == len(companies_list), (
            f"DB count ({db_count}) != Excel count ({len(companies_list)})"
        )
        print(f"  ✅ Inserted {inserted} công ty vào bảng companies")
        print(f"  ✅ DB verify: {db_count} records")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 3: {e}")
        failed += 1

    # ── Step 4: Simulate pipeline logs for first 3 companies ─────────────────
    _separator("STEP 4: Simulate pipeline log cho 3 công ty đầu tiên")
    try:
        pipeline_logger = PipelineLogger(db=db)
        first_3 = db.fetch_all("SELECT * FROM companies ORDER BY id LIMIT 3")
        assert len(first_3) >= 3, f"Need at least 3 companies, got {len(first_3)}"

        for company in first_3:
            cid = company["id"]
            cname = company["original_name"]

            # 4a. SEARCH: started → success
            log_id = pipeline_logger.log_step_start(
                company_id=cid, step="search", source_name=cname
            )
            time.sleep(0.1)  # Small delay for duration calculation
            pipeline_logger.log_step_end(
                log_id=log_id,
                status="success",
                credits_used=2,
                data_saved=True,
                metadata={"links_found": 10},
            )

            # Insert some fake search results
            for rank in range(1, 4):
                db.insert_search_result(
                    company_id=cid,
                    search_query=f"{cname} mã số thuế",
                    search_type="english",
                    result_rank=rank,
                    url=f"https://masothue.com/{cname.lower().replace(' ', '-')}-{rank}",
                    title=f"Result {rank} for {cname}",
                    snippet=f"Snippet for result {rank}",
                    credits_used=2,
                )

            # 4b. SCRAPE: started → success
            log_id = pipeline_logger.log_step_start(
                company_id=cid,
                step="scrape",
                source_url=f"https://masothue.com/{cname.lower().replace(' ', '-')}",
                source_name="masothue.com",
            )
            time.sleep(0.1)
            pipeline_logger.log_step_end(
                log_id=log_id,
                status="success",
                credits_used=1,
                data_saved=True,
                metadata={"content_length": 4532},
            )

            # Insert a fake scraped page
            db.insert_scraped_page(
                filtered_link_id=None,
                company_id=cid,
                url=f"https://masothue.com/{cname.lower().replace(' ', '-')}",
                source_type="masothue",
                markdown_content=f"# {cname}\nĐịa chỉ: 123 Nguyễn Huệ\nĐiện thoại: 028-1234-5678",
                content_length=4532,
                scrape_status="success",
                credits_used=1,
            )

            # 4c. AI_EXTRACT: started → success with fake data
            log_id = pipeline_logger.log_step_start(
                company_id=cid,
                step="ai_extract",
                source_name=cname,
            )
            time.sleep(0.1)
            pipeline_logger.log_step_end(
                log_id=log_id,
                status="success",
                credits_used=0,
                data_saved=True,
                metadata={"extracted_fields": "phone, email, address"},
            )

            # Insert fake extracted contact
            db.insert_extracted_contact(
                company_id=cid,
                scraped_page_id=None,
                source_type="masothue",
                source_url=f"https://masothue.com/{cname.lower().replace(' ', '-')}",
                address="123 Nguyễn Huệ, Quận 1, TP.HCM",
                phone="028-1234-5678",
                email="info@company.com",
                website="https://company.com",
                fax="028-1234-5679",
                representative="Nguyễn Văn A",
                raw_ai_response='{"address":"123 Nguyễn Huệ","phone":"028-1234-5678"}',
                confidence_score=0.95,
            )

        # Verify logs in DB
        log_count = db.fetch_one("SELECT COUNT(*) as cnt FROM pipeline_logs")['cnt']
        print(f"  ✅ Simulated pipeline for 3 companies")
        print(f"  ✅ Total pipeline_logs records: {log_count}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 4: {e}")
        failed += 1

    # ── Step 5: Get daily summary ────────────────────────────────────────────
    _separator("STEP 5: Gọi get_daily_summary()")
    try:
        summary = pipeline_logger.get_daily_summary()
        assert isinstance(summary, dict), "Summary should be a dict"

        required_keys = [
            "total_processed_today", "total_processed_all", "total_companies",
            "progress_percent", "success_rate", "total_credits_used",
            "avg_time_per_company", "top_5_errors", "source_distribution"
        ]
        for key in required_keys:
            assert key in summary, f"Missing key in summary: {key}"

        print(f"  ✅ Daily Summary:")
        print(f"     total_processed_today : {summary['total_processed_today']}")
        print(f"     total_processed_all   : {summary['total_processed_all']}")
        print(f"     total_companies       : {summary['total_companies']}")
        print(f"     progress_percent      : {summary['progress_percent']:.2f}%")
        print(f"     success_rate          : {summary['success_rate']:.2f}%")
        print(f"     total_credits_used    : {summary['total_credits_used']}")
        print(f"     avg_time_per_company  : {summary['avg_time_per_company']:.2f}s")
        print(f"     top_5_errors          : {summary['top_5_errors']}")
        print(f"     source_distribution   : {summary['source_distribution']}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 5: {e}")
        failed += 1

    # ── Step 6: ExcelWriter.write_results() with fake data ───────────────────
    _separator("STEP 6: Ghi file Excel output với dữ liệu giả")
    try:
        writer = ExcelWriter()
        # Build fake results for first 3 companies
        first_3_companies = db.fetch_all("SELECT * FROM companies ORDER BY id LIMIT 3")
        fake_results = []
        for comp in first_3_companies:
            fake_results.append({
                "name": comp["original_name"],
                "tax_code": comp.get("tax_code") or "",
                "sources": FAKE_SOURCES,
            })

        writer.write_results(EXCEL_OUTPUT_PATH, fake_results)
        assert os.path.exists(EXCEL_OUTPUT_PATH), "Excel output file was not created!"
        file_size = os.path.getsize(EXCEL_OUTPUT_PATH)
        print(f"  ✅ Excel output created: {EXCEL_OUTPUT_PATH}")
        print(f"     File size: {file_size:,} bytes")
        print(f"     Companies written: {len(fake_results)}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 6: {e}")
        failed += 1

    # ── Step 7: Export log to CSV ────────────────────────────────────────────
    _separator("STEP 7: Export pipeline log to CSV")
    try:
        pipeline_logger.export_log_to_csv(CSV_LOG_PATH)
        assert os.path.exists(CSV_LOG_PATH), "CSV log file was not created!"
        
        # Count lines in CSV
        with open(CSV_LOG_PATH, 'r', encoding='utf-8') as f:
            csv_lines = sum(1 for _ in f)
        
        file_size = os.path.getsize(CSV_LOG_PATH)
        print(f"  ✅ CSV log created: {CSV_LOG_PATH}")
        print(f"     File size: {file_size:,} bytes")
        print(f"     Lines (incl. header): {csv_lines}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Step 7: {e}")
        failed += 1

    # ── Bonus Step: Export summary to Excel ──────────────────────────────────
    _separator("BONUS: Export summary to Excel")
    try:
        pipeline_logger.export_summary_to_excel(SUMMARY_EXCEL_PATH)
        assert os.path.exists(SUMMARY_EXCEL_PATH), "Summary Excel file was not created!"
        file_size = os.path.getsize(SUMMARY_EXCEL_PATH)
        print(f"  ✅ Summary Excel created: {SUMMARY_EXCEL_PATH}")
        print(f"     File size: {file_size:,} bytes")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Bonus: {e}")
        failed += 1

    # ── Bonus Step: Test get_last_processed_company_id ───────────────────────
    _separator("BONUS: Test get_last_processed_company_id()")
    try:
        last_id = pipeline_logger.get_last_processed_company_id()
        assert last_id > 0, f"Expected last processed company_id > 0, got {last_id}"
        print(f"  ✅ Last processed company_id: {last_id}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        traceback.print_exc()
        errors.append(f"Bonus: {e}")
        failed += 1

    # ── Final Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    if errors:
        print("\n  Errors:")
        for err in errors:
            print(f"    ❌ {err}")

    # Verify output files
    print(f"\n  Output files:")
    for path in [TEST_DB_PATH, EXCEL_OUTPUT_PATH, CSV_LOG_PATH, SUMMARY_EXCEL_PATH]:
        exists = "✅" if os.path.exists(path) else "❌"
        print(f"    {exists} {os.path.basename(path)}")

    if failed == 0:
        print(f"\n{'='*60}")
        print(f"  GĐ1 INTEGRATION TEST: ALL PASSED ✅")
        print(f"{'='*60}\n")
    else:
        print(f"\n{'='*60}")
        print(f"  GĐ1 INTEGRATION TEST: FAILED ❌ ({failed} failures)")
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
