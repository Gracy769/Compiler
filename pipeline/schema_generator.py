import json, os, logging
from typing import Dict

logger = logging.getLogger("ai-compiler")

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
        draft = self.generate_rule_based(system_design)
        
        try:
            from pipeline.llm import review_with_model
            draft_json = json.dumps(draft)
            corrected, was_fixed = review_with_model(
                draft_json,
                "Ensure db.tables has fields with types, api.endpoints has CRUD paths with methods and roles, ui.pages and ui.routing populated, auth.roles has permissions"
            )
            if was_fixed:
                draft = json.loads(corrected)
                logger.info(f"Schema: MiniMax fixed={was_fixed}")
        except Exception as e:
            logger.warning(f"Schema review failed: {e}")
        
        return draft
    
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
            relations = entity.get("relations", [])
            
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
            
            entity_roles = []
            for role in roles:
                rn = role.get("name", "")
                perms = role.get("permissions", [])
                if any(p in perms or "admin" in perms for p in ["create", "read", "update"]):
                    entity_roles.append(rn)

            lower_name = name.lower()
            if lower_name.endswith("s"):
                plural = lower_name
            elif lower_name.endswith("y"):
                plural = lower_name[:-1] + "ies"
            else:
                plural = lower_name + "s"
            
            read_roles = entity_roles if entity_roles else ["user", "admin"]
            write_roles = ["admin"] if "admin" in [r.get("name") for r in roles] else entity_roles

            schemas["api"]["endpoints"].extend([
                {"path": f"/{plural}", "method": "GET", "roles": read_roles, "table": name},
                {"path": f"/{plural}", "method": "POST", "roles": write_roles, "table": name},
                {"path": f"/{plural}/{{id}}", "method": "GET", "roles": read_roles, "table": name},
                {"path": f"/{plural}/{{id}}", "method": "PUT", "roles": write_roles, "table": name},
                {"path": f"/{plural}/{{id}}", "method": "DELETE", "roles": ["admin"], "table": name}
            ])
            
            if relations:
                for rel in relations:
                    schemas["db"]["relationships"].append({
                        "from": name,
                        "to": rel.get("target", ""),
                        "type": rel.get("type", "many-to-one"),
                        "foreign_key": rel.get("foreign_key", "")
                    })
        
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