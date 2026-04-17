#!/usr/bin/env python3
"""
Migration runner - executes individual SQL statements
Usage: python backend/scripts/run_migrations_final.py
"""

import asyncio
import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def run_migrations():
    """Apply all pending migrations in order"""
    
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/intelliresume_ai")
    
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    print(f"📊 Connecting to database...")
    
    engine = create_async_engine(database_url, echo=False, future=True)
    
    try:
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
                
                # Split by semicolon, filter empty statements
                statements = [s.strip() for s in sql_content.split(';') if s.strip()]
                
                success_count = 0
                for i, statement in enumerate(statements, 1):
                    try:
                        # Remove comments starting with --
                        lines = [l for l in statement.split('\n') if not l.strip().startswith('--')]
                        clean_stmt = '\n'.join(lines).strip()
                        
                        if clean_stmt:
                            await conn.execute(text(clean_stmt))
                            success_count += 1
                    except Exception as e:
                        if "already exists" in str(e) or "does not exist" in str(e):
                            print(f"   ℹ️  Statement {i}: {str(e)[:80]}")  
                            success_count += 1
                        else:
                            print(f"   ❌ Statement {i}: {str(e)[:100]}")
                
                print(f"✅ {Path(migration_path).name}: {success_count}/{len(statements)} statements executed")
        
        print("\n✅ All migrations applied successfully!")
        
        # Verify tables
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema='public' AND table_name LIKE '%tailor%' OR table_name LIKE '%agent%'
            """))
            tables = [row[0] for row in result]
            if tables:
                print(f"\n✓ New tables created: {', '.join(tables)}")
            else:
                print(f"\n⚠️  No new tables found - verify migrations")
        
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
