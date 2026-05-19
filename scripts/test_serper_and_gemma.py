import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def test_serper(query: str):
    print(f"--- SERPER TEST ---")
    print(f"Query: {query}")
    url = "https://google.serper.dev/search"
    payload = json.dumps({
      "q": query,
      "gl": "vn",
      "hl": "vi",
      "num": 10
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

def test_openrouter(content: str, model: str):
    print(f"\n--- OPENROUTER TEST ---")
    print(f"Model: {model}")
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    prompt = f"""
    Trích xuất thông tin liên hệ từ văn bản sau và trả về định dạng JSON nghiêm ngặt.
    Chỉ trả về JSON với các trường: phone, email, address. Nếu không có thì để null.
    
    Văn bản:
    {content}
    """
    
    payload = json.dumps({
      "model": model,
      "messages": [
        {"role": "user", "content": prompt}
      ],
      "temperature": 0.1,
      "response_format": {"type": "json_object"}
    })
    
    headers = {
      'Authorization': f'Bearer {OPENROUTER_API_KEY}',
      'Content-Type': 'application/json'
    }
    
    response = requests.post(url, headers=headers, data=payload)
    print(f"OpenRouter Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if "choices" in data:
            ai_content = data["choices"][0]["message"]["content"]
            print(f"AI Response:\n{ai_content}")
            try:
                parsed = json.loads(ai_content)
                print(f"Parsed JSON: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
            except json.JSONDecodeError:
                print("Failed to parse JSON response!")
        else:
            print(f"Unexpected response structure: {data}")
    else:
        print(f"OpenRouter Error: {response.text}")

if __name__ == "__main__":
    company_vn = "Công ty TNHH Logistics Quốc tế Master Việt Nam"
    company_en = "Master Vietnam International Logistics Co., Ltd"
    test_query = f'"{company_vn}" OR "{company_en}"'
    
    snippet = test_serper(test_query)
    
    if snippet:
        # User requested: gemini gemma4 31b it
        model_name = "google/gemma-4-31b-it:free"
        test_openrouter(snippet, model_name)
    else:
        print("No content to test with OpenRouter.")
