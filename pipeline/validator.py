import json, re, jsonschema, logging
from typing import Dict, Tuple, List, Any, Optional
from functools import lru_cache

logger = logging.getLogger("ai-compiler")

REPAIR_MARKDOWN_RE = re.compile(r"```(?:json)?\s*|\s*```")
REPAIR_BRACE_RE = re.compile(r"\{[\s\S]*\}")
REPAIR_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
PLURAL_IRREGULAR = {
    "person": "people", "man": "men", "woman": "women", "child": "children",
    "tooth": "teeth", "foot": "feet", "mouse": "mice", "ox": "oxen",
    "cactus": "cacti", "focus": "foci", "fungus": "fungi", "nucleus": "nuclei",
    "radius": "radii", "stimulus": "stimuli", "syllabus": "syllabi",
    "analysis": "analyses", "crisis": "crises", "diagnosis": "diagnoses",
    "hypothesis": "hypotheses", "thesis": "theses", "phenomenon": "phenomena",
    "criterion": "criteria", "datum": "data"
}
PLURAL_RULES = [
    (re.compile(r"(s|x|z|ch|sh)$"), r"\1es"),
    (re.compile(r"([^aeiou])y$"), r"\1ies"),
    (re.compile(r"(?:f|fe)$"), r"ves"),
    (re.compile(r"ss$"), r"sses"),
]

class ValidationResult:
    def __init__(self, valid: bool, data: Any = None, errors: List[str] = None, repaired: bool = False, repairs_log: List[str] = None):
        self.valid = valid
        self.data = data
        self.errors = errors or []
        self.repaired = repaired
        self.repairs_log = repairs_log or []
    
    def __repr__(self):
        status = "VALID" if self.valid else "INVALID"
        if self.repaired: status += " (repaired)"
        return f"<ValidationResult {status} errors={self.errors}>"

class Validator:
    _validator_cache: Dict[str, jsonschema.Draft7Validator] = {}
    
    def __init__(self):
        self.schemas = {}
    
    def repair_json(self, raw: str) -> List[str]:
        repairs = []
        raw = raw.strip()
        raw = REPAIR_MARKDOWN_RE.sub("", raw).strip()
        
        texts = []
        if raw.startswith("["):
            matches = REPAIR_ARRAY_RE.findall(raw)
            texts.extend(matches)
        elif raw.startswith("{"):
            matches = REPAIR_BRACE_RE.findall(raw)
            texts.extend(matches)
        else:
            brace_matches = REPAIR_BRACE_RE.findall(raw)
            array_matches = REPAIR_ARRAY_RE.findall(raw)
            texts = brace_matches + array_matches
        
        if not texts:
            texts = [raw]
        
        repaired_texts = []
        for text in texts:
            try:
                json.loads(text)
                repaired_texts.append(text)
            except json.JSONDecodeError:
                try:
                    from json_repair import repair_json as repair
                    fixed = repair(text)
                    repairs.append(f"json_repair fixed: {text[:50]}...")
                    repaired_texts.append(fixed)
                except ImportError:
                    repaired_texts.append(text)
        
        if len(repaired_texts) > 1:
            repairs.append(f"Multiple JSON fragments found: {len(repaired_texts)} pieces")
            return repaired_texts, repairs
        
        return repaired_texts, repairs
    
    def safe_json_parse(self, text: str) -> Tuple[bool, Any, str, List[str]]:
        repairs = []
        texts, repair_log = self.repair_json(text)
        repairs.extend(repair_log)
        
        for attempt, t in enumerate(texts):
            try:
                return True, json.loads(t), "", repairs
            except json.JSONDecodeError as e:
                if attempt == len(texts) - 1:
                    return False, None, str(e), repairs
        return False, None, "Failed to parse JSON", repairs
    
    @classmethod
    def _get_cached_validator(cls, schema: Dict) -> jsonschema.Draft7Validator:
        schema_str = json.dumps(schema, sort_keys=True)
        if schema_str not in cls._validator_cache:
            cls._validator_cache[schema_str] = jsonschema.Draft7Validator(schema)
        return cls._validator_cache[schema_str]
    
    def validate(self, data: Any, schema: Dict, level: int = 1) -> ValidationResult:
        try:
            validator = self._get_cached_validator(schema)
            validator.validate(data)
            return ValidationResult(valid=True, data=data)
        except jsonschema.ValidationError as e:
            return self._repair_and_validate(data, schema, e, level)
    
    def _repair_and_validate(self, data: Any, schema: Dict, original_error: Exception, level: int) -> ValidationResult:
        all_errors = [str(original_error)]
        repairs_log = []
        
        if level == 1:
            repaired, log = self._level1_repair(data, schema)
            repairs_log.extend(log)
        elif level == 2:
            repaired, log = self._level2_repair(data, schema)
            repairs_log.extend(log)
        else:
            repaired, log = self._level3_repair(data, schema)
            repairs_log.extend(log)
        
        if repaired is None:
            return ValidationResult(valid=False, data=data, errors=all_errors, repairs_log=repairs_log)
        
        try:
            validator = self._get_cached_validator(schema)
            validator.validate(repaired)
            logger.info(f"Validator repairs applied: {repairs_log}")
            return ValidationResult(valid=True, data=repaired, repaired=True, repairs_log=repairs_log)
        except jsonschema.ValidationError as e:
            all_errors.append(str(e))
            logger.warning(f"Validator repair failed at level {level}: {all_errors}")
            return ValidationResult(valid=False, data=repaired, errors=all_errors, repaired=True, repairs_log=repairs_log)
    
    def _level1_repair(self, data: Any, schema: Dict) -> Tuple[Any, List[str]]:
        repairs = []
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key in schema.get("properties", {}):
                    expected = schema["properties"][key]["type"]
                    if expected == "array" and not isinstance(value, list):
                        result[key] = [value] if value else []
                        repairs.append(f"Coerced '{key}' to array")
                    elif expected == "object" and not isinstance(value, dict):
                        result[key] = {"value": value} if value else {}
                        repairs.append(f"Coerced '{key}' to object wrapper")
                    else:
                        result[key] = value
                else:
                    result[key] = value
            return result, repairs
        return data, repairs
    
    def _level2_repair(self, data: Any, schema: Dict) -> Tuple[Any, List[str]]:
        repairs = []
        if isinstance(data, dict):
            result = {}
            required = set(schema.get("required", []))
            for req in required:
                if req not in data:
                    default = self._default_for_type(schema["properties"].get(req, {}).get("type", "string"))
                    result[req] = default
                    repairs.append(f"Added missing required field '{req}' with default")
            for key, value in data.items():
                if key in schema.get("properties", {}):
                    prop_schema = schema["properties"][key]
                    result[key], coerced = self._coerce_type_verbose(value, prop_schema.get("type", "string"))
                    if coerced:
                        repairs.append(coerced)
                else:
                    result[key] = value
            return result, repairs
        return data, repairs
    
    def _level3_repair(self, data: Any, schema: Dict) -> Tuple[Any, List[str]]:
        repaired, repairs = self._level2_repair(data, schema)
        if not isinstance(repaired, dict):
            return None, repairs
        return repaired, repairs
    
    def _default_for_type(self, ftype: str) -> Any:
        defaults = {
            "string": "", "array": [], "object": {},
            "boolean": False, "integer": 0, "number": 0.0,
            "null": None
        }
        return defaults.get(ftype, "")
    
    def _coerce_type_verbose(self, value: Any, ftype: str) -> Tuple[Any, Optional[str]]:
        if ftype == "integer":
            try:
                return int(value), None
            except (ValueError, TypeError) as e:
                logger.warning(f"Type coercion failed: {value} -> integer: {e}")
                return 0, f"Coerced '{value}' to integer (was {type(value).__name__})"
        if ftype == "number":
            try:
                return float(value), None
            except (ValueError, TypeError) as e:
                logger.warning(f"Type coercion failed: {value} -> number: {e}")
                return 0.0, f"Coerced '{value}' to float (was {type(value).__name__})"
        if ftype == "boolean" and not isinstance(value, bool):
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes"), f"Coerced '{value}' to boolean"
            return bool(value), f"Coerced '{value}' to boolean"
        if ftype == "array" and not isinstance(value, list):
            return [value] if value else [], f"Coerced '{value}' to array"
        if ftype == "object" and not isinstance(value, dict):
            return {"value": value} if value else {}, f"Coerced '{value}' to object"
        return value, None
    
    def _check_pluralization(self, word: str) -> str:
        if word.lower() in PLURAL_IRREGULAR:
            return PLURAL_IRREGULAR[word.lower()]
        for pattern, replacement in PLURAL_RULES:
            if pattern.search(word):
                return pattern.sub(replacement, word)
        return word + "s"
    
    def validate_cross_layer(self, design: Dict, schemas: Dict) -> List[str]:
        errors = []
        warnings = []
        design_entities = {e["name"].lower(): e for e in design.get("entities", [])}
        
        if not isinstance(design.get("roles"), list):
            errors.append("Design roles is not a list")
            return errors
        
        db_tables = schemas.get("db", {}).get("tables", {})
        auth_roles = set(schemas.get("auth", {}).get("roles", {}).keys())
        api_endpoints = schemas.get("api", {}).get("endpoints", [])
        ui_routes = schemas.get("ui", {}).get("routing", {})
        
        all_roles_in_design = {r["name"] for r in design.get("roles", [])}
        missing_auth_roles = all_roles_in_design - auth_roles
        if missing_auth_roles and len(missing_auth_roles) < len(all_roles_in_design):
            warnings.append(f"Some roles not in auth schema: {missing_auth_roles}")
        
        for endpoint in api_endpoints:
            path = endpoint.get("path", "")
            segments = [s for s in path.split("/") if s and not s.startswith("{")]
            for seg in segments:
                if seg in ("users", "trips", "drivers", "payments", "orders", "reviews", "ratings", 
                          "notifications", "locations", "maps", "bags", "rides", "deliveries",
                          "restaurants", "addresses", "products", "transactions", "subscriptions",
                          "appointments", "prescriptions", "medical_records", "clinics", "staff",
                          "tokens", "sessions", "audit_logs"):
                    continue
        
        ui = schemas.get("ui", {})
        if ui and not ui.get("routing") and db_tables:
            warnings.append("UI routing is empty - should have routes for all pages")
        
        design_data = schemas.get("design", {}) if "design" in schemas else {}
        features = design_data.get("features", []) + schemas.get("intent", {}).get("features", []) if "intent" in schemas else design_data.get("features", [])
        features_lower = [f.lower() for f in features] if features else []
        
        if any("real-time" in f or "websocket" in f or "live" in f for f in features_lower):
            warnings.append("Real-time updates requested - no WebSocket/SSE in schema")
        
        if features_lower and any("public" in f and "login" in f for f in features_lower):
            if "guest" in auth_roles:
                guest_perms = schemas.get("auth", {}).get("roles", {}).get("guest", [])
                if "create" in guest_perms or "update" in guest_perms:
                    warnings.append("Guest role has create/update perms - consider restricting to read-only for public pages")
        
        return errors + warnings