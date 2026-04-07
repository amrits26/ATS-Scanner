-- =============================================================================
-- Phase 2: The Revenue Fortress — PostgreSQL Schema Extensions (v5.0 Final Boss)
-- File: backend/migrations/002_phase2_revenue_fortress.sql
--
-- Purpose:
--   1. Stripe webhook deduplication (processed_stripe_events) — race condition proof
--   2. Email dead-letter queue (failed_email_retry) — Resend reliability
--   3. Webhook audit trail (stripe_webhook_events) — audit-grade logging
--   4. User timezone tracking + Pro status guards
--   5. Scan fear email sent flags + deferral tracking
--
-- SAFE TO RE-RUN: Uses IF NOT EXISTS / CREATE OR REPLACE
-- Rollback: See bottom of file
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Extend users table with Phase 2 fields
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS users
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255) UNIQUE;

ALTER TABLE IF EXISTS users
ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255);

ALTER TABLE IF EXISTS users
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC';

ALTER TABLE IF EXISTS users
ADD COLUMN IF NOT EXISTS last_fear_email_sent_at TIMESTAMPTZ;

ALTER TABLE IF EXISTS users
ADD COLUMN IF NOT EXISTS upgrade_source VARCHAR(100);  -- 'web', 'email_campaign', etc.

-- Index for timezone + tier queries (fear loop)
CREATE INDEX IF NOT EXISTS idx_users_timezone_tier
    ON users (timezone, tier, created_at)
    WHERE tier = 'free';


-- ---------------------------------------------------------------------------
-- 2. Extend analysis_results with fear email tracking + deferral guards
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS fear_email_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS last_fear_email_at TIMESTAMPTZ;

ALTER TABLE IF EXISTS analysis_results
ADD COLUMN IF NOT EXISTS fear_deferral_count INT DEFAULT 0;  -- Track <= 5 deferrals

-- Index for fear loop: find unsent low-score analyses
CREATE INDEX IF NOT EXISTS idx_analysis_fear_loop
    ON analysis_results (user_id, fear_email_sent, created_at DESC)
    WHERE fear_email_sent = FALSE
      AND status = 'completed';


-- ---------------------------------------------------------------------------
-- 3. processed_stripe_events — Webhook Deduplication (Race Condition Proof)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS processed_stripe_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Stripe event ID (UNIQUE constraint for deduplication)
    -- Prevents: duplicate webhook processing + double-billing
    event_id VARCHAR(255) NOT NULL UNIQUE,
    
    -- Event type (e.g., 'checkout.session.completed', 'charge.refunded')
    event_type VARCHAR(100) NOT NULL,
    
    -- Reference to user (nullable for failed sessions without user context)
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Full webhook event JSON for debugging + audit trail
    webhook_payload JSONB NOT NULL,
    
    -- Processing metadata
    idempotency_key VARCHAR(255),  -- Stripe idempotency key
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Composite index for deduplication lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_processed_stripe_events_event_id
    ON processed_stripe_events (event_id);

-- Index for cleanup queries (e.g., delete old records)
CREATE INDEX IF NOT EXISTS idx_processed_stripe_events_created_at
    ON processed_stripe_events (created_at DESC);

-- Index for user-specific webhook history
CREATE INDEX IF NOT EXISTS idx_processed_stripe_events_user
    ON processed_stripe_events (user_id, processed_at DESC)
    WHERE user_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 4. stripe_webhook_events — Full Audit Trail (Dispute Resolution)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Stripe event ID (for correlation with processed_stripe_events)
    event_id VARCHAR(255) NOT NULL,
    
    -- Event type ('checkout.session.completed', 'charge.refunded', 'customer.subscription.deleted', etc.)
    event_type VARCHAR(100) NOT NULL,
    
    -- User affected (nullable for events before user context established)
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Full event data (for audit trail + dispute resolution)
    event_data JSONB NOT NULL,
    
    -- Processing result
    status VARCHAR(50) NOT NULL,  -- 'success', 'failure', 'skipped', 'dedup'
    error_message TEXT,
    
    -- Request/Response metadata
    http_status_code INT,
    processing_duration_ms INT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for audit trail queries
CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_event_id
    ON stripe_webhook_events (event_id);

CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_user_time
    ON stripe_webhook_events (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_type_status
    ON stripe_webhook_events (event_type, status, created_at DESC);

-- Compliance: Keep audit trail for 7 years
CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_created_at
    ON stripe_webhook_events (created_at DESC);


-- ---------------------------------------------------------------------------
-- 5. failed_email_retry — Dead Letter Queue (Email Resilience)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS failed_email_retry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- User to email
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    
    -- Email type: 'welcome_pro', 'fear_notification'
    email_type VARCHAR(50) NOT NULL,
    
    -- Where to send it
    email_address VARCHAR(255) NOT NULL,
    
    -- Full email payload (to, subject, template_id, dynamic_data)
    payload JSONB NOT NULL,
    
    -- Retry tracking (max 3 retries, then mark as abandoned)
    retry_count INT DEFAULT 0,
    last_error TEXT,
    
    -- Scheduling (exponential backoff: 1m, 2m, 4m, 8m, 16m)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Resolution tracking
    resolved_at TIMESTAMPTZ,
    resolved_status VARCHAR(50),  -- 'sent', 'abandoned', 'bounced', 'user_unsubscribed'
    
    -- Observability
    last_retry_at TIMESTAMPTZ,
    last_http_code INT
);

-- Index for recovery worker (every hour)
CREATE INDEX IF NOT EXISTS idx_failed_email_retry_next_retry
    ON failed_email_retry (next_retry_at)
    WHERE resolved_at IS NULL
      AND retry_count < 3;

-- Index for admin dashboard
CREATE INDEX IF NOT EXISTS idx_failed_email_retry_user
    ON failed_email_retry (user_id, created_at DESC)
    WHERE resolved_at IS NULL;

-- Index for monitoring
CREATE INDEX IF NOT EXISTS idx_failed_email_retry_type
    ON failed_email_retry (email_type, created_at DESC)
    WHERE resolved_at IS NULL;


-- ---------------------------------------------------------------------------
-- 6. Stripe Rate Limit Tracking (Optional: for 5 req/min guard)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stripe_rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    endpoint VARCHAR(100),  -- '/create-checkout-session'
    
    -- Sliding 1-minute window
    request_count INT DEFAULT 1,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(user_id, endpoint, window_start)
);

-- Cleanup old rate limit windows
CREATE INDEX IF NOT EXISTS idx_stripe_rate_limits_window
    ON stripe_rate_limits (window_start DESC);


-- ---------------------------------------------------------------------------
-- 7. Verify UUID extension
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- =============================================================================
-- VERIFICATION QUERIES (Run after migration to verify schema)
-- =============================================================================
/*

-- Check new tables exist
SELECT tablename FROM pg_tables WHERE schemaname = 'public' 
  AND tablename IN ('processed_stripe_events', 'stripe_webhook_events', 'failed_email_retry', 'stripe_rate_limits');

-- Check users table extensions
\d users

-- Check indexes
SELECT indexname FROM pg_indexes WHERE tablename IN 
  ('processed_stripe_events', 'stripe_webhook_events', 'failed_email_retry', 'users', 'analysis_results');

*/


-- =============================================================================
-- ROLLBACK (if needed):
-- =============================================================================
/*

DROP TABLE IF EXISTS stripe_rate_limits CASCADE;
DROP TABLE IF EXISTS failed_email_retry CASCADE;
DROP TABLE IF EXISTS stripe_webhook_events CASCADE;
DROP TABLE IF EXISTS processed_stripe_events CASCADE;

ALTER TABLE IF EXISTS analysis_results DROP COLUMN IF EXISTS fear_deferral_count;
ALTER TABLE IF EXISTS analysis_results DROP COLUMN IF EXISTS last_fear_email_at;
ALTER TABLE IF EXISTS analysis_results DROP COLUMN IF EXISTS fear_email_sent;

ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS upgrade_source;
ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS last_fear_email_sent_at;
ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS timezone;
ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS stripe_subscription_id;
ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS stripe_customer_id;

*/
