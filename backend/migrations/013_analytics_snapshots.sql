-- backend/migrations/013_analytics_snapshots.sql
-- Phase 3D: Analytics snapshot table for historical tracking

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE UNIQUE NOT NULL,
    
    -- Revenue metrics
    mrr_total DECIMAL(10, 2) NOT NULL,
    mrr_email DECIMAL(10, 2) DEFAULT 0,
    mrr_coach DECIMAL(10, 2) DEFAULT 0,
    mrr_tailor DECIMAL(10, 2) DEFAULT 0,
    mrr_interview DECIMAL(10, 2) DEFAULT 0,
    mrr_pro DECIMAL(10, 2) DEFAULT 0,
    
    -- User metrics
    active_users INTEGER DEFAULT 0,
    new_users_day INTEGER DEFAULT 0,
    churned_users_day INTEGER DEFAULT 0,
    
    -- Quality metrics
    churn_rate DECIMAL(5, 4) DEFAULT 0,
    ltv_per_user DECIMAL(10, 2) DEFAULT 0,
    conversion_rate DECIMAL(5, 4) DEFAULT 0,
    
    -- Agent adoption
    coach_active_users INTEGER DEFAULT 0,
    tailor_active_users INTEGER DEFAULT 0,
    interview_active_users INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT positive_mrr CHECK (mrr_total >= 0),
    CONSTRAINT valid_rates CHECK (churn_rate >= 0 AND churn_rate <= 1)
);

-- Index for fast date lookups
CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_date 
    ON analytics_snapshots(snapshot_date DESC);

-- Index for trend queries
CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_week 
    ON analytics_snapshots(snapshot_date) 
    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '90 days';

-- Aggregated daily metrics table
CREATE TABLE IF NOT EXISTS daily_agent_metrics (
    id SERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    agent_type VARCHAR(50) NOT NULL, -- 'coach', 'tailor', 'interview'
    
    sessions_count INTEGER DEFAULT 0,
    avg_duration_seconds DECIMAL(10, 2) DEFAULT 0,
    success_rate DECIMAL(5, 4) DEFAULT 0,
    avg_cost_cents INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(metric_date, agent_type)
);

CREATE INDEX IF NOT EXISTS idx_daily_agent_metrics_date_agent 
    ON daily_agent_metrics(metric_date DESC, agent_type);

-- Revenue forecast cache (updated daily)
CREATE TABLE IF NOT EXISTS revenue_forecasts (
    id SERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    forecast_horizon_days INTEGER NOT NULL, -- 7, 30, or 90
    
    predicted_mrr DECIMAL(10, 2) NOT NULL,
    confidence_interval_low DECIMAL(10, 2),
    confidence_interval_high DECIMAL(10, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(forecast_date, forecast_horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_revenue_forecasts_date 
    ON revenue_forecasts(forecast_date DESC);
