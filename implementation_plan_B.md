# 📞 Company Contact Extraction Pipeline (Vietnam-focused)

## 🎯 Objective
Extract:
- Phone number (priority: Admin > HR > General)
- Email (especially HR)
- Source (website / facebook / linkedin)

From a list of 5000–6000 companies.

---

## 🧠 I. Overall Pipeline

```
INPUT: Company list

FOR EACH company:
    1. Query Builder
    2. Search Layer
    3. URL Classification
    4. Website Pipeline (main)
    5. Social Pipeline (support)
    6. Extraction + Scoring
    7. Merge + Deduplicate
    8. Fallback if needed

OUTPUT: structured contact data
```

---

## 🔍 II. Query Builder

### Vietnamese + English mixed queries

```python
def build_queries(company):
    return [
        # Vietnamese (priority)
        f"{company} liên hệ",
        f"{company} số điện thoại",
        f"{company} tuyển dụng",
        f"{company} hành chính nhân sự",

        # English
        f"{company} contact",
        f"{company} phone",
        f"{company} HR",

        # Social discovery
        f"{company} tuyển dụng facebook",
        f"{company} hr tuyển dụng",
    ]
```

---

## 🌐 III. Search Layer

```python
def search_all(query):
    results = firecrawl_search(query)

    if len(results) < 3:
        results += serper_search(query)

    return results
```

---

## 🧠 IV. URL Classification

```python
def classify_url(url):
    if "facebook.com" in url:
        return "facebook"
    elif "linkedin.com" in url:
        return "linkedin"
    else:
        return "website"
```

---

## 🌍 V. Website Pipeline (CORE)

### Step 1: Extract base domain
Example:
```
https://abc.com/news → https://abc.com
```

### Step 2: Generate contact pages

```python
CONTACT_PATHS = [
    "/contact", "/lien-he",
    "/about", "/gioi-thieu",
    "/tuyen-dung", "/careers"
]
```

### Step 3: Crawl selectively

```python
for path in CONTACT_PATHS:
    url = base_url + path
    scrape(url)
```

### ❗ Do NOT crawl:
- /blog
- /news
- /products

---

## 📱 VI. Social Pipeline

### 🔵 LinkedIn (for website discovery)

Example:
```
linkedin.com/company/abc
```

```python
website = extract_website(text)
```

→ Return to Website Pipeline

---

### 🔴 Facebook Processing

#### Step 1: Classify URL

```python
def classify_facebook_url(url):
    if "/posts/" in url:
        return "post"
    elif "/groups/" in url:
        return "group"
    else:
        return "page"
```

#### Step 2: Filter valid posts

```python
VALID_FB_PATTERNS = [
    "/posts/",
    "/groups/",
    "/permalink/",
    "story_fbid"
]

INVALID_FB_PATTERNS = [
    "/photo",
    "/videos/",
    "/reel/",
    "/media"
]

def is_valid_fb_post(url):
    if any(p in url for p in VALID_FB_PATTERNS):
        if not any(p in url for p in INVALID_FB_PATTERNS):
            return True
    return False
```

#### Step 3: Context-based filtering

```python
def should_keep_fb_post(url, query):
    if not is_valid_fb_post(url):
        return False

    keywords = ["tuyển dụng", "hr", "nhân sự"]

    return any(k in query.lower() for k in keywords)
```

---

## 🧠 VII. Extraction Engine

### Phone extraction

```python
import re
def extract_phone(text):
    return re.findall(r'(\+?\d[\d\s\-]{8,})', text)
```

### Email extraction

```python
def extract_email(text):
    return re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
```

---

## 🧮 VIII. Scoring System

### Priority
```
ADMIN > HR > GENERAL
```

### Keyword mapping

```python
ADMIN = ["hành chính", "admin", "hcns"]
HR = ["nhân sự", "hr", "tuyển dụng"]
GENERAL = ["liên hệ", "contact", "hotline"]
```

### Scoring logic

```python
def score_contact(text):
    text = text.lower()

    if any(k in text for k in ADMIN):
        return 10
    elif any(k in text for k in HR):
        return 7
    elif any(k in text for k in GENERAL):
        return 3
    return 1
```

---

## 🔁 IX. Fallback Engine

### Trigger fallback

```python
if not found_phone:
    run_social_pipeline()
```

### Fallback priority

```
1. Website contact page
2. Facebook job post
3. LinkedIn → website
4. Any phone on homepage
```

---

## 🔗 X. Deduplication

```python
def dedupe(results):
    seen = set()
    final = []

    for r in results:
        if r["phone"] not in seen:
            seen.add(r["phone"])
            final.append(r)

    return final
```

---

## 📦 XI. Output Format

```json
{
  "company": "ABC Corp",
  "phone": "0909xxxx",
  "email": "hr@abc.com",
  "type": "hr",
  "source": "facebook_post"
}
```

---

## 🚀 XII. Full Flow Summary

```
Company
  ↓
Build queries
  ↓
Search
  ↓
Classify URL
  ↓
IF website → crawl contact pages
IF linkedin → extract website → back to website
IF facebook:
    → check URL pattern
    → if valid post → extract
  ↓
Extract phone/email
  ↓
Score (admin > hr > general)
  ↓
Merge
  ↓
Fallback if needed
```

---

## 💡 Key Insights

- Website → stable but generic  
- Facebook posts → real HR contacts (high value)  
- LinkedIn → best for finding official website  

---

## ✅ Result

Pipeline ensures:
- No missed contacts  
- Minimal crawling cost  
- High-quality prioritization  
