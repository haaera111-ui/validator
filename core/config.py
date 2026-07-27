"""
Core configuration module - Single source of truth for all application settings.
Reads from environment variables, with defaults where safe.
Never hardcode sensitive values here - they come from .env file.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses pydantic-settings for validation and type safety.
    """

    # ==================== DATABASE ====================
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "validator"

    @property
    def DATABASE_URL(self) -> str:
        """Construct PostgreSQL connection string from components."""
        return (
            f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    # ==================== STORAGE ====================
    STORAGE_PATH: Path = Path("./storage")

    @property
    def STORAGE_PATH_ABSOLUTE(self) -> Path:
        """Get absolute path to storage directory, create if missing."""
        path = Path(self.STORAGE_PATH).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ==================== OCR / TESSERACT ====================
    TESSERACT_PATH: Optional[str] = None
    """
    Path to Tesseract executable.
    Windows example: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
    Linux example: /usr/bin/tesseract
    If not set, pytesseract will use system PATH.
    """

    # ==================== NLP / SPACY ====================
    SPACY_MODEL: str = "en_core_web_sm"
    """spaCy model name to load for NER and linguistic processing."""

    # ==================== FEATURE FLAGS (future phases) ====================
    ENABLE_LINKEDIN_MODULE: bool = False
    """Phase 2: LinkedIn profile verification."""

    ENABLE_LLM_MODULE: bool = False
    """Phase 3: LLM-based verification and enrichment."""

    ENABLE_BACKGROUND_CHECKS: bool = False
    """Phase 4: Background check integration."""

    # ==================== API ====================
    API_TITLE: str = "Validator API"
    API_VERSION: str = "0.1.0"
    DEBUG: bool = False

    class Config:
        """Pydantic settings configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Singleton instance - import this everywhere else in the app
settings = Settings()

# ==================== VALIDATION ====================
# Ensure critical paths exist at startup
if settings.TESSERACT_PATH:
    tesseract_file = Path(settings.TESSERACT_PATH)
    if not tesseract_file.exists():
        raise FileNotFoundError(
            f"Tesseract not found at {settings.TESSERACT_PATH}. "
            "Check your .env file or install Tesseract OCR for Windows."
        )

print(f"[CONFIG] Using database: {settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}")
print(f"[CONFIG] Storage path: {settings.STORAGE_PATH_ABSOLUTE}")
print(f"[CONFIG] Tesseract: {settings.TESSERACT_PATH or 'Using system PATH'}")
print(f"[CONFIG] spaCy model: {settings.SPACY_MODEL}")
