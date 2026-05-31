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
    # Gemini 2.5 Flash enables dynamic thinking by default. Product extraction
    # and shortlist ranking are latency-sensitive structured tasks, so disable
    # hidden reasoning unless a deployment explicitly opts back in with -1.
    gemini_thinking_budget: int = 0
    # Keep model choice and shortlist size configurable for controlled latency
    # experiments. Defaults preserve the stronger visual matching path.
    gemini_analysis_model: str = "gemini-2.5-flash"
    gemini_rerank_model: str = "gemini-2.5-flash"
    rerank_shortlist: int = 18
    ucp_agent_profile_url: str = ""
    # The public catalog endpoint currently rejects `like` image search, so the
    # extra round-trip (which base64-encodes the whole photo) is wasted. Off by
    # default; flip on once a `like`-capable endpoint/profile is in use.
    ucp_like_search_enabled: bool = False
    # Reranker confidence below this flags the match as low_confidence (=> the UI
    # hedges with "not sure"). Higher = stricter "exact", fewer false-confident
    # silent matches. 0.6 favors honesty over claiming exactness.
    rerank_confidence_threshold: float = 0.6
    upload_dir: str = str(BACKEND_DIR / "uploads")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)


settings = Settings()
