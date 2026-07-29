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
        CHROMA_DB_PATH=./storage/embeddings
        EMBEDDING_MODEL=all-MiniLM-L6-v2
        ANTHROPIC_API_KEY=sk-ant-...
        ENVIRONMENT=development
    """
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/validator_db"
    
    # Storage
    STORAGE_PATH: str = "./storage/uploads"
    
    # OCR
    TESSERACT_PATH: Optional[str] = None  # Auto-detect if not set
    
    # Phase 3: Embeddings & AI
    CHROMA_DB_PATH: str = "./storage/embeddings"  # ChromaDB vector store location
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # sentence-transformers model name
    ANTHROPIC_API_KEY: Optional[str] = None  # Claude API key (from environment)
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # API
    API_TITLE: str = "Resume Validator API"
    API_VERSION: str = "0.3.0"
    API_DESCRIPTION: str = "Resume ingestion, verification, and validation API"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Singleton settings instance
settings = Settings()
