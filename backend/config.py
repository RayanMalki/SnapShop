from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    gemini_api_key: str = ""
    ucp_agent_profile_url: str = ""
    # The public catalog endpoint currently rejects `like` image search, so the
    # extra round-trip (which base64-encodes the whole photo) is wasted. Off by
    # default; flip on once a `like`-capable endpoint/profile is in use.
    ucp_like_search_enabled: bool = False
    # Reranker confidence below this flags the match as low_confidence (=> the UI
    # hedges with "not sure"). Higher = stricter "exact", fewer false-confident
    # silent matches. 0.6 favors honesty over claiming exactness.
    rerank_confidence_threshold: float = 0.6
    # MongoDB — local by default; set MONGODB_URL in .env to an Atlas URI for cloud.
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "snapshop"
    # Auth — JWT signing. Override JWT_SECRET in .env for anything real.
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_hours: int = 720  # 30 days — demo convenience
    upload_dir: str = str(BACKEND_DIR / "uploads")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)


settings = Settings()
