-- ============================================================================
-- Migration: 007_add_agency_tier.sql
-- Purpose: Add 3-tier pricing support (free/pro/agency) + user preferences
-- ============================================================================

-- 1. Add 'agency' value to user_tier ENUM
ALTER TYPE usertier ADD VALUE IF NOT EXISTS 'agency' AFTER 'pro';

-- 2. Add monthly_scan_limit column (for agency tier: 50 scans/month)
ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_scan_limit INT DEFAULT 3;

-- 3. Add health_email_opt_in toggle (for retention email job)
ALTER TABLE users ADD COLUMN IF NOT EXISTS health_email_opt_in BOOLEAN DEFAULT FALSE;

-- 4. Add plan_type to track payment method (onetime, monthly, annual)
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_type VARCHAR(50) DEFAULT 'monthly';

-- 5. Create user_preferences table for future expansion
-- (email opt-ins, notification settings, etc.)
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    email_health_check_opted_in BOOLEAN DEFAULT FALSE,
    last_health_check_sent_date DATE,
    language VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'UTC',
    notifications_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Create indices for performance
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_users_monthly_scan_limit ON users(monthly_scan_limit);

-- ============================================================================
-- Update scan_limit logic:
-- Free (tier='free'): monthly_scan_limit = 3
-- Pro (tier='pro'): monthly_scan_limit = -1 (unlimited)
-- Agency (tier='agency'): monthly_scan_limit = 50
-- ============================================================================
-- UPDATE users SET monthly_scan_limit = 3 WHERE tier = 'free';
-- UPDATE users SET monthly_scan_limit = -1 WHERE tier = 'pro';
-- UPDATE users SET monthly_scan_limit = 50 WHERE tier = 'agency';
