"""
Configuration management using Pydantic Settings.
Loads from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """
    Application settings.
    
    Load from environment variables, with defaults for development.
    
    Example .env:
        DATABASE_URL=postgresql://user:password@localhost:5432/validator_db
        STORAGE_PATH=/var/validator/uploads
        TESSERACT_PATH=/usr/bin/tesseract
        ENVIRONMENT=development
    """
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/validator_db"
    
    # Storage
    STORAGE_PATH: str = "./storage/uploads"
    
    # OCR
    TESSERACT_PATH: Optional[str] = None  # Auto-detect if not set
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # API
    API_TITLE: str = "Resume Validator API"
    API_VERSION: str = "0.1.0"
    API_DESCRIPTION: str = "Resume ingestion and parsing API - Phase 1"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Singleton settings instance
settings = Settings()
