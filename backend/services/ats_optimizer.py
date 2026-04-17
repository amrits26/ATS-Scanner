"""ATS resume optimizer: rewrite resume with better keywords and wording (no fabrication)."""

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from ..models import OptimizedResumeResponse, SectionImprovements
from ..utils.text_cleaner import clean_extracted_text

# Load environment variables and configure Gemini
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)


SYSTEM_OPT = """You are an AGGRESSIVE ATS resume optimizer. Your task is to DRAMATICALLY improve resumes for applicant tracking systems.

CRITICAL RULES:
1. Do NOT fabricate experience, jobs, or skills. Only reword and restructure what is already in the resume.
2. MUST integrate job description keywords ACTIVELY—inject at least 25% more keyword matches than original.
3. Use STRONG action verbs: Spearheaded, Architected, Optimized, Accelerated, Engineered, Designed, Developed, Delivered, Streamlined.
4. REORDER all bullet points—put the most job-matching bullets FIRST in each role.
5. Use ATS-friendly formatting: CLEAR SECTIONS, bullet points, NO icons or special characters.
6. REWRITE entire bullet points—don't just swap one word. Change structure, order, and emphasis.
7. Example transformation:
   WEAK: "Worked with Python and databases"
   STRONG: "Engineered Python-based microservices integrating PostgreSQL and Redis, reducing query latency and improving data pipeline throughput"
   NOTE: Only add metrics if they exist in the original resume. Do NOT invent numbers.
8. CRITICAL: The output MUST be noticeably different from the original by at least 25%.
9. Return STRICT JSON only. No explanations."""

USER_OPT_TEMPLATE = """CRITICAL OPTIMIZATION TASK: Aggressively rewrite this resume for the job description below.

YOU MUST MAKE SUBSTANTIAL CHANGES—not minor edits. Reorder, rephrase, restructure.

Resume (original):
---
{resume_text}
---

Job description keywords to inject (PRIORITIZE THESE):
---
{jd_excerpt}
---

REQUIRED TRANSFORMATIONS:
1. Identify 3-5 most impactful bullet points to REWRITE (not just edit)
2. Move job-matching bullets to the TOP of each job/section
3. Replace ALL weak action verbs (worked, helped, used, did) with STRONG ones (engineered, architected, spearheaded, accelerated)
4. ADD job description keywords where contextually relevant (no fabrication)
5. Result must be AT LEAST 25% different from original

BAD EXAMPLE (not acceptable):
- Original: "Worked with Python and SQL databases"
- Bad optimization: "Worked with Python and SQL databases" (SAME)

GOOD EXAMPLE (acceptable):
- Original: "Worked with Python and SQL databases"
- Good optimization: "Engineered data pipelines with Python and PostgreSQL, optimizing query performance by 35% through advanced indexing strategies"

RESPONSE FORMAT - Return STRICT JSON only:
{{
  "optimized_resume": "SUBSTANTIALLY rewritten resume (plain text, use \\n for line breaks)",
  "section_improvements": {{
    "summary": "key changes to summary section",
    "experience": "key changes to experience—explain reordering, verb upgrades, keyword injection",
    "skills": "key changes to skills section"
  }}
}}"""


async def optimize_resume(resume_text: str, jd_text: str) -> OptimizedResumeResponse:
    """Rewrite resume for ATS using JD context. With aggressive retry logic to ensure real optimization."""
    resume_clean = clean_extracted_text(resume_text)
    jd_clean = clean_extracted_text(jd_text)
    if len(resume_clean) < 30:
        return OptimizedResumeResponse(optimized_resume=resume_clean or resume_text)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return OptimizedResumeResponse(optimized_resume=resume_clean)

    jd_excerpt = (jd_clean[:6000]) if jd_clean else ""
    resume_excerpt = (resume_clean[:10000]) if resume_clean else resume_clean

    for retry_count in range(3):  # Retry up to 3 times if similarity is too high
        try:
            model = genai.GenerativeModel(
                'gemini-1.5-flash',
                generation_config={
                    "temperature": 0.7,
                    "response_mime_type": "application/json",
                },
            )
            prompt = SYSTEM_OPT + "\n\n" + USER_OPT_TEMPLATE.format(resume_text=resume_excerpt, jd_excerpt=jd_excerpt)
            resp = model.generate_content(prompt)
            content = (resp.text or "").strip()
            content = _strip_json_block(content)
            data: dict[str, Any] = json.loads(content)
            opt_text = str(data.get("optimized_resume") or "").strip().replace("\\n", "\n")
            si = data.get("section_improvements") or {}
            
            # Validate: Check similarity - accept only if <=80% similar (>20% different)
            if opt_text:
                similarity = _calculate_rewrite_similarity(resume_clean, opt_text)
                if similarity <= 0.80:  # Accept if sufficiently different (>20% changed)
                    return OptimizedResumeResponse(
                        optimized_resume=opt_text,
                        section_improvements=SectionImprovements(
                            summary=str(si.get("summary") or ""),
                            experience=str(si.get("experience") or ""),
                            skills=str(si.get("skills") or ""),
                        ),
                    )
                elif retry_count < 2:
                    # Retry if too similar
                    print(f"[ATS_OPTIMIZER] Attempt {retry_count + 1}: Similarity {similarity:.2%} too high (threshold: 80%), retrying...")
                    continue
                else:
                    # Final attempt - return even if not sufficiently different
                    print(f"[ATS_OPTIMIZER] Max retries reached, returning with similarity {similarity:.2%}")
                    return OptimizedResumeResponse(
                        optimized_resume=opt_text,
                        section_improvements=SectionImprovements(
                            summary=str(si.get("summary") or ""),
                            experience=str(si.get("experience") or ""),
                            skills=str(si.get("skills") or ""),
                        ),
                    )
            else:
                # No output from Gemini
                if retry_count < 2:
                    continue
                else:
                    return OptimizedResumeResponse(optimized_resume=resume_clean)

        except Exception as e:
            print(f"[ATS_OPTIMIZER] Error on attempt {retry_count + 1}: {e}")
            if retry_count < 2:
                continue
            else:
                return OptimizedResumeResponse(optimized_resume=resume_clean)
    
    return OptimizedResumeResponse(optimized_resume=resume_clean)


def _calculate_rewrite_similarity(original: str, rewritten: str) -> float:
    """
    Calculate similarity ratio between original and rewritten resume.
    Returns 0.0 (completely different) to 1.0 (identical).
    Threshold: Accept only if similarity <= 0.85 (meaning >15% content changed).
    """
    if not original or not rewritten:
        return 1.0
    
    # Normalize both texts for comparison
    orig_norm = " ".join(original.lower().split())
    rewr_norm = " ".join(rewritten.lower().split())
    
    if not orig_norm or not rewr_norm:
        return 1.0
    
    similarity = SequenceMatcher(None, orig_norm, rewr_norm).ratio()
    return similarity


def _strip_json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()
