"""ReportSaathi In-Memory Vernacular Audio Note Generator.

Generates 30-45 second spoken vernacular voice notes (Hindi, Kannada, English)
using an empathetic, respectful 'grandson-to-grandmother' register.
All audio processing is strictly in-memory (io.BytesIO) to comply with
the DPDP Act 2023 zero-disk persistence requirement.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from gtts import gTTS  # type: ignore[import-untyped]

from backend.gemini_analyzer import ReportSummary

logger = logging.getLogger(__name__)


def build_spoken_script(
    summary: dict[str, Any] | ReportSummary, lang: str = "en"
) -> str:
    """Constructs a calm, conversational vernacular script for audio synthesis."""
    if isinstance(summary, ReportSummary):
        data = summary.model_dump()
    else:
        data = summary

    urgency = str(data.get("urgency", "Routine"))
    normal_text = str(data.get("normal_summary", "")).strip()
    abnormal = data.get("abnormal") or []
    questions = data.get("doctor_questions") or []

    if lang == "hi":
        return _build_hindi_script(urgency, normal_text, abnormal, questions)
    elif lang == "kn":
        return _build_kannada_script(urgency, normal_text, abnormal, questions)
    return _build_english_script(urgency, normal_text, abnormal, questions)


def _build_hindi_script(
    urgency: str,
    normal_text: str,
    abnormal: list[dict[str, Any]],
    questions: list[str],
) -> str:
    parts: list[str] = [
        "नमस्ते। यह आपकी मेडिकल जांच रिपोर्ट का आसान विवरण है।"
    ]

    if urgency == "Prompt Attention":
        parts.append(
            "कृपया ध्यान दें, रिपोर्ट में कुछ जांचें तुरंत डॉक्टर को दिखाने योग्य हैं।"
        )
    elif urgency == "Consult Soon":
        parts.append("रिपोर्ट पर डॉक्टर से जल्द परामर्श लेना उचित रहेगा।")
    else:
        parts.append("आपकी अधिकतर जांचें सामान्य दायरे में हैं।")

    if normal_text:
        parts.append(normal_text)

    if abnormal:
        parts.append("जांच में कुछ बदलाव दिखे हैं:")
        for marker in abnormal[:3]:
            test = marker.get("test", "")
            exp = marker.get("explanation", "")
            parts.append(f"{test}: {exp}")

    if questions:
        parts.append("डॉक्टर साहब से मिलने पर ये सवाल जरूर पूछें:")
        for idx, q in enumerate(questions[:3], 1):
            parts.append(f"सवाल {idx}: {q}")

    parts.append(
        "घबराने की कोई बात नहीं है। यह सिर्फ आपकी जानकारी के लिए है। "
        "कृपया अपनी रिपोर्ट डॉक्टर को जरूर दिखाएं।"
    )
    return " ".join(parts)


def _build_kannada_script(
    urgency: str,
    normal_text: str,
    abnormal: list[dict[str, Any]],
    questions: list[str],
) -> str:
    parts: list[str] = [
        "ನಮಸ್ಕಾರ. ಇದು ನಿಮ್ಮ ವೈದ್ಯಕೀಯ ವರದಿಯ ಸರಳ ವಿವರಣೆ."
    ]

    if urgency == "Prompt Attention":
        parts.append(
            "ದಯವಿಟ್ಟು ಗಮನಿಸಿ, ವರದಿಯಲ್ಲಿನ ಕೆಲವು ಅಂಶಗಳನ್ನು ತಕ್ಷಣ ವೈದ್ಯರಿಗೆ ತೋರಿಸುವುದು ಅಗತ್ಯ."
        )
    elif urgency == "Consult Soon":
        parts.append("ಈ ವರದಿಯ ಬಗ್ಗೆ ಶೀಘ್ರದಲ್ಲೇ ವೈದ್ಯರೊಂದಿಗೆ ಸಮಾಲೋಚಿಸಿ.")
    else:
        parts.append("ನಿಮ್ಮ ಹೆಚ್ಚಿನ ಪರೀಕ್ಷೆಗಳು ಸಾಮಾನ್ಯ ಮಿತಿಯಲ್ಲಿದೆ.")

    if normal_text:
        parts.append(normal_text)

    if abnormal:
        parts.append("ಕೆಲವು ಮುಖ್ಯ ಬದಲಾವಣೆಗಳು ಕಂಡುಬಂದಿವೆ:")
        for marker in abnormal[:3]:
            test = marker.get("test", "")
            exp = marker.get("explanation", "")
            parts.append(f"{test}: {exp}")

    if questions:
        parts.append("ವೈದ್ಯರನ್ನು ಭೇಟಿಯಾದಾಗ ಈ ಪ್ರಶ್ನೆಗಳನ್ನು ಕೇಳಿ:")
        for idx, q in enumerate(questions[:3], 1):
            parts.append(f"ಪ್ರಶ್ನೆ {idx}: {q}")

    parts.append(
        "ಹೆದರುವ ಅಗತ್ಯವಿಲ್ಲ. ಇದು ಕೇವಲ ಮಾಹಿತಿ ಮಾತ್ರ. "
        "ದಯವಿಟ್ಟು ವರದಿಯನ್ನು ನಿಮ್ಮ ವೈದ್ಯರಿಗೆ ತೋರಿಸಿ."
    )
    return " ".join(parts)


def _build_english_script(
    urgency: str,
    normal_text: str,
    abnormal: list[dict[str, Any]],
    questions: list[str],
) -> str:
    parts: list[str] = [
        "Hello. Here is a simple, calm explanation of your medical lab report."
    ]

    if urgency == "Prompt Attention":
        parts.append(
            "Please note, certain markers need immediate medical attention "
            "from your doctor."
        )
    elif urgency == "Consult Soon":
        parts.append("We recommend discussing these results with your doctor soon.")
    else:
        parts.append("Most evaluated tests are within normal healthy ranges.")

    if normal_text:
        parts.append(normal_text)

    if abnormal:
        parts.append("Notable findings include:")
        for marker in abnormal[:3]:
            test = marker.get("test", "")
            exp = marker.get("explanation", "")
            parts.append(f"{test}: {exp}")

    if questions:
        parts.append("Here are three questions to ask your doctor:")
        for idx, q in enumerate(questions[:3], 1):
            parts.append(f"Question {idx}: {q}")

    parts.append(
        "This explanation is for your understanding and does not replace "
        "medical advice. Please consult your healthcare provider."
    )
    return " ".join(parts)


def generate_voice_note(
    summary: dict[str, Any] | ReportSummary, lang: str = "en"
) -> bytes:
    """Synthesizes speech into an in-memory byte buffer (zero disk writes)."""
    script = build_spoken_script(summary, lang=lang)
    tts_lang = "hi" if lang == "hi" else ("kn" if lang == "kn" else "en")

    fp = io.BytesIO()
    try:
        tts = gTTS(text=script, lang=tts_lang, slow=False)
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception as exc:
        logger.error("Failed to generate voice note via gTTS: %s", exc)
        raise
