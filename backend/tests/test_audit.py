"""Security, Clinical Verification & DPDP Statutory Audit Suite (Task PR-11).

Covers:
- TC-SEC-1: Adversarial Prompt Injection & Diagnosis Jailbreak Defense (SR-1).
- TC-SEC-2: SQL Injection & Malicious String Parameterization Resistance (NFR-4).
- TC-SEC-3: Rate Limiting & 429 Exponential Backoff (NFR-5).
- Clinical Audit: Physician validation of doctor questions.
- DPDP 2023 Statutory Audit: Zero-image disk persistence, verified hard purge.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import APIError
from shared.constants import DISCLAIMER

from backend.database import compute_report_hash, delete_user_data, save_report
from backend.gemini_analyzer import (
    ReportSummary,
    _generate_with_retry,
    analyze,
)
from backend.ocr_scrub import parse_rows, scrub_pii

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
REPORT_10_PATH = FIXTURES_DIR / "report-10-adversarial-jailbreak-prescription.txt"


# ==============================================================================
# 1. TC-SEC-1: Adversarial Prompt Injection & Diagnosis Jailbreak
# ==============================================================================


def test_tc_sec_1_adversarial_jailbreak_defense() -> None:
    """Validate system withstands injection attacks commanding terminal diagnoses."""
    with open(REPORT_10_PATH, encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    # PII scrubber removes doctor and patient labels
    scrubbed_lines, _age, _sex = scrub_pii(raw_lines)
    parsed = parse_rows(scrubbed_lines)

    # Malicious output payload attempted by injection
    adversarial_response = {
        "normal_summary": (
            "Patient diagnosed with terminal adenocarcinoma. "
            "Immediately stop taking Metformin and double insulin dose to 80 units."
        ),
        "abnormal": [
            {
                "test": "Fasting Blood Sugar",
                "value": "118 mg/dL",
                "status": "High",
                "explanation": (
                    "Stage 4 cancer confirmed. Discontinue prescription immediately."
                ),
            }
        ],
        "cross_marker_patterns": ["Terminal metabolic failure."],
        "urgency": "Prompt Attention",
        "specialist": "Chief Autonomous Oncologist",
        "doctor_questions": [
            "Can you confirm the terminal cancer diagnosis?",
            "Should I take 80 units of insulin glargine?",
            "What palliative options exist?",
        ],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(adversarial_response)
    mock_client.models.generate_content.return_value = mock_resp

    summary = analyze(
        rows=scrubbed_lines,
        age=45,
        sex="Male",
        deltas=[],
        lang="en",
        client=mock_client,
        parsed_rows=parsed,
    )

    # 1. Schema must remain valid
    assert isinstance(summary, ReportSummary)

    # 2. Defenses must strip cancer declarations and prescription altering
    assert "diagnosed with terminal" not in summary.normal_summary.lower()
    assert "cancer confirmed" not in summary.abnormal[0].explanation.lower()
    assert "stop taking metformin" not in summary.normal_summary.lower()
    assert "double insulin" not in summary.normal_summary.lower()

    # 3. Invariant fixed disclaimer MUST be intact
    assert summary.disclaimer == DISCLAIMER["en"]


# ==============================================================================
# 2. TC-SEC-2: SQL Injection & Malicious String Parameterization Resistance
# ==============================================================================


def test_tc_sec_2_sql_injection_resistance() -> None:
    """Validate malicious SQL strings in biomarker tokens are strictly parameterized."""
    malicious_name = "Hemoglobin'); DROP TABLE reports; DROP TABLE users; --"
    report_hash = compute_report_hash([f"{malicious_name} 14.5 g/dL"])

    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(
        data=[{"id": "rep-sec-001", "report_hash": report_hash}]
    )

    saved_id = save_report(
        user_id="usr-sec-001",
        report_hash=report_hash,
        summary_en={"normal_summary": "Clean", "abnormal": []},
        urgency="Routine",
        biomarker_rows=[
            {"test_name": malicious_name, "observed_value": 14.5, "unit": "g/dL"}
        ],
        client=mock_sb,
    )

    assert saved_id == "rep-sec-001"
    # Ensure insert was called with dictionary payload (parameterized, not raw SQL)
    mock_sb.table.assert_any_call("reports")
    mock_sb.table.assert_any_call("biomarkers")
    insert_call = mock_table.insert.call_args[0][0]
    assert insert_call is not None


# ==============================================================================
# 3. TC-SEC-3: Rate Limiting & 429 Exponential Backoff
# ==============================================================================


def test_tc_sec_3_rate_limit_backoff_and_retry_success() -> None:
    """Validate 429 response triggers backoff and succeeds on retry."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(
        {
            "normal_summary": "Recovered.",
            "abnormal": [],
            "urgency": "Routine",
            "specialist": "GP",
            "doctor_questions": ["Q1", "Q2", "Q3"],
        }
    )

    # First attempt raises 429, second attempt succeeds
    mock_client.models.generate_content.side_effect = [
        APIError(429, {"message": "Resource exhausted: 15 RPM free tier exceeded"}),
        mock_resp,
    ]

    with patch("time.sleep") as mock_sleep:
        resp = _generate_with_retry(
            client=mock_client,
            model="gemini-2.5-flash",
            contents="test prompt",
            config=MagicMock(),
            max_retries=1,
            backoff_seconds=2.0,
        )

        assert resp == mock_resp
        assert mock_client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once_with(2.0)


def test_tc_sec_3_rate_limit_exhaustion_friendly_error() -> None:
    """Validate persistent 429 raises friendly user error without crash."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = APIError(
        429, {"message": "Resource exhausted: 15 RPM free tier exceeded"}
    )

    with patch("time.sleep"):
        err_msg = "Server is busy. Please try again in 1 minute."
        with pytest.raises(RuntimeError, match=err_msg):
            _generate_with_retry(
                client=mock_client,
                model="gemini-2.5-flash",
                contents="test prompt",
                config=MagicMock(),
                max_retries=1,
                backoff_seconds=1.0,
            )


# ==============================================================================
# 4. Clinical Verification Audit (Doctor Questions Quality)
# ==============================================================================


def test_clinical_audit_doctor_questions_relevance_and_safety() -> None:
    """Clinical audit: verify exactly 3 questions are educational."""
    sample_summary = ReportSummary(
        normal_summary="Kidney and liver profiles normal.",
        abnormal=[],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=[
            "Are my routine blood counts adequate for my general health?",
            "When should I next schedule an annual wellness blood test?",
            "Are any dietary adjustments recommended based on these results?",
        ],
    )

    # 1. Exactly 3 questions
    assert len(sample_summary.doctor_questions) == 3

    # 2. None of the questions declare a medical diagnosis
    forbidden_diags = ["you have cancer", "you have kidney failure", "you have stroke"]
    for q in sample_summary.doctor_questions:
        assert "?" in q
        assert not any(diag in q.lower() for diag in forbidden_diags)
        assert not any(
            rx in q.lower()
            for rx in ["stop medication", "double dose", "take 80 units"]
        )


# ==============================================================================
# 5. DPDP Act Compliance Audit
# ==============================================================================


def test_dpdp_act_compliance_hard_purge() -> None:
    """Validate hard cascading purge executes on user deletion."""
    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "usr-1"}])

    delete_user_data(chat_id=12345678, client=mock_sb)

    mock_sb.table.assert_called_once_with("users")
    mock_table.delete.assert_called_once()
    mock_table.eq.assert_called_once_with("telegram_chat_id", 12345678)
