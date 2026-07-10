from fastapi import FastAPI, Query, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
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
from agents.red_team import generate_and_test_attacks
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import (
    init_db, db_log_trust_event, db_get_overview,
    db_get_attacks, db_get_or_set_suggestions,
    db_get_threat_heatmap_data, db_get_pending_rules,
    db_approve_rule, db_add_learned_rule, db_get_learned_rules
)
import json, os, time, random

GEOLOCATIONS = [
    {"ip": "198.51.100.42", "country": "United States", "country_code": "US", "latitude": 37.7749, "longitude": -122.4194},
    {"ip": "81.209.155.10", "country": "Germany", "country_code": "DE", "latitude": 50.1109, "longitude": 8.6821},
    {"ip": "220.181.108.5", "country": "China", "country_code": "CN", "latitude": 31.2304, "longitude": 121.4737},
    {"ip": "1.120.0.0", "country": "Australia", "country_code": "AU", "latitude": -33.8688, "longitude": 151.2093},
    {"ip": "191.240.0.0", "country": "Brazil", "country_code": "BR", "latitude": -23.5505, "longitude": -46.6333},
    {"ip": "102.89.0.0", "country": "Nigeria", "country_code": "NG", "latitude": 6.5244, "longitude": 3.3792},
    {"ip": "82.165.0.0", "country": "United Kingdom", "country_code": "GB", "latitude": 51.5074, "longitude": -0.1278},
    {"ip": "118.200.0.0", "country": "Singapore", "country_code": "SG", "latitude": 1.3521, "longitude": 103.8198},
    {"ip": "103.21.124.0", "country": "India", "country_code": "IN", "latitude": 19.0760, "longitude": 72.8777},
    {"ip": "24.48.0.1", "country": "Canada", "country_code": "CA", "latitude": 43.6532, "longitude": -79.3832},
]

app = FastAPI(title="TrustLens — AI Security Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Scheduler Setup ---
scheduler = BackgroundScheduler()

def scheduled_red_team_job():
    print("Running scheduled Red Team Attack Generator...")
    generate_and_test_attacks(num_attacks=3)

scheduler.add_job(
    scheduled_red_team_job,
    trigger=IntervalTrigger(hours=8),
    id="red_team_job",
    replace_existing=True,
)

@app.on_event("startup")
def startup():
    init_db()           # Create SQLite tables on first run
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()

# ──────────────────────────────────────────────────────────────────────────────
# Shared trust pipeline — reused by both /query and the proxy
# ──────────────────────────────────────────────────────────────────────────────

def _run_trust_pipeline(prompt: str, source: str = "ui", model: str = "gemini") -> dict:
    """
    Full TrustLens pipeline: ingress → intent → web/chat → egress → memory.
    Returns the same dict shape used by /query.
    """
    t_start = time.time()
    geo = random.choice(GEOLOCATIONS)

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_security = executor.submit(evaluate_user_prompt, prompt)
        future_intent   = executor.submit(determine_intent, prompt)
        future_memories = executor.submit(retrieve_and_validate_memories, prompt)
        future_user_mem = executor.submit(validate_and_store_memory, prompt, "user_prompt", "user_input", False)

        security_check  = future_security.result()
        user_memory_res = future_user_mem.result()

        memory_write_results = []
        for mem in user_memory_res:
            if mem.get("action") in ["Store", "Store with TTL"]:
                add_memory(mem["memory"])
            memory_write_results.append({"type": "User Input", **mem})

        if not security_check.get("safe", True):
            latency = int((time.time() - t_start) * 1000)
            db_log_trust_event(
                raw_prompt=prompt, source=source,
                ingress_safe=False,
                ingress_reason=security_check.get("reason"),
                ingress_risk=security_check.get("risk_score", 0),
                attack_type=security_check.get("attack_type"),
                blocked=True, model_used=model, latency_ms=latency,
                client_ip=geo["ip"], country=geo["country"], country_code=geo["country_code"],
                latitude=geo["latitude"], longitude=geo["longitude"],
                vulnerability_type=security_check.get("attack_type"),
            )
            return {
                "blocked": True,
                "prompt_security": security_check,
                "reason": security_check.get("reason", "Malicious prompt detected."),
                "answer": None,
                "memory_write": memory_write_results,
                "intent": None,
            }

        intent      = future_intent.result()
        safe_memories = future_memories.result()

    memory_context = "\n".join(safe_memories) if safe_memories else "No relevant memories found."

    if intent == "WEB":
        combined_content = execute_search_agent(prompt)
        if not combined_content.strip():
            analyzed_data = {"safe": True, "risk_score": 0, "detected_attacks": []}
        else:
            analyzed_data    = analyze_content(combined_content)
        risk_score       = analyzed_data.get("risk_score", 0)
        manipulation     = analyzed_data.get("detected_attacks", [])
        attack_detected  = not analyzed_data.get("safe", True)
        trusted_content  = sanitize(analyzed_data, combined_content)
    else:
        combined_content = ""
        analyzed_data    = {"safe": True}
        risk_score = 0
        manipulation = []
        attack_detected = False
        trusted_content = ""

    if intent == "WEB":
        answer_prompt = f"""Answer the following question:
{prompt}

First, attempt to answer using the following trusted web content:
{trusted_content}

Consider the following trusted long-term memories for context:
{memory_context}

If the trusted content does not contain the answer or is empty, you may answer using your own internal knowledge. However, you must be extremely accurate and factual. If you are not 100% certain of the factual accuracy, you must decline to answer by stating: 'I cannot verify the accuracy of this information.'
"""
    else:
        answer_prompt = f"""You are a helpful AI Assistant.
Respond to the user's conversational input or command.

User Input:
{prompt}

Consider the following trusted long-term memories for context:
{memory_context}
"""

    generated_answer = call_llm(answer_prompt, model=model, format_json=False)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_validation = executor.submit(validate_response, generated_answer)
        future_ai_mem     = executor.submit(validate_and_store_memory, generated_answer, "conversation_answer", "llm_generation", False)

        validation_result = future_validation.result()
        ai_memory_res     = future_ai_mem.result()

    if not validation_result.get("safe", True):
        generated_answer = "The generated answer was blocked due to security policies: " + validation_result.get("reason", "Unknown reason.")

    if validation_result.get("safe", True):
        for mem in ai_memory_res:
            if mem.get("action") in ["Store", "Store with TTL"]:
                add_memory(mem["memory"])
            memory_write_results.append({"type": "AI Answer", **mem})
    else:
        memory_write_results.append({"type": "AI Answer", "action": "Reject", "reason": "Answer was blocked."})

    latency = int((time.time() - t_start) * 1000)
    db_log_trust_event(
        raw_prompt=prompt, source=source, intent=intent,
        ingress_safe=True,
        ingress_risk=security_check.get("risk_score", 0),
        attack_type=security_check.get("attack_type"),
        content_risk=float(risk_score),
        egress_safe=validation_result.get("safe", True),
        egress_reason=validation_result.get("reason"),
        blocked=False, model_used=model, latency_ms=latency,
        client_ip=geo["ip"], country=geo["country"], country_code=geo["country_code"],
        latitude=geo["latitude"], longitude=geo["longitude"],
        vulnerability_type=security_check.get("attack_type"),
    )

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
        "memory_write": memory_write_results,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Original UI endpoint
# ──────────────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str

@app.post("/query")
async def query_endpoint(req: QueryRequest):
    return _run_trust_pipeline(req.query, source="ui", model="gemini")


@app.post("/scan-document")
async def scan_document_endpoint(file: UploadFile = File(...)):
    """
    Parses and scans uploaded files (HTML, JSON, TXT) for prompt injections,
    memory poisoning, and data leak vulnerabilities using the TrustLens pipeline.
    """
    from bs4 import BeautifulSoup
    import json
    
    contents = await file.read()
    filename = file.filename or "document.txt"
    text_content = ""
    
    # 1. Parse content based on suffix
    if filename.lower().endswith(".json"):
        try:
            parsed = json.loads(contents.decode("utf-8", errors="ignore"))
            text_content = json.dumps(parsed, indent=2)
        except Exception:
            text_content = contents.decode("utf-8", errors="ignore")
    elif filename.lower().endswith((".html", ".htm")):
        try:
            soup = BeautifulSoup(contents.decode("utf-8", errors="ignore"), "html.parser")
            text_content = soup.get_text()
        except Exception:
            text_content = contents.decode("utf-8", errors="ignore")
    elif filename.lower().endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(contents))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            text_content = "\n".join(pages)
        except Exception as e:
            text_content = f"Failed to parse PDF content: {str(e)}"
    else:
        text_content = contents.decode("utf-8", errors="ignore")
        
    # 2. Run it through the Trust pipeline!
    res = _run_trust_pipeline(text_content, source="doc_upload", model="gemini")
    res["filename"] = filename
    res["raw_content"] = text_content
    return res


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI-compatible proxy endpoint
# ──────────────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ProxyRequest(BaseModel):
    model: Optional[str] = "groq"
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

@app.post("/proxy/v1/chat/completions")
async def proxy_chat_completions(req: ProxyRequest):
    """
    OpenAI-compatible endpoint. Any app using the OpenAI SDK can point
    base_url=http://localhost:8000/proxy/v1 and all prompts will be
    intercepted and secured by TrustLens before reaching the LLM.
    """
    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming not yet supported by TrustLens proxy.")

    # Extract the last user message as the effective prompt
    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in request.")

    prompt = user_messages[-1].content

    # Map OpenAI model names to TrustLens LLM keys
    model_map = {
        "gpt-4o": "groq", "gpt-4": "groq", "gpt-3.5-turbo": "groq",
        "groq": "groq", "gemini": "groq", "deepseek": "groq",
        "llama-3.1-8b-instant": "groq", "llama3": "groq",
    }
    tl_model = model_map.get(req.model, "groq")

    result = _run_trust_pipeline(prompt, source="proxy", model=tl_model)

    # --- Build OpenAI-compatible response ---
    if result.get("blocked"):
        # Return a refusal in OpenAI format (not a 4xx — the SDK handles this as a message)
        content = f"[TrustLens] Request blocked: {result.get('reason', 'Malicious prompt detected.')}"
        finish_reason = "content_filter"
    else:
        content = result.get("answer", "")
        finish_reason = "stop"

    import uuid
    response = {
        "id": f"trustlens-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(content.split()),
            "total_tokens": len(prompt.split()) + len(content.split()),
        },
        "trustlens": {
            "verdict": "BLOCKED" if result.get("blocked") else "PASSED",
            "ingress_risk_score": result.get("prompt_security", {}).get("risk_score", 0),
            "content_risk_score": result.get("risk_score", 0),
            "egress_safe": result.get("validation_result", {}).get("safe", True),
        },
    }
    return JSONResponse(content=response)


# ──────────────────────────────────────────────────────────────────────────────
# Red Team endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/run-red-team")
async def run_red_team():
    attacks = generate_and_test_attacks(num_attacks=3)
    return {"status": "completed", "bypasses": attacks}

@app.get("/red-team-report")
def red_team_report():
    """Backwards-compat: return from DB (preferred) or fall back to JSON file."""
    try:
        attacks = db_get_attacks(limit=200)
        return {"bypasses": attacks}
    except Exception:
        filepath = "dataset/successful_bypasses.json"
        if not os.path.exists(filepath):
            return {"bypasses": []}
        try:
            with open(filepath, "r") as f:
                bypasses = json.load(f)
            return {"bypasses": bypasses}
        except Exception as e:
            return {"bypasses": [], "error": str(e)}

@app.post("/red-team-suggestions")
def red_team_suggestions(request: dict):
    """Generate (or return cached) suggestions for a bypassed attack."""
    attack_text = request.get("attack_text", "")
    reason = request.get("security_response", {}).get("reason", "unknown bypass")

    # Check cache first
    cached = db_get_or_set_suggestions(attack_text)
    if cached:
        return {"suggestions": cached, "cached": True}

    system_prompt = f"""You are an AI Security Expert specializing in LLM safety and trust layers.
A red team attack BYPASSED our security filter. Analyze it and provide actionable suggestions.

BYPASSED ATTACK:
"{attack_text}"

BYPASS REASON: {reason}

Provide exactly 3 concrete, actionable suggestions to strengthen the Trust Layer to prevent this class of attack.
Output ONLY valid JSON in this format:
{{
  "suggestions": [
    {{
      "title": "Short title of the fix",
      "description": "Detailed explanation of what to implement and why it helps",
      "priority": "HIGH" | "MEDIUM" | "LOW"
    }}
  ]
}}"""

    result = call_llm(system_prompt, model="groq", format_json=True)
    suggestions = result.get("suggestions", [])

    # Cache it
    db_get_or_set_suggestions(attack_text, suggestions)
    return {"suggestions": suggestions, "cached": False}


# ──────────────────────────────────────────────────────────────────────────────
# Analytics endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/analytics/overview")
def analytics_overview():
    """Aggregated security metrics for the Analytics dashboard."""
    try:
        return db_get_overview()
    except Exception as e:
        return {"error": str(e)}

@app.get("/analytics/attacks")
def analytics_attacks(
    limit: int = Query(default=100, le=500),
    status: Optional[str] = Query(default=None, description="BYPASSED or BLOCKED"),
):
    """Paginated attack history from DB."""
    try:
        attacks = db_get_attacks(limit=limit, status=status)
        return {"attacks": attacks, "count": len(attacks)}
    except Exception as e:
        return {"attacks": [], "count": 0, "error": str(e)}


@app.get("/analytics/threat-heatmap")
def analytics_threat_heatmap():
    """Returns aggregated data for the Threat Heatmap visualisations."""
    try:
        return db_get_threat_heatmap_data()
    except Exception as e:
        return {"error": str(e)}


@app.get("/secops/rules/pending")
def secops_rules_pending():
    """Retrieve all pending security rules awaiting approval."""
    try:
        return {"rules": db_get_pending_rules()}
    except Exception as e:
        return {"rules": [], "error": str(e)}


class ApproveRuleRequest(BaseModel):
    rule_id: int


@app.post("/secops/rules/approve")
def secops_rules_approve(req: ApproveRuleRequest):
    """Approve a proposed safety rule to enforce it active in the pipeline."""
    try:
        success = db_approve_rule(req.rule_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/secops/rules/active")
def secops_rules_active():
    """Retrieve all active (approved) security rules."""
    try:
        return {"rules": db_get_learned_rules()}
    except Exception as e:
        return {"rules": [], "error": str(e)}


class GenerateRuleRequest(BaseModel):
    attack_text: str
    category: str


@app.post("/secops/rules/generate")
def secops_rules_generate(req: GenerateRuleRequest):
    """Manually generate a safety rule proposal for an attack vector."""
    try:
        from agents.red_team import generate_learned_rule
        rule_text = generate_learned_rule(req.attack_text, req.category)
        success = db_add_learned_rule(req.attack_text, rule_text, req.category, approved=False)
        return {"success": success, "rule_text": rule_text}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
