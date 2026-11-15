"""Database persistence, deduplication caching, and trend delta engine.

Manages interactions with Supabase PostgreSQL using the service role key:
- DPDP Act 2023 compliant user lifecycle and cascading erasure.
- Deterministic SHA-256 report deduplication caching.
- Multilingual translation caching for English, Hindi, and Kannada.
- Longitudinal biomarker tracking and trend delta calculations.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any, Final, cast

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_supabase_client = None


def get_supabase_client() -> Any | None:
    """Initialize or return the cached Supabase client using environment variables.

    Returns None if SUPABASE_URL or SUPABASE_SERVICE_KEY are not configured.
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        return None

    try:
        from supabase import create_client

        _supabase_client = create_client(supabase_url, supabase_key)
        return _supabase_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize Supabase client: %s", exc)
        return None


def get_database_health() -> dict[str, Any]:
    """Execute a lightweight read against Supabase to verify connectivity.

    Returns a dict with 'status', 'value', and optional 'message'.
    """
    client = get_supabase_client()
    if client is None:
        return {
            "status": "disconnected",
            "value": None,
            "message": "SUPABASE_URL or SUPABASE_SERVICE_KEY is not configured.",
        }

    try:
        response = client.table("users").select("id", count="exact").limit(1).execute()
        count_display = (
            f"{response.count} rows" if response.count is not None else "accessible"
        )
        return {
            "status": "connected",
            "value": f"Supabase PostgreSQL (users table: {count_display})",
            "message": "Database query succeeded.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Database health query failed: %s", exc)
        return {
            "status": "error",
            "value": None,
            "message": f"Query error: {exc}",
        }


# ==============================================================================
# 1. SHA-256 Deduplication Hashing
# ==============================================================================


def compute_report_hash(scrubbed_lines: list[str]) -> str:
    """Computes a deterministic SHA-256 hash from scrubbed report rows.

    Normalizes whitespace and ignores empty rows before hashing.
    """
    normalized_lines = [
        re.sub(r"\s+", " ", line).strip() for line in scrubbed_lines if line.strip()
    ]
    payload = "\n".join(normalized_lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ==============================================================================
# 2. User Management & DPDP Consent Gate
# ==============================================================================


def get_or_create_user(
    chat_id: int | None = None,
    email: str | None = None,
    age: int | None = None,
    biological_sex: str | None = None,
    lang: str = "en",
    client: Any | None = None,
) -> dict[str, Any]:
    """Retrieves an existing user or creates a minimal user record.

    Enforces DPDP storage minimization: no names or phone numbers are stored.
    """
    sb = client or get_supabase_client()
    if sb is None:
        raise RuntimeError("Database client is not available.")

    # Search for existing user by chat_id or email
    query = sb.table("users").select("*")
    if chat_id is not None:
        res = query.eq("telegram_chat_id", chat_id).execute()
    elif email is not None:
        res = query.eq("email", email).execute()
    else:
        raise ValueError("Either chat_id or email must be provided.")

    if res.data and len(res.data) > 0:
        existing_user: dict[str, Any] = res.data[0]
        # Update age or sex if newly extracted and previously absent
        updates: dict[str, Any] = {}
        if age is not None and existing_user.get("age") is None:
            updates["age"] = age
        if biological_sex is not None and existing_user.get("biological_sex") is None:
            updates["biological_sex"] = biological_sex

        if updates:
            up_res = (
                sb.table("users")
                .update(updates)
                .eq("id", existing_user["id"])
                .execute()
            )
            if up_res.data:
                return cast(dict[str, Any], up_res.data[0])
        return existing_user

    # Create new minimal user
    new_user_payload: dict[str, Any] = {
        "preferred_lang": lang if lang in ("en", "hi", "kn") else "en",
    }
    if chat_id is not None:
        new_user_payload["telegram_chat_id"] = chat_id
    if email is not None:
        new_user_payload["email"] = email
    if age is not None:
        new_user_payload["age"] = age
    if biological_sex is not None:
        new_user_payload["biological_sex"] = biological_sex

    insert_res = sb.table("users").insert(new_user_payload).execute()
    if not insert_res.data:
        raise RuntimeError("Failed to insert user record into Supabase.")
    return cast(dict[str, Any], insert_res.data[0])


def set_consent(user_id: str, client: Any | None = None) -> dict[str, Any]:
    """Records affirmative user consent timestamp (DPDP Act 2023 requirement)."""
    sb = client or get_supabase_client()
    if sb is None:
        raise RuntimeError("Database client is not available.")

    now_iso = datetime.now(UTC).isoformat()
    res = sb.table("users").update({"consent_at": now_iso}).eq("id", user_id).execute()
    if not res.data:
        raise RuntimeError(f"User {user_id} not found to set consent.")
    return cast(dict[str, Any], res.data[0])


def set_language(user_id: str, lang: str, client: Any | None = None) -> dict[str, Any]:
    """Updates user preferred Indic language ('en', 'hi', or 'kn')."""
    sb = client or get_supabase_client()
    if sb is None:
        raise RuntimeError("Database client is not available.")

    valid_lang = lang if lang in ("en", "hi", "kn") else "en"
    res = (
        sb.table("users")
        .update({"preferred_lang": valid_lang})
        .eq("id", user_id)
        .execute()
    )
    if not res.data:
        raise RuntimeError(f"User {user_id} not found to set language.")
    return cast(dict[str, Any], res.data[0])


# ==============================================================================
# 3. Report Caching & Biomarker Persistence
# ==============================================================================


def find_report_by_hash(
    user_id: str, report_hash: str, client: Any | None = None
) -> dict[str, Any] | None:
    """Finds cached report by compound index (user_id, report_hash).

    Returns None if cache miss occurs.
    """
    sb = client or get_supabase_client()
    if sb is None:
        return None

    res = (
        sb.table("reports")
        .select("*")
        .eq("user_id", user_id)
        .eq("report_hash", report_hash)
        .execute()
    )
    if res.data and len(res.data) > 0:
        return cast(dict[str, Any], res.data[0])
    return None


def save_report(
    user_id: str,
    report_hash: str,
    summary_en: dict[str, Any],
    urgency: str,
    biomarker_rows: list[dict[str, Any]],
    client: Any | None = None,
) -> str:
    """Persists a scrubbed summary and linked biomarker rows.

    Returns the generated report UUID.
    """
    sb = client or get_supabase_client()
    if sb is None:
        raise RuntimeError("Database client is not available.")

    # 1. Insert report record
    report_data = {
        "user_id": user_id,
        "report_hash": report_hash,
        "urgency_level": urgency,
        "summary_en": summary_en,
    }
    rep_res = sb.table("reports").insert(report_data).execute()
    if not rep_res.data:
        raise RuntimeError("Failed to insert report into Supabase.")

    report_id = str(rep_res.data[0]["id"])

    # 2. Insert linked biomarker rows
    if biomarker_rows:
        rows_to_insert = []
        for r in biomarker_rows:
            test_name = str(r.get("test_name", "")).strip()
            if not test_name:
                continue

            raw_val = r.get("observed_value")
            val_float = None
            if raw_val is not None:
                try:
                    val_float = float(raw_val)
                except (ValueError, TypeError):
                    val_float = None

            rows_to_insert.append(
                {
                    "report_id": report_id,
                    "user_id": user_id,
                    "test_name": test_name,
                    "observed_value": val_float,
                    "unit": str(r.get("unit", "")).strip() or None,
                    "ref_range": str(r.get("ref_range", "")).strip() or None,
                    "status": r.get("status", "Normal"),
                }
            )

        if rows_to_insert:
            sb.table("biomarkers").insert(rows_to_insert).execute()

    return report_id


def save_translation(
    report_id: str,
    lang: str,
    summary_json: dict[str, Any],
    client: Any | None = None,
) -> None:
    """Caches on-demand vernacular translation ('hi' or 'kn') for a report."""
    sb = client or get_supabase_client()
    if sb is None:
        raise RuntimeError("Database client is not available.")

    field_map = {
        "hi": "summary_hi",
        "kn": "summary_kn",
        "en": "summary_en",
    }
    field = field_map.get(lang, "summary_en")
    sb.table("reports").update({field: summary_json}).eq("id", report_id).execute()


def get_translation(
    report_id: str,
    lang: str,
    client: Any | None = None,
) -> dict[str, Any] | None:
    """Retrieves cached vernacular summary if present."""
    sb = client or get_supabase_client()
    if sb is None:
        return None

    res = sb.table("reports").select("*").eq("id", report_id).execute()
    if not res.data:
        return None

    report = res.data[0]
    field_map = {
        "hi": "summary_hi",
        "kn": "summary_kn",
        "en": "summary_en",
    }
    field = field_map.get(lang, "summary_en")
    val = report.get(field)
    return cast("dict[str, Any] | None", val)


def get_user_biomarkers(
    user_id: str, client: Any | None = None
) -> list[dict[str, Any]]:
    """Fetches historical biomarker readings for a user, ordered newest first."""
    sb = client or get_supabase_client()
    if sb is None:
        return []

    res = (
        sb.table("biomarkers")
        .select("*")
        .eq("user_id", user_id)
        .order("recorded_at", desc=True)
        .execute()
    )
    if res.data:
        return cast(list[dict[str, Any]], res.data)
    return []


# ==============================================================================
# 4. Longitudinal Biomarker Trends & Delta Calculation
# ==============================================================================

# Biomarkers where lower is clinically improved
_LOWER_IS_BETTER: Final[set[str]] = {
    "hba1c",
    "glucose",
    "fasting blood sugar",
    "fbs",
    "postprandial blood sugar",
    "ppbs",
    "random blood sugar",
    "rbs",
    "creatinine",
    "serum creatinine",
    "uric acid",
    "serum uric acid",
    "bilirubin",
    "total bilirubin",
    "sgpt",
    "sgpt (alt)",
    "alt",
    "sgot",
    "sgot (ast)",
    "ast",
    "cholesterol",
    "total cholesterol",
    "triglycerides",
    "ldl",
    "ldl cholesterol",
}

# Biomarkers where higher is clinically improved
_HIGHER_IS_BETTER: Final[set[str]] = {
    "hemoglobin",
    "haemoglobin",
    "hb",
    "platelet",
    "platelets",
    "platelet count",
    "hdl",
    "hdl cholesterol",
    "rbc",
    "rbc count",
}


def _format_value_unit(val: float | int | str, unit: str | None) -> str:
    """Formats numeric values and units consistently with contract expectations."""
    if isinstance(val, float) and val.is_integer():
        num_str = str(int(val))
    else:
        num_str = str(val)

    if not unit:
        return num_str

    clean_unit = unit.strip()
    if clean_unit == "%":
        return f"{num_str}%"
    return f"{num_str} {clean_unit}"


def compute_deltas(
    current_rows: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[str]:
    """Computes trend deltas between current and historical biomarker rows.

    Example output: 'HbA1c: 8.4% -> 7.8% (improved)'
    """
    if not current_rows or not history:
        return []

    # Map latest historical record per lower-case test name
    history_by_test: dict[str, dict[str, Any]] = {}
    for h in sorted(history, key=lambda x: str(x.get("recorded_at", "")), reverse=True):
        name_key = str(h.get("test_name", "")).strip().lower()
        if name_key and name_key not in history_by_test:
            history_by_test[name_key] = h

    deltas: list[str] = []

    for curr in current_rows:
        test_name = str(curr.get("test_name", "")).strip()
        curr_val = curr.get("observed_value")
        if not test_name or curr_val is None:
            continue

        try:
            c_val_float = float(curr_val)
        except (ValueError, TypeError):
            continue

        name_key = test_name.lower()
        hist = history_by_test.get(name_key)
        if not hist:
            continue

        prev_val = hist.get("observed_value")
        if prev_val is None:
            continue

        try:
            p_val_float = float(prev_val)
        except (ValueError, TypeError):
            continue

        unit = curr.get("unit") or hist.get("unit")
        prev_str = _format_value_unit(p_val_float, unit)
        curr_str = _format_value_unit(c_val_float, unit)

        # Determine clinical directional assessment
        is_lower_better = any(k in name_key for k in _LOWER_IS_BETTER)
        is_higher_better = any(k in name_key for k in _HIGHER_IS_BETTER)

        if c_val_float == p_val_float:
            status = "unchanged"
        elif is_lower_better:
            status = "improved" if c_val_float < p_val_float else "increased"
        elif is_higher_better:
            status = "improved" if c_val_float > p_val_float else "decreased"
        else:
            status = "increased" if c_val_float > p_val_float else "decreased"

        deltas.append(f"{test_name}: {prev_str} -> {curr_str} ({status})")

    return deltas


# ==============================================================================
# 5. DPDP Act 2023 Permanent Cascade Erasure (/delete)
# ==============================================================================


def delete_user_data(
    chat_id: int | None = None,
    user_id: str | None = None,
    client: Any | None = None,
) -> bool:
    """Executes statutory DPDP permanent data erasure.

    Triggers SQL DELETE on users row. PostgreSQL ON DELETE CASCADE guarantees
    all associated reports and biomarkers are immediately hard-deleted.
    """
    sb = client or get_supabase_client()
    if sb is None:
        raise RuntimeError("Database client is not available.")

    query = sb.table("users").delete()
    if chat_id is not None:
        res = query.eq("telegram_chat_id", chat_id).execute()
    elif user_id is not None:
        res = query.eq("id", user_id).execute()
    else:
        raise ValueError("Either chat_id or user_id must be provided to delete.")

    return bool(res.data and len(res.data) > 0)
