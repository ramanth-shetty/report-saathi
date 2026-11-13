---
trigger: always_on
---

# Rule 02: Gemini and Medical Safety

Applies to `backend/gemini_analyzer.py` and anything that calls the Gemini API.

## 1. SDK and Model

- Use `from google import genai` and `from google.genai import types`.
- Model: `gemini-2.5-flash` only.
- Structured output via `types.GenerateContentConfig(response_mime_type="application/json", response_schema=ReportSummary, temperature=0.2)`.
- Parse the response with `ReportSummary.model_validate_json(response.text)`. On a validation error, retry **once**. If it still fails, return a safe fallback message ("Could not analyse this report. Please show it to your doctor.").

## 2. Strict Pydantic Schema

```python
from typing import Literal
from pydantic import BaseModel, Field


class AbnormalMarker(BaseModel):
    test: str
    value: str  # value + unit as printed, e.g. "9.1 g/dL"
    status: Literal["Low", "High", "Borderline"]
    explanation: str = Field(description="1-2 plain sentences, no jargon, max 40 words")
    trend_note: str | None = None  # e.g. "Was 7.4% last time, now 6.8%"


class ReportSummary(BaseModel):
    normal_summary: str  # ONE line covering all normal tests
    abnormal: list[AbnormalMarker]
    cross_marker_patterns: list[
        str
    ]  # e.g. low Hb + low MCV -> possible iron deficiency pattern
    urgency: Literal["Routine", "Consult Soon", "Prompt Attention"]
    specialist: str  # e.g. "General Physician", "Endocrinologist"
    doctor_questions: list[str] = Field(min_length=3, max_length=3)  # EXACTLY 3
```

No field for a disclaimer, greeting or free-form text. The model must not produce anything outside this schema.

## 3. Token Conservation (free tier)

1. **Cache first.** Compute `report_hash = sha256("\n".join(sorted(scrubbed_biomarker_lines)))`. Check `reports.report_hash` for that user. If found, return the stored `summary_*` JSON with **zero Gemini calls**.
2. **Compress normal results.** Send normal tests as a count and a short list of names. Gemini outputs ONE `normal_summary` line. Never explain normal tests one by one.
3. **Explain only abnormal or borderline markers**, 1 to 2 sentences each, plus cross-marker patterns.
4. **Send only** scrubbed biomarker lines, age, sex and historical deltas. No headers, no addresses, no boilerplate.
5. **Cache translations.** Store `summary_en`, `summary_hi` and `summary_kn` in the same `reports` row. A language button click first checks that column and only calls Gemini if it is `NULL`. A second click never triggers a second call.
6. Translation calls take the **stored English JSON** as input, not the image or OCR text.
7. Set a sensible `max_output_tokens` (about 1500) and handle 429 errors with one short backoff, then a polite "try again in a minute" message.

## 4. Medical Safety Guardrails (hard-coded in Python, not in the prompt)

Implement `apply_safety_overrides(parsed_rows, summary) -> ReportSummary` and run it **after** every Gemini response and also on cache reads.

Critical-value table (starting set; a clinician should review and extend it before real use):

```python
CRITICAL_RULES = [
    # (test aliases, unit, comparator, threshold, label)
    (["hemoglobin", "haemoglobin", "hb"], "g/dL", "<", 7.0, "Very low Hemoglobin"),
    (
        ["fasting glucose", "fbs", "fasting blood sugar", "fasting plasma glucose"],
        "mg/dL",
        ">",
        250,
        "Very high Fasting Glucose",
    ),
    (
        ["random glucose", "rbs", "random blood sugar"],
        "mg/dL",
        ">",
        400,
        "Very high Random Glucose",
    ),
    (["glucose", "blood sugar"], "mg/dL", "<", 50, "Very low Glucose"),
    (["potassium"], "mmol/L", ">", 6.0, "Very high Potassium"),
    (["potassium"], "mmol/L", "<", 2.8, "Very low Potassium"),
    (["sodium"], "mmol/L", "<", 120, "Very low Sodium"),
    (["platelet", "platelets"], "/cumm", "<", 20000, "Very low Platelets"),
    (["creatinine"], "mg/dL", ">", 5.0, "Very high Creatinine"),
    (["tsh"], "mIU/L", ">", 50, "Very high TSH"),
]
```

Rules:

- Match tests by lowercase alias. Normalise units first (convert e.g. `g/L`→`g/dL`, `lakhs/cumm`→`/cumm`, `mmol/L` glucose → `mg/dL` x18).
- If any critical rule matches: force `urgency = "Prompt Attention"`, add the label to `abnormal` if missing, and add a fixed (non-AI) first line telling the family to contact a doctor today.
- Overrides can only **raise** urgency, never lower it.
- If OCR confidence is low or a value could not be parsed, **do not output "Routine"**. Use at least `"Consult Soon"` and say some values could not be read.
- Never produce a diagnosis name as a conclusion. Use "pattern that doctors often check for" wording.
- Never recommend, change or stop medicines, and never give doses.
- Always include the specialist suggestion and the 3 doctor questions.

## 5. System Prompt Rules (English analysis)

The system prompt must say, in effect:

- You explain lab results to a patient's family in plain language. You do not diagnose.
- Use everyday words. If a medical term is unavoidable, add a short meaning in brackets.
- Use reference ranges **as printed in the report** for the status. Do not invent ranges.
- Compare with `history` deltas when provided, and mention improvement or worsening in `trend_note`.
- Look for cross-marker patterns (e.g. Hb + MCV + MCH, fasting glucose + HbA1c, lipid ratios, TSH + T3/T4, creatinine + urea, SGPT + SGOT).
- Tone is calm and factual. Do not use alarming words unless the numbers are critical. Do not falsely reassure.
- Output only the JSON.

## 6. Regional Language Rule (Hindi and Kannada)

For `hi` and `kn` translation calls:

- Write as if a **grandson is forwarding this message to his grandmother**: warm, simple, spoken-style language, short sentences, respectful tone (Hindi: आप-form; Kannada: ನೀವು-form).
- No medical jargon. Explain terms in everyday words, e.g. Hemoglobin as "blood strength" with the term in brackets once.
- Keep test names and numbers in English/Latin script so they match the printed report. Explain around them in the local language.
- Keep the same JSON schema, with the same exactly-3 doctor questions, translated naturally.
- Do not translate the `urgency` enum value. The bot maps it to a localised label using a fixed dictionary in code.
- Do not add or remove medical content versus the English JSON. Translate meaning only.
- Never write the disclaimer. Code injects it.
