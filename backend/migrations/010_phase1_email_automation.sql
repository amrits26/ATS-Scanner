-- Phase 1: Email Automation Tables
-- Created: 2026-04-08

-- ====================================================================
-- nudge_tracking - Track all nudge emails (fear, abandoned, digest)
-- ====================================================================

CREATE TABLE IF NOT EXISTS nudge_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analysis_session_id VARCHAR(255) NOT NULL,
    
    -- What type of nudge
    nudge_type VARCHAR(50) NOT NULL CHECK (nudge_type IN ('fear', 'abandoned', 'digest')),
    
    -- Scheduling & delivery
    scheduled_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,  -- Upgraded after this email
    
    -- Email content
    email_subject TEXT,
    template_id VARCHAR(100),  -- Resend template ID
    
    -- Cost tracking
    gemini_cost_cents DECIMAL(10, 2) DEFAULT 0.00,
    resend_cost_cents DECIMAL(10, 2) DEFAULT 0.01,  -- Resend charges per email
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for efficient querying
CREATE INDEX idx_nudge_user_id ON nudge_tracking(user_id);
CREATE INDEX idx_nudge_scheduled ON nudge_tracking(scheduled_at) 
    WHERE sent_at IS NULL;
CREATE INDEX idx_nudge_converted ON nudge_tracking(converted_at) 
    WHERE converted_at IS NOT NULL;
CREATE INDEX idx_nudge_type ON nudge_tracking(nudge_type, created_at DESC);

-- ====================================================================
-- gemini_cost_log - Track all Gemini API calls for cost monitoring
-- ====================================================================

CREATE TABLE IF NOT EXISTS gemini_cost_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- What operation used Gemini
    operation_type VARCHAR(50),  -- 'fear_email', 'coach_response', 'tailor_rewrite', etc
    
    -- Token usage (for cost calculation)
    tokens_input INT,
    tokens_output INT,
    
    -- Cost
    cost_cents DECIMAL(10, 2),  -- Calculated cost in cents
    
    -- Context
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id VARCHAR(255),  -- Link to analysis or agent session
    
    -- Error tracking
    error_message TEXT,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for cost analysis
CREATE INDEX idx_gemini_operation ON gemini_cost_log(operation_type);
CREATE INDEX idx_gemini_user ON gemini_cost_log(user_id, created_at DESC);
CREATE INDEX idx_gemini_daily_cost ON gemini_cost_log(DATE(created_at), operation_type);

-- ====================================================================
-- Grant permissions (for Supabase RLS if applicable)
-- ====================================================================

ALTER TABLE nudge_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE gemini_cost_log ENABLE ROW LEVEL SECURITY;

-- Users can only see their own nudges
CREATE POLICY "Users see own nudges" ON nudge_tracking
    FOR SELECT USING (user_id = auth.uid());

-- Only admins see cost logs
CREATE POLICY "Cost logs admin only" ON gemini_cost_log
    FOR ALL USING (auth.role() = 'admin');
