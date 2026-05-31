import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import HealthResponse, ScanResponse
from services.pipeline import run_scan

# In-memory scan jobs for optional async processing (demo: sync by default).
_scan_jobs: dict[str, ScanResponse] = {}

app = FastAPI(title="Snap & Shop API")
from pymongo.errors import DuplicateKeyError

from database import (
    create_user,
    get_cart,
    get_history,
    get_user,
    init_db,
    save_cart,
    save_scan,
)
from models.schemas import HealthResponse, LoginRequest, LoginResponse, ScanResponse
from services import auth, ucp, vision
from services.pipeline import run_scan

logger = logging.getLogger(__name__)

# In-memory scan jobs for optional async processing (demo: sync by default)
_scan_jobs: dict[str, ScanResponse] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await asyncio.gather(
            ucp.close_http_client(),
            vision.close_http_client(),
        )


app = FastAPI(title="Snap & Shop API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _user_id_from_auth(authorization: str | None) -> str:
    """Décode le JWT du header Authorization -> email (= user_id), sinon anonymous."""
    if not authorization or not authorization.startswith("Bearer "):
        return "anonymous"
    token = authorization.removeprefix("Bearer ").strip()
    return auth.decode_token(token) or "anonymous"


async def _persist_scan(user_id: str, result: ScanResponse) -> None:
    started = perf_counter()
    await asyncio.gather(
        save_cart(user_id, result),
        save_scan(user_id, result),
    )
    logger.info("scan timing: persistence %.3fs", perf_counter() - started)


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
    if result.status == "ready":
        background_tasks.add_task(_persist_scan, user_id, result)
    return result


@app.get("/scan/{job_id}", response_model=ScanResponse)
async def scan_status(job_id: str):
    job = _scan_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
