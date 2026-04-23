"""
Dictionary containing versions of extraction prompts for A/B testing and history tracking.
"""

EXTRACTION_PROMPTS = {
    "v1": {
        "created_at": "2026-04-16",
        "changelog": "Initial prompt design from Phase 3 plan",
        "template": """
Please extract the following fields exactly as they appear in the provided document:
- address: Full address including district, province/city
- phone: Telephone numbers (can be multiple, separated by commas)
- email: Email addresses (can be multiple, separated by commas)
- website: Official website URL
- fax: Fax number
- representative: Name of the representative / Director / CEO

Important instructions:
1. Pay special attention to Vietnamese text.
2. Distinguish between landlines and mobile phones. Do not confuse advertising hotlines with main contact phones.
3. The address must be the head office/office address, not a warehouse address.
4. Output must be purely JSON without markdown code blocks.
5. If a field is not found, set its value to null.
6. Add a "confidence" field ranging from 0.0 to 1.0 to indicate your self-assessed reliability.

Content:
{markdown_content}
"""
    }
}
