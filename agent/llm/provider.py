"""LLM integration for Autonomous AI Coding Agent using Google Gemini & LangSmith."""

import os
import re
import json
import logging
from typing import Optional, List, Dict, Any
import requests
from dotenv import load_dotenv

# LangSmith tracing instrumentation
try:
    from langsmith import traceable
except ImportError:
    def traceable(**kwargs):
        def decorator(func):
            return func
        return decorator

load_dotenv()
logger = logging.getLogger("autonomous_agent.llm")

def extract_code_block(text: str) -> str:
    """Extracts Python or JSON code from a markdown block, or returns stripped text if no fence."""
    pattern = r"```(?:python|json)?\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    pattern_generic = r"```(?:[a-zA-Z0-9_-]+)?\s*\n?(.*?)```"
    match_gen = re.search(pattern_generic, text, re.DOTALL)
    if match_gen:
        return match_gen.group(1).strip()

    # Handle unclosed code fence (e.g. truncated generation)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        else:
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    return cleaned

class GeminiClient:
    """Google Gemini LLM client via REST API with LangSmith trace support."""

    # High availability, rapid response Gemini models
    MODELS = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    ]

    def __init__(self, api_key: Optional[str] = None):
        raw_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.api_key = raw_key.strip("\"' \n\r\t")
        self.endpoint_base = "https://generativelanguage.googleapis.com/v1beta/models"
        self.last_token_usage: Dict[str, Any] = {}
        self.cumulative_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10 and not self.api_key.startswith("your_"))

    @traceable(run_type="llm", name="gemini_generate_call")
    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """Calls Google Gemini with automatic model fallback on error or rate-limit."""
        if not self.is_available():
            logger.warning("Gemini API key is not configured.")
            return None

        for model_name in self.MODELS:
            url = f"{self.endpoint_base}/{model_name}:generateContent?key={self.api_key}"
            
            contents = []
            if system_instruction:
                contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nTask follows."}]})
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                }
            }

            try:
                resp = requests.post(url, json=payload, timeout=18)
                if resp.status_code == 200:
                    data = resp.json()

                    # Extract usage metadata
                    usage = data.get("usageMetadata", {})
                    input_tokens = usage.get("promptTokenCount", 0)
                    output_tokens = usage.get("candidatesTokenCount", 0)
                    total_tokens = usage.get("totalTokenCount", 0)

                    self.last_token_usage = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "model": model_name,
                    }
                    self.cumulative_token_usage["input_tokens"] += input_tokens
                    self.cumulative_token_usage["output_tokens"] += output_tokens
                    self.cumulative_token_usage["total_tokens"] += total_tokens

                    # Instrument LangSmith run tree with usage metrics
                    try:
                        from langsmith.run_helpers import get_current_run_tree
                        rt = get_current_run_tree()
                        if rt:
                            rt.add_metadata({
                                "usage_metadata": {
                                    "input_tokens": input_tokens,
                                    "output_tokens": output_tokens,
                                    "total_tokens": total_tokens,
                                },
                                "ls_model_name": model_name,
                                "ls_provider": "google_gemini",
                            })
                    except Exception:
                        pass

                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"]
                else:
                    logger.warning(f"Model {model_name} returned status {resp.status_code}, trying next model...")
            except Exception as e:
                logger.warning(f"Model {model_name} request failed ({e}), trying next model...")
                continue

        return None

class LLMProvider:
    """Unified provider orchestrating LLM calls for planning, code generation, and debugging."""

    def __init__(self):
        self.gemini = GeminiClient()

    def is_available(self) -> bool:
        return self.gemini.is_available()

    @traceable(name="llm_create_plan")
    def create_plan(self, task: str, relevant_files: List[str], symbol_names: List[str]) -> Optional[List[str]]:
        """Uses LLM to synthesize a step-by-step engineering plan."""
        if not self.is_available():
            return None

        prompt = f"""You are a Principal Software Engineer.
Given the following user task and codebase context, produce a concise 4-step implementation plan.

TASK:
{task}

RELEVANT TARGET FILES:
{', '.join(relevant_files) if relevant_files else 'Repository modules'}

DETECTED AST SYMBOLS:
{', '.join(symbol_names[:15]) if symbol_names else 'None'}

Return ONLY a valid JSON list of 4 clear strings. Example:
["Analyze target module and AST symbols", "Implement missing logic and edge-case guards", "Run unit test suite in sandbox", "Verify test results and complete verification"]
"""
        raw = self.gemini.generate(prompt, temperature=0.1, max_tokens=512)
        if not raw:
            return None

        try:
            cleaned = extract_code_block(raw)
            plan = json.loads(cleaned)
            if isinstance(plan, list) and len(plan) > 0:
                return [str(p) for p in plan]
        except Exception:
            pass
        return None

    @traceable(name="llm_generate_code")
    def generate_code_patch(
        self,
        task: str,
        file_path: str,
        current_content: str,
        ast_context: str,
        test_failure: Optional[str] = None,
        iteration: int = 0
    ) -> Optional[str]:
        """Uses LLM reasoning to generate the complete corrected file content."""
        if not self.is_available():
            return None

        debugging_context = ""
        if test_failure:
            debugging_context = f"""
TEST FAILURES & TRACEBACK TO FIX (Self-Healing Loop Iteration #{iteration}):
----------------------------------------------------------------------
{test_failure}
----------------------------------------------------------------------
Carefully examine why tests failed (e.g. ValueError expected on division by zero, negative square root, or negative factorial).
Resolve all issues in your updated code!
"""

        prompt = f"""You are an Autonomous AI Senior Software Engineer.
Your task is to write clean, production-grade Python code to fulfill the requirement or fix test failures.

TASK OBJECTIVE:
{task}

TARGET FILE:
{file_path}

AST CONTEXT:
{ast_context}
{debugging_context}

CURRENT FILE CONTENT:
```python
{current_content}
```

CRITICAL INSTRUCTIONS:
1. Return the ENTIRE updated content of `{file_path}` inside a ```python ``` code block.
2. Ensure all existing functions/classes remain intact, with the missing methods or bug fixes fully implemented.
3. Handle all relevant edge cases (e.g., zero division raises ValueError, negative values for sqrt/factorial raise ValueError).
4. Output ONLY the ```python ... ``` code block. Do NOT include conversational filler.
"""
        raw = self.gemini.generate(prompt, temperature=0.1, max_tokens=3000)
        if not raw:
            return None

        code = extract_code_block(raw)
        if code and len(code) > 20 and ("def " in code or "class " in code):
            return code
        return None

# Singleton accessor
_provider_instance = None

def get_llm_provider() -> LLMProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = LLMProvider()
    return _provider_instance
