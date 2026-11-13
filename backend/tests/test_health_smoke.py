"""Automated Smoke Test for ReportSaathi API Health Endpoints.

Validates TC-FR-2.1 (Contract test: GET /health returns 200 OK)
and GET /api/health database reporting.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_get_health_contract() -> None:
    """Validate GET /health contract against docs/06a-api-contract.md."""
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "ReportSaathi"
    assert payload["version"] == "1.0.0"


def test_get_api_health_with_connected_db() -> None:
    """Validate GET /api/health returns database value when connected."""
    mock_db_status = {
        "status": "connected",
        "value": "Supabase PostgreSQL (users table: 42 rows)",
        "message": "Database query succeeded.",
    }

    with patch("backend.main.get_database_health", return_value=mock_db_status):
        response = client.get("/api/health")
        assert response.status_code == 200

        payload = response.json()
        assert payload["status"] == "healthy"
        assert payload["service"] == "ReportSaathi"
        expected_db_val = "Supabase PostgreSQL (users table: 42 rows)"
        assert "database" in payload
        assert payload["database"]["status"] == "connected"
        assert payload["database"]["value"] == expected_db_val


def test_get_api_health_graceful_when_unconfigured() -> None:
    """Validate GET /api/health handles missing DB credentials gracefully."""
    mock_db_status = {
        "status": "disconnected",
        "value": None,
        "message": "SUPABASE_URL or SUPABASE_SERVICE_KEY is not configured.",
    }

    with patch("backend.main.get_database_health", return_value=mock_db_status):
        response = client.get("/api/health")
        assert response.status_code == 200

        payload = response.json()
        assert payload["status"] == "healthy"
        assert payload["database"]["status"] == "disconnected"
        assert payload["database"]["value"] is None


def test_cors_preflight_headers() -> None:
    """Verify CORS headers allow cross-origin requests from frontend."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in (
        "http://localhost:5173",
        "*",
    )
