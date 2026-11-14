# Architectural Decision Records (ADRs) - ReportSaathi

This document records architectural, technical, and operational decisions taken throughout the project lifecycle, in accordance with `docs/AGENTS.md`.

---

## ADR 001: Repository Directory Structure & Shared Contract Domain

* **Date:** 2026-11-13
* **Status:** Accepted
* **Context:**
  The project requires a strict separation of concerns between the Indic web frontend, the FastAPI/Python OCR and AI backend, and shared contract definitions.
* **Decision:**
  - Standardized repository layout into `frontend/`, `backend/`, `shared/`, `docs/`, and `tests/`.
  - Established `shared/` as the single source of truth for both TypeScript interfaces (`shared/types.ts`) and Python constants (`shared/constants.py`).
  - Strict rule: Neither frontend nor backend should unilaterally alter schema names or API boundaries without updating `docs/06a-api-contract.md` and `shared/` concurrently.

---

## ADR 002: Dual Health Check Strategy (`/health` & `/api/health`)

* **Date:** 2026-11-13
* **Status:** Accepted
* **Context:**
  Uptime monitoring probes (Render, Cloudflare, status monitors) require a lightweight, zero-dependency `GET /health` endpoint that returns 200 OK without failing during database cold starts. Conversely, the frontend web client and walking skeleton integration test require verification that the backend can actually read from the database.
* **Decision:**
  - `GET /health`: Minimal probe returning `{"status": "healthy", "service": "ReportSaathi", "version": "1.0.0"}` without external network hops.
  - `GET /api/health`: Extended probe that executes a lightweight query against Supabase PostgreSQL and returns `database.status` ("connected", "disconnected", or "error") along with `database.value` (e.g., table row count / status metadata).
  - The API does not crash or throw 500 when database credentials are not yet configured; instead, it reports `status: "disconnected"` so the user receives actionable instructions on what secrets need to be added.

---

## ADR 003: Staging Deployment Topology

* **Date:** 2026-11-13
* **Status:** Accepted
* **Context:**
  Need zero-cost, reproducible staging environments with automated CI testing for both frontend and backend.
* **Decision:**
  - **Backend:** Render Web Service (Free Tier, Python 3.11 runtime) configured via root `render.yaml` with health check at `/health`. Dockerfile provided for container parity.
  - **Frontend:** Cloudflare Pages (Free Tier) configured via `frontend/wrangler.toml` pointing to `dist/` with `VITE_API_URL` targeting the deployed Render backend.
  - **CI:** GitHub Actions (`.github/workflows/ci.yml`) enforcing Ruff linting and formatting, MyPy strict typing, Pytest smoke tests, ESLint, TypeScript compiler checks, and Vitest frontend smoke tests on all pull requests and pushes.


---

## ADR 004: Supabase PostgreSQL Schema, Cascade Deletion & Row Level Security

* **Date:** 2026-11-14
* **Status:** Accepted
* **Context:**
  The ReportSaathi architecture mandates zero persistence of raw images and unscrubbed PII. Under India's Digital Personal Data Protection (DPDP) Act 2023, users retain the unconditional right to erasure (`/delete`). In addition, anonymous public API access to health tables must be structurally prevented.
* **Decision:**
  - **DDL Implementation:** Schema created at `supabase/schema.sql` defining `users`, `reports`, and `biomarkers` tables.
  - **Foreign Key Cascades:** `reports.user_id` and `biomarkers.user_id` reference `users(id) ON DELETE CASCADE`. `biomarkers.report_id` references `reports(id) ON DELETE CASCADE`. Executing `DELETE FROM users WHERE id = ...` guarantees 100% hard cascade deletion of all user records without orphaned data.
  - **Deduplication & Trend Indexes:** `idx_reports_user_hash` on `(user_id, report_hash)` enables $O(1)$ report deduplication lookups. `idx_biomarkers_user_test` on `(user_id, lower(test_name), recorded_at desc)` enables fast case-insensitive biomarker trend queries.
  - **Row Level Security (RLS):** Enabled on `users`, `reports`, and `biomarkers` without public policies. Direct client/browser access is completely blocked (default-deny); only the backend server possessing the Supabase `service_role` key can read or mutate database records.

---

## ADR 005: Local In-Memory Preprocessing, Row-Aware OCR & Deterministic PII Scrubbing

* **Date:** 2026-11-14
* **Status:** Accepted
* **Context:**
  Medical lab reports uploaded via Telegram or Web contain sensitive personal identifiers (patient names, phone numbers, hospital UHIDs, MRNs, residential addresses, and physician details). Under India's Digital Personal Data Protection (DPDP) Act 2023, personal data must be safeguarded. Sensitive personal identifiers must be scrubbed locally on-device / in-memory *before* any external LLM API (Google Gemini) receives the payload. Furthermore, raw images and unscrubbed OCR text must never touch persistent storage (disk or database).
* **Decision:**
  - **OpenCV In-Memory Preprocessing:** Implemented `preprocess(image_bytes)` performing 2x cubic upscaling for images under 1500px, grayscale conversion, Gaussian adaptive thresholding, and deskew correction via text pixel moments (`minAreaRect`).
  - **PyMuPDF In-Memory Rasterization:** Implemented `rasterize_pdf(pdf_bytes, dpi=300)` rendering digital and scanned multi-page PDFs to in-memory PNG byte buffers without writing temporary files to disk.
  - **Row-Aware Bounding Box OCR:** Implemented `ocr_rows()` utilizing Tesseract with `--psm 6` via `image_to_data(output_type=Output.DICT)`. Groups words based on vertical center coordinates ($y_c$) using dynamic vertical gap thresholds ($0.6 \times \text{median\_word\_height}$) and sorts horizontally by `left` coordinates to preserve column alignment (Test Name, Observed Value, Unit, Reference Range).
  - **OCR Quality Gate:** Computes average word recognition confidence across the document. If average confidence $< 55.0$, signals `low_quality = True` to prompt the user for a clearer image rather than feeding corrupted tokens to downstream LLM analyzers.
  - **Deterministic Local PII Scrubber:** Implemented `scrub_pii()` using multi-stage regex filtering for Indian phone numbers (`+91`, 10-digit mobile), emails, street addresses, postal pincodes, medical record identifiers (UHID, MRN, Sample ID, Barcode, Accession), doctor credentials/names, and accreditation footers (NABL, ISO, CAP).
  - **Clinical Demographics Preservation:** Implemented `extract_age_sex()` to extract and isolate patient age and biological sex into standalone variables for clinical reference while removing personal patient names.
  - **Immutable Trilingual Disclaimer:** Enforced constant disclaimers in English, Hindi, and Kannada (`DISCLAIMER`) hard-coded into Python constants (`shared/constants.py`) and appended deterministically to summaries, ensuring AI models are never tasked with synthesizing or modifying medical legal disclaimers.

---

## ADR 006: Deterministic Critical Overrides, Directional Urgency & Structured Gemini Analyzer

* **Date:** 2026-11-14
* **Status:** Accepted
* **Context:**
  Critical medical lab values (e.g., Hemoglobin $< 7.0\text{ g/dL}$, Fasting Glucose $> 250\text{ mg/dL}$, Platelet Count $< 20,000\text{ /\mu L}$) indicate acute physiological risks demanding immediate clinical escalation. Entrusting safety-critical decisions to a probabilistic LLM introduces unacceptable clinical risk. Furthermore, malicious actors or adversarial report notes could attempt prompt injections commanding diagnostic declarations (e.g. terminal cancer) or altering prescription dosages.
* **Decision:**
  - **Strict Pydantic Contracts:** Defined `ReportSummary` and `AbnormalMarker` in `backend/gemini_analyzer.py` enforcing strict validation, type safety, and exactly 3 actionable questions for the physician.
  - **Deterministic Rule Table (`CRITICAL_RULES`):** Compiled standard laboratory panic values in Python. Evaluated deterministically in code on all parsed biomarker rows, bypassing model hallucinations.
  - **Unit Normalization Engine:** Standardized units prior to threshold comparison (Glucose `mmol/L` $\to$ `mg/dL` $\times 18.0$, Hemoglobin `g/L` $\to$ `g/dL` $\div 10.0$, Platelets `lakhs/cumm` or `k/\mu L` $\to$ `/cumm`).
  - **Directional Urgency Invariant:** Enforced monotonic urgency rank escalation (`Routine` $1 \to$ `Consult Soon` $2 \to$ `Prompt Attention` $3$). Urgency can only escalate, never downgrade.
  - **Negative Guardrail Sanitization:** Implemented `sanitize_adversarial_output()` to intercept and neutralize adversarial attempts to issue definitive cancer diagnoses or tamper with drug dosages.
  - **Immutable Legal Disclaimers:** Trilingual disclaimers (`en`, `hi`, `kn`) are injected via Python application constants and appended to all summaries, completely insulated from AI modification.

---

## ADR 007: SHA-256 Report Deduplication Caching, Longitudinal Deltas & DPDP Cascading Erasure

* **Date:** 2026-11-14
* **Status:** Accepted
* **Context:**
  Redundant uploads of identical lab reports cause unnecessary network latency and LLM cost. The system architecture targets $\ge 40\%$ cache hit ratio with zero LLM calls on re-uploads. In addition, tracking chronic illnesses (e.g. diabetes, anemia) requires comparing current lab values against previous records for the same user. Finally, statutory compliance with India's DPDP Act 2023 requires atomic, unconditional erasure upon `/delete`.
* **Decision:**
  - **Deterministic SHA-256 Hashing:** Implemented `compute_report_hash(scrubbed_lines)` in `backend/database.py` calculating a cryptographic SHA-256 digest over normalized, scrubbed text rows.
  - **Cache-First Query Pipeline:** Implemented `find_report_by_hash(user_id, report_hash)` leveraging the compound index `(user_id, report_hash)`. Repeated uploads return stored JSON summaries with exactly 0 Gemini API calls.
  - **On-Demand Indic Translation Caching:** Implemented `save_translation()` and `get_translation()` saving `summary_hi` and `summary_kn` on demand, ensuring translation requests are synthesized at most once per language.
  - **Longitudinal Trend Delta Engine:** Implemented `compute_deltas(current_rows, history)` pairing current biomarker values with the latest previous recorded reading, generating clear clinical comparison strings (e.g. `"HbA1c: 8.4% -> 7.8% (improved)"`).
  - **DPDP Cascade Erasure:** Implemented `delete_user_data(chat_id)` executing a single delete against the `users` table, which automatically purges linked rows in `reports` and `biomarkers` via PostgreSQL `ON DELETE CASCADE`.
