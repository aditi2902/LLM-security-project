import requests
from bs4 import BeautifulSoup

def extract_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        html = requests.get(url, headers=headers, timeout=3).text
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator='\n', strip=True)
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return ""
