# Nâng cấp chiến lược tìm kiếm: Smart Search với Scoring System

## Bối cảnh
Hệ thống hiện tại sử dụng chiến lược tìm kiếm 3 bước cố định (Tax Code → English Name → Vietnamese Name) với `limit=10`, dẫn đến thiếu vắng các nguồn tuyển dụng, trang chủ công ty, và mạng xã hội trong kết quả. Cần nâng cấp sang chiến lược **"Phễu rộng → Chấm điểm → Cào chọn lọc"** để tối ưu chất lượng dữ liệu thu thập.

---

## Tóm tắt thay đổi chính

1. **SearchModule**: Thêm 3 giai đoạn truy vấn mới (Liên hệ → Tuyển dụng → Tên viết tắt) với cơ chế dừng sớm sau mỗi giai đoạn
2. **LinkFilter**: Thêm hệ thống chấm điểm (Scoring System) với Domain Score + Keyword Score
3. **ScrapeModule**: Chỉ cào Top N link có điểm cao nhất thay vì cào tất cả
4. **Pipeline**: Điều phối luồng mới: Search → Filter & Score → Select Top N → Scrape

---

## User Review Required

> [!IMPORTANT]
> **Thay đổi hành vi tìm kiếm**: Chiến lược tìm kiếm mới sẽ tốn **2-6 credits Search** (thay vì 2-4 credits cố định như cũ) nhưng tiết kiệm credits Scrape nhờ chỉ cào các link chất lượng cao.

> [!WARNING]
> **Cần chạy lại test**: Sau khi cập nhật, cần chạy lại toàn bộ test suite và thử nghiệm với 2-3 công ty mẫu để xác nhận hệ thống Scoring hoạt động đúng.

---

## Open Questions

> [!IMPORTANT]
> 1. **Ngưỡng dừng sớm (Early Stop Threshold)**: Bạn muốn dùng ngưỡng "có 5-10 link điểm > 50" hay một con số cụ thể? Gợi ý: **≥ 5 link có điểm ≥ 40** (vì thang điểm mới thấp hơn sau khi giảm Keyword Score xuống +10).
> 2. **Top N để cào**: Bạn muốn cố định Top 10, hay cho phép cấu hình linh hoạt (ví dụ: Top 8, Top 12)?
> 3. **Xử lý query cũ**: Giữ lại 3 query cũ (Tax Code, English Name, Vietnamese Name) hay thay thế hoàn toàn bằng 3 query mới?

---

## Proposed Changes

### Bảng điểm chi tiết (Scoring System)

#### Domain Score (Trọng số tên miền) — Thứ tự ưu tiên: C > D > A > B

| Nhóm | Điểm | Tên miền | Lý do ưu tiên |
|------|-------|----------|----------------|
| **C - Trang chủ công ty** | **+40** | Website chính thức của đối tượng (phát hiện qua tên miền chứa brand name) | Mục "Liên hệ" thường có đầy đủ SĐT tổng đài, Email phòng ban, địa chỉ chính xác |
| **D - Tra cứu pháp lý** | **+30** | `masothue.com`, `thuvienphapluat.vn`, `hosocongty.vn`, `yellowpages.vn` | Có SĐT đăng ký kinh doanh, địa chỉ pháp lý, tên người đại diện |
| **A - Trang tuyển dụng** | **+20** | `vietnamworks.com`, `topcv.vn`, `vieclam24h.vn`, `jobsgo.vn`, `careerbuilder.vn`, `timviec365.vn`, `vietcareer.vn` | SĐT/Email của HR, nhưng thường là nhân viên tuyển dụng, không phải quản lý cấp cao |
| **B - Mạng xã hội** | **+10** | `facebook.com`, `linkedin.com` | Có thể tìm được profile cá nhân, nhưng dữ liệu không ổn định và khó cào |

#### Keyword Score (Trọng số từ khóa) — Tất cả +10 điểm

| Nhóm từ khóa | Các từ khóa cụ thể |
|---------------|---------------------|
| **Liên hệ** | `liên hệ`, `lien-he`, `contact`, `contact-us` |
| **Tuyển dụng / HR** | `tuyển dụng`, `tuyen-dung`, `jobs`, `careers`, `hr`, `nhân sự`, `nhan-su`, `recruitment` |
| **Kế toán / Hành chính** | `kế toán`, `ke-toan`, `accounting`, `hành chính`, `hanh-chinh`, `admin` |
| **Bất động sản VP / KCN** | `văn phòng`, `van-phong`, `office`, `khu công nghiệp`, `khu-cong-nghiep`, `industrial-park`, `industrial-zone`, `kcn`, `cho thuê văn phòng`, `bất động sản công nghiệp` |

#### Cách tính tổng điểm

```
Tổng điểm = Domain Score + Keyword Score (URL) + Keyword Score (Snippet/Title)
```

- Keyword Score chỉ tính **1 lần** cho mỗi nhóm (dù có nhiều từ khóa trùng trong cùng 1 nhóm)
- Tối đa Keyword Score = +40 (nếu URL/Snippet chứa từ khóa thuộc cả 4 nhóm)
- **Điểm tối đa lý thuyết = 80** (Domain C +40 + 4 nhóm keyword x10)

---

### Chiến lược 3 giai đoạn truy vấn (Conditional Multi-Phase Search)

#### Giai đoạn 1: Query "Liên hệ" (2 credits)
```
"{Tên công ty rút gọn}" AND ("liên hệ" OR "contact" OR "địa chỉ" OR "số điện thoại")
```
→ Đánh giá: Nếu ≥ 5 link có điểm ≥ 40 → **DỪNG**

#### Giai đoạn 2: Query "Tuyển dụng / Nhân sự" (2 credits)
```
"{Tên công ty rút gọn}" AND ("tuyển dụng" OR "nhân sự" OR "jobs" OR "careers")
```
→ Đánh giá: Nếu tổng tích lũy ≥ 5 link có điểm ≥ 40 → **DỪNG**

#### Giai đoạn 3: Query "Tên viết tắt / Mở rộng" (2 credits)
```
"{Tên viết tắt}" AND ("tuyển dụng" OR "liên hệ")
```
→ Không đánh giá, chạy nốt rồi tổng hợp kết quả.

**Lưu ý:** 3 giai đoạn mới này **bổ sung** sau các bước tìm kiếm cũ (Tax Code + English Name). Tức là luồng đầy đủ sẽ là:
1. Tax Code search (giữ nguyên)
2. English Name + Anchor Keywords (giữ nguyên)
3. Vietnamese Name (giữ nguyên, có điều kiện)
4. **[MỚI] Query Liên hệ** (có điều kiện dừng sớm)
5. **[MỚI] Query Tuyển dụng** (có điều kiện dừng sớm)
6. **[MỚI] Query Tên viết tắt** (có điều kiện dừng sớm)

---

### Component 1: SearchModule

#### [MODIFY] [search_module.py](file:///home/baguf/workspaces/auto_search_company/src/search_module.py)

**Thay đổi:**
- Tăng `limit` từ 10 lên **20** cho tất cả các query (mở rộng phễu)
- Thêm method `_build_short_name()`: Rút gọn tên công ty (bỏ "CÔNG TY TNHH", "CÔNG TY CỔ PHẦN"...) để tạo từ khóa tìm kiếm linh hoạt hơn
- Thêm method `_build_abbreviation()`: Tạo tên viết tắt từ chữ cái đầu (VD: SEVT)
- Thêm method `_search_phase_contact()`: Giai đoạn 1 — Query Liên hệ
- Thêm method `_search_phase_recruitment()`: Giai đoạn 2 — Query Tuyển dụng
- Thêm method `_search_phase_abbreviation()`: Giai đoạn 3 — Query Tên viết tắt
- Cập nhật method `search_company()`: Tích hợp 3 giai đoạn mới sau các bước cũ, với kiểm tra `early_stop` sau mỗi giai đoạn

---

### Component 2: LinkFilter (Scoring System)

#### [MODIFY] [filter_module.py](file:///home/baguf/workspaces/auto_search_company/src/filter_module.py)

**Thay đổi:**
- Cập nhật `TARGET_DOMAINS`: Bổ sung các trang tuyển dụng mới (`vieclam24h.vn`, `jobsgo.vn`, `careerbuilder.vn`, `timviec365.vn`)
- Thêm dict `DOMAIN_SCORES`: Ánh xạ từng domain → điểm số theo bảng điểm ở trên
- Thêm dict `KEYWORD_GROUPS`: 4 nhóm từ khóa với danh sách từ cụ thể
- Thêm method `calculate_score(url, title, snippet)`: Tính tổng điểm = Domain Score + Keyword Score
- Cập nhật method `filter_company_links()`: Sau khi phân loại, gọi `calculate_score()` cho mỗi link và lưu điểm vào DB
- Thêm method `get_top_links(company_id, top_n=10)`: Trả về Top N link có điểm cao nhất
- Thêm method `check_early_stop(company_id, threshold_count=5, threshold_score=40)`: Kiểm tra điều kiện dừng sớm

---

### Component 3: Database

#### [MODIFY] [database.py](file:///home/baguf/workspaces/auto_search_company/src/database.py)

**Thay đổi:**
- Thêm cột `relevance_score` (REAL) vào bảng `filtered_links` để lưu điểm đánh giá
- Thêm method `get_top_scored_links(company_id, top_n)`: Query Top N link theo điểm giảm dần

---

### Component 4: ScrapeModule

#### [MODIFY] [scrape_module.py](file:///home/baguf/workspaces/auto_search_company/src/scrape_module.py)

**Thay đổi:**
- Cập nhật method `scrape_company()`: Thay vì cào tất cả link có `should_scrape=1`, chỉ cào Top N link có `relevance_score` cao nhất (gọi `db.get_top_scored_links()`)
- Thêm tham số `max_pages` (mặc định = 10) để giới hạn số trang cào

---

### Component 5: Pipeline

#### [MODIFY] [pipeline.py](file:///home/baguf/workspaces/auto_search_company/src/pipeline.py)

**Thay đổi:**
- Cập nhật luồng `run()`: Sau bước Search, gọi Filter & Score trước khi chuyển sang Scrape
- Truyền callback `early_stop_checker` từ LinkFilter vào SearchModule để kiểm tra điều kiện dừng sớm giữa các giai đoạn tìm kiếm

---

## Ví dụ minh họa luồng mới (Samsung Thái Nguyên)

```
Bước 1: Tax Code "4601124536" → limit=20 → 10 kết quả
Bước 2: English Name + Anchor → limit=20 → 10 kết quả
  → Tích lũy: ~20 link thô
  → Filter & Score: masothue.com (+30), thuvienphapluat.vn (+30)...
  → Kiểm tra: Chỉ có 2 link ≥ 40 điểm → CHƯA ĐỦ, tiếp tục

Bước 3 [MỚI]: Query Liên hệ: "Samsung Thái Nguyên" AND "liên hệ"
  → limit=20 → 15 kết quả mới (bao gồm samsung.com/vn/contact)
  → Filter & Score: samsung.com (+40 domain + 10 keyword = 50)
  → Kiểm tra: 4 link ≥ 40 điểm → CHƯA ĐỦ, tiếp tục

Bước 4 [MỚI]: Query Tuyển dụng: "Samsung Thái Nguyên" AND "tuyển dụng"
  → limit=20 → 12 kết quả mới (vietnamworks, topcv, vieclam24h...)
  → Filter & Score: vietnamworks (+20 + 10 = 30), topcv (+20 + 10 = 30)
  → Kiểm tra: 6 link ≥ 40 điểm → ĐỦ! DỪNG (bỏ qua Bước 5)

Tổng: 4 queries x 2 credits = 8 credits Search
Scrape: Top 10 link x 1 credit = 10 credits
TỔNG CỘNG: 18 credits (nhưng chất lượng dữ liệu cao hơn rất nhiều)
```

---

## Verification Plan

### Automated Tests
- Chạy unit test cho `calculate_score()` với các URL mẫu thuộc từng nhóm domain
- Chạy unit test cho `check_early_stop()` với các kịch bản đủ/không đủ ngưỡng
- Chạy integration test với 2-3 công ty mẫu (Samsung Thái Nguyên, một công ty nhỏ, một công ty có tên tiếng Anh)

### Manual Verification
- So sánh kết quả report Excel trước và sau khi áp dụng chiến lược mới
- Kiểm tra xem các trang tuyển dụng (vietnamworks, topcv...) có xuất hiện trong kết quả không
- Đối chiếu tổng credits tiêu hao trước/sau để đánh giá hiệu quả chi phí
