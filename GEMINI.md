# GEMINI.md: ReportSaathi Project Blueprint

## Goal

ReportSaathi is a **Family Health Translator** for the waiting gap between getting a lab report and seeing a doctor.
A tech-savvy family member snaps or uploads a photo or PDF of an older relative's lab report on **Telegram**.
ReportSaathi then:

1. Scrubs personal identity details locally (best effort) before any external API call.
2. Extracts lab values with OCR.
3. Checks past trends for the same user.
4. Returns a calm, jargon-free summary in **English, Hindi or Kannada**, plus **exactly 3 questions to ask the doctor**.

The summary is written so a grandson can forward it straight to a grandmother.
It **explains, it does not diagnose**.

## Locked Tech Stack (do NOT suggest alternatives)

| Layer                  | Technology                                                                                  |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| Frontend               | Node.js (Vite + vanilla JS or React) on **Cloudflare Pages**                                |
| Chat interface         | **Telegram Bot** via `python-telegram-bot` (v21+, async, webhook mode on Render)            |
| Backend API and worker | **Python 3.11+**, **FastAPI**, hosted on **Render** (free tier)                             |
| OCR                    | **Tesseract** via `pytesseract` + `opencv-python-headless` + `Pillow`                       |
| PDF to image           | `PyMuPDF` (pure pip, no system dependencies)                                                |
| AI                     | **Google Gemini API**, `google-genai` SDK, model `gemini-2.5-flash`, Structured JSON output |
| Database               | **Supabase** (PostgreSQL), `supabase` Python client                                         |
| Dev tools              | Git + GitHub, Google Antigravity IDE, Gemini CLI                                            |

## Folder Structure

```
reportsaathi/
├── GEMINI.md
├── BUILD_PLAN.md
├── .env                  # never commit
├── .env.example
├── .gitignore            # must include .env, __pycache__/, venv/, node_modules/
├── .agents/
│   └── rules/
│       ├── 01-ocr-and-privacy.md
│       ├── 02-gemini-and-safety.md
│       └── 03-database-and-telegram.md
├── backend/
│   ├── requirements.txt
│   ├── ocr_scrub.py      # Slice 1
│   ├── gemini_analyzer.py# Slice 2
│   ├── database.py       # Slice 3
│   ├── bot.py            # Slice 4
│   ├── main.py           # Slice 5
│   └── tests/
│       └── samples/      # dummy or consented sample reports only
└── frontend/
    ├── index.html
    ├── main.js
    └── package.json
```

## Environment Variables (`.env`)

```
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
WEBHOOK_BASE_URL=          # Render URL, used in production only
TESSERACT_CMD=             # Windows only, e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Core Data Flow

1. User sends photo or PDF to the Telegram bot (or uploads on the web page).
2. `ocr_scrub.py`: preprocess, OCR into rows, then scrub PII.
3. `database.py`: SHA-256 hash of the scrubbed text. On a cache hit, return the stored JSON with **0 Gemini calls**.
4. `database.py`: fetch the user's past values for the detected tests, then compute deltas.
5. `gemini_analyzer.py`: send ONLY scrubbed biomarker lines + deltas, with a strict JSON schema.
6. Python applies critical-value overrides and appends the fixed disclaimer.
7. Save to Supabase, then reply on Telegram with inline buttons.

## Global Working Rules

- Edit **targeted functions or files only**. Never regenerate the whole repo.
- Build one slice at a time from `BUILD_PLAN.md`. Each slice must run locally before the next starts.
- Secrets live only in `.env`. Never hard-code or print keys.
- Never log raw OCR text, unscrubbed text or patient identifiers.
- Python: type hints, small functions, `logging` (no `print` in production paths).
- Every user-facing string is English, Hindi or Kannada. The disclaimer is hard-coded in all three.
- Do not add dependencies outside the locked stack without asking.
