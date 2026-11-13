"""ReportSaathi Backend Service.

FastAPI entrypoint for health checks, OCR/AI pipeline, and webhooks.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared.constants import SERVICE_NAME, SERVICE_VERSION

from backend.database import get_database_health

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reportsaathi")

app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="Family Health Translator for lab reports.",
)

# Configure CORS for Cloudflare Pages and local dev
cors_env = os.getenv("CORS_ORIGIN", "")
if cors_env.strip():
    allowed_origins = [
        origin.strip() for origin in cors_env.split(",") if origin.strip()
    ]
else:
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://reportsaathi.pages.dev",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BaseHealthResponse(BaseModel):
    status: str
    service: str
    version: str


class DatabaseHealthModel(BaseModel):
    status: str
    value: str | None = None
    message: str | None = None


class ExtendedHealthResponse(BaseHealthResponse):
    database: DatabaseHealthModel


@app.get("/health", response_model=BaseHealthResponse, tags=["Health"])
def health_check() -> dict[str, str]:
    """Lightweight health check probe for Render/container runners."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


@app.get("/api/health", response_model=ExtendedHealthResponse, tags=["Health"])
def api_health_check() -> dict[str, Any]:
    """Extended health check verifying service status and database connectivity.

    Used by the web frontend to confirm backend-to-database communications.
    """
    db_health = get_database_health()
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "database": db_health,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
