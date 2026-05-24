import json
import time
from typing import Dict

from pipeline.orchestrator import Pipeline

class Compiler:
    def __init__(self):
        self.pipeline = Pipeline()
        self.metrics = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "latency": []
        }
    
    def run(self, prompt: str) -> Dict:
        self.metrics["total_requests"] += 1
        start_time = time.time()
        
        try:
            result = self.pipeline.compile(prompt)
            latency = time.time() - start_time
            self.metrics["latency"].append(latency)
            
            if result.get("success"):
                self.metrics["successful"] += 1
            else:
                self.metrics["failed"] += 1
            
            return {
                "intent": result.get("intent"),
                "design": result.get("design"),
                "schemas": result.get("schemas"),
                "validation_report": result.get("validation"),
                "latency_seconds": latency,
                "success": result.get("success"),
                "metadata": {
                    "pipeline_version": "2.0",
                    "generated_at": time.time()
                }
            }
        except Exception as e:
            latency = time.time() - start_time
            self.metrics["latency"].append(latency)
            self.metrics["failed"] += 1
            return {"error": str(e), "latency_seconds": latency}, False
    
    def get_metrics(self) -> Dict:
        latency = self.metrics["latency"]
        return {
            "total_requests": self.metrics["total_requests"],
            "successful": self.metrics["successful"],
            "failed": self.metrics["failed"],
            "success_rate": self.metrics["successful"] / max(1, self.metrics["total_requests"]),
            "avg_latency": sum(latency) / max(1, len(latency)) if latency else 0,
            "min_latency": min(latency) if latency else 0,
            "max_latency": max(latency) if latency else 0
        }

def generate(prompt: str) -> Dict:
    compiler = Compiler()
    return compiler.run(prompt)

if __name__ == "__main__":
    compiler = Compiler()
    
    test_prompts = [
        "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics.",
        "Create an ecommerce store with products, cart, checkout, and order management",
        "Build a blog with articles, comments, and user authentication",
        "Create a project management tool with tasks, teams, and deadlines"
    ]
    
    for i, prompt in enumerate(test_prompts):
        print(f"\n{'='*50}")
        print(f"Test {i+1}: {prompt[:50]}...")
        print('='*50)
        
        output = compiler.run(prompt)
        
        print(f"Success: {output.get('success', False)}")
        print(f"Latency: {output.get('latency_seconds', 0):.3f}s")
        
        if output.get("success") and "design" in output:
            design = output["design"]
            print(f"Entities: {[e['name'] for e in design.get('entities', [])]}")
            print(f"Pages: {[p['name'] for p in design.get('pages', [])][:5]}")