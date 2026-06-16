#!/usr/bin/env python3
"""Audit extracted masothue phones whose page MST differs from the target company MST.

This script is read-only: it opens SQLite with mode=ro and writes findings to CSV.
"""

import argparse
import csv
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote, urlparse


CSV_COLUMNS = [
    "company_id",
    "company_name",
    "target_mst",
    "page_mst",
    "phone",
    "source_url",
    "mismatch_reason",
]


def normalize_tax_code(value):
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value).strip()).replace("–", "-").replace("—", "-")


def is_masothue_source(source_type, source_url):
    if source_type == "masothue":
        return True
    parsed = urlparse(source_url or "")
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain == "masothue.com" or domain.endswith(".masothue.com")


def extract_masothue_tax_code_from_url(source_url):
    parsed = urlparse(source_url or "")
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not (domain == "masothue.com" or domain.endswith(".masothue.com")):
        return ""
    match = re.search(r"(?<!\d)(\d{4,14}(?:-\d{1,5})?)(?!\d)", parsed.path or "")
    return normalize_tax_code(match.group(1)) if match else ""


def extract_tax_code_from_text(text):
    if not text:
        return ""
    patterns = [
        r"(?:mã\s*số\s*thuế|ma\s*so\s*thue|mst|tax\s*code)\s*[:：]?\s*(\d{4,14}(?:-\d{1,5})?)",
        r"(?<!\d)(\d{10}(?:-\d{3})?)(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_tax_code(match.group(1))
    return ""


def connect_read_only(db_path):
    absolute_path = Path(db_path).resolve()
    uri = f"file:{quote(str(absolute_path))}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def audit(db_path, output_path):
    rows_written = 0
    with connect_read_only(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                c.id AS company_id,
                c.original_name AS company_name,
                c.tax_code AS target_mst,
                ec.phone AS phone,
                ec.source_url AS contact_source_url,
                ec.source_type AS contact_source_type,
                sp.url AS page_url,
                sp.source_type AS page_source_type,
                sp.markdown_content AS markdown_content
            FROM extracted_contacts ec
            JOIN companies c ON c.id = ec.company_id
            LEFT JOIN scraped_pages sp ON sp.id = ec.scraped_page_id
            WHERE ec.phone IS NOT NULL
              AND TRIM(ec.phone) != ''
              AND c.tax_code IS NOT NULL
              AND TRIM(c.tax_code) != ''
            """
        )

        with open(output_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()

            for row in rows:
                source_url = row["contact_source_url"] or row["page_url"] or ""
                source_type = row["contact_source_type"] or row["page_source_type"] or ""
                if not is_masothue_source(source_type, source_url):
                    continue

                target_mst = normalize_tax_code(row["target_mst"])
                page_mst = extract_masothue_tax_code_from_url(source_url) or extract_tax_code_from_text(row["markdown_content"])
                if not target_mst or not page_mst or page_mst == target_mst:
                    continue

                writer.writerow(
                    {
                        "company_id": row["company_id"],
                        "company_name": row["company_name"],
                        "target_mst": target_mst,
                        "page_mst": page_mst,
                        "phone": row["phone"],
                        "source_url": source_url,
                        "mismatch_reason": f"masothue_tax_mismatch: target_mst={target_mst}, page_mst={page_mst}",
                    }
                )
                rows_written += 1

    return rows_written


def main():
    parser = argparse.ArgumentParser(description="Audit old masothue MST mismatches without mutating the database.")
    parser.add_argument("--db", default="data/company_data.db", help="SQLite DB path. Default: data/company_data.db")
    parser.add_argument("--output", default="masothue_mismatch_audit.csv", help="Output CSV path.")
    args = parser.parse_args()

    rows_written = audit(args.db, args.output)
    print(f"Wrote {rows_written} mismatch rows to {args.output}")


if __name__ == "__main__":
    main()
