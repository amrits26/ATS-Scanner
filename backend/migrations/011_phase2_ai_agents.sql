-- Phase 2: AI Agents Tables
-- Created: 2026-04-08

-- ====================================================================
-- agent_executions - Track all agent runs
-- ====================================================================
CREATE TABLE IF NOT EXISTS agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL CHECK (agent_type IN ('coach', 'tailor', 'interview')),
    session_id VARCHAR(255) NOT NULL,
    user_goal TEXT,
    tools_called JSONB DEFAULT '[]'::jsonb,
    execution_time_seconds FLOAT,
    gemini_input_tokens INT DEFAULT 0,
    gemini_output_tokens INT DEFAULT 0,
    gemini_cost_cents DECIMAL(10, 2) DEFAULT 0.00,
    user_rating INT CHECK (user_rating >= 1 AND user_rating <= 5),
    feedback_text TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_agent_executions_user ON agent_executions(user_id, created_at DESC);
CREATE INDEX idx_agent_executions_type ON agent_executions(agent_type);
CREATE INDEX idx_agent_executions_session ON agent_executions(session_id);

-- ====================================================================
-- agent_subscriptions - Track user access to agents
-- ====================================================================
CREATE TABLE IF NOT EXISTS agent_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL CHECK (agent_type IN ('coach', 'tailor', 'interview')),
    tier_level VARCHAR(50) NOT NULL DEFAULT 'free',
    sessions_remaining INT DEFAULT 1,  -- -1 = unlimited
    last_reset_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_agent_subs_user ON agent_subscriptions(user_id);
CREATE INDEX idx_agent_subs_expires ON agent_subscriptions(expires_at) WHERE expires_at IS NOT NULL;

-- ====================================================================
-- job_description_cache - Cache scraped JDs to avoid re-scraping
-- ====================================================================
CREATE TABLE IF NOT EXISTS job_description_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA256 of URL
    url TEXT NOT NULL,
    job_description TEXT NOT NULL,
    source VARCHAR(50),
    scraped_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT now() + interval '7 days'
);

CREATE INDEX idx_jd_cache_hash ON job_description_cache(url_hash);
CREATE INDEX idx_jd_cache_expires ON job_description_cache(expires_at);
