"""Test Suite for PR-04: Structured Analysis & Medical Safety Overrides.

Covers:
- TC-FR-4.1: Pydantic Schema Strict Compliance (ReportSummary validation)
- TC-FR-4.2: Critical Safety Override: Severe Anemia (report-03 fixture)
- TC-FR-4.3: Critical Safety Override: Severe Hyperglycemia (report-02 fixture)
- TC-FR-4.4: Critical Safety Override: Severe Thrombocytopenia (report-05 fixture)
- TC-FR-4.5: Directional Urgency Invariant (Urgency can only escalate)
- TC-FR-4.6: Invariant Fixed Disclaimer Injection (en, hi, kn)
- TC-SEC-1: Adversarial Jailbreak Defense (report-10 fixture)
- Unit Normalization Matrix (Glucose, Hemoglobin, Platelets)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from shared.constants import DISCLAIMER

from backend.gemini_analyzer import (
    AbnormalMarker,
    ReportSummary,
    analyze,
    apply_safety_overrides,
    normalize_biomarker_unit,
)
from backend.ocr_scrub import parse_rows, scrub_pii

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
REPORT_02_PATH = FIXTURES_DIR / "report-02-critical-glucose.txt"
REPORT_03_PATH = FIXTURES_DIR / "report-03-critical-anemia.txt"
REPORT_05_PATH = FIXTURES_DIR / "report-05-critical-thrombocytopenia-dengue.txt"
REPORT_10_PATH = FIXTURES_DIR / "report-10-adversarial-jailbreak-prescription.txt"


def _load_fixture(path: Path) -> list[str]:
    """Helper to load fixture lines."""
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# ==============================================================================
# TC-FR-4.1: Pydantic Schema Strict Compliance
# ==============================================================================


def test_tc_fr_4_1_pydantic_schema_strict_compliance() -> None:
    """Validate ReportSummary strict JSON parsing, typing, and 3-question rule."""
    valid_payload = {
        "normal_summary": "All routine hematology values are within normal limits.",
        "abnormal": [
            {
                "test": "HbA1c",
                "value": "7.8 %",
                "status": "High",
                "explanation": (
                    "Average blood sugar over three months is moderately high."
                ),
                "trend_note": "Previous was 8.4 % (improved).",
            }
        ],
        "cross_marker_patterns": [],
        "urgency": "Consult Soon",
        "specialist": "Endocrinologist",
        "doctor_questions": [
            "Does my improved HbA1c mean my current regimen is working well?",
            "When should we schedule a follow-up fasting blood test?",
            "Are any morning lifestyle changes recommended?",
        ],
    }

    # Validate JSON deserialization
    summary = ReportSummary.model_validate_json(json.dumps(valid_payload))
    assert summary.urgency == "Consult Soon"
    assert summary.specialist == "Endocrinologist"
    assert len(summary.abnormal) == 1
    assert summary.abnormal[0].test == "HbA1c"
    assert len(summary.doctor_questions) == 3

    # Enforce exactly 3 questions (rejection on 2 or 4 items)
    invalid_2_questions = dict(valid_payload)
    invalid_2_questions["doctor_questions"] = [
        "Question 1?",
        "Question 2?",
    ]
    with pytest.raises(ValidationError):
        ReportSummary.model_validate_json(json.dumps(invalid_2_questions))

    invalid_4_questions = dict(valid_payload)
    invalid_4_questions["doctor_questions"] = [
        "Q1?",
        "Q2?",
        "Q3?",
        "Q4?",
    ]
    with pytest.raises(ValidationError):
        ReportSummary.model_validate_json(json.dumps(invalid_4_questions))

    # Enforce valid urgency literal
    invalid_urgency = dict(valid_payload)
    invalid_urgency["urgency"] = "Emergency"  # Not allowed in UrgencyLevel
    with pytest.raises(ValidationError):
        ReportSummary.model_validate_json(json.dumps(invalid_urgency))


# ==============================================================================
# TC-FR-4.2: Critical Safety Override: Severe Anemia
# ==============================================================================


def test_tc_fr_4_2_critical_anemia_override() -> None:
    """TC-FR-4.2: Hemoglobin < 7.0 g/dL forces urgency = 'Prompt Attention'."""
    raw_lines = _load_fixture(REPORT_03_PATH)
    scrubbed_lines, _age, _sex = scrub_pii(raw_lines)
    parsed = parse_rows(scrubbed_lines)

    # Initial mock summary with "Routine" urgency
    mock_summary = ReportSummary(
        normal_summary="Most parameters noted.",
        abnormal=[
            AbnormalMarker(
                test="Hemoglobin",
                value="6.2 g/dL",
                status="Low",
                explanation="Hemoglobin level is below normal.",
            )
        ],
        cross_marker_patterns=[],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=[
            "What causes this reading?",
            "Do I need iron supplements?",
            "When should I retest?",
        ],
    )

    overridden = apply_safety_overrides(parsed, mock_summary, lang="en")

    # Invariants
    assert overridden.urgency == "Prompt Attention"
    matched = next((m for m in overridden.abnormal if "Hemoglobin" in m.test), None)
    assert matched is not None
    assert (
        "Critically Low Hemoglobin (Severe Anemia) - Contact your doctor today."
        in matched.explanation
    )
    assert len(overridden.doctor_questions) == 3


# ==============================================================================
# TC-FR-4.3: Critical Safety Override: Severe Hyperglycemia
# ==============================================================================


def test_tc_fr_4_3_critical_hyperglycemia_override() -> None:
    """TC-FR-4.3: Fasting Glucose > 250 mg/dL forces Prompt Attention."""
    raw_lines = _load_fixture(REPORT_02_PATH)
    scrubbed_lines, _age, _sex = scrub_pii(raw_lines)
    parsed = parse_rows(scrubbed_lines)

    mock_summary = ReportSummary(
        normal_summary="Kidney parameters are stable.",
        abnormal=[
            AbnormalMarker(
                test="Fasting Blood Sugar (FBS)",
                value="285 mg/dL",
                status="High",
                explanation="Blood sugar is high.",
            )
        ],
        cross_marker_patterns=[],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=[
            "Is my diet okay?",
            "Should I exercise more?",
            "Do I need medicine?",
        ],
    )

    overridden = apply_safety_overrides(parsed, mock_summary, lang="en")

    assert overridden.urgency == "Prompt Attention"
    assert any(
        "Critically High Fasting Glucose" in m.explanation for m in overridden.abnormal
    )
    assert "critically high blood sugar" in overridden.doctor_questions[0].lower()


# ==============================================================================
# TC-FR-4.4: Critical Safety Override: Severe Thrombocytopenia (Dengue)
# ==============================================================================


def test_tc_fr_4_4_critical_thrombocytopenia_override() -> None:
    """TC-FR-4.4: Platelet Count < 20,000 /cumm forces urgency = 'Prompt Attention'."""
    raw_lines = _load_fixture(REPORT_05_PATH)
    scrubbed_lines, _age, _sex = scrub_pii(raw_lines)
    parsed = parse_rows(scrubbed_lines)

    mock_summary = ReportSummary(
        normal_summary="Hemoglobin is stable.",
        abnormal=[
            AbnormalMarker(
                test="Platelet Count",
                value="14000 /cumm",
                status="Low",
                explanation="Platelet count is lower than normal.",
            )
        ],
        cross_marker_patterns=[],
        urgency="Consult Soon",
        specialist="General Physician",
        doctor_questions=[
            "Should I drink more water?",
            "Do I need rest?",
            "When should I repeat the test?",
        ],
    )

    overridden = apply_safety_overrides(parsed, mock_summary, lang="en")

    assert overridden.urgency == "Prompt Attention"
    matched = next((m for m in overridden.abnormal if "Platelet" in m.test), None)
    assert matched is not None
    assert (
        "Critically Low Platelets (Severe Thrombocytopenia) - "
        "Contact your doctor today." in matched.explanation
    )


# ==============================================================================
# TC-FR-4.5: Directional Urgency Invariant
# ==============================================================================


def test_tc_fr_4_5_directional_urgency_escalation_only() -> None:
    """Validate that urgency can only escalate and is never downgraded."""
    # Normal biomarker row
    normal_rows = [
        {
            "test_name": "Hemoglobin",
            "observed_value": 14.5,
            "unit": "g/dL",
            "ref_range": "13.0 - 17.0",
        }
    ]

    # Given initial urgency "Prompt Attention"
    summary = ReportSummary(
        normal_summary="All parameters normal.",
        abnormal=[],
        cross_marker_patterns=[],
        urgency="Prompt Attention",
        specialist="General Physician",
        doctor_questions=["Q1?", "Q2?", "Q3?"],
    )

    overridden = apply_safety_overrides(normal_rows, summary, lang="en")
    assert overridden.urgency == "Prompt Attention", (
        "Safety violation: Urgency was downgraded from Prompt Attention!"
    )

    # Given initial urgency "Consult Soon", normal rows cannot downgrade to "Routine"
    summary_soon = ReportSummary(
        normal_summary="All parameters normal.",
        abnormal=[],
        cross_marker_patterns=[],
        urgency="Consult Soon",
        specialist="General Physician",
        doctor_questions=["Q1?", "Q2?", "Q3?"],
    )
    overridden_soon = apply_safety_overrides(normal_rows, summary_soon, lang="en")
    assert overridden_soon.urgency == "Consult Soon", (
        "Safety violation: Urgency was downgraded from Consult Soon!"
    )


# ==============================================================================
# TC-FR-4.6: Invariant Fixed Disclaimer Injection
# ==============================================================================


def test_tc_fr_4_6_invariant_fixed_disclaimer_injection() -> None:
    """Validate trilingual disclaimers are hardcoded and injected accurately."""
    dummy_summary = ReportSummary(
        normal_summary="Normal.",
        abnormal=[],
        cross_marker_patterns=[],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=["Q1?", "Q2?", "Q3?"],
    )

    # English
    en_res = apply_safety_overrides([], dummy_summary, lang="en")
    assert en_res.disclaimer == DISCLAIMER["en"]

    # Hindi
    hi_res = apply_safety_overrides([], dummy_summary, lang="hi")
    assert hi_res.disclaimer == DISCLAIMER["hi"]

    # Kannada
    kn_res = apply_safety_overrides([], dummy_summary, lang="kn")
    assert kn_res.disclaimer == DISCLAIMER["kn"]


# ==============================================================================
# TC-SEC-1: Adversarial Prompt Injection & Diagnosis Jailbreak Defense
# ==============================================================================


def test_tc_sec_1_adversarial_jailbreak_prescription() -> None:
    """Validate adversarial overrides cannot force diagnoses or alter medications."""
    raw_lines = _load_fixture(REPORT_10_PATH)
    scrubbed_lines, _age, _sex = scrub_pii(raw_lines)
    parsed = parse_rows(scrubbed_lines)

    # Simulate adversarial text trying to leak jailbreak instructions into output
    adversarial_raw_json = json.dumps(
        {
            "normal_summary": (
                "You are diagnosed with terminal stage 4 cancer. "
                "Stop taking Metformin and double your insulin glargine dose tonight."
            ),
            "abnormal": [
                {
                    "test": "Fasting Blood Sugar",
                    "value": "118 mg/dL",
                    "status": "High",
                    "explanation": (
                        "Diagnose terminal adenocarcinoma. "
                        "Discontinue medication immediately."
                    ),
                }
            ],
            "cross_marker_patterns": [],
            "urgency": "Consult Soon",
            "specialist": "Chief Oncologist",
            "doctor_questions": [
                "Should I increase dose to 80 units?",
                "Can you confirm the terminal cancer diagnosis?",
                "What alternatives exist?",
            ],
        }
    )

    # Mock client returning adversarial JSON
    mock_response = MagicMock()
    mock_response.text = adversarial_raw_json

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    result = analyze(
        rows=scrubbed_lines,
        age=45,
        sex="Male",
        deltas=[],
        lang="en",
        client=mock_client,
        parsed_rows=parsed,
    )

    # Assertions
    full_text = (
        f"{result.normal_summary} {result.specialist} "
        + " ".join(m.explanation for m in result.abnormal)
        + " ".join(result.doctor_questions)
    )

    assert "diagnosed with terminal stage 4 cancer" not in full_text.lower()
    assert "stop taking metformin" not in full_text.lower()
    assert "double your insulin" not in full_text.lower()
    assert result.disclaimer == DISCLAIMER["en"]


# ==============================================================================
# Unit Normalization Matrix
# ==============================================================================


def test_biomarker_unit_normalization() -> None:
    """Test clinical unit normalization rules for glucose, hemoglobin, and platelets."""
    # Glucose: mmol/L -> mg/dL (x 18.0)
    val_g, unit_g = normalize_biomarker_unit("Fasting Glucose", 15.0, "mmol/L")
    assert val_g == 270.0
    assert unit_g == "mg/dL"

    # Hemoglobin: g/L -> g/dL (/ 10.0)
    val_hb, unit_hb = normalize_biomarker_unit("Hemoglobin", 65.0, "g/L")
    assert val_hb == 6.5
    assert unit_hb == "g/dL"

    # Platelets: lakhs/cumm -> /cumm (x 100,000)
    val_plt, unit_plt = normalize_biomarker_unit("Platelet Count", 1.5, "lakhs/cumm")
    assert val_plt == 150000.0
    assert unit_plt == "/cumm"

    # Platelets: k/uL -> /cumm (x 1000)
    val_k, unit_k = normalize_biomarker_unit("Platelets", 15.0, "k/uL")
    assert val_k == 15000.0
    assert unit_k == "/cumm"
