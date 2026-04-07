-- =============================================================================
-- IntelliResume AI — Master Migration Script v7.0 (Ironclad)
-- Purpose: Complete PostgreSQL schema for Phases 1-3, optimized for pgAdmin 4
--
-- HOW TO USE IN pgAdmin 4:
-- 1. Open pgAdmin 4 → Select database "intelliresume_ai"
-- 2. Tools → Query Tool
-- 3. Copy entire script below (or save as .sql and open)
-- 4. Click Execute or Press F5
-- 5. Observe: "Query returned successfully with no result in X ms"
--
-- SAFE TO RE-RUN: All commands use IF NOT EXISTS / IF COLUMN EXISTS checks
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- 1. ENUMS (Create once, reusable across tables)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE user_tier AS ENUM ('free', 'pro');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE subscription_status AS ENUM ('active', 'trialing', 'canceled', 'past_due', 'unpaid');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE analysis_status AS ENUM ('pending', 'processing', 'completed', 'failed');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- ---------------------------------------------------------------------------
-- 2. CORE: users table (Phase 1 + Phase 2 extensions)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supabase_user_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    
    -- Monetization (Phase 1)
    tier user_tier NOT NULL DEFAULT 'free',
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    subscription_status subscription_status,
    
    -- Rate limiting (Phase 1)
    scans_this_month INT NOT NULL DEFAULT 0,
    scan_limit INT NOT NULL DEFAULT 3,
    scan_reset_date DATE,
    
    -- Phase 2: Timezone + Fear email tracking
    timezone VARCHAR(50) DEFAULT 'UTC',
    last_fear_email_sent_at TIMESTAMPTZ,
    upgrade_source VARCHAR(100),
    
    -- Phase 3: Email verification
    email_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMP,
    consent_marketing BOOLEAN DEFAULT FALSE,
    consent_legal BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for users
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_supabase_user_id ON users(supabase_user_id);
CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_users_timezone_tier ON users(timezone, tier, created_at)
    WHERE tier = 'free';

-- ---------------------------------------------------------------------------
-- 3. CORE: analysis_results table (Phase 1-3 all features)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    
    status analysis_status NOT NULL DEFAULT 'pending',
    resume_filename VARCHAR(500),
    
    -- Cache keys (SHA-256)
    resume_text_hash VARCHAR(64),
    jd_text_hash VARCHAR(64),
    
    -- Phase 1: Step tracking (Ironclad Fix progress)
    current_step INTEGER DEFAULT 0,
    step_message VARCHAR(255),
    progress_percent INTEGER DEFAULT 0,
    step_timestamps JSONB,
    retry_count INTEGER DEFAULT 0,
    
    -- Phase 2: Fear email tracking (Quiet Hours enforcement)
    fear_email_sent BOOLEAN DEFAULT FALSE,
    last_fear_email_at TIMESTAMPTZ,
    fear_deferral_count INTEGER DEFAULT 0,
    
    -- Phase 1: AI Quality Feedback (Ironclad Fix #3: Boolean type)
    user_feedback BOOLEAN,  -- True=helpful, False=not helpful (NOT Integer)
    feedback_reason VARCHAR(100),
    feedback_notes TEXT,
    feedback_at TIMESTAMPTZ,
    
    -- Phase 3: Referral + viral tracking
    og_image_url TEXT,
    shared_at TIMESTAMPTZ,
    share_token VARCHAR(255) UNIQUE,
    referrer_scan_id UUID,
    
    -- Result cache (full analysis JSON)
    result_json JSONB,
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for analysis_results (Performance)
CREATE INDEX IF NOT EXISTS idx_analysis_user_id ON analysis_results(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_session_id ON analysis_results(session_id);
CREATE INDEX IF NOT EXISTS idx_analysis_cache ON analysis_results(resume_text_hash, jd_text_hash, status, created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_share_token ON analysis_results(share_token);
CREATE INDEX IF NOT EXISTS idx_analysis_fear_loop ON analysis_results(user_id, fear_email_sent, created_at DESC)
    WHERE fear_email_sent = FALSE AND status = 'completed';

-- ---------------------------------------------------------------------------
-- 4. PHASE 2: Stripe Webhook Deduplication (Race-condition proof)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS processed_stripe_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_event_id VARCHAR(255) UNIQUE NOT NULL,  -- Deduplication key
    event_type VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    webhook_body JSONB
);

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    stripe_customer_id VARCHAR(255),
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    webhook_body JSONB
);

-- Indexes for Stripe tables
CREATE INDEX IF NOT EXISTS idx_processed_stripe_events_event_id ON processed_stripe_events(stripe_event_id);
CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_event_id ON stripe_webhook_events(stripe_event_id);

-- ---------------------------------------------------------------------------
-- 5. PHASE 2: Email Dead-Letter Queue (Resend reliability)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS failed_email_retry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_to VARCHAR(255) NOT NULL,
    email_type VARCHAR(50) NOT NULL,  -- 'fear_loop', 'welcome', 'upgrade', etc.
    subject TEXT,
    body TEXT,
    retry_count INT DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failed_email_retry_email_to ON failed_email_retry(email_to);
CREATE INDEX IF NOT EXISTS idx_failed_email_retry_retry_count ON failed_email_retry(retry_count);

-- ---------------------------------------------------------------------------
-- 6. PHASE 3: Free Scan Tracking (Idempotency + 1-per-day rate limit)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS free_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    resume_hash VARCHAR(64) NOT NULL,
    scan_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Lightweight analysis
    score INTEGER NOT NULL,
    keywords JSONB DEFAULT '[]'::jsonb,
    
    -- Consent & metadata
    consent_given BOOLEAN DEFAULT FALSE,
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Fear loop tracking (Phase 2)
    fear_email_sent BOOLEAN DEFAULT FALSE,
    fear_email_sent_at TIMESTAMPTZ,
    
    -- Viral tracking (Phase 3)
    referrer_scan_id UUID,
    
    -- Conversion
    promo_code VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- CONSTRAINT: 1 scan per email+resume per day (DB-level rate limit)
    CONSTRAINT unique_free_scan_per_day UNIQUE(email, resume_hash, scan_date)
);

-- Indexes for free_scans (Performance)
CREATE INDEX IF NOT EXISTS idx_free_scans_email ON free_scans(email);
CREATE INDEX IF NOT EXISTS idx_free_scans_score ON free_scans(score);
CREATE INDEX IF NOT EXISTS idx_free_scans_scan_date ON free_scans(scan_date);
CREATE INDEX IF NOT EXISTS idx_free_scans_fear_sent ON free_scans(fear_email_sent);

-- ---------------------------------------------------------------------------
-- 7. PHASE 3: Email Bounce Handling
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS email_bounces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    bounce_type VARCHAR(50),  -- 'permanent', 'temporary', 'complaint'
    bounce_reason TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_bounces_email ON email_bounces(email);

-- ---------------------------------------------------------------------------
-- 8. PHASE 3: Referral Tracking (Viral coefficient K-Factor)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_scan_id UUID NOT NULL UNIQUE,
    referrer_email VARCHAR(255) NOT NULL,
    referred_email VARCHAR(255),
    
    -- Viral counter: K = conversions ÷ shares
    shares_count INTEGER DEFAULT 0,
    clicks_count INTEGER DEFAULT 0,
    conversions_count INTEGER DEFAULT 0,
    
    -- Event metadata
    event_type VARCHAR(50) NOT NULL,  -- 'share', 'click', 'signup', 'convert'
    event_metadata JSONB,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_events_referrer ON referral_events(referrer_email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_events_referred ON referral_events(referred_email)
    WHERE referred_email IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 9. PHASE 3: Referral Discount Codes
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_discounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,
    discount_percent INTEGER NOT NULL,
    referrer_email VARCHAR(255) NOT NULL,
    
    max_uses INTEGER,
    uses INTEGER DEFAULT 0,
    valid_until TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_discounts_code ON referral_discounts(code);
CREATE INDEX IF NOT EXISTS idx_referral_discounts_referrer ON referral_discounts(referrer_email);

-- ---------------------------------------------------------------------------
-- VERIFICATION: Print table structure (pgAdmin 4 only)
-- ---------------------------------------------------------------------------
-- Run this query after the migration to verify all tables exist:

/*
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema='public' 
  AND table_name IN (
    'users', 'analysis_results', 'processed_stripe_events', 
    'free_scans', 'email_bounces', 'referral_events', 'referral_discounts'
  )
ORDER BY table_name;
*/

-- =============================================================================
-- DIAGNOSTIC QUERIES (Run these after migration to verify)
-- =============================================================================

/*
-- Check all indexes
SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY indexname;

-- Check users table structure
\d users

-- Check analysis_results table structure
\d analysis_results

-- Check all constraints
SELECT constraint_name, table_name, constraint_type 
FROM information_schema.table_constraints 
WHERE table_schema='public' 
ORDER BY table_name;
*/

-- =============================================================================
-- END OF MASTER MIGRATION SCRIPT
-- Status: Ready for production deployment
-- Last updated: April 6, 2026
-- =============================================================================
