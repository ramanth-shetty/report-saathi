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
