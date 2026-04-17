#!/usr/bin/env python3
import asyncio
from backend.database import engine
from sqlalchemy import text

async def check_tables():
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema='public' ORDER BY table_name
        """))
        print('📋 Tables in database:')
        tables = [row[0] for row in result]
        if not tables:
            print('   ❌ No tables found!')
        for table in tables:
            print(f'   ✓ {table}')
        return len(tables)

count = asyncio.run(check_tables())
print(f'\n📊 Total tables: {count}')
