import sys
import os
sys.path.append(os.getcwd())
from src.filter_module import LinkFilter
import unicodedata

def _remove_accents(text: str) -> str:
    if not text: return ""
    text = text.replace('đ', 'd').replace('Đ', 'D')
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')

lf = LinkFilter(None, None)

company_name = "HYCO4 - JSC"
normalized_company, company_abbrev = lf._normalize_company_name(company_name)

print(f"Company Name: {company_name}")
print(f"Normalized: '{normalized_company}'")
print(f"Abbrev: '{company_abbrev}'")

title = "[TL4] 第4灌漑建設 基本情報 - Viet-kabu.com"
normalized_title = _remove_accents(title).lower()
print(f"Normalized Title: '{normalized_title}'")

if (normalized_company and normalized_company in normalized_title):
    print("Match 1: normalized_company in normalized_title")
elif (company_abbrev and company_abbrev in normalized_title):
    print("Match 2: company_abbrev in normalized_title")
else:
    print("NO TITLE MATCH")

domain = "viet-kabu.com"
normalized_domain = lf._normalize_domain(domain)
print(f"Normalized domain: '{normalized_domain}'")

if lf._check_name_match(normalized_domain, normalized_company, company_abbrev):
    print("Match 3: _check_name_match in domain")
else:
    print("NO DOMAIN MATCH")

