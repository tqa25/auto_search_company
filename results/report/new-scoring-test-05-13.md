# Báo cáo thử nghiệm quy trình chấm điểm URL mới

**Tên tiếng Anh / Tên gốc:** Công ty TNHH Vận tải Toàn Cầu
**Tên tiếng Việt:** Công ty TNHH MTV Giao nhận Toàn Cầu

| URL Đầu Vào | URL Được Xếp Hạng (Điểm) | Nên Scrape | Lý do |
| --- | --- | --- | --- |
| https://www.toancau.com.vn | 51.4 | True | Possible official website: toancau.com.vn (TLD bonus .vn: +5) (Name match bonus: +6.4) |
| https://masothue.com/123456789-cong-ty-tnhh-van-tai-toan-cau | 0.0 | False | Blacklisted domain: masothue.com |
| https://www.facebook.com/toancau | -100.0 | False | Social media ignored: facebook.com |
| https://jobsgo.vn/cong-ty-toan-cau-tuyen-dung | 50.0 | True | Possible official website: jobsgo.vn (TLD bonus .vn: +5) |
| https://randomsite.xyz/post/123 | 42.0 | True | Possible official website: randomsite.xyz (TLD bonus .xyz: +2) |
