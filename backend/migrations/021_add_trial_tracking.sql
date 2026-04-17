-- Migration 021: Add trial tracking to users table
-- Supports 7-day Pro trial with Stripe trial_period_days

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN users.trial_ends_at IS 'Non-null = user has started (or completed) a free trial. Used to prevent re-trials.';

-- Index for checking active trials (e.g. cron job to expire stale trials)
CREATE INDEX IF NOT EXISTS idx_users_trial_ends_at
  ON users (trial_ends_at)
  WHERE trial_ends_at IS NOT NULL;
