import time, logging, os, json, re
from typing import Tuple
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

MODELS = {
    "grok": "llama-3.3-70b-versatile",
    "review": "qwen/qwen3-32b"
}

MAX_RETRIES = 2

_nvidia_client = None
_groq_client = None

def _get_nvidia_client():
    global _nvidia_client
    if _nvidia_client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY environment variable not set")
        _nvidia_client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    return _nvidia_client

def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY environment variable not set")
        _groq_client = OpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY)
    return _groq_client

def generate_with_grok(
    prompt: str,
    system_message: str,
    max_tokens: int = 8192
) -> str:
    """Generate using Groq model - fast generation"""
    model = MODELS["grok"]
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]
    
    try:
        t0 = time.time()
        client = _get_groq_client()
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.02,
            top_p=0.9,
            max_tokens=max_tokens
        )
        result = completion.choices[0].message.content
        logger.info(f"Grok generation: {len(result)} chars in {time.time()-t0:.1f}s")
        return result
    except Exception as e:
        logger.error(f"Grok generation failed: {e}")
        raise

def review_with_minimax(
    draft: str,
    review_task: str,
    max_tokens: int = 8192
) -> Tuple[str, bool]:
    """MiniMax reviews and fixes the draft JSON - fast ~10-30s"""
    model = MODELS["review"]
    
    review_system = f"""You are a JSON corrector. Fix ONLY errors, keep correct parts AS-IS.
Output ONLY corrected JSON, no explanation.

TASK: {review_task}

JSON TO REVIEW:
{draft}

Respond with ONLY corrected JSON:"""
    
    try:
        t0 = time.time()
        client = _get_nvidia_client()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": review_system},
                {"role": "user", "content": "Fix this JSON:"}
            ],
            temperature=0.02,
            top_p=0.9,
            max_tokens=max_tokens
        )
        corrected = completion.choices[0].message.content
        corrected = repair_json(corrected)
        was_fixed = corrected.strip() != draft.strip()
        logger.info(f"MiniMax review: {len(corrected)} chars in {time.time()-t0:.1f}s, was_fixed={was_fixed}")
        return corrected, was_fixed
    except Exception as e:
        logger.warning(f"MiniMax review failed: {e}")
        return draft, False

def repair_json(text: str) -> str:
    try:
        from json_repair import repair_json as repair
    except ImportError:
        def repair(t): return t
    
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