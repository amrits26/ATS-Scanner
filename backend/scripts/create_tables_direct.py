#!/usr/bin/env python3
"""Direct table creation script"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def create_tables():
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/intelliresume_ai")
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(db_url, echo=False, future=True)
    
    # Direct CREATE TABLE statements
    tables_sql = [
        # tailor_rewrite_purchases table
        """CREATE TABLE IF NOT EXISTS tailor_rewrite_purchases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID,
            email VARCHAR(255) NOT NULL,
            job_description_snippet TEXT,
            rewritten_resume_text TEXT,
            download_url VARCHAR(500),
            stripe_payment_id VARCHAR(255) UNIQUE,
            amount_cents INT DEFAULT 2900,
            status VARCHAR(50) DEFAULT 'pending',
            before_ats_score INT,
            after_ats_score INT,
            downloaded_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""",
        
        # tailor_rewrite_attempts table
        """CREATE TABLE IF NOT EXISTS tailor_rewrite_attempts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            purchase_id UUID NOT NULL,
            attempt_number INT DEFAULT 1,
            prompt_template_id VARCHAR(100),
            model_version VARCHAR(50),
            latency_ms INT,
            tokens_used INT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""",
        
        # agent_training_examples table
        """CREATE TABLE IF NOT EXISTS agent_training_examples (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_type VARCHAR(50) NOT NULL,
            input_text TEXT NOT NULL,
            output_text TEXT NOT NULL,
            rating INT CHECK (rating >= 0 AND rating <= 5),
            is_synthetic BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""",
        
        # prompt_weights table
        """CREATE TABLE IF NOT EXISTS prompt_weights (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_type VARCHAR(50) NOT NULL,
            prompt_template_id VARCHAR(100) NOT NULL,
            weight DECIMAL(5, 4) DEFAULT 1.0,
            avg_reward DECIMAL(10, 2) DEFAULT 0.0,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            week_number INT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""",
        
        # agent_decisions_log table
        """CREATE TABLE IF NOT EXISTS agent_decisions_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            agent_type VARCHAR(50) NOT NULL,
            decision_content JSONB,
            user_action VARCHAR(50),
            reward_points DECIMAL(10, 2) DEFAULT 0.0,
            week_number INT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""",
        
        # Create indexes
        """CREATE INDEX IF NOT EXISTS idx_tailor_user ON tailor_rewrite_purchases(user_id)""",
        """CREATE INDEX IF NOT EXISTS idx_agent_training_agent_type ON agent_training_examples(agent_type)""",
        """CREATE INDEX IF NOT EXISTS idx_prompt_weights_agent ON prompt_weights(agent_type)""",
        """CREATE INDEX IF NOT EXISTS idx_decisions_user ON agent_decisions_log(user_id)""",
    ]
    
    try:
        async with engine.begin() as conn:
            for i, sql in enumerate(tables_sql, 1):
                try:
                    await conn.execute(text(sql))
                    print(f"✓ Created table/index {i}/{len(tables_sql)}")
                except Exception as e:
                    print(f"⚠️  Statement {i}: {str(e)[:80]}")
        
        print("\n✅ All tables created!")
        
        # Verify
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema='public'
            """))
            count = result.scalar()
            print(f"📊 Total tables in database: {count}")
    finally:
        await engine.dispose()

asyncio.run(create_tables())
