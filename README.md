# Dual Content Trust Layer

A comprehensive full-stack application designed to enforce security, validate memory, and ensure trust when interacting with Large Language Models (LLMs). This project acts as a robust middle layer that intercepts, analyzes, and sanitizes interactions to prevent prompt injections, memory poisoning, and other malicious attacks.

## 🏗 Architecture

The project is split into a frontend UI and a powerful agentic backend, orchestrated together via Docker.

### Frontend
- **Framework:** React + Vite
- **Environment:** Node.js 20
- **Port:** `5173`

### Backend (Trust Layer)
- **Framework:** FastAPI (Python 3.11)
- **LLM Provider:** Groq
- **Core Agents:**
  - `intent_router.py`: Routes the user's intent to the appropriate internal tool or agent.
  - `prompt_security.py`: Analyzes incoming prompts for hidden prompt injections, roleplay attacks, and malicious instructions.
  - `memory_write_validator.py` & `memory_retrieval_validator.py`: Ensures that context stored in or retrieved from memory is safe and hasn't been poisoned.
  - `sanitizer.py`: Strips dangerous characters and obfuscations (like Base64 payloads).
  - `response_validator.py`: Evaluates the final LLM output for safety and contradictory information before sending it to the user.
  - `trust_analyzer.py`: The overarching orchestrator that assigns trust scores to content.

## 🚀 Getting Started

The entire application is fully Dockerized. You can spin up the frontend and backend with a single command.

### Prerequisites
1. **Docker Desktop** installed and running on your machine.
2. A **Groq API Key**.
3. A **Google Cloud (GCP) Service Account API Key**.

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/aditi2902/dual-content-trust-layer.git
   cd dual-content-trust-layer
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the root directory of the project:
   ```bash
   touch .env
   ```
   Add your API keys to the `.env` file:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   GCP_API_KEY=your_gcp_api_key_here
   ```

3. **Run the Application:**
   Start both the frontend and backend using Docker Compose:
   ```bash
   docker compose up --build
   ```

4. **Access the App:**
   - **Frontend:** [http://localhost:5173](http://localhost:5173)
   - **Backend API:** [http://localhost:8000](http://localhost:8000)

## 📁 Project Structure

```text
dual-content-trust-layer/
├── frontend/                 # React UI
│   ├── src/                  # React components and assets
│   ├── Dockerfile            # Frontend container config
│   └── package.json          # Node dependencies
├── backend/                  # FastAPI Backend & Agents
│   ├── agents/               # Security and Trust analysis modules
│   ├── dataset/              # Attack vectors, safe content, and test cases
│   ├── retrieval/            # Scrapers and search implementations
│   ├── app.py                # Main FastAPI entry point
│   ├── Dockerfile            # Backend container config
│   └── requirements.txt      # Python dependencies
├── docker-compose.yml        # Orchestrates the frontend and backend
├── .gitignore                # Ignored files (e.g., .env)
└── README.md                 # Project documentation
```

## 🛡️ Security Features Tested

The `backend/dataset/test_cases/` directory includes various HTML, JSON, and text mockups used to validate the Trust Layer against:
- Unicode obfuscation
- Base64 encoded payloads
- Hidden prompt injections
- Memory poisoning attempts
- Contradictory information injection
- Malicious API retrieval
