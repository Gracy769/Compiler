import time, logging, os, json, re
from typing import Tuple, Optional
from openai import OpenAI

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

MODELS = {
    "generation": "llama3-70b-8192",
    "review": "minimaxai/minimax-m2.7"
}

MAX_RETRIES = 2

_nvidia_client = None
_groq_client = None

def _get_nvidia_client() -> OpenAI:
    global _nvidia_client
    if _nvidia_client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY environment variable not set. Get one from https://developer.nvidia.com/")
        _nvidia_client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    return _nvidia_client

def _get_groq_client() -> OpenAI:
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY environment variable not set. Get one from https://console.groq.com/")
        _groq_client = OpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY)
    return _groq_client

def _safe_get_content(completion) -> str:
    if not completion.choices:
        return ""
    choice = completion.choices[0]
    if not hasattr(choice, 'message'):
        return ""
    return choice.message.content or ""

def generate_with_llama(
    prompt: str,
    system_message: str,
    max_tokens: int = 8192
) -> str:
    """Generate using Groq Llama model - fast generation"""
    model = MODELS["generation"]
    
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
        result = _safe_get_content(completion)
        if not result:
            raise ValueError("Empty response from Groq")
        logger.info(f"Llama generation: {len(result)} chars in {time.time()-t0:.1f}s")
        return result
    except Exception as e:
        logger.error(f"Llama generation failed: {e}")
        raise

def review_with_model(
    draft: str,
    review_task: str,
    max_tokens: int = 8192
) -> Tuple[str, bool]:
    """MiniMax reviews and fixes the draft JSON on NVIDIA - fast ~10-30s"""
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
        corrected = _safe_get_content(completion)
        if not corrected:
            logger.warning("MiniMax returned empty response")
            return draft, False
        
        corrected = repair_json(corrected)
        
        was_fixed = _json_structurally_different(draft, corrected)
        logger.info(f"MiniMax review: {len(corrected)} chars in {time.time()-t0:.1f}s, was_fixed={was_fixed}")
        return corrected, was_fixed
    except Exception as e:
        logger.warning(f"MiniMax review failed: {e}")
        return draft, False

def _json_structurally_different(original: str, corrected: str) -> bool:
    try:
        orig_parsed = json.loads(original)
        corr_parsed = json.loads(corrected)
        return orig_parsed != corr_parsed
    except json.JSONDecodeError:
        return original.strip() != corrected.strip()

def repair_json(text: str) -> str:
    try:
        from json_repair import repair_json as repair
    except ImportError:
        def repair(t): return t
    
    original_text = text
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    
    brace_count = text.count('{') - text.count('}')
    if brace_count > 0:
        text += '}' * brace_count
    elif brace_count < 0:
        text = '{' * (-brace_count) + text
    
    if not text.startswith("{"):
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            text = match.group()
    
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        repaired = repair(text)
        if repaired and repaired != text:
            try:
                json.loads(repaired)
                return repaired
            except:
                pass
        return original_text

def minify_json(text: str) -> str:
    try:
        data = json.loads(text)
        return json.dumps(data, separators=(',', ':'))
    except:
        return text