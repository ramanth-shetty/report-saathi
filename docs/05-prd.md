# 05. Product Requirements Document (PRD): ReportSaathi

## 1. Product Overview

**ReportSaathi** is a family-oriented, privacy-first Health and Medicine Explainer. It bridges the critical "waiting gap" between receiving a diagnostic lab report or long-term chronic prescription and meeting a physician. By translating technical medical jargon and complex blister-pack text into calm, plain-language vernacular cards (English, Hindi, Kannada), vernacular audio notes, and **exactly 3 questions to ask the doctor**, ReportSaathi eliminates post-consultation confusion without diagnosing or replacing the clinician.

---

## 2. Goals & Non-Goals

### A. Goals
1. **Bridge Post-Consultation Comprehension:** Enable adults over 40 (and their family caregivers) to understand what their prescribed medicines do, how to take them safely, and what normal vs. red-flag symptoms mean.
2. **Zero-App, Zero-Typing Accessibility:** Deliver 100% of the core experience over ubiquitous messaging channels (WhatsApp / Telegram) and a lightweight web page, operating via camera snaps (blister packs, printed prescriptions, or lab PDFs).
3. **Local Privacy by Design:** Scrub all Personal Identifiable Information (PII) locally *before* any cloud or AI API call, complying strictly with India’s Digital Personal Data Protection Act, 2023 (DPDP Act).
4. **Physician Empowerment:** Supply the patient with exactly 3 structured, non-alarmist questions to maximize the value of their next 5-minute doctor consultation.
5. **Deterministic Clinical Guardrails:** Hard-code clinical critical thresholds in Python so acute values (e.g., severe hypoglycemia, extreme anemia) immediately force medical attention, regardless of AI output.

### B. Non-Goals
1. **No Medical Diagnosis:** The system will never declare "You have disease X" or provide differential diagnosis. It explains mechanisms and patterns only.
2. **No Prescription Modification or Dosage Advice:** The system will never recommend starting, adjusting, or discontinuing any prescription medicine.
3. **No Emergency Triage Replacement:** ReportSaathi is not an acute emergency response tool; severe trauma, active cardiac arrest, or acute stroke symptoms trigger immediate emergency helpline referral.
4. **No Raw Image / Unscrubbed Data Persistence:** The system will never store original photos, unredacted OCR text, or patient names on disk or in the database.
5. **No Commercial E-Pharmacy Affiliation:** The product will not push generic brand substitutes, cross-sell nutritional supplements, or earn affiliate fees from medicine carts.

---

## 3. User Personas & User Stories

### Persona Profiles
* **Persona 1: The Remote Digital Caregiver (Rohan, 29, Bangalore):** Tech-savvy software engineer whose 62-year-old mother in Hubli was prescribed two new blood pressure medications. He needs a simple, trustworthy vernacular explanation he can forward straight to her on WhatsApp.
* **Persona 2: The Chronic Disease Patient (Kamala, 58, Belagavi):** Diagnosed with hypertension and Type-2 diabetes. Leaves the government hospital OPD with a handwritten prescription and blister strips. Struggles to read tiny English print and needs spoken Kannada explanations.
* **Persona 3: The Outpatient Physician (Dr. Suresh, 48, General Physician):** Overwhelmed with 60 patients per morning OPD. Desires patients who bring structured, relevant questions rather than vague internet panic.

### User Stories
* **US-1 (Caregiver Capture):** As a family caregiver, I want to snap a photo of my parent's medicine strip or upload a lab PDF, so that I can immediately receive an easy-to-read explanation without typing complex chemical names.
* **US-2 (Elder Audio Consumption):** As an older patient with presbyopia, I want to tap a single button to hear a 35-second voice note in Kannada or Hindi, so that I don't have to strain my eyes reading small text.
* **US-3 (Doctor Consultation Preparation):** As a chronic patient, I want 3 specific questions written out for my next clinic visit, so that I don't forget what to ask my doctor.
* **US-4 (DPDP Data Control):** As a privacy-conscious user, I want the ability to permanently erase all my historical reports and data by typing `/delete` or tapping a button, so that my health data is completely purged.

---

## 4. Numbered Functional Requirements

### Epic 1: Onboarding & Privacy Consent
* **FR-1.1 (First-Contact Gate):** On first interaction via `/start` or web landing, the system must display a concise consent notice stating that details are scrubbed locally, the service explains rather than diagnoses, and data can be erased anytime.
* **FR-1.2 (Affirmative Consent):** The system must block report processing until the user taps `[✅ I Agree]`. The consent timestamp (`consent_at`) must be recorded in the database.
* **FR-1.3 (Language Preference):** The user must be able to select their preferred response language (English, Hindi, or Kannada) during onboarding and toggle it at any time.

### Epic 2: Multimodal Input & Preprocessing
* **FR-2.1 (Supported File Formats):** The system must accept camera photos (`image/jpeg`, `image/png`) and multi-page digital PDFs (`application/pdf`) up to 10MB.
* **FR-2.2 (Image Optimization):** The backend must automatically upscale images below 1500px, convert to grayscale, apply adaptive thresholding, and deskew text before OCR.
* **FR-2.3 (PDF Conversion):** Multi-page PDFs must be converted into 300 DPI raster images using pure Python bindings (`PyMuPDF`) without external system binaries.
* **FR-2.4 (Quality Gate):** If the average OCR confidence score is below 55%, the system must halt analysis and return a friendly prompt requesting a flat, well-lit retake.

### Epic 3: Local Privacy Scrubbing & Hashing
* **FR-3.1 (Deterministic PII Scrubbing):** The local Python pipeline must remove or redact (`[REDACTED]`) patient names, doctor names, phone numbers, emails, clinic/hospital names, accession/barcode numbers, and dates.
* **FR-3.2 (Demographic Extraction):** The system must extract only Age and Biological Sex into isolated prompt variables for clinical context.
* **FR-3.3 (Memory Purge):** The original image buffer and unscrubbed raw text must be deleted from application memory immediately following scrubbing.
* **FR-3.4 (Deduplication Hashing):** The system must compute a SHA-256 hash of the scrubbed biomarker lines. If an identical hash exists for the user, return cached results with zero AI API calls.

### Epic 4: Analysis & Safety Overrides
* **FR-4.1 (Biomarker & Drug Extraction):** The system must group visual table rows into `{test_name, observed_value, unit, ref_range}` or map medicine packaging to active molecules and Fixed-Dose Combinations (FDCs).
* **FR-4.2 (Structured AI Analysis):** When calling the Gemini API, the output must be strictly constrained to the `ReportSummary` Pydantic schema: `normal_summary`, `abnormal` list, `cross_marker_patterns`, `urgency`, `specialist`, and exactly 3 `doctor_questions`.
* **FR-4.3 (Deterministic Safety Overrides):** Python code must inspect parsed values against a hard-coded `CRITICAL_RULES` table. Any critical value (e.g., Fasting Glucose $> 250\text{ mg/dL}$, Hemoglobin $< 7.0\text{ g/dL}$) must force `urgency = "Prompt Attention"` and append an immediate clinical consultation directive.
* **FR-4.4 (Static Disclaimer Injection):** The system must append the fixed, hard-coded trilingual disclaimer to every generated summary. The AI model must never be tasked with generating or translating the disclaimer.

### Epic 5: Delivery, Vernacular Translation & Trends
* **FR-5.1 (Instant Translation Caching):** Summary translations for Hindi (`summary_hi`) and Kannada (`summary_kn`) must be generated from the structured English JSON and saved to the database. Re-tapping a language button must read from cache with zero API calls.
* **FR-5.2 (Audio Note Generation):** The system must deliver a 30–45 second spoken vernacular voice note summarizing the medicine/report in simple spoken register (आप-form for Hindi; ನೀವು-form for Kannada).
* **FR-5.3 (Historical Delta Tracking):** When previous reports exist for the user, the system must compute deltas on matching biomarkers (e.g., *"HbA1c: 7.4% -> 6.8% (improved)"*) and include them in the explanation.
* **FR-5.4 (Complete Data Erasure):** Executing `/delete` or tapping `[🗑️ Delete My Data]` must perform a hard database delete (`ON DELETE CASCADE`) of the user, their reports, translations, and biomarkers, followed by a confirmation message.

---

## 5. Non-Functional Requirements (NFRs)

* **NFR-1 (End-to-End Latency):** From image upload to delivery of the plain-language card, total latency must not exceed **25 seconds** on a standard 4G connection. Cached queries must return in **$< 1.5$ seconds**.
* **NFR-2 (Low-End Device Compatibility):** The web frontend must render seamlessly on low-cost Android smartphones (e.g., Android 11 Go Edition, 2GB RAM, 360dp viewport width) without layout breaking or UI stutter.
* **NFR-3 (Indic Font Rendering):** Kannada and Devanagari scripts must render with line-height $\ge 1.65\times$ to prevent clipping of vowel modifiers (*matras*) and conjuncts (*vattus*).
* **NFR-4 (Zero Data Leakage):** Under no circumstance shall unredacted PII or medical images be written to disk logs, database tables, or third-party monitoring services.
* **NFR-5 (High Availability on Free Tier):** The backend must handle cold starts gracefully on Render free tier, with automated pinging and friendly waiting states.
* **NFR-6 (Accessibility Contrast):** All text elements must achieve a minimum contrast ratio of **7:1 (WCAG AAA)** against their backgrounds.

---

## 6. Safety & Regulatory Requirements

* **SR-1 (Telemedicine Compliance):** In accordance with the *Telemedicine Practice Guidelines (2020)*, the software is explicitly designated as **Public Health Education** and Clinical Decision Support; it is legally barred from offering standalone medical diagnosis or issuing prescriptions.
* **SR-2 (Magic Remedies Act):** In accordance with the *Drugs and Magic Remedies (Objectionable Advertisements) Act (1954)*, the product shall never claim to cure, prevent, or reverse chronic conditions like diabetes, cardiovascular diseases, or hypertension.
* **SR-3 (DPDP Act 2023):** User consent must be verifiable, purpose-limited, and revocable on demand via an automated, zero-barrier `/delete` command.
* **SR-4 (Strict Non-Hallucination):** Unparsed or blurry values must default to `urgency = "Consult Soon"` and explicitly state that parts of the report were unreadable, rather than assuming normal status.

---

## 7. Success Metrics & Validation Targets

| Metric Category | Target | Measurement Method |
| :--- | :--- | :--- |
| **Comprehension Utility** | $\ge 85\%$ positive rating | Exit question: *"Did this help you understand what to ask your doctor?"* |
| **Cache Hit Ratio** | $\ge 40\%$ across 30 days | Database query: `cached_hits / total_requests` |
| **LLM Call Reduction** | $< 1.2$ Gemini calls / report | Monitored via API request telemetry |
| **OCR Failure Rate** | $< 8\%$ re-take requests | Log count of `low_quality=True` events |
| **DPDP Erasure SLA** | $100\%$ deleted within 3 seconds | Automated database trigger execution verification |
| **Doctor Question Relevance** | $\ge 80\%$ clinical approval | Blind clinical audit of generated doctor questions |
