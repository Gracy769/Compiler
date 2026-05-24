import time, logging, os, json, re
from typing import Dict, Any, Tuple

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"

MODELS = {
    "fast": "meta/llama-3.1-8b-instruct",
    "review": "minimaxai/minimax-m2.7",
    "gemma": "google/gemma-2-2b-it"
}

MAX_TOKENS = {
    "fast": 2048,
    "review": 4096,
    "gemma": 1536
}

MAX_RETRIES = 2
RETRY_DELAY = 1

_client = None

from openai import OpenAI

def _get_client():
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY environment variable not set")
        _client = OpenAI(base_url=BASE_URL, api_key=NVIDIA_API_KEY)
    return _client

def call_fast(prompt: str, system: str, max_tokens: int = 2048) -> str:
    """Fast model call - generate initial output quickly"""
    model = MODELS["fast"]
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages.insert(0, {"role": "system", "content": system})
    
    try:
        t0 = time.time()
        completion = _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.05,
            top_p=0.9,
            max_tokens=max_tokens,
            stream=True
        )
        output = []
        for chunk in completion:
            if getattr(chunk, "choices", None):
                delta = chunk.choices[0].delta
                if delta.content:
                    output.append(delta.content)
        text = "".join(output)
        logger.info(f"Fast model: {len(text)} chars in {time.time()-t0:.1f}s")
        return text.strip()
    except Exception as e:
        logger.error(f"Fast model failed: {e}")
        raise

def call_review(draft: str, review_prompt: str, schema: dict = None) -> Tuple[str, bool]:
    """
    MiniMax reviews and corrects the draft JSON.
    This is NOT regeneration - it's targeted correction.
    Should be fast (~5-10s) since MiniMax just parses and fixes.
    """
    model = MODELS["review"]
    
    messages = [
        {"role": "system", "content": f"""You are a JSON corrector. Your job is NOT to regenerate - only to fix errors.
- Review the draft JSON below
- Fix ONLY broken fields, missing values, wrong types
- Keep correct parts AS-IS
- Output ONLY the corrected JSON, no explanation

REVIEW PROMPT: {review_prompt}

DRAFT JSON TO CORRECT:
{draft}

OUTPUT: Only valid JSON, no markdown."""},
        {"role": "user", "content": "Correct this JSON if needed:"}
    ]
    
    try:
        t0 = time.time()
        completion = _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.02,
            top_p=0.85,
            max_tokens=4096,
            stream=True
        )
        output = []
        for chunk in completion:
            if getattr(chunk, "choices", None):
                delta = chunk.choices[0].delta
                if delta.content:
                    output.append(delta.content)
        text = "".join(output)
        latency = time.time() - t0
        logger.info(f"MiniMax review: {len(text)} chars in {latency:.1f}s")
        
        was_fixed = text.strip() != draft.strip()
        return text.strip(), was_fixed
        
    except Exception as e:
        logger.error(f"MiniMax review failed: {e}")
        return draft, False

def repair_json(text: str) -> str:
    """Clean LLM output to valid JSON"""
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    
    if not text.startswith("{"):
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            text = match.group()
    
    try:
        json.loads(text)
        return text
    except:
        from json_repair import repair_json as repair
        return repair(text)

def call_llm(
    messages: list,
    system: str = "",
    model_tier: str = "fast",
    temperature: float = 0.05,
    max_tokens: int = None
) -> str:
    """Legacy interface - use generate_and_review for better quality"""
    return call_llm_with_review(messages, system, temperature, max_tokens)[0]

def call_llm_with_review(
    messages: list,
    system: str = "",
    temperature: float = 0.05,
    max_tokens: int = None,
    review_task: str = "Validate and fix JSON"
) -> Tuple[str, bool]:
    """
    Two-stage: Fast generation + MiniMax review.
    Returns (final_output, was_reviewed)
    """
    user_content = messages[-1]["content"] if messages else ""
    
    draft = call_fast(user_content, system, max_tokens or 2048)
    repaired = repair_json(draft)
    
    corrected, was_fixed = call_review(repaired, review_task)
    
    return corrected, was_fixed