import time, logging, os
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL       = "https://integrate.api.nvidia.com/v1"
MODEL          = "minimaxai/minimax-m2.7"
MAX_TOKENS     = 16384
MAX_RETRIES    = 5
RETRY_DELAY    = 4

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
    temperature: float = 0.05,
    max_tokens: int = MAX_TOKENS
) -> str:
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t0 = time.time()
            completion = _get_client().chat.completions.create(
                model=MODEL, messages=full_messages, temperature=max(temperature, 0.01),
                top_p=0.9, max_tokens=max_tokens, stream=True
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
            logger.info(f"LLM OK | attempt={attempt} latency={latency}s chars={len(text)}")
            if not text.strip():
                raise ValueError("Empty response from model")
            return text
        except Exception as e:
            last_error = str(e)
            logger.warning(f"LLM attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    raise RuntimeError(f"LLM failed after {MAX_RETRIES} attempts. Last error: {last_error}")