import sqlite3
import os
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv()
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

def scrape_pages():
    db_path = "data/company_data.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get the 20 social media links
    query = """
    SELECT c.original_name as Company, sr.url as URL
    FROM search_results sr
    JOIN companies c ON sr.company_id = c.id
    WHERE sr.url LIKE '%facebook.com%' OR sr.url LIKE '%linkedin.com%'
    LIMIT 20;
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    os.makedirs("results/report", exist_ok=True)
    report_path = "results/report/crawl-20-pages-05-13.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Báo cáo kết quả Scrape 20 trang Mạng Xã Hội qua Firecrawl\n\n")
        f.write("Dưới đây là nội dung markdown thu được khi gọi API Scrape của Firecrawl trên 20 URL mạng xã hội.\n\n")
        
        for idx, (company, url) in enumerate(rows, 1):
            print(f"Scraping {idx}/20: {url}")
            f.write(f"## {idx}. Công ty: {company}\n")
            f.write(f"**URL:** {url}\n\n")
            
            headers = {
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "url": url,
                "formats": ["markdown"],
                "timeout": 30000
            }
            
            try:
                resp = requests.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=payload, timeout=35)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        md_content = data.get("data", {}).get("markdown", "")
                        if not md_content or md_content.strip() == "":
                            f.write("> ⚠️ **Kết quả rỗng:** Firecrawl báo thành công nhưng không lấy được nội dung (có thể bị chặn bởi cơ chế chống bot của MXH).\n\n")
                        else:
                            # Print a snippet to avoid massive file size
                            snippet = md_content[:1000] + ("\n... [NỘI DUNG ĐÃ CẮT BỚT]" if len(md_content) > 1000 else "")
                            f.write("```markdown\n")
                            f.write(snippet)
                            f.write("\n```\n\n")
                    else:
                        f.write(f"> ❌ **Lỗi API:** {data.get('error', 'Unknown')}\n\n")
                elif resp.status_code == 429:
                    f.write("> ⏳ **Lỗi:** Quá giới hạn Rate Limit (429).\n\n")
                    time.sleep(10)
                else:
                    f.write(f"> ❌ **Lỗi HTTP {resp.status_code}:** {resp.text[:200]}\n\n")
            except Exception as e:
                f.write(f"> ❌ **Lỗi mạng/Code:** {str(e)}\n\n")
            
            # Rate limiting sleep
            time.sleep(2.5)
            
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    scrape_pages()
