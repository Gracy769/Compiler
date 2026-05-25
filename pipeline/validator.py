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
        design_entities = {e["name"].lower(): e for e in design.get("entities", [])}
        
        if "entities" in schemas and isinstance(schemas.get("entities"), dict):
            schema_entities = {k.lower(): v for k, v in schemas.get("entities", {}).items()}
            for name, entity in design_entities.items():
                if name in schema_entities:
                    schema_entity = schema_entities[name]
                    design_fields = {f.split(":")[0] for f in entity.get("fields", [])}
                    schema_fields = set(schema_entity.get("crud", {}).get("create", {}).get("properties", {}).keys())
                    missing = design_fields - schema_fields
                    if missing:
                        errors.append(f"Entity '{name}': fields in design but not schema: {missing}")
        
        if not isinstance(design.get("roles"), list):
            errors.append("Design roles is not a list")
            return errors
        
        for role in design.get("roles", []):
            if not isinstance(role, dict):
                continue
            role_name = role.get("name", "")
            for page in design.get("pages", []):
                if not isinstance(page, dict):
                    continue
                allowed = page.get("allowed_roles", [])
                if role_name in allowed:
                    perms = role.get("permissions", [])
                    if "read" not in perms and "admin" not in perms:
                        errors.append(f"Role '{role_name}' on page '{page['route']}' has no read permission")
        
        integrations = schemas.get("intent", {}).get("integrations", []) if "intent" in schemas else []
        if len(integrations) != len(set(integrations)):
            errors.append(f"Duplicate integrations found: {integrations}")
        
        db_tables = schemas.get("db", {}).get("tables", {})
        if "deals" in [t.lower() for t in db_tables.keys()]:
            deal_table = db_tables.get("Deals", {}) or db_tables.get("deals", {})
            if deal_table:
                deal_fields = deal_table.get("fields", {})
                if "stage" not in deal_fields:
                    errors.append("Deals table missing 'stage' field for deal stages (Lead, Contacted, Negotiation, Closed)")
        
        for endpoint in schemas.get("api", {}).get("endpoints", []):
            path = endpoint.get("path", "")
            
            segments = [s for s in path.split("/") if s and not s.startswith("{")]
            for seg in segments:
                singular = seg.rstrip("s")
                if seg.endswith("ss") or seg.endswith("ies"):
                    continue
                if singular != seg and seg.endswith("s"):
                    expected_singular = self._check_pluralization(singular)
                    if expected_singular != singular:
                        errors.append(f"Possible pluralization typo in API path '{path}': '{seg}' seems incorrect, expected '{expected_singular}'")
                        break
        
        ui = schemas.get("ui", {})
        if ui and not ui.get("routing"):
            errors.append("UI routing is empty - should have routes for all pages")
        
        auth_roles = set(schemas.get("auth", {}).get("roles", {}).keys())
        ui_routes = schemas.get("ui", {}).get("routing", {})
        
        for route, config in ui_routes.items():
            for role in config.get("allowed_roles", []):
                if role not in auth_roles and role not in ("guest", "user"):
                    errors.append(f"UI route '{route}' references undefined auth role: '{role}'")
        
        api_endpoints = schemas.get("api", {}).get("endpoints", [])
        for ep in api_endpoints:
            for role in ep.get("roles", []):
                if role not in auth_roles and role not in ("guest", "user"):
                    errors.append(f"API endpoint '{ep.get('path')}' references undefined auth role: '{role}'")
        
        design_data = schemas.get("design", {}) if "design" in schemas else {}
        features = design_data.get("features", []) + schemas.get("intent", {}).get("features", []) if "intent" in schemas else design_data.get("features", [])
        features_lower = [f.lower() for f in features] if features else []
        
        if any("premium" in f or "plan" in f or "billing" in f or "payment" in f for f in features_lower):
            users_table = db_tables.get("Users", {})
            if users_table:
                fields = users_table.get("fields", {})
                if "plan" not in fields and "subscription" not in fields and "tier" not in fields:
                    errors.append("Premium/billing feature detected but Users table missing 'plan'/'subscription' field")
        
        if any("assign" in f or "task" in f for f in features_lower):
            tasks_table = db_tables.get("Tasks", {}) or db_tables.get("tasks", {})
            if tasks_table:
                fields = tasks_table.get("fields", {})
                has_assignee = any("assignee" in k.lower() for k in fields.keys())
                if not has_assignee:
                    errors.append("Task assignment mentioned but Tasks table has no assignee field")
        
        if any("real-time" in f or "websocket" in f or "live" in f for f in features_lower):
            errors.append("Real-time updates requested but no WebSocket/SSE implementation. Consider polling fallback.")
        
        if any("public" in f and "login" in f for f in features_lower):
            auth_roles_dict = schemas.get("auth", {}).get("roles", {})
            if "guest" in auth_roles_dict:
                guest_perms = auth_roles_dict["guest"]
                if "create" in guest_perms or "update" in guest_perms:
                    errors.append("Public pages + login requirement: guest role should only have 'read' permission, not create/update")
        
        return errors