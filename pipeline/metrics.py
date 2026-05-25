import time
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("ai-compiler")

class MetricsTracker:
    def __init__(self):
        self.start_times: Dict[str, float] = {}
        self.stage_times: Dict[str, Dict[str, float]] = {}
        self.repair_counts: Dict[str, int] = {}
        self.completions: List[Dict] = []
    
    def reset(self) -> None:
        self.start_times.clear()
        self.stage_times.clear()
        self.repair_counts.clear()
        self.completions.clear()
        logger.info("Metrics reset")
    
    def start_timer(self, request_id: str) -> None:
        self.start_times[request_id] = time.perf_counter()
        self.stage_times[request_id] = {}
        self.repair_counts[request_id] = 0
    
    def record_stage(self, request_id: str, stage: str) -> None:
        if request_id not in self.start_times:
            logger.warning(f"start_timer not called for {request_id}")
            return
        elapsed = (time.perf_counter() - self.start_times[request_id]) * 1000
        if request_id not in self.stage_times:
            self.stage_times[request_id] = {}
        self.stage_times[request_id][stage] = elapsed
    
    def record_repair_attempts(self, request_id: str, count: int) -> None:
        self.repair_counts[request_id] = count
    
    def end_timer(self, request_id: str) -> float:
        if request_id not in self.start_times:
            logger.warning(f"start_timer not called for {request_id}")
            return 0.0
        elapsed = (time.perf_counter() - self.start_times[request_id]) * 1000
        return elapsed
    
    def log_completion(
        self,
        request_id: str,
        success: bool,
        error: Optional[str] = None,
        stage_order: Optional[List[str]] = None
    ) -> None:
        total_time_ms = self.end_timer(request_id)
        self.completions.append({
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "error": error,
            "total_time_ms": total_time_ms,
            "stages": self.stage_times.get(request_id, {}),
            "stage_order": stage_order or list(self.stage_times.get(request_id, {}).keys()),
            "repairs": self.repair_counts.get(request_id, 0)
        })
    
    def get_summary(self) -> Dict[str, Any]:
        if not self.completions:
            return {"error": "No metrics available"}
        
        total_requests = len(self.completions)
        successful = [c for c in self.completions if c['success']]
        failed = [c for c in self.completions if not c['success']]
        
        all_times = [c.get('total_time_ms', 0) for c in self.completions if c.get('total_time_ms')]
        success_times = [c.get('total_time_ms', 0) for c in successful if c.get('total_time_ms')]
        
        stage_stats = {}
        all_stages = set()
        for c in self.completions:
            all_stages.update(c.get('stage_order', []))
        
        for stage in all_stages:
            stage_times = [c['stages'].get(stage, 0) for c in self.completions if stage in c.get('stages', {})]
            if stage_times:
                stage_stats[stage] = {
                    "min_ms": round(min(stage_times), 2),
                    "max_ms": round(max(stage_times), 2),
                    "avg_ms": round(sum(stage_times) / len(stage_times), 2),
                    "count": len(stage_times)
                }
        
        return {
            "total_requests": total_requests,
            "success_count": len(successful),
            "failure_count": len(failed),
            "success_rate": round(len(successful) / total_requests * 100, 2) if total_requests > 0 else 0,
            "average_latency_ms": round(sum(all_times) / len(all_times), 2) if all_times else 0,
            "min_latency_ms": round(min(all_times), 2) if all_times else 0,
            "max_latency_ms": round(max(all_times), 2) if all_times else 0,
            "average_repairs": round(sum(c.get('repairs', 0) for c in self.completions) / total_requests, 2) if total_requests > 0 else 0,
            "stage_stats": stage_stats,
            "error_types": {
                "validation_errors": len([c for c in failed if c.get('error', '').__contains__('validation')]),
                "runtime_errors": len([c for c in failed if not c.get('error', '').__contains__('validation')])
            }
        }
    
    def to_json(self) -> str:
        return json.dumps({
            "completions": self.completions,
            "summary": self.get_summary()
        }, indent=2)
    
    def get_percentile(self, percentile: float) -> Optional[float]:
        if not self.completions:
            return None
        times = sorted([c.get('total_time_ms', 0) for c in self.completions if c.get('total_time_ms')])
        if not times:
            return None
        idx = int(len(times) * percentile / 100)
        idx = min(idx, len(times) - 1)
        return round(times[idx], 2)