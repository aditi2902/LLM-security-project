import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import call_llm

def determine_intent(query: str) -> str:
    """
    Determines if the query is a CHAT (conversational/personal command)
    or WEB (informational query, test file, URL).
    """
    query_lower = query.lower().strip()
    
    # 1. Explicit WEB intent
    if query_lower.startswith("test:") or query_lower.startswith("http"):
        return "WEB"
        
    # 2. Hardcoded CHAT intent based on simple keywords
    chat_keywords = ["hello", "hi ", "my name is", "remember", "what is my", "who am i", "favorite"]
    if any(k in query_lower for k in chat_keywords):
        return "CHAT"
        
    # 3. Default to WEB
    return "WEB"
