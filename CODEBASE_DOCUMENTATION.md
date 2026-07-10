# TrustLens — Codebase Architecture & File Reference

This document provides a detailed breakdown of every component, agent, database schema, and script in the TrustLens codebase, explaining how they work individually and how they integrate into a unified security proxy.

---

## 📁 Directory Structure Overview

```text
content-trust/
├── backend/
│   ├── app.py                      # FastAPI Application & Command Coordinator
│   ├── database.py                 # SQLite Relational Database layer (SQLAlchemy)
│   ├── llm.py                      # Unified LLM client (Groq / Gemini wrapper)
│   ├── requirements.txt            # Python dependencies
│   ├── test_threats.py             # Automated unit tests for Threat analytics
│   ├── agents/
│   │   ├── prompt_security.py      # Ingress Prompt Filter (Static & Learned Rules)
│   │   ├── search_agent.py         # Search Orchestrator & Local File Loader
│   │   ├── trust_analyzer.py       # Crawler Content Scanner & Injection Detector
│   │   ├── sanitizer.py            # Crawled Content Text Filter & Purger
│   │   ├── response_validator.py   # Egress Output Guardrail (Data leak check)
│   │   ├── memory_write_validator.py # Fact extractor and Memory filter
│   │   ├── memory_retrieval_validator.py # Memory context retriever
│   │   ├── memory_storage.py       # Memory DB CRUD controls
│   │   └── red_team.py             # Adversarial Simulator & Rule Hardener
│   └── dataset/
│       ├── test_cases/             # Mock files (.html & .json) representing attacks
│       └── successful_bypasses.json# Compat fallback logs
└── frontend/
    └── src/
        ├── App.jsx                 # Commands Console React UI Dashboard
        ├── index.css               # Command Center design system
        └── App.css                 # Observability trace styling
```

---

## ⚙️ Core System Files

### 1. [app.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/app.py)
The central coordinator of the TrustLens system. It starts the FastAPI web server, initializes the database, manages background cron tasks, and routes API requests.
* **Core Functions**:
  * `_run_trust_pipeline(prompt, source, model)`: The unified sequence manager. It runs the ingress check, routes intent, fetches scraped search results or local test files, runs the egress validator, and logs telemetry.
  * `scheduled_red_team_job()`: A background cron job managed by `BackgroundScheduler` that automatically fires adversarial red-team simulations every 8 hours.
* **Exposed Endpoints**:
  * `POST /query`: Processes user prompts through the safety command pipeline.
  * `POST /proxy/v1/chat/completions`: OpenAI-compatible proxy endpoint allowing standard SDK applications to easily leverage TrustLens security.
  * `GET /analytics/threat-heatmap`: Fetches attack coordinates, hourly peak distributions, and vector breakdown stats.
  * `POST /secops/rules/approve`: Approves a pending self-hardening rule to activate it in the pipeline.

### 2. [database.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/database.py)
Manages the SQLAlchemy configuration and ORM models for relational persistence in SQLite (`trustlens.db`).
* **Database Models**:
  * `TrustEvent`: Logs every single request, recording timestamps, latency, ingress/egress safety flags, and telemetry data (IP, Country, Latitude, Longitude).
  * `AttackRecord`: Logs detail records of automated red-team simulations.
  * `LearnedRule`: Stores dynamically generated security rules with an `approved` boolean flag.
* **Key Functions**:
  * `db_get_threat_heatmap_data()`: Compiles geographical coordinate aggregations for the command center SVG map.
  * `db_approve_rule(rule_id)`: Toggles a pending rule's `approved` status to `True`.
  * `db_get_learned_rules(limit)`: Retrieves approved rules which are injected directly into the prompt safety evaluation.

### 3. [llm.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/llm.py)
Provides a unified client for calling model providers. It encapsulates API key checks, fallback configuration, and JSON parsing.
* **Key Functions**:
  * `call_llm(prompt, model, format_json)`: Executes LLM calls. If `format_json=True`, it formats the request parameters and parses the response string into a clean Python dictionary.
  * If a model call fails (e.g. rate limit), it automatically fails over from Groq (Llama) to Google Gemini to guarantee uptime.

---

## 🕵️ Security & Processing Agents

### 4. [agents/prompt_security.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/prompt_security.py)
Handles **Ingress filtering**. Evaluates the incoming prompt *before* it reaches the core model.
* **How it works**:
  1. Queries the database for all approved rules (`approved=True`).
  2. Compiles a system prompt instructing the LLM to inspect the prompt for standard vectors (Jailbreak, Prompt Extraction, Exfiltration, Manipulation) across multiple languages.
  3. Appends the *Learned Security Rules* to enforce active hardening constraints.
  4. Returns a safety verdict (Safe/Unsafe) with risk scores and classification types.

### 5. [agents/search_agent.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/search_agent.py)
Fetches context for the user prompt. 
* **How it works**:
  * If the prompt starts with `test:`, it strips the prefix and runs a recursive search inside the `dataset/` directory to load local test files (like `02_hidden_prompt_injection.html`), handling partial filename matches.
  * If the prompt is a URL, it extracts HTML body text.
  * Otherwise, it queries web search indexes and aggregates raw crawled content.

### 6. [agents/trust_analyzer.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/trust_analyzer.py)
Scans crawled web text or loaded document data for **Indirect Prompt Injections**.
* **How it works**:
  * Evaluates raw content blocks for hidden instructions, hidden stylesheet manipulation (`display: none`), or attempts to hijack the conversation when summarized.
  * Flags sections that contain malicious patterns, giving them high risk coordinates.

### 7. [agents/sanitizer.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/sanitizer.py)
Purges threats detected by the trust analyzer.
* **How it works**:
  * Takes the original crawled text and strips out paragraphs, HTML nodes, or blocks that were flagged as unsafe by `trust_analyzer.py`, sending only sanitized text to the generator LLM.

### 8. [agents/response_validator.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/response_validator.py)
Handles **Egress filtering**. Evaluates the LLM's output *before* it is returned to the user.
* **How it works**:
  * Scans generated completions for signs of successful jailbreak prompts, leaked system prompt text, API credentials, SQL database structures, or internal PII.
  * If validation fails, it overrides the answer with a generic security block message.

### 9. [agents/memory_write_validator.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/memory_write_validator.py)
Prevents **Memory Poisoning** by filtering what facts are saved to long-term memory.
* **How it works**:
  1. Calls the LLM to extract individual facts from the prompt/response.
  2. Scores each fact on *Utility*, *Trustworthiness*, *Risk*, and *Longevity*.
  3. Runs regex overlays checking for system commands, credential keys, or admin overrides.
  4. Discards high-risk or low-trust items (such as hidden rule injections) and approves only clean facts (like user preferences) for long-term database storage.

### 10. [agents/red_team.py](file:///Users/aditigupta/Library/Mobile%20Documents/com~apple~CloudDocs/ADITI%20WORK/projects/content-trust/backend/agents/red_team.py)
The automated testing and self-hardening orchestrator.
* **How it works**:
  1. Selects categories (e.g., Jailbreak, Data Exfiltration) and generates novel prompt variants using an LLM.
  2. Submits these variants to the local proxy pipeline.
  3. If an attack is **Blocked**, it records the success of the active rules.
  4. If an attack is **Bypassed**, it triggers the self-hardening engine to formulate a crisp prompt-filtering rule (e.g. *"Block prompts adopting the DAN persona"*).
  5. Saves this new rule to the database as `approved = False` for human review, and simulates a target location IP/Coordinate pair to plot on the threat heatmap.
