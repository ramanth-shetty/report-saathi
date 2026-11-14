-- ==============================================================================
-- ReportSaathi Database DDL: Supabase PostgreSQL Schema & Row Level Security
-- Task PR-02 (Docs: docs/06-architecture.md, Rule 03: .agents/03-database-and-telegram.md)
-- ==============================================================================

-- 1. Cryptographic Extensions for UUID Generation
create extension if not exists "pgcrypto";

-- ==============================================================================
-- 2. Users Table
-- Stores minimal session identifiers and DPDP Act 2023 consent records.
-- No patient names, phone numbers, or residential addresses are ever stored.
-- ==============================================================================
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  telegram_chat_id bigint unique,
  email text unique,
  age int,
  biological_sex text,
  preferred_lang text default 'en' check (preferred_lang in ('en', 'hi', 'kn')),
  consent_at timestamptz,
  created_at timestamptz default now()
);

-- ==============================================================================
-- 3. Reports Table
-- Stores scrubbed JSON summaries and multilingual cached translations.
-- Linked to users via user_id with ON DELETE CASCADE for DPDP compliance.
-- ==============================================================================
create table if not exists reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  report_hash text not null,
  report_date date default current_date,
  urgency_level text check (urgency_level in ('Routine', 'Consult Soon', 'Prompt Attention')),
  summary_en jsonb not null,
  summary_hi jsonb,
  summary_kn jsonb,
  created_at timestamptz default now(),
  unique (user_id, report_hash)
);

-- ==============================================================================
-- 4. Biomarkers Table
-- Stores individual lab parameters extracted from reports for trend calculations.
-- Cascades on user or report deletion.
-- ==============================================================================
create table if not exists biomarkers (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  test_name text not null,
  observed_value numeric,
  unit text,
  ref_range text,
  status text check (status in ('Normal', 'Low', 'High', 'Borderline')),
  recorded_at date default current_date
);

-- ==============================================================================
-- 5. Performance Indexes
-- Compound index for O(1) deduplication cache hits by report hash
create index if not exists idx_reports_user_hash on reports (user_id, report_hash);

-- Compound index for fast historical trend lookups (case-insensitive test name)
create index if not exists idx_biomarkers_user_test on biomarkers (user_id, lower(test_name), recorded_at desc);

-- ==============================================================================
-- 6. Row Level Security (RLS) Configuration
-- Restricts all access to the backend server possessing SUPABASE_SERVICE_KEY.
-- By enabling RLS without public policies, all anonymous and authenticated client
-- requests from the internet are strictly denied by default.
-- ==============================================================================
alter table users enable row level security;
alter table reports enable row level security;
alter table biomarkers enable row level security;

-- Optional policy cleanup: drop existing public policies if re-running
drop policy if exists "Deny all public access on users" on users;
drop policy if exists "Deny all public access on reports" on reports;
drop policy if exists "Deny all public access on biomarkers" on biomarkers;
