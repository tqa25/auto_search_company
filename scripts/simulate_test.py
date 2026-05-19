import sys
import os
import pandas as pd
import sqlite3

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.filter_module import LinkFilter
from src.database import DatabaseManager
from src.logger import PipelineLogger

def main():
    csv_path = os.path.join(PROJECT_ROOT, "results", "report", "search_results_report.csv")
    if not os.path.exists(csv_path):
        print("CSV not found")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    # Get top 5 unique companies
    companies = df['Company'].dropna().unique()[:5]

    temp_db = os.path.join(PROJECT_ROOT, "data", "temp_test.db")
    db = DatabaseManager(temp_db)
    db.init_db()
    logger = PipelineLogger(db)
    filter_module = LinkFilter(db, logger)

    report_data = []

    for company in companies:
        print(f"\nProcessing: {company}")
        company_df = df[df['Company'] == company]
        
        # Simulated Gemini Quick Search
        report_data.append({
            "Company": company,
            "Step": "1. Gemini Quick Search",
            "Action": "Always executed",
            "Result": "Extracted initial data. Pipeline continues to Deep Search regardless of result (Early-stop removed).",
            "URL": "",
            "Score": "",
            "Breakdown": ""
        })

        # Deep Search (from CSV data)
        urls = company_df['URL'].dropna().tolist()
        
        scored_urls = []
        for url in urls:
            result = filter_module.classify_url(url, company)
            scored_urls.append({
                "url": url,
                "score": result['relevance_score'],
                "should_scrape": result['should_scrape'],
                "breakdown": result['score_breakdown'],
                "source": result['source_type']
            })
            
        # Sort by score descending
        scored_urls.sort(key=lambda x: x['score'], reverse=True)
        top_urls = [u for u in scored_urls if u['should_scrape']][:3]
        
        # Log Top URLs
        for i, u in enumerate(top_urls):
            report_data.append({
                "Company": company,
                "Step": f"2. Deep Search & Filter (Top {i+1})",
                "Action": "Score and select for scraping",
                "Result": f"Selected ({u['source']})",
                "URL": u['url'],
                "Score": u['score'],
                "Breakdown": str(u['breakdown'])
            })
            
        # AI Extract
        report_data.append({
            "Company": company,
            "Step": "3. AI Extract",
            "Action": "Extract contacts from scraped content",
            "Result": f"Would extract from {len(top_urls)} URLs",
            "URL": "",
            "Score": "",
            "Breakdown": ""
        })

        # Facebook Fallback
        fb_urls = [u for u in scored_urls if 'facebook.com' in u['url'].lower()]
        if fb_urls:
            report_data.append({
                "Company": company,
                "Step": "4. Facebook Fallback (Conditional)",
                "Action": "Check for Facebook links if no phone found",
                "Result": f"Found {len(fb_urls)} Facebook links as fallback",
                "URL": fb_urls[0]['url'],
                "Score": fb_urls[0]['score'],
                "Breakdown": str(fb_urls[0]['breakdown'])
            })
        else:
            report_data.append({
                "Company": company,
                "Step": "4. Facebook Fallback (Conditional)",
                "Action": "Check for Facebook links if no phone found",
                "Result": "No Facebook links available",
                "URL": "",
                "Score": "",
                "Breakdown": ""
            })

    out_df = pd.DataFrame(report_data)
    out_path = os.path.join(PROJECT_ROOT, "results", "report", "pipeline_simulation_5_companies.xlsx")
    out_df.to_excel(out_path, index=False)
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
