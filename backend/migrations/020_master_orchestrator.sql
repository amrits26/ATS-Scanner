-- ============================================================================
-- Migration 020: Master Orchestrator — user_journeys + job_application_outcomes
--
-- Supports:
--   - Full journey logging for DPO training
--   - Closed-loop outcome tracking (interview, offer, hired, rejected)
--   - Reward model training data
-- ============================================================================

-- ---------------------------------------------------------------------------
-- user_journeys: Complete orchestrator session recordings for DPO training
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_journeys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      VARCHAR(255) NOT NULL,
    journey_stage   VARCHAR(50) NOT NULL DEFAULT 'new',  -- new, scanning, optimizing, preparing, applied, interviewing, offer, hired

    -- The orchestrator's action plan (JSON array of steps)
    action_plan     JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Full event log: every step start/complete/fail/feedback
    journey_events  JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Consolidated final response from the orchestrator
    final_response  JSONB,

    -- Aggregated metrics for fast querying
    steps_completed     INTEGER NOT NULL DEFAULT 0,
    steps_failed        INTEGER NOT NULL DEFAULT 0,
    overall_confidence  FLOAT NOT NULL DEFAULT 0.0,
    total_cost_cents    INTEGER NOT NULL DEFAULT 0,
    execution_time_seconds FLOAT NOT NULL DEFAULT 0.0,

    -- DPO training labels (populated by outcome feedback or manual annotation)
    dpo_label       VARCHAR(20),  -- 'chosen', 'rejected', NULL (unlabeled)
    dpo_pair_id     UUID,         -- Links chosen↔rejected pairs

    -- Context snapshot for pairing (extracted from resume + JD)
    context_embedding_hash VARCHAR(64),  -- SHA256 of context for similarity matching

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for DPO data preparation queries
CREATE INDEX IF NOT EXISTS idx_user_journeys_user_id ON user_journeys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_journeys_session_id ON user_journeys(session_id);
CREATE INDEX IF NOT EXISTS idx_user_journeys_stage ON user_journeys(journey_stage);
CREATE INDEX IF NOT EXISTS idx_user_journeys_dpo_label ON user_journeys(dpo_label) WHERE dpo_label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_journeys_created_at ON user_journeys(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_journeys_steps_completed ON user_journeys(steps_completed) WHERE steps_completed >= 2;


-- ---------------------------------------------------------------------------
-- job_application_outcomes: Closed-loop feedback on real-world results
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_application_outcomes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    journey_id      UUID REFERENCES user_journeys(id) ON DELETE SET NULL,

    -- Link to the job (if tracked)
    job_id          UUID REFERENCES jobs(id) ON DELETE SET NULL,
    job_title       VARCHAR(500),
    company_name    VARCHAR(500),

    -- Outcome
    outcome         VARCHAR(30) NOT NULL,  -- applied, interview, offer, hired, rejected, ghosted, abandoned
    outcome_details JSONB,                 -- Free-form: interview_date, offer_amount, rejection_reason, etc.

    -- Snapshot of AI state at time of application (for reward model training)
    resume_snapshot     TEXT,              -- Resume text used for this application
    jd_snapshot         TEXT,              -- Job description text
    ats_score_at_apply  FLOAT,            -- ATS score when user applied
    agents_used         JSONB,            -- ["tailor", "coach", "interview"]
    agent_outputs       JSONB,            -- Condensed outputs from each agent

    -- User self-report
    user_satisfaction   INTEGER,          -- 1-5: How helpful was the AI?
    user_notes          TEXT,             -- Free-text feedback

    -- Timing
    applied_at          TIMESTAMPTZ,      -- When the user submitted the application
    outcome_reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Reward model score (computed after training)
    reward_score        FLOAT,            -- Predicted success probability from reward model

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for outcome analysis and reward model training
CREATE INDEX IF NOT EXISTS idx_jao_user_id ON job_application_outcomes(user_id);
CREATE INDEX IF NOT EXISTS idx_jao_journey_id ON job_application_outcomes(journey_id);
CREATE INDEX IF NOT EXISTS idx_jao_outcome ON job_application_outcomes(outcome);
CREATE INDEX IF NOT EXISTS idx_jao_outcome_reported ON job_application_outcomes(outcome_reported_at DESC);
CREATE INDEX IF NOT EXISTS idx_jao_reward_score ON job_application_outcomes(reward_score) WHERE reward_score IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Trigger: auto-update updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_journeys_updated_at ON user_journeys;
CREATE TRIGGER trg_user_journeys_updated_at
    BEFORE UPDATE ON user_journeys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_jao_updated_at ON job_application_outcomes;
CREATE TRIGGER trg_jao_updated_at
    BEFORE UPDATE ON job_application_outcomes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
