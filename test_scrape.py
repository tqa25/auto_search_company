import json
import datetime
import traceback
try:
    from firecrawl import FirecrawlApp as Firecrawl
except ImportError:
    try:
        from firecrawl import Firecrawl
    except ImportError:
        pass

def test_scrape():
    try:
        app = Firecrawl(api_key="fc-e76bd44915c745d59286af9eb4bd1aaa")
    except NameError:
        print("Lỗi: Chưa cài đặt thư viện 'firecrawl'. Bạn có thể cài đặt bằng lệnh: pip install firecrawl-py")
        return

    # 1. Đọc file kết quả search để lấy 4 URL đầu tiên
    file_path = "firecrawl_result_20260413_161928.txt"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Tách phần JSON ra từ dưới đường gạch ngang
            json_str = content.split("----------------------------------\n\n")[1]
            data = json.loads(json_str)
            
        # Lấy 4 URL đầu tiên
        urls = [item['url'] for item in data['data']['web'][:4]]
    except Exception as e:
        print(f"❌ Lỗi khi đọc file {file_path} hoặc trích xuất URL: {e}")
        return

    print(f"🔍 Đã trích xuất được {len(urls)} URLs cần scrape:")
    for i, u in enumerate(urls, 1):
        print(f"  {i}. {u}")
        
    # 2. Tạo tên file log với timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"firecrawl_scrape_result_{timestamp}.txt"
    
    # Khởi tạo file log
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write(f"--- KẾT QUẢ SCRAPE FIRECRAWL (Top {len(urls)} URLs) ---\n")
        f.write(f"Thời gian bắt đầu: {datetime.datetime.now()}\n")
        f.write(f"--------------------------------------------------\n\n")

    # 3. Tiến hành scrape cho từng URL
    for index, url in enumerate(urls, 1):
        print(f"\n🔄 [{index}/{len(urls)}] Đang thực hiện scrape: {url} ...")
        try:
            # Sử dụng tham số onlyMainContent=True để lọc bỏ menu, footer, điều hướng
            # Sử dụng params chuẩn cho SDK v4+
            params = {
                "formats": ["markdown"],
                "onlyMainContent": True,
                "maxAge": 172800000
            }

            try:
                # Thử gọi theo SDK mới nhất (v4+)
                response = app.scrape_url(url, params=params)
                scrape_data = response
            except AttributeError:
                # Nếu SDK cũ hơn
                scrape_data = app.scrape(
                    url,
                    only_main_content=True,
                    max_age=172800000,
                    formats=["markdown"]
                )
                
            print(f"✅ Scrape thành công: {url}")
            
            # Trích xuất nội dung Markdown một cách thông minh
            content_to_write = ""
            
            # Thử lấy từ attribute (SDK v4 trả về object)
            if hasattr(scrape_data, 'get'): # Nếu là dict hoặc dict-like
                content_to_write = scrape_data.get('markdown', '')
                if not content_to_write and 'data' in scrape_data:
                    content_to_write = scrape_data['data'].get('markdown', '')
            
            # Nếu vẫn chưa có, thử truy cập attribute trực tiếp
            if not content_to_write:
                try:
                    content_to_write = scrape_data.markdown
                except AttributeError:
                    pass
            
            # Fallback cuối cùng nếu không bóc tách được nội dung cụ thể
            if not content_to_write:
                if isinstance(scrape_data, dict):
                    content_to_write = json.dumps(scrape_data, ensure_ascii=False, indent=4)
                else:
                    content_to_write = str(scrape_data)

            # Ghi kết quả vào file txt
            with open(log_filename, "a", encoding="utf-8") as f:
                f.write(f"==================================================\n")
                f.write(f"VỊ TRÍ: {index}\n")
                f.write(f"URL: {url}\n")
                f.write(f"==================================================\n\n")
                f.write(content_to_write)
                f.write("\n\n\n")
                
        except Exception as e:
            print(f"❌ Scrape thất bại cho {url}. Lỗi: {str(e)}")
            # Log lỗi vào file
            with open(log_filename, "a", encoding="utf-8") as f:
                f.write(f"==================================================\n")
                f.write(f"VỊ TRÍ: {index}\n")
                f.write(f"URL: {url}\n")
                f.write(f"==================================================\n")
                f.write(f"❌ LỖI KHI SCRAPE:\n{traceback.format_exc()}\n\n\n")

    print(f"\n📁 Quá trình hoàn tất! Toàn bộ kết quả đã được lưu tại: {log_filename}")

if __name__ == "__main__":
    test_scrape()
