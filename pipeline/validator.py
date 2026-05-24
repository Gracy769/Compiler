import json, re, jsonschema
from typing import Dict, Tuple, List, Any

REPAIR_MARKDOWN_RE = re.compile(r"```(?:json)?\s*|\s*```")
REPAIR_BRACE_RE   = re.compile(r"\{[\s\S]*\}")

class ValidationResult:
    def __init__(self, valid: bool, data: Any = None, errors: List[str] = None, repaired: bool = False):
        self.valid   = valid
        self.data    = data
        self.errors  = errors or []
        self.repaired = repaired
    
    def __repr__(self):
        status = "VALID" if self.valid else "INVALID"
        if self.repaired: status += " (repaired)"
        return f"<ValidationResult {status} errors={self.errors}>"

class Validator:
    def __init__(self):
        self.schemas = {}
    
    def repair_json(self, raw: str) -> str:
        raw = raw.strip()
        raw = REPAIR_MARKDOWN_RE.sub("", raw)
        raw = raw.strip()
        if not raw.startswith("{"):
            m = REPAIR_BRACE_RE.search(raw)
            raw = m.group() if m else raw
        return raw
    
    def safe_json_parse(self, text: str) -> Tuple[bool, Any, str]:
        repaired_text = self.repair_json(text)
        try:
            return True, json.loads(repaired_text), ""
        except json.JSONDecodeError as e:
            return False, None, str(e)
    
    def validate(self, data: Any, schema: Dict, level: int = 1) -> ValidationResult:
        try:
            jsonschema.validate(instance=data, schema=schema)
            return ValidationResult(valid=True, data=data)
        except jsonschema.ValidationError as e:
            return self._repair_and_validate(data, schema, e, level)
    
    def _repair_and_validate(self, data: Any, schema: Dict, original_error: Exception, level: int) -> ValidationResult:
        if level == 1:
            repaired = self._level1_repair(data, schema)
        elif level == 2:
            repaired = self._level2_repair(data, schema)
        else:
            repaired = self._level3_repair(data, schema)
        
        if repaired is None:
            return ValidationResult(valid=False, data=data, errors=[str(original_error)], repaired=False)
        
        try:
            jsonschema.validate(instance=repaired, schema=schema)
            return ValidationResult(valid=True, data=repaired, repaired=True)
        except jsonschema.ValidationError as e:
            return ValidationResult(valid=False, data=repaired, errors=[str(e)], repaired=True)
    
    def _level1_repair(self, data: Any, schema: Dict) -> Any:
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key in schema.get("properties", {}):
                    expected = schema["properties"][key]["type"]
                    if expected == "array" and not isinstance(value, list):
                        result[key] = [value] if value else []
                    elif expected == "object" and not isinstance(value, dict):
                        result[key] = {"value": value} if value else {}
                    else:
                        result[key] = value
                else:
                    result[key] = value
            return result
        return data
    
    def _level2_repair(self, data: Any, schema: Dict) -> Any:
        if isinstance(data, dict):
            result = {}
            required = set(schema.get("required", []))
            for req in required:
                if req not in data:
                    result[req] = self._default_for_type(schema["properties"].get(req, {}).get("type", "string"))
            for key, value in data.items():
                if key in schema.get("properties", {}):
                    prop_schema = schema["properties"][key]
                    result[key] = self._coerce_type(value, prop_schema.get("type", "string"))
                else:
                    result[key] = value
            return result
        return data
    
    def _level3_repair(self, data: Any, schema: Dict) -> Any:
        repaired = self._level2_repair(data, schema)
        if not isinstance(repaired, dict):
            return None
        return repaired
    
    def _default_for_type(self, ftype: str) -> Any:
        defaults = {"string": "", "array": [], "object": {}, "boolean": False, "integer": 0, "number": 0.0}
        return defaults.get(ftype, None)
    
    def _coerce_type(self, value: Any, ftype: str) -> Any:
        if ftype == "integer":
            try: return int(value)
            except: return 0
        if ftype == "number":
            try: return float(value)
            except: return 0.0
        return value
    
    def validate_cross_layer(self, design: Dict, schemas: Dict) -> List[str]:
        errors = []
        design_entities = {e["name"].lower(): e for e in design.get("entities", [])}
        
        if "entities" in schemas:
            schema_entities = {k.lower(): v for k, v in schemas.get("entities", {}).items()}
            for name, entity in design_entities.items():
                if name in schema_entities:
                    schema_entity = schema_entities[name]
                    design_fields = {f.split(":")[0] for f in entity.get("fields", [])}
                    schema_fields = set(schema_entity.get("crud", {}).get("create", {}).get("properties", {}).keys())
                    missing = design_fields - schema_fields
                    if missing:
                        errors.append(f"Entity '{name}': fields in design but not schema: {missing}")
        
        for role in design.get("roles", []):
            role_name = role.get("name", "")
            for page in design.get("pages", []):
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
            if path.endswith("ss") and "sses" not in path and "/ss/" not in path:
                errors.append(f"Possible pluralization typo in API path: {path}")
        
        ui = schemas.get("ui", {})
        if ui and not ui.get("routing"):
            errors.append("UI routing is empty - should have routes for all pages")
        
        return errors