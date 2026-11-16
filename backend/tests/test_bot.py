"""Unit and integration test suite for Task PR-07 (Telegram Bot Event Handler).

Covers:
- /start command onboarding and DPDP Act 2023 consent gate keyboard (TC-FR-1.1).
- Unconsented upload block preventing premature analysis.
- Consent agreement callback updating DB and unlocking upload (TC-FR-1.2).
- Vernacular language selection callbacks updating preferences (TC-FR-1.3).
- Two-step /delete and [🗑️ Delete My Data] data erasure confirmation (TC-FR-5.3).
- Multimodal document & photo intake, immediate status update, card formatting,
  and in-place message edit with action keyboard.
- Application factory setup and handler registration.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.constants import ParseMode

from backend.bot import (
    callback_query_handler,
    create_bot_application,
    delete_command,
    format_summary_card,
    get_consent_keyboard,
    get_delete_confirm_keyboard,
    get_summary_keyboard,
    handle_document_or_photo,
    start_command,
)
from backend.gemini_analyzer import AbnormalMarker, ReportSummary


@pytest.fixture
def sample_summary() -> ReportSummary:
    """Fixture returning a standard mock ReportSummary."""
    return ReportSummary(
        normal_summary="All basic metabolic markers are within standard bounds.",
        abnormal=[
            AbnormalMarker(
                test="Fasting Blood Sugar",
                value="142.0 mg/dL",
                status="High",
                explanation="Slightly above normal fasting glucose levels.",
                trend_note="+12.0",
            )
        ],
        cross_marker_patterns=[
            "Isolated fasting elevation warrants routine glycemic monitoring."
        ],
        urgency="Routine",
        specialist="General Physician",
        doctor_questions=[
            "Should I schedule an HbA1c test to assess 3-month glycemic control?",
            "Are there dietary modifications recommended for my fasting sugar?",
            "When should I follow up for another fasting glucose test?",
        ],
    )


# ==============================================================================
# 1. UI Formatting & Keyboard Tests
# ==============================================================================


def test_format_summary_card(sample_summary: ReportSummary) -> None:
    """Validate summary card contains required sections and statutory disclaimer."""
    card = format_summary_card(sample_summary, lang="en")

    assert "📋 *Report Summary*" in card
    assert "Routine" in card
    assert "General Physician" in card
    assert "Fasting Blood Sugar" in card
    assert "142.0 mg/dL" in card
    assert "+12.0" in card
    assert "Questions to ask your doctor:" in card
    assert (
        "This explains your report in simple words. It is not a diagnosis." in card
    )


def test_format_summary_card_indic_disclaimers(sample_summary: ReportSummary) -> None:
    """Validate Hindi and Kannada fixed disclaimers are appended correctly."""
    card_hi = format_summary_card(sample_summary, lang="hi")
    assert "यह आपकी रिपोर्ट को आसान शब्दों में समझाता है।" in card_hi

    card_kn = format_summary_card(sample_summary, lang="kn")
    assert "ಇದು ನಿಮ್ಮ ವರದಿಯನ್ನು ಸರಳ ಪದಗಳಲ್ಲಿ ವಿವರಿಸುತ್ತದೆ." in card_kn


def test_keyboards() -> None:
    """Verify inline keyboard structures and callback data."""
    consent_kb = get_consent_keyboard()
    assert len(consent_kb.inline_keyboard) == 2
    assert consent_kb.inline_keyboard[0][0].callback_data == "consent_agree"

    card_kb = get_summary_keyboard(report_id="rep-123", user_id="usr-456")
    assert len(card_kb.inline_keyboard) == 2
    assert card_kb.inline_keyboard[0][1].callback_data == "tr_hi_rep-123"
    assert card_kb.inline_keyboard[1][0].callback_data == "trends_usr-456"
    assert card_kb.inline_keyboard[1][1].callback_data == "delete_confirm_prompt"

    del_kb = get_delete_confirm_keyboard()
    assert len(del_kb.inline_keyboard) == 1
    assert len(del_kb.inline_keyboard[0]) == 2
    assert del_kb.inline_keyboard[0][0].callback_data == "delete_confirmed"


# ==============================================================================
# 2. Command Handlers (/start, /delete)
# ==============================================================================


def test_start_command_flow() -> None:
    """TC-FR-1.1: Verify /start registers user and displays consent gate."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321
    mock_update.effective_user.first_name = "Ramesh"
    mock_update.message.reply_text = AsyncMock()
    mock_context = MagicMock()

    with patch("backend.bot.get_or_create_user") as mock_db_user:
        mock_db_user.return_value = {
            "id": "usr-1",
            "telegram_chat_id": 987654321,
            "consent_at": None,
            "preferred_language": "en",
        }

        asyncio.run(start_command(mock_update, mock_context))

        mock_db_user.assert_called_once_with(chat_id=987654321, lang="en")
        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        assert "Welcome to ReportSaathi" in args[0]
        assert "Privacy & Safety Notice" in args[0]
        assert "/delete" in args[0]
        assert kwargs["parse_mode"] == ParseMode.MARKDOWN
        assert kwargs["reply_markup"] is not None


def test_delete_command_flow() -> None:
    """TC-FR-5.3: Verify /delete initiates 2-step confirmation warning."""
    mock_update = MagicMock()
    mock_update.message.reply_text = AsyncMock()
    mock_context = MagicMock()

    asyncio.run(delete_command(mock_update, mock_context))

    mock_update.message.reply_text.assert_called_once()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Permanent Data Deletion" in args[0]
    assert kwargs["reply_markup"] is not None


# ==============================================================================
# 3. Callback Queries (Consent, Language, Erasure, Trends)
# ==============================================================================


def test_callback_consent_agree() -> None:
    """TC-FR-1.2: Agreeing to terms persists consent and invites report upload."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321
    mock_query = AsyncMock()
    mock_query.data = "consent_agree"
    mock_query.message.chat_id = 987654321
    mock_update.callback_query = mock_query
    mock_context = MagicMock()

    with (
        patch("backend.bot.get_or_create_user") as mock_user,
        patch("backend.bot.set_consent") as mock_consent,
    ):
        mock_user.return_value = {"id": "usr-1", "telegram_chat_id": 987654321}

        asyncio.run(callback_query_handler(mock_update, mock_context))

        mock_query.answer.assert_called_once()
        mock_consent.assert_called_once_with("usr-1")
        mock_query.edit_message_text.assert_called_once()
        args, _ = mock_query.edit_message_text.call_args
        assert "Terms Accepted" in args[0]


def test_callback_language_selection() -> None:
    """TC-FR-1.3: Setting language preference persists in DB."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321
    mock_query = AsyncMock()
    mock_query.data = "lang_hi"
    mock_query.message.chat_id = 987654321
    mock_update.callback_query = mock_query
    mock_context = MagicMock()

    with (
        patch("backend.bot.get_or_create_user") as mock_user,
        patch("backend.bot.set_language") as mock_lang,
    ):
        mock_user.return_value = {"id": "usr-1"}

        asyncio.run(callback_query_handler(mock_update, mock_context))

        mock_lang.assert_called_once_with("usr-1", "hi")
        mock_query.edit_message_text.assert_called_once()


def test_callback_delete_confirmed() -> None:
    """TC-FR-5.3: Confirming deletion wipes user data via delete_user_data()."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321
    mock_query = AsyncMock()
    mock_query.data = "delete_confirmed"
    mock_query.message.chat_id = 987654321
    mock_update.callback_query = mock_query
    mock_context = MagicMock()

    with patch("backend.bot.delete_user_data") as mock_del:
        asyncio.run(callback_query_handler(mock_update, mock_context))

        mock_del.assert_called_once_with(chat_id=987654321)
        mock_query.edit_message_text.assert_called_once()
        args, _ = mock_query.edit_message_text.call_args
        assert "All your data has been permanently deleted" in args[0]


def test_callback_past_trends() -> None:
    """Verifies trends query retrieves past biomarkers and displays them."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321
    mock_query = AsyncMock()
    mock_query.data = "trends_usr-1"
    mock_query.message.chat_id = 987654321
    mock_query.message.reply_text = AsyncMock()
    mock_update.callback_query = mock_query
    mock_context = MagicMock()

    with (
        patch("backend.bot.get_or_create_user") as mock_user,
        patch("backend.bot.get_user_biomarkers") as mock_bm,
    ):
        mock_user.return_value = {"id": "usr-1"}
        mock_bm.return_value = [
            {
                "test_name": "Hemoglobin",
                "observed_value": 13.8,
                "unit": "g/dL",
                "delta": 0.4,
                "recorded_at": "2026-11-15T10:00:00Z",
            }
        ]

        asyncio.run(callback_query_handler(mock_update, mock_context))

        mock_query.message.reply_text.assert_called_once()
        args, _ = mock_query.message.reply_text.call_args
        assert "Historical Biomarker Log" in args[0]
        assert "Hemoglobin" in args[0]


# ==============================================================================
# 4. Multimodal Document / Photo Intake
# ==============================================================================


def test_intake_blocks_unconsented_user() -> None:
    """TC-FR-1.1: Document upload halts when consent has not been recorded."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321
    mock_update.message.reply_text = AsyncMock()
    mock_context = MagicMock()

    with patch("backend.bot.get_or_create_user") as mock_user:
        mock_user.return_value = {
            "id": "usr-1",
            "consent_at": None,
        }

        asyncio.run(handle_document_or_photo(mock_update, mock_context))

        mock_update.message.reply_text.assert_called_once()
        args, _ = mock_update.message.reply_text.call_args
        assert "Consent Required" in args[0]


def test_intake_processes_document_and_edits_card(
    sample_summary: ReportSummary,
) -> None:
    """Validate full flow: intake, status reply, OCR/scrub, AI analyze, edit card."""
    mock_update = MagicMock()
    mock_update.effective_chat.id = 987654321

    # Mock telegram file download
    mock_file = AsyncMock()
    file_content = b"Patient: John Doe\nHemoglobin: 13.5 g/dL (13.0 - 17.0)\n"
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(file_content))

    mock_doc = MagicMock()
    mock_doc.file_name = "lab_report.txt"
    mock_doc.file_id = "doc-123"
    mock_update.message.document = mock_doc
    mock_update.message.photo = []

    mock_context = MagicMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)

    # Mock initial status message
    mock_status_msg = AsyncMock()
    mock_update.message.reply_text = AsyncMock(return_value=mock_status_msg)

    with (
        patch("backend.bot.get_or_create_user") as mock_user,
        patch("backend.bot.find_report_by_hash", return_value=None),
        patch("backend.bot.get_user_biomarkers", return_value=[]),
        patch("backend.bot.compute_deltas", return_value=[]),
        patch("backend.bot.analyze", return_value=sample_summary),
        patch(
            "backend.bot.save_report",
            return_value="rep-abc",
        ),
    ):
        mock_user.return_value = {
            "id": "usr-1",
            "consent_at": "2026-11-15T12:00:00Z",
            "preferred_language": "en",
        }

        asyncio.run(handle_document_or_photo(mock_update, mock_context))

        # Initial acknowledgment message
        mock_update.message.reply_text.assert_called_once()
        status_text = mock_update.message.reply_text.call_args[0][0]
        assert "Analyzing... ⏳" in status_text
        assert "Personal details removed (best effort)" in status_text

        # In-place editing with final summary card
        mock_status_msg.edit_text.assert_called_once()
        card_text, kwargs = mock_status_msg.edit_text.call_args
        assert "📋 *Report Summary*" in card_text[0]
        assert kwargs["reply_markup"] is not None


# ==============================================================================
# 5. Application Factory
# ==============================================================================


def test_create_bot_application() -> None:
    """Verify application factory initializes with token and registers handlers."""
    test_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": test_token}):
        app = create_bot_application()
        assert app is not None
        # Handlers registered for start, delete, callbacks, documents/photos
        assert len(app.handlers[0]) == 4


def test_create_bot_application_missing_token() -> None:
    """Verify application factory raises ValueError if token is missing."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            create_bot_application(token=None)
