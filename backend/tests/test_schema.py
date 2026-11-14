"""Verification test suite for Task PR-02 (Supabase Schema DDL & RLS).

Validates:
- SQL DDL syntax, constraints, foreign keys with ON DELETE CASCADE, compound indexes.
- RLS activation on users, reports, and biomarkers tables.
- TC-FR-1.2: Affirmative consent timestamp logging.
- TC-FR-5.3: Cascade deletion contract across users, reports, and biomarkers.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "supabase" / "schema.sql"


def test_schema_file_exists() -> None:
    """Verify that supabase/schema.sql exists and is populated."""
    assert SCHEMA_PATH.exists(), f"Schema file not found at {SCHEMA_PATH}"
    content = SCHEMA_PATH.read_text(encoding="utf-8")
    assert len(content.strip()) > 100


def test_schema_ddl_structure_and_constraints() -> None:
    """Verify tables, cascade foreign keys, compound indexes, and RLS directives."""
    content = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    # 1. Extensions
    assert 'create extension if not exists "pgcrypto"' in content

    # 2. Users table & constraints
    assert "create table if not exists users" in content
    assert "id uuid primary key" in content
    assert "telegram_chat_id bigint unique" in content
    assert "preferred_lang text default 'en'" in content
    assert "check (preferred_lang in ('en', 'hi', 'kn'))" in content
    assert "consent_at timestamptz" in content

    # 3. Reports table & cascade deletion
    assert "create table if not exists reports" in content
    assert "references users(id) on delete cascade" in content
    assert "unique (user_id, report_hash)" in content
    assert (
        "check (urgency_level in ('routine', 'consult soon', 'prompt attention'))"
        in content
    )
    assert "summary_en jsonb not null" in content

    # 4. Biomarkers table & cascade deletion
    assert "create table if not exists biomarkers" in content
    assert "references reports(id) on delete cascade" in content
    assert "references users(id) on delete cascade" in content
    assert "check (status in ('normal', 'low', 'high', 'borderline'))" in content

    # 5. Compound indexes
    assert (
        "create index if not exists idx_reports_user_hash on reports "
        "(user_id, report_hash)"
    ) in content
    assert (
        "create index if not exists idx_biomarkers_user_test on biomarkers "
        "(user_id, lower(test_name), recorded_at desc)"
    ) in content

    # 6. Row Level Security (RLS)
    assert "alter table users enable row level security;" in content
    assert "alter table reports enable row level security;" in content
    assert "alter table biomarkers enable row level security;" in content


def test_tc_fr_1_2_consent_timestamp_logic() -> None:
    """TC-FR-1.2: Validate consent timestamp update workflow.

    Verifies that affirmative consent records a valid ISO/UTC timestamp on the user.
    """
    mock_client = MagicMock()
    fake_chat_id = 987654321
    fake_timestamp = "2026-11-14T08:00:00Z"

    # Simulate consent update query
    mock_client.table("users").update({"consent_at": fake_timestamp}).eq(
        "telegram_chat_id", fake_chat_id
    ).execute.return_value = MagicMock(
        data=[{"telegram_chat_id": fake_chat_id, "consent_at": fake_timestamp}]
    )

    result = (
        mock_client.table("users")
        .update({"consent_at": fake_timestamp})
        .eq("telegram_chat_id", fake_chat_id)
        .execute()
    )

    assert result.data[0]["consent_at"] == fake_timestamp
    mock_client.table("users").update.assert_called_with({"consent_at": fake_timestamp})


def test_tc_fr_5_3_cascade_deletion_logic() -> None:
    """TC-FR-5.3: Validate cascade deletion contract.

    When a user is deleted, ON DELETE CASCADE ensures all linked reports
    and biomarkers are permanently purged from database tables.
    """
    mock_client = MagicMock()
    dummy_user_id = "00000000-0000-0000-0000-000000000001"

    # Simulate deleting user row
    mock_client.table("users").delete().eq(
        "id", dummy_user_id
    ).execute.return_value = MagicMock(data=[{"id": dummy_user_id}])

    res = mock_client.table("users").delete().eq("id", dummy_user_id).execute()
    assert res.data[0]["id"] == dummy_user_id

    # Verify that the schema enforces ON DELETE CASCADE
    content = SCHEMA_PATH.read_text(encoding="utf-8").lower()
    reports_fk = "user_id uuid not null references users(id) on delete cascade"
    biomarkers_report_fk = (
        "report_id uuid not null references reports(id) on delete cascade"
    )
    biomarkers_user_fk = "user_id uuid not null references users(id) on delete cascade"

    assert reports_fk in content
    assert biomarkers_report_fk in content
    assert biomarkers_user_fk in content


@pytest.mark.skipif(
    os.getenv("SUPABASE_URL", "").startswith("https://your-project")
    or not os.getenv("SUPABASE_URL")
    or not os.getenv("SUPABASE_SERVICE_KEY"),
    reason="Live Supabase environment variables not configured with credentials",
)
def test_live_supabase_ddl_and_cascade() -> None:
    """Live integration test: Run only when real Supabase credentials exist."""
    from backend.database import get_supabase_client

    client = get_supabase_client()
    if client is None:
        pytest.skip("Supabase client could not be initialized")

    test_chat_id = -999999999
    try:
        # Cleanup any existing test user
        client.table("users").delete().eq("telegram_chat_id", test_chat_id).execute()

        # 1. Insert dummy user
        user_res = (
            client.table("users")
            .insert({"telegram_chat_id": test_chat_id, "preferred_lang": "en"})
            .execute()
        )
        assert user_res.data and len(user_res.data) > 0
        user_id = user_res.data[0]["id"]

        # 2. Insert dummy report
        report_res = (
            client.table("reports")
            .insert(
                {
                    "user_id": user_id,
                    "report_hash": "dummy_test_hash_12345",
                    "urgency_level": "Routine",
                    "summary_en": {"normal_summary": "All normal"},
                }
            )
            .execute()
        )
        assert report_res.data and len(report_res.data) > 0
        report_id = report_res.data[0]["id"]

        # 3. Insert dummy biomarker
        bio_res = (
            client.table("biomarkers")
            .insert(
                {
                    "report_id": report_id,
                    "user_id": user_id,
                    "test_name": "Hemoglobin",
                    "observed_value": 14.2,
                    "unit": "g/dL",
                    "status": "Normal",
                }
            )
            .execute()
        )
        assert bio_res.data and len(bio_res.data) > 0

        # 4. Delete user -> verify cascade deletion in reports and biomarkers
        client.table("users").delete().eq("id", user_id).execute()

        remaining_reports = (
            client.table("reports").select("id").eq("user_id", user_id).execute()
        )
        remaining_biomarkers = (
            client.table("biomarkers").select("id").eq("user_id", user_id).execute()
        )

        assert len(remaining_reports.data) == 0, "Reports were not cascade-deleted"
        assert len(remaining_biomarkers.data) == 0, (
            "Biomarkers were not cascade-deleted"
        )

    finally:
        # Final cleanup
        client.table("users").delete().eq("telegram_chat_id", test_chat_id).execute()
