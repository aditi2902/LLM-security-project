import requests
import os
from dotenv import load_dotenv

load_dotenv()

def search_web(query):
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("Warning: SERPER_API_KEY not found in .env. Search will fail.")
        return []
        
    url = "https://google.serper.dev/search"
    payload = {"q": query, "num": 5}
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(url, headers=headers, json=payload, verify=False, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("organic", []):
            results.append({
                "href": item.get("link"),
                "title": item.get("title"),
                "body": item.get("snippet")
            })
        return results
    except Exception as e:
        print(f"Serper Search Error: {e}")
        return []