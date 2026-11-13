# 06b. Medical Safety & Privacy Enforcement Rules

This document specifies the non-negotiable safety guardrails, clinical threshold overrides, local PII scrubbing algorithms, and statutory compliance rules governing **ReportSaathi**.

---

## 1. Core Safety Philosophy

> **"ReportSaathi explains, it does not diagnose. It empowers the doctor consultation, it never replaces the doctor."**

Every architectural and algorithmic choice in the system enforces this boundary:
1. **Deterministic Execution:** No safety rule or privacy filter is ever entrusted to a probabilistic Large Language Model.
2. **Directional Urgency:** Code can only **escalate** clinical urgency (e.g., from *Routine* to *Prompt Attention*), never downgrade it.
3. **Zero Storage of Personal Identifiers:** Original photos, raw unscrubbed OCR text, patient names, and addresses are completely barred from persistence.

---

## 2. Deterministic Critical Clinical Overrides

The Python function `apply_safety_overrides(parsed_rows, summary) -> ReportSummary` runs immediately after every Gemini response and upon every cache retrieval.

### Critical Thresholds Table
If any parsed biomarker matches a critical condition below, the system immediately forces:
* `urgency = "Prompt Attention"`
* Injects a prominent, non-AI warning urging the family to consult a physician today.

```python
CRITICAL_RULES = [
    # (test aliases, unit, operator, threshold, alert label)
    (
        ["hemoglobin", "haemoglobin", "hb"],
        "g/dL",
        "<",
        7.0,
        "Critically Low Hemoglobin (Severe Anemia)",
    ),
    (
        ["fasting glucose", "fbs", "fasting blood sugar", "fasting plasma glucose"],
        "mg/dL",
        ">",
        250,
        "Critically High Fasting Glucose",
    ),
    (
        ["random glucose", "rbs", "random blood sugar"],
        "mg/dL",
        ">",
        400,
        "Critically High Random Glucose",
    ),
    (
        ["glucose", "blood sugar"],
        "mg/dL",
        "<",
        50,
        "Critically Low Glucose (Severe Hypoglycemia)",
    ),
    (["potassium"], "mmol/L", ">", 6.0, "Critically High Potassium (Hyperkalemia)"),
    (["potassium"], "mmol/L", "<", 2.8, "Critically Low Potassium (Hypokalemia)"),
    (["sodium"], "mmol/L", "<", 120, "Critically Low Sodium (Severe Hyponatremia)"),
    (
        ["platelet", "platelets"],
        "/cumm",
        "<",
        20000,
        "Critically Low Platelets (Severe Thrombocytopenia)",
    ),
    (
        ["creatinine"],
        "mg/dL",
        ">",
        5.0,
        "Critically High Creatinine (Acute Kidney Injury Risk)",
    ),
    (["tsh"], "mIU/L", ">", 50, "Critically High TSH (Severe Hypothyroidism)"),
]
```

### Unit Normalization Algorithm
Before evaluating thresholds, all incoming values are normalized into standard clinical units:
* Glucose: Convert `mmol/L` to `mg/dL` by multiplying by $18.0$.
* Hemoglobin: Convert `g/L` to `g/dL` by dividing by $10.0$.
* Platelets: Convert `lakhs/cumm` (e.g., $1.5\text{ lakhs}$) to raw count ($150,000\text{ /cumm}$).

---

## 3. Local PII Scrubbing Rules (Pre-AI Execution)

Implemented in `backend/ocr_scrub.py`. Runs entirely in local memory before any data is passed to external APIs.

### Elements Redacted to `[REDACTED]`
* **Patient Identifiers:** Lines or tokens matched by prefixes: `Name`, `Patient`, `Patient Name`, `Mr.`, `Mrs.`, `Ms.`, `Smt.`, `Shri`, `S/o`, `D/o`, `W/o`, `C/o`.
* **Telephone Numbers:** All 10-digit Indian mobile numbers and STD landline formats: `(\+?91[\-\s]?)?[6-9]\d{9}`.
* **Email Addresses:** Standard RFC-5322 regex email patterns.
* **Addresses & Locations:** Lines containing `Address`, `Addr`, `Road`, `Street`, `Nagar`, `Layout`, and 6-digit Indian PIN codes: `\b\d{6}\b`.
* **Hospital & Lab Metadata:** Barcodes, accession numbers, and identifiers matched by `UHID`, `MRN`, `Lab No`, `Sample ID`, `Reg No`, `Bill No`, `Visit ID`.
* **Clinician Names & Signatures:** Lines containing `Dr.`, `Ref. by`, `Referred by`, `Consultant`, `Pathologist`, `Signature`.
* **Corporate & Accreditation Footers:** NABL, ISO, CAP logos, website URLs, and print timestamps.

### Elements Retained for Clinical Context
* **Patient Age:** Extracted into an integer variable (e.g., `age = 58`).
* **Biological Sex:** Extracted into a string variable (e.g., `biological_sex = "Female"`).
* **Biomarker Rows:** Test Name, Observed Numeric Value, Unit, Reference Range.

---

## 4. Invariant Fixed Legal Disclaimers

The following disclaimers are hard-coded in Python and appended automatically to every outgoing card. Gemini is strictly prohibited from writing, editing, translating, or omitting these disclaimers:

```python
DISCLAIMER = {
    "en": (
        "Personal details removed (best effort).\n"
        "This explains your report in simple words. It is not a diagnosis. "
        "Please show the report to your doctor."
    ),
    "hi": (
        "व्यक्तिगत जानकारी हटा दी गई है (सर्वोत्तम प्रयास)।\n"
        "यह आपकी रिपोर्ट को आसान शब्दों में समझाता है। यह कोई निदान नहीं है। "
        "कृपया रिपोर्ट अपने डॉक्टर को दिखाएं।"
    ),
    "kn": (
        "ವೈಯಕ್ತಿಕ ವಿವರಗಳನ್ನು ತೆಗೆದುಹಾಕಲಾಗಿದೆ (ಉತ್ತಮ ಪ್ರಯತ್ನ).\n"
        "ಇದು ನಿಮ್ಮ ವರದಿಯನ್ನು ಸರಳ ಪದಗಳಲ್ಲಿ ವಿವರಿಸುತ್ತದೆ. ಇದು ರೋಗನಿರ್ಣಯವಲ್ಲ. "
        "ದಯವಿಟ್ಟು ವರದಿಯನ್ನು ನಿಮ್ಮ ವೈದ್ಯರಿಗೆ ತೋರಿಸಿ."
    ),
}
```

---

## 5. Prohibited Output & Content Rules

The system prompt and output validation layer strictly enforce the following negative constraints:

1. **No Medication Changes:** The system shall never advise changing, discontinuing, or starting a medicine or altering a dosage.
2. **No Diagnostic Finality:** The system shall never state "You have Diabetes" or "You have Chronic Kidney Disease". It must frame findings as patterns: *"Your blood sugar levels are higher than standard lab ranges, which doctors check for diabetes."*
3. **No False Reassurance:** If a value is unreadable, blurry, or missing a reference range, the system must not assign `urgency = "Routine"`. It must assign at least `"Consult Soon"` and flag the unread value.
4. **No Cure Claims:** In compliance with the *Drugs and Magic Remedies Act, 1954*, the system must never state or imply that any medicine, diet, or home remedy can permanently cure hypertension, diabetes, or cardiovascular disease.

---

## 6. DPDP Act 2023 Compliance & Data Lifecycle

* **User Consent:** Onboarding requires explicit affirmative action (`[✅ I Agree]`). The user cannot interact with the service until this is registered.
* **Storage Minimization:** The database retains only: `telegram_chat_id`, optional `age`/`biological_sex`, and scrubbed JSON summaries. No patient names, images, or raw text are ever saved.
* **Automated Data Purge:**
  * When a user sends `/delete` or taps `[🗑️ Delete My Data]`, the backend triggers a PostgreSQL delete on the user's UUID.
  * Thanks to `ON DELETE CASCADE`, all linked reports, biomarker trends, and translation caches are permanently erased.
  * A confirmation message is returned to the user in their preferred language.
