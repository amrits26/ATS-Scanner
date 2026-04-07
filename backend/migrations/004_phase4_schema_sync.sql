-- =============================================================================
-- Phase 4: Schema Sync — PostgreSQL Migration (v7.0 Ironclad)
-- File: backend/migrations/004_phase4_schema_sync.sql
--
-- Purpose: Sync db_models.py → PostgreSQL schema
-- - Phase 1 analysis_results: step tracking + progress + retry logic
-- - Phase 1 AI feedback: Boolean user_feedback + reason + notes
-- - Phase 3 referral: share_token + og_image_url + shared_at
-- - Viral tracking tables: free_scans, referral_shares, referral_discounts
--
-- SAFE TO RE-RUN: Uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. analysis_results: Add Phase 1 step tracking columns
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS current_step INTEGER DEFAULT 0;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS step_message VARCHAR(255);

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS progress_percent INTEGER DEFAULT 0;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS step_timestamps JSONB;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;

-- ---------------------------------------------------------------------------
-- 2. analysis_results: Add Phase 2 fear tracking (if not already added)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS fear_email_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS last_fear_email_at TIMESTAMPTZ;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS fear_deferral_count INTEGER DEFAULT 0;

-- ---------------------------------------------------------------------------
-- 3. analysis_results: Add Phase 1 AI Quality Feedback (Ironclad Fix #3)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS user_feedback BOOLEAN;  -- True=helpful, False=not helpful

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS feedback_reason VARCHAR(100);  -- "too_low", "too_high", etc.

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS feedback_notes TEXT;  -- Free text

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMPTZ;  -- When submitted

-- ---------------------------------------------------------------------------
-- 4. analysis_results: Add Phase 3 referral/viral columns
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS og_image_url TEXT;  -- LinkedIn OG image

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS shared_at TIMESTAMPTZ;  -- When shared

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS share_token VARCHAR(255) UNIQUE;  -- Public share link

-- Create index for share token
CREATE INDEX IF NOT EXISTS idx_analysis_share_token
    ON analysis_results (share_token);

-- ---------------------------------------------------------------------------
-- 5. free_scans: Add missing columns for Phase 3 viral tracking
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS free_scans
ADD COLUMN IF NOT EXISTS scan_date DATE DEFAULT CURRENT_DATE;  -- For daily idempotency

-- ---------------------------------------------------------------------------
-- 6. Referral System Tables (Phase 3: Viral Hook)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Referrer (who shared)
    referrer_scan_id UUID NOT NULL UNIQUE,
    referrer_email VARCHAR(255) NOT NULL,
    
    -- Referred (who clicked)
    referred_email VARCHAR(255),
    
    -- Viral tracking: shares → clicks → signups → conversions
    shares_count INTEGER DEFAULT 1,
    clicks_count INTEGER DEFAULT 0,
    conversions_count INTEGER DEFAULT 0,
    
    -- Event metadata
    event_type VARCHAR(50) NOT NULL,  -- 'share', 'click', 'signup', 'convert'
    event_metadata JSONB,  -- Custom metadata
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    FOREIGN KEY (referrer_scan_id) REFERENCES analysis_results(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_referral_events_referrer
    ON referral_events (referrer_email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_referral_events_referred
    ON referral_events (referred_email, created_at DESC)
    WHERE referred_email IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 7. Discount Codes (Phase 3: Viral referral incentives)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_discounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    code VARCHAR(20) NOT NULL UNIQUE,
    discount_percent INTEGER NOT NULL,
    referrer_email VARCHAR(255) NOT NULL,
    
    max_uses INTEGER,
    uses INTEGER DEFAULT 0,
    
    valid_until TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_discounts_code
    ON referral_discounts (code);

-- ---------------------------------------------------------------------------
-- All Schema Updates Complete
-- =============================================================================
