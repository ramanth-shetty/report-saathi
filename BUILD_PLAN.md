# BUILD_PLAN.md: ReportSaathi Execution Checklist

Feed Antigravity ONE slice at a time. Finish and test each slice before starting the next.
Start every session with: _"Read GEMINI.md and the rules in .agents/rules/. Edit only the files named in this slice."_

---

## Slice 0: Setup (before coding)

- [ ] Create the GitHub repo `reportsaathi` and open it in Antigravity.
- [ ] Add `GEMINI.md`, `BUILD_PLAN.md` and `.agents/rules/*.md`. Add `.env` to `.gitignore`.
- [ ] Create `backend/` and run `python -m venv venv`, then activate it.
- [ ] `backend/requirements.txt`: `fastapi uvicorn[standard] python-telegram-bot==21.* google-genai pydantic pytesseract opencv-python-headless pillow numpy pymupdf supabase python-dotenv pytest python-multipart`
- [ ] `pip install -r backend/requirements.txt`
- [ ] Create a Telegram bot with @BotFather, then copy the token into `.env`.
- [ ] Create a Supabase project, run the DDL from rule 03, then copy the URL and service key into `.env`.
- [ ] Put 3 to 5 dummy or consented sample reports in `backend/tests/samples/`.

---

## Slice 1: `backend/ocr_scrub.py` + local test

**Prompt:**

> Read GEMINI.md and .agents/rules/01-ocr-and-privacy.md. Create `backend/ocr_scrub.py` with `preprocess`, `ocr_rows`, `parse_rows`, `scrub_pii`, `extract_age_sex`, and the `DISCLAIMER` constants. Add a `__main__` block that takes an image path and prints the cleaned rows and the OCR confidence. Add `backend/tests/test_scrub.py` with fake PII. Edit only these files.

**Done when:**

- [ ] `python backend/ocr_scrub.py backend/tests/samples/sample1.jpg` prints one row per test line with columns together.
- [ ] `pytest backend/tests/test_scrub.py` passes (no fake name, phone, email or ID survives).
- [ ] Age and sex are kept. A blurry photo returns `low_quality=True`.

---

## Slice 2: `backend/gemini_analyzer.py` (structured JSON + critical thresholds)

**Prompt:**

> Read GEMINI.md and .agents/rules/02-gemini-and-safety.md. Create `backend/gemini_analyzer.py` with the Pydantic `ReportSummary` schema, `analyze(rows, age, sex, deltas, lang="en")`, `translate(summary_en_json, lang)`, `compute_hash(rows)`, and `apply_safety_overrides`. Use `google-genai` with `gemini-2.5-flash` and `response_schema`. Add a `__main__` block that runs on the output of Slice 1. Add `tests/test_safety.py`. Edit only these files.

**Done when:**

- [ ] The CLI prints valid JSON with exactly 3 `doctor_questions` and a single `normal_summary` line.
- [ ] A test row with Hemoglobin 6.5 g/dL forces `urgency = "Prompt Attention"` even if the mocked LLM says "Routine".
- [ ] A test with fasting glucose 280 mg/dL also forces `"Prompt Attention"`.
- [ ] `translate(..., "kn")` and `translate(..., "hi")` give simple, forwardable text.

---

## Slice 3: `backend/database.py` (Supabase + hash caching + trend query)

**Prompt:**

> Read GEMINI.md and .agents/rules/03-database-and-telegram.md. Create `backend/database.py` with all functions listed in section 2 using the `supabase` Python client and env vars. Add a `__main__` smoke test using a fake chat id: create a user, save a report, hit the cache by hash, save a translation, compute deltas, then delete the user. Edit only this file.

**Done when:**

- [ ] The smoke test passes against your real Supabase project.
- [ ] Saving the same report twice returns the cached row (no duplicate).
- [ ] `delete_user_data` removes the user's reports and biomarkers (verify in the Supabase table view).

---

## Slice 4: `backend/bot.py` (Telegram bot, Kannada and Hindi buttons, `/delete`)

**Prompt:**

> Read GEMINI.md and .agents/rules/03-database-and-telegram.md. Create `backend/bot.py` using python-telegram-bot v21 (async). Implement `/start` with consent, photo and PDF handling, the "Analyzing..." message, the full summary format, the inline keyboard (हिंदी, ಕನ್ನಡ, Trends, Delete My Data), cache-first translation, `/delete` with confirmation, and friendly errors. Wire together the modules from Slices 1 to 3. Run in polling mode when executed directly. Edit only this file.

**Done when:**

- [ ] Sending a sample photo from your phone returns a summary in under about 30 seconds.
- [ ] Tapping ಕನ್ನಡ twice makes only **one** Gemini call (check the logs).
- [ ] Sending the same photo again returns instantly from cache.
- [ ] `/delete` wipes your data and confirms.
- [ ] The disclaimer and the "Personal details removed (best effort)" line appear on every summary.
- [ ] **Demo checkpoint:** show this to 5 real people and note what confuses them.

---

## Slice 5: `backend/main.py` + minimal `frontend/`

**Prompt (backend):**

> Read GEMINI.md. Create `backend/main.py` (FastAPI) with `GET /health`, `POST /telegram/webhook/{secret}` that feeds updates into the bot application, and `POST /api/analyze` that accepts an image or PDF upload and returns the summary JSON (same pipeline, no storage unless a user id is given). Configure CORS for the Cloudflare Pages domain via an env var. Edit only this file.

**Prompt (frontend):**

> Create a minimal `frontend/` (Vite + vanilla JS): one page with a file upload, a language selector (English, हिंदी, ಕನ್ನಡ), an "Analyzing..." state, result cards (urgency badge, abnormal markers, patterns, 3 doctor questions), a "Personal details removed (best effort)" indicator and the fixed disclaimer. Read the backend URL from `VITE_API_URL`. Edit only files in `frontend/`.

**Done when:**

- [ ] `uvicorn backend.main:app --reload` serves `/health` and `/api/analyze` locally.
- [ ] The web page uploads a report and renders the result.

---

## Deploy

- [ ] Push to GitHub.
- [ ] **Render**: new Web Service from the repo. Build command `pip install -r backend/requirements.txt`. Start command `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`. Add all env vars.
- [ ] Render does not ship Tesseract by default. Add a `Dockerfile` that installs `tesseract-ocr`, `tesseract-ocr-hin` and `tesseract-ocr-kan`, or use a Docker-based Render service.
- [ ] Set the Telegram webhook: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<RENDER_URL>/telegram/webhook/<SECRET>`.
- [ ] **Cloudflare Pages**: connect the repo, root directory `frontend`, build command `npm run build`, output `dist`, env var `VITE_API_URL`.
- [ ] End-to-end test from your phone on the live bot.

---

## If Antigravity hits its free limit

Switch to Gemini CLI in the repo root (`gemini`). It reads `GEMINI.md` automatically. Paste the same slice prompt.
