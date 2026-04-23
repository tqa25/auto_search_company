import os
import sys
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.ai_extractor import AIExtractor
from src.result_aggregator import ResultAggregator
from src.excel_handler import ExcelWriter

def main():
    print("MỤC ĐÍCH: Chạy RIÊNG bước AI Extract cho dữ liệu đã scrape (không tốn thêm Firecrawl credits).\n")
    
    # 1. Load .env
    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    print("1. Loaded GEMINI API key.")

    db = DatabaseManager()
    logger = PipelineLogger(db)
    extractor = AIExtractor(db, logger, gemini_api_key)
    
    # 2. Tìm tất cả công ty có status='scraped'
    print("2. Finding scraped companies to extract...")
    companies = db.get_all_companies()
    scraped_company_ids = [c["id"] for c in companies if c["status"] == 'scraped']
    
    if not scraped_company_ids:
        print("No companies found with status='scraped'. Exiting.")
        return
        
    print(f"Found {len(scraped_company_ids)} companies ready for AI extraction: {scraped_company_ids}")
    
    # 3. Chạy AIExtractor.extract_batch()
    print("3. Running AI Extract Batch...")
    extractor.extract_batch(scraped_company_ids, delay_seconds=4.0)
    
    # 4. In summary và xuất báo cáo
    print("\n--- AI Extraction Summary ---")
    stats = extractor.get_extraction_stats()
    print(f"Total Companies Extracted Pages Processed: {stats.get('total_pages_processed')}")
    print(f"Average Confidence: {stats.get('avg_confidence_score', 0):.2f}")
    
    print("\n4. Generating Reports...")
    aggregator = ResultAggregator(db)
    aggregated_data = aggregator.aggregate_all()
    summary_stats = aggregator.generate_summary_stats(aggregated_data)
    
    writer = ExcelWriter()
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "extract_only_report.xlsx")
    
    if hasattr(writer, "write_final_report"):
        writer.write_final_report(report_path, aggregated_data, summary_stats)
        print(f"Exported final report to {report_path}")
    else:
        print("Warning: ExcelWriter.write_final_report not found. Using legacy format.")
        
    print("Done!")

if __name__ == "__main__":
    main()
