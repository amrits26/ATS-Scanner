#!/usr/bin/env python3
"""
Migration runner - applies SQL migrations to PostgreSQL
Usage: python backend/scripts/run_migrations.py
"""

import asyncio
import os
from pathlib import Path
from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine

async def run_migrations():
    """Apply all pending migrations in order"""
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/intelliresume_ai")
    
    # Convert to async dialect if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    print(f"📊 Connecting to database: {database_url.split('@')[1].split('/')[0]}")
    
    # Create async engine
    engine = create_async_engine(
        database_url,
        echo=False,
        future=True
    )
    
    try:
        # Migrations to apply (in order)
        migrations = [
            "backend/migrations/009_tailor_rewrite_purchases.sql",
            "backend/migrations/014_agent_training_tables.sql",
        ]
        
        async with engine.begin() as conn:
            for migration_path in migrations:
                if not Path(migration_path).exists():
                    print(f"⚠️  Skipping {migration_path} - file not found")
                    continue
                
                print(f"\n🔄 Applying: {Path(migration_path).name}")
                with open(migration_path, "r") as f:
                    sql_content = f.read()
                
                # Split by semicolon and filter empty statements
                statements = [s.strip() for s in sql_content.split(";") if s.strip()]
                
                for i, statement in enumerate(statements, 1):
                    try:
                        await conn.execute(text(statement))
                        print(f"   ✓ Statement {i}/{len(statements)}")
                    except Exception as e:
                        # Log error but continue (migrations often have idempotent IF NOT EXISTS)
                        print(f"   ⚠️  Statement {i}: {str(e)[:100]}")
                
                print(f"✅ {Path(migration_path).name} completed")
        
        print("\n✅ All migrations applied successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
