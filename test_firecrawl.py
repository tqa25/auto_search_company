import requests
import json
import datetime
import os

def test_firecrawl():
    url = "https://api.firecrawl.dev/v2/search"

    payload = {
      "query": "GEN CONS VIỆT NAM",
      "sources": [
        "web"
      ],
      "categories": [],
      "limit": 10
    }

    headers = {
        "Authorization": "Bearer fc-e76bd44915c745d59286af9eb4bd1aaa",
        "Content-Type": "application/json"
    }

    try:
        print(f"⏳ Đang gửi request tới {url}...")
        response = requests.post(url, json=payload, headers=headers)
        
        # Kiểm tra nếu request không thành công
        response.raise_for_status() 
        data = response.json()
        print("✅ Request thành công!")
        
        # Tạo tên file log theo thời gian thực
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"firecrawl_result_{timestamp}.txt"
        
        # Ghi kết quả ra file txt
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write(f"--- KẾT QUẢ TÌM KIẾM FIRECRAWL ---\n")
            f.write(f"Thời gian: {datetime.datetime.now()}\n")
            f.write(f"Từ khóa: {payload['query']}\n")
            f.write(f"Mã trạng thái HTTP: {response.status_code}\n")
            f.write(f"----------------------------------\n\n")
            
            # Ghi JSON response đã được format đẹp mắt (indent=4)
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        print(f"📁 Kết quả đã được lưu trữ thành công vào file: {log_filename}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Đã xảy ra lỗi: {e}")
        # Ghi log lỗi vào file
        log_filename = "firecrawl_error.log"
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] ERROR: {str(e)}\n")
            if hasattr(e, 'response') and e.response is not None:
                f.write(f"Response: {e.response.text}\n")
        print(f"📁 Chi tiết lỗi đã được ghi vào: {log_filename}")

if __name__ == "__main__":
    test_firecrawl()
