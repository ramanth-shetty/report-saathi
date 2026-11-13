---
trigger: always_on
---

# Rule 03: Database and Telegram

Applies to `backend/database.py`, `backend/bot.py` and `backend/main.py`.

## 1. Supabase PostgreSQL DDL

Run in the Supabase SQL editor. The backend uses the **service role key**, server-side only.

```sql
create extension if not exists "pgcrypto";

create table users (
  id uuid primary key default gen_random_uuid(),
  telegram_chat_id bigint unique,
  email text unique,
  age int,
  biological_sex text,
  preferred_lang text default 'en' check (preferred_lang in ('en','hi','kn')),
  consent_at timestamptz,
  created_at timestamptz default now()
);

create table reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  report_hash text not null,
  report_date date default current_date,
  urgency_level text check (urgency_level in ('Routine', 'Consult Soon', 'Prompt Attention')),
  summary_en jsonb not null,
  summary_hi jsonb,
  summary_kn jsonb,
  created_at timestamptz default now(),
  unique (user_id, report_hash)
);

create table biomarkers (
  id uuid primary key default gen_random_uuid(),
  report_id uuid references reports(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  test_name text not null,
  observed_value numeric,
  unit text,
  ref_range text,
  status text check (status in ('Normal', 'Low', 'High', 'Borderline')),
  recorded_at date default current_date
);

create index idx_reports_user_hash on reports (user_id, report_hash);
create index idx_biomarkers_user_test on biomarkers (user_id, lower(test_name), recorded_at desc);

alter table users enable row level security;
alter table reports enable row level security;
alter table biomarkers enable row level security;
-- No public policies: only the backend (service role) reads or writes.
```

## 2. `database.py` Functions

- `get_or_create_user(chat_id) -> dict`
- `set_consent(chat_id)`, `set_language(chat_id, lang)`
- `find_report_by_hash(user_id, report_hash) -> dict | None`
- `save_report(user_id, report_hash, summary_en, urgency, biomarker_rows) -> report_id`
- `save_translation(report_id, lang, summary_json)` and `get_translation(report_id, lang)`
- `get_history(user_id, test_names) -> dict[test_name, list[(date, value, unit)]]` (the latest 3 values per test, used for deltas and trends)
- `compute_deltas(current_rows, history) -> list[str]` such as `"HbA1c: 7.4% -> 6.8% (improved)"`. Match tests on normalised lowercase names.
- `delete_user_data(chat_id)` deletes the `users` row, and cascade removes everything else. Return True on success.

Rules: parameterised calls only through the Supabase client, no raw string SQL. Handle "not found" gracefully. Never log row contents.

## 3. Telegram Bot Workflow (`python-telegram-bot`, async)

1. `/start`: greeting, language choice, consent button `[✅ I agree]`. No processing before consent.
2. User sends a **photo or PDF** (`filters.PHOTO | filters.Document.PDF`).
3. Bot immediately replies **"Analyzing... ⏳"** (edit this message with the result later).
4. Download the file into memory, then run `ocr_scrub` → hash → cache check → Gemini (only on a cache miss) → safety overrides → save.
5. Delete the "Analyzing..." message or edit it into the final summary containing:
   - Urgency badge: 🟢 Routine / 🟡 Consult Soon / 🔴 Prompt Attention (localised label)
   - `normal_summary` (one line)
   - Abnormal markers, each with a 1 to 2 sentence explanation and a trend note
   - Cross-marker patterns
   - Suggested specialist
   - The **3 questions for the doctor**
   - `🔒 Personal details removed (best effort)`
   - The fixed `DISCLAIMER` for the active language
6. Attach this inline keyboard:

```python
[
    [
        InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang:hi"),
        InlineKeyboardButton("🇮🇳 ಕನ್ನಡ", callback_data="lang:kn"),
    ],
    [InlineKeyboardButton("📈 Trends", callback_data="trends")],
    [InlineKeyboardButton("🗑️ Delete My Data", callback_data="delete")],
]
```

Include the report id in `callback_data` (e.g. `lang:hi:<report_id>`) so the buttons act on the right report. Keep it under 64 bytes.

7. **Language buttons**: check `summary_hi` or `summary_kn` in the DB first. If it is `NULL`, call Gemini once, save it, then send. Add an `[🇬🇧 English]` button on the translated message. The message must be easy to forward.
8. **Trends button**: query `get_history`, then send a short text trend list (and a simple chart image only if time allows). If there is no history, say "Upload your next report to see trends."
9. **Delete button and `/delete`**: confirm with `[Yes, delete]` / `[Cancel]`, then call `delete_user_data`, then confirm in the user's language.
10. Errors: unreadable photo, low OCR quality, or Gemini failure each produce a friendly message asking for a clearer photo or a retry. The bot never shows stack traces.
11. Only one report is processed per user at a time. Ignore duplicate submissions while one is in progress.

## 4. Deployment Notes

- Production uses **webhook mode**: FastAPI route `POST /telegram/webhook/{secret}` passes updates to the bot application. Local development uses polling.
- Render free tier sleeps when idle. Expose `GET /health` for pings.
- Frontend (Cloudflare Pages) calls `POST /api/analyze` on the Render backend. Enable CORS only for the Pages domain.
