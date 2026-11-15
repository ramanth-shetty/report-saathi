"""End-to-end integration test suite for Task PR-06 (Core Pipeline Wiring).

Covers:
- POST /api/analyze accepts report-01-routine-cbc.txt (< 20s).
- Re-posting identical report returns from cache (< 1.5s, 0 Gemini calls).
- Critical overrides escalate urgency to Prompt Attention (report-03).
- Blurry / unreadable quality gate rejects with 400 Bad Request.
- Payload size limit (> 10MB) returns 413 Payload Too Large.
- Unsupported file format returns 422 Unprocessable Entity.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
REPORT_01_PATH = FIXTURES_DIR / "report-01-routine-cbc.txt"
REPORT_03_PATH = FIXTURES_DIR / "report-03-critical-anemia.txt"


@pytest.fixture
def mock_gemini_routine() -> MagicMock:
    """Mock Gemini response returning a valid Routine ReportSummary JSON."""
    routine_payload = {
        "normal_summary": (
            "All Complete Blood Count parameters are within standard ranges."
        ),
        "abnormal": [],
        "cross_marker_patterns": [],
        "urgency": "Routine",
        "specialist": "General Physician",
        "doctor_questions": [
            "Are my routine blood counts adequate for my general health?",
            "When should I next schedule an annual wellness blood test?",
            "Are any dietary adjustments recommended based on these results?",
        ],
    }
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(routine_payload)

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp
    return mock_client


def test_post_api_analyze_accepts_report_01_routine(
    mock_gemini_routine: MagicMock,
) -> None:
    """Validate POST /api/analyze processes report-01-routine-cbc.txt in < 20s."""
    start_time = time.perf_counter()

    with (
        open(REPORT_01_PATH, "rb") as f,
        patch("backend.gemini_analyzer.genai.Client", return_value=mock_gemini_routine),
    ):
        response = client.post(
            "/api/analyze",
            files={"file": ("report-01-routine-cbc.txt", f, "text/plain")},
            data={"lang": "en"},
        )

    duration = time.perf_counter() - start_time

    assert response.status_code == 200
    data = response.json()

    assert data["urgency"] == "Routine"
    assert data["specialist"] == "General Physician"
    assert "Complete Blood Count" in data["normal_summary"]
    assert len(data["doctor_questions"]) == 3
    assert "disclaimer" in data
    assert duration < 20.0, f"Analysis took {duration:.2f}s, exceeding 20s threshold"


def test_post_api_analyze_caching_deduplication(
    mock_gemini_routine: MagicMock,
) -> None:
    """Validate that re-posting an identical report returns from cache (< 1.5s)."""
    user_id = "test-user-uuid-999"

    # Simulate empty cache initially, then cached report on re-post
    report_holder: dict[str, dict[str, Any]] = {}

    def mock_find_by_hash(
        user_id: str, report_hash: str, **kwargs: Any
    ) -> dict[str, Any] | None:
        return report_holder.get(report_hash)

    def mock_save(
        user_id: str,
        report_hash: str,
        summary_en: dict[str, Any],
        urgency: str,
        biomarker_rows: list[Any],
        **kwargs: Any,
    ) -> str:
        report_id = "rep-cached-123"
        report_holder[report_hash] = {
            "id": report_id,
            "user_id": user_id,
            "report_hash": report_hash,
            "urgency_level": urgency,
            "summary_en": summary_en,
        }
        return report_id

    with (
        patch("backend.main.find_report_by_hash", side_effect=mock_find_by_hash),
        patch("backend.main.save_report", side_effect=mock_save),
        patch("backend.main.get_user_biomarkers", return_value=[]),
        patch("backend.gemini_analyzer.genai.Client", return_value=mock_gemini_routine),
    ):
        # 1. First upload (Cache Miss -> calls Gemini)
        with open(REPORT_01_PATH, "rb") as f1:
            resp1 = client.post(
                "/api/analyze",
                files={"file": ("report-01-routine-cbc.txt", f1, "text/plain")},
                data={"lang": "en", "user_id": user_id},
            )
        assert resp1.status_code == 200
        assert mock_gemini_routine.models.generate_content.call_count == 1

        # 2. Re-post identical report (Cache Hit -> 0 Gemini calls, < 1.5s)
        start_cache_time = time.perf_counter()
        with open(REPORT_01_PATH, "rb") as f2:
            resp2 = client.post(
                "/api/analyze",
                files={"file": ("report-01-routine-cbc.txt", f2, "text/plain")},
                data={"lang": "en", "user_id": user_id},
            )
        cache_duration = time.perf_counter() - start_cache_time

        assert resp2.status_code == 200
        assert resp2.json()["urgency"] == "Routine"
        # Gemini call count must remain 1 (zero calls on cache hit)
        assert mock_gemini_routine.models.generate_content.call_count == 1
        assert cache_duration < 1.5, (
            f"Cache hit took {cache_duration:.3f}s, exceeding 1.5s threshold"
        )


def test_post_api_analyze_critical_override_integration() -> None:
    """Validate critical panic values are overridden to Prompt Attention."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(
        {
            "normal_summary": "RBC parameters are evaluated.",
            "abnormal": [
                {
                    "test": "Hemoglobin",
                    "value": "6.2 g/dL",
                    "status": "Low",
                    "explanation": "Hemoglobin is low.",
                }
            ],
            "cross_marker_patterns": [],
            "urgency": "Routine",  # LLM initially says Routine
            "specialist": "General Physician",
            "doctor_questions": ["Q1?", "Q2?", "Q3?"],
        }
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    with (
        open(REPORT_03_PATH, "rb") as f,
        patch("backend.gemini_analyzer.genai.Client", return_value=mock_client),
    ):
        response = client.post(
            "/api/analyze",
            files={"file": ("report-03-critical-anemia.txt", f, "text/plain")},
            data={"lang": "en"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["urgency"] == "Prompt Attention"
    assert any(
        "Critically Low Hemoglobin (Severe Anemia)" in m["explanation"]
        for m in data["abnormal"]
    )


def test_post_api_analyze_blurry_image_quality_gate() -> None:
    """Validate that images with OCR confidence < 55.0 return 400 Bad Request."""
    fake_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with (
        patch("backend.main.preprocess", return_value=MagicMock()),
        patch("backend.main.ocr_rows", return_value=(["blurry text"], 42.0)),
    ):
        response = client.post(
            "/api/analyze",
            files={"file": ("blurry_report.png", fake_png, "image/png")},
            data={"lang": "en"},
        )

    assert response.status_code == 400
    assert "File too blurry or unreadable" in response.json()["detail"]


def test_post_api_analyze_file_size_exceeded() -> None:
    """Validate that files exceeding 10MB are rejected with 413 Payload Too Large."""
    oversized_data = b"0" * (10 * 1024 * 1024 + 100)

    response = client.post(
        "/api/analyze",
        files={"file": ("huge_report.pdf", oversized_data, "application/pdf")},
    )

    assert response.status_code == 413
    assert "exceeds maximum size limit of 10MB" in response.json()["detail"]


def test_post_api_analyze_unsupported_format() -> None:
    """Validate unsupported formats return 422 Unprocessable Entity."""
    response = client.post(
        "/api/analyze",
        files={"file": ("malware.exe", b"binary content", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "Unsupported file format" in response.json()["detail"]
