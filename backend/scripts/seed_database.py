#!/usr/bin/env python3
"""
seed_database.py

Import synthetic training data from CSV into PostgreSQL agent_training_examples table.
Also initialize prompt_weights with baseline values.

Run: python backend/scripts/seed_database.py
"""

import csv
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.database import AsyncSessionLocal

CSV_PATH = Path(__file__).parent / "seed_data_pairs.csv"

# Agent types to initialize
AGENT_TYPES = ["tailor", "coach", "interview", "matchmaker", "negotiation"]

# Initial prompt templates per agent (Version 1)
INITIAL_PROMPT_TEMPLATES = {
    "tailor": [
        "tailor_v1_basic",        # Basic rewrite
        "tailor_v1_aggressive",   # More metrics
        "tailor_v1_semantic",     # Semantic keyword matching
    ],
    "coach": [
        "coach_v1_strengths",
        "coach_v1_gaps",
        "coach_v1_actionplan",
    ],
    "interview": [
        "interview_v1_behavioral",
        "interview_v1_technical",
        "interview_v1_star",
    ],
    "matchmaker": [
        "matchmaker_v1_scoring",
    ],
    "negotiation": [
        "negotiation_v1_market_analysis",
    ],
}


async def import_csv_to_db(csv_path: Path) -> int:
    """
    Import CSV data into agent_training_examples table.
    Returns count of inserted rows.
    """
    if not csv_path.exists():
        print(f"❌ CSV not found: {csv_path}")
        print(f"   Run: python backend/scripts/generate_seed_data.py")
        return 0
    
    session = AsyncSessionLocal()
    inserted_count = 0
    
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows_to_insert = []
            
            for idx, row in enumerate(reader):
                # For Tailor Agent: mock CSV format with optional rating/is_synthetic
                rows_to_insert.append({
                    "agent_type": "tailor",
                    "input_text": row.get("original_bullet") or row.get("original_resume", ""),
                    "output_text": row.get("rewritten_bullet") or row.get("rewritten_resume", ""),
                    "rating": int(row.get("rating", 5)),  # Default to 5 stars
                    "is_synthetic": row.get("is_synthetic", "true").lower() == "true",
                })
                
                # Batch insert every 50 rows
                if (idx + 1) % 50 == 0 or idx == len(rows_to_insert) - 1:
                    await _batch_insert_training_examples(session, rows_to_insert)
                    inserted_count += len(rows_to_insert)
                    print(f"  ✅ Inserted {inserted_count} examples...")
                    rows_to_insert = []
            
            # Final batch
            if rows_to_insert:
                await _batch_insert_training_examples(session, rows_to_insert)
                inserted_count += len(rows_to_insert)
        
        print(f"✅ Imported {inserted_count} training examples from CSV")
        return inserted_count
        
    finally:
        await session.close()


async def _batch_insert_training_examples(session, rows: list) -> None:
    """Insert batch of training examples."""
    for row in rows:
        query = text("""
            INSERT INTO agent_training_examples 
            (id, agent_type, input_text, output_text, rating, is_synthetic, created_at)
            VALUES (:id, :agent_type, :input_text, :output_text, :rating, :is_synthetic, :created_at)
            ON CONFLICT (agent_type, input_text, is_synthetic) DO NOTHING
        """)
        await session.execute(query, {
            "id": str(uuid4()),
            "agent_type": row["agent_type"],
            "input_text": row["input_text"],
            "output_text": row["output_text"],
            "rating": row["rating"],
            "is_synthetic": row["is_synthetic"],
            "created_at": datetime.utcnow(),
        })
    await session.commit()


async def initialize_prompt_weights() -> int:
    """
    Initialize prompt_weights table with baseline values (1.0 for all templates).
    Returns count of inserted rows.
    """
    session = AsyncSessionLocal()
    inserted_count = 0
    
    try:
        for agent_type, templates in INITIAL_PROMPT_TEMPLATES.items():
            for template_id in templates:
                query = text("""
                    INSERT INTO prompt_weights 
                    (id, agent_type, prompt_template_id, weight, avg_reward, updated_at, week_number, created_at)
                    VALUES (:id, :agent_type, :template_id, :weight, :avg_reward, :now, :week, :now)
                    ON CONFLICT (agent_type, prompt_template_id, week_number) DO NOTHING
                """)
                await session.execute(query, {
                    "id": str(uuid4()),
                    "agent_type": agent_type,
                    "template_id": template_id,
                    "weight": 1.0,
                    "avg_reward": 0.0,
                    "week": 1,
                    "now": datetime.utcnow(),
                })
                inserted_count += 1
        
        await session.commit()
        print(f"✅ Initialized {inserted_count} prompt weight entries")
        return inserted_count
        
    finally:
        await session.close()


async def main():
    print("🌱 Starting database seeding...")
    print(f"   CSV: {CSV_PATH}")
    
    # Step 1: Import training examples
    csv_count = await import_csv_to_db(CSV_PATH)
    
    # Step 2: Initialize prompt weights
    weight_count = await initialize_prompt_weights()
    
    print(f"\n✨ Seeding complete!")
    print(f"   Training examples: {csv_count}")
    print(f"   Prompt weights: {weight_count}")
    print(f"\n📋 Next: Start Week 1 implementation tasks")


if __name__ == "__main__":
    asyncio.run(main())
