"""Unit and integration test suite for Task PR-05 (Database Service & Cache).

Covers:
- TC-FR-1.2: User Onboarding & Affirmative Consent Timestamp Logging.
- TC-FR-3.4: SHA-256 Deduplication Hashing & Cache-First Retrieval (0 AI calls).
- TC-FR-5.2: Longitudinal Biomarker Delta Calculation (e.g. HbA1c 8.4% -> 7.8%).
- TC-FR-5.3: DPDP Act 2023 Permanent Cascade Erasure (/delete).
- TC-SEC-2: SQL Injection Resistance in biomarker strings.
- Multilingual Translation Caching (en, hi, kn).
- Live Supabase Integration (conditionally run if credentials are present).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from backend.database import (
    compute_deltas,
    compute_report_hash,
    delete_user_data,
    find_report_by_hash,
    get_or_create_user,
    get_supabase_client,
    get_translation,
    save_report,
    save_translation,
    set_consent,
    set_language,
)

# ==============================================================================
# 1. TC-FR-1.2: User Creation, Consent Logging & Language Preference
# ==============================================================================


def test_tc_fr_1_2_user_creation_and_consent() -> None:
    """Validate user retrieval/creation and affirmative consent timestamp recording."""
    mock_client = MagicMock()

    # 1. Simulate new user insert
    mock_client.table().select().eq().execute.return_value.data = []
    mock_client.table().insert().execute.return_value.data = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "telegram_chat_id": 987654321,
            "preferred_lang": "en",
            "consent_at": None,
        }
    ]

    user = get_or_create_user(
        chat_id=987654321,
        lang="en",
        client=mock_client,
    )
    assert user["telegram_chat_id"] == 987654321
    assert user["preferred_lang"] == "en"
    assert user["consent_at"] is None

    # 2. Simulate setting affirmative consent
    mock_client.table().update().eq().execute.return_value.data = [
        {
            "id": user["id"],
            "telegram_chat_id": 987654321,
            "consent_at": "2026-11-14T10:00:00+00:00",
        }
    ]

    consented_user = set_consent(user["id"], client=mock_client)
    assert consented_user["consent_at"] is not None

    # 3. Simulate updating preferred language to Kannada
    mock_client.table().update().eq().execute.return_value.data = [
        {
            "id": user["id"],
            "preferred_lang": "kn",
        }
    ]
    lang_user = set_language(user["id"], "kn", client=mock_client)
    assert lang_user["preferred_lang"] == "kn"


# ==============================================================================
# 2. TC-FR-3.4: SHA-256 Deduplication Hashing & Zero AI Cost
# ==============================================================================


def test_tc_fr_3_4_sha256_deduplication_hashing() -> None:
    """Validate deterministic hashing and cache lookup to prevent redundant calls."""
    sample_lines_1 = [
        "Fasting Plasma Glucose 158 mg/dL 70 - 100",
        "Serum Creatinine 1.1 mg/dL 0.7 - 1.3",
    ]
    sample_lines_2 = [
        "  Fasting Plasma Glucose   158 mg/dL 70 - 100  ",
        "Serum Creatinine 1.1 mg/dL 0.7 - 1.3",
    ]
    diff_lines = [
        "Fasting Plasma Glucose 180 mg/dL 70 - 100",
        "Serum Creatinine 1.1 mg/dL 0.7 - 1.3",
    ]

    hash_1 = compute_report_hash(sample_lines_1)
    hash_2 = compute_report_hash(sample_lines_2)
    hash_diff = compute_report_hash(diff_lines)

    # Whitespace normalization produces identical hashes
    assert hash_1 == hash_2
    assert hash_1 != hash_diff
    assert len(hash_1) == 64

    # Simulate cache hit with mock
    mock_client = MagicMock()
    user_id = "user-uuid-123"
    mock_report = {
        "id": "report-uuid-456",
        "user_id": user_id,
        "report_hash": hash_1,
        "urgency_level": "Consult Soon",
        "summary_en": {"normal_summary": "Stable", "abnormal": []},
    }
    mock_client.table().select().eq().eq().execute.return_value.data = [mock_report]

    cached = find_report_by_hash(user_id, hash_1, client=mock_client)
    assert cached is not None
    assert cached["report_hash"] == hash_1
    assert cached["urgency_level"] == "Consult Soon"


def test_save_report_and_biomarkers_persistence() -> None:
    """Validate saving scrubbed report summaries and individual biomarker rows."""
    mock_client = MagicMock()
    reports_mock = MagicMock()
    reports_mock.insert().execute.return_value = MagicMock(
        data=[{"id": "report-uuid-789"}]
    )
    biomarkers_mock = MagicMock()
    biomarkers_mock.insert().execute.return_value = MagicMock(
        data=[{"id": "bio-1"}, {"id": "bio-2"}]
    )

    def table_router(name: str) -> MagicMock:
        if name == "reports":
            return reports_mock
        return biomarkers_mock

    mock_client.table.side_effect = table_router

    user_id = "user-uuid-123"
    report_hash = "abcdef1234567890" * 4
    summary_en = {
        "normal_summary": "All normal.",
        "abnormal": [],
        "urgency": "Routine",
    }
    biomarkers = [
        {
            "test_name": "Hemoglobin",
            "observed_value": 14.2,
            "unit": "g/dL",
            "ref_range": "13.0 - 17.0",
            "status": "Normal",
        },
        {
            "test_name": "Fasting Blood Sugar",
            "observed_value": 95,
            "unit": "mg/dL",
            "ref_range": "70 - 100",
            "status": "Normal",
        },
    ]

    report_id = save_report(
        user_id=user_id,
        report_hash=report_hash,
        summary_en=summary_en,
        urgency="Routine",
        biomarker_rows=biomarkers,
        client=mock_client,
    )

    assert report_id == "report-uuid-789"
    assert reports_mock.insert.called
    assert biomarkers_mock.insert.called


# ==============================================================================
# 3. TC-FR-5.2: Longitudinal Biomarker Delta Calculation
# ==============================================================================


def test_tc_fr_5_2_historical_delta_calculation() -> None:
    """Validate calculation of longitudinal deltas and directional status notes."""
    # TC-FR-5.2 specification: HbA1c 8.4% -> 7.8% (improved)
    history = [
        {
            "test_name": "HbA1c",
            "observed_value": 8.4,
            "unit": "%",
            "recorded_at": "2026-08-10",
        },
        {
            "test_name": "Fasting Blood Sugar",
            "observed_value": 160.0,
            "unit": "mg/dL",
            "recorded_at": "2026-08-10",
        },
        {
            "test_name": "Hemoglobin",
            "observed_value": 10.2,
            "unit": "g/dL",
            "recorded_at": "2026-08-10",
        },
        {
            "test_name": "Serum Creatinine",
            "observed_value": 1.0,
            "unit": "mg/dL",
            "recorded_at": "2026-08-10",
        },
        {
            "test_name": "Total Cholesterol",
            "observed_value": 200.0,
            "unit": "mg/dL",
            "recorded_at": "2026-08-10",
        },
    ]

    current_rows = [
        {"test_name": "HbA1c", "observed_value": 7.8, "unit": "%"},
        {"test_name": "Fasting Blood Sugar", "observed_value": 110.0, "unit": "mg/dL"},
        {"test_name": "Hemoglobin", "observed_value": 12.8, "unit": "g/dL"},
        {"test_name": "Serum Creatinine", "observed_value": 1.4, "unit": "mg/dL"},
        {"test_name": "Total Cholesterol", "observed_value": 200.0, "unit": "mg/dL"},
    ]

    deltas = compute_deltas(current_rows, history)

    # Assertions
    assert "HbA1c: 8.4% -> 7.8% (improved)" in deltas
    assert "Fasting Blood Sugar: 160 mg/dL -> 110 mg/dL (improved)" in deltas
    assert "Hemoglobin: 10.2 g/dL -> 12.8 g/dL (improved)" in deltas
    assert "Serum Creatinine: 1 mg/dL -> 1.4 mg/dL (increased)" in deltas
    assert "Total Cholesterol: 200 mg/dL -> 200 mg/dL (unchanged)" in deltas


# ==============================================================================
# 4. TC-FR-5.3: DPDP Permanent Data Purge (/delete)
# ==============================================================================


def test_tc_fr_5_3_dpdp_user_data_purge() -> None:
    """Validate that delete_user_data triggers cascade deletion on users table."""
    mock_client = MagicMock()
    mock_client.table().delete().eq().execute.return_value.data = [
        {"id": "user-uuid-123"}
    ]

    deleted = delete_user_data(chat_id=987654321, client=mock_client)
    assert deleted is True

    # Validate delete by user_id
    mock_client.table().delete().eq().execute.return_value.data = [
        {"id": "user-uuid-456"}
    ]
    deleted_by_id = delete_user_data(user_id="user-uuid-456", client=mock_client)
    assert deleted_by_id is True


# ==============================================================================
# 5. TC-SEC-2: SQL Injection Resistance
# ==============================================================================


def test_tc_sec_2_sql_injection_resistance() -> None:
    """Validate that SQL injection payloads in OCR tokens are treated as literals."""
    mock_client = MagicMock()
    reports_mock = MagicMock()
    reports_mock.insert().execute.return_value = MagicMock(
        data=[{"id": "report-uuid-sqli"}]
    )
    biomarkers_mock = MagicMock()
    biomarkers_mock.insert().execute.return_value = MagicMock(data=[{"id": "bio-sqli"}])

    def table_router(name: str) -> MagicMock:
        if name == "reports":
            return reports_mock
        return biomarkers_mock

    mock_client.table.side_effect = table_router

    malicious_biomarkers = [
        {
            "test_name": "Hemoglobin'); DROP TABLE reports; --",
            "observed_value": 14.5,
            "unit": "g/dL",
            "ref_range": "13.0 - 17.0",
            "status": "Normal",
        }
    ]

    report_id = save_report(
        user_id="user-uuid-safe",
        report_hash="safehash123",
        summary_en={"status": "ok"},
        urgency="Routine",
        biomarker_rows=malicious_biomarkers,
        client=mock_client,
    )

    assert report_id == "report-uuid-sqli"
    # Inspect arguments passed to client.table('biomarkers').insert(...)
    biomarker_payload = biomarkers_mock.insert.call_args[0][0]
    assert biomarker_payload[0]["test_name"] == "Hemoglobin'); DROP TABLE reports; --"


# ==============================================================================
# 6. Multilingual Translation Caching
# ==============================================================================


def test_translation_caching_and_retrieval() -> None:
    """Validate caching and retrieving Kannada and Hindi JSON summaries."""
    mock_client = MagicMock()

    # Save translation
    mock_client.table().update().eq().execute.return_value.data = [{"id": "report-123"}]
    save_translation(
        report_id="report-123",
        lang="kn",
        summary_json={"normal_summary": "ಖಚಿತ"},
        client=mock_client,
    )
    assert mock_client.table().update.called

    # Get translation
    mock_client.table().select().eq().execute.return_value.data = [
        {
            "id": "report-123",
            "summary_kn": {"normal_summary": "ಖಚಿತ"},
            "summary_hi": None,
            "summary_en": {"normal_summary": "Confirmed"},
        }
    ]

    kn_summary = get_translation("report-123", "kn", client=mock_client)
    assert kn_summary == {"normal_summary": "ಖಚಿತ"}

    hi_summary = get_translation("report-123", "hi", client=mock_client)
    assert hi_summary is None


# ==============================================================================
# 7. Live Supabase Integration (Skipped if no live credentials)
# ==============================================================================


@pytest.mark.skipif(
    os.getenv("SUPABASE_URL", "").startswith("https://your-project")
    or not os.getenv("SUPABASE_URL")
    or not os.getenv("SUPABASE_SERVICE_KEY"),
    reason="Live Supabase environment variables not configured with credentials",
)
def test_live_supabase_integration() -> None:
    """Live roundtrip integration test against active Supabase PostgreSQL.

    Skips automatically if live credentials are not set.
    """
    sb = get_supabase_client()
    if sb is None:
        pytest.skip(
            "Live Supabase environment variables not configured with credentials"
        )

    test_chat_id = 999999999
    try:
        # Clean up any residual test data first
        delete_user_data(chat_id=test_chat_id, client=sb)

        # 1. Create user
        user = get_or_create_user(chat_id=test_chat_id, lang="en", client=sb)
        assert user["telegram_chat_id"] == test_chat_id

        # 2. Record consent
        consented = set_consent(user["id"], client=sb)
        assert consented["consent_at"] is not None

        # 3. Save report and biomarkers
        report_hash = "live_test_hash_001"
        summary_en = {
            "normal_summary": "Live test summary",
            "abnormal": [],
            "urgency": "Routine",
        }
        biomarkers = [
            {
                "test_name": "Fasting Plasma Glucose",
                "observed_value": 92.0,
                "unit": "mg/dL",
                "ref_range": "70 - 100",
                "status": "Normal",
            }
        ]
        report_id = save_report(
            user_id=user["id"],
            report_hash=report_hash,
            summary_en=summary_en,
            urgency="Routine",
            biomarker_rows=biomarkers,
            client=sb,
        )
        assert report_id is not None

        # 4. Cache hit verification
        cached = find_report_by_hash(user["id"], report_hash, client=sb)
        assert cached is not None
        assert cached["id"] == report_id

        # 5. Cascading deletion
        deleted = delete_user_data(chat_id=test_chat_id, client=sb)
        assert deleted is True

        # 6. Verify total purge
        assert find_report_by_hash(user["id"], report_hash, client=sb) is None
    finally:
        delete_user_data(chat_id=test_chat_id, client=sb)
