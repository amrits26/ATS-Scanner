-- =============================================================================
-- Phase 5: Recruiter Lead Generation
-- File: backend/migrations/005_phase5_recruiter_lead_gen.sql
--
-- Purpose:
-- - recruiter_candidate_queue: High-score candidates (ATS >= 85) ready for recruiters
-- - recruiter_unlock_purchases: $5 unlock transactions
-- - recruiter_hire_reports: $500 success fees
--
-- SAFE TO RE-RUN: Uses IF NOT EXISTS / ON CONFLICT
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Table 1: Recruiter Candidate Queue (High-Score Candidates)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recruiter_candidate_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_result_id UUID NOT NULL UNIQUE REFERENCES analysis_results(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ats_score FLOAT NOT NULL CHECK (ats_score >= 85),
    matched_skills TEXT[],
    missing_skills TEXT[],
    experience_years INTEGER,
    location_city VARCHAR(100),
    location_state VARCHAR(50),
    job_title_detected VARCHAR(200),
    resume_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_queue_score ON recruiter_candidate_queue(ats_score);
CREATE INDEX IF NOT EXISTS idx_queue_created ON recruiter_candidate_queue(created_at);
CREATE INDEX IF NOT EXISTS idx_queue_user ON recruiter_candidate_queue(user_id);

-- ============================================================================
-- Table 2: Recruiter Unlock Purchases ($5 fee)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recruiter_unlock_purchases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES recruiter_candidate_queue(id) ON DELETE CASCADE,
    recruiter_email VARCHAR(255) NOT NULL,
    stripe_session_id VARCHAR(255) UNIQUE NOT NULL,
    stripe_invoice_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    amount_cents INT DEFAULT 500,
    purchased_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(candidate_id, recruiter_email)
);

CREATE INDEX IF NOT EXISTS idx_unlocks_recruiter ON recruiter_unlock_purchases(recruiter_email);
CREATE INDEX IF NOT EXISTS idx_unlocks_status ON recruiter_unlock_purchases(status);
CREATE INDEX IF NOT EXISTS idx_unlocks_candidate ON recruiter_unlock_purchases(candidate_id);

-- ============================================================================
-- Table 3: Recruiter Hire Reports ($500 success fee)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recruiter_hire_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES recruiter_candidate_queue(id) ON DELETE CASCADE,
    recruiter_email VARCHAR(255) NOT NULL,
    hire_date DATE DEFAULT CURRENT_DATE,
    stripe_charge_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending_payment' CHECK (status IN ('pending_payment', 'paid', 'dispute')),
    amount_cents INT DEFAULT 50000,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(candidate_id, recruiter_email)
);

CREATE INDEX IF NOT EXISTS idx_hires_recruiter ON recruiter_hire_reports(recruiter_email);
CREATE INDEX IF NOT EXISTS idx_hires_status ON recruiter_hire_reports(status);

-- ============================================================================
-- Auto-Update Trigger for updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_recruiter_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_recruiter_candidate_queue_updated_at ON recruiter_candidate_queue;
CREATE TRIGGER update_recruiter_candidate_queue_updated_at
    BEFORE UPDATE ON recruiter_candidate_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_recruiter_queue_updated_at();
