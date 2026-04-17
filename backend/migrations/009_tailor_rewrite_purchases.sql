-- 009_tailor_rewrite_purchases.sql
-- Track Tailor Agent rewrite purchases, DOCX generation, and ATS lift metrics

CREATE TABLE IF NOT EXISTS tailor_rewrite_purchases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    email VARCHAR(255) NOT NULL,
    job_description_snippet TEXT, -- first 1000 chars of JD for reference
    rewritten_resume_text TEXT,
    download_url VARCHAR(500), -- S3 signed URL
    stripe_payment_id VARCHAR(255) UNIQUE,
    amount_cents INT DEFAULT 2900, -- $29.00
    status VARCHAR(50) DEFAULT 'pending', -- pending, processing, complete, failed
    before_ats_score INT,
    after_ats_score INT,
    downloaded_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_tailor_rewrite_purchases_user_id ON tailor_rewrite_purchases(user_id, created_at DESC);
CREATE INDEX idx_tailor_rewrite_purchases_stripe_payment_id ON tailor_rewrite_purchases(stripe_payment_id);
CREATE INDEX idx_tailor_rewrite_purchases_status ON tailor_rewrite_purchases(status, created_at DESC);
CREATE INDEX idx_tailor_rewrite_purchases_email ON tailor_rewrite_purchases(email, created_at DESC);


-- Track rewrite attempt metadata for continuous learning
CREATE TABLE IF NOT EXISTS tailor_rewrite_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id UUID NOT NULL,
    attempt_number INT DEFAULT 1,
    gemini_request JSONB, -- full request sent to Gemini
    gemini_response JSONB, -- full response from Gemini
    response_quality_score DECIMAL(3, 2), -- rated 0.0-1.0 by parser (1.0 = valid JSON + all required fields)
    tokens_input INT,
    tokens_output INT,
    cost_cents INT,
    parsed_successfully BOOLEAN DEFAULT false,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (purchase_id) REFERENCES tailor_rewrite_purchases(id) ON DELETE CASCADE
);

CREATE INDEX idx_tailor_rewrite_attempts_purchase_id ON tailor_rewrite_attempts(purchase_id);
CREATE INDEX idx_tailor_rewrite_attempts_quality ON tailor_rewrite_attempts(purchase_id, response_quality_score DESC);
