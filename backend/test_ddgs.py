from duckduckgo_search import DDGS
with DDGS() as ddgs:
    results = list(ddgs.text("Who is president of India", max_results=5, backend="html"))
    print(results)
