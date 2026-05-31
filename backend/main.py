import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from database import get_cart, init_db, save_cart
from models.schemas import HealthResponse, LoginRequest, LoginResponse, ScanResponse
from services.pipeline import run_scan

# In-memory scan jobs for optional async processing (demo: sync by default)
_scan_jobs: dict[str, ScanResponse] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Snap & Shop API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _user_id_from_auth(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return "anonymous"
    return authorization.removeprefix("Bearer ").strip() or "anonymous"


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.post("/scan", response_model=ScanResponse)
async def scan(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    voice_context: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
    async_mode: bool = False,
):
    contents = await file.read()
    mime_type = file.content_type or "image/jpeg"

    user_id = _user_id_from_auth(authorization)

    if async_mode:
        job_id = uuid.uuid4().hex
        _scan_jobs[job_id] = ScanResponse(status="processing")

        async def _process():
            result = await run_scan(contents, mime_type, voice_context=voice_context)
            _scan_jobs[job_id] = result
            if result.status == "ready":
                await save_cart(user_id, result)

        background_tasks.add_task(_process)
        return ScanResponse(status="processing", cart_id=job_id)

    result = await run_scan(contents, mime_type, voice_context=voice_context)
    if result.status == "ready":
        await save_cart(user_id, result)
    return result


@app.get("/scan/{job_id}", response_model=ScanResponse)
async def scan_status(job_id: str):
    job = _scan_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/cart/current", response_model=ScanResponse)
async def cart_current(authorization: str | None = Header(default=None)):
    user_id = _user_id_from_auth(authorization)
    cart = await get_cart(user_id)
    if not cart:
        return ScanResponse(status="processing")
    return cart


@app.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    # Minimal demo auth — replace with Supabase/Clerk/Sign in with Apple
    user_id = body.email or "demo-user"
    return LoginResponse(token=f"demo-token-{user_id}", user_id=user_id)
