#!/usr/bin/env python3
"""
Migration runner - applies SQL migrations to PostgreSQL (improved)
Usage: python backend/scripts/run_migrations_v2.py
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
                
                # Execute as a single transaction with full SQL
                try:
                    await conn.execute(text(sql_content))
                    print(f"✅ {Path(migration_path).name} completed successfully")
                except Exception as e:
                    print(f"❌ Error in migration: {str(e)[:200]}")
                    print(f"   Attempting to continue...")
                    # Don't raise, let it continue to the next migration
        
        print("\n✅ Migrations processing completed!")
        
    except Exception as e:
        print(f"❌ Fatal migration error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
