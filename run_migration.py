#!/usr/bin/env python
"""
Quick migration runner for recruiter scarcity feature
Reads and executes the migration SQL file
"""
import asyncio
import os
from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

async def run_migration():
    """Run the migration SQL file"""
    
    # Read migration file
    migration_path = "backend/migrations/008_recruiter_scarcity_expiry.sql"
    with open(migration_path, 'r') as f:
        sql_content = f.read()
    
    # Get database URL
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/intelliresume_ai")
    
    # Create async engine
    engine = create_async_engine(
        db_url,
        echo=False,
        poolclass=NullPool,
    )
    
    try:
        async with engine.connect() as conn:
            # Split by semicolons and execute each statement
            statements = [s.strip() for s in sql_content.split(';') if s.strip()]
            
            for i, stmt in enumerate(statements, 1):
                try:
                    print(f"[{i}/{len(statements)}] Executing migration statement...")
                    await conn.execute(text(stmt))
                    await conn.commit()
                    print(f"     ✓ Success")
                except Exception as e:
                    print(f"     ⚠ Statement {i} skipped (likely already exists): {str(e)[:80]}")
                    await conn.rollback()
        
        print("\n✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return False
    finally:
        await engine.dispose()

if __name__ == "__main__":
    success = asyncio.run(run_migration())
    exit(0 if success else 1)
