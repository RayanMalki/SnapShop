import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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
from services import auth
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
    """Décode le JWT du header Authorization -> email (= user_id), sinon anonymous."""
    if not authorization or not authorization.startswith("Bearer "):
        return "anonymous"
    token = authorization.removeprefix("Bearer ").strip()
    return auth.decode_token(token) or "anonymous"


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
            try:
                result = await run_scan(contents, mime_type, voice_context=voice_context)
            except RuntimeError as exc:
                result = ScanResponse(status="error", error=str(exc))
            _scan_jobs[job_id] = result
            if result.status == "ready":
                await save_cart(user_id, result)
                await save_scan(user_id, result)

        background_tasks.add_task(_process)
        return ScanResponse(status="processing", cart_id=job_id)

    try:
        result = await run_scan(contents, mime_type, voice_context=voice_context)
    except RuntimeError as exc:
        return ScanResponse(status="error", error=str(exc))
    if result.status == "ready":
        await save_cart(user_id, result)
        await save_scan(user_id, result)
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


@app.get("/history", response_model=list[ScanResponse])
async def history(authorization: str | None = Header(default=None), limit: int = 50):
    user_id = _user_id_from_auth(authorization)
    return await get_history(user_id, limit=limit)


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


@app.post("/auth/signup", response_model=LoginResponse)
async def signup(body: LoginRequest):
    email = _normalize_email(body.email)
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    try:
        await create_user(email, auth.hash_password(body.password))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return LoginResponse(token=auth.create_token(email), user_id=email)


@app.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    email = _normalize_email(body.email)
    user = await get_user(email) if email else None
    if not user or not auth.verify_password(body.password or "", user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return LoginResponse(token=auth.create_token(email), user_id=email)
