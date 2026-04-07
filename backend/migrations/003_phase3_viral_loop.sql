-- =============================================================================
-- Phase 3: The Viral Hook — PostgreSQL Schema Extension
-- File: backend/migrations/003_phase3_viral_loop.sql
--
-- Implements: Email verification, free scan tracking, referral system,
-- discount codes, bounce handling, viral coefficient tracking
--
-- HOW TO RUN:
--   psql "$DATABASE_URL" -f backend/migrations/003_phase3_viral_loop.sql
--
-- ROLLBACK:
--   psql "$DATABASE_URL" -f - << 'EOF'
--   DROP TABLE IF EXISTS referral_shares CASCADE;
--   DROP TABLE IF EXISTS referral_discounts CASCADE;
--   DROP TABLE IF EXISTS free_scans CASCADE;
--   DROP TABLE IF EXISTS free_scan_usage CASCADE;
--   DROP TABLE IF EXISTS email_bounces CASCADE;
--   ALTER TABLE users DROP COLUMN IF EXISTS email_verified;
--   ALTER TABLE users DROP COLUMN IF EXISTS email_verified_at;
--   ALTER TABLE users DROP COLUMN IF EXISTS consent_marketing;
--   ALTER TABLE users DROP COLUMN IF EXISTS consent_legal;
--   ALTER TABLE analysis_results DROP COLUMN IF EXISTS referrer_scan_id;
--   ALTER TABLE analysis_results DROP COLUMN IF EXISTS share_token;
--   ALTER TABLE analysis_results DROP COLUMN IF EXISTS og_image_url;
--   ALTER TABLE analysis_results DROP COLUMN IF EXISTS shared_at;
--   EOF
--
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Free Scan Usage Tracking (fix #3: idempotency + #2: Pro user check)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS free_scan_usage (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Link to user (email-based tracking for anonymous users)
    user_id               UUID,
    email                 VARCHAR(255) NOT NULL,
    
    -- Tracking idempotency: email + resume_hash + date prevents double-counting
    resume_hash           VARCHAR(64) NOT NULL,
    scan_date             DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Metadata
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(email, resume_hash, scan_date)  -- Idempotency constraint
);

CREATE INDEX IF NOT EXISTS idx_free_scan_usage_email_date 
    ON free_scan_usage(email, scan_date);
CREATE INDEX IF NOT EXISTS idx_free_scan_usage_user_id 
    ON free_scan_usage(user_id, scan_date);

-- ---------------------------------------------------------------------------
-- 1b. Free Scans (Fear Loop Data)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS free_scans (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    email                 VARCHAR(255) NOT NULL,
    resume_hash           VARCHAR(64) NOT NULL,
    scan_date             DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Lightweight analysis (500 words max)
    score                 INTEGER NOT NULL,  -- 1-100
    keywords              JSONB DEFAULT '[]'::jsonb,  -- Top 3 missing keywords
    
    -- Consent & metadata
    consent_given         BOOLEAN DEFAULT FALSE,
    timezone              VARCHAR(50) DEFAULT 'UTC',
    
    -- Fear loop tracking
    fear_email_sent       BOOLEAN DEFAULT FALSE,
    fear_email_sent_at    TIMESTAMP,
    
    -- Viral tracking
    referrer_scan_id      UUID,
    
    -- Conversion
    promo_code            VARCHAR(50),
    
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints: Prevent duplicate scans per email+resume per day
    UNIQUE(email, resume_hash, scan_date)
);

CREATE INDEX IF NOT EXISTS idx_free_scans_email 
    ON free_scans(email);
CREATE INDEX IF NOT EXISTS idx_free_scans_score 
    ON free_scans(score);
CREATE INDEX IF NOT EXISTS idx_free_scans_fear_sent 
    ON free_scans(fear_email_sent);

-- ---------------------------------------------------------------------------
-- 2. Email Verification & Consent (#1: email verification + legal consent)
-- ---------------------------------------------------------------------------

ALTER TABLE users 
    ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS consent_marketing BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS consent_legal BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL,
    email                 VARCHAR(255) NOT NULL,
    token                 VARCHAR(255) UNIQUE NOT NULL,
    expires_at            TIMESTAMP NOT NULL,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_verification_token 
    ON email_verification_tokens(token);
CREATE INDEX IF NOT EXISTS idx_email_verification_expires 
    ON email_verification_tokens(expires_at);

-- ---------------------------------------------------------------------------
-- 3. Email Bounce Tracking (#10: bounce handling)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS email_bounces (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                 VARCHAR(255) NOT NULL,
    bounce_type           VARCHAR(50),  -- 'permanent', 'temporary'
    bounce_reason         TEXT,
    resend_bounce_id      VARCHAR(255) UNIQUE,
    flagged_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_email_bounces_email 
    ON email_bounces(email);
CREATE INDEX IF NOT EXISTS idx_email_bounces_flagged 
    ON email_bounces(flagged_at);

-- ---------------------------------------------------------------------------
-- 4. Referral & Sharing System (#11: viral coefficient tracking)
-- ---------------------------------------------------------------------------

ALTER TABLE analysis_results 
    ADD COLUMN IF NOT EXISTS referrer_scan_id UUID,
    ADD COLUMN IF NOT EXISTS share_token VARCHAR(255) UNIQUE,
    ADD COLUMN IF NOT EXISTS og_image_url TEXT,
    ADD COLUMN IF NOT EXISTS shared_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS referral_shares (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Original scan (by referrer)
    referrer_scan_id      UUID NOT NULL,
    referrer_user_id      UUID NOT NULL,
    referrer_email        VARCHAR(255) NOT NULL,
    
    -- Share metadata
    share_token           VARCHAR(255) UNIQUE NOT NULL,
    platform              VARCHAR(50) DEFAULT 'linkedin',  -- linkedin, email, etc.
    shared_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Tracking clicks & conversions (viral coefficient)
    views_count           INTEGER DEFAULT 0,
    last_view_at          TIMESTAMP,
    
    -- Referred user (creates PRO account from link)
    referred_user_id      UUID,
    referred_email        VARCHAR(255),
    conversion_at         TIMESTAMP,
    
    FOREIGN KEY (referrer_scan_id) REFERENCES analysis_results(id) ON DELETE CASCADE,
    FOREIGN KEY (referrer_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_referral_shares_token 
    ON referral_shares(share_token);
CREATE INDEX IF NOT EXISTS idx_referral_shares_referrer 
    ON referral_shares(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_shares_referred 
    ON referral_shares(referred_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_shares_conversion 
    ON referral_shares(conversion_at);

-- ---------------------------------------------------------------------------
-- 5. Referral Discount Codes (#5: store once, reuse on retries)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_discounts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Link to share
    share_id              UUID NOT NULL UNIQUE,
    
    -- Discount code (unique per referral, reusable)
    discount_code         VARCHAR(50) UNIQUE NOT NULL,
    stripe_coupon_id      VARCHAR(255),
    
    -- Discount properties
    discount_percent      INTEGER NOT NULL DEFAULT 20,
    
    -- Validity (#6: expiry validation)
    valid_from            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until           TIMESTAMP NOT NULL,
    
    -- Tracking
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_count         INTEGER DEFAULT 0,
    
    FOREIGN KEY (share_id) REFERENCES referral_shares(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_referral_discounts_code 
    ON referral_discounts(discount_code);
CREATE INDEX IF NOT EXISTS idx_referral_discounts_expiry 
    ON referral_discounts(valid_until);

-- ---------------------------------------------------------------------------
-- 6. OG Image Generation Tracking (#7: async OG + fallback, #8: cloud storage)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS og_image_generation (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id               UUID NOT NULL UNIQUE,
    
    status                VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    
    -- Cloud storage
    bucket_path           VARCHAR(255),  -- s3://bucket/uuid or supabase path
    image_url             TEXT,
    fallback_used         BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at          TIMESTAMP,
    retry_count           INTEGER DEFAULT 0,
    
    FOREIGN KEY (scan_id) REFERENCES analysis_results(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_og_image_generation_status 
    ON og_image_generation(status);
CREATE INDEX IF NOT EXISTS idx_og_image_generation_scan_id 
    ON og_image_generation(scan_id);

-- ---------------------------------------------------------------------------
-- 7. Rate Limiting Tracking (#9: no rate limit leak)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS share_rate_limits (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL,
    email                 VARCHAR(255) NOT NULL,
    
    request_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_share_rate_limits_user_time 
    ON share_rate_limits(user_id, request_at);
CREATE INDEX IF NOT EXISTS idx_share_rate_limits_email_time 
    ON share_rate_limits(email, request_at);

-- ---------------------------------------------------------------------------
-- 8. Audit: Referral Events (PostHog tracking logs)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_events (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Event type: share_created, share_viewed, share_converted, discount_applied
    event_type            VARCHAR(50) NOT NULL,
    
    -- Actor
    user_id               UUID,
    email                 VARCHAR(255),
    
    -- Context
    share_id              UUID,
    scan_id               UUID,
    
    -- PostHog event ID (for deduplication)
    posthog_event_id      VARCHAR(255) UNIQUE,
    
    -- Metadata
    metadata              JSONB DEFAULT '{}',
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_referral_events_type 
    ON referral_events(event_type);
CREATE INDEX IF NOT EXISTS idx_referral_events_user 
    ON referral_events(user_id, created_at);

-- ---------------------------------------------------------------------------
-- Foreign Key: analysis_results.referrer_scan_id
-- ---------------------------------------------------------------------------

ALTER TABLE analysis_results 
    ADD CONSTRAINT fk_analysis_referrer_scan 
    FOREIGN KEY (referrer_scan_id) REFERENCES analysis_results(id) ON DELETE SET NULL;

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

/*
SELECT 'Phase 3 Migration' as migration, 
       COUNT(*) as tables_created
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN (
    'free_scan_usage',
    'email_bounce_tracking',
    'referral_shares',
    'referral_discounts',
    'og_image_generation',
    'share_rate_limits',
    'referral_events'
  );
*/
