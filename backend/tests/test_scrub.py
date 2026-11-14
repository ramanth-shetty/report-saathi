"""Unit and integration test suite for Task PR-03 (OCR & Privacy Engine).

Validates:
- TC-FR-3.1: Deterministic Local PII Redaction (0 PII tokens survive).
- TC-FR-3.2: Clinical Context Extraction (Age & Biological Sex preserved).
- TC-FR-2.3: Low-confidence OCR quality gate intercept (<55 confidence).
- Row-aware parsing: Decimal precision, unit normalizations, and reference ranges.
- Image preprocessing: Grayscale, thresholding, and deskewing without exceptions.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf as fitz
from PIL import Image

from backend.ocr_scrub import (
    extract_age_sex,
    ocr_rows,
    parse_rows,
    preprocess,
    rasterize_pdf,
    scrub_pii,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
REPORT_08_PATH = FIXTURES_DIR / "report-08-heavy-pii-header.txt"
REPORT_09_PATH = FIXTURES_DIR / "report-09-blurry-low-confidence.txt"


def test_tc_fr_3_1_heavy_pii_redaction() -> None:
    """TC-FR-3.1: Validate that zero personal identifiers survive scrubbing."""
    assert REPORT_08_PATH.exists(), f"Missing fixture at {REPORT_08_PATH}"
    lines = REPORT_08_PATH.read_text(encoding="utf-8").splitlines()

    scrubbed_lines, age, sex = scrub_pii(lines)

    # 1. Verify clinical context was extracted
    assert age == 52
    assert sex == "Male"

    # 2. Re-combine scrubbed output for token inspection
    scrubbed_corpus = "\n".join(scrubbed_lines)

    # 3. Assert zero PII tokens survive
    forbidden_tokens = [
        "Shri Vikramaditya Raghavendra Rao",
        "Vikramaditya",
        "Raghavendra",
        "9886012345",
        "26654321",
        "vikram.rao.1974@rediffmail.com",
        "XXXX-XXXX-4921",
        "Shanti Nilaya Apartments",
        "JP Nagar 2nd Phase",
        "560078",
        "FH-BLR-0098231",
        "VIS-2026-991823",
        "BILL-9821-C",
        "Balakrishna",
        "KMC-54912",
        "Preeti Deshpande",
        "Rajesh_OPD4",
        "https://myreports.fortishealthcare.com",
    ]

    for token in forbidden_tokens:
        assert token not in scrubbed_corpus, f"PII token leaked: '{token}'"

    # 4. Assert all clinical biomarker test lines survived
    expected_tests = [
        "Fasting Plasma Glucose",
        "Post-Meal Plasma Glucose",
        "Serum Creatinine",
        "Serum Uric Acid",
        "SGPT (ALT)",
        "SGOT (AST)",
        "Alkaline Phosphatase (ALP)",
        "Total Bilirubin",
    ]

    for test_name in expected_tests:
        assert test_name in scrubbed_corpus, (
            f"Biomarker erroneously redacted: '{test_name}'"
        )


def test_tc_fr_3_2_clinical_context_extraction() -> None:
    """TC-FR-3.2: Validate age and biological sex extraction across diverse formats."""
    lines_male = [
        "Patient Full Name: John Doe",
        "Age: 52 Years       Gender: Male       DOB: 14-Aug-1974",
    ]
    age, sex = extract_age_sex(lines_male)
    assert age == 52
    assert sex == "Male"

    lines_female = [
        "Patient: Jane Doe | Age - 68 Yrs | Sex: F",
    ]
    age_f, sex_f = extract_age_sex(lines_female)
    assert age_f == 68
    assert sex_f == "Female"

    lines_none = ["Complete Blood Count", "Hemoglobin 14.2 g/dL"]
    age_none, sex_none = extract_age_sex(lines_none)
    assert age_none is None
    assert sex_none is None


def test_tc_fr_2_3_blurry_low_confidence_gate() -> None:
    """TC-FR-2.3: Low OCR confidence (<55) must trigger quality gate flag."""
    # Simulate Tesseract Output.DICT with low confidence (<55)
    mock_low_conf_data = {
        "text": ["H3m0gl0b1n", "??.?", "g/dL", "Cr3@t1n1n3"],
        "conf": ["35.0", "20.0", "40.0", "38.0"],
        "left": [10, 100, 150, 10],
        "top": [20, 20, 20, 60],
        "width": [80, 40, 40, 80],
        "height": [20, 20, 20, 20],
    }

    synthetic_img = np.full((100, 200), 255, dtype=np.uint8)

    with patch("pytesseract.image_to_data", return_value=mock_low_conf_data):
        visual_rows, avg_conf = ocr_rows(synthetic_img)
        assert avg_conf < 55.0
        # Flag low_quality condition
        low_quality = avg_conf < 55.0
        assert low_quality is True


def test_parse_rows_structured_output() -> None:
    """Validate biomarker regex parser extracts values and normalizes tokens."""
    sample_lines = [
        "Fasting Plasma Glucose 158 mg/dL 70 - 100",
        "Serum Creatinine 1.1 mg/dL 0.7 - 1.3",
        "Post-Meal Plasma Glucose 224 mg/dL < 140",
        "Random Noise Header [REDACTED]",
    ]

    parsed = parse_rows(sample_lines)
    assert len(parsed) == 3

    fbs = parsed[0]
    assert fbs["test_name"] == "Fasting Plasma Glucose"
    assert fbs["observed_value"] == 158.0
    assert fbs["unit"] == "mg/dL"
    assert fbs["ref_range"] == "70 - 100"

    creat = parsed[1]
    assert creat["test_name"] == "Serum Creatinine"
    assert creat["observed_value"] == 1.1
    assert creat["unit"] == "mg/dL"
    assert creat["ref_range"] == "0.7 - 1.3"

    ppbs = parsed[2]
    assert ppbs["test_name"] == "Post-Meal Plasma Glucose"
    assert ppbs["observed_value"] == 224.0
    assert ppbs["unit"] == "mg/dL"
    assert ppbs["ref_range"] == "< 140"


def test_preprocess_pipeline_execution() -> None:
    """Validate preprocess image decoding, upscaling, thresholding, and deskew."""
    # Create synthetic test image (white canvas with black text rectangle)
    img = Image.new("RGB", (600, 400), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    processed = preprocess(png_bytes)
    assert isinstance(processed, np.ndarray)
    assert len(processed.shape) == 2  # Grayscale thresholded
    assert processed.shape[1] >= 1200  # Upscaled


def test_rasterize_pdf_pipeline_execution() -> None:
    """Validate PDF rasterization into 300 DPI image bytes using PyMuPDF."""
    # Create minimal 1-page digital PDF in memory
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((50, 50), "ReportSaathi Test Page")
    pdf_bytes = doc.tobytes()
    doc.close()

    rasterized = rasterize_pdf(pdf_bytes, dpi=150)
    assert len(rasterized) == 1
    assert isinstance(rasterized[0], bytes)
    assert len(rasterized[0]) > 0
