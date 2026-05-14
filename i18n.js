const I18N = {
  vi: {
    badge: "Kiến trúc Hệ thống",
    title: "Auto Search Company",
    subtitle: 'Kiến trúc <strong>Sequential Fallback</strong> & <strong>Early Stop</strong> — Tối đa hoá tỷ lệ tìm thấy thông tin liên hệ với chi phí API thấp nhất',
    stats: ["Core Steps", "Early Stop Points", "Search Strategies", "API Integrations", "Resumable"],
    btnSub: "📐 Sub-steps",
    btnHighlight: "✨ Highlight All",
    footerTitle: "Auto Search Company — Sequential Fallback Pipeline v1.0",
    footerHint: "Hover để xem tóm tắt • Click để xem chi tiết • Đường nối sáng lên khi hover node",
    legendItems: ["Bước 1: Khởi tạo","Bước 2: AI Search","Bước 3: Maps","Bước 4: Deep Search","Bước 5: Scrape & Extract","Early Stop Point"],
    modalSections: { mission:"🎯 Nhiệm vụ", input:"📥 Input", process:"⚙️ Quy trình xử lý", earlyStop:"⚡ Early Stop", output:"📤 Output", example:"💡 Ví dụ minh hoạ" },
    steps: [
      {
        title:"Khởi tạo Dữ liệu", titleEn:"Input & Initialization",
        subtitle:"Import Excel → SQLite DB → Hàng đợi xử lý",
        tooltip:"Đưa danh sách công ty thô vào hệ thống và khởi tạo quy trình theo dõi. Hỗ trợ cơ chế Resumable.",
        status:"Auto-resume",
        detail:{
          mission:"Đưa danh sách công ty thô vào hệ thống và khởi tạo quy trình theo dõi.",
          input:"File Excel do người dùng tải lên chứa danh sách tên công ty tiếng Anh hoặc tiếng Việt.",
          process:[
            {title:"Đọc file Excel",desc:"Hệ thống đọc file và đẩy vào cơ sở dữ liệu SQLite (bảng companies)."},
            {title:"Gán trạng thái",desc:"Trạng thái ban đầu: status = 'pending'. Mỗi công ty được gán ID duy nhất."},
            {title:"Cơ chế Resumable",desc:"Nếu hệ thống bị tắt đột ngột, lần chạy sau sẽ tiếp tục từ công ty đang bị dở dang thay vì chạy lại từ đầu."}
          ],
          output:"Hàng đợi các công ty chờ xử lý trong DB với status = 'pending'.",
          earlyStop:null,
          example:"VD: Upload file 500 công ty → DB tạo 500 records pending → Bắt đầu xử lý từ record #1."
        }
      },
      {
        title:"Khảo sát Nhanh AI", titleEn:"AI Quick Search / Grounding",
        subtitle:"AI + Search Grounding → Chốt nhanh công ty dễ tìm",
        tooltip:"Dùng AI gọi công cụ tìm kiếm thực tế để 'chốt nhanh' các công ty dễ tìm.",
        status:"Early-stop enabled",
        detail:{
          mission:"Dùng AI gọi công cụ tìm kiếm thực tế để 'chốt nhanh' các công ty dễ tìm.",
          input:"Tên công ty thô (tiếng Anh hoặc tiếng Việt).",
          process:[
            {title:"Gửi prompt cho AI",desc:"Mô hình AI (hỗ trợ Search Grounding) thực hiện search Google theo thời gian thực."},
            {title:"AI suy luận",desc:"AI đọc các đoạn trích dẫn (snippet) để suy luận và trả về JSON: core_name_vi, tax_code, phone, address, website, confidence."},
            {title:"Early Stop Check",desc:"Nếu có Số điện thoại và confidence đủ cao → chốt 'done', bỏ qua các bước sau."}
          ],
          output:"Thành công: Lưu liên hệ vào DB → Công ty tiếp theo.\nThất bại: Cập nhật Tên VN + MST vào DB làm 'vốn' cho bước sau.",
          earlyStop:"Có SĐT + Confidence cao → DONE",
          example:"VD: AI tìm 'ABC Corp' → Google trả về snippet chứa SĐT 028-xxxx → confidence 0.9 → Chốt done!"
        }
      },
      {
        title:"Google Maps Search", titleEn:"Google Maps via Serper",
        subtitle:"Serper Places API → SĐT từ chính chủ doanh nghiệp",
        tooltip:"Tra cứu trên bản đồ. Dữ liệu Maps thường do chính chủ cung cấp nên độ tin cậy cực cao.",
        status:"Early-stop enabled",
        detail:{
          mission:"Tra cứu thông tin trên bản đồ. Dữ liệu trên Maps thường do chính chủ doanh nghiệp cung cấp nên độ tin cậy cực cao.",
          input:"Tên công ty (ưu tiên Tên pháp lý tiếng Việt lấy từ Bước 2).",
          process:[
            {title:"Gọi Serper Places API",desc:"Tra cứu Google Maps để tìm thông tin doanh nghiệp."},
            {title:"Phân tích kết quả",desc:"Lọc kết quả trả về để tìm phoneNumber, address, website."},
            {title:"Tận dụng tối đa",desc:"Nếu Maps không có SĐT nhưng có Website → lưu Website vào hàng đợi cạo dữ liệu (should_scrape = 1) với điểm ưu tiên rất cao."}
          ],
          output:"Thành công: SĐT lưu vào DB → DONE.\nThất bại: Chuyển sang Bước 4 (mang theo URL Website từ Maps nếu có).",
          earlyStop:"Tìm thấy phoneNumber → DONE",
          example:"VD: 'CÔNG TY TNHH ABC' → Maps trả về SĐT: 028-1234-5678, Địa chỉ: Q7, HCM → Chốt!"
        }
      },
      {
        title:"Deep Search 4-Step", titleEn:"Deep Search Strategy",
        subtitle:"Contact → Infer → Tax Code → Bare Query",
        tooltip:"Chiến thuật cốt lõi với 4 công đoạn tinh vi để thu thập URL chất lượng cao.",
        status:"Multi-stage",
        detail:{
          mission:"Chiến thuật cốt lõi (Module SearchModule). Thay vì search mù quáng, hệ thống đi qua 4 công đoạn tinh vi để thu thập URL, ưu tiên tiết kiệm API credit.",
          input:"Tên công ty (EN + VN), Mã số thuế (nếu có).",
          process:[
            {title:"4.1 Contact Query",desc:"Query: (\"Tên EN\" OR \"Tên VN\") AND (\"liên hệ\" OR \"contact\"). Bắn thẳng vào trang chứa SĐT. Early Stop nếu đủ link xịn."},
            {title:"4.2 Infer VN Data",desc:"Chỉ chạy nếu chưa có MST/Tên VN. Lướt URL từ 4.1, lọc trang .gov.vn, masothue... Dùng Regex ép lấy Tên pháp lý + MST."},
            {title:"4.3 Tax Code Query",desc:"Chỉ chạy nếu đã có MST. Query: \"{MST}\". MST là định danh duy nhất → lòi ra danh bạ DN uy tín nhất."},
            {title:"4.4 Bare Query",desc:"Query: \"{Tên EN}\" OR \"{Tên VN}\". Bước vét máng cuối cùng nếu chưa đủ URL."}
          ],
          output:"Tập hợp các URL chất lượng cao, đã loại bỏ trùng lặp (dedup) và chấm điểm (score), sẵn sàng để cạo.",
          earlyStop:"Mỗi sub-step có Early Stop riêng khi đủ link xịn",
          example:"VD: Contact Query tìm 3 link → Infer ra MST: 0312345678 → Tax Query thêm 5 link → Tổng 8 URL unique, scored."
        }
      },
      {
        title:"Scrape & Extract AI", titleEn:"Scrape + AI Extract",
        subtitle:"Firecrawl → Regex Filter → AI Extract → Final Result",
        tooltip:"Vào sâu bên trong các URL đã lọc để 'bắt' liên hệ. Xử lý xung đột bằng confidence scoring.",
        status:"Final output",
        detail:{
          mission:"Vào sâu bên trong các URL đã lọc để 'bắt' liên hệ.",
          input:"Tập hợp URL chất lượng cao từ Bước 4.",
          process:[
            {title:"5.1 Firecrawl Scrape",desc:"Gọi Firecrawl API để cào nội dung HTML của các URL đạt chuẩn, chuyển thành Markdown sạch."},
            {title:"5.2a Quét sơ bộ (Regex)",desc:"Nếu văn bản không có cụm số nào giống SĐT → vứt bỏ ngay để tiết kiệm tiền AI."},
            {title:"5.2b AI Extraction",desc:"Nếu có tín hiệu khả quan → đẩy vào AI trích xuất JSON: phone, email, address, representative."},
            {title:"Xử lý xung đột",desc:"Nhiều SĐT từ các trang khác nhau → so sánh confidence score → giữ lại SĐT điểm cao nhất."}
          ],
          output:"Chốt hạ kết quả, đổi status = 'done' và xuất Excel báo cáo (bao gồm sheet chi tiết tracking đường đi dữ liệu).",
          earlyStop:null,
          example:"VD: 8 URL → Firecrawl cạo → 5 có tín hiệu SĐT → AI extract → 3 SĐT khác nhau → Chọn SĐT confidence cao nhất → Done!"
        }
      }
    ],
    connections:[
      {label:"Hàng đợi công ty"},
      {label:"Thiếu SĐT → Tiếp tục"},
      {label:"Thiếu SĐT + URL Website"},
      {label:"Tập URL đã chấm điểm"}
    ]
  },
  ko: {
    badge: "시스템 아키텍처",
    title: "Auto Search Company",
    subtitle: '<strong>Sequential Fallback</strong> & <strong>Early Stop</strong> 아키텍처 — 최소 API 비용으로 연락처 정보 검색률 극대화',
    stats: ["핵심 단계", "조기 중단 지점", "검색 전략", "API 통합", "재개 가능"],
    btnSub: "📐 하위 단계",
    btnHighlight: "✨ 전체 강조",
    footerTitle: "Auto Search Company — Sequential Fallback Pipeline v1.0",
    footerHint: "호버하여 요약 보기 • 클릭하여 상세 보기 • 노드 호버 시 연결선 활성화",
    legendItems: ["1단계: 초기화","2단계: AI 검색","3단계: Maps","4단계: 심층 검색","5단계: 스크래핑 & 추출","조기 중단 지점"],
    modalSections: { mission:"🎯 임무", input:"📥 입력", process:"⚙️ 처리 과정", earlyStop:"⚡ 조기 중단", output:"📤 출력", example:"💡 예시" },
    steps: [
      {
        title:"데이터 초기화", titleEn:"Input & Initialization",
        subtitle:"Excel 가져오기 → SQLite DB → 처리 대기열",
        tooltip:"원시 회사 목록을 시스템에 입력하고 추적 프로세스를 초기화합니다. 재개 가능 메커니즘 지원.",
        status:"자동 재개",
        detail:{
          mission:"원시 회사 목록을 시스템에 입력하고 추적 프로세스를 초기화합니다.",
          input:"사용자가 업로드한 영어 또는 베트남어 회사명이 포함된 Excel 파일.",
          process:[
            {title:"Excel 파일 읽기",desc:"시스템이 파일을 읽어 SQLite 데이터베이스(companies 테이블)에 저장합니다."},
            {title:"상태 할당",desc:"초기 상태: status = 'pending'. 각 회사에 고유 ID가 할당됩니다."},
            {title:"재개 가능 메커니즘",desc:"시스템이 갑자기 중단되면, 다음 실행 시 처음부터 다시 시작하지 않고 중단된 회사부터 계속합니다."}
          ],
          output:"DB에서 status = 'pending'인 처리 대기 회사 대기열.",
          earlyStop:null,
          example:"예: 500개 회사 파일 업로드 → DB에 500개 pending 레코드 생성 → 레코드 #1부터 처리 시작."
        }
      },
      {
        title:"AI 빠른 검색", titleEn:"AI Quick Search / Grounding",
        subtitle:"AI + Search Grounding → 쉬운 회사 즉시 확정",
        tooltip:"AI가 실시간 검색 도구를 호출하여 쉽게 찾을 수 있는 회사를 '즉시 확정'합니다.",
        status:"조기 중단 활성",
        detail:{
          mission:"AI가 실시간 검색 도구를 호출하여 쉽게 찾을 수 있는 회사를 '즉시 확정'합니다.",
          input:"원시 회사명 (영어 또는 베트남어).",
          process:[
            {title:"AI에 프롬프트 전송",desc:"AI 모델(Search Grounding 지원)이 실시간으로 Google 검색을 수행합니다."},
            {title:"AI 추론",desc:"AI가 검색 스니펫을 읽고 추론하여 JSON 형식으로 반환: core_name_vi, tax_code, phone, address, website, confidence."},
            {title:"조기 중단 확인",desc:"전화번호가 있고 confidence가 충분히 높으면 → 'done'으로 확정, 이후 단계 건너뜁니다."}
          ],
          output:"성공: 연락처를 DB에 저장 → 다음 회사로.\n실패: 베트남어 이름 + 세금코드를 DB에 업데이트하여 이후 단계의 '자산'으로 활용.",
          earlyStop:"전화번호 + 높은 Confidence → DONE",
          example:"예: AI가 'ABC Corp' 검색 → Google 스니펫에서 전화번호 028-xxxx 발견 → confidence 0.9 → 확정!"
        }
      },
      {
        title:"Google Maps 검색", titleEn:"Google Maps via Serper",
        subtitle:"Serper Places API → 사업주 직접 제공 전화번호",
        tooltip:"지도에서 조회. Maps 데이터는 보통 사업주가 직접 제공하므로 신뢰도가 매우 높습니다.",
        status:"조기 중단 활성",
        detail:{
          mission:"지도에서 정보를 조회합니다. Maps의 데이터는 보통 사업주가 직접 제공하므로 신뢰도가 매우 높습니다.",
          input:"회사명 (2단계에서 얻은 베트남어 법적 명칭 우선).",
          process:[
            {title:"Serper Places API 호출",desc:"Google Maps에서 기업 정보를 조회합니다."},
            {title:"결과 분석",desc:"반환된 결과에서 phoneNumber, address, website를 필터링합니다."},
            {title:"최대 활용",desc:"Maps에 전화번호가 없지만 웹사이트가 있으면 → 웹사이트를 스크래핑 대기열에 저장 (should_scrape = 1), 매우 높은 우선순위."}
          ],
          output:"성공: 전화번호를 DB에 저장 → DONE.\n실패: 4단계로 이동 (Maps에서 얻은 웹사이트 URL 포함).",
          earlyStop:"phoneNumber 발견 → DONE",
          example:"예: '회사 ABC' → Maps에서 전화번호: 028-1234-5678, 주소: Q7, HCM 반환 → 확정!"
        }
      },
      {
        title:"심층 검색 4단계", titleEn:"Deep Search Strategy",
        subtitle:"Contact → Infer → Tax Code → Bare Query",
        tooltip:"고품질 URL 수집을 위한 4가지 정교한 단계의 핵심 전략.",
        status:"다단계",
        detail:{
          mission:"핵심 전략 (SearchModule). 무작위 검색 대신, 시스템이 4가지 정교한 단계를 거쳐 URL을 수집하며 API 크레딧 절약을 우선합니다.",
          input:"회사명 (EN + VN), 세금코드 (있는 경우).",
          process:[
            {title:"4.1 Contact Query",desc:"쿼리: (\"영문명\" OR \"베트남명\") AND (\"liên hệ\" OR \"contact\"). 전화번호가 있을 가능성이 가장 높은 페이지를 직접 타겟팅. 충분한 링크 확보 시 조기 중단."},
            {title:"4.2 Infer VN Data",desc:"세금코드/베트남명이 없을 때만 실행. 4.1에서 얻은 URL을 탐색하여 .gov.vn, masothue 등의 신뢰할 수 있는 페이지 필터링. Regex로 법적 명칭 + 세금코드 추출."},
            {title:"4.3 Tax Code Query",desc:"세금코드가 있을 때만 실행. 쿼리: \"{세금코드}\". 세금코드는 고유 식별자 → 가장 신뢰할 수 있는 기업 디렉토리가 나옵니다."},
            {title:"4.4 Bare Query",desc:"쿼리: \"{영문명}\" OR \"{베트남명}\". 이전 단계에서 충분한 URL을 확보하지 못한 경우의 최종 검색."}
          ],
          output:"중복 제거(dedup) 및 점수화(score)된 고품질 URL 모음, 스크래핑 준비 완료.",
          earlyStop:"각 하위 단계에서 충분한 링크 확보 시 개별 조기 중단",
          example:"예: Contact Query에서 3개 링크 → MST 추론: 0312345678 → Tax Query에서 5개 추가 → 총 8개 고유 URL, 점수화 완료."
        }
      },
      {
        title:"스크래핑 & AI 추출", titleEn:"Scrape + AI Extract",
        subtitle:"Firecrawl → Regex 필터 → AI 추출 → 최종 결과",
        tooltip:"필터링된 URL 내부를 깊이 탐색하여 연락처를 '포착'. Confidence 점수로 충돌을 해결합니다.",
        status:"최종 출력",
        detail:{
          mission:"필터링된 URL 내부를 깊이 탐색하여 연락처를 '포착'합니다.",
          input:"4단계에서 얻은 고품질 URL 모음.",
          process:[
            {title:"5.1 Firecrawl 스크래핑",desc:"Firecrawl API를 호출하여 적합한 URL의 HTML 콘텐츠를 크롤링하고 깨끗한 Markdown으로 변환합니다."},
            {title:"5.2a 예비 검사 (Regex)",desc:"텍스트에 전화번호와 유사한 숫자 조합이 없으면 → AI 비용 절약을 위해 즉시 폐기합니다."},
            {title:"5.2b AI 추출",desc:"유망한 신호가 있으면 → AI에 전달하여 JSON 추출: phone, email, address, representative."},
            {title:"충돌 처리",desc:"여러 페이지에서 다른 전화번호 → confidence 점수 비교 → 가장 높은 점수의 전화번호 유지."}
          ],
          output:"최종 결과 확정, status = 'done'으로 변경 후 Excel 보고서 출력 (데이터 추적 상세 시트 포함).",
          earlyStop:null,
          example:"예: 8개 URL → Firecrawl 크롤링 → 5개에서 전화번호 신호 → AI 추출 → 3개 다른 전화번호 → 최고 confidence 전화번호 선택 → Done!"
        }
      }
    ],
    connections:[
      {label:"회사 대기열"},
      {label:"전화번호 없음 → 계속"},
      {label:"전화번호 없음 + 웹사이트 URL"},
      {label:"점수화된 URL 모음"}
    ]
  }
};
