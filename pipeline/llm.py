import time, logging, os, json, re
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("ai-compiler")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"

MODELS = {
    "fast": "meta/llama-3.1-8b-instruct",
    "gemma": "google/gemma-2-2b-it",
    "medium": "mistralai/mistral-7b-instruct-v0.3"
}

MAX_TOKENS = {
    "fast": 4096,
    "gemma": 2048,
    "medium": 4096
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

from openai import OpenAI

def call_llm_with_repair(
    messages: list,
    system: str = "",
    model_tier: str = "fast",
    temperature: float = 0.05,
    max_tokens: int = None,
    schema: dict = None
) -> Tuple[str, bool]:
    """
    Smart LLM call with JSON repair and validation.
    Returns (output, was_repaired)
    """
    model = MODELS.get(model_tier, MODELS["fast"])
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
            raw_text = "".join(output)
            latency = round(time.time() - t0, 2)
            logger.info(f"LLM OK | tier={model_tier} latency={latency}s chars={len(raw_text)}")
            
            if not raw_text.strip():
                raise ValueError("Empty response from model")
            
            repaired_text = repair_json_output(raw_text)
            
            if schema:
                from jsonschema import validate, ValidationError
                try:
                    data = json.loads(repaired_text)
                    validate(instance=data, schema=schema)
                    return repaired_text, False
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.warning(f"Validation failed, attempting repair: {e}")
                    repaired = repair_json_with_schema(repaired_text, schema)
                    if repaired:
                        return json.dumps(repaired), True
            
            return repaired_text, False
            
        except Exception as e:
            last_error = str(e)
            logger.warning(f"LLM attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    
    raise RuntimeError(f"LLM failed after {MAX_RETRIES} attempts. Last error: {last_error}")

def repair_json_output(raw: str) -> str:
    """Clean and repair potentially broken JSON from LLM"""
    from json_repair import repair_json
    
    text = raw.strip()
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    
    if not text.startswith("{"):
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            text = match.group()
    
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        repaired = repair_json(text)
        if repaired and len(repaired) > 0:
            logger.info("JSON repaired by json-repair library")
            return repaired
        return text

def repair_json_with_schema(text: str, schema: dict) -> Optional[dict]:
    """Attempt to repair JSON to match schema"""
    from jsonschema import validate, ValidationError
    
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        from json_repair import repair_json
        data = repair_json(text)
        if not data:
            return None
    
    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})
    
    for field in required_fields:
        if field not in data:
            if field in properties:
                field_type = properties[field].get("type", "string")
                if field_type == "string":
                    data[field] = ""
                elif field_type == "array":
                    data[field] = []
                elif field_type == "object":
                    data[field] = {}
                elif field_type == "integer":
                    data[field] = 0
                elif field_type == "boolean":
                    data[field] = False
    
    for key, value in list(data.items()):
        if key not in properties:
            continue
        prop_schema = properties[key]
        expected_type = prop_schema.get("type")
        
        if expected_type == "array" and not isinstance(value, list):
            data[key] = [value] if value else []
        elif expected_type == "object" and not isinstance(value, dict):
            data[key] = {"value": value} if value else {}
    
    try:
        validate(instance=data, schema=schema)
        return data
    except ValidationError as e:
        logger.warning(f"Schema repair failed: {e}")
        return None

def call_llm(
    messages: list,
    system: str = "",
    model_tier: str = "fast",
    temperature: float = 0.05,
    max_tokens: int = None
) -> str:
    """Simple LLM call without repair (for backwards compatibility)"""
    result, _ = call_llm_with_repair(messages, system, model_tier, temperature, max_tokens)
    return result