from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> core -> app -> backend -> <repo root>
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent  # the folder that contains backend/ and data/


class Settings(BaseSettings):
    # .env lives in the repository root (see .env.example); backend/.env also works
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
        populate_by_name=True,
    )

    debug: bool = False

    # --- API ---
    # "" = URLs like /auth/login. Set API_PREFIX=/api/v1 in .env to move EVERYTHING
    # (auth, notebooks, documents) under /api/v1 at once.
    api_prefix: str = ""
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    max_message_length: int = 10000

    # --- security (Task 2) ---
    secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # tokens last 24 hours

    # --- document storage (Task 3) ---
    data_dir: Path = Field(
        default=PROJECT_ROOT / "data",
        validation_alias=AliasChoices("LSN_DATA_DIR", "DATA_DIR"),
    )
    max_upload_mb: float = Field(
        default=50, validation_alias=AliasChoices("LSN_MAX_UPLOAD_MB", "MAX_UPLOAD_MB")
    )
    allowed_extensions: tuple[str, ...] = (".pdf", ".docx", ".txt", ".csv", ".xlsx")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temporary"

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


settings = Settings()
