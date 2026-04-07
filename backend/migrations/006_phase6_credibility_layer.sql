-- =============================================================================
-- Phase 6: Credibility Layer — Percentile Ranking & Confidence Scoring
-- Purpose: Add fields to show users where they rank and how confident the AI is
-- =============================================================================

-- Add columns to analysis_results table if they don't exist
ALTER TABLE analysis_results
ADD COLUMN IF NOT EXISTS percentile_rank FLOAT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS confidence_score FLOAT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS algorithm_breakdown JSONB DEFAULT NULL,
ADD COLUMN IF NOT EXISTS keyword_impact_data JSONB DEFAULT NULL;

-- Create index for percentile queries (used for calculating rankings)
CREATE INDEX IF NOT EXISTS idx_analysis_score_created ON analysis_results(
    (result_json -> 'ats_score' -> 'final_ats_score'),
    created_at DESC
) WHERE status = 'completed' AND user_id IS NOT NULL;

-- Track benchmarks per industry (for future use)
CREATE TABLE IF NOT EXISTS score_benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    industry VARCHAR(100) NOT NULL,
    job_title VARCHAR(100) NOT NULL,
    percentile FLOAT NOT NULL,
    score FLOAT NOT NULL,
    sample_size INT DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_benchmarks_industry_job ON score_benchmarks(industry, job_title);
