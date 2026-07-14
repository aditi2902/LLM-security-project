import re
import sys
import os
import json
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import call_llm
from agents.memory_storage import get_all_memories

def run_retrieval_rule_engine(memory: dict) -> bool:
    """Checks memory for TTL expiration and obvious tampering."""
    # Check TTL
    creation_time = memory.get("creation_timestamp", 0)
    ttl = memory.get("ttl", 0)
    if time.time() > creation_time + ttl:
        return False # Expired
        
    content = memory.get("content", "")
    malicious_patterns = [
        r"(?i)ignore previous instructions",
        r"(?i)system override",
        r"(?i)forget everything"
    ]
    
    for pattern in malicious_patterns:
        if re.search(pattern, content):
            return False # Tampered
            
    return True

def verify_trust(memory: dict) -> bool:
    """Check if the memory's trust score is still acceptable."""
    # Trust decay could be implemented here
    trust_score = memory.get("trust_score", 0)
    risk = memory.get("risk", 100)
    
    if trust_score < 50 or risk > 40:
        return False
    return True

def retrieve_and_validate_memories(current_context: str) -> list:
    """
    Retrieves all memories, filters them by relevance (word overlap),
    and validates them instantly using the deterministic Rule Engine.
    (LLM evaluation has been removed to reduce latency and API cost, 
    as memories are already vetted during the write phase).
    """
    all_memories = get_all_memories()
    candidate_memories = []
    
    # Extract query words for simple keyword filtering
    query_words = set(re.findall(r'\w+', current_context.lower()))
    stop_words = {"what", "is", "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "at", "by", "you", "me", "how", "can"}
    meaningful_query_words = query_words - stop_words

    for mem in all_memories:
        # 1. Rule Engine (TTL + Tamper check)
        if not run_retrieval_rule_engine(mem):
            continue
            
        # 2. Trust Verification
        if not verify_trust(mem):
            continue
            
        # 3. Quick Relevance Filter (text overlap)
        content = mem.get("content", "")
        content_words = set(re.findall(r'\w+', content.lower()))
        overlap = meaningful_query_words.intersection(content_words)
        
        # If there's keyword overlap, or if it's a short conversational query, it is relevant
        if overlap or len(meaningful_query_words) == 0:
            candidate_memories.append(mem.get("content"))

    # Limit to top 3 candidates to keep context window small
    return candidate_memories[:3]
