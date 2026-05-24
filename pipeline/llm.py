import time, logging, os, json, re
from typing import Dict, Any, Tuple
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"

MODELS = {
    "fast": "meta/llama-3.1-8b-instruct",
    "deepseek": "deepseek-ai/deepseek-v4-flash",
    "gemma": "google/gemma-2-2b-it",
    "mistral": "mistralai/mistral-7b-instruct-v0.3",
    "minimax": "minimaxai/minimax-m2.7"
}

MAX_TOKENS = {
    "fast": 4096,
    "deepseek": 16384,
    "gemma": 2048,
    "mistral": 16384,
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

def _stream_response(messages: list, model: str, temperature: float, max_tokens: int, extra_params: dict = None) -> str:
    """Internal streaming call"""
    request_params = {
        "model": model,
        "messages": messages,
        "temperature": max(temperature, 0.01),
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "stream": True
    }
    if extra_params:
        request_params.update(extra_params)
    
    completion = _get_client().chat.completions.create(**request_params)
    output = []
    for chunk in completion:
        if getattr(chunk, "choices", None):
            delta = chunk.choices[0].delta
            if delta.content:
                output.append(delta.content)
    return "".join(output)

def call_llm(
    messages: list,
    system: str = "",
    model_tier: str = "deepseek",
    temperature: float = 0.05,
    max_tokens: int = None,
    extra_params: dict = None
) -> str:
    """Simple LLM call"""
    model = MODELS.get(model_tier, MODELS["deepseek"])
    tokens = max_tokens or MAX_TOKENS.get(model_tier, 8192)
    
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t0 = time.time()
            text = _stream_response(full_messages, model, temperature, tokens, extra_params)
            latency = time.time() - t0
            logger.info(f"LLM OK | model={model_tier} latency={latency:.1f}s chars={len(text)}")
            if not text.strip():
                raise ValueError("Empty response")
            return text.strip()
        except Exception as e:
            last_error = str(e)
            logger.warning(f"LLM attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    raise RuntimeError(f"LLM failed: {last_error}")

def generate_and_review(
    user_prompt: str,
    system_prompt: str,
    review_task: str = "Fix any errors in this JSON",
    max_tokens: int = 16384
) -> Tuple[str, bool]:
    """
    Two-stage: Fast generation + MiniMax review/correct.
    
    Stage 1: DeepSeek Flash generates quickly
    Stage 2: MiniMax reviews and fixes ONLY broken parts (not regeneration)
    
    Returns (final_output, was_reviewed)
    """
    fast_model = "deepseek"
    review_model = "minimax"
    
    t0 = time.time()
    logger.info(f"Stage 1: {fast_model} generating...")
    
    messages = [{"role": "user", "content": user_prompt}]
    full_messages = [{"role": "system", "content": system_prompt}] + messages if system_prompt else messages
    
    try:
        draft = _stream_response(full_messages, MODELS[fast_model], 0.05, max_tokens)
        draft = repair_json(draft)
        logger.info(f"Stage 1 complete: {len(draft)} chars in {time.time()-t0:.1f}s")
    except Exception as e:
        logger.error(f"Stage 1 failed: {e}")
        raise
    
    t1 = time.time()
    logger.info(f"Stage 2: {review_model} reviewing...")
    
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
    
    try:
        corrected = _stream_response(review_messages, MODELS[review_model], 0.02, max_tokens, 
                                      extra_params={"chat_template_kwargs": {"thinking": False}})
        corrected = repair_json(corrected)
        was_fixed = corrected.strip() != draft.strip()
        logger.info(f"Stage 2 complete: reviewed in {time.time()-t1:.1f}s, was_fixed={was_fixed}")
        return corrected, was_fixed
    except Exception as e:
        logger.warning(f"Stage 2 review failed: {e}, using draft")
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