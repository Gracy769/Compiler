import time, logging, os
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"

MODELS = {
    "fast": "meta/llama-3.1-8b-instruct",
    "medium": "mistralai/mistral-7b-instruct-v0.3",
    "slow": "minimaxai/minimax-m2.7"
}

MAX_TOKENS = {
    "fast": 4096,
    "medium": 4096,
    "slow": 16384
}

MAX_RETRIES = 3
RETRY_DELAY = 2

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
    model_tier: str = "medium",
    temperature: float = 0.1,
    max_tokens: int = None
) -> str:
    model = MODELS.get(model_tier, MODELS["medium"])
    tokens = max_tokens or MAX_TOKENS.get(model_tier, 4096)
    
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t0 = time.time()
            completion = _get_client().chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=max(temperature, 0.02),
                top_p=0.9,
                max_tokens=tokens,
                stream=True
            )
            output = []
            for chunk in completion:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    output.append(delta.content)
            text = "".join(output)
            latency = round(time.time() - t0, 2)
            logger.info(f"LLM OK | tier={model_tier} model={model} attempt={attempt} latency={latency}s chars={len(text)}")
            if not text.strip():
                raise ValueError("Empty response from model")
            return text
        except Exception as e:
            last_error = str(e)
            logger.warning(f"LLM attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    
    raise RuntimeError(f"LLM failed after {MAX_RETRIES} attempts. Last error: {last_error}")