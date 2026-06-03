import urllib.parse

def normalize_url(url: str) -> str:
    """
    Normalize URL before saving: 
    - resolve www.
    - remove trailing slash
    - strip tracking params (utm_*, fbclid, etc.)
    """
    if not url: return ""
    try:
        parsed = urllib.parse.urlparse(url)
        # Drop tracking params
        query_params = urllib.parse.parse_qsl(parsed.query)
        clean_params = [(k, v) for k, v in query_params if not k.startswith("utm_") and not k.startswith("fbclid")]
        
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
            
        path = parsed.path
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]
            
        clean_query = urllib.parse.urlencode(clean_params)
        
        # We don't want to preserve trailing slashes or empty queries
        normalized = urllib.parse.urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, clean_query, parsed.fragment))
        return normalized
    except Exception:
        return url
