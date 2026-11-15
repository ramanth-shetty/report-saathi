"""ReportSaathi Backend Service.

FastAPI entrypoint for health checks, OCR/AI core pipeline, and webhooks.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared.constants import SERVICE_NAME, SERVICE_VERSION

from backend.database import (
    compute_deltas,
    compute_report_hash,
    find_report_by_hash,
    get_database_health,
    get_user_biomarkers,
    save_report,
    save_translation,
)
from backend.gemini_analyzer import (
    ReportSummary,
    analyze,
    apply_safety_overrides,
)
from backend.ocr_scrub import (
    ocr_rows,
    parse_rows,
    preprocess,
    rasterize_pdf,
    scrub_pii,
)

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

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


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


@app.post("/api/analyze", tags=["Analysis"])
async def analyze_report(
    file: UploadFile = File(...),  # noqa: B008
    lang: str = Form("en"),  # noqa: B008
    user_id: str | None = Form(None),  # noqa: B008
) -> dict[str, Any]:
    """Synchronous core pipeline for medical lab report analysis.

    Flow:
    1. Validate payload size (max 10MB) and format (JPEG, PNG, PDF, TXT).
    2. Extract visual rows via OpenCV + PyMuPDF + Tesseract OCR.
    3. Low confidence quality gate intercept (< 55.0).
    4. Deterministic local PII scrubbing (no cloud PII transmission).
    5. SHA-256 deduplication cache check (0 LLM calls on hits).
    6. Longitudinal trend delta calculation from historical user records.
    7. Structured analysis via Gemini 2.5 Flash.
    8. Deterministic critical overrides & invariant disclaimer injection.
    9. Cache persistence and structured response dispatch.
    """
    # 1. Payload size validation
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum size limit of 10MB.",
        )

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    is_pdf = filename.endswith(".pdf") or "application/pdf" in content_type
    is_image = filename.endswith((".jpg", ".jpeg", ".png")) or content_type.startswith(
        "image/"
    )
    is_text = (
        filename.endswith(".txt")
        or content_type.startswith("text/")
        or "text/plain" in content_type
    )

    if not (is_pdf or is_image or is_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported file format. Please upload JPEG, PNG, or PDF.",
        )

    # 2. Extract visual text rows
    raw_lines: list[str] = []

    if is_text:
        text_str = content.decode("utf-8", errors="replace")
        raw_lines = [line.strip() for line in text_str.splitlines() if line.strip()]
    elif is_pdf:
        try:
            page_images = rasterize_pdf(content, dpi=300)
            total_conf = 0.0
            page_count = 0
            for page_bytes in page_images:
                preprocessed = preprocess(page_bytes)
                lines, conf = ocr_rows(preprocessed)
                raw_lines.extend(lines)
                total_conf += conf
                page_count += 1

            avg_conf = (total_conf / page_count) if page_count > 0 else 0.0
            if avg_conf < 55.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "File too blurry or unreadable. Please place the "
                        "strip flat under good lighting and take a straight-on photo."
                    ),
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to rasterize or OCR PDF: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal analysis error. Please try again later.",
            ) from exc
    elif is_image:
        try:
            preprocessed = preprocess(content)
            lines, avg_conf = ocr_rows(preprocessed)
            if avg_conf < 55.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "File too blurry or unreadable. Please place the "
                        "strip flat under good lighting and take a straight-on photo."
                    ),
                )
            raw_lines = lines
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to preprocess or OCR image: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal analysis error. Please try again later.",
            ) from exc

    # In-memory purge: clear raw image buffer immediately post-OCR
    del content

    if not raw_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "File too blurry or unreadable. Please place the "
                "strip flat under good lighting and take a straight-on photo."
            ),
        )

    # 3. Local PII scrubbing & row parsing
    scrubbed_lines, age, sex = scrub_pii(raw_lines)
    parsed_rows = parse_rows(scrubbed_lines)

    # 4. SHA-256 Deduplication cache check
    report_hash = compute_report_hash(scrubbed_lines)
    if user_id:
        try:
            cached_report = find_report_by_hash(user_id, report_hash)
            if cached_report:
                cached_id = str(cached_report["id"])
                field_name = f"summary_{lang}" if lang in ("hi", "kn") else "summary_en"
                cached_data = cached_report.get(field_name) or (
                    cached_report.get("summary_en") if lang == "en" else None
                )

                if cached_data and isinstance(cached_data, dict):
                    cached_data["report_id"] = cached_id
                    return cached_data
        except Exception as exc:
            logger.warning("Cache lookup encountered error: %s", exc)

    # 5. Longitudinal history & trend delta calculation
    deltas: list[str] = []
    if user_id:
        try:
            history = get_user_biomarkers(user_id)
            deltas = compute_deltas(parsed_rows, history)
        except Exception as exc:
            logger.warning("Failed to fetch historical trends: %s", exc)

    # 6. Structured AI analysis via Gemini 2.5 Flash
    try:
        summary: ReportSummary = analyze(
            rows=scrubbed_lines,
            age=age,
            sex=sex,
            deltas=deltas,
            lang=lang,
            parsed_rows=parsed_rows,
        )
    except Exception as exc:
        err_msg = str(exc)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="API rate limit reached. Please retry in a few moments.",
            ) from exc
        logger.error("Gemini analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis error. Please try again later.",
        ) from exc

    # 7. Apply deterministic clinical safety overrides
    summary = apply_safety_overrides(parsed_rows, summary, lang=lang)

    # 8. Persistence to Supabase
    report_dict = summary.model_dump()
    if user_id:
        try:
            saved_id = save_report(
                user_id=user_id,
                report_hash=report_hash,
                summary_en=report_dict,
                urgency=summary.urgency,
                biomarker_rows=parsed_rows,
            )
            report_dict["report_id"] = saved_id

            if lang != "en":
                save_translation(
                    report_id=saved_id,
                    lang=lang,
                    summary_json=report_dict,
                )
        except Exception as exc:
            logger.error("Failed to save report to database: %s", exc)

    return report_dict


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
