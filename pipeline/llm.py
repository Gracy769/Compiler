import time, logging, os, json, re
from typing import Dict, Any, Tuple
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"

MODELS = {
    "deepseek": "deepseek-ai/deepseek-v4-flash",
    "minimax": "minimaxai/minimax-m2.7"
}

MAX_TOKENS = {
    "deepseek": 16384,
    "minimax": 16384
}

MAX_RETRIES = 2
RETRY_DELAY = 1

_client = None

def _get_client():
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY environment variable not set")
        _client = OpenAI(base_url=BASE_URL, api_key=NVIDIA_API_KEY)
    return _client

def _stream_response(messages: list, model: str, temperature: float, max_tokens: int) -> str:
    completion = _get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=max(temperature, 0.01),
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
    return "".join(output)

def review_with_minimax(
    draft: str,
    review_task: str,
    max_tokens: int = 8192
) -> Tuple[str, bool]:
    """
    MiniMax ONLY reviews and fixes the draft JSON.
    Fast operation - ~10-30s
    """
    model = MODELS["minimax"]
    
    review_system = f"""You are a JSON corrector. Your job is ONLY to fix errors, NOT regenerate.
- Review the JSON below
- Fix ONLY broken fields, missing values, wrong types  
- Keep correct parts AS-IS
- Output ONLY corrected JSON, no explanation

TASK: {review_task}

JSON TO REVIEW:
{draft}

Respond with ONLY the corrected JSON:"""
    
    review_messages = [{"role": "user", "content": "Fix this JSON if needed:"}]
    full_messages = [{"role": "system", "content": review_system}] + review_messages
    
    try:
        t0 = time.time()
        corrected = _stream_response(full_messages, model, 0.02, max_tokens)
        corrected = repair_json(corrected)
        was_fixed = corrected.strip() != draft.strip()
        logger.info(f"MiniMax review: {len(corrected)} chars in {time.time()-t0:.1f}s, was_fixed={was_fixed}")
        return corrected, was_fixed
    except Exception as e:
        logger.warning(f"MiniMax review failed: {e}")
        return draft, False

def repair_json(text: str) -> str:
    """Clean LLM output to valid JSON"""
    from json_repair import repair_json as repair
    
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
        repaired = repair(text)
        return repaired if repaired else text