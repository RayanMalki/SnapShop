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
    # Reranker confidence below this flags the match as low_confidence.
    rerank_confidence_threshold: float = 0.5
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'snapshop.db'}"
    upload_dir: str = str(BACKEND_DIR / "uploads")

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        if not path.is_absolute():
            return BACKEND_DIR / path
        return path


settings = Settings()
