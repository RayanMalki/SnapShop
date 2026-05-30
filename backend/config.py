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
    use_mock_ucp: bool = True
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'snapshop.db'}"
    upload_dir: str = str(BACKEND_DIR / "uploads")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)


settings = Settings()
