#!/usr/bin/env python3
"""
generate_seed_data.py

Generate 500 synthetic resume + JD pairs using Gemini for cold-start AI agent training.
Output: CSV file + database seeding ready.

Run: python backend/scripts/generate_seed_data.py
"""

import json
import os
import sys
import csv
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import google.generativeai as genai

# Configuration
GEMINI_MODEL = "gemini-1.5-flash"
BATCH_SIZE = 10  # Generate in batches to avoid rate limits
TOTAL_PAIRS = 500
OUTPUT_CSV = project_root / "backend" / "scripts" / "seed_data_pairs.csv"

# Gemini API key
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not set. Please set it in .env or environment.")

genai.configure(api_key=API_KEY)

# Few-shot examples for high-quality synthetic data
FEW_SHOT_EXAMPLE = """
Example: Software Engineer role at tech startup

Original Resume Bullet:
- Worked on backend systems

Job Description Keywords:
Python, Django, RestAPI, PostgreSQL, Docker, Kubernetes, unit testing

Rewritten Resume Bullet:
- Built 3 scalable Django REST APIs handling 10M+ requests/month, reducing response latency by 40% via PostgreSQL query optimization; containerized with Docker and deployed via Kubernetes
"""


async def generate_resume_jd_pair(pair_index: int) -> Tuple[str, str, str]:
    """
    Generate a synthetic (resume, jd, rewritten_resume) triple using Gemini.
    
    Returns:
        Tuple of (resume_text, jd_text, rewritten_resume_text)
    """
    prompt = f"""You are an expert tech recruiter and resume writer. Generate a realistic but synthetic job application scenario.

FEW-SHOT EXAMPLE:
{FEW_SHOT_EXAMPLE}

Task (Scenario {pair_index}):
1. Generate a realistic ORIGINAL RESUME (3-5 bullet points from 1-2 jobs only, impactful but generic)
2. Generate a specific JOB DESCRIPTION (tech, sales, marketing, or finance role with 8-12 key skills)
3. Generate the REWRITTEN RESUME optimized for that specific JD (same bullets but quantified, keyword-matched)

Format your response as JSON with these exact keys:
{{
    "original_resume": "- Bullet 1\\n- Bullet 2\\n- Bullet 3",
    "job_description_snippet": "Role: ... Key Skills: Python, AWS, Docker, etc. (comma-separated)",
    "rewritten_resume": "- Optimized Bullet 1\\n- Optimized Bullet 2\\n- Optimized Bullet 3"
}}

Important:
- Make the rewritten version 20-40% different (more metrics, more keywords)
- Use realistic technologies and frameworks for the year 2026
- Vary industries: include tech, finance, healthcare, marketing, operations
- ONLY output valid JSON, nothing else"""

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt, generation_config={"temperature": 0.9})
        
        # Parse JSON response
        response_text = response.text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()
        
        data = json.loads(response_text)
        
        return (
            data["original_resume"],
            data["job_description_snippet"],
            data["rewritten_resume"]
        )
    except Exception as e:
        print(f"❌ Error generating pair {pair_index}: {e}")
        return None


async def generate_seed_data(total: int = TOTAL_PAIRS) -> List[Dict]:
    """
    Generate all synthetic pairs in batches.
    """
    all_pairs = []
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_size = batch_end - batch_start
        
        print(f"\n📊 Batch {batch_idx + 1}/{batches} ({batch_start + 1}-{batch_end})...")
        
        # Generate pairs in parallel within batch
        tasks = [generate_resume_jd_pair(i) for i in range(batch_start, batch_end)]
        results = await asyncio.gather(*tasks)
        
        # Filter out failed generations + store
        for idx, result in enumerate(results):
            if result:
                original_resume, jd_snippet, rewritten_resume = result
                all_pairs.append({
                    "pair_id": batch_start + idx,
                    "original_resume": original_resume,
                    "jd_snippet": jd_snippet,
                    "rewritten_resume": rewritten_resume,
                    "rating": 5,  # All synthetic examples start at 5 stars
                    "is_synthetic": True,
                    "generated_at": datetime.now().isoformat()
                })
                print(f"  ✅ Pair {batch_start + idx + 1} generated")
        
        # Rate limit: pause between batches
        if batch_idx < batches - 1:
            print(f"  ⏸️  Waiting before next batch...")
            await asyncio.sleep(2)
    
    return all_pairs


def save_to_csv(pairs: List[Dict], output_path: Path) -> None:
    """Save generated pairs to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "pair_id", "original_resume", "jd_snippet", "rewritten_resume", 
            "rating", "is_synthetic", "generated_at"
        ])
        writer.writeheader()
        writer.writerows(pairs)
    
    print(f"\n✅ Saved {len(pairs)} pairs to {output_path}")


async def main():
    print("🚀 Starting synthetic seed data generation...")
    print(f"   Target: {TOTAL_PAIRS} resume+JD pairs")
    print(f"   Model: {GEMINI_MODEL}")
    print(f"   Output: {OUTPUT_CSV}")
    
    # Generate all pairs
    pairs = await generate_seed_data(TOTAL_PAIRS)
    
    if pairs:
        save_to_csv(pairs, OUTPUT_CSV)
        
        # Summary statistics
        print(f"\n📈 Generation Summary:")
        print(f"   Total pairs generated: {len(pairs)}")
        print(f"   Success rate: {len(pairs) / TOTAL_PAIRS * 100:.1f}%")
        print(f"   Estimated cost: ${len(pairs) * 0.000003:.2f} (at $0.075/1M input tokens)")
        print(f"\n✨ Next: Run seed_database.py to import into DB")
    else:
        print("❌ No pairs generated. Check API key and rate limits.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
