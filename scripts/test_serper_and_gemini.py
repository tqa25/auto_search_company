import os
import json
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def test_serper(query: str, num_results: int = 100):
    print(f"--- SERPER TEST ---")
    print(f"Query: {query}")
    print(f"Num Results Limit: {num_results}")
    url = "https://google.serper.dev/search"
    payload = json.dumps({
      "q": query,
      "gl": "vn",
      "hl": "vi",
      "num": num_results
    })
    headers = {
      'X-API-KEY': SERPER_API_KEY,
      'Content-Type': 'application/json'
    }
    
    response = requests.post(url, headers=headers, data=payload)
    print(f"Serper Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        organic = data.get("organic", [])
        print(f"Found {len(organic)} results.")
        if organic:
            first_result = organic[0]
            print(f"First result: {first_result.get('title')}")
            print(f"Snippet: {first_result.get('snippet')}")
            return first_result.get('snippet')
    else:
        print(f"Serper Error: {response.text}")
    return None

def test_gemini_gemma(content: str, model_name: str):
    print(f"\n--- GEMINI API (Gemma Model) TEST ---")
    print(f"Model: {model_name}")
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Trích xuất thông tin liên hệ từ văn bản sau và trả về định dạng JSON nghiêm ngặt.
    Chỉ trả về JSON với các trường: phone, email, address. Nếu không có thì để null.
    
    Văn bản:
    {content}
    """
    
    print("Calling Gemini API...")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        print(f"AI Response:\n{response.text}")
        try:
            parsed = json.loads(response.text)
            print(f"Parsed JSON: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            print("Failed to parse JSON response!")
    except Exception as e:
        print(f"Gemini API Error: {e}")

if __name__ == "__main__":
    # Test for company using Vietnamese/English OR logic
    company_vn = "Công ty TNHH Logistics Quốc tế Master Việt Nam"
    company_en = "Master Vietnam International Logistics Co., Ltd"
    test_query = f'"{company_vn}" OR "{company_en}"'
    
    # 1. Run Serper with limit = 100
    snippet = test_serper(test_query, num_results=100)
    
    if not snippet:
        print("\n--- FALLBACK FOR AI EXTRACT ---")
        print("Because Serper failed, using a mock snippet to test Gemini Gemma 4 31b IT API...")
        snippet = "Công ty Master Vietnam. Địa chỉ: 123 Đường Hải Phòng, Việt Nam. Số điện thoại: 0987654321. Email: contact@mastervietnam.com."
        
    # 2. Run Gemini Extraction with gemma4 31b
    # Use gemma4 31b as requested
    test_gemini_gemma(snippet, "models/gemma-4-31b-it")
