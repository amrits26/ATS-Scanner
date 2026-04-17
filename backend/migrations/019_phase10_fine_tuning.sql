-- Migration 019: Phase 10 – Fine-Tuning Pipeline
-- Adds tables for tracking fine-tuning jobs and model deployments.

-- ============================================================================
-- fine_tuning_jobs: lifecycle tracking for each LoRA fine-tuning run
-- ============================================================================
CREATE TABLE IF NOT EXISTS fine_tuning_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider        VARCHAR(50) NOT NULL,          -- together, replicate, openai
    base_model      VARCHAR(100) NOT NULL,         -- e.g. meta-llama/Llama-3.2-3B-Instruct
    agent_type      VARCHAR(50) NOT NULL,          -- coach, tailor, interview, etc.

    status          VARCHAR(30) NOT NULL DEFAULT 'pending',
    provider_job_id VARCHAR(200),
    fine_tuned_model_id VARCHAR(200),

    training_file_url TEXT,
    examples_count  INTEGER DEFAULT 0,

    hyperparameters JSONB,
    training_metrics JSONB,
    cost_usd        DOUBLE PRECISION,
    error_message   TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,

    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    is_active       BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_ft_job_status     ON fine_tuning_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ft_job_agent_type ON fine_tuning_jobs(agent_type);

-- ============================================================================
-- model_deployments: which fine-tuned model is live for each agent type
-- ============================================================================
CREATE TABLE IF NOT EXISTS model_deployments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fine_tuning_job_id  UUID NOT NULL REFERENCES fine_tuning_jobs(id) ON DELETE CASCADE,
    agent_type          VARCHAR(50) NOT NULL,
    model_id            VARCHAR(200) NOT NULL,
    provider            VARCHAR(50) NOT NULL,

    deployment_type     VARCHAR(20) NOT NULL DEFAULT 'primary',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    rollout_percentage  INTEGER NOT NULL DEFAULT 100,  -- 1-100 for gradual A/B rollout

    deployed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_at      TIMESTAMPTZ,

    performance_metrics JSONB
);

CREATE INDEX IF NOT EXISTS idx_model_deployment_active ON model_deployments(agent_type, is_active);
