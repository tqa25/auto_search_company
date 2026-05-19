import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("FIRECRAWL_API_KEY")
if not api_key:
    print("FIRECRAWL_API_KEY is not set in .env")
    exit(1)

print(f"Testing Firecrawl API Key: {api_key[:5]}...{api_key[-4:] if len(api_key) > 9 else ''}")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# The simplest endpoint is a GET request to the /v1/team or just trying to scrape a tiny url
# For Firecrawl v1, let's do a simple scrape request to example.com
payload = {
    "url": "https://example.com"
}

try:
    response = requests.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=payload, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    if response.status_code == 200:
        print("\n✅ API Key is VALID!")
    elif response.status_code == 401:
        print("\n❌ API Key is INVALID (Unauthorized)!")
    else:
        print("\n⚠️ API Key might have issues or rate limits.")
except Exception as e:
    print(f"Error connecting to Firecrawl API: {e}")
