import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from src.database import DatabaseManager


AUTO_MATCH_SCORE = 85.0
MIN_CANDIDATE_SCORE = 60.0
AUTO_MATCH_MARGIN = 15.0


@dataclass
class MatchCandidate:
    company: dict[str, Any]
    score: float
    method: str
    evidence: dict[str, Any]


@dataclass
class MatchDecision:
    decision: str
    candidate: MatchCandidate | None
    candidates: list[MatchCandidate]
    reason: str


def normalize_tax_code(value: str | None) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    match = re.search(r"\d{10}(?:-\d{1,5})?", value)
    if match:
        return match.group(0)
    digits = re.sub(r"\D+", "", value)
    return digits


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", value)
        if unicodedata.category(ch) != "Mn"
    )


def normalize_text(value: str | None) -> str:
    value = _strip_accents(str(value or "").casefold())
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def core_company_name(value: str | None) -> str:
    text = normalize_text(value)
    stop_words = {
        "cong", "ty", "tnhh", "trach", "nhiem", "huu", "han", "co", "phan",
        "cp", "mtv", "mot", "thanh", "vien", "limited", "company", "co",
        "ltd", "corporation", "corp", "jsc", "llc", "vietnam", "viet", "nam",
    }
    tokens = [token for token in text.split() if token not in stop_words]
    return " ".join(tokens) or text


PROVINCE_ALIASES = {
    "ho chi minh": ["ho chi minh", "hcm", "sai gon"],
    "ha noi": ["ha noi"],
    "hai phong": ["hai phong"],
    "da nang": ["da nang"],
    "can tho": ["can tho"],
    "binh duong": ["binh duong"],
    "dong nai": ["dong nai"],
    "bac ninh": ["bac ninh"],
    "long an": ["long an"],
    "ba ria vung tau": ["ba ria vung tau", "vung tau"],
    "hai duong": ["hai duong"],
    "hung yen": ["hung yen"],
    "tay ninh": ["tay ninh"],
    "vinh phuc": ["vinh phuc"],
    "ha nam": ["ha nam"],
    "thai nguyen": ["thai nguyen"],
    "bac giang": ["bac giang"],
    "thanh hoa": ["thanh hoa"],
    "nghe an": ["nghe an"],
    "binh dinh": ["binh dinh"],
    "khanh hoa": ["khanh hoa"],
    "quang nam": ["quang nam"],
    "quang ngai": ["quang ngai"],
    "lam dong": ["lam dong"],
}

_PROVINCE_LOOKUP = sorted(
    [
        (alias, canonical)
        for canonical, aliases in PROVINCE_ALIASES.items()
        for alias in aliases
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)


def extract_province_from_address(address: str | None) -> str:
    text = normalize_text(address)
    if not text:
        return ""
    for alias, canonical in _PROVINCE_LOOKUP:
        if re.search(rf"(^|\W){re.escape(alias)}(\W|$)", text):
            return canonical
    return ""


def normalize_domain(value: str | None) -> str:
    value = str(value or "").strip().casefold()
    if "@" in value:
        value = value.rsplit("@", 1)[-1]
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0].split(":", 1)[0]
    return value[4:] if value.startswith("www.") else value


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("84") and len(digits) >= 11:
        return "0" + digits[2:]
    return digits


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _candidate_rows(db: DatabaseManager, name_key: str, tax_code: str) -> list[dict[str, Any]]:
    rows_by_id: dict[int, dict[str, Any]] = {}
    if tax_code:
        for row in db.fetch_all("SELECT * FROM companies WHERE tax_code IS NOT NULL AND TRIM(tax_code) != ''"):
            if normalize_tax_code(row.get("tax_code")) == tax_code:
                rows_by_id[row["id"]] = row

    for row in db.fetch_all(
        """
        SELECT * FROM companies
        WHERE original_name_key = ?
           OR original_name_key LIKE ?
           OR LOWER(original_name) = LOWER(?)
        """,
        (name_key, f"{name_key}#duplicate-%", name_key),
    ):
        rows_by_id[row["id"]] = row

    if rows_by_id:
        placeholders = ",".join("?" * len(rows_by_id))
        contacts = db.fetch_all(
            f"""
            SELECT company_id, address, phone, email, website
            FROM extracted_contacts
            WHERE id IN (
                SELECT MAX(id)
                FROM extracted_contacts
                WHERE company_id IN ({placeholders})
                GROUP BY company_id
            )
            """,
            tuple(rows_by_id.keys()),
        )
        for contact in contacts:
            row = rows_by_id.get(contact["company_id"])
            if not row:
                continue
            for field in ("address", "phone", "email", "website"):
                if contact.get(field) and not row.get(field):
                    row[field] = contact[field]

    return list(rows_by_id.values())


def score_company_match(input_record: dict[str, Any], candidate: dict[str, Any]) -> MatchCandidate:
    input_name = input_record.get("name") or ""
    input_tax = normalize_tax_code(input_record.get("tax_code"))
    candidate_tax = normalize_tax_code(candidate.get("tax_code"))
    input_address = input_record.get("address") or ""
    candidate_address = candidate.get("address") or ""
    input_domain = normalize_domain(input_record.get("website") or input_record.get("email"))
    candidate_domain = normalize_domain(candidate.get("website") or candidate.get("email"))
    input_phone = normalize_phone(input_record.get("phone"))
    candidate_phone = normalize_phone(candidate.get("phone"))

    evidence: dict[str, Any] = {
        "input_tax_code": input_tax,
        "candidate_tax_code": candidate_tax,
        "candidate_company_id": candidate.get("id"),
        "candidate_name": candidate.get("original_name"),
        "signals": [],
    }

    if input_tax and candidate_tax:
        if input_tax == candidate_tax:
            evidence["signals"].append("tax_code_exact")
            return MatchCandidate(candidate, 100.0, "tax_code", evidence)
        evidence["signals"].append("tax_code_mismatch")
        return MatchCandidate(candidate, 0.0, "tax_code_mismatch", evidence)

    score = 0.0
    input_name_key = DatabaseManager.normalize_company_name(input_name)
    candidate_name_key = candidate.get("original_name_key") or DatabaseManager.normalize_company_name(candidate.get("original_name"))
    if candidate_name_key == input_name_key or str(candidate_name_key).startswith(f"{input_name_key}#duplicate-"):
        score += 45.0
        evidence["signals"].append("normalized_name_exact")
    else:
        name_similarity = _similarity(core_company_name(input_name), core_company_name(candidate.get("original_name")))
        name_score = round(name_similarity * 25.0, 2)
        score += name_score
        evidence["name_similarity"] = round(name_similarity, 4)
        if name_score:
            evidence["signals"].append("core_name_similarity")

    input_province = input_record.get("province") or extract_province_from_address(input_address)
    candidate_province = candidate.get("province") or extract_province_from_address(candidate_address)
    evidence["input_province"] = input_province
    evidence["candidate_province"] = candidate_province
    if input_province and candidate_province:
        if input_province == candidate_province:
            score += 15.0
            evidence["signals"].append("province_exact")
        else:
            score -= 20.0
            evidence["signals"].append("province_mismatch")

    input_address_norm = normalize_text(input_address)
    candidate_address_norm = normalize_text(candidate_address)
    address_similarity = _similarity(input_address_norm, candidate_address_norm)
    if input_address_norm and candidate_address_norm:
        evidence["address_similarity"] = round(address_similarity, 4)
        if address_similarity >= 0.9:
            score += 25.0
            evidence["signals"].append("address_high_similarity")
        elif address_similarity >= 0.75:
            score += 15.0
            evidence["signals"].append("address_medium_similarity")

    if input_domain and candidate_domain and input_domain == candidate_domain:
        score += 30.0
        evidence["signals"].append("domain_exact")

    if input_phone and candidate_phone and input_phone == candidate_phone:
        score += 25.0
        evidence["signals"].append("phone_exact")

    return MatchCandidate(candidate, max(0.0, round(score, 2)), "score", evidence)


def resolve_company_match(db: DatabaseManager, input_record: dict[str, Any]) -> MatchDecision:
    name = input_record.get("name") or ""
    name_key = DatabaseManager.normalize_company_name(name)
    tax_code = normalize_tax_code(input_record.get("tax_code"))
    candidates = [
        score_company_match(input_record, row)
        for row in _candidate_rows(db, name_key, tax_code)
    ]
    candidates.sort(key=lambda item: (-item.score, item.company["id"]))

    tax_matches = [item for item in candidates if item.method == "tax_code" and item.score == 100.0]
    if tax_matches:
        return MatchDecision("matched_by_tax_code", tax_matches[0], candidates, "tax_code_exact")

    if not candidates:
        return MatchDecision("no_match", None, [], "no_candidates")

    top = candidates[0]
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    if top.score >= AUTO_MATCH_SCORE and top.score - second_score >= AUTO_MATCH_MARGIN:
        return MatchDecision("matched_by_score", top, candidates, "high_confidence_score")

    if top.score >= MIN_CANDIDATE_SCORE or any("normalized_name_exact" in c.evidence.get("signals", []) for c in candidates):
        return MatchDecision("ambiguous", top, candidates, "insufficient_disambiguating_evidence")

    return MatchDecision("no_match", None, candidates, "low_score")


def evidence_json(candidate: MatchCandidate | None, decision: MatchDecision) -> str:
    payload = {
        "decision": decision.decision,
        "reason": decision.reason,
        "candidate_count": len(decision.candidates),
    }
    if candidate:
        payload.update(candidate.evidence)
        payload["score"] = candidate.score
        payload["method"] = candidate.method
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
