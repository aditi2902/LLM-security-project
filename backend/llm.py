import ollama
import json
import os
from dotenv import load_dotenv

load_dotenv()

def call_llm(prompt, model="groq", format_json=False, retries=1):
    if format_json:
        prompt = prompt + "\n\nIMPORTANT: Output ONLY valid JSON. Do not include markdown formatting or backticks."

    if model == "groq":
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                print("Warning: GROQ_API_KEY not found in .env, falling back to Ollama.")
                return call_llm(prompt, model="qwen2.5:3b", format_json=format_json, retries=0)
                
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.1-8b-instant",
                response_format={"type": "json_object"} if format_json else None
            )
            text = chat_completion.choices[0].message.content
            return _parse_json(text) if format_json else text
        except Exception as e:
            if retries > 0 and ("429" in str(e) or "rate limit" in str(e).lower() or "limit" in str(e).lower()):
                import time
                print(f"Groq Rate Limit detected. Retrying in 1.5s... (Retries left: {retries})")
                time.sleep(1.5)
                return call_llm(prompt, model="groq", format_json=format_json, retries=retries - 1)
            print(f"Groq Error: {e} - Falling back to Ollama.")
            return call_llm(prompt, model="qwen2.5:3b", format_json=format_json, retries=0)
            
    elif model == "gemini":
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                print("Warning: GEMINI_API_KEY not found in .env, falling back to Groq.")
                return call_llm(prompt, model="groq", format_json=format_json, retries=retries)
                
            client = genai.Client(api_key=api_key)
            config_kwargs = {}
            if format_json:
                from google.genai import types
                config_kwargs["response_mime_type"] = "application/json"
                
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=config_kwargs if config_kwargs else None
            )
            text = response.text
            return _parse_json(text) if format_json else text
        except Exception as e:
            if retries > 0 and ("429" in str(e) or "quota" in str(e).lower() or "limit" in str(e).lower()):
                import time
                print(f"Gemini Rate Limit detected. Retrying in 1.5s... (Retries left: {retries})")
                time.sleep(1.5)
                return call_llm(prompt, model="gemini", format_json=format_json, retries=retries - 1)
            print(f"Gemini Error: {e} - Falling back to Groq.")
            return call_llm(prompt, model="groq", format_json=format_json, retries=retries)
            
    elif model == "deepseek":
        try:
            from openai import OpenAI
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                print("Warning: DEEPSEEK_API_KEY not found in .env, falling back to Groq.")
                return call_llm(prompt, model="groq", format_json=format_json)
                
            base_url = "https://api.deepseek.com"
            model_name = "deepseek-chat"
            
            # Auto-detect NVIDIA NIM API keys
            if api_key.startswith("nvapi-"):
                base_url = "https://integrate.api.nvidia.com/v1"
                model_name = "deepseek-ai/deepseek-v4-flash"
                
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            # NVIDIA's DeepSeek-R1 does not support response_format={"type": "json_object"} well due to <think> tags.
            kwargs = {
                "messages": [{"role": "user", "content": prompt}],
                "model": model_name,
                "timeout": 10
            }
            if not api_key.startswith("nvapi-") and format_json:
                kwargs["response_format"] = {"type": "json_object"}
                
            chat_completion = client.chat.completions.create(**kwargs)
            text = chat_completion.choices[0].message.content
            return _parse_json(text) if format_json else text
        except Exception as e:
            print(f"DeepSeek Error: {e} - Falling back to Groq.")
            return call_llm(prompt, model="groq", format_json=format_json, retries=retries)
            
    else:
        # Fallback to Ollama
        kwargs = {"model": model, "prompt": prompt}
        if format_json:
            kwargs["format"] = "json"
            
        try:
            response = ollama.generate(**kwargs)
            text = response['response']
            return _parse_json(text) if format_json else text
        except Exception as e:
            print(f"Ollama Error: {e}")
            return {} if format_json else ""

def _parse_json(text):
    import re
    try:
        # Remove <think>...</think> tags which DeepSeek-R1 outputs
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # Sometimes LLMs add markdown even when asked not to
        text = text.strip()
        
        # Try to find JSON blocks within markdown
        json_match = re.search(r'```(?:json)?(.*?)```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()
            
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON. Raw text: {text}")
        return {} # Fallback