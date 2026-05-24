import time, logging, os, json, re
from typing import Dict, Any, Tuple
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"

MODELS = {
    "deepseek": "deepseek-ai/deepseek-v4-flash",
    "fast": "meta/llama-3.1-8b-instruct",
    "gemma": "google/gemma-2-2b-it",
    "mistral": "mistralai/mistral-7b-instruct-v0.3"
}

MAX_TOKENS = {
    "deepseek": 8192,
    "fast": 2048,
    "gemma": 1536,
    "mistral": 4096
}

MAX_RETRIES = 3
RETRY_DELAY = 1

_client = None

def _get_client():
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY environment variable not set")
        _client = OpenAI(base_url=BASE_URL, api_key=NVIDIA_API_KEY)
    return _client

def call_llm(
    messages: list,
    system: str = "",
    model_tier: str = "deepseek",
    temperature: float = 0.05,
    max_tokens: int = None,
    extra_params: dict = None
) -> str:
    """
    Call LLM with specified model.
    Use 'deepseek' for best quality, 'fast' for quick generation.
    """
    model = MODELS.get(model_tier, MODELS["deepseek"])
    tokens = max_tokens or MAX_TOKENS.get(model_tier, 4096)
    
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    
    request_params = {
        "model": model,
        "messages": full_messages,
        "temperature": max(temperature, 0.01),
        "top_p": 0.9,
        "max_tokens": tokens,
        "stream": True
    }
    
    if model_tier == "deepseek" and extra_params:
        request_params.update(extra_params)
    
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t0 = time.time()
            completion = _get_client().chat.completions.create(**request_params)
            
            output = []
            for chunk in completion:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    output.append(delta.content)
            
            text = "".join(output)
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
    
    raise RuntimeError(f"LLM failed after {MAX_RETRIES} attempts. Last error: {last_error}")

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