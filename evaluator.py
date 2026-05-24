import json
import time
from typing import Dict
from pipeline.orchestrator import Pipeline

class Evaluator:
    def __init__(self):
        self.real_prompts = [
            {"id": "p1", "prompt": "Build a CRM with contact management, deal tracking, and task assignment. Include admin and sales roles.", "expected_complexity": "complex"},
            {"id": "p2", "prompt": "Create a blog platform with post creation, comments, and user profiles.", "expected_complexity": "medium"},
            {"id": "p3", "prompt": "Make an e-commerce store with products, shopping cart, and Stripe payment integration.", "expected_complexity": "complex"},
            {"id": "p4", "prompt": "Build a task management app with due dates, priorities, and team assignment.", "expected_complexity": "medium"},
            {"id": "p5", "prompt": "Create a social media dashboard showing posts, mentions, and analytics from Twitter and Facebook.", "expected_complexity": "complex"},
            {"id": "p6", "prompt": "Build an inventory management system with stock tracking, reorder alerts, and supplier management.", "expected_complexity": "complex"},
            {"id": "p7", "prompt": "Make a team collaboration tool with chat, file sharing, and project boards.", "expected_complexity": "complex"},
            {"id": "p8", "prompt": "Create a customer support ticketing system with priority levels, assignment, and SLAs.", "expected_complexity": "complex"},
            {"id": "p9", "prompt": "Build a learning management system with courses, quizzes, and progress tracking.", "expected_complexity": "complex"},
            {"id": "p10", "prompt": "Create an event booking platform with calendar, payments, and email confirmations.", "expected_complexity": "complex"}
        ]
        
        self.edge_case_prompts = [
            {"id": "e1", "prompt": "Make an app.", "type": "vague", "expected_behavior": "ask_clarification"},
            {"id": "e2", "prompt": "Build a social network where everyone is anonymous but all posts are public and require login to view.", "type": "conflicting", "expected_behavior": "resolve_conflict"},
            {"id": "e3", "prompt": "Create a dashboard.", "type": "incomplete", "expected_behavior": "make_assumptions"},
            {"id": "e4", "prompt": "Build a tool that's both a public website and requires login for everything.", "type": "conflicting", "expected_behavior": "resolve_conflict"},
            {"id": "e5", "prompt": "Make a system with infinite scalability and zero cost.", "type": "unrealistic", "expected_behavior": "document_constraints"},
            {"id": "e6", "prompt": "Create a CRM with payments but no user data storage.", "type": "conflicting", "expected_behavior": "resolve_conflict"},
            {"id": "e7", "prompt": "Build something.", "type": "extremely_vague", "expected_behavior": "ask_clarification"},
            {"id": "e8", "prompt": "Make an app that does everything (CRM, e-commerce, social, analytics, payments, chat, video, AI) for 10 users.", "type": "overscoped", "expected_behavior": "prioritize_features"},
            {"id": "e9", "prompt": "Build a system with no database but user accounts.", "type": "conflicting", "expected_behavior": "resolve_conflict"},
            {"id": "e10", "prompt": "Create a real-time chat app that works offline.", "type": "technical_conflict", "expected_behavior": "document_limitations"}
        ]
        
        self.results = []
        self.pipeline = Pipeline()
    
    def evaluate_all(self) -> Dict:
        all_prompts = [(p, "real") for p in self.real_prompts] + [(p, "edge") for p in self.edge_case_prompts]
        
        for prompt, category in all_prompts:
            result = self._evaluate_single(prompt, category)
            self.results.append(result)
        
        return self._generate_report()
    
    def _evaluate_single(self, prompt_data: Dict, category: str) -> Dict:
        prompt = prompt_data["prompt"]
        start_time = time.time()
        
        try:
            output = self.pipeline.compile(prompt)
            latency = time.time() - start_time
            
            sim = output.get("simulation_result", {})
            
            return {
                "test_id": prompt_data["id"],
                "prompt": prompt,
                "category": category,
                "type": prompt_data.get("type", ""),
                "expected_behavior": prompt_data.get("expected_behavior", ""),
                "valid": output.get("success", False),
                "latency": output.get("latency_ms", latency * 1000) / 1000,
                "errors": output.get("validation", {}).get("errors", []),
                "simulation_passed": sim.get("can_execute", False),
                "checks_passed": len(sim.get("checks_passed", [])),
                "checks_failed": len(sim.get("checks_failed", [])),
                "entities_count": len(output.get("design", {}).get("entities", [])),
                "pages_count": len(output.get("design", {}).get("pages", [])),
                "endpoints_count": len(output.get("schemas", {}).get("api", {}).get("endpoints", []))
            }
        except Exception as e:
            latency = time.time() - start_time
            return {
                "test_id": prompt_data["id"],
                "prompt": prompt,
                "category": category,
                "type": prompt_data.get("type", ""),
                "valid": False,
                "latency": latency,
                "errors": [{"type": "exception", "message": str(e)}],
                "simulation_passed": False
            }
    
    def _generate_report(self) -> Dict:
        real_results = [r for r in self.results if r['category'] == 'real']
        edge_results = [r for r in self.results if r['category'] == 'edge']
        
        real_successful = sum(1 for r in real_results if r['valid'])
        edge_successful = sum(1 for r in edge_results if r['valid'])
        
        metrics = {
            "total_prompts": len(self.results),
            "real_prompts": len(real_results),
            "edge_prompts": len(edge_results),
            "success_rate": sum(1 for r in self.results if r['valid']) / len(self.results) * 100,
            "real_success_rate": real_successful / max(1, len(real_results)) * 100,
            "edge_success_rate": edge_successful / max(1, len(edge_results)) * 100,
            "avg_latency_ms": sum(r['latency'] for r in self.results) / max(1, len(self.results)) * 1000,
            "failure_types": self._count_failure_types(),
            "avg_entities": sum(r['entities_count'] for r in self.results) / max(1, len(self.results)),
            "avg_pages": sum(r['pages_count'] for r in self.results) / max(1, len(self.results)),
            "avg_endpoints": sum(r['endpoints_count'] for r in self.results) / max(1, len(self.results)),
            "simulation_summary": {
                "passed": sum(1 for r in self.results if r.get('simulation_passed')),
                "failed": sum(1 for r in self.results if not r.get('simulation_passed'))
            },
            "per_prompt_results": self.results
        }
        
        return metrics
    
    def _count_failure_types(self) -> Dict:
        types = {}
        for r in self.results:
            if not r['valid']:
                for err in r.get('errors', []):
                    err_type = err.get('type', 'unknown')
                    types[err_type] = types.get(err_type, 0) + 1
        return types
    
    def print_report(self, metrics: Dict):
        print("=" * 60)
        print("EVALUATION REPORT")
        print("=" * 60)
        print(f"Total Prompts: {metrics['total_prompts']}")
        print(f"  Real prompts: {metrics['real_prompts']}")
        print(f"  Edge case prompts: {metrics['edge_prompts']}")
        print()
        print(f"Success Rate: {metrics['success_rate']:.1f}%")
        print(f"  Real prompts: {metrics['real_success_rate']:.1f}%")
        print(f"  Edge prompts: {metrics['edge_success_rate']:.1f}%")
        print()
        print(f"Simulation:")
        print(f"  Passed: {metrics['simulation_summary']['passed']}")
        print(f"  Failed: {metrics['simulation_summary']['failed']}")
        print()
        print(f"Avg Latency: {metrics['avg_latency_ms']:.1f}ms")
        print()
        print("Failure Types:")
        for ft, count in metrics['failure_types'].items():
            print(f"  {ft}: {count}")
        print()
        print("Output Averages:")
        print(f"  Entities: {metrics['avg_entities']:.1f}")
        print(f"  Pages: {metrics['avg_pages']:.1f}")
        print(f"  Endpoints: {metrics['avg_endpoints']:.1f}")
        print("=" * 60)


if __name__ == "__main__":
    evaluator = Evaluator()
    metrics = evaluator.evaluate_all()
    evaluator.print_report(metrics)
    
    with open('/home/acer_/compiler-gen/evaluation_report.json', 'w') as f:
        json.dump(metrics, f, indent=2, default=str)