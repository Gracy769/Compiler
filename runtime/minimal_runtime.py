import json
from typing import Dict, List, Any

class MinimalRuntime:
    def __init__(self):
        self.db = {}
        self.sessions = {}
        self.endpoints_called = []
    
    def execute_schema(self, schema: Dict) -> Dict:
        results = {
            "db_schema_valid": True,
            "api_schema_valid": True,
            "ui_schema_valid": True,
            "tables_created": [],
            "endpoints_registered": [],
            "pages_registered": [],
            "errors": []
        }
        
        db_schema = schema.get('schemas', {}).get('db', {})
        for table in db_schema.get('tables', []):
            table_name = table['name']
            self.db[table_name] = []
            results["tables_created"].append(table_name)
        
        api_schema = schema.get('schemas', {}).get('api', {})
        for endpoint in api_schema.get('endpoints', []):
            results["endpoints_registered"].append(f"{endpoint['method']} {endpoint['path']}")
        
        ui_schema = schema.get('schemas', {}).get('ui', {})
        for page in ui_schema.get('pages', []):
            results["pages_registered"].append(page['route'])
        
        return results
    
    def simulate_api_call(self, method: str, path: str, data: Dict = None) -> Dict:
        self.endpoints_called.append(f"{method} {path}")
        
        return {
            "success": True,
            "method": method,
            "path": path,
            "data": data,
            "message": "API call simulated successfully"
        }
    
    def validate_endpoints(self, schema: Dict) -> List[str]:
        inconsistencies = []
        
        api_endpoints = schema.get('schemas', {}).get('api', {}).get('endpoints', [])
        db_tables = {t['name'] for t in schema.get('schemas', {}).get('db', {}).get('tables', [])}
        
        for endpoint in api_endpoints:
            entity = endpoint.get('entity')
            if entity and entity not in db_tables and entity not in ['users', 'auth']:
                inconsistencies.append(f"Endpoint {endpoint['path']} references non-existent table: {entity}")
        
        ui_pages = schema.get('schemas', {}).get('ui', {}).get('pages', [])
        for page in ui_pages:
            for comp in page.get('components', []):
                entity = comp.get('entity')
                if entity and entity not in db_tables:
                    inconsistencies.append(f"Page {page['name']} component references non-existent entity: {entity}")
        
        return inconsistencies


def generate_and_validate(prompt: str) -> Dict:
    from pipeline.main import Pipeline
    
    pipeline = Pipeline()
    output, valid = pipeline.run(prompt)
    
    if not valid:
        return {"valid": False, "output": output, "execution_report": None}
    
    runtime = MinimalRuntime()
    execution_report = runtime.execute_schema(output)
    
    inconsistencies = runtime.validate_endpoints(output)
    execution_report["inconsistencies"] = inconsistencies
    execution_report["valid"] = len(inconsistencies) == 0
    
    return {
        "valid": execution_report["valid"],
        "output": output,
        "execution_report": execution_report
    }


if __name__ == "__main__":
    result = generate_and_validate("Build a CRM with login, contacts, dashboard")
    print(json.dumps(result, indent=2))