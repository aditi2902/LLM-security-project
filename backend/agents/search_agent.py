from retrieval.search import search_web
from retrieval.scraper import extract_text
import os

def execute_search_agent(query: str) -> str:
    """
    Uses Web Retrieval to get raw content for the query.
    Returns combined raw scraped text.
    If the query starts with 'test:', it loads the local test file from the dataset directory instead.
    """
    if query.lower().startswith("test:"):
        filename = query.split(":", 1)[1].strip()
        base_dataset_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset")
        filepath = os.path.join(base_dataset_dir, filename)
        
        # Check direct or recursive file existence
        if not os.path.exists(filepath):
            found_path = None
            for root, _, files in os.walk(base_dataset_dir):
                for file in files:
                    # Match exact filename, or match suffix to handle indexed files (e.g. contradictory_information.html -> 08_contradictory_information.html)
                    if file.lower() == filename.lower() or file.lower().endswith(filename.lower()):
                        found_path = os.path.join(root, file)
                        break
                if found_path:
                    filepath = found_path
                    break
                    
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return f"[Source: Local Test File - {os.path.basename(filepath)}]\n{content}"
        else:
            return f"[Source: Error]\nTest file '{filename}' not found recursively in dataset directory."

    if query.lower().startswith("http"):
        url = query.strip()
        text = extract_text(url)
        return f"[Source: {url}]\n{text[:4000]}"

    search_results = search_web(query)
    scraped_texts = []
    for res in search_results:
        url = res.get('href')
        if url:
            text = extract_text(url)
            if not text.strip():
                # Fallback to the snippet if scraping fails or blocks us
                text = res.get('body', '')
            # Limit text length and format with source URL
            formatted_text = f"[Source: {url}]\n{text[:2000]}"
            scraped_texts.append(formatted_text)
            
    return "\n\n---\n\n".join(scraped_texts)
