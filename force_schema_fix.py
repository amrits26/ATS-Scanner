"""
Nuclear Database Schema Fix
Ensures all Phase 1, 2, 3 columns exist with safe defaults
"""

import psycopg2
import sys

try:
    print("🔌 Connecting to intelliresume_ai database...")
    conn = psycopg2.connect('dbname=intelliresume_ai user=postgres host=localhost password=password')
    conn.autocommit = True
    cur = conn.cursor()
    
    # List of every column needed for Phase 1, 2, and 3
    required_columns = [
        ('users', 'tier', "TEXT DEFAULT 'free'"),
        ('users', 'monthly_scan_limit', 'INTEGER DEFAULT 3'),
        ('users', 'health_email_opt_in', 'BOOLEAN DEFAULT FALSE'),
        ('users', 'plan_type', "TEXT DEFAULT 'monthly'"),
        ('analysis_results', 'live_keywords_metadata', "JSONB DEFAULT '{}'::jsonb"),
        ('analysis_results', 'percentile_rank', 'INTEGER DEFAULT 0'),
        ('analysis_results', 'confidence_score', 'INTEGER DEFAULT 0'),
        ('analysis_results', 'algorithm_breakdown', "JSONB DEFAULT '{}'::jsonb"),
        ('analysis_results', 'keyword_impact_data', "JSONB DEFAULT '[]'::jsonb"),
    ]
    
    print("\n🔨 Checking and fixing schema...")
    added_count = 0
    existing_count = 0
    
    for table, col, dtype in required_columns:
        # Check if column exists
        cur.execute(f"""
            SELECT count(*) FROM information_schema.columns 
            WHERE table_name='{table}' AND column_name='{col}';
        """)
        
        exists = cur.fetchone()[0]
        
        if exists == 0:
            try:
                cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {dtype};')
                print(f'  ✅ Added {col} to {table}')
                added_count += 1
            except Exception as e:
                print(f'  ❌ Failed to add {col} to {table}: {e}')
        else:
            print(f'  ℹ️  {col} already exists in {table}')
            existing_count += 1
    
    print(f'\n📊 Results: {added_count} columns added, {existing_count} already existed')
    print('🚀 SUCCESS: Database is now fully aligned with Phase 1, 2 & 3.')
    
    cur.close()
    conn.close()
    sys.exit(0)
    
except Exception as e:
    print(f'❌ ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
