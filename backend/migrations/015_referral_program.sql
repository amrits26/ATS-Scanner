-- Phase 7: Referral Program Tables
-- Supports viral growth with user referrals and professional affiliate program

-- Create referral_codes table
CREATE TABLE IF NOT EXISTS referral_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    code VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Viral tracking
    clicks INTEGER NOT NULL DEFAULT 0,
    signups INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    INDEX idx_referral_codes_user_id ON user_id,
    INDEX idx_referral_codes_code ON code
);

-- Create referral_conversions table
CREATE TABLE IF NOT EXISTS referral_conversions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    referral_code_used VARCHAR(50) NOT NULL,
    conversion_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Subscription details at time of conversion
    subscription_tier VARCHAR(20),  -- pro, premium
    commission_rate FLOAT NOT NULL DEFAULT 0.20,  -- 20% default
    commission_amount FLOAT NOT NULL DEFAULT 0.0,  -- Dollar amount
    
    -- Subscription tracking
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, canceled, refunded
    stripe_subscription_id VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    INDEX idx_referral_conversions_referrer_id ON referrer_id,
    INDEX idx_referral_conversions_referred_user_id ON referred_user_id,
    INDEX idx_referral_conversions_created_at ON created_at
);

-- Create trigger to auto-update updated_at on referral_conversions
CREATE OR REPLACE FUNCTION update_referral_conversions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_referral_conversions_updated_at ON referral_conversions;
CREATE TRIGGER trg_referral_conversions_updated_at
    BEFORE UPDATE ON referral_conversions
    FOR EACH ROW
    EXECUTE FUNCTION update_referral_conversions_updated_at();
