#!/usr/bin/env python3
"""Build the Korean Blacklist/Skip domain evidence report from read-only data."""

from __future__ import annotations

import html
import json
import sqlite3
import urllib.parse
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "company_data.db"
OUTPUT = ROOT / "output" / "reports" / "blacklist-skip-domain-evidence-ko.html"

MANUAL_BLACKLIST = [
    "infocom.vn", "xinvoice.vn", "dauthau.info", "dauthau.net",
    "thuonghieuviet.info.vn", "fiingate.vn",
]
AUTO_BLACKLIST = OrderedDict([
    ("barnesandnoble.com", (10, 0)), ("camnangxnk-logistics.net", (10, 0)),
    ("ceginfo.hu", (10, 0)), ("cmoa.jp", (10, 0)), ("deviantart.com", (10, 0)),
    ("en.52wmb.com", (22, 1)), ("es.importgenius.com", (18, 2)),
    ("finance.vietstock.vn", (10, 0)), ("fr.dhgate.com", (10, 0)),
    ("fr.importgenius.com", (12, 0)), ("guland.vn", (12, 0)),
    ("hu.dhgate.com", (10, 0)), ("importgenius.co.kr", (11, 0)),
    ("jobs.vn.indeed.com", (10, 0)), ("keepital.com", (10, 0)),
    ("menafn.com", (10, 0)), ("quizlet.com", (10, 0)),
    ("shutterstock.com", (10, 0)), ("topcv.vn", (294, 0)),
    ("vieclam.tv", (12, 0)), ("vietstock.vn", (10, 0)), ("wattpad.com", (10, 0)),
    ("yandex.ru", (10, 0)), ("zenithlongevity.eu", (10, 0)),
    ("zenithtrademark.com", (10, 0)),
])
SKIP_ENTRIES = [
    ("google.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("youtube.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("wikipedia.org", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("baomoi.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("vnexpress.net", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("bing.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("twitter.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("tiktok.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("pinterest.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("amazon.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("shopee.vn", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("lazada.vn", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("topcv.vn", "수동 설정", "Skip 설정이지만 현재 자동 Blacklist가 먼저 적용됨"),
    ("tratencongty.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("emis.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("nhansu.vn", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("vn.joboko.com", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("ybox.vn", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("cdn.thuvienphapluat.vn", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("files.thuvienphapluat.vn", "수동 설정", "뉴스·검색·소셜·중간 수집 사이트 그룹"),
    ("linkedin.com", "런타임 설정", "SCRAPE_LINKEDIN_ENABLED=false일 때 자동 Skip"),
]


def normalized_host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def host_matches(url: str, rule: str) -> bool:
    value = normalized_host(url)
    return value == rule or value.endswith("." + rule)


def load_samples(connection: sqlite3.Connection) -> dict[str, list[dict[str, str]]]:
    connection.row_factory = sqlite3.Row
    pages: dict[str, dict[str, object]] = {}
    rows = connection.execute(
        """
        SELECT sp.url, sp.scrape_status, sp.created_at, ec.id AS contact_id,
               ec.address, ec.phone, ec.email, ec.website, ec.fax, ec.representative
        FROM scraped_pages AS sp
        LEFT JOIN extracted_contacts AS ec ON ec.scraped_page_id = sp.id
        ORDER BY sp.created_at DESC, sp.id DESC
        """
    )
    contact_fields = ("address", "phone", "email", "website", "fax", "representative")
    for row in rows:
        record = pages.setdefault(row["url"], {
            "success": row["scrape_status"] == "success",
            "has_extract": False,
            "has_contact": False,
        })
        if row["contact_id"] is not None:
            record["has_extract"] = True
            if any(row[field] for field in contact_fields):
                record["has_contact"] = True

    rules = set([*MANUAL_BLACKLIST, *AUTO_BLACKLIST])
    buckets: dict[str, list[list[tuple[str, str]]]] = {
        rule: [[], [], [], []] for rule in rules
    }

    def matching_rules(url: str) -> list[str]:
        parts = normalized_host(url).split(".")
        return [".".join(parts[index:]) for index in range(len(parts)) if ".".join(parts[index:]) in rules]

    for url, page in pages.items():
        category = "ai_empty" if page["has_extract"] and not page["has_contact"] else (
            "scraped_no_extract" if page["success"] and not page["has_extract"] else ""
        )
        if category:
            index = 0 if category == "ai_empty" else 1
            for rule in matching_rules(url):
                buckets[rule][index].append((url, category))
    for url, in connection.execute("SELECT url FROM filtered_links ORDER BY id DESC"):
        for rule in matching_rules(url):
            buckets[rule][2].append((url, "filter_record"))
    for url, in connection.execute("SELECT url FROM search_results ORDER BY id DESC"):
        for rule in matching_rules(url):
            buckets[rule][3].append((url, "search_record"))

    selected: dict[str, list[dict[str, str]]] = {}
    for rule in [*MANUAL_BLACKLIST, *AUTO_BLACKLIST]:
        seen: set[str] = set()
        samples: list[dict[str, str]] = []
        for bucket in buckets[rule]:
            for url, category in bucket:
                if url in seen:
                    continue
                seen.add(url)
                samples.append({"url": url, "category": category})
                if len(samples) == 20:
                    break
            if len(samples) == 20:
                break
        selected[rule] = samples
    return selected


def evidence_list(samples: list[dict[str, str]]) -> str:
    labels = {
        "ai_empty": "AI 추출 후 연락처 없음",
        "scraped_no_extract": "스크레이프 완료 · AI 추출 기록 없음",
        "filter_record": "필터 기록 URL · 스크레이프 실패 증거 아님",
        "search_record": "검색 기록 URL · 스크레이프 증거 아님",
    }
    if not samples:
        return '<p class="empty">검증된 URL 기록이 없습니다.</p>'
    items = []
    for item in samples:
        url = html.escape(item["url"], quote=True)
        label = labels[item["category"]]
        items.append(
            f'<li><span class="evidence-label {item["category"]}">{label}</span>'
            f'<a href="{url}" target="_blank" rel="noreferrer">{url}</a></li>'
        )
    return "<ol>" + "".join(items) + "</ol>"


def build_report(samples: dict[str, list[dict[str, str]]]) -> str:
    blacklist_rows = []
    for host in MANUAL_BLACKLIST:
        values = samples[host]
        blacklist_rows.append(f"""
        <tr>
          <td><code>{host}</code></td><td>수동 설정</td>
          <td>호스트별 추가 사유 감사 로그 없음. 코드의 공통 설명은 ‘전화번호를 포함하지 않는 도메인’입니다.</td>
          <td>해당 없음</td>
          <td><details><summary>실제 URL {len(values)}건 보기</summary>{evidence_list(values)}</details></td>
        </tr>""")
    for host, (attempts, contacts) in AUTO_BLACKLIST.items():
        values = samples[host]
        note = "자동 해제 없음" if host not in {"en.52wmb.com", "es.importgenius.com"} else "후속 성공이 있어도 자동 해제되지 않음"
        blacklist_rows.append(f"""
        <tr>
          <td><code>{host}</code></td><td>자동 Blacklist</td>
          <td>AI 추출의 연락처 없음 또는 JSON 처리 실패가 누적되어 초기 기준(10회 이상·성공 0회)을 충족. {note}.</td>
          <td>{attempts}회 / 연락처 {contacts}회</td>
          <td><details><summary>실제 URL {len(values)}건 보기</summary>{evidence_list(values)}</details></td>
        </tr>""")
    skip_rows = "".join(
        f"<tr><td><code>{host}</code></td><td>{source}</td><td>{reason}</td></tr>"
        for host, source, reason in SKIP_ENTRIES
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blacklist · Skip 도메인 근거 목록</title>
  <style>
    :root {{ --navy:#102a43; --teal:#0f766e; --ink:#243b53; --muted:#627d98; --line:#d9e2ec; --paper:#fff; --soft:#f7fafc; --amber:#92400e; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.55 Arial, "Noto Sans KR", sans-serif; }}
    main {{ max-width:1320px; margin:0 auto; padding:44px 32px 72px; }} h1 {{ margin:0 0 8px; color:var(--navy); font-size:31px; line-height:1.22; }} h2 {{ margin:42px 0 12px; color:var(--navy); font-size:22px; border-bottom:2px solid var(--teal); padding-bottom:8px; }} h3 {{ margin:25px 0 8px; font-size:17px; color:var(--navy); }}
    p {{ margin:8px 0; }} .meta {{ color:var(--muted); }} .summary {{ margin:24px 0; padding:16px 20px; border-left:4px solid var(--teal); background:var(--soft); }} .summary strong {{ color:var(--navy); }}
    .notice {{ margin:18px 0; padding:14px 18px; background:#fffbeb; border:1px solid #fde68a; color:var(--amber); }} .legend {{ color:var(--muted); font-size:13px; }}
    .table-wrap {{ overflow-x:auto; border:1px solid var(--line); }} table {{ width:100%; min-width:980px; border-collapse:collapse; }} th,td {{ padding:12px 14px; vertical-align:top; text-align:left; border-bottom:1px solid var(--line); }} th {{ background:var(--navy); color:#fff; font-size:14px; }} tr:last-child td {{ border-bottom:0; }} td:nth-child(1) {{ width:15%; }} td:nth-child(2) {{ width:13%; }} td:nth-child(3) {{ width:31%; }} td:nth-child(4) {{ width:13%; }} td:nth-child(5) {{ width:28%; }} code {{ color:#0f4c5c; font-size:13px; word-break:break-all; }}
    details summary {{ cursor:pointer; color:var(--teal); font-weight:700; }} details[open] summary {{ margin-bottom:10px; }} ol {{ margin:0; padding-left:22px; }} li {{ margin:7px 0; word-break:break-all; }} a {{ color:#135f96; }} .evidence-label {{ display:inline-block; margin:0 7px 3px 0; padding:1px 6px; border:1px solid var(--line); color:var(--muted); font-size:11px; font-weight:700; white-space:nowrap; }} .ai_empty {{ color:#0f766e; border-color:#99f6e4; background:#f0fdfa; }} .scraped_no_extract {{ color:#075985; border-color:#bae6fd; background:#f0f9ff; }} .filter_record,.search_record {{ color:#6b7280; background:#f8fafc; }} .empty {{ color:var(--muted); }} footer {{ margin-top:40px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); padding-top:14px; }}
    @media (max-width:700px) {{ main {{ padding:28px 16px 48px; }} h1 {{ font-size:25px; }} h2 {{ font-size:20px; }} .summary,.notice {{ padding:13px 14px; }} }}
    @media print {{ @page {{ size:A4 landscape; margin:12mm; }} body {{ font-size:9px; }} main {{ max-width:none; padding:0; }} h1 {{ font-size:20px; }} h2 {{ margin-top:20px; font-size:15px; }} .summary,.notice {{ break-inside:avoid; padding:8px; }} .table-wrap {{ overflow:visible; }} table {{ min-width:0; font-size:8px; }} th,td {{ padding:5px; }} details {{ display:block; }} details > summary {{ list-style:none; pointer-events:none; }} details > summary::-webkit-details-marker {{ display:none; }} details:not([open]) > *:not(summary) {{ display:block; }} ol {{ padding-left:14px; }} li {{ margin:2px 0; }} a {{ color:#102a43; text-decoration:none; }} .evidence-label {{ font-size:7px; padding:0 3px; }} }}
  </style>
</head>
<body><main>
  <h1>Blacklist · Skip 도메인 근거 목록</h1>
  <p class="meta">데이터 기준: <code>company_data.db</code> · 설정 기준: <code>pipeline_config.json</code> · 이 문서는 현재 구현과 저장된 기록을 설명합니다.</p>
  <div class="summary"><strong>한눈에 보기:</strong> Blacklist 유효 호스트 31개(수동 6개 + 자동 25개), Skip 항목 21개(수동 20개 + LinkedIn 런타임 1개)입니다. <code>topcv.vn</code>은 두 목록에 모두 있지만 Blacklist가 먼저 검사되어 현재 Blacklist로 처리됩니다. 현재 Whitelist 기능은 없습니다.</div>
  <div class="notice"><strong>URL 표본 해석:</strong> 표본 URL은 도메인의 내용과 저장 기록을 보여 주는 참고 자료입니다. 수동 Blacklist의 표본은 추가 사유를 증명하지 않습니다. ‘필터 기록’과 ‘검색 기록’은 스크레이프 후 연락처 없음의 증거가 아닙니다.</div>
  <h2>1. Blacklist (유효 호스트 31개)</h2>
  <p class="legend">자동 Blacklist는 AI 추출 결과에 연락처 필드가 없거나 JSON 처리 실패가 누적되고, <strong>초기 판단 시점에 10회 이상·연락처 성공 0회</strong>이면 설정됩니다. 이후 연락처가 발견되어도 자동으로 해제되지 않습니다.</p>
  <div class="table-wrap"><table><thead><tr><th>호스트</th><th>등록 방식</th><th>확인된 사유</th><th>통계<br>(기록 / 연락처)</th><th>URL 표본</th></tr></thead><tbody>{''.join(blacklist_rows)}</tbody></table></div>
  <h2>2. Skip 도메인 (항목 21개)</h2>
  <p class="legend">Skip은 점수 0점, 스크레이프 제외로 처리됩니다. 수동 Skip의 도메인별 추가 사유·등록자·등록 시점은 감사 로그에 저장되어 있지 않습니다.</p>
  <div class="table-wrap"><table><thead><tr><th>호스트</th><th>등록 방식</th><th>확인된 분류 이유</th></tr></thead><tbody>{skip_rows}</tbody></table></div>
  <h3>판단 순서와 한계</h3>
  <p>필터는 <strong>Blacklist → Skip</strong> 순서로 검사합니다. 자동 Blacklist 통계는 Firecrawl 호출 실패만을 뜻하지 않으며, AI 추출 단계의 연락처 결과를 기반으로 합니다. 저장된 데이터에는 각 수동 도메인의 등록자, 등록일, 개별 업무 사유가 없으므로 이 문서는 그 이유를 추정하지 않습니다.</p>
  <footer>생성 시점의 읽기 전용 데이터에서 URL을 선택했습니다. 각 Blacklist 호스트는 최대 20개의 고유 URL을 보이며, 우선순위는 AI 추출 후 연락처 없음 → 스크레이프 완료·AI 추출 기록 없음 → 필터 기록 → 검색 기록입니다.</footer>
</main></body></html>"""


def main() -> None:
    with sqlite3.connect(DATABASE) as connection:
        samples = load_samples(connection)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_report(samples), encoding="utf-8")
    counts = {host: len(urls) for host, urls in samples.items()}
    print(f"Wrote {OUTPUT}")
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
