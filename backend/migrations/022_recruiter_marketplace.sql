-- =============================================================================
-- Migration 022: Recruiter Marketplace
--
-- Adds subscription-based recruiter accounts, job postings, and candidate
-- matching for the B2B revenue pillar ($99/$299 per month).
--
-- This extends the existing Phase 5 tables (recruiter_candidate_queue,
-- recruiter_unlock_purchases, recruiter_hire_reports) with a proper
-- recruiter identity layer.
--
-- SAFE TO RE-RUN: Uses IF NOT EXISTS throughout.
-- =============================================================================

-- ============================================================================
-- Table 1: Recruiter Accounts (separate from job-seeker users)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recruiter_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    company_name VARCHAR(255),
    full_name VARCHAR(255),

    -- Auth: uses same Supabase JWT, identified by a role claim or separate lookup
    supabase_user_id VARCHAR(255) UNIQUE,

    -- Stripe billing
    stripe_customer_id VARCHAR(255),
    subscription_tier VARCHAR(50) NOT NULL DEFAULT 'free'
        CHECK (subscription_tier IN ('free', 'basic', 'pro')),
    subscription_status VARCHAR(50) NOT NULL DEFAULT 'inactive'
        CHECK (subscription_status IN ('inactive', 'active', 'trialing', 'canceled', 'past_due')),
    stripe_subscription_id VARCHAR(255),
    subscription_ends_at TIMESTAMPTZ,

    -- Usage tracking
    unlocks_this_month INT NOT NULL DEFAULT 0,
    unlock_reset_date DATE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recruiter_accounts_email
    ON recruiter_accounts (email);
CREATE INDEX IF NOT EXISTS idx_recruiter_accounts_supabase
    ON recruiter_accounts (supabase_user_id)
    WHERE supabase_user_id IS NOT NULL;

-- ============================================================================
-- Table 2: Recruiter Job Postings (for candidate matching)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recruiter_job_postings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recruiter_id UUID NOT NULL REFERENCES recruiter_accounts(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    parsed_keywords JSONB,         -- extracted skills / requirements
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recruiter_job_postings_recruiter
    ON recruiter_job_postings (recruiter_id);
CREATE INDEX IF NOT EXISTS idx_recruiter_job_postings_active
    ON recruiter_job_postings (is_active)
    WHERE is_active = true;

-- ============================================================================
-- Table 3: Candidate Matches (links analysis results to recruiter job postings)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recruiter_candidate_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recruiter_id UUID NOT NULL REFERENCES recruiter_accounts(id) ON DELETE CASCADE,
    job_posting_id UUID NOT NULL REFERENCES recruiter_job_postings(id) ON DELETE CASCADE,
    analysis_id UUID NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    match_score DECIMAL(5,2) NOT NULL CHECK (match_score >= 0 AND match_score <= 100),
    is_viewed BOOLEAN NOT NULL DEFAULT false,
    is_unlocked BOOLEAN NOT NULL DEFAULT false,
    unlocked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate matches for same job+analysis pair
    UNIQUE (job_posting_id, analysis_id)
);

CREATE INDEX IF NOT EXISTS idx_recruiter_matches_recruiter
    ON recruiter_candidate_matches (recruiter_id);
CREATE INDEX IF NOT EXISTS idx_recruiter_matches_job
    ON recruiter_candidate_matches (job_posting_id);
CREATE INDEX IF NOT EXISTS idx_recruiter_matches_score
    ON recruiter_candidate_matches (match_score DESC);
