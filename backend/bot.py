"""ReportSaathi Telegram Bot Asynchronous Event Handler.

Implements:
- Asynchronous python-telegram-bot (v21+) event processing.
- First-contact onboarding, terms, and DPDP Act 2023 consent gate.
- Document and photo intake with in-memory processing (no disk persistence).
- Instant "Analyzing... ⏳" status message with in-place card editing.
- Trilingual translation switching ([🇮🇳 हिंदी], [🇮🇳 ಕನ್ನಡ], [🇬🇧 English]).
- Longitudinal trend review and statutory cascading data erasure (/delete).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shared.constants import DISCLAIMER
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from backend.database import (
    compute_deltas,
    compute_report_hash,
    delete_user_data,
    find_report_by_hash,
    get_or_create_user,
    get_translation,
    get_user_biomarkers,
    save_report,
    save_translation,
    set_consent,
    set_language,
)
from backend.gemini_analyzer import (
    ReportSummary,
    analyze,
    apply_safety_overrides,
)
from backend.ocr_scrub import (
    ocr_rows,
    parse_rows,
    preprocess,
    rasterize_pdf,
    scrub_pii,
)

logger = logging.getLogger("reportsaathi.bot")

WELCOME_TEXT = (
    "👋 *Welcome to ReportSaathi* — your Family Health Translator.\n\n"
    "We explain complex medical lab reports in simple, jargon-free words "
    "that you can easily understand and forward to older relatives.\n\n"
    "🛡️ *Privacy & Safety Notice:*\n"
    "• ReportSaathi explains, it *does not diagnose* or alter prescriptions.\n"
    "• All personal identifiers (name, phone, address) are *removed in memory* "
    "before any AI analysis.\n"
    "• You can permanently erase all your data anytime with /delete.\n\n"
    "Please accept the terms to get started:"
)

CONSENT_REQUIRED_MSG = (
    "⚠️ *Consent Required*\n\n"
    "Please tap *[✅ I Agree & Continue]* to accept our terms "
    "and enable report analysis."
)


# ==============================================================================
# 1. Keyboards & Presentation Formatting
# ==============================================================================


def get_consent_keyboard() -> InlineKeyboardMarkup:
    """Builds inline keyboard for initial user onboarding and terms consent."""
    keyboard = [
        [InlineKeyboardButton("✅ I Agree & Continue", callback_data="consent_agree")],
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi"),
            InlineKeyboardButton("🇮🇳 ಕನ್ನಡ", callback_data="lang_kn"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_summary_keyboard(report_id: str, user_id: str) -> InlineKeyboardMarkup:
    """Builds inline action keyboard for a delivered summary card."""
    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 English", callback_data=f"tr_en_{report_id}"),
            InlineKeyboardButton("🇮🇳 हिंदी", callback_data=f"tr_hi_{report_id}"),
            InlineKeyboardButton("🇮🇳 ಕನ್ನಡ", callback_data=f"tr_kn_{report_id}"),
        ],
        [
            InlineKeyboardButton("📈 Past Trends", callback_data=f"trends_{user_id}"),
            InlineKeyboardButton(
                "🗑️ Delete My Data", callback_data="delete_confirm_prompt"
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_delete_confirm_keyboard() -> InlineKeyboardMarkup:
    """Builds two-step confirmation keyboard for DPDP statutory data purge."""
    keyboard = [
        [
            InlineKeyboardButton(
                "❌ Yes, Permanently Delete", callback_data="delete_confirmed"
            ),
            InlineKeyboardButton("Cancel", callback_data="delete_cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def format_summary_card(
    summary_data: dict[str, Any] | ReportSummary, lang: str = "en"
) -> str:
    """Formats structured report data into a clean, markdown-friendly Telegram card."""
    if isinstance(summary_data, ReportSummary):
        data = summary_data.model_dump()
    else:
        data = summary_data

    urgency = str(data.get("urgency", "Routine"))
    urgency_emoji = {
        "Routine": "🟢",
        "Consult Soon": "🟡",
        "Prompt Attention": "🔴",
    }.get(urgency, "ℹ️")

    specialist = str(data.get("specialist", "General Physician"))
    normal_text = str(data.get("normal_summary", "")).strip()
    abnormal = data.get("abnormal") or []
    questions = data.get("doctor_questions") or []
    disclaimer = str(data.get("disclaimer") or DISCLAIMER.get(lang, DISCLAIMER["en"]))

    lines: list[str] = [
        "📋 *Report Summary*",
        f"Urgency: {urgency_emoji} *{urgency}*",
        f"Recommended Specialist: *{specialist}*",
        "",
        "*Normal Parameters:*",
        normal_text or "All evaluated parameters are within standard intervals.",
    ]

    if abnormal:
        lines.append("")
        lines.append("*Notable / Out-of-Range Biomarkers:*")
        for item in abnormal:
            test = item.get("test", "")
            val = item.get("value", "")
            status = item.get("status", "")
            exp = item.get("explanation", "")
            note = item.get("trend_note")
            trend_str = f" _({note})_" if note else ""
            lines.append(f"• *{test}*: {val} [{status}]{trend_str}\n  {exp}")

    if questions:
        lines.append("")
        lines.append("*Questions to ask your doctor:*")
        for idx, q in enumerate(questions[:3], 1):
            lines.append(f"{idx}. {q}")

    lines.append("")
    lines.append(f"_{disclaimer}_")

    return "\n".join(lines)


# ==============================================================================
# 2. Command Handlers
# ==============================================================================


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /start command with user registration and consent terms."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    try:
        get_or_create_user(chat_id=chat_id, lang="en")
    except Exception as exc:
        logger.error("Failed to register user in start_command: %s", exc)

    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_consent_keyboard(),
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /delete command with explicit confirmation dialog."""
    if not update.message:
        return

    warning_text = (
        "⚠️ *Permanent Data Deletion*\n\n"
        "Are you sure you want to permanently erase all your uploaded reports, "
        "biomarker history, and language preferences?\n\n"
        "This cannot be undone."
    )
    await update.message.reply_text(
        warning_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_delete_confirm_keyboard(),
    )


# ==============================================================================
# 3. Callback Query Handlers
# ==============================================================================


async def callback_query_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Routes inline button taps for consent, language switches, and deletions."""
    query = update.callback_query
    if not query or not query.data or not update.effective_chat:
        return

    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    # 1. Affirmative consent agreed
    if data == "consent_agree":
        try:
            user = get_or_create_user(chat_id=chat_id)
            set_consent(user["id"])
            await query.edit_message_text(
                "✅ *Terms Accepted*\n\n"
                "You are all set! You can now send or forward a photo or PDF "
                "of your lab report.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            logger.error("Failed to record consent: %s", exc)
            await query.edit_message_text(
                "✅ Terms accepted. You can now send a lab report photo or PDF."
            )
        return

    # 2. Onboarding language selection
    if data.startswith("lang_"):
        chosen_lang = data.split("_")[1]
        try:
            user = get_or_create_user(chat_id=chat_id)
            set_language(user["id"], chosen_lang)
            lang_names = {"en": "English", "hi": "हिंदी", "kn": "ಕನ್ನಡ"}
            lang_label = lang_names.get(chosen_lang, "English")
            await query.edit_message_text(
                f"🌐 Preferred language set to *{lang_label}*.\n\n"
                "Please tap *[✅ I Agree & Continue]* to complete setup.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_consent_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to set language: %s", exc)
        return

    # 3. Delete confirmation prompt
    if data == "delete_confirm_prompt":
        warning_text = (
            "⚠️ *Permanent Data Deletion*\n\n"
            "Are you sure you want to permanently erase all your data?\n"
            "This cannot be undone."
        )
        await query.edit_message_text(
            warning_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_delete_confirm_keyboard(),
        )
        return

    # 4. Deletion confirmed
    if data == "delete_confirmed":
        try:
            delete_user_data(chat_id=chat_id)
            await query.edit_message_text(
                "🗑️ *All your data has been permanently deleted.* \n\n"
                "In compliance with the DPDP Act 2023, all records, reports, "
                "and biomarker trends have been wiped. Send /start to begin anew.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            logger.error("Failed to delete user data: %s", exc)
            await query.edit_message_text(
                "Error processing data deletion. Please try again or contact support."
            )
        return

    # 5. Deletion cancelled
    if data == "delete_cancel":
        await query.edit_message_text(
            "👍 Deletion cancelled. Your data remains secure."
        )
        return

    # 6. Vernacular summary translation switch (tr_<lang>_<report_id>)
    if data.startswith("tr_"):
        parts = data.split("_")
        if len(parts) >= 3:
            target_lang = parts[1]
            report_id = "_".join(parts[2:])
            try:
                cached_trans = get_translation(report_id, target_lang)
                if cached_trans:
                    new_text = format_summary_card(cached_trans, lang=target_lang)
                    user = get_or_create_user(chat_id=chat_id)
                    await query.edit_message_text(
                        new_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_summary_keyboard(report_id, user["id"]),
                    )
                else:
                    await query.answer("Translation not yet cached.", show_alert=False)
            except Exception as exc:
                logger.error("Failed to switch translation: %s", exc)
        return

    # 7. Trends review (trends_<user_id>)
    if data.startswith("trends_"):
        try:
            user = get_or_create_user(chat_id=chat_id)
            history = get_user_biomarkers(user["id"])
            if not history:
                await query.answer(
                    "No previous reports found for trend comparison.",
                    show_alert=True,
                )
            else:
                trend_lines = ["📈 *Historical Biomarker Log:*"]
                for h in history[:8]:
                    test = h.get("test_name", "")
                    val = h.get("observed_value", "")
                    unit = h.get("unit", "")
                    date = h.get("recorded_at", "")
                    trend_lines.append(f"• {date}: {test} = {val} {unit}")
                await query.message.reply_text(  # type: ignore[union-attr]
                    "\n".join(trend_lines), parse_mode=ParseMode.MARKDOWN
                )
        except Exception as exc:
            logger.error("Failed to show trends: %s", exc)


# ==============================================================================
# 4. Multimodal File Intake (Photos & Documents)
# ==============================================================================


async def handle_document_or_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Processes uploaded report photos and PDF documents.

    Flow:
    1. Consent check: block if unconsented.
    2. Instant acknowledgement: "Analyzing... ⏳".
    3. Memory intake and rasterization/OCR.
    4. Blurry intercept quality gate.
    5. Local PII scrub, deduplication check, AI analysis, safety overrides.
    6. In-place card edit and action keyboard attachment.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    # 1. Check consent gate
    try:
        user = get_or_create_user(chat_id=chat_id)
        if not user.get("consent_at"):
            await update.message.reply_text(
                CONSENT_REQUIRED_MSG,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_consent_keyboard(),
            )
            return
    except Exception as exc:
        logger.error("User retrieval failed during intake: %s", exc)
        user = {"id": f"chat_{chat_id}", "preferred_lang": "en"}

    user_lang = str(user.get("preferred_lang") or "en")
    user_id = str(user["id"])

    # 2. Immediate user acknowledgement
    status_msg = await update.message.reply_text(
        "Analyzing... ⏳ Personal details removed (best effort)."
    )

    try:
        # 3. Download bytes into RAM
        file_bytes: bytes = b""
        filename = ""

        if update.message.photo:
            photo = update.message.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            file_bytes = bytes(await tg_file.download_as_bytearray())
            filename = "report.jpg"
        elif update.message.document:
            doc = update.message.document
            tg_file = await context.bot.get_file(doc.file_id)
            file_bytes = bytes(await tg_file.download_as_bytearray())
            filename = doc.file_name or "report.pdf"
        else:
            await status_msg.edit_text(
                "Please upload a photo or PDF file of your lab report."
            )
            return

        # 4. OCR / Rasterize
        raw_lines: list[str] = []
        is_pdf = filename.lower().endswith(".pdf")
        is_text = filename.lower().endswith(".txt")

        if is_text:
            raw_lines = [
                line.strip()
                for line in file_bytes.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            ]
        elif is_pdf:
            page_images = rasterize_pdf(file_bytes, dpi=300)
            total_conf = 0.0
            page_count = 0
            for page in page_images:
                pre = preprocess(page)
                lines, conf = ocr_rows(pre)
                raw_lines.extend(lines)
                total_conf += conf
                page_count += 1
            avg_conf = (total_conf / page_count) if page_count > 0 else 0.0
            if avg_conf < 55.0:
                await status_msg.edit_text(
                    "The photo is blurry or angled. Please place the "
                    "strip flat under good lighting and take a straight-on photo."
                )
                return
        else:
            pre = preprocess(file_bytes)
            lines, avg_conf = ocr_rows(pre)
            if avg_conf < 55.0:
                await status_msg.edit_text(
                    "The photo is blurry or angled. Please place the "
                    "strip flat under good lighting and take a straight-on photo."
                )
                return
            raw_lines = lines

        # Immediate memory purge of original binary buffer
        del file_bytes

        if not raw_lines:
            await status_msg.edit_text(
                "The photo is blurry or angled. Please place the "
                "strip flat under good lighting and take a straight-on photo."
            )
            return

        # 5. Local PII scrubbing & row parsing
        scrubbed_lines, age, sex = scrub_pii(raw_lines)
        parsed_rows = parse_rows(scrubbed_lines)

        # 6. Deduplication Cache Check (0 AI calls on hit)
        report_hash = compute_report_hash(scrubbed_lines)
        cached = find_report_by_hash(user_id, report_hash)
        if cached:
            cached_id = str(cached["id"])
            field_name = (
                f"summary_{user_lang}" if user_lang in ("hi", "kn") else "summary_en"
            )
            cached_summary = cached.get(field_name) or cached.get("summary_en")
            if cached_summary:
                card_text = format_summary_card(cached_summary, lang=user_lang)
                await status_msg.edit_text(
                    card_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_summary_keyboard(cached_id, user_id),
                )
                return

        # 7. Longitudinal Trend Deltas
        history = get_user_biomarkers(user_id)
        deltas = compute_deltas(parsed_rows, history)

        # 8. AI Analysis & Safety Overrides
        summary: ReportSummary = analyze(
            rows=scrubbed_lines,
            age=age,
            sex=sex,
            deltas=deltas,
            lang=user_lang,
            parsed_rows=parsed_rows,
        )
        summary = apply_safety_overrides(parsed_rows, summary, lang=user_lang)

        # 9. Persistence
        summary_dict = summary.model_dump()
        report_id = save_report(
            user_id=user_id,
            report_hash=report_hash,
            summary_en=summary_dict,
            urgency=summary.urgency,
            biomarker_rows=parsed_rows,
        )

        if user_lang != "en":
            save_translation(
                report_id=report_id,
                lang=user_lang,
                summary_json=summary_dict,
            )

        # 10. Edit message with final summary card
        card_text = format_summary_card(summary, lang=user_lang)
        await status_msg.edit_text(
            card_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_summary_keyboard(report_id, user_id),
        )

    except Exception as exc:
        logger.error("Pipeline failure in handle_document_or_photo: %s", exc)
        await status_msg.edit_text(
            "An error occurred while analyzing the report. Please try again."
        )


# ==============================================================================
# 5. Application Factory
# ==============================================================================


def create_bot_application(
    token: str | None = None,
) -> Application[Any, Any, Any, Any, Any, Any]:
    """Builds and configures python-telegram-bot Application instance."""
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

    app = Application.builder().token(bot_token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, handle_document_or_photo)
    )

    return app
