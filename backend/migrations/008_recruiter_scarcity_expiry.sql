-- Add 7-day expiration tracking to recruiter candidate queue
-- Enables FOMO-based scarcity messaging for higher conversion
-- Date: April 9, 2026

-- 1. Add expires_at column
ALTER TABLE recruiter_candidate_queue 
ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '7 days');

-- 2. Set expiration for existing pending rows (if not already set)
UPDATE recruiter_candidate_queue 
SET expires_at = COALESCE(expires_at, NOW() + INTERVAL '7 days')
WHERE expires_at IS NULL;

-- 3. Performance index for active candidate queries
CREATE INDEX IF NOT EXISTS idx_recruiter_queue_expires_active 
ON recruiter_candidate_queue (expires_at DESC) 
WHERE status = 'pending';

-- 4. View: Only active (pending, non-expired) candidates
CREATE OR REPLACE VIEW recruiter_active_candidates AS
SELECT * FROM recruiter_candidate_queue
WHERE status = 'pending' 
  AND (expires_at IS NULL OR expires_at > NOW());

-- 5. Analytics table for scarcity A/B testing
CREATE TABLE IF NOT EXISTS recruiter_scarcity_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recruiter_email VARCHAR(255) NOT NULL,
    candidate_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    candidate_count_at_time INTEGER,
    message_variant VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scarcity_events_recruiter 
ON recruiter_scarcity_events (recruiter_email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scarcity_events_type 
ON recruiter_scarcity_events (event_type);

-- 6. Add status column if missing (should exist, but just in case)
ALTER TABLE recruiter_candidate_queue
ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';
