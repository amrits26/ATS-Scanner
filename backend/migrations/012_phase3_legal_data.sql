-- backend/migrations/012_phase3_legal_data.sql
-- Phase 3: User-generated interview marketplace + trending skills tracking

BEGIN;

-- User Interview Submissions Table
-- Tracks user contributions to public Q&A bank
CREATE TABLE IF NOT EXISTS user_interview_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company VARCHAR(100) NOT NULL,
    role VARCHAR(100) NOT NULL,
    questions JSONB NOT NULL, -- [{question: string, answer: string}, ...]
    outcome VARCHAR(20), -- offer, rejected, pending
    difficulty INT CHECK (difficulty BETWEEN 1 AND 5),
    status VARCHAR(20) DEFAULT 'pending_review', -- pending_review, approved, rejected
    reviewer_notes TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_interview_submissions_company ON user_interview_submissions(company);
CREATE INDEX idx_interview_submissions_role ON user_interview_submissions(company, role);
CREATE INDEX idx_interview_submissions_status ON user_interview_submissions(status);
CREATE INDEX idx_interview_submissions_user_id ON user_interview_submissions(user_id);
CREATE INDEX idx_interview_submissions_created ON user_interview_submissions(created_at DESC);

-- Interview Questions Bank (Public)
-- Add new fields to existing table if not present
ALTER TABLE IF EXISTS interview_questions_bank
ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS submitted_by UUID REFERENCES users(id),
ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual'; -- manual, user_submitted, api

-- Trending Skills Table
-- Tracks skill demand from HN and other sources
CREATE TABLE IF NOT EXISTS trending_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(100) NOT NULL,
    demand_percentage NUMERIC(5, 2), -- 0-100%
    job_count INT,
    month VARCHAR(7), -- YYYY-MM format
    source VARCHAR(50), -- hn_whoishiring, linkedin, etc
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_trending_skills_skill ON trending_skills(skill_name);
CREATE INDEX idx_trending_skills_month ON trending_skills(month);
CREATE INDEX idx_trending_skills_demand ON trending_skills(demand_percentage DESC);
CREATE UNIQUE INDEX idx_trending_skills_unique ON trending_skills(skill_name, month);

-- User Rewards Table
-- Track rewards for user contributions
CREATE TABLE IF NOT EXISTS user_rewards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    submission_id UUID REFERENCES user_interview_submissions(id),
    reward_type VARCHAR(50), -- stripe_credit, pro_days, badge
    amount_cents INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending_approval', -- pending_approval, claimed, expired
    claimed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_user_rewards_user_id ON user_rewards(user_id);
CREATE INDEX idx_user_rewards_status ON user_rewards(status);
CREATE INDEX idx_user_rewards_created ON user_rewards(created_at DESC);

-- Ensure interview_questions_bank has all needed fields
CREATE TABLE IF NOT EXISTS interview_questions_bank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company VARCHAR(100) NOT NULL,
    role VARCHAR(100),
    question TEXT NOT NULL,
    answer_example TEXT,
    difficulty INT CHECK (difficulty BETWEEN 1 AND 5),
    verified BOOLEAN DEFAULT false,
    submitted_by UUID REFERENCES users(id),
    source VARCHAR(50) DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_interview_questions_company ON interview_questions_bank(company);
CREATE INDEX IF NOT EXISTS idx_interview_questions_role ON interview_questions_bank(company, role);
CREATE INDEX IF NOT EXISTS idx_interview_questions_verified ON interview_questions_bank(verified);

COMMIT;
