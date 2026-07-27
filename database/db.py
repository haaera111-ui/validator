"""
Database connection and session management.
Sets up SQLAlchemy engine and session factory.
Every API request gets its own session (dependency injection).
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from core.config import settings

# ==================== ENGINE ====================
# Create database engine with connection pooling
# NullPool is used to avoid connection pooling issues in some environments
# For production with high concurrency, consider using QueuePool or StaticPool
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Log all SQL queries if DEBUG=True
    pool_pre_ping=True,  # Test connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# ==================== SESSION FACTORY ====================
# Create a session factory that produces new sessions on demand
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ==================== DEPENDENCY INJECTION ====================
def get_db() -> Session:
    """
    FastAPI dependency that provides a database session.
    Usage in endpoints:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            # Use db for queries
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== BASE FOR ORM MODELS ====================
from sqlalchemy.orm import declarative_base

Base = declarative_base()
"""
All SQLAlchemy ORM models should inherit from Base.
This makes them discoverable by Alembic migrations.
"""


print(f"[DATABASE] Engine created for {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'unknown'}")
