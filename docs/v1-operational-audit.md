# Báo cáo vận hành và kiểm toán dữ liệu Version 1

> Ngày lập: 2026-07-29  
> Phạm vi kiểm tra V1: `/home/ubuntu/workspaces2/projects/auto_search_company_v1`  
> Commit chung đang được checkout khi kiểm tra: `8be2634230287a622b665c36db978d64d593b9ef`

## 1. Mục đích và kết luận

V1 là một pipeline đang hoạt động: nhận danh sách công ty, bổ sung thông tin nhận diện, search URL, lọc URL, scrape nội dung, dùng AI lấy contact và xuất kết quả.

Có thể hình dung pipeline là **người điều phối sân bay**: nó quyết định bước nào được chạy, chuyển dữ liệu giữa các bước và lưu checkpoint. Checkpoint là **điểm lưu game** giúp lần chạy sau tiếp tục từ bước còn dở.

Tài liệu này ghi lại luồng vận hành, bằng chứng database và giới hạn chất lượng dữ liệu của V1. Đây không phải kế hoạch triển khai V2.

V1 có giá trị để:

- đối chiếu hành vi nghiệp vụ;
- chạy lại dữ liệu lịch sử;
- kiểm tra các rule lọc và nguồn dữ liệu hiện có;
- làm phương án rollback trong thời gian V2 chưa đạt tiêu chuẩn nghiệm thu.

V1 không nên được coi là nguồn dữ liệu đúng tuyệt đối. Database hiện tại chứa dữ liệu lặp, trạng thái lịch sử chưa đồng nhất và kết quả do AI suy ra. Người nhận phải phân biệt **bằng chứng gốc** với **kết quả đã diễn giải**.

Điểm quan trọng nhất:

1. Không dùng riêng `companies.status = 'done'` để kết luận công ty đã có kết quả hợp lệ.
2. Không dùng số lượng row để kết luận nguồn nào tốt hơn.
3. Không tin mù quáng vào `extracted_contacts`, file re-extract hoặc file export tổng hợp.
4. Khi có xung đột, quay lại URL và `scraped_pages.markdown_content` để kiểm chứng.
5. Không chạy `scripts/merge_db.py` lên database chính nếu chưa backup, dry-run và lưu danh sách công ty bị thay thế.

## 2. Luồng hoạt động của Version 1

```text
Nhập công ty
    ↓
Gemini Quick Search: bổ sung tên tiếng Việt/tax code/contact ban đầu
    ↓ checkpoint gemini_quick_done
Firecrawl Deep Search: chạy nhiều query lấy URL
    ↓
Link Filter + Business Status: chấm điểm, blacklist, kiểm tra tình trạng hoạt động
    ↓ checkpoint searched
Scrape: lấy markdown của các URL được chọn
    ↓ checkpoint ai_extract_pending
AI Extract: lấy phone/email/address/website/fax/đại diện từ từng trang
    ↓
Completion Audit + status done
    ↓
Dashboard/Excel/CSV tổng hợp kết quả
```

### 2.1 Nhập và chuẩn hóa công ty

App nhập tên công ty, tạo khóa tên chuẩn hóa và lưu batch import. Một công ty có thể có tên gốc, tên tiếng Việt, tax code và địa chỉ.

Cần lưu ý:

- khóa tên chuẩn hóa có thể gộp các tên gần nhau nhưng không chứng minh hai pháp nhân là một;
- tax code hoặc tên tiếng Việt có thể được bổ sung về sau bởi Quick Search;
- dữ liệu người dùng nhập và dữ liệu AI bổ sung hiện chưa được tách provenance đủ chặt.

### 2.2 Gemini Quick Search

Quick Search dùng Google Search Grounding để tìm nhanh tên tiếng Việt, tax code và contact. Kết quả thô lưu ở `gemini_quick_results`; một phần dữ liệu được ghi vào `companies` và `extracted_contacts`.

Cần lưu ý:

- code V1 có thể cập nhật trực tiếp `companies.tax_code` và `companies.vietnamese_name`;
- cùng một bộ contact Quick Search có thể được ghi lặp theo tối đa ba source URL;
- các row này có `source_type = 'gemini_grounding'` và không gắn `scraped_page_id`;
- đây là kết quả enrichment chưa được xác nhận, không tương đương bằng chứng registry chính thức.

### 2.3 Deep Search

App chạy các query về contact, tuyển dụng, tax và thông tin chung. Kết quả Firecrawl Search được lưu vào `search_results`.

Cần lưu ý:

- query V1 không luôn bắt buộc tỉnh/thành nên có thể tìm đúng tên nhưng sai công ty;
- cache hit có thể bị lưu lại thành row mới;
- một lỗi API ở lớp dưới có thể bị biến thành danh sách rỗng, làm lớp retry bên ngoài không thử lại;
- search snippet chỉ là gợi ý để tìm URL, không phải bằng chứng contact cuối cùng.

### 2.4 Link Filter và Business Status

Link Filter chấm điểm URL, loại blacklist, domain nước ngoài, tên công ty khớp không an toàn và tax code Masothue mâu thuẫn. Business Status tìm dấu hiệu công ty ngừng hoạt động.

Cần lưu ý:

- điểm cao là kết quả heuristic, không phải xác nhận URL chính thức;
- nhãn `official_website` có thể đến từ rule phân loại, không phải chứng thư sở hữu domain;
- tax code mục tiêu sai có thể làm URL đúng bị loại;
- trang directory hoặc nội dung sao chép nhau không phải các bằng chứng độc lập;
- status phrase trên nguồn tổng hợp có thể cũ hoặc sai, nên quyết định dừng công ty phải lưu URL và đoạn bằng chứng.

### 2.5 Scrape

App chọn các URL đủ điều kiện, ưu tiên theo score/source, gọi Firecrawl và lưu markdown ở `scraped_pages`.

Cần lưu ý:

- V1 có cả `waitFor=3000` và đường tuần tự `sleep(3)`, làm chậm mọi trang;
- cùng URL của cùng công ty có thể có nhiều scrape row lịch sử;
- scrape `success` chỉ nói đã lấy được nội dung, không nói nội dung thuộc đúng công ty;
- markdown có thể chứa footer, hotline của báo, quảng cáo hoặc công ty khác.

### 2.6 AI Extract

AI đọc từng trang scrape thành công và ghi `extracted_contacts`. Code hiện kiểm tra một số giá trị phải xuất hiện trong nội dung trang.

Cần lưu ý:

- `extracted_contacts` không có unique constraint bắt buộc một row cho mỗi `scraped_page_id`;
- kiểm tra “đã extract chưa” nằm ở application code nên không chống được mọi đường import hoặc race condition;
- phần “conflict resolution” chỉ log nguồn có confidence cao hơn; nó không xóa row thua và không tạo một bảng winner chuẩn;
- `result_aggregator.py` vẫn trả các contact row nguồn, nên consumer có thể thấy nhiều giá trị xung đột;
- confidence là đánh giá của AI/rule, không phải xác suất đúng đã được hiệu chuẩn.

### 2.7 Completion và export

`completion_audit.py` cố gắng suy ra checkpoint từ dữ liệu đã có để tiếp tục mà không trả tiền lại. Dashboard và export đọc database để hiển thị/tổng hợp.

Cần lưu ý:

- code cũ từng gắn `done` ngay cả khi không có trang scrape hoặc contact;
- database lịch sử có thể không tuân theo audit mới;
- export làm phẳng dữ liệu có thể che mất xung đột nguồn và provenance;
- ngày xuất báo cáo không phải ngày nguồn công bố contact;
- phải báo riêng `strict_done`, `incomplete`, `no_contact` và `failed`, không gom tất cả thành “đã xong”.

## 3. Các vấn đề dữ liệu đã xác nhận trong database V1

Kiểm tra read-only trên `data/company_data.db`, ngày 2026-07-29:

| Kiểm tra | Kết quả |
|---|---:|
| `PRAGMA integrity_check` | `ok` |
| Công ty | 8.701 |
| Search result | 1.048.364 |
| Filtered link | 413.183 |
| Scraped page | 66.970 |
| Extracted contact | 74.523 |
| Gemini Quick result | 8.152 |
| Pipeline log | 142.529 |
| Nhóm search trùng theo company + query + URL | 85.336 |
| Row search dư trong các nhóm trùng | 89.070 |
| Nhóm filtered link trùng theo company + URL | 13.080 |
| Row filtered link dư | 33.953 |
| Nhóm scraped page trùng theo company + URL | 6.305 |
| Row scraped page dư | 8.665 |
| Scraped page có nhiều contact row | 696 |
| Contact row dư trên các page đó | 1.009 |
| Nhóm batch AI gán cùng response cho nhiều URL | 5.964 |
| Công ty có dấu vết batch AI này | 5.645 |
| Contact row thuộc các nhóm batch AI này | 22.696 |
| Công ty `done` nhưng không có contact | 156 |
| Contact không gắn scraped page | 12.072 |
| Orphan được kiểm tra giữa các bảng chính | 0 |

12.072 contact không gắn scraped page trùng với số row `gemini_grounding`. Chúng không có markdown page trong database để đối chiếu trực tiếp theo `scraped_page_id`.

Phân bố lớn nhất của `extracted_contacts`:

| Source type | Row | Công ty |
|---|---:|---:|
| `official_website` | 36.795 | 6.730 |
| `gemini_grounding` | 12.072 | 5.643 |
| `masothue` | 11.783 | 6.480 |
| `thuvienphapluat` | 7.238 | 6.152 |
| `jobsgo` | 3.168 | 2.952 |

Số row lớn không chứng minh độ chính xác cao, đặc biệt khi cùng dữ liệu có thể được lặp qua nhiều URL hoặc nhiều lần chạy.

## 4. Làm rõ `batch_ai_extract` và nguy cơ ghi đè

### 4.1 Điều đã xác nhận

Lịch sử code và database V1 xác nhận cơ chế batch cũ đã làm sai quan hệ giữa URL và kết quả extract.

Code cũ trong `src/ai_extractor.py` thực hiện:

1. `_batch_short_pages()` gom nhiều trang ngắn của cùng công ty vào một batch.
2. `_extract_batch()` nối markdown của các trang thành một prompt duy nhất.
3. Gemini trả về một object chung gồm address, phone, email, website, fax và representative.
4. Code chạy vòng lặp qua mọi page trong batch và gọi `insert_extracted_contact()` với **cùng field, cùng `raw_ai_response` và cùng confidence**.
5. Chỉ `scraped_page_id`, `source_type` và `source_url` thay đổi theo page.

Vì vậy:

- lỗi nằm ở bảng `extracted_contacts`;
- `scraped_pages.markdown_content` không bị batch AI ghi đè;
- kết quả chung của toàn batch bị gán cho từng URL như thể mỗi URL tự chứa toàn bộ contact đó;
- không thể khẳng định kết quả đến từ URL đầu tiên: nó có thể đến từ bất kỳ page nào trong prompt ghép, hoặc do AI tổng hợp từ nhiều page;
- thao tác database là `INSERT`, không phải SQL `UPDATE`, nhưng về ý nghĩa dữ liệu nó đã ghi sai/ghi đè quan hệ provenance giữa từng URL và contact.

### 4.2 Bằng chứng trong database

Database có 6.023 log `AI_EXT_BATCH` của 5.675 công ty:

| Trạng thái log | Số lượng |
|---|---:|
| `SUCCESS` | 6.012 |
| `FAILED` | 11 |

Đối chiếu `company_id + created_at + raw_ai_response` giữa các URL khác nhau cho thấy:

| Dấu vết batch bị gán chung | Kết quả |
|---|---:|
| Nhóm có cùng response AI trong cùng giây nhưng nhiều URL | 5.964 |
| Công ty bị ảnh hưởng | 5.645 |
| Contact row thuộc các nhóm này | 22.696 |
| Row dư sau khi giữ một response cấp batch | 16.732 |

Trong 5.964 nhóm trên, 5.919 nhóm khớp một log `AI_EXT_BATCH SUCCESS` của cùng công ty tại cùng `finished_at`. Tỷ lệ khớp là 99,2%.

Phần còn lại có cùng dấu vết dữ liệu nhưng có thể lệch timestamp hoặc đến từ lần chạy không còn log tương ứng.

Kiểm tra literal phone/email trên chính markdown được gắn với từng row:

| Kiểm tra | Tổng row có field | Không có trên page của row | Có trên một page khác trong cùng batch |
|---|---:|---:|---:|
| Phone | 9.243 | 7.297 | 6.539 |
| Email | 4.159 | 3.324 | 2.614 |

Đây là bằng chứng trực tiếp rằng contact tìm thấy trên một page đã bị gán sang các page khác của cùng batch.

Ngược lại, toàn bộ bảng `scraped_pages` chỉ có **1 nhóm** cùng công ty, khác URL nhưng markdown giống hệt nhau. Con số này không phù hợp với giả thuyết “batch AI ghi đè nội dung scrape cho hàng nghìn công ty”.

Ví dụ company ID 2:

- batch gồm ba URL từ Vieclam24h, Vieclamnhamay và VietnamWorks;
- log ghi `batch_size = 3`;
- một response chung chứa phone `0291.3957555, 0911.892.879`;
- response đó được lưu cho cả ba URL;
- phone không xuất hiện trên markdown của hai trong ba URL nhưng xuất hiện trên page còn lại.

Kết luận: **batch AI làm hỏng kết quả extract theo URL, không làm hỏng markdown scrape theo URL**.

### 4.3 Phân biệt với công cụ re-extract tạo sau này

`re_extract_tool/cli_batch.py` là công cụ khác:

- đọc `scraped_pages.markdown_content`;
- gọi OpenRouter để extract lại;
- ghi kết quả ra CSV theo tham số `--output`;
- code hiện có không ghi CSV đó trở lại database chính.

Khi một page dài bị chia thành nhiều chunk, công cụ này có thể ghép field từ các chunk theo rule “field không rỗng đầu tiên thắng”, còn confidence lấy giá trị lớn nhất. Kết quả vẫn cần được kiểm tra với markdown gốc.

Marker `ai_batch_extract` chỉ xuất hiện trong `scripts/export_domain_retrieval_report.py` như một marker loại trừ.

Không tìm thấy marker trong `companies`, `pipeline_logs`, `reported_companies`, `company_import_items` hoặc `company_match_candidates`.

### 4.4 Cơ chế merge có thể thay toàn bộ dữ liệu công ty

`scripts/merge_db.py` có policy `overwrite` và `smart`.

Khi quyết định thay thế một công ty, script xóa dữ liệu đích của công ty đó ở:

- `extracted_contacts`;
- `scraped_pages`;
- `filtered_links`;
- `search_results`;
- `pipeline_logs`;
- `query_cache`;
- `pipeline_jobs`;
- `gemini_quick_results`;
- `companies`.

Sau đó script chép dữ liệu của công ty từ database nguồn vào. Script không lưu snapshot của row cũ và không tạo audit table ghi trước/sau.

Policy `smart` cũng có thể thay thế dữ liệu dựa trên một richness score đơn giản:

```text
contacts × 10 + scraped_pages × 2 + search_results
```

Vì database có dữ liệu trùng, bao gồm row do batch AI nhân ra, một bản có nhiều row hơn có thể thắng dù chất lượng thực tế kém hơn.

### 4.5 Cảnh báo bắt buộc trong biên bản

Nên dùng nguyên văn cảnh báo sau:

> Batch AI cũ đã ghép nhiều URL vào một lần extract và lưu cùng một response cho mọi URL. Database xác nhận ít nhất 22.696 contact row thuộc 5.964 nhóm có dấu vết này.
>
> Không dùng `extracted_contacts.source_url` làm bằng chứng nếu chưa đối chiếu field với `scraped_pages.markdown_content`. Nội dung scrape không có dấu hiệu bị batch AI ghi đè trên diện rộng.
>
> Cơ chế merge V1 còn có thể xóa lịch sử của một công ty rồi chép bản khác vào mà không lưu bản trước và sau.

### 4.6 Thứ tự tin cậy khi điều tra một kết quả

Từ cao xuống thấp:

1. Dữ liệu định danh do người dùng cung cấp và đã xác nhận.
2. Registry có thẩm quyền, với URL và thời điểm truy xuất.
3. Nội dung `scraped_pages.markdown_content` đúng URL, đúng công ty, có đoạn bằng chứng literal.
4. Search result/snippet dùng để tìm nguồn.
5. `extracted_contacts` có `scraped_page_id`, sau khi đối chiếu lại page.
6. `gemini_grounding` chưa được xác nhận.
7. CSV re-extract hoặc file export tổng hợp không còn đầy đủ provenance.

Không phải mọi “bước trước” đều đáng tin hơn. Search snippet vẫn yếu hơn nội dung page. Bằng chứng tốt nhất cho một contact là giá trị xuất hiện trong nội dung đúng công ty, đúng nguồn và còn phù hợp tại thời điểm kiểm tra.

## 5. Bảng rủi ro V1

| Mức | Rủi ro | Tác động | Cách xử lý khi tiếp nhận |
|---|---|---|---|
| Critical | Batch AI gán một response chung cho mọi URL trong batch | Contact bị gắn sai source URL trên ít nhất 22.696 row | Không tin provenance của contact lịch sử; đối chiếu literal từng field với markdown |
| Critical | Merge có thể xóa và thay toàn bộ dữ liệu công ty | Mất provenance, mất lịch sử, chọn nhầm bản “giàu row” | Cấm chạy trực tiếp; bắt buộc backup, dry-run, manifest và review |
| Critical | `.env` chứa secret cục bộ | Rò API key | Không nộp `.env`; rotate key nếu từng chia sẻ |
| High | 89.070 search row dư | Sai thống kê, tăng dữ liệu và có thể làm score lệch | Dedupe migration rồi thêm unique key |
| High | `done` không đồng nghĩa có contact hợp lệ | Báo cáo sai tỷ lệ hoàn thành | Dùng completion audit nghiêm ngặt |
| High | Quick Search ghi dữ liệu chưa xác nhận vào bảng chính/contact | Sai tax code hoặc contact, khó phân biệt nguồn | V2 tách observation/promotion/provenance |
| High | AI conflict chỉ được log, không có winner chuẩn | Consumer chọn tùy ý | V2 lưu decision rõ ràng theo field |
| High | Retry có thể không tới đủ lần thử | Bỏ sót dữ liệu do lỗi tạm thời | Stage 1 dùng retry executor chung |
| High | Query thiếu tỉnh/thành | Nhầm công ty trùng tên | V2 bắt buộc identity context và preview |
| Medium | Label `official_website` là heuristic | Tin nhầm domain | Yêu cầu bằng chứng sở hữu/identity |
| Medium | Fixed wait 3 giây | Chậm, tốn thời gian batch | Mặc định 0, cấu hình theo domain |
| Medium | Nhiều scrape/contact row cho cùng page | Báo cáo lặp/xung đột | Unique/idempotency key và migration |
| Medium | File export làm phẳng provenance | Người dùng tưởng output là dữ liệu gốc | Luôn xuất URL, page ID, evidence và model/policy version |

## 6. Những việc chưa được khẳng định

Cuộc kiểm tra này chưa chứng minh:

- batch re-extract đã từng được import thủ công ngược vào database bằng một script ngoài repository;
- ai đã chạy `scripts/merge_db.py`, chạy lúc nào và những company ID nào bị overwrite;
- file console/log bên ngoài nào còn giữ danh sách `[OVERWRITE]`;
- 156 công ty `done` không có contact là lỗi lịch sử, chủ ý nghiệp vụ cũ hay kết quả merge;
- mọi contact lặp đều sai; một page có thể chứa nhiều loại dữ liệu, nhưng schema hiện không diễn đạt rõ winner.

Nếu cần kết luận pháp lý hoặc dữ liệu chính thức, phải tìm thêm lịch sử shell, log CI, backup database theo ngày và file export đã giao cho người dùng. Không được suy luận ngược chỉ từ database hiện tại.
