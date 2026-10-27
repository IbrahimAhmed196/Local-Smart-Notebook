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
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:3000")

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
    # --- presentations (Task 3) ---
    max_presentation_slides: int = 20

    # --- chat answers (Ollama) ---
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "LSN_OLLAMA_URL"),
    )
    chat_model: str = Field(
        default="qwen2.5:3b",
        validation_alias=AliasChoices("CHAT_MODEL", "LSN_CHAT_MODEL"),
    )
    chat_temperature: float = 0.3
    chat_num_ctx: int = 8192             # context window asked from Ollama
    chat_timeout_seconds: float = 180    # a small local model can be slow on CPU
    chat_history_messages: int = 12      # how many earlier messages the model sees
    chat_context_chars: int = 6000       # how much document text is put in the prompt

    # Week 6 presentation edits (LLM-01): timeouts for the JSON client (outline + slide content).
    ollama_connect_timeout_seconds: float = 5     # Ollama not running -> fail fast
    ollama_read_timeout_seconds: float = 300      # one slide on a CPU-only laptop can take minutes

    # Week 6 presentation edits (ARC-07): everything a deployer may want to tune for presentations.
    # Each one can be set in .env (see .env.example); the defaults are the values that used to be hard-coded.
    # The model and the Ollama URL (ollama_base_url above) are shared by the outline and the slide writer.
    presentation_model: str = Field(
        default="qwen2.5:3b",
        validation_alias=AliasChoices("PRESENTATION_MODEL", "LSN_PRESENTATION_MODEL"),
    )
    outline_temperature: float = Field(default=0.3, ge=0, le=2)   # outline: a little variety is fine
    slide_temperature: float = Field(default=0.1, ge=0, le=2)     # slides must follow the sources
    presentation_num_ctx: int = Field(default=8192, ge=512)       # context window for outline + slide prompts
    ollama_json_max_attempts: int = Field(default=2, ge=1)        # JSON client: first try + retries after bad JSON
    slide_max_attempts: int = Field(default=2, ge=1)              # slide writer: tries when the model cites unknown sources

    # Week 6 presentation edits (LLM-02): send the JSON schema itself in Ollama's "format" field (needs a recent
    # Ollama). An old server that refuses it is detected automatically; set false to force the old format="json".
    ollama_structured_output: bool = True

    # Charts and tables: how much of a spreadsheet may end up on one slide.
    chart_max_bar_categories: int = Field(default=12, ge=1)
    chart_max_pie_slices: int = Field(default=8, ge=1)
    chart_max_line_points: int = Field(default=24, ge=1)
    table_max_rows: int = Field(default=15, ge=1)
    table_max_columns: int = Field(default=6, ge=1)

    # What the model is told about the notebook's spreadsheets (keeps the prompt small).
    catalog_max_files: int = Field(default=5, ge=1)
    catalog_max_sheets: int = Field(default=5, ge=1)
    catalog_max_columns: int = Field(default=15, ge=1)
    catalog_sample_rows: int = Field(default=50, ge=1)            # rows read only to detect the column kinds
 
    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"      # data/artifacts



settings = Settings()
