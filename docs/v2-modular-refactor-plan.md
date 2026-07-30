# Kế hoạch xây dựng Version 2

> Bản báo cáo dành cho quản lý và người sử dụng không chuyên về công nghệ  
> Nguồn đối chiếu V1: `/home/ubuntu/workspaces2/projects/auto_search_company_v1`  
> Ngày cập nhật: 2026-07-29  
> Ưu tiên cao nhất: giảm chi phí tìm kiếm và thu thập dữ liệu, đồng thời có thể dừng và chạy tiếp mà không làm lại từ đầu  
> Cách làm: **sửa dần trên bản V1 đã copy vào root hiện tại**, không viết lại từ số không

> Phạm vi tài liệu: đây là nguồn chuẩn về hành vi và kiến trúc V2. Luồng vận hành, số liệu kiểm toán và cảnh báo dữ liệu V1 nằm tại `docs/v1-operational-audit.md`. Hồ sơ bàn giao bắt đầu tại `PROJECT_HANDOVER.md`.

## 1. Tóm tắt dành cho quản lý

V1 đang chạy được, nhưng các bước tìm kiếm, kiểm tra URL, scrape, gọi AI và lưu dữ liệu còn phụ thuộc chặt vào nhau.

`Pipeline` là toàn bộ chuỗi xử lý từ lúc đọc thông tin công ty đến khi lưu contact cuối cùng.

`Query` là câu tìm kiếm app gửi tới Google thông qua Firecrawl Search.

`Scrape` là tải và chuyển nội dung một URL thành văn bản để app tiếp tục xử lý.

`API` là cổng để app gửi yêu cầu đến một dịch vụ bên ngoài như Firecrawl.

Khi một bước lỗi hoặc hệ thống bị dừng, app có thể chạy lại phần đã làm xong, lưu dữ liệu trùng hoặc tiếp tục chạy worker trong nền.

`Worker` là tiến trình nhận và xử lý công việc. Có thể hiểu đơn giản là một phiên chạy độc lập của app đang xử lý một công ty hoặc một URL.

V2 sẽ chia quy trình thành các `module` — những khối chức năng nhỏ, mỗi khối làm một nhiệm vụ rõ ràng và có đầu vào, đầu ra riêng.

Ví dụ, khối tạo query chỉ tạo câu tìm kiếm. Khối này không tự gọi Firecrawl, không tự chấm URL và không tự ghi contact vào database.

Mỗi việc nhỏ sẽ trở thành một `work unit` — một đơn vị công việc có thể chạy, dừng và thử lại riêng.

Ví dụ:

- “Tìm kiếm query số 2 của công ty A” là một work unit.
- “Kiểm tra blacklist trên URL X” là một work unit khác.
- “Scrape URL X” là một work unit khác nữa.

Sau mỗi work unit, app lưu một `checkpoint` — dấu mốc cho biết việc nào đã xong và việc nào còn dở.

Nếu hệ thống dừng sau khi đã xử lý 13/20 URL, lần chạy sau chỉ tiếp tục 7 URL còn lại.

### Kết quả V2 cần mang lại

| Nhu cầu quản lý | Kết quả mong đợi |
|---|---|
| Giảm chi phí | Không search, scrape hoặc gọi AI lại khi kết quả cũ còn dùng được. |
| Giảm dữ liệu sai | Query luôn gắn với tỉnh/thành; AI chỉ đọc đoạn liên quan đến công ty. |
| Dễ kiểm tra | Mỗi bước có đầu vào, đầu ra và lý do quyết định riêng. |
| Dễ chạy tiếp | Dừng ở đâu thì tiếp tục từ đó, không chạy lại toàn bộ công ty. |
| Chạy nhanh hơn | Nhiều worker chạy song song nhưng không lấy trùng cùng một việc. |
| Dừng thật sự | Dashboard dừng cả nơi phát việc mới và các worker đang chạy, không chỉ đổi trạng thái hiển thị. |
| Dễ thay đổi nghiệp vụ | Domain, thứ tự nguồn, điểm số và công thức query nằm trong file cấu hình. |

### Cách xây V2: sửa dần trên bản copy của V1

V2 **không** được viết lại từ số không.

Lý do: V1 đã có sẵn nhiều thứ mà V2 cần và các thứ đó đang chạy đúng.

| Việc V2 cần | V1 đã có |
|---|---|
| Hai worker không giành cùng một việc | Job claiming bằng `BEGIN IMMEDIATE` |
| Biết worker đã chết | `heartbeat`, ngưỡng 15 phút |
| Chạy tiếp mà không trả tiền lại | Checkpoint `ai_extract_pending` |
| Dừng an toàn giữa lúc chạy | Stop check tại safe boundary |
| Phân loại lỗi tạm thời / bỏ qua / dừng hẳn | `src/errors.py` |
| Bảng điểm URL, blacklist domain, dedup theo domain | `src/filter_module.py` |
| Kiểm tra công ty còn hoạt động | `src/business_status.py` |
| Bổ sung tax code và tên tiếng Việt còn thiếu | `src/gemini_quick_search.py` |
| Chạy lại toàn bộ luồng mà không gọi API tốn tiền | Replay mode |

Việc thật của V2 là **chia nhỏ đơn vị công việc** từ mức “một công ty” xuống mức “một việc nhỏ”, và **tách code thành nhiều module nhỏ**. Đây là việc sửa lại, không phải xây mới.

Cách triển khai:

```text
Copy V1 sang root dành cho V2
Bỏ lại: output/, re_extract_tool/, venv/, graphify/, graphify-out/, index/
Copy riêng: data/company_data.db
Tạo lại venv trong root V2 (không copy venv cũ)
```

Sau khi copy, V1 được giữ nguyên và không sửa nữa. V1 dùng để so sánh kết quả và làm phương án quay lại nếu V2 chưa đạt yêu cầu.

## 2. Bốn vấn đề V1 mà V2 phải sửa

Phần này chỉ ghi quyết định V2. Bằng chứng code, database và giới hạn dữ liệu V1 nằm tại `docs/v1-operational-audit.md`.

| Vấn đề V1 | Quyết định bắt buộc của V2 |
|---|---|
| Query thiếu tỉnh/thành và AI có thể lấy contact ở footer của trang tin | Query theo tên phải có tỉnh/thành. AI chỉ đọc đoạn gần bằng chứng nhận diện công ty. |
| Retry dừng sớm hoặc lỗi tạm thời bị đổi thành kết quả rỗng | Dùng một retry executor chung. HTTP 5xx và timeout phải giữ đúng loại lỗi cho đến lớp điều phối. |
| Cache hit vẫn lưu thêm search result | Không lưu lại khi cache hit. Thêm unique key `(company_id, search_query, url)` sau khi dọn dữ liệu trùng. |
| Mọi trang bị chờ cố định ba giây | `wait_for_ms=0` mặc định. Chỉ domain đặc biệt mới có selector hoặc thời gian chờ riêng. |

Kế hoạch cũ từng đề xuất một bộ search result dùng chung cho nhiều công ty. Đề xuất đó đã bị bỏ vì query thường chứa tên công ty và gần như không được dùng chung.

V2 giữ search result theo từng công ty. Cách này bảo toàn review, trạng thái và lý do quyết định riêng của công ty đó.

Chi tiết migration cache nằm ở mục 10. Quy tắc retry nằm ở mục 11. Cấu hình scrape nằm ở mục 12. Test hồi quy bắt buộc nằm ở mục 17.

## 3. Những nguyên tắc vận hành của V2

### 3.1 Chi phí được kiểm tra trước mỗi bước tốn tiền

V2 không tự động scrape chỉ vì đã có URL.

Trước scrape, app lần lượt kiểm tra:

1. Công ty còn hoạt động hay đã giải thể. Nếu đã giải thể thì không scrape URL nào.
2. URL đã có kết quả cache còn mới hay chưa.
3. Trong cùng một domain, chỉ giữ **một URL điểm cao nhất**. Các URL còn lại của domain đó không được mở.
4. URL có đủ điểm và đủ bằng chứng hay chưa.
5. Tax code trên URL hoặc trang có mâu thuẫn với tax code mục tiêu hay không.
6. Domain có cho phép kiểm tra HTML bằng GET rẻ hay không.
7. HTML hoặc thông tin tóm tắt của kết quả search có chứa số blacklist hay không.
8. Tier hiện tại đã tìm được số hợp lệ và cần dừng hay chưa.

Kiểm tra 1 và 3 là hai bước tiết kiệm chi phí lớn nhất. V1 đã có cả hai và V2 phải giữ nguyên.

Ví dụ tác dụng của kiểm tra 3:

```text
Query trả về 10 URL cùng thuộc yellowpages.vn
Không dedup domain: mở 10 URL → tốn 10 credit → thông tin bằng 1 trang
Có dedup domain:    mở 1 URL  → tốn 1 credit  → thông tin tương đương
```

`Tier` là một nhóm nguồn có cùng mức ưu tiên.

Ví dụ:

- Tier 1: Business Directory.
- Tier 2: Job Portal.
- Tier 3: Facebook.

Thứ tự và số lượng tier do người dùng cấu hình. App không viết cố định chỉ ba nhóm trên vào code.

### 3.2 Mọi quyết định quan trọng nằm trong Source Policy

`Source Policy` là file quy tắc cho biết app phải ưu tiên domain nào, cộng bao nhiêu điểm, khi nào scrape và khi nào dừng.

Mỗi lần chạy giữ một bản chụp policy kèm version.

`Snapshot` là bản chụp input và cấu hình tại đúng thời điểm bắt đầu. Nhờ đó, app có thể giải thích một kết quả đã được tạo theo quy tắc nào.

Nếu policy thay đổi, kết quả cũ không bị xóa. App đánh dấu kết quả đó là `stale` — kết quả được tạo theo quy tắc cũ và có thể cần tính lại.

### 3.3 Field đã dùng trong query không được dùng lại để tự xác nhận

`Field` là một trường dữ liệu, ví dụ tên công ty, tax code, tỉnh/thành hoặc người đại diện pháp luật.

Ví dụ query dùng:

```text
Tên tiếng Việt + tỉnh/thành + từ khóa liên hệ
```

Tên tiếng Việt và tỉnh/thành giúp Google tìm đúng hướng.

Quy tắc này tránh tình trạng app tự kết luận “URL đúng” chỉ vì URL lặp lại chính các từ app đã dùng để tìm.

#### Field đã dùng trong query vẫn được tính điểm, nhưng ít hơn

Field đã dùng trong query **không bị bỏ hoàn toàn**. Nó vẫn là thông tin có ích, chỉ không được coi là bằng chứng độc lập.

Lý do: Google không luôn trả về trang chứa đúng cụm từ đã tìm. Việc xác nhận tên công ty thật sự có trên trang vẫn có giá trị.

V2 chia bằng chứng thành ba loại:

| Loại bằng chứng | Điểm | Có tự làm URL thành `accepted` |
|---|---|---|
| Field **chưa** dùng trong query (ví dụ tax code, người đại diện) | Điểm đầy đủ | Có |
| Field **đã** dùng trong query (ví dụ tên, tỉnh/thành) | Điểm giảm, mặc định 25% điểm đầy đủ | Không |
| Không có bằng chứng nhận diện nào | 0 | Không |

Điều kiện để một URL thành `accepted`:

```text
Tổng điểm >= ngưỡng policy (mặc định 35)
VÀ có ít nhất một bằng chứng CHƯA dùng trong query
```

Nếu URL đủ điểm nhưng **chỉ** có bằng chứng đã dùng trong query, URL vào nhóm `deferred`, không phải `rejected`.

Ví dụ:

```text
Query đã dùng: vietnamese_name + province

URL A: có tên công ty trên trang, có tax code đúng
       → tên: 25% điểm (đã dùng trong query)
       → tax code: điểm đầy đủ (chưa dùng trong query)
       → có bằng chứng độc lập → accepted

URL B: chỉ có tên công ty và tỉnh/thành trên trang
       → cả hai đều đã dùng trong query → chỉ được 25% điểm
       → không có bằng chứng độc lập → deferred, chờ người dùng xem
```

Tỷ lệ 25% được đặt trong policy. Người dùng có thể đổi thành 0% nếu muốn chặt hơn, hoặc 50% nếu thấy quá nhiều URL đúng bị đẩy sang `deferred`.

### 3.4 Rule V1 vẫn được giữ nếu chưa có quyết định thay thế

Rule mặc định vẫn là:

```text
Tiếp tục query cho đến khi có đủ 10 URL chất lượng
URL chất lượng phải có điểm từ 35 trở lên
Khi đủ 10 URL thì dừng tạo query mới và bắt đầu giai đoạn scrape
```

Điểm 35 và số lượng 10 được đặt trong policy. Người dùng có thể thay đổi sau mà không sửa code.

File export vẫn giữ khả năng truy ngược từng Search Result URL.

Thông tin lấy trực tiếp từ một URL phải được phân biệt với thông tin tổng hợp ở cấp công ty.

Các rule V1 về business status, replay và force refresh chỉ thay đổi khi có yêu cầu nghiệp vụ mới và test thay thế rõ ràng.

### 3.5 Bổ sung dữ liệu nhận diện trước khi tạo query

Bước đầu tiên của V1 là `Gemini Quick Search` — dùng Google Search Grounding để tra thông tin nhận diện của công ty.

Bước này điền các trường còn thiếu: tax code, tên tiếng Việt, địa chỉ.

V2 **giữ nguyên bước này làm bước đầu tiên**.

Lý do bắt buộc: rule ở mục 5.4 nói “không có tỉnh/thành thì chuyển sang query tax code”. Nếu bỏ bước Quick Search, tax code không được điền và rule dự phòng đó vô nghĩa.

Ví dụ:

```text
Dòng input:  CÔNG TY TNHH MINH AN   (không có địa chỉ, không có tax code)

Có Quick Search:  Gemini trả tax code 3701234567 và tỉnh Bình Dương
                  → app tạo được query đúng

Không Quick Search: không có tỉnh/thành, không có tax code
                  → công ty bị đưa vào danh sách cần kiểm tra thủ công
```

Trong database hiện tại, 1.252 trong 8.701 công ty không có địa chỉ. Đây đúng là nhóm cần bước này nhất.

Quick Search tạo contact ở **cấp công ty**. Contact cấp công ty phải được phân biệt với contact lấy từ một URL cụ thể.

### 3.6 Kiểm tra công ty còn hoạt động trước khi scrape

V1 có `business status gate` — bước đọc trang nguồn pháp lý để lấy tình trạng hoạt động.

Công ty tạm ngừng, đã giải thể, đóng mã số thuế hoặc chờ phá sản được kết thúc ngay với lý do được lưu lại.

“Không hoạt động tại địa chỉ đã đăng ký” **không** phải điều kiện dừng.

V2 giữ nguyên bước này. Đây là bước tiết kiệm chi phí lớn nhất của toàn hệ thống.

Ví dụ một công ty đã giải thể năm 2024:

```text
Có gate:    đọc 1 trang pháp lý → thấy "đã giải thể" → kết thúc → tốn ~1 credit
Không gate: chấm 10 URL → scrape 10 URL → gọi AI 10 lần → không tìm được gì
```

Bước này cần scrape một trang trước, nên nó là ngoại lệ có chủ đích của rule “kiểm tra chi phí trước mọi bước tốn tiền” ở mục 3.1.

### 3.7 Tax code chỉ được chặn URL khi app chắc chắn

Tax code vừa là bằng chứng, vừa là quyền phủ quyết.

Rule nghiệp vụ: nếu biết chắc cả hai tax code và hai giá trị khác nhau thì URL bị loại ngay.

Vấn đề thực tế: một dãy 10 số trên trang web có thể là tax code, số điện thoại hoặc số căn cước.

#### Tax code Việt Nam tự kiểm tra được

Chữ số cuối của tax code được tính ra từ chín chữ số đầu. Đây không phải số ngẫu nhiên.

Cách tính:

```text
Tax code 0100112437

9 số đầu:  0    1    0    0    1    1    2    4    3
Trọng số:  31   29   23   19   17   13   7    5    3
Nhân, cộng: 0 + 29 + 0 + 0 + 17 + 13 + 14 + 20 + 9  = 102

102 chia 11  → dư 3
10 - 3 = 7   → chữ số cuối phải là 7   → đúng
```

Số điện thoại không có quy tắc này nên chỉ lọt qua do trùng hợp.

Kết quả kiểm tra trên database hiện tại:

| Dữ liệu thật | Kết quả |
|---|---|
| 7.448 tax code của công ty | 99,9% qua được phép kiểm tra |
| 5.687 số điện thoại 10 chữ số | chỉ 9,9% lọt qua |

Một phép tính duy nhất loại được khoảng 90% trường hợp nhận nhầm, trên mọi website kể cả website chưa từng gặp.

#### Thang tin cậy

| Bước | Kiểm tra | Tác dụng |
|---|---|---|
| 1 | Đúng 10 chữ số, hoặc 13 chữ số dạng `...-001` | lọc hình dạng |
| 2 | Qua được phép kiểm tra chữ số cuối | loại 90% số điện thoại |
| 3 | Ngay trước số có chữ `MST`, `Mã số thuế`, `Mã số doanh nghiệp`, `Tax code` | bằng chứng rất mạnh |
| 4 | Ngay trước số có chữ `Điện thoại`, `Hotline`, `Tel`, `Zalo` | đây là số điện thoại — loại |
| 5 | Tax code nằm trong chính đường dẫn URL | mạnh nhất, V1 đã dùng cho masothue |

#### Trang lạ gặp lần đầu: dùng ba kết quả, không phải hai

Đây là quy tắc quan trọng nhất của mục này.

| Kết quả | Nghĩa | App làm gì |
|---|---|---|
| `match` | Chắc chắn là tax code và trùng mục tiêu | Cộng điểm |
| `mismatch` | Chắc chắn là tax code và khác mục tiêu | **Loại URL** |
| `unknown` | Không xác định được đó có phải tax code | **Không làm gì**, chấm URL bằng bằng chứng khác |

`unknown` không bao giờ được loại URL.

Ví dụ tai họa nếu chỉ dùng hai kết quả:

```text
Tax code mục tiêu: 3701234567
Trang lạ có chuỗi: 0912345678

Hai kết quả: app đoán đó là tax code → khác mục tiêu → loại URL
             → mất một trang đúng, không có lý do rõ ràng

Ba kết quả:  phép kiểm tra chữ số cuối không đạt
             không có chữ MST đứng trước
             đầu số 09 là đầu số di động
             → unknown → URL vẫn được xét bằng domain, tên và địa chỉ
```

Hai chiều dùng hai mức chặt khác nhau:

- Để **cộng điểm**: đạt bước 1 và 2 là đủ. Nếu sai thì chỉ mất một URL tốt. Thiệt hại nhỏ.
- Để **loại URL**: phải đạt bước 2 **và** bước 3, hoặc đạt bước 5. Loại URL là hành động phá hủy và không để lại dấu vết cho người dùng, nên không được làm theo phỏng đoán.

#### Phanh an toàn khi tax-code veto loại hết URL

Ngay cả tax code `confirmed` cũng có thể sai do người dùng nhập nhầm hoặc app đã nâng nhầm trước đó.

Vì vậy, nếu có ít nhất một URL `accepted` hoặc đủ ngưỡng bằng chứng **trước khi kiểm tra tax code**, và tax-code veto là lý do duy nhất làm tất cả các URL đó bị loại, app không được âm thầm kết thúc với kết quả “không tìm thấy”.

App phải:

```text
Không chốt các URL đó thành rejected
Giữ trạng thái held_for_review
Dừng tự động xử lý công ty
Ghi reason = tax_code_veto_rejects_all
Đưa công ty vào Deferred Review
```

Màn hình review phải hiển thị tax code mục tiêu và nguồn gốc của nó, tax code đối thủ, URL bị ảnh hưởng, tên/địa chỉ trên từng trang và các trang từng làm tax code mục tiêu được nâng lên `confirmed`.

Rule này **không** chạy chỉ vì kết quả cuối cùng có 0 URL. Nếu các URL đã không đủ điểm vì sai tên, sai tỉnh hoặc không có bằng chứng nhận diện trước khi veto, 0 URL là kết quả bình thường.

Ví dụ:

```text
Người dùng nhập nhầm: 3701234568
8 URL có tên và địa chỉ đúng, nhưng đều ghi: 3701234567

Không có phanh: 8 URL bị loại → app báo không tìm thấy contact
Có phanh:       8 URL held_for_review
                company reason = tax_code_veto_rejects_all
                người dùng thấy ngay tax code input có thể bị gõ sai
```

#### App tự học dần các trang lạ

Mỗi lần gặp `unknown`, app ghi lại domain, chuỗi số tìm được và lý do không xác định được.

Người dùng xem lại danh sách này theo định kỳ. Khi một website được xác nhận có định dạng ổn định, domain đó được thêm rule riêng trong policy.

Nhờ vậy các domain đã biết ngày càng chặt hơn, còn domain lạ vẫn an toàn theo mặc định.

### 3.8 Dữ liệu do Quick Search bổ sung phải được đánh dấu là chưa xác nhận

Đây là vấn đề khó nhất của bước Quick Search.

App dùng Quick Search để điền field còn thiếu. Nhưng để kiểm tra Quick Search có đúng công ty hay không thì lại cần chính các field đó. Đây là vòng lặp không thể phá hoàn toàn.

Vì vậy V2 không cố chứng minh Quick Search đúng. V2 **đánh dấu mức tin cậy** và **giới hạn quyền** của dữ liệu chưa xác nhận.

#### Mỗi field mang theo nguồn gốc và mức tin cậy

| Nguồn gốc | Nghĩa | Mức tin cậy |
|---|---|---|
| `user_input` | Người dùng nhập trong file | `confirmed` |
| `quick_search` | Gemini tra được | `unconfirmed` |
| `scraped` | Lấy từ trang đã scrape | `unconfirmed` cho đến khi có xác nhận chéo |

#### Quyền của field chưa xác nhận

Đây là rule quan trọng nhất của mục này.

| Việc | Field `confirmed` | Field `unconfirmed` |
|---|---|---|
| Dùng để tạo query | Được | Được |
| Cộng điểm cho URL | Điểm đầy đủ | Điểm giảm một nửa |
| **Loại URL (veto)** | **Được** | **Không bao giờ** |

Lý do rule veto: nếu Gemini trả sai tax code và app dùng tax code đó để loại URL, thì **mọi URL đúng đều bị loại** và người dùng không thấy nguyên nhân. Một lần Gemini đoán sai sẽ phá toàn bộ công ty đó.

Đây cũng là điểm nối với mục 3.7: `mismatch` chỉ được loại URL khi tax code mục tiêu là `confirmed`.

#### Kiểm tra kết quả Quick Search bằng chính bộ chấm điểm khi import

V1 đã có bộ chấm điểm so khớp công ty ở bước import: tax code trùng được 100 điểm, tên/tỉnh/địa chỉ/domain/phone góp điểm, tax code khác nhau bị 0 điểm, tự động khớp cần từ 85 điểm và cách người thứ hai 15 điểm.

V2 dùng lại đúng bộ này để chấm kết quả Quick Search so với dòng input gốc.

```text
Input người dùng:  CÔNG TY TNHH MINH AN, Bình Dương
Gemini trả về:     CÔNG TY TNHH MINH AN, Bình Dương, MST 3701234567

→ tên khớp, tỉnh khớp → điểm cao → nhận, đánh dấu unconfirmed
```

```text
Input người dùng:  CÔNG TY TNHH MINH AN, Bình Dương
Gemini trả về:     CÔNG TY TNHH MINH AN, Hà Nội, MST 0101234567

→ tỉnh mâu thuẫn với dữ liệu người dùng đã cung cấp
→ KHÔNG nhận, ghi lý do quick_search_conflict, giữ nguyên input gốc
```

**Rule mỏ neo:** field nào người dùng đã cung cấp thì Quick Search không được ghi đè và không được mâu thuẫn. Quick Search chỉ được điền vào chỗ trống.

#### Khi Gemini trả về nhiều công ty cùng tên

App đếm số công ty khác nhau trong các nguồn Gemini đã dẫn.

```text
Nếu các nguồn chỉ về 1 công ty  → nhận, unconfirmed
Nếu các nguồn chỉ về >= 2 công ty → không nhận
                                   → company vào hàng chờ review
                                   → lý do: identity_ambiguous
```

App không tự chọn một trong nhiều công ty cùng tên.

#### Nâng từ unconfirmed lên confirmed

Promotion là việc nâng một field từ `unconfirmed` lên `confirmed`. Sau promotion, field mới có quyền loại URL, nên mọi bằng chứng dùng để promotion phải lưu được nguồn gốc và phải qua toàn bộ điều kiện sau:

1. Có ít nhất hai trang hỗ trợ thuộc hai domain và hai `source family` khác nhau; **hoặc** một trang thuộc loại `authoritative_registry`.
2. Trang không được tìm thấy bằng query chứa chính field đang được xác nhận. Trang tìm bằng tax code không được dùng để xác nhận tax code đó.
3. Tên công ty trên trang phải khớp với công ty mục tiêu theo rule bên dưới.
4. Hai đoạn văn quanh field không được gần như giống hệt nhau. App chuẩn hóa chữ, khoảng trắng và dấu câu rồi so sánh token; similarity từ ngưỡng policy `promotion_evidence_similarity_threshold` (mặc định `0.85`) trở lên chỉ được tính là một nguồn.
5. Không có field đối thủ cũng vượt qua các điều kiện 1–4. Nếu hai tax code cùng đủ bằng chứng, dừng với `identity_ambiguous`.

`source family` là một nhóm website có khả năng cùng mạng lưới hoặc sao chép cùng một nguồn. Khác domain nhưng cùng source family chỉ được tính là một nguồn.

Mỗi promotion phải lưu:

```text
field và giá trị được nâng
supporting URLs, domain và source_family
query_id và danh sách field đã dùng trong query
đoạn bằng chứng quanh field
điểm/quan hệ so khớp tên công ty
policy version và thời điểm promotion
```

Nếu nguồn đáng tin hơn sau này mâu thuẫn, app hạ field về `unconfirmed`, đánh dấu kết quả chịu ảnh hưởng là `stale` và đưa công ty vào review.

#### Tên giống 90% chưa tự động là cùng một công ty

App chuẩn hóa chữ hoa/thường, khoảng trắng, dấu câu, dấu tiếng Việt và cách viết loại hình doanh nghiệp trước khi tính similarity.

`name_similarity >= promotion_name_probable_threshold` (mặc định `0.90`) chỉ tạo kết quả `probable`, không tự đủ để promotion. Một tên chứa toàn bộ tên mục tiêu nhưng có thêm từ phân biệt vẫn có thể là công ty khác:

```text
MINH AN
MINH AN PHÁT
MINH AN GROUP
ĐẦU TƯ MINH AN
```

Để tên `probable` được dùng trong promotion, phải có thêm ít nhất một field nhận diện độc lập mạnh như địa chỉ cụ thể, người đại diện, official domain hoặc tax code đã confirmed; đồng thời không được có field mạnh mâu thuẫn. Tax code khác nhau luôn thắng điểm similarity của tên.

App lưu cả `name_similarity` và quan hệ, ví dụ `exact`, `legal_form_variant`, `target_contained_with_suffix`, `probable` hoặc `conflict`, thay vì chỉ lưu đúng/sai.

#### Trường hợp input chỉ có tên công ty

Đây là trường hợp xấu nhất và cần rule rõ ràng.

| Tình huống | App làm gì |
|---|---|
| Quick Search trả **tên + tỉnh + tax code**, chỉ về một công ty | Điền tỉnh và tax code, đánh dấu `unconfirmed`, chạy query bình thường |
| Quick Search trả **tax code nhưng không có tỉnh** | Chạy query chỉ bằng tax code. Query này không cần tỉnh/thành |
| Quick Search trả **tỉnh nhưng không có tax code** | Chạy query tên + tỉnh. URL cần bằng chứng độc lập mới được `accepted` |
| Quick Search trả **nhiều công ty cùng tên** | Dừng công ty, ghi `identity_ambiguous`, đưa vào hàng chờ review |
| Quick Search **không trả được gì** | Dừng công ty, ghi `dependency_missing: province, tax_code`, đưa vào danh sách cần bổ sung input |

Hai dòng cuối bảng là câu trả lời cho câu hỏi “nếu chỉ có tên thì app làm gì”: app **không** chạy query chỉ có tên. Nó dừng lại và báo cho người dùng.

Nếu người dùng muốn thử dù thiếu dữ liệu, policy có thể bật:

```yaml
allow_name_only_query: false      # mặc định tắt
name_only_score_threshold: 60     # nếu bật, ngưỡng cao hơn mức 35 thường
name_only_max_queries: 1          # chỉ cho phép một query duy nhất
```

Cách này giữ quyền quyết định cho người dùng và giới hạn thiệt hại khi bật.

## 4. Dữ liệu đầu vào của một công ty

### 4.1 Các trường chính

| Trường | Bắt buộc | Cách V2 sử dụng |
|---|---:|---|
| Tên công ty | Có | Nhận diện company input và tạo query khi policy chọn. |
| Tên tiếng Việt | Không | Có thể dùng trong query bằng placeholder. |
| Tax code | Không | Tạo query hoặc làm bằng chứng nếu chưa dùng trong query. |
| Tỉnh/thành | Không, nhưng cần cho query theo tên mặc định | Thu hẹp kết quả search theo địa phương. |
| Người đại diện pháp luật | Không | Tạo query hoặc làm bằng chứng độc lập. |
| Blacklist phone | Không | Kiểm tra URL và contact để tránh thu thập lại số cũ. |
| Trường do người dùng bổ sung | Không | Có thể được đưa vào công thức query nếu policy cho phép. |

### 4.2 Địa chỉ chỉ còn một cấp: tỉnh/thành

Kế hoạch cũ từng đề xuất Address Level 1 và Level 2. V2 bỏ cách chia đó.

V2 chỉ dùng một trường có cấu trúc:

```text
province
```

Trường này chứa tỉnh hoặc thành phố trực thuộc trung ương.

Ví dụ:

```text
Bình Dương
Hồ Chí Minh
Đồng Nai
```

App không dùng phường, xã, quận, huyện hoặc tên đường làm điều kiện bắt buộc.

Lý do:

- Tên phường, xã có thể chưa ổn định sau sáp nhập.
- Dữ liệu cũ và mới có thể ghi hai tên khác nhau cho cùng khu vực.
- Công ty trong khu công nghiệp có thể không có tên đường cụ thể.
- Dùng tên đường không chắc chắn có thể loại nhầm URL đúng.

Nếu file đầu vào có địa chỉ đầy đủ, app vẫn giữ nguyên chuỗi đó để hiển thị và xuất báo cáo.

Phần vận hành chỉ lấy tỉnh/thành. Các thành phần còn lại không được dùng để chặn query hoặc tự động loại URL.

Nếu tỉnh/thành có nhiều cách viết, người dùng có thể cung cấp bảng alias.

`Alias` là các cách viết khác nhau được coi là cùng một giá trị.

Ví dụ:

```text
TP.HCM
HCM
Thành phố Hồ Chí Minh
```

Ba cách viết trên có thể được chuẩn hóa thành `Hồ Chí Minh`.

Nếu app không xác định chắc chắn tỉnh/thành, nó không tự đoán theo tên đường hoặc khu công nghiệp. Dòng input được đưa vào danh sách cần kiểm tra.

## 5. Công thức query bằng placeholder

### 5.1 Placeholder là gì

`Placeholder` là vị trí trống trong một công thức query. Khi chạy, app thay vị trí đó bằng dữ liệu thật của từng công ty.

Ví dụ công thức:

```text
"{{vietnamese_name}}" "{{province}}" ({{contact_keywords}})
```

Với dữ liệu:

```text
vietnamese_name = CÔNG TY TNHH MINH AN
province = Bình Dương
contact_keywords = "số điện thoại" OR "liên hệ" OR "contact"
```

Query thực tế trở thành:

```text
"CÔNG TY TNHH MINH AN" "Bình Dương"
("số điện thoại" OR "liên hệ" OR "contact")
```

Người dùng quyết định công thức. App không cố định tên công ty phải đứng trước hay tax code phải chạy ở bước thứ mấy.

### 5.2 Hai loại placeholder

#### Placeholder lấy từ Company Input Profile

`Company Input Profile` là bản dữ liệu đã chuẩn hóa của một công ty trước khi chạy pipeline.

Ví dụ:

```text
{{company_name}}
{{vietnamese_name}}
{{tax_code}}
{{province}}
{{legal_representative}}
{{custom_input_field}}
```

Nếu file input có thêm cột `factory_name`, người dùng có thể cho phép `{{factory_name}}` xuất hiện trong query.

#### Placeholder là giá trị cố định do người dùng khai báo

Giá trị cố định phù hợp với các nhóm keyword luôn được dùng lại.

Ví dụ:

```yaml
custom_values:
  contact_keywords: '"số điện thoại" OR "liên hệ" OR "contact"'
  recruitment_keywords: '"tuyển dụng" OR "việc làm"'
```

Sau đó query dùng:

```text
"{{vietnamese_name}}" "{{province}}" ({{contact_keywords}})
```

Người dùng chỉ sửa nhóm keyword ở một nơi. Mọi query liên quan tự nhận giá trị mới ở lần chạy sau.

### 5.3 Mỗi công thức phải khai báo field bắt buộc

Ví dụ:

```yaml
query_templates:
  - name: contact_by_vietnamese_name
    template: '"{{vietnamese_name}}" "{{province}}" ({{contact_keywords}})'
    required_fields:
      - vietnamese_name
      - province
```

Nếu công ty không có `province`, app không tạo một query tên quá rộng.

Work unit của query được ghi:

```text
skipped
reason: missing required field province
```

Nếu có tax code, planner có thể chuyển sang công thức khác:

```text
"{{tax_code}}"
```

`Planner` là khối đọc input và policy để quyết định các work unit nào cần được tạo.

### 5.4 Query theo tên phải có tỉnh/thành

Policy mặc định áp dụng quy tắc:

- Query có tên công ty hoặc tên tiếng Việt phải kèm `{{province}}`.
- Query chỉ bằng tax code có thể chạy không cần tỉnh/thành.
- Không có tỉnh/thành và không có tax code thì không chạy broad name-only query.

`Broad query` là câu tìm kiếm quá rộng, ví dụ chỉ có `"MINH AN"` mà không có địa phương hoặc mã số nhận diện.

Trường hợp thiếu dữ liệu được ghi `dependency_missing` — chưa chạy tiếp được vì thiếu thông tin đầu vào cần thiết.

### 5.5 App kiểm tra công thức trước khi chạy thật

Trước khi mở batch, app phải hiển thị bản xem trước.

Ví dụ với 1.000 công ty:

```text
920 công ty tạo được query theo tên + tỉnh/thành
55 công ty chuyển sang query tax code
25 công ty thiếu cả tỉnh/thành và tax code
0 placeholder không hợp lệ
```

Nếu có placeholder viết sai như `{{provine}}`, app báo lỗi cấu hình trước khi gọi API.

Việc kiểm tra trước giúp tránh trả tiền cho hàng nghìn query được tạo sai.

## 6. Source Policy: cấu hình nguồn và thứ tự ưu tiên

Mỗi domain hoặc nhóm domain có thể cấu hình:

- Thuộc tier nào.
- Thứ tự ưu tiên.
- Điểm cộng khi xuất hiện trong search.
- Điểm tối thiểu để được xem xét scrape.
- Có cho phép Cheap GET Preflight hay không.
- Chế độ scrape.
- Selector cần chờ nếu trang động.
- Số worker tối đa.
- Số lần thử API.
- Giới hạn chi phí.

`Cheap GET Preflight` là bước tải HTML bằng request rẻ trước khi dùng Firecrawl Scrape có tính phí.

Thứ tự mặc định hiện tại:

1. Business Directory.
2. Nếu chưa có contact mới phù hợp, chuyển Job Portal.
3. Nếu vẫn chưa có contact mới phù hợp, chuyển Facebook.

Saramin hoặc domain mới chỉ cần thêm vào policy. Không cần sửa khối chấm điểm hoặc pipeline.

Ví dụ:

```yaml
source_families:
  - name: yellowpages_network
    domains:
      - yellowpages.vn
      - yellowpages.com.vn
      - trangvangvietnam.com

promotion_name_probable_threshold: 0.90
promotion_evidence_similarity_threshold: 0.85

tiers:
  - name: authoritative_registry # nguồn đăng ký chính thức, có thể tự xác nhận nếu tên khớp
    priority: 0
    scrape_mode: scrape_all_planned
    require_tax_code_match: true
    one_url_per_domain: true

  - name: tax_directory          # nguồn tổng hợp/tra cứu thuế, vẫn cần xác nhận chéo
    priority: 1
    scrape_mode: scrape_all_planned
    require_tax_code_match: true
    one_url_per_domain: true

  - name: business_directory
    priority: 2
    scrape_mode: scrape_all_planned
    one_url_per_domain: true

  - name: job_portal
    priority: 3
    scrape_mode: stop_on_first_valid_phone
    one_url_per_domain: true

  - name: facebook
    priority: 4
    scrape_mode: stop_on_first_valid_phone
    one_url_per_domain: true
```

`scrape_all_planned` nghĩa là scrape tất cả URL đã được chọn trong tier.

`stop_on_first_valid_phone` nghĩa là ngừng mở URL mới khi tier đã tìm được một số điện thoại hợp lệ.

Mỗi tier được chọn chế độ riêng.

`one_url_per_domain: true` nghĩa là trong cùng một domain chỉ URL điểm cao nhất được mở. Mặc định bật cho mọi tier.

`authoritative_registry` và `tax_directory` không được coi là tương đương. Chỉ nguồn đăng ký chính thức hoặc nguồn được người dùng cấu hình rõ là `authoritative_registry` mới có thể tự mình hỗ trợ promotion. Trang tổng hợp như Masothue thuộc `tax_directory`, vẫn cần xác nhận chéo.

`require_tax_code_match: true` áp dụng cho cả hai tier trên khi nhận contact. Trang Masothue mang tax code trong đường dẫn, nên tax code trên trang phải trùng tax code mục tiêu mới được chấp nhận số điện thoại. Rule này V1 đã có và V2 phải giữ; nó không biến Masothue thành nguồn tự xác nhận.

Ví dụ:

```text
Tax code mục tiêu: 3701234567
URL tìm được:      masothue.com/3709999999-cong-ty-minh-an
                                ^^^^^^^^^^ công ty khác, tên gần giống
→ hai tax code khác nhau → loại URL, ghi lý do masothue_tax_mismatch
```

## 7. Một ví dụ hoàn chỉnh khi V2 chạy

Ví dụ dưới đây dùng số liệu minh họa cụ thể để thể hiện cách các module phối hợp.

### 7.1 Input

```text
Tên công ty: CÔNG TY TNHH MINH AN
Tên tiếng Việt: CÔNG TY TNHH MINH AN
Tỉnh/thành: Bình Dương
Tax code: 3701234567
Người đại diện: Nguyễn Văn A

Blacklist:
- 0901111222, label = wrong_num
- 0274388888, label = same_num
```

App chỉ hiểu `wrong_num` và `same_num` là label do người dùng cung cấp.

App không tự kết luận số nào sai, không hợp lệ hoặc trùng. Việc đánh giá đó đã được người dùng xác nhận thủ công trước khi nhập.

### 7.2 Tạo và chạy query

Query 1:

```text
"CÔNG TY TNHH MINH AN" "Bình Dương"
("số điện thoại" OR "liên hệ" OR "contact")
```

Firecrawl Search trả 8 URL. Sau khi chấm, 4 URL đạt từ 35 điểm.

Query 2:

```text
"3701234567"
```

Query 2 trả thêm 10 URL. Có 6 URL mới đạt từ 35 điểm.

Tổng cộng đã có 10 URL chất lượng. Planner dừng tạo query mới và chuyển sang bước kiểm tra URL.

### 7.3 Chấm và chia URL

Mỗi URL được đưa vào một trong ba nhóm:

- `Accepted`: đủ điều kiện đi tiếp.
- `Deferred`: có tín hiệu nhưng chưa đủ chắc, cần người dùng xem.
- `Rejected`: điểm quá thấp hoặc có mâu thuẫn rõ.

Ví dụ:

```text
10 URL accepted
2 URL deferred
6 URL rejected hoặc không đạt ngưỡng
```

`Deferred` không phải lỗi. Đây là hàng chờ dành cho trường hợp app không nên tự quyết vì bằng chứng còn yếu.

Hai URL deferred không chặn các công ty khác. Worker tiếp tục xử lý company tiếp theo trong lúc chờ người dùng review.

### 7.4 Cheap GET Preflight

Trong 10 URL accepted, policy cho phép GET rẻ trên 4 URL thuộc Business Directory.

`Metadata` là thông tin tóm tắt đã có từ search, chủ yếu gồm URL, tiêu đề trang và phần mô tả.

Kết quả:

```text
URL 1 chứa 0901111222 → skip URL 1
URL 2 không chứa blacklist → pass
URL 3 không chứa blacklist → pass
URL 4 không phản hồi GET → kiểm tra metadata search
```

`Regex` là cách tìm một mẫu ký tự trong văn bản. Ở đây regex chỉ dùng để tìm các cách viết khác nhau của đúng số blacklist.

Ví dụ `0901111222`, `0901 111 222` và `0901-111-222` có thể được chuẩn hóa để so sánh cùng một giá trị.

Nếu URL 4 có title và description không chứa blacklist nhưng thông tin chưa đủ, URL vẫn được scrape vì trước đó đã đạt điểm.

Blacklist match chỉ skip URL đang kiểm tra. Nó không skip toàn bộ công ty.

### 7.5 Scrape song song và dừng mềm

Giả sử còn 9 URL có thể scrape và tier dùng chế độ `stop_on_first_valid_phone`.

Ba worker nhận ba URL đầu tiên.

`Concurrency` là số công việc được chạy cùng lúc. Trong ví dụ này concurrency bằng 3.

Kết quả:

```text
Worker 1: tìm thấy 0274388888 → trùng blacklist, gắn label same_num
Worker 2: tìm thấy 0912345678 → số mới hợp lệ
Worker 3: đang chạy → được phép hoàn tất và lưu kết quả
6 URL còn lại: chưa được mở → dừng theo policy
```

`Dừng mềm` nghĩa là không mở việc mới, nhưng không cắt ngang URL đang gần hoàn tất.

Nếu cắt ngang ngay, app có thể đã tốn credit scrape nhưng chưa kịp lưu kết quả.

Trong ví dụ, app chỉ mở 3/9 URL. Nếu mỗi URL tốn một scrape credit, app tiết kiệm được tối đa 6 credit ở tier này.

### 7.6 Cắt nội dung trước khi gọi AI

Firecrawl trả một trang Markdown dài 25.000 ký tự.

`Markdown` là bản nội dung trang web đã được làm gọn thành văn bản có tiêu đề, đoạn, danh sách và bảng.

`Context Slicing` là cắt lấy các đoạn gần dữ liệu nhận diện công ty trước khi gửi AI.

App tìm các `anchor` — điểm neo như tax code, tên pháp lý hoặc người đại diện.

Ví dụ:

```text
[Giữ] Công ty TNHH Minh An, MST 3701234567, tại Bình Dương...
[Giữ] Số liên hệ của công ty: 0912345678...
[Bỏ]  Liên hệ quảng cáo của tòa soạn: 0289999999...
```

Sau khi cắt, AI chỉ nhận 1.800 ký tự thay vì 25.000 ký tự.

Lượng văn bản gửi AI giảm khoảng 92,8% trong ví dụ này.

Context Slicing tiết kiệm token AI và giảm khả năng lấy nhầm footer. Nó không hoàn lại credit scrape đã dùng, nên Cheap GET vẫn phải chạy trước.

### 7.7 Kết quả được lưu

Mỗi contact được lưu cùng:

- Giá trị contact.
- URL nguồn.
- Đoạn văn chứa contact.
- Ngày đăng nếu trang có công bố.
- Ngày app scrape.
- Kết quả so sánh blacklist.
- Lý do accepted hoặc rejected.

Ví dụ:

```text
0912345678
source_url: https://example-directory.vn/minh-an
published_date: 2026-06-15
blacklist_match: false
decision: valid_contact
```

Nếu trang không có ngày đăng, trường `published_date` để trống. App không dùng ngày scrape để giả làm ngày đăng.

## 8. Quy trình vận hành đầy đủ của V2

Thứ tự đầy đủ:

| Thứ tự | Bước | Có tốn tiền |
|---:|---|---|
| 1 | Đọc và chuẩn hóa input | Không |
| 2 | Chụp lại cấu hình của lần chạy | Không |
| 3 | **Gemini Quick Search — bổ sung tax code, tên tiếng Việt, địa chỉ** | Có |
| 4 | Lập kế hoạch query | Không |
| 5 | Kiểm tra Search Cache | Không |
| 6 | Search cho đến khi đủ URL chất lượng | Có |
| 7 | Chấm URL, dedup domain, kiểm tra tax code | Không |
| 8 | Người dùng review Deferred | Không |
| 9 | **Business status gate — công ty còn hoạt động hay không** | Có |
| 10 | Cheap GET và metadata fallback | Rất rẻ |
| 11 | Lập kế hoạch scrape theo tier | Không |
| 12 | Scrape với thời gian chờ theo domain | Có |
| 13 | Cắt ngữ cảnh và extract | Có |
| 14 | So sánh blacklist và tổng hợp | Không |
| 15 | Kết thúc tier hoặc mở tier tiếp theo | Không |
| 16 | Tính trạng thái tổng hợp | Không |

Hai bước in đậm là bước V1 đang có nhưng bản kế hoạch trước đã bỏ sót.

### Bước 1 — Đọc và chuẩn hóa input

App chuẩn hóa tên, tax code, tỉnh/thành, người đại diện và blacklist phone.

Chuỗi địa chỉ đầy đủ được giữ để hiển thị. Chỉ tỉnh/thành được dùng như field địa chỉ có cấu trúc.

### Bước 2 — Chụp lại cấu hình của lần chạy

App lưu version của Source Policy, công thức query và input.

### Bước 3 — Gemini Quick Search

App gọi Google Search Grounding để tra thông tin nhận diện của công ty.

Bước này điền các trường còn thiếu: tax code, tên tiếng Việt, địa chỉ, người đại diện.

Kết quả được lưu thành contact **cấp công ty**, kèm các URL mà Gemini đã dẫn nguồn.

App đếm số lần dùng trong ngày để không vượt hạn mức miễn phí.

Các URL Gemini đã dẫn nguồn được loại khỏi kết quả search ở bước sau để không trả tiền hai lần cho cùng một trang.

Nếu bước này thất bại, app vẫn đi tiếp bằng dữ liệu input gốc. Đây không phải lỗi chặn.

### Bước 4 — Lập kế hoạch query

Planner thay placeholder bằng dữ liệu thật.

Mỗi query ghi rõ field nào đã được dùng. Danh sách này được chuyển sang khối chấm URL để tránh tính điểm lặp.

### Bước 5 — Kiểm tra Search Cache

`Provider` là dịch vụ bên ngoài thực hiện một nhiệm vụ, ví dụ Firecrawl cung cấp search và scrape.

App tạo `fingerprint` — dấu vân tay từ query, provider, option và version policy.

Hai request chỉ được coi là giống nhau khi fingerprint giống nhau.

Cache hit trả lại kết quả cũ và ghi chi phí search bằng 0. App không insert lại các Search Result URL.

### Bước 6 — Search cho đến khi đủ URL chất lượng

Query chạy theo thứ tự trong policy.

Khi đủ 10 URL có điểm từ 35 trở lên, planner đóng giai đoạn search. Query chưa chạy được đánh dấu `cancelled_by_policy`.

Trạng thái này có nghĩa query không còn cần thiết, không phải query bị lỗi.

### Bước 7 — Chấm URL, dedup domain và kiểm tra tax code

Khối chấm điểm xem domain, title, description và evidence chưa dùng trong query.

`Evidence` là bằng chứng cho thấy URL thuộc đúng công ty mục tiêu.

Tax code exact có thể là bằng chứng rất mạnh nếu tax code chưa được dùng làm field chính của query đó.

Ba việc được làm theo thứ tự:

1. Loại ngay các domain blacklist và domain tin tức.
2. Kiểm tra tax code theo ba kết quả `match`, `mismatch`, `unknown` như mục 3.7. Chỉ `mismatch` loại URL.
3. Chấm điểm, sau đó trong mỗi domain chỉ giữ **một URL điểm cao nhất**.

URL được chia thành accepted, deferred hoặc rejected. Mỗi URL giữ bảng điểm chi tiết để người dùng kiểm tra.

URL bị loại vì trùng domain vẫn được lưu kèm lý do `duplicate_domain`. Nó không bị xóa khỏi database, để export vẫn truy ngược được.

### Bước 8 — Người dùng review Deferred

User có thể chọn từng URL hoặc nhiều URL rồi bấm:

- Scrape.
- Skip.
- Keep deferred.

Quyết định được lưu. Khi resume, app không hỏi lại các URL đã được xử lý.

### Bước 9 — Business status gate

Trước khi mở toàn bộ URL, app scrape một trang nguồn pháp lý để đọc tình trạng hoạt động.

Nếu công ty tạm ngừng, đã giải thể, đóng mã số thuế hoặc chờ phá sản:

```text
company kết thúc với trạng thái done
stop_reason: business_status_inactive
số URL được scrape thêm: 0
```

Trạng thái “không hoạt động tại địa chỉ đã đăng ký” không phải điều kiện dừng. Công ty đó tiếp tục chạy bình thường.

Nếu không đọc được tình trạng, app đi tiếp. Không có kết luận nghĩa là không chặn.

### Bước 10 — Cheap GET và metadata fallback

App chỉ GET những domain được policy cho phép.

`Fallback` là cách dự phòng. Nếu GET không phản hồi, app dùng URL, title và description từ kết quả search.

Nếu metadata vẫn không đủ nhưng URL đã accepted, app chuyển sang scrape.

### Bước 11 — Lập kế hoạch scrape theo tier

Tier có thể scrape toàn bộ URL đã chọn hoặc dừng khi có số hợp lệ đầu tiên.

Worker chỉ nhận các Scrape Work Unit còn pending.

`Pending` nghĩa là việc đã được tạo nhưng chưa có worker nào xử lý.

### Bước 12 — Scrape với thời gian chờ theo domain

Trang thông thường dùng smart wait của Firecrawl và `waitFor=0`.

Trang động chỉ chờ selector nếu domain có cấu hình riêng.

App không gửi `waitUntil: networkidle` như một option chung của Batch Scrape vì API hiện tại không có field đó.

### Bước 13 — Cắt ngữ cảnh và extract

`Extract` là lấy dữ liệu có cấu trúc như phone, email hoặc ngày đăng từ phần nội dung đã chọn.

AI chỉ nhận Context Slice, không nhận cứng 15.000 ký tự đầu trang.

Contact chỉ được chấp nhận khi chuỗi contact xuất hiện trong đoạn bằng chứng đã lưu.

### Bước 14 — So sánh blacklist và tổng hợp

Số điện thoại được chuẩn hóa rồi so với blacklist của đúng công ty.

Nếu trùng, app gắn lại label do người dùng cung cấp. App không tự đổi `wrong_num`, `invalid_num`, `same_num` hoặc label tùy chỉnh.

### Bước 15 — Kết thúc tier hoặc mở tier tiếp theo

Nếu tier đã đạt mục tiêu, các work unit chưa mở được đóng theo policy.

Nếu tier chưa có contact mới, planner mở tier kế tiếp.

### Bước 16 — Tính trạng thái tổng hợp

App đọc các work unit và lần thử đã lưu để tạo thẻ trạng thái của công ty.

App không dùng một status duy nhất cho mọi ý nghĩa.

## 9. Các khối chức năng của V2

Mỗi hàng dưới đây là một module có thể test riêng.

`Artifact` là kết quả gốc được lưu lại, ví dụ một bộ search result hoặc một trang Markdown.

`Contact Observation` là contact vừa quan sát được từ một URL. Nó chưa phải kết quả cuối trước khi qua bước blacklist và tổng hợp.

`Attempt` là một lần worker thử thực hiện work unit.

`Work Log` là sổ lịch sử chỉ ghi thêm. Nó lưu việc nào đã được tạo, ai nhận, đã thử mấy lần và kết quả cuối là gì. Nó dùng để tra cứu và giải thích, **không** dùng để tính trạng thái hiện tại.

### 9.1 Nguyên tắc chia module

Mỗi file chỉ làm một việc. File nhỏ dễ sửa, dễ test và dễ nhờ AI sửa hộ mà không phá phần khác.

Quy ước:

- Một file không quá khoảng 200 dòng.
- File nào gọi API tốn tiền thì không được đồng thời ghi database.
- File nào quyết định nghiệp vụ thì không được gọi API.
- Mọi file đều nhận dữ liệu vào và trả dữ liệu ra, không tự đọc config toàn cục.

Lý do quan trọng: sau khi test thật sẽ có nhiều lần đổi nghiệp vụ. Nếu logic nằm rải trong file lớn thì mỗi lần đổi phải sửa nhiều nơi và dễ sinh lỗi mới.

### 9.2 Cấu trúc thư mục

Code V2 nằm trong package mới, đặt cạnh code V1 để chuyển dần từng phần:

```text
src/v2/
  policy/
    loader.py          đọc và kiểm tra file policy
    snapshot.py        chụp lại policy của một lần chạy
  input/
    normalizer.py      chuẩn hóa tên, tax code, người đại diện
    province.py        lấy tỉnh/thành và xử lý alias
    blacklist.py       chuẩn hóa số blacklist và label
  identity/
    taxcode.py         kiểm tra chữ số cuối, trả match/mismatch/unknown
    enricher.py        gọi Gemini Quick Search bổ sung field thiếu
    status_gate.py     đọc tình trạng hoạt động của công ty
  query/
    template.py        thay placeholder
    validator.py       báo lỗi placeholder trước khi mở batch
    planner.py         quyết định query nào cần chạy
  search/
    adapter.py         gọi Firecrawl Search
    cache.py           tra fingerprint, trả hit hoặc miss
  scoring/
    scorer.py          cộng điểm URL
    evidence.py        tìm bằng chứng chưa dùng trong query
    domain_dedupe.py   giữ một URL điểm cao nhất mỗi domain
    classifier.py      chia accepted/deferred/rejected
  scrape/
    planner.py         chọn URL nào cần mở theo tier
    preflight.py       GET rẻ và tìm blacklist
    adapter.py         gọi Firecrawl Scrape
  extract/
    slicer.py          cắt đoạn quanh anchor
    extractor.py       gọi AI lấy contact
    verifier.py        kiểm tra contact có trong đoạn bằng chứng
    blacklist_match.py so số với blacklist và gắn label
    aggregator.py      tổng hợp kết quả công ty
  work/
    unit.py            định nghĩa một work unit
    store.py           tạo, nhận và cập nhật work unit
    log.py             ghi lịch sử để giải thích kết quả
  runtime/
    retry.py           một bộ quy tắc retry chung
    resources.py       credit, rate limit, budget
    worker.py          [ĐỢT SAU] vòng chạy của một worker
    supervisor.py      [ĐỢT SAU] pause, resume, drain, shutdown
  service/
    application.py     lớp chung cho dashboard, dòng lệnh và API
```

Tổng khoảng 30 file nhỏ thay vì vài file lớn.

### 9.3 Bảng module

| Khối | File | Nhận vào | Trả ra | Nhiệm vụ thực tế |
|---|---|---|---|---|
| Input Normalizer | `input/normalizer.py` | File người dùng | Company Input Profile | Chuẩn hóa dữ liệu nhưng không gọi API. |
| Province Resolver | `input/province.py` | Địa chỉ đầy đủ | Tỉnh/thành | Lấy tỉnh/thành, xử lý alias, không đoán theo tên đường. |
| Blacklist Loader | `input/blacklist.py` | Số và label người dùng nhập | Blacklist chuẩn hóa | Chuẩn hóa số, giữ nguyên label. |
| Policy Registry | `policy/loader.py` | File policy | Policy đã kiểm tra | Kiểm tra domain, tier, query, điểm và giới hạn. |
| Policy Snapshot | `policy/snapshot.py` | Policy + input | Bản chụp có version | Giải thích kết quả cũ theo quy tắc nào. |
| **Identity Enricher** | `identity/enricher.py` | Company Profile | Profile đã bổ sung | Gọi Gemini Quick Search điền tax code, tên tiếng Việt, địa chỉ. |
| **Tax Code Validator** | `identity/taxcode.py` | Chuỗi số + ngữ cảnh | match / mismatch / unknown | Kiểm tra chữ số cuối và nhãn đứng trước. Không gọi API. |
| **Business Status Gate** | `identity/status_gate.py` | Trang nguồn pháp lý | Tình trạng hoạt động | Kết thúc sớm công ty đã giải thể. |
| Query Template | `query/template.py` | Công thức + profile | Query text | Thay placeholder và ghi field đã dùng. |
| Query Validator | `query/validator.py` | Công thức | Danh sách lỗi | Báo placeholder sai trước khi mở batch. |
| Query Planner | `query/planner.py` | Profile + policy | Query Work Unit | Quyết định query nào cần chạy và theo thứ tự nào. |
| Search Adapter | `search/adapter.py` | Query Work Unit | Search Result | Gọi Firecrawl Search. Không ghi database. |
| Search Cache | `search/cache.py` | Fingerprint | Cache hit hoặc miss | Trả kết quả cũ, **không lưu thêm dòng nào**. |
| Candidate Scorer | `scoring/scorer.py` | URL + profile + policy | Điểm + bảng điểm | Cộng điểm và lưu lý do. |
| Evidence Finder | `scoring/evidence.py` | URL + field đã dùng | Bằng chứng độc lập | Không tính lại field đã dùng trong query. |
| **Domain Deduper** | `scoring/domain_dedupe.py` | Danh sách URL đã chấm | Một URL mỗi domain | Giữ URL điểm cao nhất, ghi lý do `duplicate_domain`. |
| Candidate Classifier | `scoring/classifier.py` | Điểm + bằng chứng | accepted/deferred/rejected | Chia nhóm URL. |
| Review Queue | `service/application.py` | URL deferred | Quyết định user | Giữ hàng chờ review mà không khóa toàn app. |
| Cheap Preflight | `scrape/preflight.py` | URL + blacklist | pass/skip/unknown | GET HTML và tìm blacklist trước scrape. |
| Scrape Planner | `scrape/planner.py` | URL + tier policy | Scrape Work Unit | Chọn URL nào cần mở. |
| Scrape Adapter | `scrape/adapter.py` | Scrape Work Unit | Nội dung trang | Gọi Firecrawl. Không ghi database. |
| Context Slicer | `extract/slicer.py` | Markdown + anchor | Context Slice | Bỏ phần thừa, giữ đoạn liên quan. |
| Contact Extractor | `extract/extractor.py` | Context Slice | Contact Observation | Lấy contact, ngày và đoạn bằng chứng. |
| Contact Verifier | `extract/verifier.py` | Contact + đoạn văn | pass/fail | Chỉ nhận contact có mặt trong đoạn bằng chứng. |
| Blacklist Matcher | `extract/blacklist_match.py` | Contact + blacklist | Contact Decision | Gắn label người dùng và loại số trùng. |
| Contact Aggregator | `extract/aggregator.py` | Các Contact Decision | Kết quả công ty | Tổng hợp và kiểm tra điều kiện dừng tier. |
| Work Store | `work/store.py` | Work Unit | Trạng thái + quyền giữ việc | Tạo, nhận, cập nhật, thu hồi việc quá hạn. |
| Work Log | `work/log.py` | Mọi thay đổi | Lịch sử | Ghi lại để giải thích kết quả. Không dùng làm nguồn tính trạng thái. |
| Retry Executor | `runtime/retry.py` | Một lần gọi API | Các lần thử | Thử lại lỗi tạm thời theo một quy tắc chung. |
| Resource Controller | `runtime/resources.py` | Credit, rate, budget | Trạng thái tài nguyên | Ngăn mở việc mới khi không đủ tài nguyên. |
| Worker — **đợt sau** | `runtime/worker.py` | Work Unit | Attempt | Chạy việc, heartbeat, dừng ở điểm an toàn. Đợt đầu dùng worker của V1. |
| Runtime Supervisor — **đợt sau** | `runtime/supervisor.py` | Lệnh điều khiển | Trạng thái process thật | Pause, resume, drain, shutdown worker. Đợt đầu dùng cơ chế của V1. |
| Application Service | `service/application.py` | Yêu cầu người dùng | Lệnh hoặc báo cáo | Dashboard, dòng lệnh và API cùng gọi lớp này. |

Bốn khối in đậm là khối V1 đang có nhưng bản kế hoạch trước đã bỏ sót.

### 9.3b Phần chạy song song để lại đợt sau

Đợt đầu **không** xây worker pool và runtime supervisor mới.

Lý do: cơ chế chạy nhiều worker của V1 đang hoạt động được. Nó đã có nhận việc an toàn, heartbeat, thu hồi việc của worker chết và dừng ở điểm an toàn.

Đợt đầu dùng nguyên cơ chế đó:

| Phần | Đợt đầu | Đợt sau |
|---|---|---|
| Hàng đợi công việc | Dùng `pipeline_jobs` của V1 | Đổi sang work unit nhỏ |
| Nhận việc, heartbeat | Dùng nguyên của V1 | Giữ nguyên, chỉ đổi mức chi tiết |
| Pause, resume, drain, shutdown | Dùng nguyên của V1 | Tách thành `runtime/supervisor.py` |
| Số worker chạy cùng lúc | Giữ như hiện tại | Điều chỉnh theo policy |

Các module nghiệp vụ mới trong `src/v2/` được viết sao cho **không phụ thuộc vào cách chạy song song**. Mỗi module nhận dữ liệu vào và trả dữ liệu ra. Nhờ vậy, khi đổi sang worker mới ở đợt sau thì các module nghiệp vụ không phải sửa.

Chỉ chuyển sang worker mới khi có lý do rõ ràng, ví dụ tốc độ không đủ hoặc thật sự cần chạy nhiều việc nhỏ song song trong cùng một công ty.

### 9.4 Trạng thái được lưu trên dòng, không tính lại từ lịch sử

Kế hoạch cũ đề xuất tính trạng thái công ty bằng cách đọc lại toàn bộ `Work Ledger`.

Cách đó chậm và rất khó tìm lỗi.

V2 dùng cách đơn giản hơn:

- Trạng thái hiện tại được lưu ngay trên dòng work unit.
- `Work Log` chỉ để tra lịch sử và giải thích, không phải nguồn tính trạng thái.

Cách nhận việc dùng đúng cơ chế V1 đang chạy: một câu lệnh cập nhật có điều kiện trong một transaction ngắn.

```text
UPDATE work_units SET owner = :worker, claimed_at = now
WHERE id = :id AND status = 'pending'
```

Nếu hai worker cùng chạy câu này thì chỉ một worker cập nhật được. Worker còn lại nhận việc khác.


## 10. Search Cache và chống dữ liệu trùng

### 10.1 Nguyên nhân thật của 89.070 dòng trùng

Trong V1, sau khi lấy kết quả từ cache, luồng bên ngoài vẫn gọi hàm lưu thêm một lần nữa. Database lại không có hàng rào chặn dòng trùng, nên lỗi này tích lũy dần.

Toàn bộ 89.070 dòng dư đều là trùng **trong cùng một công ty**, không phải trùng giữa các công ty.

### 10.2 Hai thay đổi để sửa

**Thay đổi 1 — sửa bug cache hit.**

```text
Cache hit → trả kết quả cũ → ghi một event cache_reused để báo chi phí bằng 0
         → KHÔNG gọi hàm lưu search result nữa
```

**Thay đổi 2 — thêm hàng rào ở database.**

`Unique key` là quy tắc database không cho phép hai dòng có cùng danh tính được lưu lặp.

```text
UNIQUE (company_id, search_query, url) trên bảng search_results
```

Sau thay đổi này, dòng trùng bị database từ chối. Lỗi không thể quay lại dù code sau này viết sai.

**Việc kèm theo:** chạy một script dọn 89.070 dòng trùng đang có, trước khi thêm unique key. Nếu chưa dọn thì không thêm được.

### 10.3 Idempotency key cho work unit

`Idempotency key` là mã của một work unit, giúp gọi lại cùng một việc vẫn chỉ tạo một kết quả.

Ví dụ hai worker cùng gặp cache miss trên cùng một query:

```text
Worker 1 và Worker 2 cùng muốn lưu kết quả của query Q cho công ty A
Unique key cho phép một worker lưu thành công
Worker còn lại đọc lại kết quả đã có thay vì tạo bản sao
```

### 10.4 Tại sao không dùng thiết kế “một bộ kết quả dùng chung”

Kế hoạch cũ đề xuất lưu mỗi bộ search result một lần, các công ty chỉ trỏ tới bộ đó.

Đề xuất này bị bỏ sau khi đo trên database thật:

| Nội dung | Tỷ lệ |
|---|---:|
| Trùng trong cùng một công ty — bug thật | 8,5% |
| Query được nhiều công ty dùng chung — mức tối đa thiết kế dùng chung có thể tiết kiệm | 2,1% |

Chỉ 164 trong 21.041 query được nhiều hơn một công ty sử dụng, vì query có chứa tên công ty.

Thiết kế dùng chung còn tạo thêm hai rủi ro:

1. Mỗi công ty có quyết định riêng trên cùng một URL. Ví dụ công ty A loại URL số 3, công ty B scrape URL số 3 và tìm được số điện thoại. Các quyết định này không có chỗ lưu trong bộ dùng chung, nên vẫn phải thêm một bảng riêng — và bảng đó lại có đúng một dòng cho mỗi công ty và mỗi URL, giống hệt bảng đang có.
2. Database hiện chưa bật cơ chế chặn xóa dữ liệu đang được nơi khác tham chiếu. Nếu xóa bộ kết quả gốc, dữ liệu của nhiều công ty mất tham chiếu.

Hai thay đổi ở mục 10.2 giải quyết đúng 8,5% và không tạo rủi ro mới.

## 11. Retry và xử lý lỗi API

V2 dùng tên `max_attempts` để tránh hiểu nhầm giữa số lần gọi tổng cộng và số lần gọi lại.

Cấu hình khuyến nghị:

```yaml
retry:
  max_attempts: 3
  base_delay_seconds: 2
  max_delay_seconds: 60
  honor_retry_after: true
  jitter: true
```

`max_attempts: 3` nghĩa là gọi tối đa ba lần: lần đầu và tối đa hai lần thử lại.

Nếu nghiệp vụ muốn “lần đầu cộng thêm ba retry”, policy đặt `max_attempts: 4`.

### Lỗi được thử lại

- Timeout hoặc HTTP 408.
- Mất kết nối tạm thời.
- HTTP 429 theo thời gian `Retry-After` do provider trả về.
- HTTP 500, 502, 503 hoặc 504 nếu lỗi có khả năng tạm thời.

### Lỗi không thử lại

- HTTP 400 do request sai.
- HTTP 401 do API key sai.
- HTTP 402 do hết credit.
- Thiếu field bắt buộc trong input.
- Cấu hình placeholder sai.

`Backoff` là thời gian chờ tăng dần sau mỗi lần lỗi.

Ví dụ:

```text
Lần 1 lỗi → chờ khoảng 2 giây
Lần 2 lỗi → chờ khoảng 4 giây
Lần 3 vẫn lỗi → dừng work unit theo policy
```

`Jitter` là một khoảng chờ ngẫu nhiên nhỏ. Nó tránh việc 20 worker cùng gọi lại API đúng một thời điểm.

Mỗi attempt được ghi vào Work Log. Retry chỉ chạy lại API operation bị lỗi, không chạy lại toàn bộ công ty.

Lệnh shutdown có thể ngắt thời gian backoff. Worker không phải chờ đủ 60 giây mới tắt.

## 12. Scrape nhanh hơn nhưng vẫn có kiểm soát

Mục này nói về bốn cái núm điều chỉnh khi gọi Firecrawl Scrape.

```yaml
firecrawl:
  wait_for_ms: 0
  only_main_content: true
  max_age_ms: policy_controlled
  max_concurrency: policy_controlled
```

### 12.1 `wait_for_ms` — chờ thêm bao lâu trước khi đọc trang

Firecrawl đã tự chờ trang tải xong. `wait_for_ms` là thời gian chờ **cộng thêm** sau đó.

V1 đặt 3.000 ms cho mọi trang. Nghĩa là mọi trang đều bị cộng thêm 3 giây dù trang đã sẵn sàng.

```text
20 URL × 3 giây = 60 giây chờ vô ích cho mỗi công ty
1.000 công ty  → khoảng 16 giờ chờ vô ích
```

V2 đặt `wait_for_ms: 0`. Chỉ những domain có trang tải chậm bằng JavaScript mới được cấu hình riêng.

### 12.2 `only_main_content` — chỉ lấy phần nội dung chính

Bật lên thì Firecrawl bỏ menu, header và footer, chỉ trả phần thân trang.

```text
Tắt: 25.000 ký tự — gồm cả menu, quảng cáo, số hotline của tòa soạn ở footer
Bật:  8.000 ký tự — chỉ phần nội dung
```

Hai lợi ích: ít token AI hơn, và bớt nguy cơ AI lấy số điện thoại ở footer của website chủ.

Đây là lớp bảo vệ thứ nhất. Context Slicing ở mục 7.6 là lớp thứ hai.

### 12.3 `max_age_ms` — cho phép dùng lại bản trang Firecrawl đã lưu

Firecrawl giữ sẵn bản trang đã tải trước đó. `max_age_ms` nói rằng bản cũ đến mức nào thì vẫn dùng được.

Dùng bản cũ thì rẻ hơn và nhanh hơn tải lại.

```text
max_age_ms: 604800000  (7 ngày)
→ nếu Firecrawl đã có bản trang trong 7 ngày qua thì trả bản đó

max_age_ms: 0
→ luôn tải lại từ website
```

Cách đặt theo loại nguồn:

| Loại nguồn | Đặt bao nhiêu | Lý do |
|---|---|---|
| Trang danh bạ doanh nghiệp | 7 đến 30 ngày | Số điện thoại rất ít đổi |
| Trang tuyển dụng | 1 đến 3 ngày | Tin tuyển dụng thay đổi nhanh |
| Trang nguồn pháp lý dùng cho status gate | 0 | Cần tình trạng hoạt động mới nhất |

### 12.4 `max_concurrency` — mở bao nhiêu URL cùng lúc

Mở nhiều URL cùng lúc thì nhanh hơn, nhưng Firecrawl sẽ chặn nếu gọi quá nhanh.

`HTTP 429` là câu trả lời “bạn gọi quá nhiều, hãy chờ” — xem thêm mục 17.3.

App không tăng số việc song song vô hạn. Nó tự giảm khi bị chặn và tăng lại từ từ khi ổn định.

Ví dụ diễn biến thật:

```text
Đang mở 8 URL cùng lúc
→ Firecrawl trả 429 kèm "chờ 30 giây"
→ app chờ đúng 30 giây
→ app giảm xuống 4 URL cùng lúc
→ 20 request liên tiếp thành công
→ app tăng lên 5, rồi 6 URL cùng lúc
→ nếu lại bị 429 thì giảm tiếp
```

Cách này giữ tốc độ cao nhất mà nhà cung cấp còn cho phép, thay vì để người dùng tự đoán một con số cố định.

### 12.5 Cheap GET có giới hạn riêng

Cheap GET Preflight ở mục 7.4 đi trực tiếp từ máy của người dùng, không qua Firecrawl.

Nghĩa là website nhìn thấy địa chỉ IP của người dùng. Nếu gọi quá nhanh, website có thể chặn IP đó.

Vì vậy Cheap GET có giới hạn riêng theo từng domain, đặt thấp hơn nhiều so với `max_concurrency` của Firecrawl.

```yaml
cheap_get:
  max_concurrent_per_domain: 1
  min_delay_between_requests_ms: 1000
```

## 13. Màn hình Deferred Review

Màn hình Deferred dành cho URL có khả năng đúng nhưng chưa đủ bằng chứng để app tự bỏ tiền scrape.

Mỗi URL hiển thị:

- Tên công ty và tỉnh/thành.
- URL, domain và tier.
- Title và description từ search.
- Query đã tạo ra URL.
- Field nào đã dùng trong query.
- Evidence nào tìm thấy.
- Điểm tổng và chi tiết điểm.
- Lý do bị deferred.
- Kết quả GET hoặc metadata nếu đã kiểm tra.
- Chi phí scrape dự kiến.

Người dùng có thể chọn từng URL hoặc nhiều URL rồi đánh dấu:

- Scrape.
- Skip.
- Keep deferred.

Nếu người dùng chưa review ngay, chỉ company hoặc tier đang chờ bị giữ ở checkpoint đó.

Các công ty khác tiếp tục chạy. Toàn bộ pipeline không bị dừng.

## 14. Stop, pause và resume toàn hệ thống

V2 có bốn lệnh riêng:

| Lệnh | Hành vi thực tế |
|---|---|
| Pause scheduling | Không phát thêm việc mới; việc đang chạy được phép đến điểm an toàn. |
| Resume | Worker tiếp tục nhận work unit pending. |
| Drain and shutdown | Ngừng nhận việc mới, chờ việc hiện tại lưu xong rồi tắt worker. |
| Emergency shutdown | Yêu cầu dừng ngay; hết thời gian an toàn thì terminate process. |

`Drain` là ngừng nhận việc mới nhưng chờ việc đang làm lưu xong trước khi tắt.

`Emergency shutdown` chỉ dùng khi cần tắt nhanh. Work unit chưa commit kết quả sẽ trở lại pending sau khi hết quyền giữ việc.

`Commit` ở đây nghĩa là kết quả đã được database xác nhận lưu thành công.

Mỗi worker có:

- `Lease`: quyền giữ một work unit trong thời gian giới hạn.
- `Heartbeat`: tín hiệu định kỳ cho biết worker còn sống.

Nếu worker chết, heartbeat ngừng. Khi lease hết hạn, work unit quay lại hàng chờ để worker khác tiếp tục.

Dashboard không tự kết luận “đã stop” chỉ vì một status trong database đổi.

`Runtime Supervisor` kiểm tra process thật, PID, heartbeat và work lease.

`PID` là mã của process đang chạy trên hệ điều hành.

### Điều kiện xác nhận hệ thống đã dừng

- Không còn worker process.
- Không còn heartbeat mới.
- Không có API call mới sau thời gian cho phép.
- Work unit đang dở không bị đánh dấu completed.
- Khi resume, chỉ work unit pending hoặc lease đã hết hạn được nhận lại.

## 15. Thẻ trạng thái của một công ty

V2 không dùng một status duy nhất để mô tả mọi vấn đề.

Thẻ trạng thái được đọc từ trạng thái đang lưu trên các work unit của công ty, không phải tính lại từ lịch sử:

| Nhóm | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Thực thi | running, paused, blocked, completed | Hệ thống có còn chạy được không? |
| Độ bao phủ | not_started, partial, complete | Các work unit trong plan đã xử lý đến đâu? |
| Contact | none, found, verified | Đã tìm thấy contact và bằng chứng chưa? |
| Tài nguyên | available, credit_exhausted, rate_limited | Có thể tiếp tục gọi API không? |
| Lý do dừng | user_stop, budget, api_error, dependency_missing | Vì sao chưa đi tiếp? |
| Độ mới | current, stale | Kết quả còn khớp input và policy hiện tại không? |

Ví dụ:

```text
paused
coverage: partial
contacts: found
resources: credit_exhausted
stop_reason: budget
```

Dashboard diễn giải:

```text
Đã tìm thấy contact.
Còn 7/20 URL chưa xử lý.
Cần bổ sung credit để tiếp tục.
```

Khi có credit, planner chỉ mở lại 7 URL còn lại.

`Completed` chỉ có nghĩa mọi work unit trong plan đã chọn đã ở trạng thái kết thúc.

Completed không đồng nghĩa “đã tìm thấy contact”.

Work unit bị dừng vì đã tìm đủ số hợp lệ có thể kết thúc bằng `cancelled_by_policy`. Đây vẫn là trạng thái kết thúc hợp lệ.

## 16. Lộ trình sửa dần trên codebase đã copy

`Application service` là lớp xử lý chung nằm giữa các giao diện và module nghiệp vụ. Nhờ đó, dashboard và dòng lệnh không tự viết hai cách stop/resume khác nhau.

### 16.1 Nguyên tắc lộ trình

- Sau **mỗi** giai đoạn, app phải chạy được hết một công ty từ đầu đến cuối. Không có giai đoạn nào để lại hệ thống hỏng.
- Code mới nằm trong `src/v2/`. Code V1 cũ chỉ được xóa sau khi phần mới đã có test và đã chạy thật.
- Mỗi giai đoạn dùng `replay mode` của V1 để chạy lại trên dữ liệu đã lưu, không tốn tiền API.
- Kiểm tra bằng cùng một bộ 30 công ty mẫu ở mọi giai đoạn.

`Replay mode` là chế độ chạy lại toàn bộ luồng trên dữ liệu đã lưu mà không gọi API tốn tiền. V1 đã có sẵn chế độ này và V2 dùng nó làm công cụ test chính.

### 16.2 Các giai đoạn

| Giai đoạn | Việc thực hiện | Kết quả cần kiểm tra |
|---|---|---|
| 0. Chọn bộ mẫu | Chọn 30 công ty gồm: trùng tên khác tỉnh, trang tin, timeout, cache hit, blacklist, công ty đã giải thể, công ty thiếu tỉnh/thành. Chạy V1 và lưu kết quả. | Có bộ kết quả V1 để so sánh về sau. |
| 1. Sửa ba lỗi rẻ nhất | Bỏ `waitFor: 3000`, đặt `DELAY_SECONDS` về 0, sửa bug cache hit, dọn dòng trùng, thêm unique key, tạo retry executor tối thiểu với `max_attempts` và phân loại lỗi 5xx. | Trang tĩnh không còn chờ cố định. Cache hit không sinh dòng mới. Chuỗi 503,503,200 thành công ở lần thứ ba. |
| 2. Tách module không gọi API | `input/`, `policy/`, `identity/taxcode.py`. Chưa đổi luồng chạy. | Test chạy được từng file riêng. Tax code trả đúng match/mismatch/unknown. |
| 3. Query có tỉnh/thành | `query/`, đo tỷ lệ lấy được tỉnh/thành trên 8.701 công ty, thêm bản xem trước trước khi mở batch. | Query theo tên luôn có tỉnh/thành. Placeholder sai báo trước khi gọi API. |
| 4. Chấm URL và dedup domain | `scoring/`. Giữ nguyên bảng điểm V1, thêm dedup domain và veto tax code. | Cùng input cho cùng quyết định. Một domain chỉ mở một URL. |
| 5. Cắt ngữ cảnh trước khi gọi AI | `extract/slicer.py`, `extract/verifier.py`. | Không lấy contact ở footer của trang tin. Contact phải có trong đoạn bằng chứng. |
| 6. Retry và tài nguyên chung | Mở rộng `runtime/retry.py` từ Stage 1, thêm `runtime/resources.py`, cost/rate budget và dọn retry code cũ còn sót. | 402 không retry. 429 tôn trọng `Retry-After`. Shutdown ngắt được backoff. |
| 7. Chia work unit | `work/`. Đổi từ một job mỗi công ty sang nhiều work unit nhỏ. **Dùng nguyên cơ chế nhận việc và heartbeat của V1.** | Kill giữa lúc chạy rồi bật lại: chỉ việc còn dở được chạy lại. |
| 8. Worker và điều khiển — **đợt sau** | `runtime/worker.py`, `runtime/supervisor.py`. Chỉ làm khi tốc độ thật sự không đủ. Xem mục 9.3b. | Nhiều worker không lấy trùng việc. Stop tắt process thật. |
| 9. Policy ra file cấu hình | Chuyển domain, tier, điểm, công thức query từ code sang file policy có version. | Thêm domain mới không cần sửa code. |
| 10. Màn hình Deferred | API và giao diện review. | Review không chặn các công ty khác. |
| 11. Gộp giao diện | Dòng lệnh, API và dashboard cùng gọi `service/application.py`. | Ba giao diện cho cùng kết quả và cùng lệnh điều khiển. |
| 12. Chạy song song V1–V2 | Cùng bộ input, hai database tách biệt. | Có báo cáo chi phí, độ chính xác và thời gian. |
| 13. Chuyển vận hành | Chọn V2 làm hệ thống chính, giữ V1 chỉ đọc. | Có hướng dẫn quay lại V1 và chạy tiếp từ checkpoint. |

### 16.3 Giai đoạn 1 tách riêng vì có giá trị ngay

Giai đoạn 1 chỉ sửa vài chỗ nhưng giải quyết phần lớn vấn đề chi phí và dữ liệu trùng của V1.

Nên hoàn thành và chạy thật giai đoạn 1 trước, rồi mới làm các giai đoạn sau.

Nếu vì lý do nào đó phải dừng dự án, giai đoạn 1 vẫn để lại một hệ thống tốt hơn V1 hiện tại.

Kế hoạch triển khai chi tiết, thứ tự commit, migration, rollback và test gate của ba mục này nằm tại `docs/v2-stage1-critical-fixes-implementation-plan.md`.


## 17. Bộ test bắt buộc trước khi đưa V2 vào vận hành

### 17.1 Query và nhận diện công ty

1. Hai công ty cùng tên ở hai tỉnh phải tạo query khác nhau.
2. Query theo tên thiếu tỉnh/thành phải bị **chặn trước khi gọi API**.
3. Query tax code vẫn chạy được khi không có tỉnh/thành.
4. Placeholder sai phải được **báo trước khi query đầu tiên được chạy**.
5. Field đã dùng trong query chỉ được cộng điểm giảm và không tự làm URL thành `accepted`.
6. App không dùng phường, tên đường hoặc khu công nghiệp làm điều kiện bắt buộc.
7. Field do Quick Search bổ sung không được dùng để loại URL.
8. Quick Search trả về nhiều công ty cùng tên thì công ty phải vào hàng chờ review.

#### Giải thích “chặn trước khi gọi API” (mục 2)

Mỗi lần gọi Firecrawl Search là một lần **mất tiền**, dù kết quả có dùng được hay không.

Có hai cách xử lý một query xấu:

```text
Cách sai:  tạo query → gọi API → trả tiền → nhận 100 URL rác → lọc bỏ hết
           → đã mất tiền, không thu được gì

Cách đúng: tạo query → kiểm tra thấy thiếu tỉnh/thành → KHÔNG gọi API
           → ghi lý do skipped: missing required field province
           → không mất tiền
```

“Chặn trước khi gọi API” nghĩa là app phải phát hiện query xấu ở trong máy, trước khi gửi ra ngoài.

Một query tên công ty thiếu tỉnh/thành là query xấu vì nó có thể trả về hàng loạt công ty trùng tên ở các tỉnh khác.

Trường hợp input chỉ có tên công ty được xử lý theo bảng ở mục 3.8.

#### Giải thích “báo trước khi mở batch” (mục 4)

Đúng, nghĩa là báo **trước khi query đầu tiên được chạy**.

Ví dụ người dùng viết sai `{{provine}}` thay vì `{{province}}` và mở batch 1.000 công ty:

```text
Không kiểm tra trước: app chạy 1.000 query sai → mất tiền 1.000 lần
Có kiểm tra trước:    app dừng ngay và báo
                      "Lỗi cấu hình: placeholder {{provine}} không tồn tại"
                      → mất 0 đồng
```

Bản xem trước ở mục 5.5 chạy cùng lúc với việc kiểm tra này.

### 17.1b Tax code

1. Tax code thật `0100112437` phải qua được phép kiểm tra chữ số cuối.
2. Số điện thoại `0912345678` không được nhận là tax code khi không có nhãn `MST` đứng trước.
3. Chuỗi số không xác định được phải trả `unknown`, và `unknown` không được loại URL.
4. Tax code trong đường dẫn masothue khác tax code mục tiêu phải loại URL ngay.
5. Tax code trùng mục tiêu chỉ được cộng điểm khi tax code chưa dùng làm field chính của query đó.
6. Tax code dạng 13 chữ số `...-001` phải được nhận đúng.
7. Trang được tìm bằng query chứa tax code không được dùng để promotion chính tax code đó.
8. Hai domain cùng `source_family` chỉ được tính là một nguồn hỗ trợ promotion.
9. Hai trang có đoạn bằng chứng gần như giống nhau chỉ được tính là một nguồn.
10. Tên giống từ 90% nhưng có từ phân biệt như “PHÁT” hoặc “GROUP” không tự đủ để promotion.
11. Hai tax code cùng vượt điều kiện promotion phải tạo `identity_ambiguous`, không tự chọn.
12. Nếu tax-code veto là nguyên nhân duy nhất loại toàn bộ URL vốn đủ bằng chứng, các URL phải thành `held_for_review` và công ty có reason `tax_code_veto_rejects_all`.
13. Không có URL đủ bằng chứng trước veto thì phanh `tax_code_veto_rejects_all` không được kích hoạt.

### 17.1c Bổ sung dữ liệu và tình trạng hoạt động

1. Công ty không có tỉnh/thành và không có tax code phải được Quick Search bổ sung trước khi tạo query.
2. Quick Search lỗi thì công ty vẫn đi tiếp bằng dữ liệu input gốc.
3. Contact từ Quick Search phải được lưu ở cấp công ty, không phải cấp URL.
4. URL mà Quick Search đã dẫn nguồn không được search và scrape lại.
5. Công ty đã giải thể phải kết thúc với 0 URL được scrape.
6. Công ty “không hoạt động tại địa chỉ đã đăng ký” vẫn phải chạy bình thường.
7. Không đọc được tình trạng hoạt động thì không được chặn công ty.

### 17.1d Dedup domain

1. Mười URL cùng một domain chỉ được mở một URL điểm cao nhất.
2. Chín URL bị loại vẫn được lưu kèm lý do `duplicate_domain`.
3. Export vẫn truy ngược được các URL bị loại vì trùng domain.

### 17.2 Trang tin và Context Slicing

1. Contact của tòa soạn ở footer không được lưu thành contact công ty.
2. Tax code nằm sau ký tự thứ 15.000 vẫn được tìm thấy.
3. Contact phải xuất hiện trong đoạn bằng chứng đã lưu.
4. Trang có ngày đăng thì output giữ đúng ngày đó.
5. Trang không có ngày đăng thì không tự điền ngày scrape.

### 17.3 Retry

#### Trước hết: “HTTP status code” là gì

Mỗi lần app gọi một dịch vụ bên ngoài, dịch vụ đó trả lại một con số cho biết chuyện gì đã xảy ra.

Chỉ cần nhớ chữ số đầu tiên:

| Bắt đầu bằng | Nghĩa | Ai sai | Thử lại có ích không |
|---|---|---|---|
| **2xx** | Thành công | — | Không cần |
| **4xx** | Yêu cầu của app có vấn đề | Phía app | **Không** — thử lại vẫn sai như vậy |
| **5xx** | Máy chủ của dịch vụ có vấn đề | Phía dịch vụ | **Có** — lát sau có thể hết lỗi |

Nguyên tắc chung: **4xx là lỗi của mình, thử lại vô ích. 5xx là lỗi của họ, thử lại có thể được.**

Các mã cụ thể app gặp:

| Mã | Nghĩa dân dụng | App làm gì |
|---|---|---|
| `200` | Xong, đây là dữ liệu | Đi tiếp |
| `400` | “Yêu cầu của bạn viết sai” | Không thử lại. Sửa code hoặc cấu hình |
| `401` | “API key sai hoặc hết hiệu lực” | Không thử lại. Báo người dùng kiểm tra key |
| `402` | **“Bạn hết tiền/hết credit”** | Không thử lại. Dừng cả batch, ghi `credit_exhausted` |
| `408` | “Chờ bạn quá lâu, tôi bỏ” | Thử lại |
| `429` | **“Bạn gọi quá nhanh, hãy chờ”** | Chờ đúng thời gian họ nói rồi thử lại, đồng thời giảm số việc chạy cùng lúc |
| `500` | “Máy chủ tôi bị lỗi” | Thử lại |
| `502` `503` `504` | “Máy chủ tôi đang quá tải hoặc không phản hồi” | Thử lại |
| `timeout` | Không nhận được câu trả lời nào | Thử lại |

Hai mã quan trọng nhất cần phân biệt:

- `402` = **hết tiền**. Thử lại 100 lần cũng không tự có thêm tiền. Phải dừng và nạp thêm.
- `429` = **gọi quá nhanh**. Chờ rồi gọi lại là được. Đây không phải lỗi thật.

`Retry-After` là con số dịch vụ gửi kèm mã 429 để nói “hãy chờ bao nhiêu giây”. App phải chờ đúng con số đó, không tự đoán.

#### Các test bắt buộc

1. Chuỗi `503, 503, 200` tạo đúng ba attempt và thành công ở lần thứ ba.
2. Chuỗi `timeout, timeout, 200` tạo đúng ba attempt và thành công ở lần thứ ba.
3. `402` không thử lại lần nào và chuyển tài nguyên sang `credit_exhausted`.
4. `401` không thử lại lần nào và báo lỗi API key.
5. `400` không thử lại lần nào.
6. `429` chờ đúng số giây trong `Retry-After`, không tự đoán.
7. Shutdown ngắt được thời gian chờ giữa các lần thử. Worker không phải chờ hết 60 giây mới tắt.
8. Retry không tạo thêm dòng dữ liệu trùng.

Test 1 và 2 là hai test quan trọng nhất, vì V1 hiện đang sai đúng chỗ này: V1 chỉ chạy hai lần rồi báo thất bại.

### 17.4 Cache và nhiều worker

1. Cùng query cache hit 100 lần vẫn không sinh thêm dòng nào trong `search_results`.
2. Cố tình lưu lại đúng `(company_id, search_query, url)` phải bị database từ chối.
3. Hai worker cùng lưu một kết quả chỉ có một bản được chấp nhận.
4. Worker chết giữa chừng thì work unit quay lại pending sau khi lease hết.
5. Resume không chạy lại work unit đã hoàn tất.

### 17.4b Một lần gọi AI chỉ được ứng với một URL

Đây là lỗi V1 đã từng gặp và phải khóa lại bằng test để không tái diễn.

**Lỗi cũ:** một hàm gom 2–3 trang ngắn vào **một** lần gọi Gemini để tiết kiệm tiền. Kết quả trả về bị ghi cho tất cả các trang trong nhóm đó. Nghĩa là số điện thoại của URL thứ nhất bị gán luôn cho URL thứ hai và thứ ba của cùng công ty.

Hậu quả: nhìn vào database thấy ba URL đều có contact, nhưng thực tế chỉ một URL có. Truy ngược nguồn bị sai và không phát hiện được bằng mắt.

**Tình trạng hiện tại:** lỗi đã được sửa. Vòng lặp hiện gọi từng trang một. Nhưng hàm gom nhóm cũ **vẫn còn trong code** ở `src/ai_extractor.py`, tên `_batch_short_pages`, và không còn nơi nào gọi nó.

Đây là bẫy thật: một AI agent được yêu cầu “giảm chi phí AI” rất dễ tìm thấy hàm này và nối lại, làm lỗi quay về mà không ai biết.

**Việc phải làm:**

1. Xóa hàm `_batch_short_pages` khỏi code V2.
2. Thêm test khóa quy tắc dưới đây.

**Các test bắt buộc:**

1. Một lần gọi AI chỉ được ứng với đúng một `scraped_page_id`.
2. Ba URL của cùng một công ty, chỉ URL thứ nhất có số điện thoại: sau khi extract, chỉ URL thứ nhất có contact. URL thứ hai và thứ ba phải trống.
3. Mọi số điện thoại đã lưu phải xuất hiện trong nội dung của đúng trang đã sinh ra nó.
4. Không có hàm nào gom nhiều trang vào một lần gọi AI.
5. Contact cấp công ty từ Quick Search không được lưu như contact cấp URL.

Quy tắc gốc: **contact phải luôn truy ngược được về đúng một URL đã sinh ra nó.**

Nếu sau này cần giảm chi phí AI, cách đúng là Context Slicing ở mục 7.6 — cắt nội dung ngắn hơn cho từng trang, chứ không gộp nhiều trang.

### 17.5 Tốc độ và điều khiển

1. Trang tĩnh không bị `sleep(3)` hoặc `waitFor: 3000`.
2. Chỉ domain có selector policy mới nhận wait action.
3. Khi gặp 429, concurrency giảm theo policy.
4. Drain and shutdown không để lại worker process.
5. Emergency shutdown không tạo API call mới sau khoảng chờ an toàn đã quy định.


## 18. Chỉ số báo cáo để quyết định V2 có tốt hơn V1 hay không

V1 và V2 phải chạy trên cùng một bộ company mẫu.

`Shadow run` là chạy V2 song song để đo kết quả nhưng chưa dùng V2 làm hệ thống chính.

Các chỉ số cần báo cáo:

- Tỷ lệ URL đúng công ty mục tiêu.
- Tỷ lệ contact có đoạn bằng chứng đúng công ty.
- Số contact footer hoặc publisher bị loại.
- Số search call trên mỗi công ty.
- Số scrape credit trên mỗi công ty.
- Số token AI trên mỗi contact hợp lệ.
- Thời gian trung vị trên mỗi công ty.
- Thời gian của nhóm 5% công ty chạy chậm nhất.
- Số work unit bị chạy trùng.
- Số row trùng do cache.
- Tỷ lệ resume không chạy lại việc đã xong.
- Thời gian từ lệnh shutdown đến khi không còn worker.

Ví dụ báo cáo:

```text
100 công ty mẫu

V1:
- 760 scrape call
- 18 contact bị nghi lấy từ footer
- 14 search result row trùng trên tập mẫu
- thời gian trung vị: 92 giây/công ty

V2:
- 510 scrape call
- 2 contact cần review vì nghi từ footer
- 0 search result row trùng
- thời gian trung vị: 61 giây/công ty
```

Các số trên chỉ là mẫu trình bày, không phải cam kết kết quả trước khi shadow run.

V2 chỉ được thay V1 khi:

- Không kém V1 về khả năng tìm được contact cần thiết.
- Giảm rõ ràng URL sai công ty và contact sai nguồn.
- Giảm search, scrape hoặc token AI trung bình.
- Stop/resume và cache vượt qua toàn bộ test bắt buộc.

## 19. Các nội dung chưa làm trong đợt đầu

Đợt đầu chưa xây tính năng cho người dùng chọn giữa Gemini cũ và OpenRouter free model.

V2 chỉ tạo một cổng gọi AI chung để sau này có thể thêm lựa chọn provider mà không sửa toàn bộ pipeline.


Đợt đầu cũng không tự phân loại số điện thoại thành wrong, invalid hoặc same.

App chỉ đọc label do người dùng cung cấp, chuẩn hóa số và so sánh.

### Công cụ test dùng lại của V1

V1 có `replay mode` — chạy lại toàn bộ luồng trên dữ liệu đã lưu mà không gọi API tốn tiền.

V2 dùng chế độ này làm công cụ test chính cho toàn bộ bộ test ở mục 17 và cho bước chạy song song ở mục 18.

Nhờ vậy, phần lớn việc kiểm tra V2 không phát sinh chi phí API.

`Force refresh` của V1 cũng được giữ, dùng khi cần lấy lại dữ liệu mới cho một công ty cụ thể.

## 20. Bảng log trực tiếp để debug

Mục tiêu: khi một công ty ra kết quả sai, người dùng phải tìm được nguyên nhân **mà không cần đọc code**.

### 20.1 Vấn đề của log V1

V1 ghi log ra bảng `pipeline_logs` và ra file JSONL theo ngày. Log này ghi “việc gì đã chạy”, nhưng ghi thiếu “vì sao app quyết định như vậy”.

Khi một URL đúng bị loại, log hiện tại không cho biết nó bị loại ở bước nào và vì lý do gì.

### 20.2 Bảng log của V2

V2 thêm một bảng, mỗi dòng là **một quyết định**:

| Cột | Nội dung | Ví dụ |
|---|---|---|
| `time` | Thời điểm theo giờ Việt Nam | `2026-07-28 14:32:07` |
| `company_id` | Công ty nào | `4821` |
| `work_unit_id` | Việc nhỏ nào | `wu_4821_scrape_7` |
| `module` | File nào ra quyết định | `scoring/domain_dedupe.py` |
| `action` | Đang làm gì | `dedupe_domain` |
| `decision` | Kết quả | `rejected` |
| `reason` | **Vì sao** | `duplicate_domain: đã có yellowpages.vn điểm 62` |
| `target` | Đối tượng bị tác động | `https://yellowpages.vn/minh-an/branch` |
| `cost` | Chi phí bước này | `0` |
| `duration_ms` | Mất bao lâu | `4` |

Cột `reason` là cột quan trọng nhất. **Mọi quyết định `rejected`, `skipped`, `deferred` hoặc `cancelled` đều bắt buộc có `reason`.**

### 20.3 Cách dùng khi debug

Người dùng mở màn hình log, lọc theo một `company_id`, và đọc từ trên xuống.

Ví dụ công ty Minh An không ra contact:

```text
14:32:01  identity/enricher      quick_search    success    tax_code=3701234567 (unconfirmed)
14:32:03  query/planner          plan_query      created    "MINH AN" "Bình Dương" (contact)
14:32:05  search/cache           cache_lookup    hit        tiết kiệm 1 search credit
14:32:06  scoring/scorer         score_url       62         yellowpages.vn/minh-an
14:32:06  scoring/domain_dedupe  dedupe_domain   rejected   duplicate_domain: đã có điểm 62
14:32:07  identity/status_gate   status_check    inactive   "đã giải thể" → dừng công ty
```

Đọc xong biết ngay: công ty không ra contact vì đã giải thể, không phải vì app lỗi.

### 20.4 Ba việc bắt buộc

1. **Xem trực tiếp trong lúc đang chạy.** Dùng lại đường `/ws/logs` của V1 để đẩy dòng mới lên dashboard, không cần bấm tải lại.
2. **Lọc được theo `company_id` và `work_unit_id`.** Hai cột này phải có index, nếu không màn hình sẽ chậm khi bảng lớn.
3. **Tự dọn bảng.** Bảng này lớn rất nhanh. Log chi tiết chỉ giữ 30 ngày, sau đó xóa. Số liệu tổng hợp được cộng dồn sang bảng riêng trước khi xóa.

Không tự dọn thì sau vài tháng bảng log sẽ lớn hơn cả dữ liệu thật và làm chậm toàn hệ thống.

## 21. Ghi lại kiến trúc cho AI agent

Mục này phục vụ tình huống thật: phần lớn code sẽ do AI agent viết, và mỗi lần agent phải tự đọc lại cả codebase thì vừa chậm vừa tốn token vừa dễ hiểu sai.

### 21.1 Bốn file bắt buộc

| File | Dùng để làm gì | Ai đọc |
|---|---|---|
| `AGENTS.md` ở thư mục gốc | Quy tắc bắt buộc và bảng chỉ đường | AI agent đọc đầu tiên, tự động |
| `docs/architecture/INDEX.md` | Bảng “muốn sửa X thì đọc file nào” | AI agent, khi nhận việc |
| `docs/architecture/<module>.md` | Hợp đồng của một module | AI agent, khi sửa đúng module đó |
| `docs/implementation/STATUS.md` | Trạng thái triển khai, bằng chứng kiểm tra và bước tiếp theo | Mọi agent khi bắt đầu và trước khi kết thúc phiên |

`AGENTS.md` là tên file mà Codex và nhiều công cụ AI tự đọc trước khi làm việc. Đặt đúng tên này thì không cần nhắc agent mỗi lần.

`AGENTS.md` chỉ giữ quy tắc ổn định. Không ghi tiến độ thay đổi theo từng phiên vào file này. Tiến độ nằm trong `STATUS.md` để agent không hiểu nhầm một ghi chú tạm thời thành instruction lâu dài.

`AGENTS.md` phải có instruction cố định: **đọc và xác minh `docs/implementation/STATUS.md` trước khi bắt đầu; cập nhật file đó trước khi kết thúc hoặc bàn giao một phiên triển khai.**

Nếu bộ bootstrap chưa tồn tại hoặc thiếu một phần, `AGENTS.md` phải yêu cầu agent tự tạo theo protocol ở §21.6 **trước lần sửa code đầu tiên**. Nhiệm vụ chỉ đọc/đánh giá không tự ý tạo file; agent chỉ báo bootstrap đang thiếu.

### 21.2 Bảng chỉ đường

Đây là phần tiết kiệm token nhiều nhất. Thay vì để agent đọc cả `src/`, bảng này chỉ thẳng vào file cần sửa.

Ví dụ nội dung `docs/architecture/INDEX.md`:

```text
| Muốn sửa                          | Đọc file                        | Test liên quan              |
|-----------------------------------|---------------------------------|-----------------------------|
| Cách nhận biết tax code           | src/v2/identity/taxcode.py      | tests/test_taxcode.py       |
| Điểm của một domain               | policy/sources.yaml             | tests/test_scorer.py        |
| Công thức query                   | policy/queries.yaml             | tests/test_query.py         |
| Chỉ giữ 1 URL mỗi domain          | src/v2/scoring/domain_dedupe.py | tests/test_dedupe.py        |
| Cắt nội dung trước khi gọi AI     | src/v2/extract/slicer.py        | tests/test_slicer.py        |
| Quy tắc thử lại khi API lỗi       | src/v2/runtime/retry.py         | tests/test_retry.py         |
```

Quy tắc cho agent: **đọc `INDEX.md` trước, chỉ mở file được chỉ tên, không quét cả thư mục.**

### 21.3 Hợp đồng của một module

Mỗi module có một file mô tả ngắn, tối đa một trang:

```text
# scoring/domain_dedupe.py

Nhiệm vụ:  Trong danh sách URL đã chấm điểm, chỉ giữ URL điểm cao nhất mỗi domain.

Nhận vào:  danh sách URL, mỗi URL có: url, domain, score
Trả ra:    danh sách URL, mỗi URL có thêm: keep (đúng/sai), reason

Không được: gọi API, ghi database, đọc config toàn cục.

Quy tắc bất biến:
- URL bị loại vẫn phải được trả về kèm reason = "duplicate_domain".
- Điểm bằng nhau thì giữ URL có source_priority cao hơn.

Test: tests/test_dedupe.py
```

Ba dòng “Nhận vào / Trả ra / Không được” là phần quan trọng nhất. Nó cho agent biết giới hạn của module mà không cần đọc code xung quanh.

### 21.4 Quy tắc cập nhật

- Sửa code làm sai một dòng trong tài liệu thì **phải sửa tài liệu trong cùng lần đó**.
- Tài liệu chỉ ghi hợp đồng và quy tắc. Không copy code vào tài liệu.
- Khi tài liệu và code khác nhau, đó là một lỗi chưa hoàn thành. Không được âm thầm giả định bên nào đúng.

Phân biệt hai câu hỏi:

| Câu hỏi | Nguồn quyết định |
|---|---|
| App hiện tại đang thực sự làm gì? | Code chạy được, migration và test |
| App phải làm gì theo nghiệp vụ? | Kế hoạch tiếng Việt và quyết định đã được người dùng phê duyệt |
| Module đã hứa interface nào? | Module contract và test |
| Thay đổi này có được chủ động quyết định không? | Changelog, ADR hoặc issue đã được duyệt |

Ví dụ: kế hoạch nói field `unconfirmed` không được veto nhưng code lại cho phép veto. Code mô tả đúng hành vi hiện tại, nhưng hành vi đó là bug; phải sửa code và thêm regression test, không được sửa kế hoạch để hợp thức hóa bug.

#### Definition of Done

Một thay đổi chưa hoàn thành cho đến khi các mục liên quan dưới đây được cập nhật trong cùng change:

| Thứ đã thay đổi | Tài liệu/test bắt buộc |
|---|---|
| `src/v2/<area>/<module>.py` | Module contract tương ứng trong `docs/architecture/` và test liên quan |
| File mới trong `src/v2/` | Thêm dòng vào `docs/architecture/INDEX.md` |
| Policy key | `docs/architecture/policy.md` và test policy |
| Bảng, cột hoặc index | `docs/architecture/schema.md`, migration và test |
| Business rule hoặc numeric threshold | Cả hai plan, §24 changelog và regression test |
| Kết thúc hoặc bàn giao phiên triển khai | `docs/implementation/STATUS.md` có bằng chứng kiểm tra và bước tiếp theo |

Repository phải giữ một script kiểm tra, ví dụ `scripts/check-doc-sync.sh`, và chạy cùng script đó ở pre-commit lẫn CI. Gate tối thiểu phải chặn trường hợp code V2 đổi nhưng không có tài liệu kiến trúc liên quan đổi. Hook chỉ ngăn việc quên tài liệu; test và review vẫn phải kiểm tra nội dung có đúng hay không.

Không đặt logic kiểm tra duy nhất trong `.git/hooks/pre-commit`, vì thư mục `.git/hooks` không được commit và máy khác không tự nhận được.

#### Khi dùng Graphify

`INDEX.md` và module contracts được đọc trong mỗi task. Graphify chỉ dùng khi `INDEX.md` không đủ, khi onboarding/refactor lớn hoặc ở cuối milestone; không rebuild sau mỗi thay đổi nhỏ.

Mọi lần tạo hoặc đọc graph phải giới hạn vào code của dự án như `src/`, `dashboard/`, `scripts/`, `tests/` và loại `graphify/`, `version1-lasted/`, dependency/vendor. Nếu không lọc, agent có thể học nhầm kiến trúc của tool hoặc code V1 thay vì V2.

### 21.5 Hai bản kế hoạch phải khớp nhau

Kế hoạch này có hai bản:

| Bản | File | Dành cho |
|---|---|---|
| Tiếng Việt | `docs/v2-modular-refactor-plan.md` | Người đọc, quản lý |
| Tiếng Anh | `docs/v2-modular-refactor-plan.en.md` | AI agent |

Bản tiếng Anh không phải bản dịch từng câu. Nó là bản đặc tả ngắn hơn, dùng cùng số mục và cùng con số.

Quy tắc giữ hai bản khớp nhau:

1. Cùng hệ thống số mục. Mục 3.7 ở bản Việt là mục 3.7 ở bản Anh.
2. Đổi một quyết định nghiệp vụ thì **phải sửa cả hai bản trong cùng lần**.
3. Mọi con số chỉ được viết một chỗ và lặp lại y nguyên ở bản kia. Ví dụ ngưỡng 35 điểm, 10 URL, 25% điểm giảm.
4. Khi hai bản khác nhau thì **bản tiếng Việt đúng**, vì đó là bản người dùng quyết định.
5. Cuối mỗi bản có bảng lịch sử thay đổi ghi ngày và mục đã sửa.

### 21.6 Bàn giao tiến độ giữa AI agent và chat session

Mục tiêu: một agent hoặc chat session mới có thể tiếp tục ngay mà không phải đoán việc nào đã làm, nhưng vẫn phải kiểm tra trạng thái thật trước khi tin tài liệu.

#### Self-bootstrap khi bộ tài liệu chưa tồn tại

Với mọi nhiệm vụ được phép thêm/sửa/xóa code, agent phải kiểm tra các path sau trước lần edit code đầu tiên:

```text
AGENTS.md
docs/architecture/INDEX.md
docs/implementation/STATUS.md
docs/implementation/work-items/
scripts/check-doc-sync.sh
```

Nếu thiếu, agent tự tạo phần thiếu trong phạm vi repository; không dừng để hỏi chỉ vì bootstrap chưa có. Quy tắc:

1. Không ghi đè file đã tồn tại. Đọc và giữ nội dung hiện có; chỉ bổ sung section bắt buộc còn thiếu.
2. Tạo directory bằng path chính xác, không quét hoặc copy tài liệu từ V1, backup, Graphify hay repository khác.
3. Dùng kế hoạch V2 tiếng Việt làm nguồn nghiệp vụ. Không tự phát minh module, trạng thái hoặc quyết định chưa có bằng chứng.
4. `INDEX.md` ban đầu chỉ liệt kê file đã xác minh bằng code và test. Mục chưa xác minh ghi `unverified`, không đoán.
5. Tạo module contract cho module được task hiện tại chạm tới trước khi sửa module đó. Không cần tạo hàng loạt contract rỗng cho toàn codebase.
6. `STATUS.md` ban đầu được lập từ `git status`, code/migration hiện có và test thực sự đã chạy. Không ghi `completed` dựa vào plan.
7. Tạo work-item file cho task hiện tại, với owner, file scope, acceptance criteria, status và evidence.
8. `scripts/check-doc-sync.sh` ban đầu phải chạy read-only, không tự sửa file, không gọi API và chặn code V2 thay đổi mà thiếu contract/STATUS liên quan.
9. Ghi một event trong `STATUS.md`: `bootstrap_created` hoặc `bootstrap_repaired`, timestamp, file đã tạo/bổ sung và verification command.
10. Chạy kiểm tra bootstrap trước khi code edit:

   ```text
   mọi path bắt buộc tồn tại
   STATUS có Current handoff và Verification
   work item hiện tại có owner và acceptance criteria
   doc-sync checker chạy được
   ```

Nếu task chỉ yêu cầu đọc, giải thích, review hoặc chẩn đoán không sửa code, agent không tự tạo bootstrap. Agent báo ngắn rằng bootstrap thiếu và chỉ tạo khi người dùng cho phép thay đổi repository.

Nếu bootstrap tạo thất bại do permission hoặc trạng thái mâu thuẫn, agent không được tiếp tục sửa code. Ghi blocker nếu có thể và yêu cầu người dùng xử lý.

#### File trạng thái triển khai

`docs/implementation/STATUS.md` là bản tổng hợp tiến độ hiện tại. File này phải ngắn, ưu tiên thông tin giúp thực hiện bước tiếp theo, và có cấu trúc bắt buộc:

```markdown
# V2 Implementation Status

Last updated: 2026-07-29 16:30 +07
Updated by: <agent hoặc người cập nhật>
Current milestone: <giai đoạn trong §16>
Overall state: pending | in_progress | blocked | completed

## Current handoff
Next action: <một hành động cụ thể có thể bắt đầu ngay>
Read first: <plan section, module contract, code và test cần đọc>
Do not redo: <việc đã hoàn thành và có bằng chứng>

## Stage progress
| Stage/work item | Status | Evidence |

## Work completed this session
<hành vi đã thay đổi và danh sách file>

## Verification
<command đã chạy, kết quả, test còn fail hoặc chưa chạy>

## Decisions made
<quyết định mới và link tới plan/ADR/issue nếu có>

## Blockers and open questions
<blocker, chủ sở hữu, điều kiện để tiếp tục>

## Working-tree warning
<thay đổi không thuộc task hiện tại; không được sửa hoặc revert>
```

`Next action` phải là một hành động thực thi được, ví dụ “viết failing test số 7 trong `tests/test_taxcode.py`”, không ghi mơ hồ như “tiếp tục stage 2”.

#### Protocol khi bắt đầu phiên

1. Đọc `AGENTS.md`.
2. Nếu task có sửa code, chạy kiểm tra self-bootstrap và tạo/sửa phần còn thiếu theo mục trên.
3. Đọc `docs/implementation/STATUS.md`.
4. Kiểm tra trạng thái thật bằng `git status`, file/migration liên quan và test phù hợp.
5. Nếu `STATUS.md` khác trạng thái thật, ghi rõ sai khác và sửa `STATUS.md` trước khi dựa vào nó.
6. Bắt đầu từ `Next action`; không làm lại phần `Do not redo` nếu không có bằng chứng ngược lại.

#### Protocol trong lúc làm và trước khi kết thúc

Không cần sửa `STATUS.md` sau mỗi dòng code. Phải cập nhật tại checkpoint có ý nghĩa:

- Work item hoặc stage đổi trạng thái.
- Một nhóm test chuyển từ fail sang pass hoặc phát sinh failure mới.
- Có quyết định thiết kế/nghiệp vụ mới.
- Có blocker.
- Chuyển việc cho agent khác hoặc kết thúc chat session.

Trước khi kết thúc hoặc bàn giao, agent phải ghi:

1. Hành vi đã hoàn thành và file đã đổi.
2. Lệnh kiểm tra đã chạy và kết quả chính xác; nếu chưa chạy phải ghi `not run`.
3. Test còn fail, blocker và câu hỏi mở.
4. Một `Next action` cụ thể.
5. Danh sách file/mục tài liệu agent sau cần đọc.
6. Thay đổi trong working tree thuộc người dùng hoặc task khác cần giữ nguyên.

Không được ghi `completed` chỉ vì đã sửa code. Chỉ ghi `completed` khi acceptance criteria liên quan đã đạt và có evidence. Nếu session bị dừng giữa chừng, ghi phần đã làm là `in_progress`, không đoán kết quả.

#### Khi có nhiều agent chạy song song

Nhiều agent không cùng sửa tự do một đoạn trong `STATUS.md`. Dùng:

```text
docs/implementation/STATUS.md
docs/implementation/work-items/<work-item-id>.md
```

Mỗi work item có đúng một owner tại một thời điểm, phạm vi file rõ ràng, acceptance criteria, evidence và trạng thái:

```text
pending → in_progress → completed
                    ↘ blocked
```

Agent chỉ sửa file work item mình sở hữu. `STATUS.md` tổng hợp và liên kết tới các work item; người/agent điều phối cập nhật phần tổng hợp để tránh xung đột.

#### Quy tắc chống status bị cũ hoặc sai

`STATUS.md` là chỉ dẫn bàn giao, không phải bằng chứng cuối cùng. Agent mới phải xác minh các claim quan trọng bằng code, Git và test. Nếu file ghi “test pass” nhưng không có command/kết quả hoặc code hiện tại đã đổi sau timestamp đó, coi claim là chưa xác minh.

## 22. Mức cần thiết và thời gian của từng bước

Mục này dành cho tình huống: người dùng có kiến thức IT cơ bản, dùng AI agent để viết code, và tự kiểm tra kết quả bằng tay.

Vì vậy thời gian được tách thành hai phần khác nhau:

- **Thời gian AI viết code**: tính theo số phiên làm việc với agent.
- **Thời gian người dùng kiểm tra**: thời gian thật người dùng phải ngồi xem kết quả có đúng hay không.

Với cách làm này, **kiểm tra tốn nhiều thời gian hơn viết code**.

### 22.1 Ba mức cần thiết

| Mức | Nghĩa |
|---|---|
| **BẮT BUỘC** | Không làm thì V2 không tốt hơn V1, hoặc sẽ sinh dữ liệu sai |
| **NÊN LÀM** | Giảm chi phí hoặc giảm lỗi rõ rệt, nhưng có thể lùi |
| **ĐỢT SAU** | Có thể bỏ hoàn toàn ở đợt đầu |

### 22.2 Bảng đánh giá

| Việc | Mức | Lý do | AI viết code | Người kiểm tra |
|---|---|---|---|---|
| Bỏ `waitFor: 3000` và `DELAY_SECONDS` | **BẮT BUỘC** | Mỗi công ty tiết kiệm ~60 giây, sửa 2 dòng | 1 phiên | 1 giờ |
| Sửa bug cache hit + dọn 89.070 dòng trùng + thêm unique key | **BẮT BUỘC** | Dữ liệu trùng đang tăng dần | 1 phiên | 3 giờ |
| Sửa retry: `max_attempts`, phân loại 4xx/5xx | **BẮT BUỘC** | Đang mất kết quả vì bỏ cuộc quá sớm | 1–2 phiên | 3 giờ |
| Module kiểm tra tax code (checksum, 3 kết quả) | **BẮT BUỘC** | Chặn dữ liệu sai công ty. Test được offline, không tốn tiền API | 1 phiên | 2 giờ |
| Giữ Quick Search + đánh dấu `unconfirmed` | **BẮT BUỘC** | Không có thì 1.252 công ty thiếu địa chỉ bị dừng | 1–2 phiên | 4 giờ |
| Giữ business status gate | **BẮT BUỘC** | Tiết kiệm chi phí lớn nhất | 1 phiên | 3 giờ |
| Dedup domain: 1 URL mỗi domain | **BẮT BUỘC** | Tránh mua 10 lần cùng một trang | 1 phiên | 3 giờ |
| Bảng log trực tiếp có cột `reason` | **BẮT BUỘC** | Không có thì mọi bước kiểm tra sau đều rất chậm | 1–2 phiên | 2 giờ |
| `AGENTS.md` + `INDEX.md` + hợp đồng module + `STATUS.md` | **BẮT BUỘC** | Làm trước thì mọi phiên AI sau đều rẻ hơn, ít sai hơn và tiếp tục đúng chỗ | 1 phiên | 1 giờ |
| Query bắt buộc có tỉnh/thành + xem trước trước khi mở batch | **BẮT BUỘC** | Chặn tiêu tiền cho query sai | 2 phiên | 5 giờ |
| Test khóa “một lần gọi AI = một URL” | **BẮT BUỘC** | Xóa hàm cũ còn sót, chặn lỗi tái diễn | 1 phiên | 1 giờ |
| Chấm điểm ba loại bằng chứng (mục 3.3) | **NÊN LÀM** | Giảm URL sai công ty | 1–2 phiên | 5 giờ |
| Context Slicing trước khi gọi AI | **NÊN LÀM** | Giảm token và giảm lấy nhầm footer | 2 phiên | 6 giờ |
| Chuyển domain, điểm, query ra file policy | **NÊN LÀM** | Sau này đổi nghiệp vụ không cần sửa code | 2 phiên | 4 giờ |
| Chia work unit nhỏ | **NÊN LÀM** | Dừng và chạy tiếp chính xác hơn | 3–4 phiên | 8 giờ |
| Cheap GET Preflight | **ĐỢT SAU** | Lợi ích chưa chắc, có rủi ro bị chặn IP. Nên đo trên 100 URL trước | 2 phiên | 6 giờ |
| Màn hình Deferred Review | **ĐỢT SAU** | Có ích nhưng chưa chặn việc chạy | 3 phiên | 6 giờ |
| Worker pool và Runtime Supervisor mới | **ĐỢT SAU** | V1 đang chạy được, xem mục 9.3b | 4 phiên | 10 giờ |
| Gộp ba giao diện vào một application service | **ĐỢT SAU** | Việc dọn code, không thêm kết quả | 3 phiên | 5 giờ |

### 22.3 Tổng thời gian

| Nhóm | AI viết code | Người kiểm tra | Ước tính thực tế |
|---|---|---|---|
| **BẮT BUỘC** | 12–15 phiên | ~28 giờ | **2 đến 3 tuần** |
| **NÊN LÀM** | 8–10 phiên | ~23 giờ | thêm 2 đến 3 tuần |
| **ĐỢT SAU** | 12 phiên | ~27 giờ | thêm 3 đến 4 tuần |

Ước tính thực tế dựa trên khoảng 2–3 giờ làm việc mỗi ngày.

Con số “ước tính thực tế” lớn hơn tổng hai cột bên trái, vì trong thực tế còn phát sinh: sửa lại chỗ AI làm sai, chờ chạy batch thật, và đọc kết quả.

### 22.4 Thứ tự nên làm khi gần hết thời gian

Nếu chỉ còn khoảng hai tuần, làm đúng bốn nhóm này theo thứ tự:

```text
Ngày 1        AGENTS.md + INDEX.md + hợp đồng module + STATUS.md
              → làm trước để mọi phiên AI sau đều rẻ hơn

Ngày 2        Bảng log có cột reason
              → làm sớm để kiểm tra các bước sau nhanh hơn nhiều

Ngày 3–5      Ba lỗi rẻ: waitFor, cache hit + unique key, retry
              → đây là phần cho kết quả rõ nhất trên mỗi giờ bỏ ra

Ngày 6–10     Bốn hành vi V1 đang có: Quick Search, status gate,
              dedup domain, tax code checksum
              → phần này bảo vệ độ chính xác và chi phí
```

Hai việc đầu không tạo kết quả nhìn thấy được, nhưng làm trước sẽ rút ngắn tất cả các việc sau. Nếu làm sau, mỗi lần kiểm tra đều phải mò trong code.

Phần còn lại của kế hoạch để dành cho đợt sau, không ảnh hưởng đến việc V2 chạy được.

## 23. Tài liệu API đã đối chiếu

- [Firecrawl Batch Scrape API](https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape)
- [Firecrawl Advanced Scraping Guide](https://docs.firecrawl.dev/advanced-scraping-guide)
- [Firecrawl API errors](https://docs.firecrawl.dev/api-reference/introduction)

## 24. Lịch sử thay đổi

Bản tiếng Anh `docs/v2-modular-refactor-plan.en.md` phải được sửa cùng lần với bảng này. Xem quy tắc ở mục 21.5.

| Ngày | Mục đã sửa | Nội dung |
|---|---|---|
| 2026-07-27 | — | Bản đầu tiên |
| 2026-07-28 | 1, 2.3, 3.1, 3.5, 3.6, 3.7, 6, 8, 9, 10, 16, 17, 19 | Chuyển hướng sang sửa dần trên bản copy của V1. Bổ sung lại Quick Search, business status gate, veto tax code và dedup domain. Bỏ thiết kế dùng chung một bộ search result. Chia code thành khoảng 30 file nhỏ. |
| 2026-07-28 | 3.3, 3.8, 9.3b, 12, 16, 17.1, 17.3, 17.4b, 20, 21, 22 | Field trong query được tính điểm giảm thay vì bỏ hẳn. Thêm rule dữ liệu Quick Search là `unconfirmed` và không được veto. Giải thích lại mục 12 và mã lỗi HTTP. Lùi worker pool sang đợt sau. Thêm bảng log có cột `reason`, tài liệu kiến trúc cho AI agent, và bảng mức cần thiết kèm thời gian. |
| 2026-07-29 | 3.7, 3.8, 6, 17.1b, 21, 24 | Siết promotion: cấm field tự xác nhận qua query của chính nó, nhóm source family và nội dung copy, yêu cầu so khớp tên kèm bằng chứng độc lập, xử lý field đối thủ và lưu provenance. Thêm phanh `tax_code_veto_rejects_all`, phân biệt authoritative registry với tax directory, test hồi quy, Definition of Done, doc-sync gate, quy tắc nguồn quyết định và phạm vi dùng Graphify. Thêm `docs/implementation/STATUS.md`, protocol bắt đầu/kết thúc phiên, bằng chứng bàn giao, bảo vệ status cũ và work item cho nhiều agent chạy song song. |
| 2026-07-29 | 16, 24 | Thêm `docs/v2-stage1-critical-fixes-implementation-plan.md`: kế hoạch chi tiết cho fixed wait, cache/dedup migration và retry; gồm baseline, test đỏ, thứ tự commit, backup/rollback, test gate và Definition of Done. Làm rõ Stage 1 tạo retry executor tối thiểu, Stage 6 mở rộng resource control. |
| 2026-07-29 | 21, 24 | Thêm self-bootstrap protocol: trước code edit, agent tự tạo/sửa phần bootstrap còn thiếu, không ghi đè, không đoán tiến độ, xác minh bằng Git/test và tạo work item. Nhiệm vụ read-only chỉ báo thiếu, không tự ghi repository. Thêm `AGENTS.md` tối thiểu ở root để instruction được tự động phát hiện. |
