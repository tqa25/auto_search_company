import requests
import os
from dotenv import load_dotenv

load_dotenv()

def check_serper():
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return "No Serper API Key found."
    try:
        resp = requests.get(
            "https://google.serper.dev/account",
            headers={"X-API-KEY": api_key}
        )
        if resp.status_code == 200:
            return resp.json()
        return f"Error Serper: {resp.status_code} - {resp.text}"
    except Exception as e:
        return f"Exception Serper: {e}"

def check_firecrawl():
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return "No Firecrawl API Key found."
    try:
        # Firecrawl v1 usage endpoint
        resp = requests.get(
            "https://api.firecrawl.dev/v1/team/credit-usage",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        if resp.status_code == 200:
            return resp.json()
        return f"Error Firecrawl: {resp.status_code} - {resp.text}"
    except Exception as e:
        return f"Exception Firecrawl: {e}"

if __name__ == "__main__":
    print("--- SERPER USAGE ---")
    print(check_serper())
    print("\n--- FIRECRAWL USAGE ---")
    print(check_firecrawl())
