import difflib

def get_best_partial_ratio(query, text):
    if not query or not text: return 0.0
    if query in text: return 1.0
    max_r = 0.0
    for i in range(len(text) - len(query) + 1):
        window = text[i:i+len(query)]
        r = difflib.SequenceMatcher(None, query, window).ratio()
        if r > max_r:
            max_r = r
    if len(text) < len(query):
        max_r = max(max_r, difflib.SequenceMatcher(None, query, text).ratio())
    return max_r

print(get_best_partial_ratio("samsung", "samsung.com"))
print(get_best_partial_ratio("samsung", "cong ty samsung thai nguyen"))
print(get_best_partial_ratio("samsung", "sam sung"))
print(get_best_partial_ratio("samsung electronics", "samsung electric"))
