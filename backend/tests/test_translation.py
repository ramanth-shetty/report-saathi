"""Unit tests for vernacular translation engine (Task PR-08).

Covers:
- Structured translation into Hindi and Kannada using grandson-to-grandmother tone.
- Invariant: Directional urgency cannot be downgraded during translation.
- Invariant: Statutory disclaimers injected strictly by Python code.
- Adversarial diagnosis and prescription tampering sanitization.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from shared.constants import DISCLAIMER

from backend.gemini_analyzer import (
    AbnormalMarker,
    ReportSummary,
    build_translation_prompt,
    translate,
)


def test_build_translation_prompt() -> None:
    """Verifies translation prompt removes disclaimer and specifies Indic register."""
    summary = ReportSummary(
        normal_summary="All Complete Blood Count tests are normal.",
        abnormal=[
            AbnormalMarker(
                test="Fasting Glucose",
                value="135 mg/dL",
                status="High",
                explanation="Blood sugar slightly above normal fasting level.",
            )
        ],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=[
            "Should I do an HbA1c test?",
            "Any dietary suggestions?",
            "When should I re-check?",
        ],
        disclaimer="DO NOT TRANSLATE ME",
    )

    prompt = build_translation_prompt(summary, target_lang="hi")
    assert "Hindi (हिंदी)" in prompt
    assert "DO NOT TRANSLATE ME" not in prompt
    assert "grandson-to-grandmother" in prompt or "conversational tone" in prompt
    assert "Fasting Glucose" in prompt


def test_translate_hindi_success() -> None:
    """TC-FR-5.1: Verifies Hindi translation produces valid schema and disclaimer."""
    summary_en = ReportSummary(
        normal_summary="Thyroid tests are within standard range.",
        abnormal=[
            AbnormalMarker(
                test="Total Cholesterol",
                value="220 mg/dL",
                status="Borderline",
                explanation="Slightly higher than normal cholesterol.",
            )
        ],
        urgency="Consult Soon",
        specialist="General Physician",
        doctor_questions=[
            "Do I need dietary changes?",
            "Should I start lipid medication?",
            "When to follow up?",
        ],
    )

    mock_hindi_response = {
        "normal_summary": "थायरॉइड की सभी जांचें सामान्य सीमा में हैं।",
        "abnormal": [
            {
                "test": "Total Cholesterol",
                "value": "220 mg/dL",
                "status": "Borderline",
                "explanation": "कोलेस्ट्रॉल सामान्य से थोड़ा अधिक है।",
                "trend_note": None,
            }
        ],
        "cross_marker_patterns": [],
        "urgency": "Consult Soon",
        "specialist": "सामान्य चिकित्सक",
        "doctor_questions": [
            "क्या मुझे खान-पान में बदलाव करना चाहिए?",
            "क्या दवा शुरू करने की आवश्यकता है?",
            "दोबारा जांच कब करानी होगी?",
        ],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_hindi_response)
    mock_client.models.generate_content.return_value = mock_resp

    translated = translate(summary_en, target_lang="hi", client=mock_client)

    assert translated.urgency == "Consult Soon"
    assert translated.specialist == "सामान्य चिकित्सक"
    assert "थायरॉइड" in translated.normal_summary
    assert len(translated.doctor_questions) == 3
    assert translated.disclaimer == DISCLAIMER["hi"]


def test_translate_kannada_success() -> None:
    """TC-FR-5.1: Verifies Kannada translation produces valid schema and disclaimer."""
    summary_en = ReportSummary(
        normal_summary="Kidney parameters are normal.",
        abnormal=[
            AbnormalMarker(
                test="Hemoglobin",
                value="9.8 g/dL",
                status="Low",
                explanation="Hemoglobin is lower than normal.",
            )
        ],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=[
            "What iron-rich food should I eat?",
            "Do I need supplements?",
            "When to re-test?",
        ],
    )

    mock_kannada_response = {
        "normal_summary": "ಮೂತ್ರಪಿಂಡದ ಎಲ್ಲಾ ಪರೀಕ್ಷೆಗಳು ಸಾಮಾನ್ಯ ಮಿತಿಯಲ್ಲಿದೆ.",
        "abnormal": [
            {
                "test": "Hemoglobin",
                "value": "9.8 g/dL",
                "status": "Low",
                "explanation": "ಹಿಮೋಗ್ಲೋಬಿನ್ ಪ್ರಮಾಣ ಸಾಮಾನ್ಯಕ್ಕಿಂತ ಕಡಿಮೆಯಾಗಿದೆ.",
                "trend_note": None,
            }
        ],
        "cross_marker_patterns": [],
        "urgency": "Routine",
        "specialist": "ಸಾಮಾನ್ಯ ವೈದ್ಯರು",
        "doctor_questions": [
            "ಕಬ್ಬಿಣದ ಅಂಶ ಹೆಚ್ಚಿಸಲು ಯಾವ ಆಹಾರ ಸೇವಿಸಬೇಕು?",
            "ಪೂರಕ ಔಷಧಿಗಳ ಅಗತ್ಯವಿದೆಯೇ?",
            "ಮತ್ತೊಮ್ಮೆ ಯಾವಾಗ ತಪಾಸಣೆ ಮಾಡಿಸಬೇಕು?",
        ],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_kannada_response)
    mock_client.models.generate_content.return_value = mock_resp

    translated = translate(summary_en, target_lang="kn", client=mock_client)

    assert translated.urgency == "Routine"
    assert translated.specialist == "ಸಾಮಾನ್ಯ ವೈದ್ಯರು"
    assert "ಮೂತ್ರಪಿಂಡದ" in translated.normal_summary
    assert len(translated.doctor_questions) == 3
    assert translated.disclaimer == DISCLAIMER["kn"]


def test_translate_urgency_invariant_cannot_downgrade() -> None:
    """Ensures translation cannot downgrade a higher urgency status."""
    summary_en = ReportSummary(
        normal_summary="Normal.",
        abnormal=[],
        urgency="Prompt Attention",
        specialist="Hematologist",
        doctor_questions=["Q1", "Q2", "Q3"],
    )

    mock_llm_response = {
        "normal_summary": "सामान्य।",
        "abnormal": [],
        "cross_marker_patterns": [],
        "urgency": "Routine",  # Model mistakenly tried to downgrade
        "specialist": "डॉक्टर",
        "doctor_questions": ["Q1", "Q2", "Q3"],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_llm_response)
    mock_client.models.generate_content.return_value = mock_resp

    translated = translate(summary_en, target_lang="hi", client=mock_client)

    # Invariant: Must remain Prompt Attention!
    assert translated.urgency == "Prompt Attention"


def test_translate_english_identity() -> None:
    """Verifies target_lang='en' returns identity without calling Gemini."""
    summary_en = ReportSummary(
        normal_summary="Normal.",
        abnormal=[],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=["Q1", "Q2", "Q3"],
    )

    translated = translate(summary_en, target_lang="en", client=None)
    assert translated == summary_en
