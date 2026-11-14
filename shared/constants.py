"""Shared Constants for ReportSaathi (Python Backend).

Single source of truth matching shared/constants.ts and docs/06a-api-contract.md.
"""

from typing import Final, Literal

SERVICE_NAME: Final[str] = "ReportSaathi"
SERVICE_VERSION: Final[str] = "1.0.0"

SupportedLanguage = Literal["en", "hi", "kn"]
SUPPORTED_LANGUAGES: Final[tuple[SupportedLanguage, ...]] = ("en", "hi", "kn")

UrgencyLevel = Literal["Routine", "Consult Soon", "Prompt Attention"]
URGENCY_LEVELS: Final[tuple[UrgencyLevel, ...]] = (
    "Routine",
    "Consult Soon",
    "Prompt Attention",
)

DISCLAIMER: Final[dict[str, str]] = {
    "en": (
        "This explains your report in simple words. "
        "It is not a diagnosis. Please show the report to your doctor."
    ),
    "hi": (
        "यह आपकी रिपोर्ट को आसान शब्दों में समझाता है। "
        "यह कोई निदान नहीं है। कृपया रिपोर्ट अपने डॉक्टर को दिखाएं।"
    ),
    "kn": (
        "ಇದು ನಿಮ್ಮ ವರದಿಯನ್ನು ಸರಳ ಪದಗಳಲ್ಲಿ ವಿವರಿಸುತ್ತದೆ. "
        "ಇದು ರೋಗನಿರ್ಣಯವಲ್ಲ. ದಯವಿಟ್ಟು ವರದಿಯನ್ನು ನಿಮ್ಮ ವೈದ್ಯರಿಗೆ ತೋರಿಸಿ."
    ),
}
