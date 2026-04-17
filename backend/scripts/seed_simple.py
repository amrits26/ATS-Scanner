#!/usr/bin/env python3
"""
Simple seed database script - just import CSV data
"""

import csv
import asyncio
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def seed():
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/intelliresume_ai")
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(db_url, echo=False, future=True)
    
    csv_path = Path("backend/scripts/seed_data_pairs.csv")
    
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        return
    
    print(f"🌱 Seeding database from {csv_path.name}...")
    
    async with engine.begin() as conn:
        # Read CSV and insert
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            
            for row in reader:
                sql = """
                    INSERT INTO agent_training_examples 
                    (agent_type, input_text, output_text, rating, is_synthetic)
                    VALUES (:agent_type, :input, :output, :rating, '{}')
                """.format("true")
                
                try:
                    await conn.execute(text(sql), {
                        "agent_type": "tailor",
                        "input": row.get("original_bullet", ""),
                        "output": row.get("rewritten_bullet", ""),
                        "rating": 5,  # 5 stars for all seed data
                    })
                    count += 1
                    
                    if count % 100 == 0:
                        print(f"  ✓ Inserted {count} examples...")
                except Exception as e:
                    print(f"  ⚠️  Row insert error: {str(e)[:80]}")
                    continue
        
        print(f"✅ Successfully inserted {count} training examples")
        
        # Initialize prompt weights
        print("\n📋 Initializing prompt weights...")
        weight_sql = """
            INSERT INTO prompt_weights 
            (agent_type, prompt_template_id, weight, avg_reward, week_number)
            VALUES (:agent_type, :template_id, 1.0, 0.0, 1)
            ON CONFLICT DO NOTHING
        """
        
        templates = [
            ("tailor", "tailor_v1_basic"),
            ("tailor", "tailor_v1_aggressive"),
            ("tailor", "tailor_v1_semantic"),
            ("coach", "coach_v1_strengths"),
            ("coach", "coach_v1_gaps"),
            ("interview", "interview_v1_behavioral"),
        ]
        
        for agent_type, template_id in templates:
            try:
                await conn.execute(text(weight_sql), {
                    "agent_type": agent_type,
                    "template_id": f"{agent_type}_v1",
                })
            except:
                # Insert without conflict handling
                simple_sql = f"""
                    INSERT INTO prompt_weights 
                    (agent_type, prompt_template_id, weight, avg_reward, week_number)
                    VALUES ('{agent_type}', '{template_id}', 1.0, 0.0, 1)
                """
                try:
                    await conn.execute(text(simple_sql))
                except:
                    pass  # Ignore duplicates
        
        print(f"✅ Prompt weights initialized")
    
    await engine.dispose()
    print("\n✅ Database seeding complete!")

asyncio.run(seed())
