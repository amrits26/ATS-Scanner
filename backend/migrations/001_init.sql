-- =============================================================================
-- IntelliResume AI — PostgreSQL Schema
-- File: backend/migrations/001_init.sql
--
-- HOW TO RUN:
--   Supabase: paste into the SQL Editor at app.supabase.com → SQL Editor → New Query
--   Raw psql: psql $DATABASE_URL -f backend/migrations/001_init.sql
--
-- SAFE TO RE-RUN: All statements use IF NOT EXISTS / CREATE OR REPLACE.
-- =============================================================================

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- ENUMs
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE user_tier AS ENUM ('free', 'pro');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE subscription_status AS ENUM (
        'active', 'trialing', 'canceled', 'past_due', 'unpaid'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE analysis_status AS ENUM (
        'pending', 'processing', 'completed', 'failed'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Links to Supabase auth.users.id (populated after Supabase Auth JWT verification)
    supabase_user_id      VARCHAR(255) UNIQUE NOT NULL,
    email                 VARCHAR(255) UNIQUE NOT NULL,
    full_name             VARCHAR(255),

    -- Monetization -------------------------------------------------------
    tier                  user_tier           NOT NULL DEFAULT 'free',
    stripe_customer_id    VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    subscription_status   subscription_status,

    -- Rate limiting -------------------------------------------------------
    -- free tier: 3 scans/month | pro: -1 = unlimited
    scans_this_month      INT  NOT NULL DEFAULT 0,
    scan_limit            INT  NOT NULL DEFAULT 3,
    scan_reset_date       DATE,            -- API resets count on this date

    -- Timestamps ----------------------------------------------------------
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- analysis_results
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS analysis_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- NULL-able: anonymous scans allowed (won't show in history, but still cached)
    user_id           UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Public-facing polling key returned as 202 Accepted
    session_id        VARCHAR(255) UNIQUE NOT NULL,

    status            analysis_status NOT NULL DEFAULT 'pending',

    resume_filename   VARCHAR(500),

    -- SHA-256 of raw resume text + JD text — used for 24-hour result cache
    resume_text_hash  VARCHAR(64),
    jd_text_hash      VARCHAR(64),

    -- Full ComprehensiveAnalysisResult serialized as JSONB.
    -- Free-tier responses have optimized_resume / skill_gap / docx stubbed out.
    result_json       JSONB,

    error_message     TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Hash-based cache lookup: find a completed result for the same inputs < 24 h ago
CREATE INDEX IF NOT EXISTS idx_analysis_cache
    ON analysis_results (resume_text_hash, jd_text_hash, status, created_at);

-- Per-user history: most recent first
CREATE INDEX IF NOT EXISTS idx_analysis_user_history
    ON analysis_results (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- Fast session-id polling
CREATE INDEX IF NOT EXISTS idx_analysis_session
    ON analysis_results (session_id);

-- ---------------------------------------------------------------------------
-- updated_at auto-update trigger
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_updated_at        ON users;
DROP TRIGGER IF EXISTS trg_analysis_updated_at     ON analysis_results;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_analysis_updated_at
    BEFORE UPDATE ON analysis_results
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ---------------------------------------------------------------------------
-- Row Level Security (Supabase best practice)
-- Enable RLS so that Supabase's anon / service_role keys respect ownership.
-- Application reads via the service_role key (bypasses RLS), so these
-- policies protect direct client access only.
-- ---------------------------------------------------------------------------

ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_results ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Only applied when running on Supabase (auth schema present).
-- Local PostgreSQL (pgAdmin) skips these safely.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
        -- Users can only read/update their own row
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'users: owner access'
        ) THEN
            EXECUTE $p$
                CREATE POLICY "users: owner access"
                    ON users FOR ALL
                    USING (supabase_user_id = auth.uid()::text)
            $p$;
        END IF;

        -- Users can only read their own analyses
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE tablename = 'analysis_results' AND policyname = 'analysis: owner read'
        ) THEN
            EXECUTE $p$
                CREATE POLICY "analysis: owner read"
                    ON analysis_results FOR SELECT
                    USING (
                        user_id = (
                            SELECT id FROM users WHERE supabase_user_id = auth.uid()::text
                        )
                    )
            $p$;
        END IF;
    ELSE
        RAISE NOTICE 'Supabase auth schema not found — skipping RLS policies (local dev mode).';
    END IF;
END $$;
