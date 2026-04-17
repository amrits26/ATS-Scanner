-- Migration 016: Phase 8 – Autonomous Job Agents + Resume Architect
-- Adds: job_agents, job_agent_results, architect_sessions

-- -------------------------------------------------------------------------
-- job_agents: saved job search configs owned by a user
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_agents (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                 VARCHAR(255) NOT NULL,
    query                VARCHAR(500) NOT NULL,
    location             VARCHAR(255),
    country_code         CHAR(2)      NOT NULL DEFAULT 'US',
    visa_sponsorship     BOOLEAN      NOT NULL DEFAULT FALSE,
    remote_only          BOOLEAN      NOT NULL DEFAULT FALSE,
    salary_min           INTEGER,
    base_resume_text     TEXT,
    email_digest_enabled BOOLEAN      NOT NULL DEFAULT TRUE,
    frequency            VARCHAR(20)  NOT NULL DEFAULT 'daily',   -- daily | weekly
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    last_run_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_agents_user_id   ON job_agents(user_id);
CREATE INDEX IF NOT EXISTS idx_job_agents_is_active  ON job_agents(is_active);

-- -------------------------------------------------------------------------
-- job_agent_results: jobs discovered + (optionally) scored per agent run
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_agent_results (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_agent_id   UUID        NOT NULL REFERENCES job_agents(id) ON DELETE CASCADE,
    job_id         UUID        NOT NULL REFERENCES jobs(id)       ON DELETE CASCADE,
    match_score    FLOAT,
    match_tier     VARCHAR(50),
    missing_signals JSONB,
    was_emailed    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jar_job_agent_id ON job_agent_results(job_agent_id);
CREATE INDEX IF NOT EXISTS idx_jar_job_id       ON job_agent_results(job_id);
CREATE INDEX IF NOT EXISTS idx_jar_created_at   ON job_agent_results(created_at);

-- -------------------------------------------------------------------------
-- architect_sessions: interactive Resume Architect conversations
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS architect_sessions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id          UUID        NOT NULL REFERENCES jobs(id)  ON DELETE CASCADE,
    base_resume     TEXT        NOT NULL,
    gaps            JSONB,
    questions       JSONB,
    user_answers    JSONB,
    tailored_resume TEXT,
    status          VARCHAR(30) NOT NULL DEFAULT 'awaiting_input',  -- awaiting_input | complete
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_architect_sessions_user_id ON architect_sessions(user_id);

-- Auto-update updated_at
CREATE OR REPLACE TRIGGER trg_architect_sessions_updated_at
    BEFORE UPDATE ON architect_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
