from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import logging, os

from pipeline.orchestrator import Pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-compiler")

app = FastAPI(title="AI Compiler API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = Pipeline(use_llm=False)

class CompileRequest(BaseModel):
    prompt: str
    use_llm: bool = False

class CompileResponse(BaseModel):
    success: bool
    request_id: str
    intent: dict
    design: dict
    schemas: dict
    validation: dict
    simulation_result: dict
    metrics: dict
    latency_ms: float
    stage_errors: list

@app.get("/")
async def root():
    return FileResponse("www/index.html")

@app.post("/compile", response_model=CompileResponse)
async def compile_app(request: CompileRequest):
    logger.info(f"Compile request: {request.prompt[:100]}...")
    try:
        result = pipeline.compile(request.prompt)
        return CompileResponse(**result)
    except Exception as e:
        logger.error(f"Compile failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)