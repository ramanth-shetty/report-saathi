# 06a. API Contract: ReportSaathi

This document defines the formal interfaces, HTTP payloads, and internal module contracts for **ReportSaathi**.

---

## 1. External REST API (`backend/main.py`)

### 1.1 `GET /health`
* **Purpose:** Health check probe for container runners (Render) and uptime monitors.
* **Request:** None
* **Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "ReportSaathi",
  "version": "1.0.0"
}
```

---

### 1.2 `POST /api/analyze`
* **Purpose:** Synchronous analysis endpoint for web uploads (Cloudflare Pages).
* **Content-Type:** `multipart/form-data`
* **Request Parameters:**
  * `file` (File, Required): Binary payload of the image (`.jpg`, `.jpeg`, `.png`) or PDF (`.pdf`), max 10MB.
  * `lang` (String, Optional): Target vernacular language (`"en"`, `"hi"`, or `"kn"`). Defaults to `"en"`.
  * `user_id` (UUID, Optional): User identifier for saving history/trends. If omitted, analysis runs ephemerally without persistence.
* **Success Response (200 OK):**
```json
{
  "report_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "urgency": "Routine",
  "specialist": "General Physician",
  "normal_summary": "Complete Blood Count, Kidney and Liver parameters are within standard ranges.",
  "abnormal": [
    {
      "test": "HbA1c",
      "value": "7.8 %",
      "status": "High",
      "explanation": "Your average three-month sugar level is slightly elevated above standard targets.",
      "trend_note": "Was 8.4% three months ago (improved)."
    }
  ],
  "cross_marker_patterns": [],
  "doctor_questions": [
    "Does my improved HbA1c mean my current medicine dosage is working well?",
    "Should we recheck my fasting blood sugar in 6 or 12 weeks?",
    "Do I need any additional adjustments to my morning diet?"
  ],
  "disclaimer": "This explains your report in simple words. It is not a diagnosis. Please show the report to your doctor."
}
```
* **Error Responses:**
  * `400 Bad Request`: `{"detail": "File too blurry or unreadable. Please provide a clear, straight-on photo."}`
  * `413 Payload Too Large`: `{"detail": "File exceeds maximum size limit of 10MB."}`
  * `422 Unprocessable Entity`: `{"detail": "Unsupported file format. Please upload JPEG, PNG, or PDF."}`
  * `429 Too Many Requests`: `{"detail": "API rate limit reached. Please retry in a few moments."}`
  * `500 Internal Server Error`: `{"detail": "Internal analysis error. Please try again later."}`

---

### 1.3 `POST /telegram/webhook/{secret_token}`
* **Purpose:** Ingestion webhook for Telegram updates.
* **Path Parameter:** `secret_token` matches `WEBHOOK_SECRET` environment variable.
* **Request Body:** Standard Telegram `Update` object.
* **Response:** `200 OK`

---

## 2. Internal Module Contracts

### 2.1 `backend/ocr_scrub.py`
```python
def preprocess(image_bytes: bytes) -> np.ndarray:
    """Decodes, upscales if <1500px, converts to grayscale, applies adaptive threshold, and deskews."""
    ...


def ocr_rows(img: np.ndarray) -> tuple[list[str], float]:
    """Runs Tesseract --psm 6 and groups words by vertical center.
    Returns (visual_rows, avg_confidence). Flag low_quality=True if avg_confidence < 55.0.
    """
    ...


def parse_rows(lines: list[str]) -> list[dict]:
    """Extracts {test_name: str, observed_value: float, unit: str, ref_range: str} via regex."""
    ...


def scrub_pii(lines: list[str]) -> tuple[list[str], int | None, str | None]:
    """Redacts patient/doctor names, phones, UHIDs, addresses.
    Returns (scrubbed_lines, age, biological_sex).
    """
    ...
```

---

### 2.2 `backend/gemini_analyzer.py`
```python
class AbnormalMarker(BaseModel):
    test: str
    value: str
    status: Literal["Low", "High", "Borderline"]
    explanation: str
    trend_note: str | None = None


class ReportSummary(BaseModel):
    normal_summary: str
    abnormal: list[AbnormalMarker]
    cross_marker_patterns: list[str]
    urgency: Literal["Routine", "Consult Soon", "Prompt Attention"]
    specialist: str
    doctor_questions: list[str] = Field(min_length=3, max_length=3)


def analyze(
    rows: list[str],
    age: int | None,
    sex: str | None,
    deltas: list[str],
    lang: str = "en",
) -> ReportSummary:
    """Calls Gemini 2.5 Flash with response_schema=ReportSummary."""
    ...


def apply_safety_overrides(
    parsed_rows: list[dict], summary: ReportSummary
) -> ReportSummary:
    """Deterministic check against CRITICAL_RULES table. Only raises urgency, never lowers."""
    ...
```

---

### 2.3 `backend/database.py`
```python
def find_report_by_hash(user_id: str, report_hash: str) -> dict | None: ...
def save_report(
    user_id: str,
    report_hash: str,
    summary_en: dict,
    urgency: str,
    biomarker_rows: list[dict],
) -> str: ...
def save_translation(report_id: str, lang: str, summary_json: dict) -> None: ...
def get_translation(report_id: str, lang: str) -> dict | None: ...
def delete_user_data(chat_id: int) -> bool: ...
```
