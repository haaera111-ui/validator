"""
Main FastAPI application entry point.

Start server with:
    uvicorn main:app --reload --port 8000

API docs available at:
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import settings
from app.api.routes import router
from database.db import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown event handler.
    Creates database tables on startup.
    """
    # Startup
    print("[App] Starting up...")
    print(f"[App] Environment: {settings.ENVIRONMENT}")
    print(f"[App] Database: {settings.DATABASE_URL}")
    print(f"[App] Storage: {settings.STORAGE_PATH}")
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    print("[App] Database tables ready")
    
    yield
    
    # Shutdown
    print("[App] Shutting down...")


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
