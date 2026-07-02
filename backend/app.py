from fastapi import FastAPI
from pydantic import BaseModel
from agents.prompt_security import evaluate_user_prompt
from agents.search_agent import execute_search_agent
from agents.trust_analyzer import analyze_content
from agents.sanitizer import sanitize
from agents.response_validator import validate_response
from agents.memory_write_validator import validate_and_store_memory
from agents.memory_retrieval_validator import retrieve_and_validate_memories
from agents.intent_router import determine_intent
from llm import call_llm
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor
from agents.memory_storage import add_memory

app = FastAPI(title="Content Trust Layer MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

@app.post("/query")
async def query_endpoint(req: QueryRequest):
    # Step 1: User Prompt Security Agent (Block / Allow)
    security_check = evaluate_user_prompt(req.query)
    if not security_check.get("safe", True):
        return {
            "blocked": True,
            "prompt_security": security_check,
            "reason": security_check.get("reason", "Malicious prompt detected."),
            "answer": None
        }
    
    # Step 1.5: Determine Intent (WEB vs CHAT)
    intent = determine_intent(req.query)
    
    if intent == "WEB":
        # Step 2: Search Agent & Web Retrieval
        combined_content = execute_search_agent(req.query)
        
        # Step 3: Retrieved Content Analyzer
        analyzed_data = analyze_content(combined_content)
        risk_score = analyzed_data.get("risk_score", 0)
        manipulation = analyzed_data.get("detected_attacks", [])
        attack_detected = not analyzed_data.get("safe", True)
        
        # Step 4: Content Sanitizer
        trusted_content = sanitize(analyzed_data, combined_content)
    else:
        # CHAT Intent: Skip web search and content analysis
        combined_content = ""
        analyzed_data = {"safe": True}
        risk_score = 0
        manipulation = []
        attack_detected = False
        trusted_content = ""
    
    # Step 4.5: Memory Retrieval Validator
    safe_memories = retrieve_and_validate_memories(req.query)
    memory_context = "\n".join(safe_memories) if safe_memories else "No relevant memories found."
    
    # Step 5: Answer LLM
    if intent == "WEB":
        answer_prompt = f"""
Answer the following question:
{req.query}

First, attempt to answer using the following trusted web content:
{trusted_content}

Consider the following trusted long-term memories for context:
{memory_context}

If the trusted content does not contain the answer or is empty, you may answer using your own internal knowledge. However, you must be extremely accurate and factual. If you are not 100% certain of the factual accuracy, you must decline to answer by stating: 'I cannot verify the accuracy of this information.'
"""
    else:
        answer_prompt = f"""
You are a helpful AI Assistant.
Respond to the user's conversational input or command.

User Input:
{req.query}

Consider the following trusted long-term memories for context:
{memory_context}
"""
        
    generated_answer = call_llm(answer_prompt, model="gemini", format_json=False)
    
    # Step 6 & 7: Parallel Post-Generation Validation (Massive Speedup)
    memory_write_results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Launch all three DeepSeek LLM tasks simultaneously
        future_validation = executor.submit(validate_response, generated_answer)
        future_user_mem = executor.submit(validate_and_store_memory, req.query, "user_prompt", "user_input", False)
        future_ai_mem = executor.submit(validate_and_store_memory, generated_answer, "conversation_answer", "llm_generation", False)
        
        # Wait for them to finish
        validation_result = future_validation.result()
        user_memory_res = future_user_mem.result()
        ai_memory_res = future_ai_mem.result()
        
    # Process Response Validation
    if not validation_result.get("safe", True):
        generated_answer = "The generated answer was blocked due to security policies: " + validation_result.get("reason", "Unknown reason.")
        
    # Process User Memory Write (Safe to store immediately if rules allow)
    if user_memory_res.get("action") in ["Store", "Store with TTL"]:
        add_memory(user_memory_res["memory"])
    memory_write_results.append({"type": "User Input", **user_memory_res})
    
    # Process AI Memory Write (Only store if the Egress wasn't blocked!)
    if validation_result.get("safe", True):
        if ai_memory_res.get("action") in ["Store", "Store with TTL"]:
            add_memory(ai_memory_res["memory"])
        memory_write_results.append({"type": "AI Answer", **ai_memory_res})
    else:
        memory_write_results.append({"type": "AI Answer", "action": "Reject", "reason": "Answer was blocked."})
        
    return {
        "intent": intent,
        "blocked": False,
        "prompt_security": security_check,
        "risk_score": risk_score,
        "attack_detected": attack_detected,
        "removed_content": manipulation,
        "raw_content": combined_content,
        "sanitized_content": trusted_content,
        "answer": generated_answer,
        "validation_result": validation_result,
        "memory_write": memory_write_results
    }

if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
