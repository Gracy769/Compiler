from typing import Dict, Any, List

class RuntimeSimulator:
    def __init__(self):
        pass
    
    def simulate_execution(self, schemas: Dict[str, Any]) -> Dict[str, Any]:
        results = {
            "can_execute": True,
            "checks_passed": [],
            "checks_failed": [],
            "warnings": [],
            "execution_plan": [],
            "estimated_performance": {}
        }
        
        db_check = self._check_database(schemas.get('db', {}))
        if db_check['valid']:
            results['checks_passed'].append("Database schema is valid")
        else:
            results['checks_failed'].extend(db_check['errors'])
            results['can_execute'] = False
        
        api_check = self._check_api(schemas.get('api', {}))
        if api_check['valid']:
            results['checks_passed'].append("API routes are valid")
        else:
            results['checks_failed'].extend(api_check['errors'])
            results['can_execute'] = False
        
        ui_check = self._check_ui(schemas.get('ui', {}))
        if ui_check['valid']:
            results['checks_passed'].append("UI components are valid")
        else:
            results['warnings'].extend(ui_check['warnings'])
        
        auth_check = self._check_auth(schemas.get('auth', {}))
        if auth_check['valid']:
            results['checks_passed'].append("Auth rules are consistent")
        else:
            results['checks_failed'].extend(auth_check['errors'])
        
        results['execution_plan'] = self._generate_execution_plan(schemas)
        results['estimated_performance'] = self._estimate_performance(schemas)
        
        return results
    
    def _check_database(self, db_schema: Dict) -> Dict:
        errors = []
        tables = db_schema.get('tables', {})
        
        if not tables:
            errors.append("No tables defined")
            return {"valid": False, "errors": errors}
        
        for table_name, table_config in tables.items():
            fields = table_config.get('fields', {})
            if not fields:
                errors.append(f"Table '{table_name}' has no fields")
            has_primary = any(f.get('primary_key') for f in fields.values() if isinstance(f, dict))
            if not has_primary:
                errors.append(f"Table '{table_name}' has no primary key")
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    def _check_api(self, api_schema: Dict) -> Dict:
        errors = []
        endpoints = api_schema.get('endpoints', [])
        
        if not endpoints:
            errors.append("No API endpoints defined")
        
        paths = [(e.get('path'), e.get('method', '').upper()) for e in endpoints if isinstance(e, dict)]
        if len(paths) != len(set(paths)):
            errors.append("Duplicate API paths detected")
        
        valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
        for endpoint in endpoints:
            if isinstance(endpoint, dict):
                method = endpoint.get('method', '').upper()
                if method not in valid_methods:
                    errors.append(f"Invalid HTTP method: {method}")
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    def _check_ui(self, ui_schema: Dict) -> Dict:
        warnings = []
        if not ui_schema.get('pages'):
            warnings.append("No pages defined")
        if not ui_schema.get('routing'):
            warnings.append("No routing configuration")
        return {"valid": True, "warnings": warnings}
    
    def _check_auth(self, auth_schema: Dict) -> Dict:
        errors = []
        if not auth_schema.get('roles'):
            errors.append("No roles defined")
        return {"valid": len(errors) == 0, "errors": errors}
    
    def _generate_execution_plan(self, schemas: Dict) -> List[Dict]:
        return [
            {"step": 1, "action": "Initialize database", "details": "Create tables and relationships", "status": "pending"},
            {"step": 2, "action": "Setup API server", "details": "Create endpoints and middleware", "status": "pending"},
            {"step": 3, "action": "Configure auth system", "details": "Setup roles and permissions", "status": "pending"},
            {"step": 4, "action": "Generate frontend", "details": "Create pages and components", "status": "pending"}
        ]
    
    def _estimate_performance(self, schemas: Dict) -> Dict:
        db_tables = len(schemas.get('db', {}).get('tables', {}))
        api_endpoints = len(schemas.get('api', {}).get('endpoints', []))
        ui_pages = len(schemas.get('ui', {}).get('pages', {}))
        complexity_score = db_tables + api_endpoints + ui_pages
        
        if complexity_score < 10:
            performance = "Fast response times (<100ms)"
        elif complexity_score < 30:
            performance = "Good performance (100-300ms)"
        else:
            performance = "May need optimization (300ms+)"
        
        return {
            "complexity_score": complexity_score,
            "estimated_performance": performance,
            "db_tables": db_tables,
            "api_endpoints": api_endpoints,
            "ui_pages": ui_pages
        }