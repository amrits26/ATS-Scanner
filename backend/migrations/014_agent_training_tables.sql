-- 010_agent_training_tables.sql
-- Agent infrastructure: training examples, prompt weight tracking, RLHF signals

CREATE TABLE IF NOT EXISTS agent_training_examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(50) NOT NULL, -- tailor, coach, interview, matchmaker, negotiation
    input_text TEXT NOT NULL,
    output_text TEXT NOT NULL,
    rating INT CHECK (rating >= 0 AND rating <= 5), -- quality score: 0-5 stars
    is_synthetic BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT agent_training_examples_uq UNIQUE (agent_type, input_text, is_synthetic)
);

CREATE INDEX idx_agent_training_examples_agent_type ON agent_training_examples(agent_type);
CREATE INDEX idx_agent_training_examples_rating ON agent_training_examples(agent_type, rating DESC);


CREATE TABLE IF NOT EXISTS prompt_weights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(50) NOT NULL,
    prompt_template_id VARCHAR(100) NOT NULL, -- e.g., "tailor_v1", "tailor_v2"
    weight DECIMAL(5, 4) DEFAULT 1.0, -- 0.0-1.0, lower = deprecated
    avg_reward DECIMAL(10, 2) DEFAULT 0.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    week_number INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT prompt_weights_uq UNIQUE (agent_type, prompt_template_id, week_number)
);

CREATE INDEX idx_prompt_weights_agent_type ON prompt_weights(agent_type, weight DESC);
CREATE INDEX idx_prompt_weights_week ON prompt_weights(week_number DESC);


CREATE TABLE IF NOT EXISTS agent_decisions_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    decision_content JSONB, -- full context of agent's decision
    user_action VARCHAR(50), -- accept, reject, upgrade, purchase, ignore
    reward_points DECIMAL(10, 2) DEFAULT 0.0, -- signal mag: 0.5 (accept), 5.0 (upgrade), 10.0 (purchase)
    week_number INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_agent_decisions_log_user_id ON agent_decisions_log(user_id, created_at DESC);
CREATE INDEX idx_agent_decisions_log_agent_type ON agent_decisions_log(agent_type, week_number DESC);
CREATE INDEX idx_agent_decisions_log_reward ON agent_decisions_log(user_id, reward_points DESC);


-- Expand existing agent_executions table to support RLHF logging
ALTER TABLE agent_executions 
    ADD COLUMN IF NOT EXISTS user_action VARCHAR(50), -- filled by reward signal
    ADD COLUMN IF NOT EXISTS reward_points DECIMAL(10, 2) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS week_number INT;
