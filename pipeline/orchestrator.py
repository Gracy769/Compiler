import time, logging
from typing import Dict, Any
from datetime import datetime

from pipeline.intent_extractor import IntentExtractor
from pipeline.system_designer import SystemDesigner
from pipeline.schema_generator import SchemaGenerator
from pipeline.validator import Validator
from pipeline.metrics import MetricsTracker
from runtime.simulator import RuntimeSimulator

logger = logging.getLogger("ai-compiler")

class Pipeline:
    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self.intent_extractor = IntentExtractor()
        self.system_designer = SystemDesigner()
        self.schema_generator = SchemaGenerator()
        self.validator = Validator()
        self.simulator = RuntimeSimulator()
        self.metrics = MetricsTracker()
        self.results = {}
        self.request_id = 0
    
    def compile(self, prompt: str) -> Dict[str, Any]:
        self.request_id += 1
        request_id = f"req_{datetime.now().timestamp()}"
        start = time.time()
        errors = []
        self.metrics.start_timer(request_id)
        
        try:
            logger.info(f"[{request_id}] Stage 1: Extracting intent")
            intent = self.intent_extractor.extract(prompt)
            self.results["intent"] = intent
            self.metrics.record_stage(request_id, "intent_extraction")
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            errors.append(f"Intent: {str(e)}")
            intent = self.intent_extractor.extract_rule_based(prompt)
        
        try:
            logger.info(f"[{request_id}] Stage 2: Designing system")
            design = self.system_designer.design(intent)
            self.results["design"] = design
            self.metrics.record_stage(request_id, "system_design")
        except Exception as e:
            logger.error(f"System design failed: {e}")
            errors.append(f"Design: {str(e)}")
            design = self.system_designer.design_rule_based(intent)
        
        try:
            logger.info(f"[{request_id}] Stage 3: Generating schemas")
            schemas = self.schema_generator.generate(design)
            self.results["schemas"] = schemas
            self.metrics.record_stage(request_id, "schema_generation")
        except Exception as e:
            logger.error(f"Schema generation failed: {e}")
            errors.append(f"Schemas: {str(e)}")
            schemas = self.schema_generator.generate_rule_based(design)
        
        logger.info(f"[{request_id}] Stage 4: Validating")
        validation_errors = self.validator.validate_cross_layer(design, schemas)
        self.metrics.record_stage(request_id, "validation_repair")
        self.metrics.record_repair_attempts(request_id, self.validator.repair_count if hasattr(self.validator, 'repair_count') else 0)
        
        logger.info(f"[{request_id}] Stage 5: Simulating execution")
        simulation = self.simulator.simulate_execution(schemas)
        self.metrics.record_stage(request_id, "simulation")
        
        total_time = self.metrics.end_timer(request_id)
        self.metrics.log_completion(request_id, simulation['can_execute'] and len(validation_errors) == 0)
        
        return {
            "request_id": request_id,
            "intent": intent,
            "design": design,
            "schemas": schemas,
            "validation": {"valid": len(validation_errors) == 0, "errors": validation_errors},
            "simulation_result": simulation,
            "metrics": {
                "total_time_ms": total_time,
                "stages": self.metrics.stage_times.get(request_id, {}),
                "repairs": self.metrics.repair_counts.get(request_id, 0)
            },
            "latency_ms": round((time.time() - start) * 1000, 2),
            "success": simulation['can_execute'] and len(validation_errors) == 0,
            "stage_errors": errors
        }
    
    def get_results(self) -> Dict[str, Any]:
        return self.results