import json
from typing import Dict, List

SYSTEM_DESIGN_SCHEMA = {
    "type": "object",
    "required": ["entities", "flows", "roles", "permissions", "pages"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "fields", "relations"],
                "properties": {
                    "name": {"type": "string"},
                    "fields": {"type": "array", "items": {"type": "string"}},
                    "relations": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "flows": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "steps", "actors"],
                "properties": {
                    "name": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "actors": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "roles": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "permissions"],
                "properties": {
                    "name": {"type": "string"},
                    "permissions": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "permissions": {"type": "object"},
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "route", "allowed_roles", "components"],
                "properties": {
                    "name": {"type": "string"},
                    "route": {"type": "string"},
                    "allowed_roles": {"type": "array", "items": {"type": "string"}},
                    "components": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    }
}

SYSTEM_DESIGN_PROMPT = """Generate app architecture as JSON only. No explanation.

Format:
{"entities":[{"name":"EntityName","fields":["id:uuid","name:string","created_at:timestamp"],"relations":[]}],"flows":[{"name":"FlowName","steps":["step1","step2"],"actors":["role"]}],"roles":[{"name":"rolename","permissions":["read","write"]}],"permissions":{"permName":["role"]},"pages":[{"name":"PageName","route":"/route","allowed_roles":["role"],"components":["Component"]}]}"""

class SystemDesigner:
    def design_llm(self, intent: Dict) -> Dict:
        try:
            from pipeline.llm import call_llm
            entity_names = [e.get("name") for e in intent.get("entities", [])]
            roles_info = [f"{r.get('name')}: {r.get('permissions',[])}" for r in intent.get('roles', [])]
            
            messages = [{"role": "user", "content": f"Design app architecture. Entities: {entity_names}. Roles: {roles_info}. App type: {intent.get('app_type')}. Output JSON only."}]
            raw = call_llm(messages, system=SYSTEM_DESIGN_PROMPT, temperature=0.05, model_tier="deepseek")
            return self._parse_and_validate(raw)
        except Exception as e:
            return self.design_rule_based(intent)
    
    def _parse_and_validate(self, raw: str) -> Dict:
        import jsonschema
        import re
        text = re.sub(r"```(?:json)?\s*", "", raw).strip().replace("```", "").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', text)
            data = json.loads(match.group()) if match else {}
        
        for entity in data.get("entities", []):
            fields = entity.get("fields", [])
            field_names = [f.split(":")[0] for f in fields]
            if "id" not in field_names:
                entity["fields"].insert(0, "id:uuid")
            if "created_at" not in field_names:
                entity["fields"].append("created_at:timestamp")
            if "updated_at" not in field_names:
                entity["fields"].append("updated_at:timestamp")
        
        try:
            jsonschema.validate(instance=data, schema=SYSTEM_DESIGN_SCHEMA)
        except jsonschema.ValidationError:
            pass
        
        return data
    
    def design(self, intent: Dict) -> Dict:
        return self.design_llm(intent)
    
    def design_rule_based(self, intent: Dict) -> Dict:
        entities = self._design_entities(intent)
        roles = self._design_roles(intent)
        
        return {
            "entities": entities,
            "flows": self._design_flows(entities, roles),
            "roles": roles,
            "permissions": self._generate_permissions(roles),
            "pages": self._design_pages(entities, roles)
        }
    
    def _design_entities(self, intent: Dict) -> List[Dict]:
        entities = []
        entity_names = intent.get("entities", [])
        
        base_fields = {
            'users': ['id:uuid', 'email:string', 'password_hash:string', 'role:enum', 'created_at:timestamp'],
            'contacts': ['id:uuid', 'name:string', 'email:string', 'phone:string', 'company:string', 'created_at:timestamp'],
            'customers': ['id:uuid', 'name:string', 'email:string', 'phone:string', 'address:text', 'created_at:timestamp'],
            'products': ['id:uuid', 'name:string', 'description:text', 'price:float', 'stock:integer', 'created_at:timestamp'],
            'orders': ['id:uuid', 'customer_id:uuid', 'total:float', 'status:enum', 'created_at:timestamp'],
            'payments': ['id:uuid', 'order_id:uuid', 'amount:float', 'method:string', 'status:enum', 'created_at:timestamp'],
            'invoices': ['id:uuid', 'order_id:uuid', 'amount:float', 'status:enum', 'due_date:timestamp', 'created_at:timestamp'],
        }
        
        for name in entity_names:
            fields = base_fields.get(name, ['id:uuid', 'name:string', 'created_at:timestamp'])
            entities.append({
                "name": name.title(),
                "fields": fields,
                "relations": []
            })
        
        if not entities:
            entities.append({"name": "Item", "fields": ['id:uuid', 'name:string', 'created_at:timestamp'], "relations": []})
        
        return entities
    
    def _design_roles(self, intent: Dict) -> List[Dict]:
        roles_data = intent.get("roles", [])
        roles = []
        
        for role in roles_data:
            name = role.get("name", "user") if isinstance(role, dict) else role
            if name == "admin":
                perms = ["create", "read", "update", "delete", "admin"]
            elif name == "guest":
                perms = ["read"]
            else:
                perms = ["create", "read", "update"]
            roles.append({
                "name": name,
                "permissions": perms
            })
        
        return roles
    
    def _generate_permissions(self, roles: List[Dict]) -> Dict:
        permissions = {}
        for role in roles:
            role_name = role["name"]
            perms = role.get("permissions", [])
            for perm in perms:
                if perm not in permissions:
                    permissions[perm] = []
                if role_name not in permissions[perm]:
                    permissions[perm].append(role_name)
        return permissions
    
    def _design_flows(self, entities: List[Dict], roles: List[Dict]) -> List[Dict]:
        flows = [
            {
                "name": "User Authentication",
                "steps": ["POST /auth/login", "Validate credentials", "Return JWT token"],
                "actors": ["guest"]
            },
            {
                "name": "Manage Resources",
                "steps": ["GET /{resource}", "POST /{resource}", "PUT /{resource}/:id", "DELETE /{resource}/:id"],
                "actors": list(set(r["name"] for r in roles))
            }
        ]
        return flows
    
    def _design_pages(self, entities: List[Dict], roles: List[Dict]) -> List[Dict]:
        pages = [
            {"name": "Login", "route": "/login", "allowed_roles": ["guest"], "components": ["Form"]},
            {"name": "Dashboard", "route": "/dashboard", "allowed_roles": ["user", "admin"], "components": ["StatsCard", "Table"]}
        ]
        
        for entity in entities:
            entity_name = entity["name"]
            lower = entity_name.lower()
            if lower.endswith("s"):
                plural = lower
            elif lower.endswith("y"):
                plural = lower[:-1] + "ies"
            else:
                plural = lower + "s"
            pages.append({
                "name": f"{entity_name} List",
                "route": f"/{plural}",
                "allowed_roles": ["user", "admin"],
                "components": ["Table", "SearchInput", "CreateButton"]
            })
            pages.append({
                "name": f"{entity_name} Form",
                "route": f"/{plural}/new",
                "allowed_roles": ["user", "admin"],
                "components": ["Form", "SubmitButton"]
            })
        
        return pages