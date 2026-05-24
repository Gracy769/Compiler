from typing import Dict, Any, List
from datetime import datetime
import json

class MetricsTracker:
    def __init__(self):
        self.start_times = {}
        self.stage_times = {}
        self.repair_counts = {}
        self.completions = []
    
    def start_timer(self, request_id: str):
        self.start_times[request_id] = datetime.now()
    
    def record_stage(self, request_id: str, stage: str):
        if request_id not in self.stage_times:
            self.stage_times[request_id] = {}
        elapsed = (datetime.now() - self.start_times[request_id]).total_seconds() * 1000
        self.stage_times[request_id][stage] = elapsed
    
    def record_repair_attempts(self, request_id: str, count: int):
        self.repair_counts[request_id] = count
    
    def end_timer(self, request_id: str) -> float:
        end_time = datetime.now()
        return (end_time - self.start_times[request_id]).total_seconds() * 1000
    
    def log_completion(self, request_id: str, success: bool, error: str = None):
        self.completions.append({
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "error": error,
            "total_time_ms": (datetime.now() - self.start_times.get(request_id, datetime.now())).total_seconds() * 1000,
            "stages": self.stage_times.get(request_id, {}),
            "repairs": self.repair_counts.get(request_id, 0)
        })
    
    def get_summary(self) -> Dict:
        if not self.completions:
            return {"error": "No metrics available"}
        
        successful = [c for c in self.completions if c['success']]
        return {
            "total_requests": len(self.completions),
            "success_rate": len(successful) / len(self.completions) * 100,
            "average_repairs": sum(c.get('repairs', 0) for c in self.completions) / len(self.completions),
            "average_total_time": sum(c.get('total_time_ms', 0) for c in self.completions if c.get('total_time_ms')) / len(self.completions)
        }