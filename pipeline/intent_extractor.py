import json, re
from typing import Dict, List, Any

INTENT_SCHEMA = {
    "type": "object",
    "required": ["app_name", "app_type", "features", "entities", "roles", "integrations", "ambiguities"],
    "properties": {
        "app_name":      {"type": "string"},
        "app_type":      {"type": "string", "enum": ["crm", "ecommerce", "saas", "dashboard", "marketplace", "custom"]},
        "features":      {"type": "array", "items": {"type": "string"}},
        "entities":      {"type": "array", "items": {"type": "string"}},
        "roles":         {"type": "array", "items": {"type": "string"}},
        "integrations": {"type": "array", "items": {"type": "string"}},
        "ambiguities":   {"type": "array", "items": {"type": "string"}},
        "assumptions":   {"type": "array", "items": {"type": "string"}}
    }
}

INTENT_PROMPT = """Extract app intent from user request.

Output ONLY valid JSON (no markdown):
{"app_name":"Name","app_type":"crm|ecommerce|saas|dashboard|marketplace|custom","features":["Feature1"],"entities":["entity1"],"roles":["admin","user"],"integrations":[],"ambiguities":[],"assumptions":[]}

Rules:
- features: max 10 items, be specific (e.g. "User Authentication" not just "auth")
- entities: data objects plural (users, products, orders)
- roles: user roles (admin, customer, vendor, etc)
- app_type: choose one
- integrations: external services (Stripe, SendGrid, Auth0)

class IntentExtractor:
    def __init__(self):
        self.entity_keywords = {
            'contact': 'contacts', 'user': 'users', 'customer': 'customers',
            'product': 'products', 'order': 'orders', 'invoice': 'invoices',
            'payment': 'payments', 'task': 'tasks', 'project': 'projects',
            'company': 'companies', 'lead': 'leads', 'deal': 'deals',
            'ticket': 'tickets', 'article': 'articles', 'post': 'posts',
            'comment': 'comments', 'category': 'categories', 'tag': 'tags'
        }
        self.role_keywords = {
            'admin': 'admin', 'administrator': 'admin', 'user': 'user', 
            'customer': 'customer', 'guest': 'guest', 'manager': 'manager',
            'vendor': 'vendor', 'doctor': 'doctor', 'patient': 'patient'
        }
    
    def extract(self, prompt: str) -> Dict[str, Any]:
        return self.extract_llm(prompt)
    
    def extract_llm(self, prompt: str) -> Dict:
        try:
            from pipeline.llm import generate_and_review
            
            raw, was_reviewed = generate_and_review(
                user_prompt=f"Extract intent:\n\n{prompt}",
                system_prompt=INTENT_PROMPT,
                review_task="Ensure app_name, app_type, features[], entities[], roles[], integrations[] are all present and valid",
                max_tokens=4096
            )
            logger.info(f"Intent: reviewed={was_reviewed}")
            return self._parse_and_repair(raw)
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}, using rule-based")
            return self.extract_rule_based(prompt)
    
    def _parse_and_repair(self, raw: str) -> Dict:
        import jsonschema
        text = re.sub(r"```(?:json)?\s*", "", raw).strip().replace("```", "").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError("Failed to parse JSON")
        
        try:
            jsonschema.validate(instance=data, schema=INTENT_SCHEMA)
        except jsonschema.ValidationError:
            data.setdefault("assumptions", [])
            data.setdefault("ambiguities", [])
            if not data.get("roles"):
                data["roles"] = ["user", "admin"]
                data["assumptions"].append("Default roles assumed")
        
        return data
    
    def extract_rule_based(self, prompt: str) -> Dict:
        prompt_lower = prompt.lower()
        entities = self._extract_entities(prompt_lower)
        roles = self._extract_roles(prompt_lower)
        features = self._extract_features(prompt, entities, roles)
        integrations = self._detect_integrations(prompt_lower)
        app_type = self._detect_app_type(prompt_lower)
        
        intent = {
            "app_name": self._generate_app_name(prompt),
            "app_type": app_type,
            "features": list(set(features)),
            "entities": list(set(entities)),
            "roles": roles,
            "integrations": list(set(integrations)),
            "ambiguities": [],
            "assumptions": []
        }
        
        if len(roles) == 1:
            intent["assumptions"].append("Added complementary role")
            if roles[0]["name"] == "admin":
                intent["roles"].append({"name": "user", "permissions": ["create", "read", "update"]})
            else:
                intent["roles"].append({"name": "admin", "permissions": ["create", "read", "update", "delete", "admin"]})
        
        return intent
    
    def _extract_entities(self, text: str) -> List[str]:
        found = set()
        entities = []
        for keyword, entity_name in self.entity_keywords.items():
            if keyword in text and entity_name not in found:
                entities.append(entity_name)
                found.add(entity_name)
        return entities
    
    def _extract_roles(self, text: str) -> List[Dict]:
        roles = []
        seen = set()
        for keyword, role in self.role_keywords.items():
            if keyword in text and role not in seen:
                perms = ['read'] if role != 'admin' else ['create', 'read', 'update', 'delete', 'admin']
                roles.append({"name": role, "permissions": perms})
                seen.add(role)
        return roles if roles else [{"name": "user", "permissions": ["create", "read", "update"]}]
    
    def _extract_features(self, prompt: str, entities: List, roles: List) -> List[str]:
        features = []
        prompt_lower = prompt.lower()
        
        feature_keywords = {
            'login': 'Authentication', 'register': 'Registration', 'dashboard': 'Dashboard',
            'analytics': 'Analytics', 'payment': 'Payments', 'billing': 'Billing',
            'search': 'Search', 'filter': 'Filtering', 'export': 'Export', 'import': 'Import',
            'chat': 'Chat', 'messaging': 'Messaging', 'notification': 'Notifications'
        }
        
        for keyword, feature in feature_keywords.items():
            if keyword in prompt_lower:
                features.append(feature)
        
        for entity in entities:
            features.append(f"{entity.title()} CRUD")
        
        return list(set(features))
    
    def _detect_integrations(self, text: str) -> List[str]:
        integration_map = {
            'stripe': 'Stripe', 'payment': 'Stripe', 'email': 'SendGrid',
            'sms': 'Twilio', 'auth': 'Auth0', 'analytics': 'Mixpanel',
            'slack': 'Slack', 'github': 'GitHub', 'google': 'Google OAuth'
        }
        return [name for key, name in integration_map.items() if key in text]
    
    def _detect_app_type(self, text: str) -> str:
        type_signatures = {
            'crm': ['crm', 'customer relationship', 'contacts', 'leads', 'deals'],
            'ecommerce': ['ecommerce', 'shop', 'store', 'cart', 'checkout'],
            'saas': ['saas', 'subscription', 'multi-tenant'],
            'dashboard': ['dashboard', 'analytics', 'metrics', 'reporting'],
            'marketplace': ['marketplace', 'vendor', 'seller']
        }
        for app_type, signatures in type_signatures.items():
            if any(sig in text for sig in signatures):
                return app_type
        return 'custom'
    
    def _generate_app_name(self, prompt: str) -> str:
        words = [w for w in prompt.split() if len(w) > 3 and w.lower() not in 
                ['crm', 'user', 'admin', 'build', 'create', 'make', 'with', 'that', 'this']]
        return ''.join(w.capitalize() for w in words[:3]) or 'MyApp'