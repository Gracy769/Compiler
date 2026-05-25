import asyncio
import json
import time
import logging
import os
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, AsyncGenerator, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-compiler")

app = FastAPI(title="AI Compiler API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from pipeline.orchestrator import Pipeline
    pipeline = Pipeline(use_llm=False)
    pipeline_llm = Pipeline(use_llm=True)
except ImportError as e:
    logger.error(f"Failed to import Pipeline: {e}")
    pipeline = None
    pipeline_llm = None

class CompileRequest(BaseModel):
    prompt: str

STAGES = [
    {"name": "1_intent_extraction", "display": "Intent Extraction", "key": "intent"},
    {"name": "2_system_design", "display": "System Design", "key": "design"},
    {"name": "3_schema_generation", "display": "Schema Generation", "key": "schemas"},
    {"name": "4_validation_refinement", "display": "Validation & Refinement", "key": "validation"},
    {"name": "5_output", "display": "Output Ready", "key": "output"},
]

tracker_store: Dict[str, 'ProgressTracker'] = {}

class ProgressTracker:
    def __init__(self, request_id: str, stages: list):
        self.request_id = request_id
        self.stages = stages
        self.current_stage = 0
        self.progress = 0
        self.start_time = time.time()
        self.is_complete = False
        self._queue = asyncio.Queue()
        self._result = None
        self.error_type: Optional[str] = None
    
    async def update_stage(self, stage_name: str, status: str, details: str = "", error: str = None):
        stage_names = [s['name'] for s in self.stages]
        if stage_name in stage_names:
            self.current_stage = stage_names.index(stage_name) + 1
            self.progress = (self.current_stage / len(self.stages)) * 100
        
        event = {
            "type": "stage_update",
            "stage": stage_name,
            "status": status,
            "progress": self.progress,
            "timestamp": time.time() - self.start_time,
            "details": details,
            "error": error,
        }
        await self._queue.put(event)
        
        if status == "completed" and self.current_stage == len(self.stages):
            self.is_complete = True
            await self._queue.put({"type": "complete", "progress": 100})
    
    async def event_stream(self) -> AsyncGenerator:
        while not self.is_complete or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
        yield "data: {\"type\": \"close\"}\n\n"

@app.get("/")
async def root():
    return FileResponse("www/index.html")

@app.post("/compile")
async def compile_endpoint(request: CompileRequest, background_tasks: BackgroundTasks):
    if pipeline_llm is None:
        return JSONResponse({"error": "Pipeline not available. Check configuration.", "success": False}, status_code=503)
    
    request_id = f"req_{int(time.time() * 1000)}"
    
    tracker = ProgressTracker(request_id, STAGES)
    tracker_store[request_id] = tracker
    
    logger.info(f"Starting compilation request {request_id}: prompt length={len(request.prompt)}")
    background_tasks.add_task(run_compiler_pipeline, request.prompt, request_id, tracker)
    
    return JSONResponse({
        "request_id": request_id,
        "success": True
    })

@app.get("/compile-stream/{request_id}")
async def compile_stream(request_id: str):
    if request_id not in tracker_store:
        return JSONResponse({"error": "Request not found"}, status_code=404)
    
    tracker = tracker_store[request_id]
    return StreamingResponse(
        tracker.event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/compile-result/{request_id}")
async def get_result(request_id: str):
    if request_id not in tracker_store:
        return JSONResponse({"error": "Request not found"}, status_code=404)
    tracker = tracker_store[request_id]
    if not tracker.is_complete:
        return JSONResponse({"error": "Still processing"}, status_code=202)
    return JSONResponse(tracker._result or {"error": "No result", "success": False})

async def run_compiler_pipeline(prompt: str, request_id: str, tracker: ProgressTracker):
    stage_timings = {}
    latency_ms = 0
    error_type = None
    
    try:
        t0 = time.time()
        logger.info(f"[{request_id}] Stage 1: Intent extraction starting")
        await tracker.update_stage("1_intent_extraction", "started", "Analyzing request...")
        
        intent = await asyncio.get_event_loop().run_in_executor(
            None, lambda: pipeline_llm.intent_extractor.extract_with_review(prompt)
        )
        intent_time = time.time() - t0
        stage_timings["1_intent_extraction"] = round(intent_time * 1000, 2)
        await tracker.update_stage("1_intent_extraction", "completed", f"Found {len(intent.get('entities', []))} entities, {len(intent.get('roles', []))} roles")
        logger.info(f"[{request_id}] Stage 1 complete: {intent_time*1000:.0f}ms")
        
        t1 = time.time()
        logger.info(f"[{request_id}] Stage 2: System design starting")
        await tracker.update_stage("2_system_design", "started", "Designing architecture...")
        design = await asyncio.get_event_loop().run_in_executor(
            None, lambda: pipeline_llm.system_designer.design_llm(intent)
        )
        design_time = time.time() - t1
        stage_timings["2_system_design"] = round(design_time * 1000, 2)
        await tracker.update_stage("2_system_design", "completed", f"Designed {len(design.get('pages', []))} pages, {len(design.get('entities', []))} entities")
        logger.info(f"[{request_id}] Stage 2 complete: {design_time*1000:.0f}ms")
        
        t2 = time.time()
        logger.info(f"[{request_id}] Stage 3: Schema generation starting")
        await tracker.update_stage("3_schema_generation", "started", "Generating schemas...")
        schemas = await asyncio.get_event_loop().run_in_executor(
            None, lambda: pipeline_llm.schema_generator.generate_llm(design)
        )
        schema_time = time.time() - t2
        stage_timings["3_schema_generation"] = round(schema_time * 1000, 2)
        await tracker.update_stage("3_schema_generation", "completed", f"Generated {len(schemas.get('db', {}).get('tables', {}))} tables, {len(schemas.get('api', {}).get('endpoints', []))} endpoints")
        logger.info(f"[{request_id}] Stage 3 complete: {schema_time*1000:.0f}ms")
        
        t3 = time.time()
        logger.info(f"[{request_id}] Stage 4: Validation starting")
        await tracker.update_stage("4_validation_refinement", "started", "Validating...")
        validation_errors = pipeline.validator.validate_cross_layer(design, schemas)
        validation_time = time.time() - t3
        stage_timings["4_validation_refinement"] = round(validation_time * 1000, 2)
        
        issues_found = []
        refinement_notes = []
        
        for err in validation_errors:
            if any(keyword in err.lower() for keyword in ['undefined', 'missing', 'no']):
                issues_found.append(f"[ERROR] {err}")
                error_type = "validation_error"
            else:
                refinement_notes.append(err)
        
        validation_status = "Validation passed" if not issues_found else f"{len(issues_found)} issues found"
        if issues_found:
            error_type = "validation_error"
        await tracker.update_stage("4_validation_refinement", "completed", validation_status)
        logger.info(f"[{request_id}] Stage 4 complete: {validation_time*1000:.0f}ms, issues={len(issues_found)}")
        
        t4 = time.time()
        await tracker.update_stage("5_output", "started", "Finalizing...")
        simulation = pipeline.simulator.simulate_execution(schemas)
        output_time = time.time() - t4
        stage_timings["5_output"] = round(output_time * 1000, 2)
        
        latency_ms = (time.time() - t0) * 1000
        
        result = {
            "success": simulation.get('can_execute', True) and len([e for e in issues_found if '[ERROR]' in e]) == 0,
            "request_id": request_id,
            "intent": intent,
            "system_design": design,
            "db_schema": schemas.get("db", {}),
            "api_schema": schemas.get("api", {}),
            "ui_schema": schemas.get("ui", {}),
            "auth_schema": schemas.get("auth", {}),
            "simulation_result": simulation,
            "issues_found": issues_found,
            "refinement_notes": refinement_notes,
            "assumptions": intent.get("assumptions", []) + intent.get("ambiguities", []),
            "metrics": {
                "latency_ms": round(latency_ms, 2),
                "stage_timings_ms": stage_timings,
                "retries": 0,
                "error_type": error_type
            }
        }
        
        tracker._result = result
        logger.info(f"[{request_id}] Complete: success={result['success']}, latency_ms={latency_ms:.0f}")
        await tracker.update_stage("5_output", "completed", "Ready!")
        
    except Exception as e:
        error_type = "runtime_error"
        logger.error(f"[{request_id}] Compilation failed: {e}")
        await tracker.update_stage("1_intent_extraction", "error", str(e))
        tracker._result = {
            "error": str(e),
            "success": False,
            "latency_ms": round((time.time() - tracker.start_time) * 1000, 2),
            "error_type": error_type
        }

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)