import requests
import re

def search_web(query):
    """Searches the web using Wikipedia API (reliable, free, no API key required)."""
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": "",
            "format": "json",
            "srlimit": 3
        }
        headers = {
            "User-Agent": "TrustLens/1.0 (Contact: trustlens@example.com)"
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("query", {}).get("search", []):
            # Clean HTML from snippet
            clean_snippet = re.sub('<[^<]+?>', '', item.get("snippet", ""))
            title = item.get("title", "")
            results.append({
                "href": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "title": title,
                "body": clean_snippet
            })
        return results
    except Exception as e:
        print(f"Wikipedia Search Error: {e}")
        return []