import json, os
from typing import Dict

SCHEMA_GENERATION_PROMPT = """You are Stage 3 of an AI compiler — Schema Generator.

Generate complete JSON schemas for all entities in the system design.
- Output ONLY raw JSON. No markdown.
- Every entity needs full CRUD operations.
- Include validation rules and relationships.

Output:
{
  "db": {
    "tables": {
      "User": {
        "fields": {
          "id": {"type": "uuid", "primary_key": true},
          "email": {"type": "string"}
        }
      }
    },
    "relationships": []
  },
  "api": {
    "endpoints": [{"path": "/users", "method": "POST", "roles": ["admin"], "table": "User"}]
  },
  "ui": {
    "pages": {"Dashboard": {"components": []}},
    "routing": {}
  },
  "auth": {
    "roles": {"admin": ["read", "write", "delete"]},
    "permissions": {}
  }
}"""

class SchemaGenerator:
    def __init__(self, schema_dir: str = None):
        self.schema_dir = schema_dir or "/home/acer_/compiler-gen/schemas"
        os.makedirs(self.schema_dir, exist_ok=True)
    
    def generate_llm(self, system_design: Dict) -> Dict:
        try:
            from pipeline.llm import call_llm
            messages = [{"role": "user", "content": f"Generate schemas:\n{json.dumps(system_design, indent=2)}"}]
            raw = call_llm(messages, system=SCHEMA_GENERATION_PROMPT, temperature=0.1)
            return self._parse_and_save(raw)
        except Exception as e:
            return self.generate_rule_based(system_design)
    
    def _parse_and_save(self, raw: str) -> Dict:
        import re
        text = re.sub(r"```(?:json)?\s*", "", raw).strip().replace("```", "").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', text)
            data = json.loads(match.group()) if match else {}
        self._save_schemas(data)
        return data
    
    def _save_schemas(self, schemas: Dict) -> None:
        for entity_name, schema in schemas.get("db", {}).get("tables", {}).items():
            path = os.path.join(self.schema_dir, f"{entity_name.lower()}.json")
            with open(path, 'w') as f:
                json.dump(schema, f, indent=2)
    
    def generate(self, system_design: Dict) -> Dict:
        return self.generate_llm(system_design)
    
    def generate_rule_based(self, system_design: Dict) -> Dict:
        entities = system_design.get("entities", [])
        roles = system_design.get("roles", [])
        pages = system_design.get("pages", [])
        
        schemas = {
            "db": {"tables": {}, "relationships": []},
            "api": {"endpoints": []},
            "ui": {"pages": {}, "routing": {}},
            "auth": {"roles": {}, "permissions": {}}
        }
        
        for entity in entities:
            name = entity.get("name", "Unknown")
            fields = entity.get("fields", [])
            
            table_fields = {}
            for field in fields:
                parts = field.split(":")
                fname = parts[0]
                ftype = parts[1] if len(parts) > 1 else "string"
                table_fields[fname] = {
                    "type": ftype,
                    "primary_key": fname == "id"
                }
            
            schemas["db"]["tables"][name] = {"fields": table_fields}
            
            plural = name.lower() + ("es" if name.lower().endswith("s") else "s")
            schemas["api"]["endpoints"].extend([
                {"path": f"/{plural}", "method": "GET", "roles": ["user", "admin"], "table": name},
                {"path": f"/{plural}", "method": "POST", "roles": ["admin"], "table": name},
                {"path": f"/{plural}/{{id}}", "method": "GET", "roles": ["user", "admin"], "table": name},
                {"path": f"/{plural}/{{id}}", "method": "PUT", "roles": ["admin"], "table": name},
                {"path": f"/{plural}/{{id}}", "method": "DELETE", "roles": ["admin"], "table": name}
            ])
        
        for role in roles:
            role_name = role.get("name", "user")
            perms = role.get("permissions", ["read"])
            schemas["auth"]["roles"][role_name] = perms
        
        for page in pages:
            page_name = page.get("name", "Unknown")
            page_route = page.get("route", "/" + page_name.lower().replace(" ", "_"))
            schemas["ui"]["pages"][page_name] = {
                "components": page.get("components", [])
            }
            schemas["ui"]["routing"][page_route] = {"page": page_name, "allowed_roles": page.get("allowed_roles", [])}
        
        self._save_schemas(schemas)
        return schemas
    
    def _fields_to_schema(self, fields: list) -> Dict:
        schema = {}
        type_map = {
            "string": "string", "text": "string", "email": "string", "uuid": "string",
            "integer": "integer", "float": "number", "boolean": "boolean",
            "timestamp": "string", "date": "string", "enum": "string"
        }
        for field in fields:
            parts = field.split(":")
            name = parts[0]
            ftype = parts[1] if len(parts) > 1 else "string"
            schema[name] = {"type": type_map.get(ftype, "string")}
            if ftype == "email":
                schema[name]["format"] = "email"
            if ftype == "uuid":
                schema[name]["format"] = "uuid"
        return schema