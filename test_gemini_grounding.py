import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

print("Starting script...")
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("NO API KEY!")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = """
Tìm thông tin liên hệ của công ty "CIRCO SERVICES JOINT-STOCK COMPANY" tại Việt Nam.

Tôi cần bạn trả về ĐỊNH DẠNG JSON với các trường sau (nếu không có thì để null):
{
  "core_name": "Tên định danh ngắn gọn (ví dụ: CIRCO)",
  "core_name_vi": "Tên tiếng Việt đầy đủ",
  "abbreviation": "Tên viết tắt (ví dụ: CIRCO)",
  "noise_tokens": ["các", "từ", "nhiễu", "không", "nên", "dùng", "khi", "so", "sánh", "chuỗi"],
  "address": "Địa chỉ đầy đủ",
  "phone": "Số điện thoại",
  "email": "Địa chỉ email",
  "website": "URL website chính thức",
  "tax_code": "Mã số thuế",
  "representative": "Người đại diện pháp luật",
  "confidence": 0.95
}

Chỉ trả về JSON thuần túy, không có block markdown (```json).
"""

print("Initializing model...")
try:
    print("Generating content with models/gemma-4-31b-it and Google Search Grounding...")
    response = client.models.generate_content(
        model='models/gemma-4-31b-it',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.0
        )
    )
    
    print("\n--- RESPONSE ---")
    print(response.text)
    
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        print("\n--- TOKEN USAGE ---")
        print(f"Input Tokens (Prompt): {response.usage_metadata.prompt_token_count}")
        print(f"Output Tokens (Candidates): {response.usage_metadata.candidates_token_count}")
        print(f"Total Tokens: {response.usage_metadata.total_token_count}")

    # Extract search metadata
    if response.candidates and response.candidates[0].grounding_metadata:
        metadata = response.candidates[0].grounding_metadata
        if metadata.grounding_chunks:
            print("\n--- GROUNDING SOURCES ---")
            for chunk in metadata.grounding_chunks:
                if chunk.web:
                    print(f"- Source: {chunk.web.title} ({chunk.web.uri})")
                    
except Exception as e:
    print(f"Error: {e}")
