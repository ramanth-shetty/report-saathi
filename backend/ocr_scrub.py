"""ReportSaathi OCR Preprocessing and Deterministic PII Scrubbing Engine.

Applies:
- OpenCV image preprocessing (adaptive threshold, grayscale, deskew, upscale).
- PyMuPDF multi-page PDF rasterization (300 DPI).
- Tesseract row-aware OCR (--psm 6) grouping words by vertical centers (y_c).
- Quality Gate: flags low_quality=True if average confidence < 55.0.
- Local deterministic PII scrubbing: redacting patient names, phones, UHIDs,
  addresses, and doctor credentials to [REDACTED] without external API calls.
- Invariant clinical context extraction (Age and Biological Sex).
- Invariant trilingual DISCLAIMER constants.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Final

import cv2
import numpy as np
import pymupdf as fitz
import pytesseract
from pytesseract import Output

logger = logging.getLogger(__name__)

# Configure local Tesseract path for Windows if present
_DEFAULT_TESSERACT_WIN: Final[str] = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_configured_tesseract = os.getenv("TESSERACT_CMD", _DEFAULT_TESSERACT_WIN)
if os.path.exists(_configured_tesseract):
    pytesseract.pytesseract.tesseract_cmd = _configured_tesseract


# ==============================================================================
# 1. Image Pre-processing (OpenCV)
# ==============================================================================


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Decodes, upscales if <1500px, converts to grayscale, denoises,

    applies adaptive threshold, and deskews.

    Follows Rule 01 (docs/06-architecture.md & .agents/rules/01-ocr-and-privacy.md).
    """
    if not image_bytes:
        raise ValueError("Image bytes payload is empty.")

    # 1. Decode with cv2.imdecode
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image bytes into OpenCV matrix.")

    # Upscale 2x if longest side is below 1500 px
    max_dim = max(img.shape[0], img.shape[1])
    if max_dim < 1500:
        img = cv2.resize(img, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    # 2. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3. Light denoise (median blur kernel 3)
    denoised = cv2.medianBlur(gray, 3)

    # 4. Adaptive thresholding (removes shadows)
    thresh = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    # 5. Deskew: estimate angle on dark text pixels
    text_coords = np.column_stack(np.where(thresh < 128))
    if len(text_coords) > 50:
        rect = cv2.minAreaRect(text_coords)
        angle = rect[-1]

        # Normalize OpenCV angle
        if angle < -45.0:
            angle = -(90.0 + angle)
        elif angle > 45.0:
            angle = 90.0 - angle

        # Rotate only if rotation angle is meaningful and realistic (<45 deg)
        if 0.5 <= abs(angle) <= 45.0:
            h, w = thresh.shape[:2]
            center = (w // 2, h // 2)
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            thresh = cv2.warpAffine(
                thresh,
                rot_mat,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=255,
            )

    return thresh


def rasterize_pdf(pdf_bytes: bytes, dpi: int = 300) -> list[bytes]:
    """Rasterize multi-page digital or scanned PDF documents at 300 DPI."""
    if not pdf_bytes:
        raise ValueError("PDF bytes payload is empty.")

    pages_images: list[bytes] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=dpi)
            pages_images.append(pix.tobytes("png"))
    finally:
        doc.close()

    return pages_images


# ==============================================================================
# 2. Row-Aware OCR (Grouping by Vertical Centers)
# ==============================================================================


def ocr_rows(img: np.ndarray) -> tuple[list[str], float]:
    """Executes Tesseract with --psm 6 and groups words by vertical center (y_c).

    Returns (visual_rows, avg_confidence).
    Quality gate: average confidence < 55.0 signals low_quality = True.
    """
    data = pytesseract.image_to_data(
        img,
        config="--psm 6",
        output_type=Output.DICT,
    )

    n_boxes = len(data["text"])
    words: list[dict[str, Any]] = []
    conf_sum = 0.0
    conf_count = 0

    for i in range(n_boxes):
        text = str(data["text"][i]).strip()
        conf_raw = data["conf"][i]

        try:
            conf = float(conf_raw)
        except (ValueError, TypeError):
            conf = -1.0

        if conf < 30.0 or not text:
            continue

        conf_sum += conf
        conf_count += 1

        top = int(data["top"][i])
        height = int(data["height"][i])
        left = int(data["left"][i])
        width = int(data["width"][i])
        y_c = top + (height / 2.0)

        words.append(
            {
                "text": text,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "y_c": y_c,
            }
        )

    if not words:
        return ([], 0.0)

    avg_conf = conf_sum / conf_count if conf_count > 0 else 0.0

    # Calculate median word height
    heights = sorted(w["height"] for w in words)
    median_h = float(heights[len(heights) // 2]) if heights else 15.0
    row_threshold = max(8.0, 0.6 * median_h)

    # Sort words by vertical center y_c
    words.sort(key=lambda w: w["y_c"])

    # Group words into visual rows
    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = [words[0]]
    current_row_yc = words[0]["y_c"]

    for w in words[1:]:
        if abs(w["y_c"] - current_row_yc) <= row_threshold:
            current_row.append(w)
            current_row_yc = sum(item["y_c"] for item in current_row) / len(current_row)
        else:
            rows.append(current_row)
            current_row = [w]
            current_row_yc = w["y_c"]
    if current_row:
        rows.append(current_row)

    # Within each row, sort words by left coordinate and join
    visual_lines: list[str] = []
    for row in rows:
        row.sort(key=lambda w: w["left"])
        line_parts: list[str] = []
        for idx, word in enumerate(row):
            if idx > 0:
                prev_word = row[idx - 1]
                gap = word["left"] - (prev_word["left"] + prev_word["width"])
                # If large horizontal column gap, use pipe separator or multi-space
                if gap > 2.5 * median_h:
                    line_parts.append(" | ")
                else:
                    line_parts.append(" ")
            line_parts.append(word["text"])
        visual_lines.append("".join(line_parts).strip())

    return (visual_lines, avg_conf)


# ==============================================================================
# 3. Row Parsing & OCR Normalization
# ==============================================================================


def _normalize_numeric_token(tok: str) -> str:
    """Normalize common OCR confusions strictly inside numeric tokens."""
    # O -> 0, o -> 0, l -> 1, I -> 1, comma -> dot
    return (
        tok.replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("I", "1")
        .replace(",", ".")
    )


def parse_rows(lines: list[str]) -> list[dict[str, Any]]:
    """Extracts structured biomarker dicts:

    {test_name, observed_value (float), unit, ref_range} via regex.
    Handles numeric token normalizations and preserves decimal precision.
    """
    parsed: list[dict[str, Any]] = []

    pattern = re.compile(
        r"^(?P<name>[A-Za-z0-9\s\(\)\/\-\+\_]+?)\s*[:|]?\s+"
        r"(?P<val>[0-9OlI]+(?:\.[0-9OlI]+)?)\s*[:|]?\s*"
        r"(?P<unit>[a-zA-Z\%\/\u03bc\u00b5][a-zA-Z0-9\/\%\u03bc\u00b5\-]*)?\s*[:|]?\s*"
        r"(?P<range>.*?)$",
        re.IGNORECASE,
    )

    for line in lines:
        cleaned_line = line.strip()
        if (
            not cleaned_line
            or cleaned_line.startswith(("===", "---", "***"))
            or "[REDACTED]" in cleaned_line
        ):
            continue

        match = pattern.match(cleaned_line)
        if match:
            raw_name = match.group("name").strip(" |:")
            raw_val = match.group("val")
            raw_unit = match.group("unit") or ""
            raw_range = match.group("range") or ""

            if not raw_name or len(raw_name) < 2:
                continue

            # Normalize OCR confusion on numbers
            norm_val = _normalize_numeric_token(raw_val)
            try:
                val_float = float(norm_val)
            except ValueError:
                continue

            parsed.append(
                {
                    "test_name": raw_name,
                    "observed_value": val_float,
                    "unit": raw_unit.strip(),
                    "ref_range": raw_range.strip(),
                }
            )

    return parsed


# ==============================================================================
# 4. Clinical Context Extraction (Age & Biological Sex)
# ==============================================================================


def extract_age_sex(lines: list[str]) -> tuple[int | None, str | None]:
    """Extracts age integer and biological sex string from report lines.

    Preserves clinical grounding while allowing full redaction of demographic headers.
    """
    age: int | None = None
    sex: str | None = None

    age_regex = re.compile(
        r"\bAge\s*[:\s\-]\s*(\d{1,3})\s*(?:Yrs?|Years?|Y)?\b", re.IGNORECASE
    )
    sex_regex = re.compile(
        r"\b(?:Gender|Sex)\s*[:\s\-]\s*(Male|Female|Other|M|F)\b", re.IGNORECASE
    )

    for line in lines:
        if age is None:
            age_m = age_regex.search(line)
            if age_m:
                try:
                    age = int(age_m.group(1))
                except ValueError:
                    pass

        if sex is None:
            sex_m = sex_regex.search(line)
            if sex_m:
                raw_sex = sex_m.group(1).capitalize()
                if raw_sex in ("M", "Male"):
                    sex = "Male"
                elif raw_sex in ("F", "Female"):
                    sex = "Female"
                else:
                    sex = "Other"

        if age is not None and sex is not None:
            break

    return (age, sex)


# ==============================================================================
# 5. Best-Effort Local Deterministic PII Scrubbing
# ==============================================================================

# Patient identifier label prefixes
_PII_LINE_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(
        r"^\s*(?:Patient\s+(?:Full\s+)?Name|Patient|Name)\s*[:\s]", re.IGNORECASE
    ),
    re.compile(r"^\s*(?:Relative\s+Name|S/o|D/o|W/o|C/o)\s*[:\s]", re.IGNORECASE),
    re.compile(r"^\s*(?:Mr\.|Mrs\.|Ms\.|Smt\.|Shri)\b", re.IGNORECASE),
    re.compile(
        r"^\s*(?:Hospital\s+)?(?:UHID|MRN|Lab\s+No|Sample\s+ID|Reg\s+No|Barcode|Bill\s+No|Visit\s+(?:ID|Number)|Accession|Billing\s+Invoice)\s*[:\s]",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:Attending\s+)?(?:Consultant|Pathologist|Referred\s+by|Ref\.\s*by|Doctor|Dr\.)\s*[:\s]",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:Residential\s+)?(?:Address|Addr)\s*[:\s]", re.IGNORECASE),
    re.compile(r"^\s*(?:National\s+ID|Aadhaar)\s*[:\s]", re.IGNORECASE),
    re.compile(
        r"^\s*(?:NABL|ISO\s+\d+|CAP\s+Accredited|Web\s+Portal|Printed\s+by|Printed\s+on)\b",
        re.IGNORECASE,
    ),
]

_PHONE_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:\+?91[\-\s]?)?[6-9]\d{9}|\b0\d{2,4}[\-\s]?\d{6,8}\b"
)
_EMAIL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
_PINCODE_REGEX: Final[re.Pattern[str]] = re.compile(r"\b5[6-8]\d{4}\b|\b\d{6}\b")
_URL_REGEX: Final[re.Pattern[str]] = re.compile(r"https?://\S+")
_DOCTOR_NAME_REGEX: Final[re.Pattern[str]] = re.compile(
    r"\bDr\.\s+[A-Za-z\.\s]+", re.IGNORECASE
)


def scrub_pii(lines: list[str]) -> tuple[list[str], int | None, str | None]:
    """Scrub PII locally and deterministically BEFORE any external API call.

    Redacts:
    - Patient and relative names, titles (Shri, Smt, etc.)
    - Phone numbers (mobile, landline)
    - Email addresses
    - Physical addresses, layout/street names, 6-digit postal pincodes
    - Hospital identifiers (UHID, MRN, Lab No, Visit ID, Invoice No)
    - Doctor names, registration numbers, credentials
    - Laboratory boilerplate (NABL, ISO, portal URLs, operator signatures)

    Preserves:
    - Extracted age and biological sex context
    - Structured biomarker rows and clinical parameters

    Returns (scrubbed_lines, age, biological_sex).
    """
    age, sex = extract_age_sex(lines)
    scrubbed_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check line-level whole-line redaction patterns
        is_pii_line = any(pattern.search(stripped) for pattern in _PII_LINE_PATTERNS)
        if is_pii_line:
            # Check if line contains Age/Gender on the same line; preserve them
            has_age = bool(re.search(r"\bAge\b", stripped, re.IGNORECASE))
            has_gender = bool(re.search(r"\b(?:Gender|Sex)\b", stripped, re.IGNORECASE))
            if has_age or has_gender:
                # Retain an isolated demographic line without personal names
                context_parts: list[str] = []
                if age is not None:
                    context_parts.append(f"Age: {age} Years")
                if sex is not None:
                    context_parts.append(f"Gender: {sex}")
                scrubbed_lines.append(" | ".join(context_parts))
            else:
                scrubbed_lines.append("[REDACTED]")
            continue

        # Token-level redactions on remaining lines
        redacted = stripped

        # 1. Emails
        redacted = _EMAIL_REGEX.sub("[REDACTED]", redacted)

        # 2. URLs
        redacted = _URL_REGEX.sub("[REDACTED]", redacted)

        # 3. Phone numbers
        redacted = _PHONE_REGEX.sub("[REDACTED]", redacted)

        # 4. Doctor names
        redacted = _DOCTOR_NAME_REGEX.sub("[REDACTED]", redacted)

        # 5. Addresses and Postal Pincodes (if line appears address-like)
        if re.search(
            r"\b(?:Apartments?|Cross|Main|Nagar|Layout|Phase|Street|Road)\b",
            redacted,
            re.IGNORECASE,
        ):
            redacted = "[REDACTED]"
        elif _PINCODE_REGEX.search(redacted) and not re.search(
            r"\b(?:U/L|mg/dL|mmol/L|g/dL)\b", redacted
        ):
            redacted = _PINCODE_REGEX.sub("[REDACTED]", redacted)

        # Check for lingering ID patterns (e.g. XXXX-XXXX-4921)
        if re.search(r"\bXXXX[- ]XXXX[- ]\d{4}\b", redacted):
            redacted = "[REDACTED]"

        scrubbed_lines.append(redacted)

    return (scrubbed_lines, age, sex)


# ==============================================================================
# 6. CLI Verification Entrypoint
# ==============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python backend/ocr_scrub.py <path_to_image_or_pdf>")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        sys.exit(1)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    print(f"Processing: {file_path} ({len(file_bytes)} bytes)")

    if file_path.lower().endswith(".pdf"):
        images = rasterize_pdf(file_bytes)
        print(f"Rasterized {len(images)} PDF page(s).")
        raw_image_bytes = images[0]
    else:
        raw_image_bytes = file_bytes

    preprocessed_img = preprocess(raw_image_bytes)
    lines, avg_confidence = ocr_rows(preprocessed_img)

    print(f"Average OCR Confidence: {avg_confidence:.2f}%")
    if avg_confidence < 55.0:
        print("QUALITY GATE: low_quality = True (photo is blurry or low confidence)")
    else:
        print("QUALITY GATE: Passed.")

    scrubbed, extracted_age, extracted_sex = scrub_pii(lines)
    print(f"Clinical Context: Age={extracted_age}, Sex={extracted_sex}")
    print("\n--- Scrubbed Rows ---")
    for row in scrubbed:
        print(row)

    parsed_biomarkers = parse_rows(scrubbed)
    print(f"\nParsed Biomarkers ({len(parsed_biomarkers)}):")
    for b in parsed_biomarkers:
        print(b)
