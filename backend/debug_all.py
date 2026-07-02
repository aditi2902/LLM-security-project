import asyncio
from app import query_endpoint, QueryRequest
import json
from llm import call_llm

print("--- Testing Ollama directly ---")
try:
    res = call_llm("Say hello", model="qwen3:8b")
    print(f"Ollama direct response: {res[:50]}")
except Exception as e:
    print(f"Ollama direct failed: {e}")

print("\n--- Testing Pipeline ---")
async def main():
    try:
        req = QueryRequest(query="What is AI?")
        res = await query_endpoint(req)
        print("Pipeline Result:")
        print(json.dumps(res, indent=2))
    except Exception as e:
        print("Pipeline Exception:", e)

asyncio.run(main())
