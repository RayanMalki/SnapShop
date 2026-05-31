import uuid

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import HealthResponse, ScanResponse
from services.pipeline import run_scan

# In-memory scan jobs for optional async processing (demo: sync by default).
_scan_jobs: dict[str, ScanResponse] = {}

app = FastAPI(title="Snap & Shop API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.post("/scan", response_model=ScanResponse)
async def scan(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    voice_context: str | None = Form(default=None),
    async_mode: bool = False,
):
    contents = await file.read()
    mime_type = file.content_type or "image/jpeg"

    if async_mode:
        job_id = uuid.uuid4().hex
        _scan_jobs[job_id] = ScanResponse(status="processing")

        async def _process():
            try:
                result = await run_scan(contents, mime_type, voice_context=voice_context)
            except RuntimeError as exc:
                result = ScanResponse(status="error", error=str(exc))
            _scan_jobs[job_id] = result

        background_tasks.add_task(_process)
        return ScanResponse(status="processing", cart_id=job_id)

    try:
        result = await run_scan(contents, mime_type, voice_context=voice_context)
    except RuntimeError as exc:
        return ScanResponse(status="error", error=str(exc))
    return result


@app.get("/scan/{job_id}", response_model=ScanResponse)
async def scan_status(job_id: str):
    job = _scan_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
