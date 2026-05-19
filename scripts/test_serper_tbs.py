"""Mini test: Check if Serper accepts tbs=ctr:CountryVN parameter."""
import os, sys, requests, json
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

API_KEY = os.getenv("SERPER_API_KEY")
URL = "https://google.serper.dev/search"

query = "point grey vietnam contact"

# Test 1: WITHOUT tbs
print("=" * 60)
print("TEST 1: WITHOUT tbs parameter")
print("=" * 60)
resp1 = requests.post(
    URL,
    headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
    json={"q": query, "gl": "vn", "hl": "vi", "num": 5},
    timeout=10
)
print(f"Status: {resp1.status_code}")
if resp1.status_code == 200:
    data1 = resp1.json()
    for i, item in enumerate(data1.get("organic", [])):
        print(f"  [{i+1}] {item.get('link', '')}")
        print(f"      {item.get('title', '')}")
else:
    print(f"Error: {resp1.text}")

print()

# Test 2: WITH tbs=ctr:CountryVN
print("=" * 60)
print("TEST 2: WITH tbs=ctr:CountryVN")
print("=" * 60)
resp2 = requests.post(
    URL,
    headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
    json={"q": query, "gl": "vn", "hl": "vi", "num": 5, "tbs": "ctr:CountryVN"},
    timeout=10
)
print(f"Status: {resp2.status_code}")
if resp2.status_code == 200:
    data2 = resp2.json()
    for i, item in enumerate(data2.get("organic", [])):
        print(f"  [{i+1}] {item.get('link', '')}")
        print(f"      {item.get('title', '')}")
else:
    print(f"Error: {resp2.text}")
    print("=> tbs parameter NOT supported by Serper. Do NOT integrate.")

# Compare
print()
print("=" * 60)
print("COMPARISON")
print("=" * 60)
if resp1.status_code == 200 and resp2.status_code == 200:
    urls1 = set(item.get("link") for item in data1.get("organic", []))
    urls2 = set(item.get("link") for item in data2.get("organic", []))
    only_in_1 = urls1 - urls2
    only_in_2 = urls2 - urls1
    print(f"Only in Test 1 (no tbs): {only_in_1 or 'none'}")
    print(f"Only in Test 2 (with tbs): {only_in_2 or 'none'}")
    vn_count_1 = sum(1 for u in urls1 if u and '.vn' in u)
    vn_count_2 = sum(1 for u in urls2 if u and '.vn' in u)
    print(f".vn domains: Test 1 = {vn_count_1}, Test 2 = {vn_count_2}")
elif resp2.status_code != 200:
    print("=> CONCLUSION: tbs parameter causes error. Do NOT use.")
