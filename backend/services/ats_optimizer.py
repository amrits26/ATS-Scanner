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


SYSTEM_OPT = """You are an expert ATS resume optimizer. Your task is to substantially improve resumes for applicant tracking systems.

CRITICAL RULES:
1. Do NOT fabricate experience, jobs, or skills. Only reword and restructure what is already in the resume.
2. MUST integrate job description keywords ACTIVELY—at least 20% more keyword density than original.
3. Use STRONG action verbs (e.g., "Spearheaded", "Architected", "Optimized", "Accelerated", "Engineered").
4. Reorder bullets to prioritize keywords that match the job description FIRST.
5. Use ATS-friendly formatting: clear SECTIONS, bullet points, no icons or special characters.
6. Metrics are ONLY acceptable if implied or stated in original (e.g., "Led team" → "Led team of 5").
7. STRICT: You MUST rewrite substantial portions of the resume. DO NOT return text identical or near-identical to the original.
8. Return STRICT JSON only. No explanations."""

USER_OPT_TEMPLATE = """CRITICAL INSTRUCTION: Optimize this resume for ATS matching the job description. 

YOU MUST:
1. SUBSTANTIALLY rewrite the resume (not minimal changes)
2. Integrate at least 20% more keywords from the job description
3. Replace weak verbs with strong action verbs from the job description
4. Reorder bullets to highlight matching keywords FIRST
5. The output MUST be visibly different from the input

Resume (original):
---
{resume_text}
---

Job description (keywords to incorporate):
---
{jd_excerpt}
---

MANDATORY: Return STRICT JSON with:
- optimized_resume: SUBSTANTIALLY improved resume (plain text, use \\n for line breaks). MUST be different from original by at least 20%.
- section_improvements: {{"summary": "specific changes made", "experience": "specific changes made", "skills": "specific changes made"}}

STRICT REQUIREMENT: If the optimized_resume is too similar to the original, the optimization has FAILED. You must rewrite.
Return STRICT JSON only. No markdown, no code blocks."""


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
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = SYSTEM_OPT + "\n\n" + USER_OPT_TEMPLATE.format(resume_text=resume_excerpt, jd_excerpt=jd_excerpt)
            resp = model.generate_content(prompt)
            content = (resp.text or "").strip()
            content = _strip_json_block(content)
            data: dict[str, Any] = json.loads(content)
            opt_text = str(data.get("optimized_resume") or "").strip().replace("\\n", "\n")
            si = data.get("section_improvements") or {}
            
            # Validate: Check similarity - accept only if <=85% similar (>15% different)
            if opt_text:
                similarity = _calculate_rewrite_similarity(resume_clean, opt_text)
                if similarity <= 0.85:  # Accept if sufficiently different (>15% changed)
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
                    print(f"[ATS_OPTIMIZER] Attempt {retry_count + 1}: Similarity {similarity:.2%} too high (threshold: 85%), retrying...")
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
