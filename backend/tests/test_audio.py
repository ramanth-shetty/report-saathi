"""Unit tests for in-memory vernacular audio generation (Task PR-08).

Covers:
- Spoken script generation in English, Hindi, and Kannada (FR-5.2).
- Empathetic grandson-to-grandmother tone validation.
- In-memory gTTS voice note synthesis with zero disk writes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from backend.audio import build_spoken_script, generate_voice_note
from backend.gemini_analyzer import AbnormalMarker, ReportSummary


def test_build_spoken_script_hindi() -> None:
    """Verifies Hindi spoken script contains greeting and doctor questions."""
    summary = ReportSummary(
        normal_summary="आपकी किडनी और लिवर की जांचें सामान्य हैं।",
        abnormal=[
            AbnormalMarker(
                test="Fasting Blood Sugar",
                value="142 mg/dL",
                status="High",
                explanation="खाली पेट की शुगर थोड़ी बढ़ी हुई है।",
            )
        ],
        urgency="Routine",
        specialist="सामान्य चिकित्सक",
        doctor_questions=[
            "क्या मुझे खान-पान में कुछ बदलाव करने चाहिए?",
            "क्या तीन महीने वाली एचबीए1सी जांच करानी चाहिए?",
            "अगली बार जांच कब करानी होगी?",
        ],
    )

    script = build_spoken_script(summary, lang="hi")
    assert "नमस्ते" in script
    assert "Fasting Blood Sugar" in script
    assert "खाली पेट की शुगर थोड़ी बढ़ी हुई है।" in script
    assert "डॉक्टर साहब से मिलने पर ये सवाल जरूर पूछें" in script
    assert "खान-पान में कुछ बदलाव" in script
    assert "घबराने की कोई बात नहीं है" in script


def test_build_spoken_script_kannada() -> None:
    """Verifies Kannada spoken script contains greeting and doctor questions."""
    summary = ReportSummary(
        normal_summary="ನಿಮ್ಮ ರಕ್ತದ ಕಣಗಳ ಸಂಖ್ಯೆ ಸಾಮಾನ್ಯವಾಗಿದೆ.",
        abnormal=[
            AbnormalMarker(
                test="Hemoglobin",
                value="10.5 g/dL",
                status="Low",
                explanation="ಹಿಮೋಗ್ಲೋಬಿನ್ ಪ್ರಮಾಣ ಸ್ವಲ್ಪ ಕಡಿಮೆಯಾಗಿದೆ.",
            )
        ],
        urgency="Consult Soon",
        specialist="ಸಾಮಾನ್ಯ ವೈದ್ಯರು",
        doctor_questions=[
            "ಕಬ್ಬಿಣದ ಅಂಶ ಹೆಚ್ಚಿಸಲು ಯಾವ ಆಹಾರ ಸೇವಿಸಬೇಕು?",
            "ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳುವ ಅಗತ್ಯವಿದೆಯೇ?",
            "ಮತ್ತೊಮ್ಮೆ ಯಾವಾಗ ತಪಾಸಣೆ ಮಾಡಿಸಬೇಕು?",
        ],
    )

    script = build_spoken_script(summary, lang="kn")
    assert "ನಮಸ್ಕಾರ" in script
    assert "ಶೀಘ್ರದಲ್ಲೇ ವೈದ್ಯರೊಂದಿಗೆ ಸಮಾಲೋಚಿಸಿ" in script
    assert "Hemoglobin" in script
    assert "ಹಿಮೋಗ್ಲೋಬಿನ್ ಪ್ರಮಾಣ ಸ್ವಲ್ಪ ಕಡಿಮೆಯಾಗಿದೆ" in script
    assert "ವೈದ್ಯರನ್ನು ಭೇಟಿಯಾದಾಗ ಈ ಪ್ರಶ್ನೆಗಳನ್ನು ಕೇಳಿ" in script
    assert "ಹೆದರುವ ಅಗತ್ಯವಿಲ್ಲ" in script


def test_build_spoken_script_english_prompt_attention() -> None:
    """Verifies English script escalates urgency appropriately for critical values."""
    summary = ReportSummary(
        normal_summary="Platelet count is normal.",
        abnormal=[
            AbnormalMarker(
                test="Fasting Glucose",
                value="280 mg/dL",
                status="High",
                explanation="Critically high blood sugar level.",
            )
        ],
        urgency="Prompt Attention",
        specialist="Endocrinologist",
        doctor_questions=[
            "What immediate action is needed for this glucose level?",
            "Should medication be adjusted today?",
            "When should I re-test my blood sugar?",
        ],
    )

    script = build_spoken_script(summary, lang="en")
    assert "Hello" in script
    assert "immediate medical attention" in script
    assert "Fasting Glucose" in script
    assert "Question 1" in script


def test_generate_voice_note_in_memory() -> None:
    """Verifies voice note generation returns valid audio bytes in memory."""
    summary = ReportSummary(
        normal_summary="All normal.",
        abnormal=[],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=["Question 1", "Question 2", "Question 3"],
    )

    # Test with mock gTTS to verify in-memory buffer handling
    with patch("backend.audio.gTTS") as mock_gtts_cls:
        mock_instance = mock_gtts_cls.return_value

        def fake_write(fp: Any) -> None:
            fp.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00")

        mock_instance.write_to_fp.side_effect = fake_write

        audio_bytes = generate_voice_note(summary, lang="kn")
        assert len(audio_bytes) > 0
        assert audio_bytes.startswith(b"RIFF")
        mock_gtts_cls.assert_called_once()
