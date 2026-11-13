"""Database connectivity and health check module for ReportSaathi.

Interacts with Supabase PostgreSQL using the service role key.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Cache client instance
_supabase_client = None


def get_supabase_client() -> Any | None:
    """Initialize or return the cached Supabase client using environment variables.

    Returns None if SUPABASE_URL or SUPABASE_SERVICE_KEY are missing.
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        return None

    try:
        from supabase import create_client

        _supabase_client = create_client(supabase_url, supabase_key)
        return _supabase_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize Supabase client: %s", exc)
        return None


def get_database_health() -> dict[str, Any]:
    """Execute a lightweight read against Supabase to verify connectivity.

    Returns a dict with 'status', 'value', and optional 'message'.
    """
    client = get_supabase_client()
    if client is None:
        return {
            "status": "disconnected",
            "value": None,
            "message": "SUPABASE_URL or SUPABASE_SERVICE_KEY is not configured.",
        }

    try:
        # Query users table metadata/count without returning sensitive data
        response = client.table("users").select("id", count="exact").limit(1).execute()
        count_display = (
            f"{response.count} rows" if response.count is not None else "accessible"
        )
        return {
            "status": "connected",
            "value": f"Supabase PostgreSQL (users table: {count_display})",
            "message": "Database query succeeded.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Database health query failed: %s", exc)
        return {
            "status": "error",
            "value": None,
            "message": f"Query error: {exc}",
        }
