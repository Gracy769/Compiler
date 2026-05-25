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

ENTITY_KEYWORDS = {
    'user': 'users', 'contact': 'contacts', 'customer': 'customers',
    'product': 'products', 'order': 'orders', 'invoice': 'invoices',
    'payment': 'payments', 'task': 'tasks', 'project': 'projects',
    'company': 'companies', 'lead': 'leads', 'deal': 'deals',
    'ticket': 'tickets', 'article': 'articles', 'post': 'posts',
    'comment': 'comments', 'category': 'categories', 'tag': 'tags',
    'doctor': 'doctors', 'patient': 'patients', 'appointment': 'appointments',
    'inventory': 'inventory', 'vendor': 'vendors', 'subscription': 'subscriptions',
    'driver': 'drivers', 'vehicle': 'vehicles', 'trip': 'trips',
    'delivery': 'deliveries', 'restaurant': 'restaurants',
    'passenger': 'passengers', 'ride': 'rides', 'booking': 'bookings',
    'location': 'locations', 'address': 'addresses', 'rating': 'ratings',
    'review': 'reviews', 'route': 'routes', 'zone': 'zones',
    'bag': 'bags', 'insulated': 'bags', 'map': 'maps', 'request': 'requests',
    'dispatch': 'dispatches', 'clinic': 'clinics', 'tenant': 'tenants',
    'medical_record': 'medical_records', 'prescription': 'prescriptions',
    'chat': 'chats', 'message': 'messages', 'notification': 'notifications',
    'subscription': 'subscriptions', 'plan': 'plans', 'tier': 'tiers',
    'analytics': 'analytics', 'report': 'reports', 'dashboard': 'dashboards',
    'item': 'items', 'cart': 'carts', 'checkout': 'checkouts',
    'shipment': 'shipments', 'tracking': 'trackings',
    'auth': 'auth', 'token': 'tokens', 'session': 'sessions',
    'email': 'emails', 'sms': 'sms', 'webhook': 'webhooks'
}

ROLE_KEYWORDS = {
    'admin': 'admin', 'administrator': 'admin', 
    'user': 'user', 'customer': 'customer', 'guest': 'guest', 
    'manager': 'manager', 'vendor': 'vendor', 'doctor': 'doctor', 
    'patient': 'patient', 'editor': 'editor', 'viewer': 'viewer', 
    'owner': 'owner', 'moderator': 'moderator', 'agent': 'agent',
    'driver': 'driver', 'rider': 'rider', 'passenger': 'passenger',
    'globaladmin': 'global_admin', 'global_admin': 'global_admin',
    'clinicmanager': 'clinic_manager', 'clinic_manager': 'clinic_manager',
    'superadmin': 'super_admin', 'super_admin': 'super_admin',
    'tenant': 'tenant', 'member': 'member', 'subscriber': 'subscriber',
    'staff': 'staff', 'rep': 'rep', 'representative': 'rep'
}

FEATURE_KEYWORDS = {
    'login': 'Passwordless Magic Link Auth', 'register': 'Registration',
    'signup': 'Registration', 'magic link': 'Passwordless Magic Link Auth',
    '2fa': '2FA Authentication', 'mfa': '2FA Authentication',
    'dashboard': 'Dashboard', 'analytics': 'Analytics', 'reporting': 'Reporting',
    'payment': 'Payments', 'billing': 'Billing', 'checkout': 'Checkout',
    'search': 'Search', 'filter': 'Filtering', 'sort': 'Sorting',
    'export': 'Export', 'import': 'Import', 'chat': 'Chat', 'messaging': 'Messaging',
    'notification': 'Notifications', 'email': 'Email Notifications', 
    'sms': 'SMS Notifications', 'push': 'Push Notifications',
    'comment': 'Comments', 'like': 'Likes', 'follow': 'Follow', 'post': 'Posts',
    'review': 'Reviews', 'rating': 'Ratings', 'star': 'Ratings',
    'cart': 'Shopping Cart', 'order': 'Order Management', 'refund': 'Refunds',
    'crud': 'CRUD Operations', 'api': 'REST API',
    'map': 'Map View', 'location': 'Location Tracking', 'gps': 'GPS Tracking',
    'tracking': 'Real-time Tracking', 'realtime': 'Real-time Updates',
    'booking': 'Booking System', 'reservation': 'Reservations',
    'dispatch': 'Auto Dispatch', 'routing': 'Route Optimization',
    'multi_tenant': 'Multi-tenancy', 'saas': 'SaaS Features',
    'role': 'Role-based Access', 'permission': 'Permissions',
    'auth': 'Authentication', 'passwordless': 'Passwordless Auth',
    'dark mode': 'Dark Mode', 'darkmode': 'Dark Mode',
    'insulated bag': 'Insulated Bags', ' insulated': 'Insulated Bags',
    '5-star': 'Rating System', '5 star': 'Rating System',
    'closest': 'Closest Driver Matching', 'auto-assign': 'Auto Assignment',
    'reject': 'Driver Rejection', 'accept': 'Accept Flow',
    '30 second': '30s Acceptance Timer', '30sec': '30s Acceptance Timer',
    'magic link': 'Magic Link Auth', 'email auth': 'Email Auth',
    'corporate': 'Corporate 2FA', 'token': '2FA Token'
}

class IntentExtractor:
    def extract(self, prompt: str) -> Dict[str, Any]:
        return self.extract_rule_based(prompt)
    
    def extract_with_review(self, prompt: str) -> Dict[str, Any]:
        draft = self.extract_rule_based(prompt)
        
        try:
            from pipeline.llm import review_with_minimax
            draft_json = json.dumps(draft)
            corrected, was_fixed = review_with_minimax(
                draft_json,
                "Ensure app_name, app_type, features[], entities[], roles[], integrations[] are all present and comprehensive"
            )
            if was_fixed:
                draft = json.loads(corrected)
                logger.info(f"Intent: MiniMax fixed={was_fixed}")
        except Exception as e:
            logger.warning(f"Intent review failed: {e}")
        
        return draft
    
    def extract_rule_based(self, prompt: str) -> Dict:
        prompt_lower = prompt.lower()
        entities = self._extract_entities(prompt_lower, prompt)
        roles = self._extract_roles(prompt_lower, prompt)
        features = self._extract_features(prompt, entities, roles)
        integrations = self._detect_integrations(prompt_lower)
        app_type = self._detect_app_type(prompt_lower)
        ambiguities = self._detect_ambiguities(prompt, entities, roles)
        
        app_name = self._generate_app_name(prompt)
        
        intent = {
            "app_name": app_name,
            "app_type": app_type,
            "features": list(set(features)),
            "entities": list(set(entities)),
            "roles": roles,
            "integrations": list(set(integrations)),
            "ambiguities": ambiguities,
            "assumptions": []
        }
        
        if len(roles) == 1:
            intent["assumptions"].append("Added complementary role for balanced access")
            if roles[0]["name"] == "admin":
                intent["roles"].append({"name": "user", "permissions": ["create", "read", "update"]})
            else:
                intent["roles"].append({"name": "admin", "permissions": ["create", "read", "update", "delete", "admin"]})
        
        if not any('map' in f.lower() or 'location' in f.lower() for f in features):
            if any(k in prompt_lower for k in ['driver', 'ride', 'delivery', 'trip', 'route']):
                intent["features"].append("Map View")
        
        return intent
    
    def _extract_entities(self, text: str, full_prompt: str) -> List[str]:
        found = set()
        entities = []
        
        for keyword, entity_name in ENTITY_KEYWORDS.items():
            if keyword in text and entity_name not in found:
                if keyword == 'insulated' and 'bag' not in text:
                    continue
                entities.append(entity_name)
                found.add(entity_name)
        
        composite_patterns = [
            (r'driver[s]?(?:s)?', 'drivers'),
            (r'food (?:delivery|box)', 'deliveries'),
            (r'medical record', 'medical_records'),
            (r'prescription', 'prescriptions'),
            (r'insulated bag', 'bags'),
        ]
        for pattern, entity in composite_patterns:
            if re.search(pattern, text) and entity not in found:
                entities.append(entity)
                found.add(entity)
        
        if not entities:
            entities.append("items")
        
        return entities
    
    def _extract_roles(self, text: str, full_prompt: str) -> List[Dict]:
        roles = []
        seen = set()
        
        for keyword, role in ROLE_KEYWORDS.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', text) and role not in seen:
                perms = self._get_role_permissions(role)
                roles.append({"name": role, "permissions": perms})
                seen.add(role)
        
        if 'admin' in text and 'user' not in seen and 'customer' not in seen:
            roles.append({"name": "user", "permissions": ["create", "read", "update"]})
        
        if not roles:
            roles.append({"name": "user", "permissions": ["create", "read", "update"]})
        
        return roles
    
    def _get_role_permissions(self, role: str) -> List[str]:
        if role == 'admin' or role == 'global_admin' or role == 'super_admin':
            return ["create", "read", "update", "delete", "admin"]
        elif role == 'manager' or role == 'clinic_manager':
            return ["create", "read", "update"]
        elif role == 'guest' or role == 'viewer':
            return ["read"]
        elif role == 'moderator':
            return ["create", "read", "update", "delete"]
        else:
            return ["create", "read", "update"]
    
    def _extract_features(self, prompt: str, entities: List, roles: List) -> List[str]:
        features = []
        prompt_lower = prompt.lower()
        
        for keyword, feature in FEATURE_KEYWORDS.items():
            if keyword.lower() in prompt_lower and feature not in features:
                features.append(feature)
        
        for entity in entities:
            if entity not in ['items', 'auth', 'tokens', 'sessions', 'emails', 'sms', 'webhooks']:
                features.append(f"{entity.title()} CRUD")
        
        auth_features = set()
        has_passwordless = 'magic link' in prompt_lower or 'passwordless' in prompt_lower
        has_2fa = '2fa' in prompt_lower or 'mfa' in prompt_lower or 'corporate' in prompt_lower or 'token' in prompt_lower
        
        if has_passwordless and has_2fa:
            auth_features.add("Passwordless Magic Link Auth")
            auth_features.add("Corporate 2FA (Username + Password + Token)")
        elif has_passwordless:
            auth_features.add("Passwordless Magic Link Auth")
        elif has_2fa:
            auth_features.add("Username/Password Auth with 2FA Token")
        
        if 'driver' in prompt_lower:
            auth_features.add("Driver Status (Online/Offline)")
            if any(k in prompt_lower for k in ['30 second', '30sec', '30s']):
                auth_features.add("30s Driver Acceptance Timer")
            if any(k in prompt_lower for k in ['insulated', 'bag']):
                auth_features.add("Insulated Bag Indicator for Drivers")
        
        if 'reject' in prompt_lower or 'accept' in prompt_lower:
            auth_features.add("Driver Accept/Reject Flow")
        
        if 'closest' in prompt_lower or 'closest driver' in prompt_lower:
            auth_features.add("Closest Driver Auto-Assignment")
        
        if 'hybrid' in prompt_lower and ('ride' in prompt_lower or 'food' in prompt_lower):
            auth_features.add("Hybrid Ride/Food Delivery")
        
        if 'dark mode' in prompt_lower or 'darkmode' in prompt_lower:
            auth_features.add("Dark Mode Toggle")
        
        features.extend(list(auth_features))
        
        return list(set(features))
    
    def _detect_integrations(self, text: str) -> List[str]:
        integration_map = {
            'stripe': 'Stripe', 'payment': 'Stripe', 'checkout': 'Stripe',
            'sendgrid': 'SendGrid', 'email': 'SendGrid', 'mail': 'SendGrid',
            'twilio': 'Twilio', 'sms': 'Twilio',
            'auth': 'Auth0', 'auth0': 'Auth0',
            'mapbox': 'Mapbox', 'map': 'Mapbox', 'google maps': 'Google Maps',
            'openstreetmap': 'OpenStreetMap', 'osmium': 'OpenStreetMap',
            'slack': 'Slack', 'github': 'GitHub', 'google': 'Google OAuth',
            'facebook': 'Facebook', 'twitter': 'Twitter', 'instagram': 'Instagram',
            'firebase': 'Firebase', 'firestore': 'Firebase',
            'aws': 'AWS', 's3': 'AWS S3',
            'postgres': 'PostgreSQL', 'mysql': 'MySQL', 'mongodb': 'MongoDB'
        }
        return [name for key, name in integration_map.items() if key in text]
    
    def _detect_app_type(self, text: str) -> str:
        type_signatures = {
            'crm': ['crm', 'customer relationship', 'contacts', 'leads', 'deals'],
            'ecommerce': ['ecommerce', 'shop', 'store', 'cart', 'checkout', 'product catalog'],
            'saas': ['saas', 'subscription', 'multi-tenant', 'multi tenant'],
            'dashboard': ['dashboard', 'analytics', 'metrics', 'reporting'],
            'marketplace': ['marketplace', 'vendor', 'seller', 'buyer'],
            'social': ['social', 'post', 'like', 'comment', 'follow', 'feed'],
            'healthcare': ['patient', 'doctor', 'medical', 'health', 'clinic'],
            'booking': ['booking', 'appointment', 'reservation', 'ticket'],
            'ride': ['ride-sharing', 'ride sharing', 'rideshare', 'taxi', 'driver'],
            'delivery': ['delivery', 'food delivery', 'courier', 'logistics']
        }
        for app_type, signatures in type_signatures.items():
            if any(sig in text for sig in signatures):
                return app_type
        return 'custom'
    
    def _detect_ambiguities(self, prompt: str, entities: List, roles: List) -> List[str]:
        ambiguities = []
        prompt_lower = prompt.lower()
        
        if 'hybrid' in prompt_lower and ('but' in prompt_lower or 'however' in prompt_lower or 'except' in prompt_lower):
            ambiguities.append("Hybrid app with conflicting requirements - may need conditional logic")
        
        if 'magic link' in prompt_lower and 'admin' in prompt_lower:
            ambiguities.append("Admin 2FA requires username/password - may conflict with passwordless user auth")
        
        if 'admin' in roles and 'user' in [r['name'] for r in roles]:
            if 'globaladmin' in prompt_lower or 'superadmin' in prompt_lower:
                ambiguities.append("Multiple admin tiers detected - ensure proper hierarchy")
        
        if 'reject' in prompt_lower and 'auto' in prompt_lower and '30' not in prompt_lower:
            ambiguities.append("Auto-assignment with rejection needs clear timeout definition")
        
        return ambiguities
    
    def _generate_app_name(self, prompt: str) -> str:
        stop_words = {'crm', 'user', 'admin', 'build', 'create', 'make', 'with', 'that', 'this', 'the', 'a', 'an', 'for', 'and', 'or', 'but', 'hybrid', 'app', 'application'}
        words = [w for w in prompt.split() if len(w) > 3 and w.lower() not in stop_words]
        name = ''.join(w.capitalize() for w in words[:3]) or 'MyApp'
        
        if 'ride' in prompt.lower() and 'delivery' in prompt.lower():
            name = 'RideDeliveryHub'
        elif 'ride' in prompt.lower() or 'driver' in prompt.lower():
            name = name or 'RideShareApp'
        elif 'delivery' in prompt.lower() or 'food' in prompt.lower():
            name = name or 'DeliveryApp'
        
        return name