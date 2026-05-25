import json, re, logging
from typing import Dict, List, Any

logger = logging.getLogger("ai-compiler")

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

class IntentExtractor:
    def __init__(self):
        self.entity_keywords = {
            'contact': 'contacts', 'user': 'users', 'customer': 'customers',
            'product': 'products', 'order': 'orders', 'invoice': 'invoices',
            'payment': 'payments', 'task': 'tasks', 'project': 'projects',
            'company': 'companies', 'lead': 'leads', 'deal': 'deals',
            'ticket': 'tickets', 'article': 'articles', 'post': 'posts',
            'comment': 'comments', 'category': 'categories', 'tag': 'tags',
            'doctor': 'doctors', 'patient': 'patients', 'appointment': 'appointments',
            'inventory': 'inventory', 'vendor': 'vendors', 'subscription': 'subscriptions'
        }
        self.role_keywords = {
            'admin': 'admin', 'administrator': 'admin', 'user': 'user', 
            'customer': 'customer', 'guest': 'guest', 'manager': 'manager',
            'vendor': 'vendor', 'doctor': 'doctor', 'patient': 'patient',
            'editor': 'editor', 'viewer': 'viewer', 'owner': 'owner'
        }
    
    def extract(self, prompt: str) -> Dict[str, Any]:
        return self.extract_rule_based(prompt)
    
    def extract_with_review(self, prompt: str) -> Dict[str, Any]:
        """Rule-based extraction + MiniMax review"""
        draft = self.extract_rule_based(prompt)
        
        try:
            from pipeline.llm import review_with_minimax
            draft_json = json.dumps(draft)
            corrected, was_fixed = review_with_minimax(
                draft_json,
                "Ensure app_name, app_type, features[], entities[], roles[], integrations[] are all present"
            )
            if was_fixed:
                draft = json.loads(corrected)
                logger.info(f"Intent: MiniMax fixed={was_fixed}")
        except Exception as e:
            logger.warning(f"Intent review failed: {e}")
        
        return draft
    
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
        return entities if entities else ["items"]
    
    def _extract_roles(self, text: str) -> List[Dict]:
        roles = []
        seen = set()
        for keyword, role in self.role_keywords.items():
            if keyword in text and role not in seen:
                perms = ['create', 'read', 'update'] if role != 'admin' else ['create', 'read', 'update', 'delete', 'admin']
                roles.append({"name": role, "permissions": perms})
                seen.add(role)
        return roles if roles else [{"name": "user", "permissions": ["create", "read", "update"]}]
    
    def _extract_features(self, prompt: str, entities: List, roles: List) -> List[str]:
        features = []
        prompt_lower = prompt.lower()
        
        feature_keywords = {
            'login': 'Authentication', 'register': 'Registration', 'signup': 'Registration',
            'dashboard': 'Dashboard', 'analytics': 'Analytics', 'payment': 'Payments',
            'billing': 'Billing', 'search': 'Search', 'filter': 'Filtering',
            'export': 'Export', 'import': 'Import', 'chat': 'Chat', 'messaging': 'Messaging',
            'notification': 'Notifications', 'email': 'Email Notifications', 'sms': 'SMS Notifications',
            'comment': 'Comments', 'like': 'Likes', 'follow': 'Follow', 'post': 'Posts',
            'review': 'Reviews', 'rating': 'Ratings', 'cart': 'Shopping Cart',
            'checkout': 'Checkout', 'order': 'Orders', 'refund': 'Refunds'
        }
        
        for keyword, feature in feature_keywords.items():
            if keyword in prompt_lower:
                features.append(feature)
        
        for entity in entities:
            if entity != 'items':
                features.append(f"{entity.title()} CRUD")
        
        return list(set(features))
    
    def _detect_integrations(self, text: str) -> List[str]:
        integration_map = {
            'stripe': 'Stripe', 'payment': 'Stripe', 'email': 'SendGrid',
            'sms': 'Twilio', 'auth': 'Auth0', 'analytics': 'Mixpanel',
            'slack': 'Slack', 'github': 'GitHub', 'google': 'Google OAuth',
            'facebook': 'Facebook', 'twitter': 'Twitter', 'instagram': 'Instagram'
        }
        return [name for key, name in integration_map.items() if key in text]
    
    def _detect_app_type(self, text: str) -> str:
        type_signatures = {
            'crm': ['crm', 'customer relationship', 'contacts', 'leads', 'deals'],
            'ecommerce': ['ecommerce', 'shop', 'store', 'cart', 'checkout'],
            'saas': ['saas', 'subscription', 'multi-tenant'],
            'dashboard': ['dashboard', 'analytics', 'metrics', 'reporting'],
            'marketplace': ['marketplace', 'vendor', 'seller'],
            'social': ['social', 'post', 'like', 'comment', 'follow', 'feed'],
            'healthcare': ['patient', 'doctor', 'medical', 'health', 'clinic'],
            'booking': ['booking', 'appointment', 'reservation', 'ticket']
        }
        for app_type, signatures in type_signatures.items():
            if any(sig in text for sig in signatures):
                return app_type
        return 'custom'
    
    def _generate_app_name(self, prompt: str) -> str:
        stop_words = {'crm', 'user', 'admin', 'build', 'create', 'make', 'with', 'that', 'this', 'the', 'a', 'an', 'for', 'and', 'or', 'but'}
        words = [w for w in prompt.split() if len(w) > 3 and w.lower() not in stop_words]
        return ''.join(w.capitalize() for w in words[:3]) or 'MyApp'