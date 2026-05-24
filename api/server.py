from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

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

pipeline = Pipeline(use_llm=True)

class CompileRequest(BaseModel):
    prompt: str
    use_llm: bool = True

class CompileResponse(BaseModel):
    success: bool
    intent: dict
    design: dict
    schemas: dict
    validation: dict
    latency_ms: float
    stage_errors: list

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
    uvicorn.run(app, host="0.0.0.0", port=8000)