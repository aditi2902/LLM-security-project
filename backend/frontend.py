import streamlit as st
import requests
import json

st.set_page_config(page_title="Content Trust Layer", page_icon="🛡️", layout="wide")

# Custom CSS for a professional, modern look (Glassmorphism, Google Fonts, etc.)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
    }
    
    .stTextInput>div>div>input {
        background-color: rgba(30, 41, 59, 0.7);
        color: #f8fafc;
        border-radius: 8px;
        border: 1px solid #334155;
        padding: 12px 16px;
    }
    
    .stTextInput>div>div>input:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
    }
    
    .stAlert {
        border-radius: 12px;
        border: none;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    [data-testid="stExpander"] {
        background-color: rgba(30, 41, 59, 0.5);
        border: 1px solid #334155;
        border-radius: 12px;
        overflow: hidden;
    }
    
    [data-testid="stExpander"] > summary {
        background-color: rgba(30, 41, 59, 0.8);
        padding: 12px 16px;
    }
    
    h1, h2, h3 {
        background: -webkit-linear-gradient(45deg, #60a5fa, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    
    .stDivider {
        border-bottom-color: #334155;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Content Trust Layer")
st.markdown("Built a semantic trust layer for retrieval-augmented AI systems that classifies retrieved content into knowledge and instruction components, sanitizes manipulation attempts, and prevents indirect prompt injection attacks before content reaches the language model.")

query = st.text_input("Enter your question:", placeholder="e.g. Best AI startup ideas")

if st.button("Search & Analyze"):
    if query:
        # Step 1: Only run the spinner during the API request
        with st.spinner("Processing through Trust Layer..."):
            try:
                response = requests.post("http://localhost:8000/query", json={"query": query})
                response_data = response.json() if response.status_code == 200 else None
                status_code = response.status_code
            except requests.exceptions.ConnectionError:
                response_data = None
                status_code = 0
                
        # Step 2: Render UI outside the spinner
        if status_code == 200 and response_data:
            data = response_data
            
            st.divider()
            st.header("Stage 1: User Prompt Security")
            prompt_sec = data.get("prompt_security", {})
            
            if data.get("blocked", False) and not prompt_sec.get("safe", True):
                st.error("🚨 MALICIOUS PROMPT DETECTED")
                st.write(f"**Reason:** {data.get('reason')}")
                with st.expander("View Security Analysis Details"):
                    st.json(prompt_sec)
                st.stop() # Stop further execution
            else:
                st.success("✅ User Prompt is Safe")
                with st.expander("View Security Analysis Details"):
                    st.json(prompt_sec)
            
            st.divider()
            st.header("Stage 2: Web Search & Content Security")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Website Threat Analysis")
                risk_score = data.get('risk_score', 0)
                
                if risk_score > 70:
                    st.error(f"High Risk Website Content Detected! Score: {risk_score}")
                elif risk_score > 30:
                    st.warning(f"Moderate Risk Website Content. Score: {risk_score}")
                else:
                    st.success(f"Low Risk Website Content. Score: {risk_score}")
                    
                with st.expander("View Website Threat JSON"):
                    st.json({
                        "risk_score": risk_score,
                        "attack_detected": data.get("attack_detected", False),
                        "removed_content": data.get("removed_content", [])
                    })
                    
                with st.expander("🔍 View Raw Retrieved Content"):
                    st.markdown(data.get("raw_content", ""))
                
            with col2:
                st.subheader("Final Answer")
                st.info(data.get("answer", ""))
                
                if data.get("validation_result"):
                    st.caption("Post-generation Validation")
                    with st.expander("View Validation JSON"):
                        st.json(data.get("validation_result"))
                
                with st.expander("🛡️ View Sanitized Content"):
                    st.markdown(data.get("sanitized_content", ""))
                
        elif status_code == 0:
            st.error("Failed to connect to backend. Is FastAPI running on port 8000?")
        else:
            st.error(f"Backend Error: {status_code}")
    else:
        st.warning("Please enter a question.")
