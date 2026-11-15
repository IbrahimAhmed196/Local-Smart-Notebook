from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
        populate_by_name=True,
    )

    debug: bool = False

    # API
    api_prefix: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:3000")

    # Security
    secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Document storage
    data_dir: Path = Field(
        default=PROJECT_ROOT / "data",
        validation_alias=AliasChoices("LSN_DATA_DIR", "DATA_DIR"),
    )
    max_upload_mb: float = Field(
        default=50,
        validation_alias=AliasChoices("LSN_MAX_UPLOAD_MB", "MAX_UPLOAD_MB"),
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

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    # Shared Ollama defaults
    ollama_model: str = Field(
        default="qwen2.5:3b",
        validation_alias=AliasChoices("OLLAMA_MODEL", "LSN_OLLAMA_MODEL"),
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "LSN_OLLAMA_URL"),
    )
    ollama_connect_timeout_seconds: float = 5
    ollama_read_timeout_seconds: float = 300
    ollama_json_max_attempts: int = Field(default=2, ge=1)
    ollama_structured_output: bool = True

    # Notebook chat policy
    chat_model: str = Field(
        default="qwen2.5:3b",
        validation_alias=AliasChoices("CHAT_MODEL", "LSN_CHAT_MODEL"),
    )
    chat_temperature: float = 0.3
    chat_num_ctx: int = 8192
    chat_timeout_seconds: float = 180
    chat_history_messages: int = 12
    chat_context_chars: int = 6000

    # Presentation policy: passed explicitly by presentation callers
    presentation_model: str = Field(
        default="qwen2.5:3b",
        validation_alias=AliasChoices("PRESENTATION_MODEL", "LSN_PRESENTATION_MODEL"),
    )
    max_presentation_slides: int = 20
    outline_temperature: float = Field(default=0.3, ge=0, le=2)
    slide_temperature: float = Field(default=0.1, ge=0, le=2)
    presentation_num_ctx: int = Field(default=8192, ge=512)
    slide_max_attempts: int = Field(default=2, ge=1)

    # Presentation chart and table limits
    presentation_chart_max_bar_categories: int = Field(default=12, ge=1)
    presentation_chart_max_pie_slices: int = Field(default=8, ge=1)
    presentation_chart_max_line_points: int = Field(default=24, ge=1)
    presentation_table_max_rows: int = Field(default=15, ge=1)
    presentation_table_max_columns: int = Field(default=6, ge=1)

    # Spreadsheet catalog limits
    presentation_catalog_max_files: int = Field(default=5, ge=1)
    presentation_catalog_max_sheets: int = Field(default=5, ge=1)
    presentation_catalog_max_columns: int = Field(default=15, ge=1)
    presentation_catalog_sample_rows: int = Field(default=50, ge=1)

    # Week 6 presentation edits (DAT-02 / DAT-05 / DAT-06): limits of the chart/table checks, the data catalog
    # and the data facts.
    presentation_chart_max_series: int = Field(default=4, ge=1)                # more value columns than this are cut (with a warning)
    presentation_chart_scale_ratio_warning: float = Field(default=100, gt=1)   # warn when one series is this many times bigger than another
    presentation_table_max_cell_chars: int = Field(default=60, ge=10)          # warn about table cells longer than this
    presentation_catalog_example_labels: int = Field(default=5, ge=0)          # example labels shown for a text column (0 = none)
    presentation_slide_data_facts: bool = True                                 # false = skip the extra model call that writes bullets from the data facts

  # presentation Context extraction (CTX-02 / CTX-03 / CTX-04): the temporary LLM extractor only handles small documents.
    presentation_context_max_pdf_pages: int = Field(default=100, ge=1)  # CTX-02: a PDF with more pages is "too large"
    presentation_context_max_docx_mb: float = Field(default=20, gt=0)  # CTX-02: uncompressed size of word/document.xml
    presentation_context_max_chars_per_document: int | None = Field(default=None, ge=500)  # CTX-03: None = by model and language
    presentation_context_max_documents: int = Field(default=5, ge=1)  # CTX-03
    presentation_context_max_facts_per_document: int = Field(default=12, ge=1)  # CTX-04
    presentation_context_max_facts_total: int = Field(default=40, ge=1)  # CTX-04
    presentation_context_temperature: float = Field(default=0.1, ge=0, le=2)  # CTX-04


settings = Settings()
